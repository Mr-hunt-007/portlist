"""Agentless remote inventory over SSH.

`portlist ssh user@host` ships Portlist itself down the SSH connection into a
temporary directory, runs one scan there, reads the JSON back and deletes it.
Nothing is installed and nothing is left behind, so a machine you only visit
occasionally still gets the full pipeline: probes run *on the remote host*, so
"localhost only" means localhost from that machine's point of view, which is
the only answer that means anything.

Requirements on the remote: an SSH login, python3, and a writable temp dir.
"""
import json
import os
import shlex
import socket
import subprocess
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAYLOAD = ["plcore", "portlist.py"]

SSH_BASE = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10"]

REMOTE_SCRIPT = (
    'set -e; d=$(mktemp -d 2>/dev/null || mktemp -d -t portlist); '
    'trap "rm -rf $d" EXIT INT TERM; '
    'tar xzf - -C "$d"; '
    '{py} "$d/portlist.py" scan --json'
)


def _bundle():
    """Tar up the parts of Portlist the remote host needs to run one scan."""
    buf = tempfile.TemporaryFile()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in PAYLOAD:
            path = os.path.join(ROOT, name)
            tar.add(path, arcname=name, filter=_skip_junk)
    buf.seek(0)
    return buf


def _skip_junk(info):
    base = os.path.basename(info.name)
    if base in ("__pycache__", ".DS_Store") or base.endswith(".pyc"):
        return None
    return info


def check(target, ssh_opts=None, python="python3"):
    """-> (ok, detail). Confirms login and a usable interpreter before shipping."""
    cmd = SSH_BASE + (ssh_opts or []) + [target,
                                         "uname -s; %s -c 'import sys;print(sys.version.split()[0])'" % python]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        return False, "timed out connecting to %s" % target
    except FileNotFoundError:
        return False, "ssh is not installed locally"
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        hint = ""
        if any("Permission denied" in l for l in err):
            hint = " (BatchMode is on, so Portlist will not prompt for a password - use a key or an agent)"
        return False, ((err[-1] if err else "ssh exited %d" % p.returncode) + hint)
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return False, "%s has no working %s on PATH" % (target, python)
    return True, {"os": lines[0], "python": lines[-1]}


def scan(target, name=None, ssh_opts=None, python="python3", timeout=180):
    """Run one full Portlist scan on a remote host. -> (payload, error)."""
    ok, detail = check(target, ssh_opts, python)
    if not ok:
        return None, detail

    cmd = SSH_BASE + (ssh_opts or []) + [target, REMOTE_SCRIPT.format(py=shlex.quote(python))]
    started = time.time()
    try:
        with _bundle() as bundle:
            p = subprocess.run(cmd, stdin=bundle, capture_output=True, text=True,
                               timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "remote scan timed out after %ds" % timeout
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        return None, (err[-1] if err else "remote scan exited %d" % p.returncode)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        head = (p.stdout or "")[:200].replace("\n", " ")
        return None, "remote did not return JSON: %s" % (head or "(no output)")

    host_name = name or _hostname_of(target, data)
    system = data.get("system") or {}
    payload = {
        "agent_version": "ssh",
        "via": "ssh",
        "target": target,
        "redacted": False,
        "host": {
            "id": host_name,
            "name": host_name,
            "os": system.get("os") or {},
            "platform": (detail or {}).get("os"),
            "addresses": (data.get("host") or {}).get("lan", []),
        },
        "summary": data.get("summary") or {},
        "rows": data.get("rows") or [],
        "system": system,
        "ai": data.get("ai") or {},
        "events": [],
        "sent_at": time.time(),
        "duration": round(time.time() - started, 1),
    }
    return payload, None


def ssh_config_hosts(path="~/.ssh/config"):
    """Host aliases from ssh_config, skipping patterns that are not real hosts."""
    path = os.path.expanduser(path)
    hosts = []
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return hosts
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition(" ")
        if key.lower() != "host":
            continue
        for alias in val.split():
            if any(c in alias for c in "*?!") or alias in hosts:
                continue
            hosts.append(alias)
    return hosts


def ssh_config_map(path="~/.ssh/config"):
    """{address: alias} so an outbound connection can be shown by the name you use."""
    path = os.path.expanduser(path)
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return {}
    out, current = {}, []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition(" ")
        key = key.lower()
        if key == "host":
            current = [a for a in val.split() if not any(c in a for c in "*?!")]
            for alias in current:                 # a bare "Host 1.2.3.4" is its own address
                out.setdefault(alias, alias)
        elif key == "hostname" and current:
            for alias in current:
                out[val.strip()] = alias
    return out


def _hostname_of(target, data):
    host = (data.get("system") or {}).get("hostname")
    if host:
        return host
    return target.split("@")[-1].split(":")[0]

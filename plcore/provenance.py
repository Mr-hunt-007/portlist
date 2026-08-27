"""Answer "why is this port open?" with a chain, not a guess.

Walks outward from the listening process: container -> orchestrator -> service
manager -> package manager -> project on disk. Every link is something that was
read off the system, and each carries the evidence that produced it.
"""
import json
import os
import re

from .platforms.base import cached, have, run, short_name

MAX_WALK_UP = 6


# ------------------------------------------------------------------ docker

@cached(30)
def _containers():
    """{published_port: container} for whatever container engine is reachable."""
    if not have("docker"):
        return {}
    out = run(["docker", "ps", "--format",
               "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Command}}"], timeout=6)
    if not out.strip():
        return {}
    by_port, ids = {}, []
    for line in out.strip().splitlines():
        p = line.split("\t")
        if len(p) < 4:
            continue
        c = {"id": p[0], "name": p[1], "image": p[2], "ports": p[3],
             "command": p[4] if len(p) > 4 else ""}
        ids.append(p[0])
        for m in re.finditer(r"(?:([\d.]+|\[::\]):)?(\d+)->(\d+)/tcp", p[3]):
            by_port[int(m.group(2))] = c
    labels = _compose_labels(ids)
    for c in by_port.values():
        c.update(labels.get(c["id"], {}))
    return by_port


def _compose_labels(ids):
    if not ids:
        return {}
    out = run(["docker", "inspect", "--format",
               "{{.Id}}\t{{index .Config.Labels \"com.docker.compose.project\"}}\t"
               "{{index .Config.Labels \"com.docker.compose.service\"}}\t"
               "{{index .Config.Labels \"com.docker.compose.project.config_files\"}}\t"
               "{{index .Config.Labels \"com.docker.compose.project.working_dir\"}}"] + ids,
              timeout=8)
    res = {}
    for line in out.strip().splitlines():
        p = line.split("\t")
        if len(p) < 5:
            continue
        cid = p[0][:12]
        res[cid] = {k: v for k, v in
                    (("compose_project", p[1]), ("compose_service", p[2]),
                     ("compose_file", p[3]), ("compose_dir", p[4])) if v and v != "<no value>"}
    return res


# ----------------------------------------------------------------- projects

# Directories that hold other people's stuff. A package.json sitting in
# ~/Downloads does not make every server under it part of a "Downloads" project.
def _junk_roots():
    home = os.path.expanduser("~")
    return {home, "/", "/tmp", "/private/tmp", "/opt", "/usr", "/usr/local",
            "/opt/homebrew", "/var", "/etc", "/Applications",
            os.path.join(home, "Downloads"), os.path.join(home, "Desktop"),
            os.path.join(home, "Documents"), os.path.join(home, "Library")}


def _find_up(start, names, limit=MAX_WALK_UP, ceiling=None):
    """Walk up from a directory looking for project markers.

    Stops at `ceiling` (normally the git root) and never accepts a marker that
    lives in a junk root, so one stray file in a home directory cannot adopt
    every service on the box.
    """
    junk, cur = _junk_roots(), start
    for _ in range(limit):
        if not cur or cur == "/":
            break
        if cur not in junk:
            for name in names:
                path = os.path.join(cur, name)
                if os.path.exists(path):
                    return path
        if ceiling and os.path.normpath(cur) == os.path.normpath(ceiling):
            break
        cur = os.path.dirname(cur)
    return None


def _git_root(cwd):
    junk, cur = _junk_roots(), cwd
    for _ in range(MAX_WALK_UP):
        if not cur or cur == "/":
            return None
        if os.path.exists(os.path.join(cur, ".git")) and cur not in junk:
            return cur
        cur = os.path.dirname(cur)
    return None


def _read_json(path, limit=200000):
    try:
        if os.path.getsize(path) > limit:
            return None
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _node_project(cwd, ceiling=None):
    pkg = _find_up(cwd, ["package.json"], ceiling=ceiling)
    if not pkg:
        return None
    data = _read_json(pkg) or {}
    return {"kind": "node", "file": pkg, "dir": os.path.dirname(pkg),
            "name": data.get("name") or os.path.basename(os.path.dirname(pkg)),
            "scripts": data.get("scripts") or {},
            "deps": sorted(list((data.get("dependencies") or {}).keys()))[:12]}


def _python_project(cwd, ceiling=None):
    marker = _find_up(cwd, ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
                      ceiling=ceiling)
    if not marker:
        return None
    name = os.path.basename(os.path.dirname(marker))
    if marker.endswith("pyproject.toml"):
        try:
            with open(marker) as f:
                txt = f.read(20000)
            m = re.search(r'^\s*name\s*=\s*["\']([^"\']+)', txt, re.M)
            if m:
                name = m.group(1)
        except OSError:
            pass
    return {"kind": "python", "file": marker, "dir": os.path.dirname(marker), "name": name}


def _git_repo(cwd):
    root = _git_root(cwd)
    if not root:
        return None
    gitdir = os.path.join(root, ".git")
    remote, branch = None, None
    cfg = os.path.join(gitdir, "config") if os.path.isdir(gitdir) else None
    if cfg and os.path.exists(cfg):
        try:
            with open(cfg) as f:
                m = re.search(r"\[remote \"origin\"\][^\[]*url\s*=\s*(\S+)", f.read())
                if m:
                    remote = m.group(1)
        except OSError:
            pass
    head = os.path.join(gitdir, "HEAD") if os.path.isdir(gitdir) else None
    if head and os.path.exists(head):
        try:
            with open(head) as f:
                ref = f.read().strip()
            branch = ref.rsplit("/", 1)[-1] if ref.startswith("ref:") else ref[:8]
        except OSError:
            pass
    return {"kind": "git", "dir": root, "name": os.path.basename(root),
            "remote": remote, "branch": branch}


def _venv(cmdline, exe):
    blob = " ".join(filter(None, [cmdline, exe]))
    m = re.search(r"([^\s]*/(?:\.venv|venv|env|virtualenv|conda/envs/[^/]+))/bin/", blob)
    return m.group(1) if m else None


# ---------------------------------------------------------- service manager

@cached(300)
def _launchd_index():
    """Map executable path -> the launchd plist that starts it (macOS)."""
    index = {}
    dirs = [os.path.expanduser("~/Library/LaunchAgents"), "/Library/LaunchAgents",
            "/Library/LaunchDaemons"]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)[:400]
        except OSError:
            continue
        for name in names:
            if not name.endswith(".plist"):
                continue
            path = os.path.join(d, name)
            try:
                if os.path.getsize(path) > 200000:
                    continue
                with open(path, "rb") as f:
                    blob = f.read().decode("utf-8", "replace")
            except OSError:
                continue
            for m in re.finditer(r"<string>([^<]{4,})</string>", blob):
                val = m.group(1)
                if "/" in val:
                    index.setdefault(os.path.basename(val), []).append(path)
    return index


def _systemd_unit(pid):
    if pid is None:
        return None
    try:
        with open("/proc/%d/cgroup" % pid) as f:
            txt = f.read()
    except OSError:
        return None
    m = re.search(r"/([\w\-.@\\]+\.service)", txt)
    if m:
        return m.group(1).replace("\\x2d", "-")
    m = re.search(r"/(docker|containerd)[-/]([0-9a-f]{12,})", txt)
    if m:
        return None
    return None


# -------------------------------------------------------------------- main

def explain(row, procs, chain_up):
    """-> {summary, chain:[{kind,label,detail,path}], evidence:[str]}"""
    port, pid = row["port"], row["pid"]
    cmdline, cwd, exe = row.get("cmdline", ""), row.get("dir", ""), row.get("exe", "")
    chain, evidence = [], []

    chain.append({"kind": "process", "label": row.get("cmd") or short_name(cmdline),
                  "detail": "pid %s, listening on :%d" % (pid, port), "path": exe or None})

    # --- container?
    names_up = " ".join(a["name"] for a in chain_up).lower()
    container = _containers().get(port)
    looks_dockery = ("docker-proxy" in (row.get("cmd") or "").lower()
                     or "dockerd" in names_up or "containerd" in names_up
                     or "com.docker" in names_up)
    if container:
        chain.append({"kind": "container", "label": "container: " + container["name"],
                      "detail": container["ports"], "path": None})
        chain.append({"kind": "image", "label": "image: " + container["image"],
                      "detail": container.get("command") or "", "path": None})
        evidence.append("docker ps publishes %d from container %s" % (port, container["name"]))
        if container.get("compose_project"):
            chain.append({"kind": "compose",
                          "label": "compose: %s / %s" % (container["compose_project"],
                                                         container.get("compose_service", "?")),
                          "detail": container.get("compose_file") or "",
                          "path": container.get("compose_dir")})
            evidence.append("container carries docker compose labels")
        return {"summary": "Published by container %s (%s)" % (container["name"], container["image"]),
                "chain": chain, "evidence": evidence}
    if looks_dockery:
        chain.append({"kind": "container", "label": "a container runtime",
                      "detail": "port is proxied by Docker, but the container list "
                                "was not readable (is the daemon running?)", "path": None})
        evidence.append("process or ancestry looks like Docker's port proxy")

    # --- service manager?
    unit = _systemd_unit(pid) if os.path.exists("/proc") else None
    if unit:
        chain.append({"kind": "service", "label": "systemd unit: " + unit,
                      "detail": "started by systemd", "path": "/etc/systemd/system/" + unit})
        evidence.append("/proc/%d/cgroup names %s" % (pid, unit))
    elif chain_up and chain_up[0]["pid"] == 1 and os.path.exists("/System"):
        hits = _launchd_index().get(os.path.basename(exe or ""), [])
        if hits:
            chain.append({"kind": "service", "label": "launchd job",
                          "detail": os.path.basename(hits[0]), "path": hits[0]})
            evidence.append("a launchd plist references this executable")
        else:
            chain.append({"kind": "service", "label": "started by launchd",
                          "detail": "parent is pid 1; no matching plist found in the "
                                    "usual LaunchAgents/LaunchDaemons directories",
                          "path": None})

    # --- how it was launched (npm run dev, uvicorn, manage.py, ...)
    launcher = None
    for anc in reversed(chain_up[:-1] if len(chain_up) > 1 else []):
        cl = anc.get("cmdline", "")
        if re.search(r"\b(npm|pnpm|yarn|bun|make|poetry|pipenv|nodemon|air|cargo)\b", cl):
            launcher = anc
            break
    if launcher:
        chain.append({"kind": "launcher", "label": launcher["cmdline"][:90],
                      "detail": "parent process (pid %d)" % launcher["pid"], "path": None})
        evidence.append("launched by pid %d: %s" % (launcher["pid"], launcher["cmdline"][:60]))

    # --- project on disk
    venv = _venv(cmdline, exe)
    git = _git_repo(cwd) if cwd else None
    ceiling = git["dir"] if git else None
    node = _node_project(cwd, ceiling) if cwd else None
    py = _python_project(cwd, ceiling) if cwd else None
    project = node or py

    if project:
        label = "project: %s" % project["name"]
        detail = os.path.basename(project["file"])
        if node and node["scripts"]:
            script = None
            for name, body in node["scripts"].items():
                if launcher and re.search(r"\brun\s+%s\b" % re.escape(name), launcher.get("cmdline", "")):
                    script = (name, body)
                    break
            if script:
                detail = "npm run %s  ->  %s" % (script[0], script[1][:60])
                evidence.append("package.json script %r matches the parent command" % script[0])
        chain.append({"kind": "project", "label": label, "detail": detail,
                      "path": project["dir"]})
    if venv:
        chain.append({"kind": "venv", "label": "virtualenv", "detail": os.path.basename(venv),
                      "path": venv})
        evidence.append("interpreter lives in %s" % venv)
    if git:
        chain.append({"kind": "git", "label": "git: %s" % git["name"],
                      "detail": " ".join(filter(None, [git.get("branch"), git.get("remote")])),
                      "path": git["dir"]})
    elif cwd:
        chain.append({"kind": "dir", "label": "working directory", "detail": "", "path": cwd})

    if project:
        summary = "%s from %s" % (
            "npm script" if (node and launcher) else "a local project", project["name"])
    elif git:
        summary = "Started from the %s checkout" % git["name"]
    elif container or looks_dockery:
        summary = "A container runtime published this port"
    elif unit:
        summary = "systemd unit %s" % unit
    elif chain_up and chain_up[0]["pid"] == 1:
        summary = "Started at boot by the system service manager"
    else:
        summary = "Started manually by %s" % (row.get("user") or "a user")
    return {"summary": summary, "chain": chain, "evidence": evidence}

"""Which container is holding this port, and which project it belongs to.

Portlist already counted containers for the System page. A count does not help
the case that actually hurts: a detached Redis from one project keeps :6379, you
bring up another project's stack, and the port is taken by something whose name
you cannot see. On macOS and Windows every published port is held by the Docker
VM's proxy, so the process behind :6379 reads as `com.docker.backend` and the
answer to "what is this?" is nothing at all.

So this maps published host ports back to the container, its image, and the
compose project it came from, and the scan hangs that on the row.

Nothing here starts, stops or removes anything. `docker ps` and `docker inspect`
are reads, and that is the whole surface.

The three states are kept apart on purpose, because collapsing them is how a
tool ends up reporting "no containers" to somebody whose daemon is simply not
running:

    engine None            docker is not installed
    reachable False        installed, daemon not answering
    containers []          answered, and there are none
"""
import re
import shutil
import subprocess
import time

TTL = 6.0
_cache = {"t": 0.0, "doc": None}

# The processes a container engine uses to hold a published host port. The row
# for such a port is the proxy, not the service, which is the whole reason this
# module exists. Used to tell that row apart from a real local process that
# happens to be listening on the same port.
PROXIES = ("com.docker.backend", "docker-proxy", "vpnkit", "orbstack", "colima",
           "qemu", "podman", "gvproxy", "rancher")

# id, name, image, state, status, created, ports, and the two compose labels.
FORMAT = ("{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}\t{{.RunningFor}}\t"
          "{{.Ports}}\t{{.Label \"com.docker.compose.project\"}}\t"
          "{{.Label \"com.docker.compose.service\"}}\t"
          "{{.Label \"com.docker.compose.project.working_dir\"}}")

# "0.0.0.0:6379->6379/tcp", "[::]:8080->80/tcp", "127.0.0.1:5432->5432/tcp",
# and the unpublished "6379/tcp", which has no host port and must not match one.
PUBLISHED = re.compile(r"(?:(?P<ip>\[[0-9a-fA-F:]+\]|[0-9.]+):)?(?P<host>\d+)->"
                       r"(?P<cport>\d+)/(?P<proto>tcp|udp)")


def _run(cmd, timeout=6):
    """-> (ok, stdout, why). Not `collect.run`, on purpose.

    `collect.run` returns stdout and swallows the exit code, so a command that
    failed is indistinguishable from one that succeeded with nothing to say. For
    most callers that is fine. Here it is the difference between "the daemon is
    not running" and "you have no containers", and reporting the first as the
    second is exactly the kind of confident wrong answer this project exists to
    avoid. It measured as `reachable: true, running: 0` against a daemon that was
    not up, which is how it was caught.
    """
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "", "%s is not on PATH" % cmd[0]
    except subprocess.TimeoutExpired:
        return False, "", "%s did not answer within %ds" % (cmd[0], timeout)
    except Exception as e:
        return False, "", str(e)[:140]
    if p.returncode != 0:
        why = (p.stderr or "").strip().splitlines()
        return False, "", (_trim(why[-1]) if why else "exit status %d" % p.returncode)
    return True, p.stdout, ""


def _trim(text, limit=160):
    """Cut at a word, not mid-word: an error ending in "con" reads like a bug
    in the error rather than the thing it is reporting."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


def _engine():
    for name in ("docker", "podman"):
        if shutil.which(name):
            return name
    return None


def _parse_ports(text):
    """Docker publishes the same mapping once for IPv4 and once for IPv6, so
    `0.0.0.0:3000->80/tcp, [::]:3000->80/tcp` is one published port, not two.
    Collapsed by (host port, container port, protocol); off-box wins, because a
    mapping reachable off this machine on either family is reachable."""
    seen = {}
    for m in PUBLISHED.finditer(text or ""):
        ip = (m.group("ip") or "").strip("[]")
        host, cport, proto = int(m.group("host")), int(m.group("cport")), m.group("proto")
        off = ip in ("", "0.0.0.0", "::")
        key = (host, cport, proto)
        cur = seen.get(key)
        if cur:
            cur["published_off_box"] = cur["published_off_box"] or off
            if off and cur["host_ip"] not in ("0.0.0.0", "::"):
                cur["host_ip"] = ip or "0.0.0.0"
            continue
        seen[key] = {"host_ip": ip or "0.0.0.0", "host_port": host,
                     "container_port": cport, "proto": proto,
                     # A container published on 0.0.0.0 is reachable from the LAN
                     # even though the process behind it looks local.
                     "published_off_box": off}
    return list(seen.values())


def parse(lines, engine="docker"):
    """Split `docker ps` output into rows. Pure, so it can be tested without a daemon."""
    rows = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        parts += [""] * (10 - len(parts))
        cid, name, image, state, status, age, ports, project, service, workdir = parts[:10]
        rows.append({
            "id": cid[:12], "name": name, "image": image,
            "state": (state or "").lower(), "status": status, "running_for": age,
            "engine": engine,
            "project": project or None, "service": service or None,
            "dir": workdir or None,
            "ports": _parse_ports(ports),
        })
    return rows


def inventory(ttl=TTL):
    """-> {engine, reachable, containers, note}. Never returns [] for "cannot see"."""
    now = time.time()
    if _cache["doc"] is not None and now - _cache["t"] < ttl:
        return _cache["doc"]
    engine = _engine()
    if not engine:
        doc = {"engine": None, "reachable": False, "containers": [],
               "note": "no container engine on this machine"}
        _cache.update(t=now, doc=doc)
        return doc
    ok, out, why = _run([engine, "ps", "-a", "--no-trunc", "--format", FORMAT])
    if not ok:
        doc = {"engine": engine, "reachable": False, "containers": [], "error": why,
               "note": "%s is installed but its daemon did not answer, so containers "
                       "are not being reported. That is not the same as there "
                       "being none." % engine}
        _cache.update(t=now, doc=doc)
        return doc
    rows = parse(out.splitlines(), engine)
    doc = {"engine": engine, "reachable": True, "containers": rows,
           "running": sum(1 for c in rows if c["state"] == "running"),
           "total": len(rows), "note": ""}
    _cache.update(t=now, doc=doc)
    return doc


def by_port(doc=None):
    """-> {host_port: container} for running containers that publish one."""
    doc = doc if doc is not None else inventory()
    table = {}
    for c in doc.get("containers") or []:
        if c["state"] != "running":
            continue
        for p in c["ports"]:
            table.setdefault(p["host_port"], dict(c, published=p))
    return table


def is_proxy(row):
    """-> True, False, or None when it genuinely cannot be told.

    Two processes can share a port: the engine publishing :8000 from a container
    and your own `python -m http.server 8000` on 127.0.0.1. Attaching the
    container to both said the local one was the container, which is the kind of
    confident wrong answer that makes people stop the wrong thing.

    The three-state return matters more than it looks. The old version fell back
    to "a proxy has no working directory of its own", which is also true of every
    process whose directory Portlist is not allowed to read - another user's
    process, or one in a restricted path. That made a stale, unreadable process
    on a shared port inherit the compose project of whatever container happened
    to publish that port: a repo label attached to something that has nothing to
    do with the repo. Unknown is now its own answer, and the caller must decide
    what to do with it rather than being handed a guess.
    """
    hay = ((row.get("cmd") or "") + " " + (row.get("cmdline") or "")).lower()
    if any(p in hay for p in PROXIES):
        return True
    d = row.get("dir")
    if d:
        # It has a working directory of its own, so it is a real local service.
        return d == "/"
    # No name match and nothing readable to go on.
    return None


def summarise(c):
    """The one line that replaces `com.docker.backend` on a row."""
    if not c:
        return ""
    where = ("%s in %s" % (c.get("service") or c["name"], c["project"])
             if c.get("project") else c["name"])
    return "%s container %s (%s)" % (c.get("engine", "docker"), where, c["image"])


def projects(doc=None):
    """Containers grouped by their compose project, so a stack reads as a stack."""
    doc = doc if doc is not None else inventory()
    groups = {}
    for c in doc.get("containers") or []:
        key = c.get("project") or "(no compose project)"
        g = groups.setdefault(key, {"project": c.get("project"), "dir": c.get("dir"),
                                    "containers": [], "ports": [], "running": 0})
        g["containers"].append(c)
        if c["state"] == "running":
            g["running"] += 1
            g["ports"] += [p["host_port"] for p in c["ports"]]
    for g in groups.values():
        g["ports"] = sorted(set(g["ports"]))
    return [dict(v, key=k) for k, v in sorted(groups.items())]

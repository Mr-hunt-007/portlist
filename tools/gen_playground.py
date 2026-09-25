#!/usr/bin/env python3
"""Build the playground's simulated machines: docs/play/data.js and harbour.html.

    python3 tools/gen_playground.py

The playground at docs/play/ runs in a browser with no portlist behind it, so
everything it shows is computed here, by portlist's own code, from two made-up
machines: the answers to `portlist <port>` come from plcore.explain, and the
harbour snapshot from plcore.world. Nothing here is anyone's real computer: host
names are invented, addresses are from the documentation ranges (192.0.2.0/24,
198.51.100.0/24, 203.0.113.0/24).

The harbour page itself is copied from plcore/data/world.html so the playground
never drifts from the real one; in the browser it notices it was not served by
portlist and asks the playground for its data instead.
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from plcore import explain, world  # noqa: E402

OUT = os.path.join(ROOT, "docs", "play")
# a fixed moment, so the same code always builds the same bytes (CI checks that it does)
NOW = 1_790_000_000.0
DAY = 86400


# ------------------------------------------------------------------ building blocks
def row(port, pid, service, cmd, cmdline, *, user="you", project=None, cat="Dev server", sid=None,
        up=3600, exposure="loopback", addrs=None, verified=None, conns=0, conns_public=0, risk=12,
        band="Info", reasons=(), leftover=None, starter=None, idle=None, ever_busy=True, quiet=False,
        container=None, depends=(), exe=None):
    lvl_label = {"loopback": "Localhost only", "all": "All interfaces", "lan": "One network"}[exposure]
    return {
        "id": "%d-%d" % (port, pid), "port": port, "pid": pid, "ppid": 1, "user": user,
        "cmd": cmd, "cmdline": cmdline, "exe": exe or "", "service": service, "service_id": sid,
        "service_cat": cat, "uptime": up, "started": NOW - up, "first_seen": NOW - up,
        "dir": (project or {}).get("path", ""), "dir_short": (project or {}).get("short", ""),
        "project": {"name": project["name"], "short": project["short"], "path": project["path"]} if project else None,
        "exposure": {"level": exposure, "label": lvl_label, "addrs": addrs or (["127.0.0.1"] if exposure == "loopback" else ["0.0.0.0"]),
                     "verified": verified},
        "activity": {"known": True, "ever_busy": ever_busy, "idle_seconds": idle, "watched_for": max(up, 600),
                     "samples": 20, "busy_samples": 10 if ever_busy else 0},
        "conns": conns, "conns_public": conns_public, "health": "up", "health_label": "answering",
        "risk": risk, "risk_band": band, "reasons": [{"points": 0, "label": r} for r in reasons],
        "leftover": leftover or {"likely": False, "reasons": []},
        "starter": starter or {}, "origin": {"live": starter} if starter else {},
        "quiet": quiet, "container": container, "depends_on": list(depends), "used_by": [],
        "url": "http://localhost:%d" % port,
    }


def agent(name, kind, alive, pid=None, cls="AI agent"):
    return {"name": name, "kind": kind, "class": cls, "ai": cls.startswith("AI"), "alive": alive, "pid": pid,
            "evidence": "its environment carries %s" % ("CLAUDECODE" if kind == "claude-code" else kind.upper())}


def reach(ip, iface):
    return {"accepting": True, "ip": ip, "iface": iface}


def proj(name, where):
    return {"name": name, "short": "~/code/%s" % where, "path": "/home/you/code/%s" % where}


# ------------------------------------------------------------------ the two machines
def devbox():
    """A developer laptop an agent has been busy on."""
    claude_now = agent("Claude Code", "claude-code", True, 901)
    claude_gone = agent("a Claude Code session", "claude-code", False)
    term = agent("a terminal", "shell", True, 700, "terminal")
    lead = [{"pid": 1, "name": "launchd"}]
    rows = [
        (row(3000, 4123, "Next.js", "node", "node node_modules/.bin/next dev -p 3000", project=proj("storefront", "storefront"),
             sid="nextjs", up=2 * 3600, conns=3, idle=40, starter=claude_now, depends=["5432-2211"]),
         lead + [{"pid": 812, "name": "zsh"}, {"pid": 901, "name": "claude"}, {"pid": 4100, "name": "npm"}], ["CLAUDECODE"]),
        (row(5173, 4480, "Vite", "node", "node node_modules/.bin/vite", project=proj("admin-ui", "admin-ui"), sid="vite",
             up=5 * 3600, idle=3 * 3600, starter=term),
         lead + [{"pid": 700, "name": "zsh"}], []),
        (row(8787, 4412, "Python http.server", "python3", "python3 -m http.server 8787 --bind 0.0.0.0",
             project=proj("data-export", "data-export"), sid="python-http", cat="File server", up=5 * DAY,
             exposure="all", addrs=["0.0.0.0"], verified=reach("192.0.2.14", "en0"), risk=71, band="High",
             reasons=["serves files from a project directory", "reachable from the network", "no authentication"],
             leftover={"likely": True, "reasons": ["a dev server that has been running for 5 days",
                                                   "nothing has connected to it in the 5 days portlist has been watching"]},
             ever_busy=False, starter=claude_gone),
         lead + [{"pid": 4412, "name": "python3"}], ["CLAUDECODE"]),
        (row(5432, 2211, "PostgreSQL", "postgres", "postgres -D /var/lib/postgresql/data", cat="Database", sid="postgres",
             up=2 * DAY, conns=4, idle=40, container="shop-db-1", project=proj("storefront", "storefront"),
             starter=agent("Docker", "docker", True, 150, "runtime")),
         lead + [{"pid": 150, "name": "com.docker.backend"}], []),
        (row(6379, 2240, "Redis", "redis-server", "redis-server *:6379", cat="Cache", sid="redis", up=2 * DAY,
             conns=1, idle=300, container="shop-cache-1", starter=agent("Docker", "docker", True, 150, "runtime")),
         lead + [{"pid": 150, "name": "com.docker.backend"}], []),
        (row(11434, 610, "Ollama", "ollama", "ollama serve", cat="AI model", sid="ollama", up=9 * DAY, idle=2 * DAY,
             starter=agent("launchd", "launchd", True, 1, "service manager")),
         lead, []),
        (row(5000, 380, "AirPlay Receiver", "ControlCenter", "/System/Library/CoreServices/ControlCenter.app", cat="System",
             sid="airplay", up=20 * DAY, quiet=True, starter=agent("launchd", "launchd", True, 1, "service manager")),
         lead, []),
    ]
    return {"key": "devbox", "title": "Developer laptop", "user": "you", "host": "devbox", "os": "macOS 15",
            "lan": "192.0.2.14", "blurb": "Claude Code has been busy here: a Next.js app with its database and cache in "
            "Docker, a Vite server, a local model, and a file server from a session that ended five days ago.",
            "tutorial": True, "rows": rows,
            "groups": [{"key": "claude-code:901", "name": "Claude Code", "class": "AI agent", "kind": "claude-code", "ai": True,
                        "alive": True, "pid": 901, "services": [{"id": "3000-4123"}], "ports": [3000]},
                       {"key": "claude-code:-", "name": "a Claude Code session", "class": "AI agent", "kind": "claude-code",
                        "ai": True, "alive": False, "pid": None, "services": [{"id": "8787-4412"}], "ports": [8787]}],
            "containers": [{"id": "c1", "name": "shop-db-1", "image": "postgres:16", "state": "running", "status": "Up 2 days",
                            "project": "storefront", "service": "db", "ports": [{"host_port": 5432}]},
                           {"id": "c2", "name": "shop-cache-1", "image": "redis:7", "state": "running", "status": "Up 2 days",
                            "project": "storefront", "service": "cache", "ports": [{"host_port": 6379}]}],
            "traffic": [{"key": "198.51.100.%d" % i, "address": "198.51.100.%d" % i, "alias": None, "apps": [a], "services": ["HTTPS"],
                         "ports": [443], "scope": "public", "count": n} for i, (a, n) in enumerate([("Google Chrome", 6), ("Code", 2), ("claude", 3)], 1)],
            "islands": [], "inbound": []}


def web1():
    """A small staging server. Some of this is meant to be public; one thing is not."""
    systemd = agent("systemd", "systemd", True, 1, "service manager")
    lead = [{"pid": 1, "name": "systemd"}]
    rows = [
        (row(443, 1200, "nginx", "nginx", "nginx: master process /usr/sbin/nginx", user="root", cat="Web server", sid="nginx",
             up=40 * DAY, exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), conns=18, conns_public=18,
             idle=2, risk=30, band="Low", reasons=["public web server"], starter=systemd),
         lead, []),
        (row(8080, 2310, "Node / Express", "node", "node /srv/api/server.js", user="deploy", project={"name": "api", "short": "/srv/api", "path": "/srv/api"},
             sid="express", cat="App server", up=12 * DAY, conns=5, idle=1,
             starter=agent("PM2", "pm2", True, 2300, "service manager")),
         lead + [{"pid": 2300, "name": "PM2 v5.3.1: God"}], []),
        (row(5432, 900, "PostgreSQL", "postgres", "postgres -D /var/lib/postgresql/16/main", user="postgres", cat="Database",
             sid="postgres", up=40 * DAY, exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), conns=6,
             conns_public=1, idle=5, risk=88, band="Critical",
             reasons=["a database reachable from the internet", "a connection from a public address right now"], starter=systemd),
         lead, []),
        (row(6379, 1500, "Redis", "redis-server", "redis-server 127.0.0.1:6379", user="redis", cat="Cache", sid="redis",
             up=40 * DAY, conns=2, idle=10, starter=systemd),
         lead, []),
        (row(22, 800, "OpenSSH", "sshd", "sshd: /usr/sbin/sshd -D", user="root", cat="Remote access", sid="ssh", up=90 * DAY + 3600,
             exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), conns=1, conns_public=1, idle=0,
             risk=20, band="Low", reasons=["remote login, key-only"], starter=systemd),
         lead, []),
        (row(4444, 3777, "unknown", "kworkerd", "/tmp/.x/kworkerd -p 4444", user="deploy", cat=None, up=2 * DAY,
             exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), risk=64, band="High",
             reasons=["an unrecognised program reachable from the internet", "runs from /tmp"], ever_busy=False,
             exe="/tmp/.x/kworkerd"),
         lead + [{"pid": 3770, "name": "sh"}], ["LD_PRELOAD"]),
    ]
    return {"key": "web1", "title": "Staging server", "user": "deploy", "host": "web-1", "os": "Ubuntu 24.04",
            "lan": "203.0.113.20", "blurb": "A small staging server: nginx in front, a PM2 app, Postgres and Redis, "
            "and SSH. Some of it is meant to be public. Some of it is not.", "tutorial": False, "rows": rows,
            "groups": [], "containers": [], "traffic": [],
            "islands": [], "inbound": [{"direction": "inbound", "lport": 22, "raddr": "198.51.100.77", "rport": 51522,
                                        "scope": "public", "pid": 800}]}


# ------------------------------------------------------------------ computing
def machine(m):
    rows = [r for r, _, _ in m["rows"]]
    det = {}
    for r, chain, env in m["rows"]:
        det[r["pid"]] = {"tree": {"ancestry": chain + ([] if chain and chain[-1]["pid"] == r["pid"] else [{"pid": r["pid"], "name": r["cmd"]}]),
                                  "children": []},
                         "provenance": {"summary": "a local project from %s" % r["project"]["name"] if r.get("project")
                                        else ("started by %s" % (r["starter"] or {}).get("name", "nobody on record"))},
                         "environ_names": env}
    # the playground never measures: memory and history come from the scenario
    explain._rss = lambda pid: {4412: 38 << 20, 900: 1600 << 20, 4123: 410 << 20}.get(pid, 64 << 20)
    explain._restarts = lambda port, service, now: 0
    answers = {str(r["pid"]): explain.explain(r, det[r["pid"]], now=NOW) for r in rows}
    listing = [explain.list_row(r) for r in sorted(rows, key=lambda r: r["port"]) if not r.get("quiet")]
    sysinfo = {"hostname": m["host"], "os": {"pretty": m["os"]}, "uptime": 9 * DAY,
               "cpu": {"load_pct": 22.0, "model": "simulated", "cores": 8, "load": [1.4, 1.2, 1.1]},
               "memory": {"pct": 58.0, "used": 9 << 30, "total": 16 << 30},
               "disks": [{"mount": "/", "pct": 61.0, "free": 180 << 30, "total": 460 << 30}],
               "processes": {"count": 312}, "network": {"interfaces": []}}
    hostinfo = {"hostname": m["host"], "lan": [{"ip": m["lan"]}], "firewall": {"enabled": True, "name": "Firewall", "stealth": False}}
    # the model words a few things per platform: word them for the simulated machine, not the one building it
    real_platform, sys.platform = sys.platform, "darwin" if m["os"].startswith("macOS") else "linux"
    try:
        snap = _build(m, rows, hostinfo, sysinfo)
    finally:
        sys.platform = real_platform
    tasks = world.plan_pets(snap, [], now=NOW)
    return _finish(m, rows, answers, listing, snap, tasks)


def _build(m, rows, hostinfo, sysinfo):
    return world.build(rows, hostinfo, m["groups"], {"engine": "docker" if m["containers"] else None,
                       "reachable": bool(m["containers"]), "note": "", "containers": m["containers"]},
                       {"sessions": []}, sysinfo, [], now=NOW, outbound=m["islands"], conns=m["inbound"], traffic=m["traffic"])


def _finish(m, rows, answers, listing, snap, tasks):
    doc = dict(snap, events=[], seq=1, pets=tasks, chatter=world.chatter(tasks, snap), history=[], stdio_mcp=[], fleet=[])
    lsof = [{"cmd": r["cmd"][:9], "pid": r["pid"], "user": r["user"], "port": r["port"],
             "addr": (r["exposure"]["addrs"] or ["*"])[0].replace("0.0.0.0", "*")} for r in sorted(rows, key=lambda r: r["port"])]
    return {"key": m["key"], "title": m["title"], "user": m["user"], "host": m["host"], "os": m["os"], "blurb": m["blurb"],
            "tutorial": m["tutorial"], "answers": answers, "listing": listing, "lsof": lsof, "world": doc,
            "system_pids": [r["pid"] for r in rows if r.get("quiet")]}


def main():
    os.makedirs(OUT, exist_ok=True)
    data = {"machines": [machine(devbox()), machine(web1())]}
    with open(os.path.join(OUT, "data.js"), "w", encoding="utf-8") as f:
        f.write("// Generated by tools/gen_playground.py from portlist's own code. Do not edit.\n")
        f.write("window.PLAY = " + json.dumps(data, separators=(",", ":"), default=str) + ";\n")
    src = open(os.path.join(ROOT, "plcore", "data", "world.html"), encoding="utf-8").read()
    with open(os.path.join(OUT, "harbour.html"), "w", encoding="utf-8") as f:
        f.write(src)
    print("wrote docs/play/data.js (%d bytes) and docs/play/harbour.html" % os.path.getsize(os.path.join(OUT, "data.js")))


if __name__ == "__main__":
    main()

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plcore import agents, explain, report, stop, world  # noqa: E402

import playtui  # noqa: E402  (tools/, next to this file)

OUT = os.path.join(ROOT, "docs", "play")
from plcore.app import VERSION  # noqa: E402
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
        "project": {"key": project["path"], "name": project["name"], "short": project["short"], "path": project["path"]} if project else None,
        "exposure": {"level": exposure, "label": lvl_label, "addrs": addrs or (["127.0.0.1"] if exposure == "loopback" else ["0.0.0.0"]),
                     "verified": verified},
        "activity": {"known": True, "ever_busy": ever_busy, "idle_seconds": idle, "watched_for": max(up, 600),
                     "samples": 20, "busy_samples": 10 if ever_busy else 0},
        "conns": conns, "conns_public": conns_public, "health": "up", "health_label": "answering",
        "risk": risk, "risk_band": band, "reasons": [{"points": pts, "label": lab} for lab, pts in reasons],
        "leftover": leftover or {"likely": False, "reasons": []},
        "starter": starter or {}, "origin": {"live": starter, "observed": True, "started_at": NOW - up} if starter else {},
        "quiet": quiet, "container": container, "depends_on": list(depends), "used_by": [],
        "url": "http://localhost:%d" % port, "probe": {"http": cat not in ("Database", "Cache", "Remote access")},
        "why": "; ".join(lab for lab, _ in reasons) if reasons else ("%s, local to this machine" % (cat or "a program").lower()
                                                   if exposure == "loopback" else (cat or "a program").lower()),
        "ai": cat == "AI model", "mcp": False, "is_new": False, "blast": None,
    }


def agent(name, kind, alive, pid=None, cls="AI agent"):
    return {"name": name, "kind": kind, "class": cls, "ai": cls.startswith("AI"), "alive": alive, "pid": pid,
            "evidence": "its environment carries %s" % ("CLAUDECODE" if kind == "claude-code" else kind.upper())}


def reach(ip, iface):
    return {"accepting": True, "ip": ip, "iface": iface,
            "note": "accepted a connection on %s (%s) just now" % (ip, iface)}


def proj(name, where):
    return {"name": name, "short": "~/code/%s" % where, "path": "/home/you/code/%s" % where}


def out_web(ip, alias, app, port=443, svc="HTTPS", kind="web", count=1):
    """An outbound connection as the scanner reports it: one remote host."""
    return {"address": ip, "alias": alias, "processes": [{"name": app}], "services": [svc],
            "ports": [{"port": port, "service": svc, "kind": kind}], "scope": "public", "count": count}


def out_ssh(ip, alias, pid, port=22, svc="SSH"):
    return {"address": ip, "alias": alias, "ssh": svc == "SSH", "ports": [{"port": port, "service": svc}],
            "processes": [{"pid": pid, "name": "ssh" if svc == "SSH" else "psql"}], "scope": "public", "count": 1}


def ssh_in(ip, rport, pid=800):
    return {"direction": "inbound", "lport": 22, "raddr": ip, "rport": rport, "scope": "public", "pid": pid}


def mcp(name, pid, starter):
    return {"name": name, "pid": pid, "cmd": "npx -y @modelcontextprotocol/server-" + name, "starter": starter}


def box(cid, name, image, service, state="running", status="Up 2 days", ports=()):
    return {"id": cid, "name": name, "image": image, "state": state, "status": status, "project": "storefront",
            "service": service, "ports": [{"host_port": p} for p in ports]}


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
             reasons=[("Listening on all interfaces (0.0.0.0)", 42), ("Static file server exposing its working directory off-box", 15),
                      ("No authentication seen and reachable off-box", 14)],
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
            "tutorial": True, "rows": rows, "sessions": _devbox_sessions(),
            "units": {}, "labels": {610: "homebrew.mxcl.ollama"},
            "events": [(40, {"type": "opened", "text": "Next.js opened on :3000 (Localhost only)"}),
                       (1300, {"type": "closed", "text": "Storybook on :6006 stopped listening"}),
                       (3 * 3600, {"type": "opened", "text": "Vite opened on :5173 (Localhost only)"}),
                       (2 * 3600, {"type": "closed", "text": "Redis on :6380 stopped listening"})],
            "groups": [{"key": "claude-code:901", "name": "Claude Code", "class": "AI agent", "kind": "claude-code", "ai": True,
                        "alive": True, "pid": 901, "services": [{"id": "3000-4123"}], "ports": [3000]},
                       {"key": "claude-code:-", "name": "a Claude Code session", "class": "AI agent", "kind": "claude-code",
                        "ai": True, "alive": False, "pid": None, "services": [{"id": "8787-4412"}], "ports": [8787]}],
            "life": _devbox_life(claude_now)}


def _devbox_life(claude):
    """A few minutes on a laptop, on a loop: what comes and goes around the
    services while nobody touches them. Web traffic drives in and out, a mail
    check sails in, an SSH session to the staging box goes out and comes back,
    a worker container starts and exits, and the agent's MCP servers, which hold
    no port, surface and dive."""
    db, cache = box("c1", "shop-db-1", "postgres:16", "db", ports=[5432]), box("c2", "shop-cache-1", "redis:7", "cache", ports=[6379])
    worker = box("c3", "shop-worker-1", "storefront-worker:dev", "worker", status="Up 4 seconds")
    worker_done = dict(worker, state="exited", status="Exited (0) 6 seconds ago")
    chrome = out_web("198.51.100.10", "www.example.com", "Google Chrome", count=6)
    claude_api = out_web("198.51.100.20", "api.anthropic.com", "claude", count=3)
    code = out_web("198.51.100.30", "github.com", "Code", count=2)
    push = out_web("198.51.100.40", "push.apple.com", "apsd", port=5223, svc="APNs", kind="push")
    mail = out_web("198.51.100.50", "imap.example.com", "Mail", port=993, svc="IMAPS", kind="mail")
    npm = out_web("198.51.100.60", "registry.npmjs.org", "node", count=4)
    to_web1 = out_ssh("203.0.113.20", "web-1", 5120)
    fs, gh, pw = mcp("filesystem", 9101, claude), mcp("github", 9102, claude), mcp("playwright", 9103, claude)
    return [
        {"traffic": [chrome, claude_api, code, push], "outbound": [], "inbound": [], "containers": [db, cache], "stdio": [fs, gh]},
        {"traffic": [chrome, claude_api, code, push, mail, npm], "outbound": [], "inbound": [], "containers": [db, cache, worker],
         "stdio": [fs, gh, pw]},
        {"traffic": [chrome, claude_api, push, mail, npm], "outbound": [to_web1], "inbound": [], "containers": [db, cache, worker],
         "stdio": [fs, gh, pw]},
        {"traffic": [chrome, claude_api, code, push], "outbound": [to_web1], "inbound": [], "containers": [db, cache, worker_done],
         "stdio": [fs, gh, pw]},
        {"traffic": [chrome, claude_api, code, push], "outbound": [], "inbound": [], "containers": [db, cache], "stdio": [fs, gh]},
    ]


def _devbox_sessions():
    def sess(sid, tool, title, project, ctx, turns, ago, live=False, model=None, first=None, summary=None):
        return {"id": sid, "tool": tool, "title": title, "project": project, "cwd": "/Users/you/code/" + project,
                "context": ctx, "turns": turns, "last_active": NOW - ago, "live": live,
                "live_pids": [901] if live else [], "ambiguous": False, "model": model,
                "first_prompt": first or title, "summary": summary}
    return {"processes": [{"pid": 901, "name": "claude", "cwd": "/Users/you/code/storefront"}],
            "accounts": [{"name": "Claude Code", "tool": "claude-code", "plan": "Max", "model": "claude-opus-5-5",
                          "signed_in": True},
                         {"name": "Codex", "tool": "codex", "plan": "Plus", "signed_in": True}],
            "sessions": [
                sess("5f0c9a1e-storefront", "claude", "Add checkout page and wire it to the orders API", "storefront",
                     184000, 96, 40, live=True, model="claude-opus-5-5",
                     summary="checkout page renders, orders API returns 201, next: payment webhook"),
                sess("a2d77be0-admin-ui", "codex", "Fix the date picker in the admin filters", "admin-ui",
                     61000, 22, 3 * 3600),
                sess("0b31e6c4-data-export", "claude", "Export last month's orders to CSV and serve it so I can "
                     "download it on my phone", "data-export", 412000, 140, 5 * DAY, model="claude-sonnet-5",
                     summary="started python3 -m http.server 8787 --bind 0.0.0.0 for the phone download"),
                sess("7c19f2aa-storefront", "claude", "Set up Postgres and Redis in docker compose", "storefront",
                     233000, 71, 2 * DAY, model="claude-opus-5-5"),
            ]}


def _hist(seed):
    """A minute of made-up samples: smooth, bounded, the same every build."""
    import math
    cpu = [round(18 + 9 * math.sin((i + seed) / 5.0) + 4 * math.sin(i / 1.7), 1) for i in range(60)]
    mem = [round(57 + 2 * math.sin((i + seed) / 11.0), 1) for i in range(60)]
    net = [int(40000 + 30000 * abs(math.sin((i + seed) / 4.0))) for i in range(60)]
    return {"cpu": cpu, "mem": mem, "net": net}


def web1():
    """A small staging server. Some of this is meant to be public; one thing is not."""
    systemd = agent("systemd", "systemd", True, 1, "service manager")
    lead = [{"pid": 1, "name": "systemd"}]
    rows = [
        (row(443, 1200, "nginx", "nginx", "nginx: master process /usr/sbin/nginx", user="root", cat="Web server", sid="nginx",
             up=40 * DAY, exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), conns=18, conns_public=18,
             idle=2, risk=30, band="Low", reasons=[("Public web server, meant to be reachable", 30)], starter=systemd),
         lead, []),
        (row(8080, 2310, "Node / Express", "node", "node /srv/api/server.js", user="deploy", project={"name": "api", "short": "/srv/api", "path": "/srv/api"},
             sid="express", cat="App server", up=12 * DAY, conns=5, idle=1,
             starter=agent("PM2", "pm2", True, 2300, "service manager")),
         lead + [{"pid": 2300, "name": "PM2 v5.3.1: God"}], []),
        (row(5432, 900, "PostgreSQL", "postgres", "postgres -D /var/lib/postgresql/16/main", user="postgres", cat="Database",
             sid="postgres", up=40 * DAY, exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), conns=6,
             conns_public=1, idle=5, risk=88, band="Critical",
             reasons=[("Database listening on all interfaces", 50), ("Reachable from the internet, verified", 28),
                      ("A connection from a public address right now", 10)], starter=systemd),
         lead, []),
        (row(6379, 1500, "Redis", "redis-server", "redis-server 127.0.0.1:6379", user="redis", cat="Cache", sid="redis",
             up=40 * DAY, conns=2, idle=10, starter=systemd),
         lead, []),
        (row(22, 800, "OpenSSH", "sshd", "sshd: /usr/sbin/sshd -D", user="root", cat="Remote access", sid="ssh", up=90 * DAY + 3600,
             exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), conns=1, conns_public=1, idle=0,
             risk=20, band="Low", reasons=[("Remote login, key-only", 20)], starter=systemd),
         lead, []),
        (row(4444, 3777, "unknown", "kworkerd", "/tmp/.x/kworkerd -p 4444", user="deploy", cat=None, up=2 * DAY,
             exposure="all", addrs=["0.0.0.0"], verified=reach("203.0.113.20", "eth0"), risk=64, band="High",
             reasons=[("Unrecognised program reachable from the internet", 40), ("Runs from /tmp", 24)], ever_busy=False,
             exe="/tmp/.x/kworkerd"),
         lead + [{"pid": 3770, "name": "sh"}], ["LD_PRELOAD"]),
    ]
    return {"key": "web1", "title": "Staging server", "user": "deploy", "host": "web-1", "os": "Ubuntu 24.04",
            "lan": "203.0.113.20", "blurb": "A small staging server: nginx in front, a PM2 app, Postgres and Redis, "
            "and SSH. Some of it is meant to be public. Some of it is not.", "tutorial": False, "rows": rows, "sessions": {"sessions": [], "processes": [], "accounts": []},
            "units": {1200: "nginx.service", 900: "postgresql.service", 1500: "redis-server.service", 800: "ssh.service"},
            "labels": {},
            "events": [(25, {"type": "opened", "text": "a connection to :5432 from 198.51.100.77"}),
                       (2 * DAY, {"type": "opened", "text": "kworkerd opened on :4444 (All interfaces)"}),
                       (12 * DAY, {"type": "opened", "text": "Node / Express opened on :8080 (Localhost only)"})],
            "groups": [], "life": _web1_life()}


def _web1_life():
    """The staging box on a loop: people log in over SSH and leave, the nightly
    replica connection comes and goes, the app calls out and goes quiet."""
    you, ci = ssh_in("198.51.100.77", 51522), ssh_in("198.51.100.90", 40110, 812)
    apt = out_web("203.0.113.80", "archive.ubuntu.com", "apt", port=80, svc="HTTP")
    hook = out_web("203.0.113.90", "hooks.example.net", "node", count=2)
    replica = out_ssh("203.0.113.30", "db-replica", 2400, port=5432, svc="PostgreSQL")
    return [
        {"traffic": [hook], "outbound": [], "inbound": [you], "containers": [], "stdio": []},
        {"traffic": [hook, apt], "outbound": [], "inbound": [you, ci], "containers": [], "stdio": []},
        {"traffic": [apt], "outbound": [replica], "inbound": [ci], "containers": [], "stdio": []},
        {"traffic": [hook], "outbound": [replica], "inbound": [], "containers": [], "stdio": []},
    ]


# ------------------------------------------------------------------ computing
def _link(rows, containers):
    """depends_on as the scanner writes it: edges both ways, not bare ids."""
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        c = next((c for c in containers if c["name"] == r["container"]), None) if r["container"] else None
        if c:
            r["container"] = {"id": c["id"], "name": c["name"], "image": c["image"], "project": c["project"],
                              "service": c["service"], "engine": "docker", "status": c["status"],
                              "container_port": c["ports"][0]["host_port"], "published_off_box": False,
                              "summary": "%s (%s), %s" % (c["name"], c["image"], c["status"].lower())}
    for r in rows:
        ids, r["depends_on"] = r["depends_on"], []
        for i in ids:
            t = by_id[i]
            r["depends_on"].append({"id": t["id"], "pid": t["pid"], "name": t["service"], "port": t["port"],
                                    "conns": 2, "project": (t.get("project") or {}).get("name")})
            t["used_by"].append({"id": r["id"], "pid": r["pid"], "name": r["service"], "port": r["port"],
                                 "listening": True, "conns": 2, "project": (r.get("project") or {}).get("name")})


def machine(m):
    rows = [r for r, _, _ in m["rows"]]
    m["containers"] = m["life"][0]["containers"]
    _link(rows, m["containers"])
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
               "processes": {"count": 312}}
    live = [r for r in rows if not r.get("quiet")]
    iface = "en0" if m["os"].startswith("macOS") else "eth0"
    sysinfo.update({
        "network": {"interfaces": [{"name": "lo0"}, {"name": iface}], "rx_rate": 48000,
                    "addresses": [{"iface": iface, "ip": m["lan"], "scope": "lan"}]},
        "ports": {"listening": len(live), "exposed": sum(1 for r in live if r["exposure"]["level"] != "loopback"),
                  "critical": sum(1 for r in live if r["risk_band"] == "Critical"),
                  "high": sum(1 for r in live if r["risk_band"] == "High"), "ai": sum(1 for r in live if r["ai"])},
        "security": {"firewall": {"enabled": m["os"].startswith("macOS"), "stealth": False},
                     "ssh": any(r["port"] == 22 for r in live)},
        "containers": {"engine": "docker" if m["containers"] else None, "reachable": bool(m["containers"])}})
    hostinfo = {"hostname": m["host"], "lan": [{"ip": m["lan"]}], "firewall": {"enabled": True, "name": "Firewall", "stealth": False}}
    # the model words a few things per platform: word them for the simulated machine, not the one building it
    real_platform, sys.platform = sys.platform, "darwin" if m["os"].startswith("macOS") else "linux"
    try:
        snap = _build(m, rows, hostinfo, sysinfo)
        beats, beat_events = _life(m, rows, hostinfo, sysinfo, snap)
        tui = _screens(m, rows, hostinfo, sysinfo)
    finally:
        sys.platform = real_platform
    tasks = world.plan_pets(snap, [], now=NOW)
    out = _finish(m, rows, answers, listing, snap, tasks)
    out["tui"] = tui
    out["stops"], out["cleanup"], out["report"] = _stops(m, rows, det, hostinfo, sysinfo)
    out["beats"], out["beat_events"] = beats, beat_events
    return out


def _screens(m, rows, hostinfo, sysinfo):
    """The terminal program's screens, for every combination of services the
    visitor can stop: `kill` in the playground changes what the views show, so
    each state is painted by the real code rather than patched up in the page."""
    import itertools
    killable = sorted(r["pid"] for r in rows if not r.get("quiet"))
    table = {"lines": [], "index": {}}
    states = {}
    for n in range(len(killable) + 1):
        for gone in itertools.combinations(killable, n):
            left = [r for r in rows if r["pid"] not in gone]
            live = [r for r in left if not r.get("quiet")]
            alive = {r["starter"].get("pid") for r in live if (r.get("starter") or {}).get("alive")}
            stdio = m["life"][0]["stdio"]
            alive |= {x["starter"]["pid"] for x in stdio}
            si = dict(sysinfo, ports=dict(sysinfo["ports"], listening=len(live),
                      exposed=sum(1 for r in live if r["exposure"]["level"] != "loopback"),
                      critical=sum(1 for r in live if r["risk_band"] == "Critical"),
                      high=sum(1 for r in live if r["risk_band"] == "High"),
                      ai=sum(1 for r in live if r["ai"])))
            states[",".join(map(str, gone))] = playtui.frames({
                "rows": left, "host": hostinfo, "groups": agents.groups(live, procs=alive, stdio=stdio, now=NOW),
                "stdio": stdio,
                "containers": {"engine": "docker" if m["containers"] else None, "reachable": bool(m["containers"]),
                               "containers": m["containers"]},
                "sessions": m["sessions"], "sysinfo": si, "hist": _hist(len(rows)),
                "events": [dict(e, ts=NOW - ago) for ago, e in m["events"]]}, NOW, table)
    return {"size": [playtui.W, playtui.H], "lines": table["lines"], "states": states}


def _build(m, rows, hostinfo, sysinfo, beat=None):
    beat = beat or m["life"][0]
    cons = beat["containers"]
    engine = "docker" if any(x["containers"] for x in m["life"]) else None
    snap = world.build(rows, hostinfo, m["groups"], {"engine": engine, "reachable": bool(engine), "note": "", "containers": cons},
                       {"sessions": []}, sysinfo, [], now=NOW, outbound=world.sea_destinations(beat["outbound"]),
                       conns=beat["inbound"], traffic=world.traffic_endpoints(beat["traffic"]))
    snap["stdio_mcp"] = [{"name": x["name"], "pid": x["pid"]} for x in beat["stdio"]]
    return snap


def _life(m, rows, hostinfo, sysinfo, base):
    """-> [{changed fields}, ...] per beat, and the events the harbour's own
    differ reports on the way into each one (the last beat wraps to the first)."""
    import json as _json
    snaps = [base] + [_build(m, rows, hostinfo, sysinfo, b) for b in m["life"][1:]]
    d = world.Differ()
    events = [None] * len(snaps)
    for i in list(range(len(snaps))) + [0]:
        got = d.feed(snaps[i], now=NOW)
        if events[i] is None or got:
            events[i] = [{k: v for k, v in e.items() if k not in ("seq", "ts")} for e in got]
    keys = ("traffic", "islands", "lighthouse", "yard", "stdio_mcp", "stats", "conditions", "gate")
    beats = [{k: s[k] for k in keys if k in s and _json.dumps(s[k], sort_keys=True, default=str)
              != _json.dumps(base.get(k), sort_keys=True, default=str)} for s in snaps]
    return beats, events


def _stops(m, rows, det, hostinfo, sysinfo):
    """How `portlist kill` would stop each listener here, from portlist's own
    supervisor detection, fed the units and launchd labels this machine has;
    which listeners `portlist cleanup` would offer; and the report page."""
    saved = stop._cgroup_unit, stop._launchd_label, stop.os.geteuid
    stop._cgroup_unit = lambda pid: ("system", m["units"][pid]) if pid in m["units"] else None
    stop._launchd_label = lambda pid: m["labels"].get(pid)
    stop.os.geteuid = lambda: 1000                       # the visitor is not root
    try:
        plans = {}
        for r in rows:
            sup = stop.supervisor(r, det[r["pid"]]["tree"]["ancestry"])
            plans[str(r["pid"])] = ({"command": " ".join(sup["command"]) if sup["command"] else None,
                                     "runnable": bool(sup["runnable"] and sup["command"]), "note": sup["note"],
                                     "kind": sup["kind"]} if sup else None)
    finally:
        stop._cgroup_unit, stop._launchd_label, stop.os.geteuid = saved
    cleanup = [r["pid"] for r in stop.candidates(rows)]
    name = "report-%s.html" % m["key"]
    for redact, path in ((False, name), (True, name.replace(".html", "-redacted.html"))):
        with playtui.Clock(NOW):
            page = report.build(rows, hostinfo, sysinfo, det, redact=redact, now=NOW, version=VERSION)
        with open(os.path.join(OUT, path), "w", encoding="utf-8") as f:
            f.write(page)
    return plans, cleanup, name


def _finish(m, rows, answers, listing, snap, tasks):
    doc = dict(snap, events=[], seq=1, pets=tasks, chatter=world.chatter(tasks, snap), history=[], fleet=[])
    lsof = [{"cmd": r["cmd"][:9], "pid": r["pid"], "user": r["user"], "port": r["port"],
             "addr": (r["exposure"]["addrs"] or ["*"])[0].replace("0.0.0.0", "*")} for r in sorted(rows, key=lambda r: r["port"])]
    return {"key": m["key"], "title": m["title"], "user": m["user"], "host": m["host"], "os": m["os"], "blurb": m["blurb"],
            "tutorial": m["tutorial"], "answers": answers, "listing": listing, "lsof": lsof, "world": doc,
            "system_pids": [r["pid"] for r in rows if r.get("quiet")]}


def main():
    os.makedirs(OUT, exist_ok=True)
    data = {"version": VERSION, "machines": [machine(devbox()), machine(web1())]}
    with open(os.path.join(OUT, "data.js"), "w", encoding="utf-8") as f:
        f.write("// Generated by tools/gen_playground.py from portlist's own code. Do not edit.\n")
        f.write("window.PLAY = " + json.dumps(data, separators=(",", ":"), default=str) + ";\n")
    src = open(os.path.join(ROOT, "plcore", "data", "world.html"), encoding="utf-8").read()
    with open(os.path.join(OUT, "harbour.html"), "w", encoding="utf-8") as f:
        f.write(src)
    print("wrote docs/play/data.js (%d bytes) and docs/play/harbour.html" % os.path.getsize(os.path.join(OUT, "data.js")))


if __name__ == "__main__":
    main()

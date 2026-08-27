"""One pass: sockets -> processes -> fingerprint -> exposure -> risk -> history."""
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import (access, activity, catalog, collect, containers, depends,
               fingerprint, fix, graph as graph_mod, history, ledger, lifecycle,
               mcp as mcp_mod, names as names_mod, posture,
               projects as projects_mod, provenance, recipes as recipes_mod, risk)

# Background OS/editor plumbing - real, but not what you are looking for.
QUIET_CATS = {"macOS service", "Editor tooling"}
QUIET_IDS = {"rapportd", "vscode", "airplay"}

_lock = threading.Lock()
_verify_cache = {}
_mcp_cache = {}
_MCP_TTL = 90.0
_VERIFY_TTL = 60.0
_last = {"t": 0, "rows": [], "host": None, "stdio_mcp": []}

# Portlist watches for resource problems, so it should be able to prove it is
# not one. Every scan records what it cost.
_stats = {"scans": 0, "total_ms": 0.0, "last_ms": 0.0, "max_ms": 0.0,
          "last_probes": 0, "started": time.time(), "requests": 0, "bytes": 0}
_MIN_INTERVAL = 2.0
_recipes_at = 0.0
_RECIPE_EVERY = 30.0
_REFRESH_AFTER = 4.0        # older than this and a background refresh starts
_refreshing = threading.Event()


def _verify(level, port, host):
    # Keyed by (level, port): two processes can share a port with different bind
    # scopes, and a loopback row's None must not become the wildcard row's answer.
    key = (level, port)
    hit = _verify_cache.get(key)
    now = time.time()
    if hit and now - hit[0] < _VERIFY_TTL:
        return hit[1]
    val = risk.verify_exposure(level, port, host)
    _verify_cache[key] = (now, val)
    return val


def _mcp_for(port, sig_id, cmdline, pr):
    """Enumerate MCP capabilities, but only where there is a reason to look.

    Never fired at an arbitrary service: it needs either a process that looks
    like an MCP server, or an endpoint that answers a GET the way an MCP
    endpoint does. Enumeration is read-only - no tool is ever invoked.
    """
    if not pr.get("http"):
        return None
    looks = sig_id == "mcp" or any(
        re.search(pat, cmdline or "") for pat in mcp_mod.STDIO_PATTERNS)
    if not looks and sig_id not in (None, "express", "nextjs", "bun", "uvicorn", "vite"):
        return None
    now = time.time()
    hit = _mcp_cache.get(port)
    if hit and now - hit[0] < _MCP_TTL:
        return hit[1]
    try:
        info = mcp_mod.enumerate_server(port, tls=bool(pr.get("https")))
    except Exception:
        info = None
    _mcp_cache[port] = (now, info)
    return info


# Every `except Exception: pass` in a scan is a decision to keep serving data
# rather than fail the whole request, which is right - a broken container daemon
# must not take the port list down with it. What was wrong was that the failure
# then vanished. `lifecycle.sentence()` raised NameError on every row for an
# unknown length of time and nothing anywhere said so. These are kept, capped,
# and served at /api/health so a swallowed error is a visible one.
_problems = {}
MAX_PROBLEMS = 40


def note_problem(where, exc):
    key = "%s: %s" % (where, type(exc).__name__)
    slot = _problems.get(key)
    if slot:
        slot["count"] += 1
        slot["last"] = time.time()
        return
    if len(_problems) >= MAX_PROBLEMS:
        return
    _problems[key] = {"where": where, "error": "%s: %s" % (type(exc).__name__, exc),
                      "count": 1, "first": time.time(), "last": time.time()}


def problems():
    return sorted(_problems.values(), key=lambda p: -p["last"])


def _project_of(row):
    """The cheap half of provenance: the repository or directory a service came
    from. The full chain is still built on demand in detail()."""
    cwd = row.get("dir") or ""
    if not cwd:
        return None
    git = None
    try:
        git = provenance._git_root(cwd)
    except Exception:
        git = None
    path = git or cwd
    # A service whose working directory is /opt/homebrew is not part of a
    # "homebrew project". The same junk-root rule provenance uses applies here.
    try:
        junk = provenance._junk_roots()
    except Exception:
        junk = {"/"}
    if path in junk or path.startswith("/System") or path.startswith("/Library"):
        return None
    return {"key": path, "name": os.path.basename(path) or path, "path": path,
            "short": short_dir(path), "kind": "git repository" if git else "directory"}


def short_dir(path):
    home = os.path.expanduser("~")
    if path and path.startswith(home):
        return "~" + path[len(home):]
    return path or ""


def scan(force=False):
    """Return the inventory immediately; refresh it behind the request.

    A poll that blocks on a full re-probe makes the dashboard feel slow for no
    benefit: the data it would wait for is at most one poll newer. Only an
    explicit rescan blocks, and only the very first call has nothing to serve.
    """
    now = time.time()
    if not force and _last["rows"]:
        age = now - _last["t"]
        if age >= _REFRESH_AFTER and not _refreshing.is_set():
            _refreshing.set()
            threading.Thread(target=_refresh_bg, daemon=True).start()
        return _last["rows"], _last["host"]
    return _scan_now(force=force)


def _refresh_bg():
    try:
        _scan_now(force=True)
    except Exception:
        pass
    finally:
        _refreshing.clear()


def _scan_now(force=False):
    with _lock:
        now = time.time()
        if not force and now - _last["t"] < _MIN_INTERVAL and _last["rows"]:
            return _last["rows"], _last["host"]
        if force:
            collect.invalidate()
        _t0 = time.time()

        socks = collect.listening()
        procs = collect.processes()
        host = collect.host()
        # A pid of None is a socket whose owner we are not allowed to see. It
        # still gets a row; it just has nothing to look up in /proc.
        pids = sorted({s["pid"] for s in socks if s["pid"] is not None})
        dirs = collect.cwds(pids)
        exes = collect.exe_paths(pids)
        conns = collect.established()

        merged = {}
        for s in socks:
            key = (s["pid"], s["port"])
            e = merged.setdefault(key, {"pid": s["pid"], "cmd": s["cmd"],
                                        "port": s["port"], "addrs": set()})
            e["addrs"].add(s["addr"])

        holders = {}
        for e in merged.values():
            holders[e["port"]] = holders.get(e["port"], 0) + 1

        # When two sockets share a port, the more specific bind wins for its own
        # address. Probing everything at 127.0.0.1 would hand one socket's
        # response to the other, which is how a wildcard row ended up showing a
        # loopback server's page next to its own directory.
        lan_ips = [a["ip"] for a in host.get("lan", [])]
        loopback_owner = {}
        for e in merged.values():
            if any(a in collect.LOOPBACK for a in e["addrs"]):
                loopback_owner[e["port"]] = e["pid"]

        targets = []
        for e in merged.values():
            probe_host = None
            if holders[e["port"]] > 1:
                owns_loopback = any(a in collect.LOOPBACK for a in e["addrs"])
                if not owns_loopback and loopback_owner.get(e["port"]) not in (None, e["pid"]):
                    # Someone else owns 127.0.0.1 here; this socket answers on the
                    # network address instead.
                    probe_host = next((ip for ip in lan_ips), None)
            e["probe_host"] = probe_host
            targets.append((e["port"], probe_host))

        with ThreadPoolExecutor(max_workers=24) as pool:
            list(pool.map(lambda t: fingerprint.probe(t[0], t[1]), set(targets)))

        rows = []
        for e in merged.values():
            pid, port = e["pid"], e["port"]
            proc = procs.get(pid, {})
            pr = fingerprint.probe(port, e.get("probe_host"))
            cmdline = proc.get("cmdline", "")
            sig, conf, evidence = fingerprint.resolve(cmdline, e["cmd"], port, pr)
            mcp_info = _mcp_for(port, sig["id"] if sig else None, cmdline, pr)
            if mcp_info and not (sig and sig["id"] == "mcp"):
                sig = catalog.BY_ID["mcp"]                # the handshake outranks a guess
                conf = max(conf, catalog.W_BODY + catalog.W_PATH)
                evidence = list(evidence) + [
                    ("mcp", "completed an MCP initialize handshake on %s" % mcp_info["endpoint"])]

            level = risk.classify_exposure(e["addrs"])
            exposure = dict(risk.EXPOSURE[level])
            exposure["addrs"] = sorted(e["addrs"])
            exposure["verified"] = _verify(level, port, host)

            cwd = dirs.get(pid, "")
            row = {
                # A listener owned by another user comes back with no pid on
                # Linux: visible socket, invisible process. That is a real state,
                # not an error, so the row keeps its identity without one.
                "id": ("%d-%d" % (port, pid)) if pid is not None else "%d-nopid" % port,
                "port": port, "pid": pid, "ppid": proc.get("ppid"),
                "cmd": e["cmd"], "cmdline": cmdline,
                "exe": exes.get(pid, ""), "user": proc.get("user", ""),
                "cpu": proc.get("cpu"), "mem": proc.get("mem"),
                "uptime": proc.get("uptime"), "started": proc.get("started"),
                "dir": cwd, "dir_short": short_dir(cwd),
                "service": sig["name"] if sig else None,
                "service_id": sig["id"] if sig else None,
                "service_cat": sig["cat"] if sig else None,
                "service_note": (sig or {}).get("note"),
                "sensitivity": (sig or {}).get("sensitivity", "low"),
                "ai": bool((sig or {}).get("ai")),
                "confidence": conf,
                "evidence": [{"kind": k, "text": t} for k, t in evidence],
                "exposure": exposure,
                "probe": {k: v for k, v in pr.items() if not k.startswith("_")},
                "conns": len(conns.get(pid, [])),
                "conns_public": sum(1 for c in conns.get(pid, []) if c["scope"] == "public"),
                "mcp": mcp_info,
                "shared": holders[port] > 1,
                "answers_on": (pr.get("probed_at") or "127.0.0.1"),
                "serves_url": "%s://%s:%d" % ("https" if pr.get("https") else "http",
                                              pr.get("probed_at") or "localhost", port),
                "url": "%s://localhost:%d" % ("https" if pr.get("https") else "http", port),
                # Addresses another device on this network could actually open.
                # Only for binds that accept off-box: a localhost URL on a phone
                # is a broken promise, not a convenience.
                "lan_urls": ([] if level == "loopback" else
                             ["%s://%s:%d" % ("https" if pr.get("https") else "http",
                                              a["ip"], port) for a in host.get("lan", [])]),
            }
            st, label, detail = health_of(row)
            row["health"] = st
            row["health_label"] = label
            row["health_detail"] = detail
            row["service_sig"] = sig          # scoring needs the signature...
            row["risk"], row["risk_band"], row["reasons"] = risk.score(row, host)
            row.pop("service_sig")             # ...but it must not reach the JSON
            row["quiet"] = bool(sig and (sig["cat"] in QUIET_CATS or sig["id"] in QUIET_IDS)) or (
                not sig and not pr.get("http") and port >= 49152)
            rows.append(row)

        # What each of these could reach if it were taken. Exposure says who can
        # get in; this says what is behind the door.
        stdio_pids = [pid for pid, p_ in procs.items()
                      if any(re.search(pat, p_.get("cmdline") or "")
                             for pat in mcp_mod.STDIO_PATTERNS)]
        dirs_for_stdio = collect.cwds(stdio_pids) if stdio_pids else {}

        try:
            envs = collect.environs({r["pid"] for r in rows} | set(procs))
        except Exception:
            envs = {}
        for r in rows:
            names = envs.get(r["pid"], [])
            try:
                r["access"] = access.analyse(r, names, env_readable=r["pid"] in envs,
                                             conns=conns.get(r["pid"], []))
            except Exception as e:                 # access analysis never breaks a scan
                r["access"] = {"error": str(e)[:120], "credentials": [], "paths": [],
                               "radius": [], "overall": "unknown",
                               "credentials_readable": False, "tool_capabilities": []}
            a = r["access"]
            r["blast"] = {"overall": a.get("overall"), "creds": len(a.get("credentials") or []),
                          "caps": len(a.get("tool_capabilities") or []),
                          "paths": len(a.get("paths") or []),
                          "readable": a.get("credentials_readable", False)}

        # Who started it, what project it belongs to, and whether anyone still
        # wants it. All three are cheap dictionary and stat work on top of data
        # already collected, so they belong in the row rather than behind a
        # second request that some surfaces would forget to make.
        for r in rows:
            chain = collect.ancestry(r["pid"], procs)
            try:
                r["starter"] = lifecycle.starter(r, chain, envs.get(r["pid"], []))
            except Exception as e:
                r["starter"] = None
                note_problem("lifecycle.starter", e)
            try:
                r["project"] = _project_of(r)
            except Exception as e:
                r["project"] = None
                note_problem("scan._project_of", e)
            try:
                r["why"] = lifecycle.sentence(r, None, r["starter"], chain)
            except Exception as e:
                r["why"] = None
                note_problem("lifecycle.sentence", e)
        # The recipe book learns from the scan, but writing a file on every poll
        # would be a disk write every few seconds for data that rarely changes.
        global _recipes_at
        try:
            if now - _recipes_at > _RECIPE_EVERY:
                recipes_mod.observe(rows)
                _recipes_at = now
            book = recipes_mod._load()
        except Exception:
            book = {}
        for r in rows:
            try:
                e = book.get(recipes_mod.key_for(r))
            except Exception:
                e = None
            r["recipe"] = ({"name": e.get("name"), "notes": e.get("notes"),
                            "adopted": bool(e.get("adopted")), "key": e.get("key"),
                            "ports": e.get("ports") or [],
                            "moved": recipes_mod._moved(e)} if e else None)

        # What needs what. A loopback connection from one service into another's
        # port is the only evidence of a local dependency that is not a guess
        # from names, and it is half the answer to "why is this running".
        try:
            depends.build(rows, connections_all(2000))
        except Exception as e:
            note_problem("depends.build", e)
            for r in rows:
                r.setdefault("depends_on", [])
                r.setdefault("used_by", [])

        # Containers: on macOS and Windows every published port is held by the
        # Docker VM's proxy, so without this a container-backed service reads as
        # `com.docker.backend` and the row cannot say what it actually is.
        try:
            cdoc = containers.inventory()
            cmap = containers.by_port(cdoc)
        except Exception as e:
            note_problem("containers.inventory", e)
            cdoc, cmap = {"engine": None, "reachable": False, "containers": []}, {}
        shared_ports = {}
        for r in rows:
            shared_ports[r["port"]] = shared_ports.get(r["port"], 0) + 1
        for r in rows:
            c = cmap.get(r["port"])
            # Two processes can hold one port: the engine publishing a container
            # on 0.0.0.0 and your own server on 127.0.0.1. Only the proxy is the
            # container; badging both said the local one was the container too.
            #
            # `is_proxy` can also answer None - no name match and no readable
            # working directory. On a shared port that has to mean "badge
            # nothing", not "probably the proxy": guessing there attaches a
            # compose project, and therefore a repo label, to a process that may
            # have nothing to do with it.
            if c and shared_ports.get(r["port"], 1) > 1:
                verdict = containers.is_proxy(r)
                if verdict is not True:
                    c = None
                    if verdict is None:
                        r["container_ambiguous"] = (
                            "another process holds :%d and a container publishes it; "
                            "this one's working directory is not readable, so which "
                            "of them is the container cannot be told apart"
                            % r["port"])
            # A published container port is held by the engine's proxy, whose
            # working directory is "/" and belongs to no project at all. The
            # compose project IS this service's project, and saying so is the
            # difference between four containers filed under "/" and a stack.
            if c and c.get("project") and (not r.get("project")
                                           or (r.get("project") or {}).get("name") == "/"):
                cdir = c.get("dir")
                r["project"] = {"key": cdir or ("compose:" + c["project"]),
                                "name": c["project"], "path": cdir or "",
                                "short": short_dir(cdir) if cdir else
                                         ("compose project " + c["project"]),
                                "kind": "compose project", "from_container": True}
            r["container"] = ({"id": c["id"], "name": c["name"], "image": c["image"],
                               "project": c.get("project"), "service": c.get("service"),
                               "dir": c.get("dir"), "engine": c.get("engine"),
                               "running_for": c.get("running_for"),
                               "status": c.get("status"),
                               "container_port": c["published"]["container_port"],
                               "published_off_box": c["published"]["published_off_box"],
                               "summary": containers.summarise(c)} if c else None)

        # The sentence was built before the container was known, and for a
        # published container port the process behind it is the engine's proxy.
        # Rebuild those, now that there is something better to say than
        # "started by launchd running OrbStack Helper".
        for r in rows:
            if not r.get("container"):
                continue
            try:
                r["why"] = lifecycle.sentence(r, None, r.get("starter"),
                                              collect.ancestry(r["pid"], procs))
            except Exception:
                pass

        # Use, as opposed to uptime. One sample per scan; the record is keyed by
        # command signature so it survives the service restarting.
        try:
            activity.observe(rows)
            for r in rows:
                r["activity"] = activity.of(r, now)
            activity.flush()
        except Exception as e:
            note_problem("activity", e)
            for r in rows:
                r.setdefault("activity", None)

        # The launch ledger. Runs after the starter, the project and the
        # container are known, because all three go into the birth record, and
        # before the leftover score, which is allowed to read the origin.
        try:
            for r in rows:
                if not r.get("git_root"):
                    try:
                        r["git_root"] = provenance._git_root(r.get("dir") or "") or ""
                    except Exception:
                        r["git_root"] = ""
            ledger.observe(rows, now=now)
        except Exception as e:
            note_problem("ledger.observe", e)
            for r in rows:
                r.setdefault("origin", None)

        ignored = lifecycle.ignored()
        for r in rows:
            try:
                lo = lifecycle.leftover(r, procs)
            except Exception:
                lo = {"likely": False, "score": 0, "reasons": [], "idle_days": None}
            if str(r["port"]) in ignored:
                lo = dict(lo, likely=False, ignored=True)
            r["leftover"] = lo

        try:
            stdio = mcp_mod.find_stdio(procs, {r["pid"] for r in socks})
        except Exception:
            stdio = []
        # A stdio MCP server holds no port, so nothing above touched it - but it
        # is the case most worth analysing: full tool access, no socket to find.
        for p_ in stdio:
            proc = procs.get(p_["pid"], {})
            try:
                kids = mcp_mod.descendants(p_["pid"], procs)
                p_["descendants"] = kids
                p_["descendant_groups"] = mcp_mod.group_descendants(kids)
                p_["descendant_count"] = len(kids)
            except Exception:
                p_["descendants"], p_["descendant_groups"], p_["descendant_count"] = [], [], 0
            p_["ancestry"] = collect.ancestry(p_["pid"], procs)
            try:
                p_["starter"] = lifecycle.starter(
                    {"cmdline": proc.get("cmdline") or p_.get("cmdline", "")},
                    p_["ancestry"], envs.get(p_["pid"], []))
            except Exception:
                p_["starter"] = None
            p_["dir"] = dirs_for_stdio.get(p_["pid"], "")
            try:
                p_["access"] = access.analyse(
                    {"cmdline": proc.get("cmdline") or p_.get("cmdline", ""),
                     "dir": p_["dir"], "user": p_.get("user"), "name": p_["name"]},
                    envs.get(p_["pid"], []), env_readable=p_["pid"] in envs,
                    conns=conns.get(p_["pid"], []))
            except Exception:
                p_["access"] = {"credentials": [], "paths": [], "radius": [],
                                "overall": "unknown", "credentials_readable": False,
                                "tool_capabilities": []}
        _last["stdio_mcp"] = stdio

        events, first_seen = history.reconcile(rows)
        day = 86400
        for r in rows:
            fs = first_seen.get(str(r["port"]))
            r["first_seen"] = fs
            r["is_new"] = bool(fs and (now - fs) < day)

        order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
        rows.sort(key=lambda r: (r["quiet"], order.get(r["risk_band"], 5), -r["risk"], r["port"]))
        elapsed_ms = (time.time() - _t0) * 1000.0
        _stats["scans"] += 1
        _stats["total_ms"] += elapsed_ms
        _stats["last_ms"] = elapsed_ms
        _stats["max_ms"] = max(_stats["max_ms"], elapsed_ms)
        _stats["last_probes"] = len(set(targets))
        _last.update(t=now, rows=rows, host=host)
        return rows, host


# Status-page vocabulary, matching the convention already used across these
# services: up / minor / partial / major / down / nodata.
HEALTH = {
    "up":      ("Operational", "up"),
    "minor":   ("Degraded", "minor"),
    "partial": ("Partial outage", "partial"),
    "major":   ("Major outage", "major"),
    "down":    ("Not responding", "down"),
    "nodata":  ("Not measured", "nodata"),
}


# Categories that never speak HTTP. Rejecting an HTTP probe is correct
# behaviour for these, not an outage.
NON_HTTP_CATS = {"Proxy", "Database", "Cache", "Remote access", "File sharing",
                 "Search", "Object storage", "Container runtime", "Orchestrator",
                 "Vector database", "Queue", "Directory"}


def health_of(row):
    """-> (state, label, detail). What the service is actually doing, not just
    whether a socket is open. A port can be bound while the app behind it 500s."""
    pr = row.get("probe") or {}
    st = pr.get("status")
    if pr.get("probed") == "passive":
        return "nodata", HEALTH["nodata"][0], "not probed (protocol is not safe to send to)"
    if pr.get("http"):
        if st is None:
            return "minor", HEALTH["minor"][0], "answered, but no status line"
        if st in (401, 403, 407):
            return "up", HEALTH["up"][0], "HTTP %d - authentication enforced" % st
        if st < 400:
            return "up", HEALTH["up"][0], "HTTP %d" % st
        non_http = (row.get("service_cat") in NON_HTTP_CATS)
        if non_http and st in (400, 405, 501):
            return "up", HEALTH["up"][0], (
                "HTTP %d - not an HTTP service; it rejected the probe, which is correct" % st)
        if st < 500:
            return "minor", HEALTH["minor"][0], "HTTP %d" % st
        return "major", HEALTH["major"][0], "HTTP %d - the app behind the port is failing" % st
    if pr.get("banner"):
        return "up", HEALTH["up"][0], "responded with a protocol banner"
    if pr.get("error") and "refused" in (pr.get("error") or "").lower():
        return "down", HEALTH["down"][0], pr["error"]
    if pr.get("error"):
        return "partial", HEALTH["partial"][0], "listening, but did not answer: %s" % pr["error"]
    return "nodata", HEALTH["nodata"][0], "no probe result"


def stdio_mcp():
    """MCP servers that hold no socket - they never appear in a port inventory."""
    return _last.get("stdio_mcp", [])


# Fields the table never shows. They tick every second, so leaving them in the
# list response changes its ETag on every poll and defeats conditional requests.
# The drawer gets them from /api/detail, which is fetched on demand.
LIST_OMIT = ("started", "uptime", "cpu", "mem", "cmdline", "evidence", "reasons",
             "health_detail", "service_note",
             # the table shows row["blast"]; the full picture is drawer-only
             "access")
# Not omitted, and worth saying why: `depends_on` and `used_by` look like drawer
# material and are not. The stack panel draws its arrows from the list, and
# dropping them cost 305 bytes across every row on this machine while silently
# emptying a column. Measure before trimming, and check what reads it.
# Same reasoning one level down: a response time that moves by a millisecond
# between polls is not news, and it changes the ETag for the whole page.
PROBE_OMIT = ("response_ms", "body_preview", "headers", "probed_at")


# The launch ledger's answer, cut down to what a list can draw. The full origin
# is 750 bytes a row - a quarter of the whole payload - and most of it is only
# ever read in the drawer, which fetches the row again anyway. Sending it to
# every open panel every five seconds was the single most expensive thing on the
# wire, and none of those panels drew it.
def _lean_origin(o):
    if not isinstance(o, dict):
        return o
    def who(w):
        if not isinstance(w, dict):
            return w
        return {k: w[k] for k in ("kind", "name", "ai") if k in w}
    out = {k: o[k] for k in ("carries_context", "live_is_container", "observed",
                             "started_at", "respawns", "matched")
           if k in o}
    if o.get("live"):
        out["live"] = who(o["live"])
    if o.get("recorded"):
        out["recorded"] = who(o["recorded"])
    return out


def lean(rows):
    out = []
    for r in rows:
        row = {k: v for k, v in r.items() if k not in LIST_OMIT}
        if isinstance(row.get("probe"), dict):
            row["probe"] = {k: v for k, v in row["probe"].items() if k not in PROBE_OMIT}
        if "origin" in row:
            row["origin"] = _lean_origin(row["origin"])
        out.append(row)
    return out


def summary(rows, host):
    live = [r for r in rows if not r["quiet"]]
    ai_listening = sum(1 for r in live if r["ai"])
    stdio = len(_last.get("stdio_mcp", []))
    return {
        "mcp": sum(1 for r in live if r.get("mcp")),
        "mcp_stdio": stdio,
        # An MCP server over stdio is an AI asset with tool access. It holds no
        # port, so counting only listening services reported "0 AI" on a machine
        # actively running two of them.
        "ai_total": ai_listening + stdio,
        "total": len(rows),
        "shown": len(live),
        "http": sum(1 for r in live if r["probe"].get("http")),
        "ai": sum(1 for r in live if r["ai"]),
        "exposed": sum(1 for r in live if r["exposure"]["level"] in ("all", "lan")),
        "critical": sum(1 for r in live if r["risk_band"] == "Critical"),
        "high": sum(1 for r in live if r["risk_band"] == "High"),
        "new": sum(1 for r in live if r["is_new"]),
        "blast": sum(1 for r in live
                     if (r.get("blast") or {}).get("overall") in ("high", "critical")),
        "leftovers": sum(1 for r in live if (r.get("leftover") or {}).get("likely")),
        "ai_started": sum(1 for r in live if (r.get("starter") or {}).get("ai")),
        "host": host,
    }


def project_stacks():
    """Services grouped into the projects they came from."""
    rows, _ = scan()
    return projects_mod.group(rows)


def graph(mode="machine"):
    """Nodes and edges for one view of this machine."""
    rows, host = scan()
    conns = []
    if mode in ("machine", "exposure"):
        try:
            conns = connections()[0]
        except Exception:
            conns = []
    return graph_mod.build(rows, mode=mode, host=host, conns=conns)


def leftovers():
    rows, _ = scan()
    out = [r for r in rows if (r.get("leftover") or {}).get("likely")]
    return sorted(out, key=lambda r: -(r["leftover"]["score"]))


_posture = {"t": 0, "v": None}
_POSTURE_TTL = 20.0


def ai_posture(force=False):
    """AI exposure score, MCP estate and findings. Cached: it reads config files
    off disk and reconciles them against the process table, which is more work
    than a poll should do every time."""
    now = time.time()
    if not force and _posture["v"] and now - _posture["t"] < _POSTURE_TTL:
        return _posture["v"]
    rows, host = scan(force=force)
    rep = posture.report(rows, stdio_mcp(), host, summary(rows, host))
    _posture.update(t=now, v=rep)
    return rep


def connections(pid):
    return collect.established().get(pid, [])


def tree(pid):
    procs = collect.processes()
    return {"ancestry": collect.ancestry(pid, procs),
            "children": collect.children(pid, procs)}


def detail(row):
    """Everything expensive, computed only when a service is actually opened."""
    procs = collect.processes()
    chain_up = collect.ancestry(row["pid"], procs)
    out = dict(row)
    out["tree"] = {"ancestry": chain_up, "children": collect.children(row["pid"], procs)}
    out["connections"] = collect.established().get(row["pid"], [])
    try:
        out["provenance"] = provenance.explain(row, procs, chain_up)
    except Exception as e:                      # never let provenance break a page
        out["provenance"] = {"summary": "could not be determined (%s)" % e,
                             "chain": [], "evidence": []}
    out["environ_names"] = collect.environ(row["pid"])
    try:
        rows, _ = scan()
        out["names"] = names_mod.names_for(row, names_mod.build(rows))
    except Exception:
        out["names"] = []
    try:
        out["fixes"] = fix.for_row(row)
    except Exception:
        out["fixes"] = []
    return out


_sys_cache = {"t": 0, "v": None}
_sys_refreshing = threading.Event()


def system_info(ttl=4.0):
    """System page payload. Served from cache and refreshed behind the request,
    for the same reason the port scan is: nobody should watch a spinner for
    numbers that will be one poll old either way."""
    now = time.time()
    if _sys_cache["v"]:
        if now - _sys_cache["t"] >= ttl and not _sys_refreshing.is_set():
            _sys_refreshing.set()
            threading.Thread(target=_refresh_system, daemon=True).start()
        return _sys_cache["v"]
    return _build_system()


def _refresh_system():
    try:
        _build_system()
    except Exception:
        pass
    finally:
        _sys_refreshing.clear()


def _build_system():
    now = time.time()
    info = collect.system()
    try:
        rows, host = scan()
        live = [r for r in rows if not r["quiet"]]
        info["ports"] = {
            "listening": len(live), "total_sockets": len(rows),
            "exposed": sum(1 for r in live if r["exposure"]["level"] in ("all", "lan")),
            "ai": sum(1 for r in live if r["ai"]),
            "critical": sum(1 for r in live if r["risk_band"] == "Critical"),
            "high": sum(1 for r in live if r["risk_band"] == "High"),
        }
    except Exception:
        info["ports"] = {}
    try:
        info["containers"] = _container_stats()
    except Exception:
        info["containers"] = {"engine": None, "running": None}
    info["platform"] = {"name": collect.NAME, "verified": collect.VERIFIED}
    _sys_cache.update(t=time.time(), v=info)
    return info


def _container_stats():
    doc = containers.inventory()
    if not doc.get("engine"):
        return {"engine": None, "running": None, "note": doc.get("note") or ""}
    if not doc.get("reachable"):
        return {"engine": doc["engine"], "running": None, "total": None,
                "reachable": False, "note": doc.get("note") or ""}
    return {"engine": doc["engine"], "running": doc.get("running", 0),
            "total": doc.get("total", 0), "reachable": True,
            "projects": len([g for g in containers.projects(doc) if g["project"]]),
            "note": ""}


# What a remote port means when THIS machine dials out to it.
# (name, kind, tone, notable, what it means)
#   notable -> sorted to the top and coloured, because a shell, a tunnel or a
#   database leaving this machine matters more than another browser tab.
REMOTE_SERVICES = {
    22:    ("SSH", "remote shell", "red", True,
            "An interactive shell or file transfer to another machine. Whatever is typed "
            "or copied in that session leaves this computer."),
    23:    ("Telnet", "remote shell", "red", True,
            "Unencrypted remote shell. Credentials cross the network in clear text."),
    3389:  ("RDP", "remote desktop", "red", True,
            "Remote desktop session to another machine."),
    5900:  ("VNC", "remote desktop", "red", True, "Screen sharing to another machine."),
    5901:  ("VNC", "remote desktop", "red", True, "Screen sharing to another machine."),
    1194:  ("OpenVPN", "vpn", "amber", True,
            "A VPN tunnel. Traffic that looks local may actually be crossing this."),
    1723:  ("PPTP", "vpn", "amber", True, "A legacy VPN tunnel; PPTP is considered broken."),
    51820: ("WireGuard", "vpn", "amber", True, "A VPN tunnel."),
    1080:  ("SOCKS proxy", "tunnel", "amber", True,
            "A SOCKS proxy. Other traffic is being tunnelled through it."),
    3128:  ("HTTP proxy", "tunnel", "amber", True, "Traffic is being routed through a proxy."),
    9050:  ("Tor SOCKS", "tunnel", "amber", True, "Traffic is being routed through Tor."),
    9150:  ("Tor SOCKS", "tunnel", "amber", True, "Traffic is being routed through Tor."),
    9051:  ("Tor control", "tunnel", "amber", True, "Control channel for a Tor daemon."),
    27017: ("MongoDB", "database", "red", True,
            "A database client talking to a database somewhere else. Records are moving "
            "off this machine."),
    5432:  ("PostgreSQL", "database", "red", True, "A database on another machine."),
    3306:  ("MySQL", "database", "red", True, "A database on another machine."),
    1433:  ("SQL Server", "database", "red", True, "A database on another machine."),
    6379:  ("Redis", "database", "red", True, "A key-value store on another machine."),
    9042:  ("Cassandra", "database", "red", True, "A database on another machine."),
    9200:  ("Elasticsearch", "database", "red", True, "A search cluster on another machine."),
    11211: ("memcached", "cache", "red", True, "A cache on another machine."),
    5672:  ("AMQP", "queue", "amber", True, "A message broker on another machine."),
    5671:  ("AMQPS", "queue", "amber", True, "A message broker on another machine."),
    9092:  ("Kafka", "queue", "amber", True, "A message broker on another machine."),
    11434: ("Ollama", "ai", "blue", True,
            "An LLM API on another machine. Prompts sent to it leave this computer."),
    445:   ("SMB", "file sharing", "amber", True, "A network file share."),
    2049:  ("NFS", "file sharing", "amber", True, "A network file share."),
    21:    ("FTP", "file transfer", "amber", True, "Unencrypted file transfer."),
    389:   ("LDAP", "directory", "amber", True, "A directory server, usually for logins."),
    636:   ("LDAPS", "directory", "amber", True, "A directory server, usually for logins."),
    25:    ("SMTP", "mail", "amber", True, "Outbound mail relay."),
    465:   ("SMTPS", "mail", "amber", True, "Outbound mail relay."),
    587:   ("SMTP", "mail", "amber", True, "Outbound mail relay."),
    2375:  ("Docker API", "container", "red", True,
            "An unencrypted Docker control API. That is root on the far machine."),
    2376:  ("Docker API", "container", "red", True, "A Docker control API on another machine."),
    6443:  ("Kubernetes API", "container", "red", True, "A Kubernetes control plane."),
    # Ordinary traffic. Named, but not flagged.
    80:    ("HTTP", "web", "grey", False, "Plain web traffic."),
    443:   ("HTTPS", "web", "grey", False, "Encrypted web traffic. The bulk of normal traffic."),
    8080:  ("HTTP alt", "web", "grey", False, "Web traffic on an alternate port."),
    8443:  ("HTTPS alt", "web", "grey", False, "Encrypted web traffic on an alternate port."),
    53:    ("DNS", "naming", "grey", False, "Name lookups."),
    853:   ("DNS over TLS", "naming", "grey", False, "Encrypted name lookups."),
    110:   ("POP3", "mail", "grey", False, "Mail retrieval."),
    143:   ("IMAP", "mail", "grey", False, "Mail retrieval."),
    993:   ("IMAPS", "mail", "grey", False, "Mail retrieval."),
    995:   ("POP3S", "mail", "grey", False, "Mail retrieval."),
    5222:  ("XMPP", "chat", "grey", False, "Chat protocol."),
    5228:  ("Google push", "push", "grey", False, "Google push notifications, used by Chrome."),
}

# Backwards-compatible name lookup.
REMOTE_PORTS = {p: v[0] for p, v in REMOTE_SERVICES.items()}


def classify_remote(port):
    hit = REMOTE_SERVICES.get(port)
    if hit:
        name, kind, tone, notable, blurb = hit
        return {"remote_service": name, "kind": kind, "tone": tone,
                "notable": notable, "blurb": blurb}
    return {"remote_service": None, "kind": None, "tone": "grey", "notable": False,
            "blurb": "Portlist does not recognise this port. It could be anything: "
                     "an application protocol, an API on a non-standard port, or a "
                     "service worth looking at."}


_conn_cache = {"t": 0, "v": None, "eps": None}
_conn_refreshing = threading.Event()


def connections(limit=500):
    """Cached view of connections + grouped endpoints, refreshed behind the
    request. Building it costs two lsof calls; a poll should not pay for that."""
    now = time.time()
    if _conn_cache["v"] is not None:
        if now - _conn_cache["t"] >= 3.0 and not _conn_refreshing.is_set():
            _conn_refreshing.set()
            threading.Thread(target=_refresh_conns, daemon=True).start()
        return _conn_cache["v"], _conn_cache["eps"]
    return _build_conns()


def _refresh_conns():
    try:
        _build_conns()
    except Exception:
        pass
    finally:
        _conn_refreshing.clear()


def _build_conns():
    conns = connections_all(2000)
    eps = remote_endpoints()
    _conn_cache.update(t=time.time(), v=conns, eps=eps)
    return conns, eps


def connections_all(limit=500):
    """Every established connection, not just those owned by a listening process.

    An outbound SSH session or a database client holds no listening socket, so it
    never appears in the service inventory. It is still traffic leaving this
    machine, and "what is communicating" is a different question from "what is
    listening".
    """
    from . import remote
    try:
        aliases = remote.ssh_config_map()
    except Exception:
        aliases = {}
    est = collect.established()
    procs = collect.processes()
    listen = collect.listening()
    listen_ports = {r["port"] for r in listen}
    listen_pids = {r["pid"] for r in listen}
    # For an inbound connection the meaningful port is the LOCAL one - the
    # service someone connected to - not the caller's ephemeral port. Prefer the
    # name the scan already worked out over a port-table lookup.
    named = {}
    for r in (_last.get("rows") or []):
        if r.get("service"):
            named.setdefault(r["port"], (r["service"], r.get("service_cat")))

    out = []
    for pid, conns in est.items():
        proc = procs.get(pid, {})
        name = conns[0].get("cmd") or collect.short_name(proc.get("cmdline", ""))
        for c in conns:
            inbound = c["lport"] in listen_ports
            if inbound:
                info = classify_remote(c["lport"])
                hit = named.get(c["lport"])
                if hit:
                    info = dict(info, remote_service=hit[0], kind=hit[1] or info["kind"],
                                blurb="Something on this machine connected to %s, which is "
                                      "listening on port %d here." % (hit[0], c["lport"]))
                elif info["remote_service"]:
                    info = dict(info, blurb="Something connected to %s on this machine."
                                % info["remote_service"])
                else:
                    info = dict(info, blurb="Something connected to port %d on this machine, "
                                            "and Portlist could not name that service."
                                % c["lport"])
            else:
                info = classify_remote(c["rport"])
                # A connection to one of our own ports should say what that
                # service is, not "unrecognised" because 7337 is not a
                # well-known port anywhere but here.
                if not info["remote_service"] and c["scope"] in ("loopback", "private"):
                    hit = named.get(c["rport"])
                    if hit:
                        info = dict(info, remote_service=hit[0], kind=hit[1] or info["kind"],
                                    blurb="A local service on this machine: %s, listening "
                                          "on port %d here." % (hit[0], c["rport"]))
            out.append({
                "id": "%s-%s-%d" % (pid if pid is not None else "nopid",
                                    c["raddr"].strip("[]"), c["rport"]),
                "pid": pid, "name": name, "user": proc.get("user", ""),
                "cmdline": (proc.get("cmdline") or "")[:160],
                "laddr": c["laddr"], "lport": c["lport"],
                "raddr": c["raddr"], "rport": c["rport"],
                "scope": c["scope"],
                "direction": "inbound" if inbound else "outbound",
                "service_port": c["lport"] if inbound else c["rport"],
                "remote_alias": aliases.get(c["raddr"].strip("[]")),
                "serves": pid in listen_pids,
                **info,
            })
    # Notable first: a shell, a tunnel or a database leaving this machine is the
    # reason to look at this table at all.
    tone_rank = {"red": 0, "amber": 1, "blue": 2, "grey": 3}
    scope_rank = {"public": 0, "private": 1, "loopback": 2, "unknown": 3}
    out.sort(key=lambda c: (not c["notable"], tone_rank.get(c["tone"], 4),
                            scope_rank.get(c["scope"], 4), c["name"].lower(), c["rport"]))
    return out[:limit]


def remote_endpoints(limit=40):
    """Outbound connections grouped by the machine on the other end.

    The service inventory answers "what can reach me". This answers "what am I
    reaching", which is the question an open SSH session actually belongs to.
    """
    groups = {}
    for c in connections_all(2000):
        if c["direction"] != "outbound":
            continue
        # Loopback endpoints are kept: something on this machine talking to
        # another service on this machine is a real dependency, and the only
        # place it would otherwise show is a raw connection row.
        key = c["raddr"].strip("[]")
        if c["scope"] == "loopback":
            key = "localhost:%d" % c["rport"]
        g = groups.setdefault(key, {
            "address": c["raddr"].strip("[]"), "alias": c.get("remote_alias"),
            "scope": c["scope"], "local": c["scope"] == "loopback",
            "ports": {}, "processes": {}, "count": 0, "ssh": False,
            "notable": False, "tone": "grey"})
        g["count"] += 1
        g["alias"] = g["alias"] or c.get("remote_alias")
        g["ports"].setdefault(c["rport"], c.get("remote_service"))
        if c.get("notable"):
            g["notable"] = True
            g["tone"] = c["tone"] if g.get("tone") != "red" else "red"
        g["processes"].setdefault(c["name"], {"name": c["name"], "pid": c["pid"]})
        if c["rport"] == 22:
            g["ssh"] = True

    out = []
    for g in groups.values():
        ports = sorted(g["ports"].items())
        out.append({
            "address": g["address"], "alias": g["alias"], "scope": g["scope"],
            "local": g.get("local", False),
            "count": g["count"], "ssh": g["ssh"],
            "notable": g["notable"], "tone": g["tone"],
            "ports": [{"port": p, "service": s} for p, s in ports],
            "services": sorted({s for _, s in ports if s}),
            "processes": sorted(g["processes"].values(), key=lambda x: x["name"]),
            # only offered for hosts you can actually name; scanning needs a login
            "scan_command": ("portlist ssh %s" % g["alias"]) if (g["ssh"] and g["alias"]) else None,
        })
    tone_rank = {"red": 0, "amber": 1, "blue": 2, "grey": 3}
    out.sort(key=lambda g: (g["local"], not g["notable"], tone_rank.get(g["tone"], 4),
                            -g["count"], g["address"]))
    return out[:limit]


_fd_cache = {"t": 0, "v": None}


def _open_fds():
    """Cheap on Linux, cached everywhere else - counting fds should not cost more
    than the thing it is measuring."""
    if os.path.isdir("/proc/self/fd"):
        try:
            return len(os.listdir("/proc/self/fd"))
        except OSError:
            return None
    now = time.time()
    if _fd_cache["v"] is not None and now - _fd_cache["t"] < 60:
        return _fd_cache["v"]
    out = collect.run(["lsof", "-p", str(os.getpid())], timeout=6)
    val = max(0, len(out.strip().splitlines()) - 1) if out.strip() else None
    _fd_cache.update(t=now, v=val)
    return val


def self_metrics():
    """What Portlist itself costs to run. Measured, not claimed."""
    import threading as _t
    pid = os.getpid()
    # One targeted ps instead of enumerating ~700 processes to find ourselves.
    cpu = mem = rss = None
    out = collect.run(["ps", "-o", "pcpu=,pmem=,rss=", "-p", str(pid)], timeout=4).strip()
    parts = out.split()
    if len(parts) >= 3:
        try:
            cpu, mem, rss = float(parts[0]), float(parts[1]), int(parts[2]) * 1024
        except ValueError:
            pass
    me = {"cpu": cpu, "mem": mem}

    scans = _stats["scans"]
    avg = (_stats["total_ms"] / scans) if scans else 0.0
    uptime = time.time() - _stats["started"]
    return {
        "pid": pid,
        "cpu_pct": me.get("cpu"),
        "mem_pct": me.get("mem"),
        "rss": rss,
        "threads": _t.active_count(),
        "open_fds": _open_fds(),
        "uptime": uptime,
        "scans": scans,
        "last_scan_ms": round(_stats["last_ms"], 1),
        "avg_scan_ms": round(avg, 1),
        "slowest_scan_ms": round(_stats["max_ms"], 1),
        "ports_probed": _stats["last_probes"],
        "requests_served": _stats["requests"],
        "bytes_served": _stats["bytes"],
        "scan_duty_pct": round(100.0 * (_stats["total_ms"] / 1000.0) / uptime, 2) if uptime > 0 else 0.0,
        "dependencies": 0,
    }


def note_request(nbytes):
    _stats["requests"] += 1
    _stats["bytes"] += int(nbytes or 0)


def top_processes(by="cpu", limit=12):
    """Backing data for the clickable System cards."""
    procs = collect.processes().values()
    key = (lambda p: p.get("cpu") or 0) if by == "cpu" else (lambda p: p.get("mem") or 0)
    ranked = sorted(procs, key=key, reverse=True)[:limit]
    return [{"pid": p["pid"], "name": collect.short_name(p["cmdline"]),
             "user": p.get("user"), "cpu": p.get("cpu"), "mem": p.get("mem"),
             "cmdline": p.get("cmdline", "")[:160]} for p in ranked]

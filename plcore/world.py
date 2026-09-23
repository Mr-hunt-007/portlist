"""The living world: portlist's model, read as a harbour.

This is the semantic engine behind `portlist --world`. It never looks at the
machine itself. It takes the rows, groups, containers and sessions the scan
already produced and says what they mean in the world: which building, which
dock, which worker, which gate, and what each pet should be doing about it.

Three rules shape every line here.

**Everything has a reason.** Every entity is a row, a group, a container or a
session. Every state carries the measurement behind it. Every pet task names
its trigger and its evidence, so the page can answer "why is it doing that?".

**Unknown is not dangerous.** A service with no attribution is unidentified
machinery with missing paperwork. It is never coloured as a threat, and nothing
here raises its priority for being unknown beyond "the inspector is curious".

**Unknown is not clean either.** A container engine that did not answer is a
closed yard, not an empty one. An activity record with too few samples is
"still measuring", not "idle".

Pure functions over plain dicts, so the whole thing is testable without a
machine: `build()` makes a snapshot, `Differ.feed()` turns two snapshots into
events (and the first one into none), `plan_pets()` gives each pet one task.
"""
import hashlib
import json
import os
import re
import sys
import threading
import time

SCHEMA = "portlist/world/1"

# ------------------------------------------------------------------ families
# Service id (from the catalog) -> the family that decides the building shape
# and the emblem painted on its wall. A family is presentation only: two
# services in one family are drawn alike, nothing is inferred from it.
FAMILY_OF = {
    "ssh": "ssh", "vnc": "remote", "smb": "files", "tor": "tor",
    "postgres": "postgres", "mysql": "mysql", "mongodb": "mongo",
    "clickhouse": "columnar", "elasticsearch": "search", "opensearch": "search",
    "redis": "redis", "memcached": "memcached", "minio": "storage",
    "qdrant": "vector", "chroma": "vector", "weaviate": "vector", "milvus": "vector",
    "ollama": "llm", "vllm": "llm", "lmstudio": "llm", "localai": "llm",
    "openwebui": "ai", "comfyui": "ai", "gradio": "ai", "streamlit": "ai",
    "langflow": "ai", "flowise": "ai", "dify": "ai", "anythingllm": "ai",
    "n8n": "ai", "jupyter": "notebook", "mlflow": "notebook",
    "mcp": "mcp",
    "docker": "containers", "kubernetes": "containers", "portainer": "containers",
    "grafana": "metrics", "prometheus": "metrics",
    "nginx": "proxy", "apache": "proxy", "caddy": "proxy",
    "nextjs": "dev", "vite": "dev", "webpack": "dev", "bun": "dev",
    "express": "api", "uvicorn": "api", "gunicorn": "api", "flask": "api",
    "django": "api", "rails": "api",
    "pyhttp": "static",
    "airplay": "system", "rapportd": "system", "vscode": "system",
    "chromedev": "debug",
}

# family -> (building shape, human label). Shapes are what world.html knows how
# to draw; labels are what the inspector says.
FAMILIES = {
    "ssh":        ("lighthouse", "SSH"),
    "remote":     ("tower",      "remote desktop"),
    "files":      ("warehouse",  "file sharing"),
    "tor":        ("onion",      "Tor"),
    "postgres":   ("tanks",      "PostgreSQL"),
    "mysql":      ("tanks",      "MySQL / MariaDB"),
    "mongo":      ("tanks",      "MongoDB"),
    "columnar":   ("tanks",      "ClickHouse"),
    "search":     ("tanks",      "search engine"),
    "redis":      ("cache",      "Redis"),
    "memcached":  ("cache",      "memcached"),
    "storage":    ("warehouse",  "object storage"),
    "vector":     ("dome",       "vector database"),
    "llm":        ("dome",       "local model"),
    "ai":         ("dome",       "AI app"),
    "notebook":   ("dome",       "notebook / ML"),
    "mcp":        ("mast",       "MCP server"),
    "containers": ("control",    "container control"),
    "metrics":    ("observatory", "metrics"),
    "proxy":      ("gatehouse",  "web server / proxy"),
    "dev":        ("garage",     "dev server"),
    "api":        ("factory",    "app server"),
    "static":     ("warehouse",  "static file server"),
    "system":     ("shed",       "system service"),
    "debug":      ("shed",       "debug endpoint"),
    "unknown":    ("shed",       "unidentified"),
}

# Categories the catalog did not give an id for still say something useful.
CAT_FAMILY = [
    (re.compile(r"(?i)database|sql"), "postgres"),
    (re.compile(r"(?i)cache"), "redis"),
    (re.compile(r"(?i)dev server"), "dev"),
    (re.compile(r"(?i)app server|api"), "api"),
    (re.compile(r"(?i)proxy|web server"), "proxy"),
    (re.compile(r"(?i)\bai\b|model|llm"), "ai"),
]


def family_of(row):
    sid = row.get("service_id")
    if sid in FAMILY_OF:
        return FAMILY_OF[sid]
    if row.get("mcp"):
        return "mcp"
    cat = row.get("service_cat") or ""
    for rx, fam in CAT_FAMILY:
        if rx.search(cat):
            return fam
    if row.get("ai"):
        return "ai"
    return "unknown"


# ------------------------------------------------------------------ states
BUSY_CONNS = 3             # open connections right now that make a building "busy"
RECENT = 120               # seconds since last observed use that still count as active
LONG_IDLE = 6 * 3600       # quiet for this long, with use on record, gathers dust


def _dur(s):
    if s is None:
        return "?"
    s = int(max(0, s))
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh %02dm" % (s // 3600, (s % 3600) // 60)
    return "%dd %02dh" % (s // 86400, (s % 86400) // 3600)


def activity_state(row, now=None):
    """-> (state, why). busy | active | idle | long_idle | unmeasured.

    `unmeasured` is its own state on purpose: a service portlist has watched for
    six seconds has not been idle, it has been watched for six seconds.
    """
    act = row.get("activity") or {}
    conns = row.get("conns") or 0
    if conns >= BUSY_CONNS:
        return "busy", "%d connections open right now" % conns
    if conns > 0:
        return "active", "%d connection%s open right now" % (conns, "" if conns == 1 else "s")
    if not act.get("known"):
        return "unmeasured", (act.get("note") or "not watched long enough to say")
    idle = act.get("idle_seconds")
    if act.get("ever_busy") and idle is not None and idle < RECENT:
        return "active", "used %s ago" % _dur(idle)
    if act.get("ever_busy") and idle is not None and idle >= LONG_IDLE:
        return "long_idle", "last used %s ago" % _dur(idle)
    if not act.get("ever_busy") and (act.get("watched_for") or 0) >= LONG_IDLE:
        return "long_idle", "no use seen in %s of watching" % _dur(act.get("watched_for"))
    if act.get("ever_busy") and idle is not None:
        return "idle", "last used %s ago" % _dur(idle)
    return "idle", "no use seen in %s of watching" % _dur(act.get("watched_for"))


def exposure_state(row):
    """-> (state, why). local | reachable | bound | unreachable | unknown.

    The gate only opens on `reachable`, which means portlist actually connected
    to the machine's own network address and was accepted. A 0.0.0.0 bind with
    no successful connection is `bound`: worth a look, not an open gate.
    """
    exp = row.get("exposure") or {}
    level = exp.get("level")
    if level == "loopback":
        return "local", "bound to loopback only (%s)" % ", ".join(exp.get("addrs") or ["127.0.0.1"])
    if level in ("all", "lan"):
        v = exp.get("verified") or {}
        if v.get("accepting") is True:
            return "reachable", "accepted a connection on %s (%s)" % (v.get("ip"), v.get("iface"))
        if v.get("accepting") is False:
            return "unreachable", ("bound to %s, but a connection to %s was refused"
                                   % (exp.get("label") or level, v.get("ip") or "the LAN address"))
        return "bound", "bound to %s, reachability not verified" % (exp.get("label") or level)
    return "unknown", "bind address could not be read"


def origin_state(row):
    """-> (state, name, why). known | recorded | system | ambiguous | unknown."""
    o = row.get("origin") or {}
    st = row.get("starter") or {}
    live, rec = o.get("live") or {}, o.get("recorded") or {}
    if o.get("matched") == "ambiguous":
        return "ambiguous", None, "more than one launch record could be this service"
    if live and o.get("carries_context"):
        if live.get("class") == "service manager":
            return "system", live.get("name"), "started by %s" % live.get("name")
        return "known", live.get("name"), "the running process carries it (%s)" % (live.get("via") or "ancestry")
    if rec.get("name"):
        if rec.get("class") == "service manager" or rec.get("kind") in ("launchd", "systemd", "cron"):
            return "system", rec.get("name"), "started by %s, on record since portlist saw it" % rec.get("name")
        return "recorded", rec.get("name"), "portlist saw the launch; the starter has since gone"
    if st.get("class") == "service manager":
        return "system", st.get("name"), "adopted by %s" % st.get("name")
    if st.get("name") and st.get("class") not in ("service manager",):
        return "known", st.get("name"), st.get("evidence") or "from the process ancestry"
    return "unknown", None, "already running before portlist first looked, and nothing on it says who started it"


def failure_state(row):
    h = row.get("health")
    if h == "down":
        return "failed", row.get("health_detail") or "refused the probe"
    if h in ("major", "partial"):
        return "degraded", row.get("health_detail") or row.get("health_label") or h
    return "ok", row.get("health_detail") or ""


RISKY = ("Critical", "High")


def service_key(row):
    """Identity that survives a restart: port + what runs + where it runs."""
    base = "%s|%s" % (row.get("dir") or "", " ".join((row.get("cmdline") or row.get("cmd") or "").split()))
    base = re.sub(r"\b\d{4,6}\b", "#", base)            # ports and pids in args
    return "%d/%s" % (row.get("port") or 0, hashlib.sha256(base.encode()).hexdigest()[:10])


# ------------------------------------------------------------------ badges
# What the process runs on and what it was built with, for the logos on a
# building's sign. Both are read, never guessed: the runtime from the process
# itself, the framework from the dependency file in the directory it runs from.
RUNTIMES = [
    (re.compile(r"(?i)^python(\d(\.\d+)?)?$|^pypy"), "python"),
    (re.compile(r"(?i)^node$|^nodejs$"), "nodedotjs"),
    (re.compile(r"(?i)^bun$"), "bun"),
    (re.compile(r"(?i)^deno$"), "deno"),
    (re.compile(r"(?i)^ruby$|^puma$"), "ruby"),
    (re.compile(r"(?i)^java$"), "openjdk"),
    (re.compile(r"(?i)^php(-fpm)?$"), "php"),
    (re.compile(r"(?i)^dotnet$"), "dotnet"),
]
JS_FRAMEWORKS = [("next", "nextdotjs"), ("nuxt", "nuxt"), ("@remix-run/react", "remix"),
                 ("astro", "astro"), ("@angular/core", "angular"), ("@sveltejs/kit", "svelte"),
                 ("svelte", "svelte"), ("vue", "vuedotjs"), ("react", "react"),
                 ("express", "express")]
PY_FRAMEWORKS = [("fastapi", "fastapi"), ("django", "django"), ("flask", "flask"),
                 ("streamlit", "streamlit"), ("gradio", "gradio")]
_dep_cache = {}


def runtime_of(row):
    for part in ((row.get("exe") or "").split("/")[-1], row.get("cmd") or "",
                 (row.get("cmdline") or "").split(" ")[0].split("/")[-1]):
        for rx, slug in RUNTIMES:
            if part and rx.search(part):
                return slug
    return None


def _read_small(path, limit=512 * 1024):
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    key = (path, st.st_mtime)
    if key in _dep_cache:
        return _dep_cache[key], path
    if st.st_size > limit:
        return None, None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None, None
    _dep_cache[key] = text
    return text, path


def framework_of(row):
    """-> (slug, why) from the project's own dependency file, or (None, None)."""
    dirs = []
    for d in (row.get("dir"), (row.get("project") or {}).get("path"), row.get("git_root")):
        if d and d not in dirs and d != "/":
            dirs.append(d)
    for d in dirs:
        text, path = _read_small(os.path.join(d, "package.json"))
        if text:
            try:
                doc = json.loads(text)
            except ValueError:
                doc = {}
            deps = {}
            for k in ("dependencies", "devDependencies"):
                if isinstance(doc.get(k), dict):
                    deps.update(doc[k])
            for name, slug in JS_FRAMEWORKS:
                if name in deps:
                    return slug, "%s in %s" % (name, _home(path))
        for fname in ("requirements.txt", "pyproject.toml", "Pipfile"):
            text, path = _read_small(os.path.join(d, fname))
            if text:
                low = text.lower()
                for name, slug in PY_FRAMEWORKS:
                    if re.search(r"(^|[\s\"'\[])%s([\s<>=~!\"',\]]|$)" % name, low, re.M):
                        return slug, "%s in %s" % (name, _home(path))
    return None, None


def _home(path):
    h = os.path.expanduser("~")
    return "~" + path[len(h):] if path.startswith(h) else path


# ------------------------------------------------------------------ ssh destinations
# Outbound SSH is read from the same grouping the dashboard's network view uses
# (scan.remote_endpoints): no second reader of the connection table.
ISLAND_KINDS = {"remote shell": "ssh", "database": "db"}
DB_LOGO = {"MongoDB": "mongodb", "PostgreSQL": "postgresql", "MySQL": "mysql", "Redis": "redis",
           "Elasticsearch": "elasticsearch", "MariaDB": "mariadb"}


def _kind_of(e):
    """-> "ssh", "db" or None, from the ports the scan already classified."""
    if e.get("ssh"):
        return "ssh"
    try:
        from .scan import REMOTE_SERVICES
    except ImportError:
        REMOTE_SERVICES = {}
    for p in e.get("ports") or []:
        hit = REMOTE_SERVICES.get(p.get("port"))
        if hit and hit[1] in ISLAND_KINDS:
            return ISLAND_KINDS[hit[1]]
    return None


def sea_destinations(endpoints, fleet=(), can_inventory=False):
    """-> one island per machine this one holds an SSH or database session to."""
    out = []
    for e in endpoints or []:
        kind = _kind_of(e)
        if not kind:
            continue
        name = (e.get("alias") or e.get("address") or "?").split("@")[-1][:60]
        ports = [p.get("port") for p in e.get("ports") or [] if p.get("port")]
        service = next((p.get("service") for p in e.get("ports") or [] if p.get("service")), None)
        out.append({"target": name, "kind": kind, "service": service or ("SSH" if kind == "ssh" else "database"),
                    "logo": DB_LOGO.get(service), "raddr": e.get("address"),
                    "rport": ports[0] if ports else None, "scope": e.get("scope"), "count": e.get("count") or 1,
                    "pids": [p.get("pid") for p in e.get("processes") or [] if p.get("pid")],
                    "client": ((e.get("processes") or [{}])[0]).get("name") or "?",
                    "in_fleet": name in fleet or (e.get("address") in fleet),
                    "scan_command": e.get("scan_command") if (can_inventory and kind == "ssh") else None})
    out.sort(key=lambda x: (x["kind"] != "ssh", x["target"]))
    return out[:6]


def ssh_destinations(endpoints, fleet=(), can_inventory=False):
    return [d for d in sea_destinations(endpoints, fleet, can_inventory) if d["kind"] == "ssh"]


# What an outbound connection is, from the port portlist recognised, never guessed.
# The harbour draws web traffic as cars on the causeway and the rest at sea.
VESSEL_OF = {"web": "car", "mail": "mailboat", "push": "fishing", "chat": "ferry",
             "ai": "launch", "queue": "tug", "cache": "tug", "database": "tug",
             "directory": "tender", "naming": "tender", "container": "tug"}


def vessel_kind(ports):
    """-> car, mailboat, fishing, ferry, launch, tug or tender. The first
    recognised port decides; nothing recognised stays a car, as before."""
    for p in ports:
        v = VESSEL_OF.get(p.get("kind") or "")
        if v:
            return v
    return "car"


def memory_of(services, history, now=None):
    """-> {port: counts} from the recorded opens and closes: how often each port
    opened and closed since local midnight, how many earlier opens were bound
    beyond loopback, and when it was first recorded. Counts only; the pets say
    them, they never guess them."""
    now = now or time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    ports = {s.get("port") for s in services}
    out = {}
    for h in history or []:
        p = h.get("port")
        if p not in ports or h.get("type") not in ("opened", "closed"):
            continue
        m = out.setdefault(p, {"opens_today": 0, "stops_today": 0, "exposed_before": 0, "since": None})
        ts = h.get("ts") or 0
        if h["type"] == "opened":
            m["since"] = ts if m["since"] is None else min(m["since"], ts)
            if ts >= midnight:
                m["opens_today"] += 1
            if (h.get("exposure") or "loopback") not in ("loopback", "local"):
                m["exposed_before"] += 1
        elif ts >= midnight:
            m["stops_today"] += 1
    return out


def traffic_endpoints(endpoints, limit=24):
    """-> outbound connections other than SSH, one per remote host: the cars
    in the lot. Same grouping the dashboard's network view shows."""
    out = []
    for e in endpoints or []:
        if e.get("local") or _kind_of(e):
            continue
        procs = []
        for p in e.get("processes") or []:
            n = re.sub(r" (Helper|Renderer|GPU)( \(.*\))?$", "", p.get("name") or "?")
            if n not in procs:
                procs.append(n)
        out.append({"key": e.get("address"), "address": e.get("address"), "alias": e.get("alias"),
                    "apps": procs[:3], "services": (e.get("services") or [])[:2],
                    "ports": [p.get("port") for p in e.get("ports") or []][:3],
                    "kind": vessel_kind(e.get("ports") or []),
                    "scope": e.get("scope"), "count": e.get("count") or 1})
    return out[:limit]


def inbound_ssh(conns, ssh_ports):
    """-> SSH sessions into this machine: inbound connections to its SSH port."""
    out, seen = [], set()
    for c in conns or []:
        if c.get("direction") != "inbound" or c.get("lport") not in ssh_ports:
            continue
        key = (c.get("raddr"), c.get("rport"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"raddr": c.get("raddr"), "rport": c.get("rport"), "lport": c.get("lport"),
                    "scope": c.get("scope"), "pid": c.get("pid")})
    return out[:6]


def _short_host(name):
    return (name or "this machine").split(".")[0]


def _scrub(text, limit=90):
    if not text:
        return ""
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[address]", str(text))
    text = " ".join(text.split())
    return text[:limit - 1] + "..." if len(text) > limit else text


# ------------------------------------------------------------------ build
def build(rows, host=None, groups=None, containers=None, sessions=None,
          sysinfo=None, history=None, now=None, outbound=None, conns=None, traffic=None):
    """-> the world snapshot. Pure: same inputs, same world."""
    now = now or time.time()
    host = host or {}
    # Quiet rows are services portlist files under "system" (AirPlay, editor
    # helpers). They are real listeners, so the harbour draws them, in their
    # own small quarter, and leaves them out of every count and every alarm,
    # exactly as the terminal does.
    live = [r for r in (rows or []) if not r.get("quiet")]
    quiet = [r for r in (rows or []) if r.get("quiet")]

    owner_of = {}
    for g in groups or []:
        for s in g.get("services") or []:
            owner_of[s.get("id")] = g

    by_port = {}
    for r in live:
        by_port.setdefault(r.get("port"), []).append(r)

    services = []
    for r in live + quiet:
        fam = family_of(r)
        shape, fam_label = FAMILIES.get(fam, FAMILIES["unknown"])
        act, act_why = activity_state(r, now)
        exp, exp_why = exposure_state(r)
        org, org_name, org_why = origin_state(r)
        fail, fail_why = failure_state(r)
        g = owner_of.get(r.get("id")) or {}
        left = bool(g) and g.get("alive") is False and g.get("key") != "unknown"
        peers = [p for p in by_port.get(r.get("port"), []) if p is not r]
        lo = r.get("leftover") or {}
        services.append({
            "id": r.get("id"), "key": service_key(r),
            "port": r.get("port"), "pid": r.get("pid"),
            "name": r.get("service") or r.get("cmd") or "?",
            "cmd": r.get("cmd"), "cmdline": _scrub(r.get("cmdline"), 140),
            "category": r.get("service_cat"), "service_id": r.get("service_id"),
            "family": fam, "shape": shape, "family_label": fam_label,
            "project": (r.get("project") or {}).get("name"),
            "dir": r.get("dir_short"),
            "uptime": r.get("uptime"), "started": r.get("started"),
            "cpu": r.get("cpu"),
            "first_seen": r.get("first_seen"), "is_new": bool(r.get("is_new")),
            "activity": act, "activity_why": act_why,
            "conns": r.get("conns") or 0, "conns_public": r.get("conns_public") or 0,
            "exposure": exp, "exposure_why": exp_why,
            "bind": ", ".join((r.get("exposure") or {}).get("addrs") or []),
            "origin": org, "origin_name": org_name, "origin_why": org_why,
            "origin_phrase": _origin_phrase(r),
            "owner": g.get("key"), "owner_name": g.get("name"),
            "owner_ai": bool(g.get("ai")), "owner_alive": g.get("alive"),
            "lights_left_on": left,
            "failure": fail, "failure_why": fail_why,
            "health": r.get("health"), "health_label": r.get("health_label"),
            "risk": r.get("risk") or 0, "risk_band": r.get("risk_band") or "",
            "reasons": [x.get("label") for x in (r.get("reasons") or [])][:4],
            "leftover": bool(lo.get("likely")), "leftover_why": lo.get("reasons") or [],
            "conflict": [p.get("id") for p in peers],
            "container": (r.get("container") or {}).get("name") if isinstance(r.get("container"), dict) else r.get("container"),
            "depends_on": [d.get("id") if isinstance(d, dict) else d for d in (r.get("depends_on") or [])],
            "used_by": [d.get("id") if isinstance(d, dict) else d for d in (r.get("used_by") or [])],
            "url": r.get("url"),
            "why": _scrub(r.get("why"), 240),
            "ai": bool(r.get("ai")), "mcp": bool(r.get("mcp")),
            "system": bool(r.get("quiet")),
            "runtime": runtime_of(r),
        })
        fw, fw_why = framework_of(r) if not r.get("quiet") else (None, None)
        services[-1]["framework"], services[-1]["framework_why"] = fw, fw_why
    for sv in services:
        if sv["system"]:
            sv["shape"], sv["conflict"] = "shed", []

    # stable *.localhost names, from the same table the names feature serves
    try:
        from . import names as names_mod
        table = names_mod.build(live)
        for sv in services:
            ns = [n for n, r in table.items() if r.get("id") == sv["id"] and not n.isdigit()]
            ns.sort(key=lambda n: (n.count("-"), len(n)))
            sv["local_name"] = ns[0] if ns else None
            sv["local_url"] = names_mod.url_for(ns[0], sv["port"]) if ns else None
    except Exception:
        pass
    services.sort(key=lambda s: (s["system"], s["port"] or 0, s["id"] or ""))
    main = [s for s in services if not s["system"]]

    workers = []
    for g in groups or []:
        cls = g.get("class") or ""
        if g.get("key") == "unknown" or cls in ("service manager", "runtime", "container"):
            continue
        ai = bool(g.get("ai")) or cls.startswith("AI")
        workers.append({
            "key": g.get("key"), "name": g.get("name"), "class": cls,
            "kind": g.get("kind"), "look": "robot" if ai else "human",
            "ai": ai, "alive": g.get("alive"), "pid": g.get("pid"),
            "services": [s.get("id") for s in g.get("services") or []],
            "ports": g.get("ports") or [], "projects": g.get("projects") or [],
            "mcp": len(g.get("mcp") or []),
            "evidence": _scrub(g.get("evidence"), 200), "note": g.get("note") or "",
            "one_session": bool(g.get("one_session")),
            "session": None,
        })

    sess_out = []
    sdoc = sessions or {}
    for s in (sdoc.get("sessions") or [])[:24]:
        # Titles only. Prompts never reach the world, the same rule every other
        # surface follows.
        sess_out.append({
            "id": str(s.get("id") or "")[:12], "tool": s.get("tool"),
            "title": _scrub(s.get("title") or s.get("summary") or "", 70),
            "project": s.get("project"), "live": bool(s.get("live")),
            "ambiguous": bool(s.get("ambiguous")),
            "live_pids": s.get("live_pids") or [],
            "context": s.get("context"), "last_active": s.get("last_active"),
        })
    for w in workers:
        if w["pid"] is None:
            continue
        hit = [s for s in sess_out if w["pid"] in s["live_pids"] and not s["ambiguous"]]
        if hit:
            w["session"] = hit[0]["title"] or hit[0]["id"]

    cdoc = containers or {}
    yard = {"engine": cdoc.get("engine"), "reachable": bool(cdoc.get("reachable")),
            "note": cdoc.get("note") or "", "containers": []}
    for c in cdoc.get("containers") or []:
        ports = []
        for p in c.get("ports") or []:
            hp = p.get("host_port") if isinstance(p, dict) else p
            if hp:
                ports.append(hp)
        yard["containers"].append({
            "id": c.get("id"), "name": c.get("name"), "image": c.get("image"),
            "state": c.get("state"), "status": c.get("status"),
            "running": c.get("state") == "running", "project": c.get("project"),
            "service": c.get("service"), "ports": ports,
            "colour": "#" + hashlib.sha256((c.get("project") or c.get("name") or "").encode()).hexdigest()[:6],
        })

    si = sysinfo or {}
    disks = si.get("disks") or []
    root = next((d for d in disks if d.get("mount") == "/"), disks[0] if disks else {})
    ship = {
        "name": _short_host(si.get("hostname") or host.get("hostname")),
        "hostname": si.get("hostname") or host.get("hostname"),
        "os": (si.get("os") or {}).get("pretty"),
        "lan": [a.get("ip") for a in host.get("lan") or [] if a.get("ip")],
        "firewall": (host.get("firewall") or {}).get("enabled"),
        "firewall_name": (host.get("firewall") or {}).get("name"),
        "firewall_stealth": (host.get("firewall") or {}).get("stealth"),
        "firewall_detail": (host.get("firewall") or {}).get("detail"),
        "load_pct": (si.get("cpu") or {}).get("load_pct"),
        "mem_pct": (si.get("memory") or {}).get("pct"),
        "disk_pct": root.get("pct"),
        "uptime": si.get("uptime"),
        # the machine readout, as the terminal's system view shows it
        "model": (si.get("cpu") or {}).get("model"),
        "cores": (si.get("cpu") or {}).get("cores"),
        "pcores": (si.get("cpu") or {}).get("performance_cores"),
        "ecores": (si.get("cpu") or {}).get("efficiency_cores"),
        "load": [round(x, 2) for x in ((si.get("cpu") or {}).get("load") or [])][:3],
        "mem_used": (si.get("memory") or {}).get("used"),
        "mem_total": (si.get("memory") or {}).get("total"),
        "swap_used": (si.get("memory") or {}).get("swap_used"),
        "swap_total": (si.get("memory") or {}).get("swap_total"),
        "disk_free": root.get("free"), "disk_total": root.get("total"),
        "processes": (si.get("processes") or {}).get("count"),
        "net_rx": _net(si, "rx_rate"), "net_tx": _net(si, "tx_rate"),
        # the network view's four counts, from the same connection list
        "sockets": {
            "listening": len(rows or []),
            "inbound": sum(1 for c in conns or [] if c.get("direction") == "inbound"),
            "outbound": sum(1 for c in conns or [] if c.get("direction") == "outbound"),
            "public": sum(1 for c in conns or [] if c.get("direction") == "outbound" and c.get("scope") == "public"),
        } if conns is not None else None,
    }

    gate = {
        "reachable": [s["id"] for s in main if s["exposure"] == "reachable"],
        "bound": [s["id"] for s in main if s["exposure"] == "bound"],
        "refused": [s["id"] for s in main if s["exposure"] == "unreachable"],
        "system_reachable": [s["id"] for s in services if s["system"] and s["exposure"] == "reachable"],
        "firewall": ship["firewall"],
        "public_traffic": sum(s["conns_public"] for s in main),
    }
    gate["state"] = ("open" if gate["reachable"] else
                     "watch" if gate["bound"] else "closed")

    ruins = []
    # The lighthouse is always there. It is lit only when an SSH server is
    # actually listening; dark means the scan found nothing on it.
    ssh = [s for s in main if s["family"] == "ssh"]
    inbound = inbound_ssh(conns, {s["port"] for s in ssh})
    ssh_out = [d for d in (outbound or []) if d.get("kind", "ssh") == "ssh"]
    lighthouse = {"listening": bool(ssh), "ids": [s["id"] for s in ssh],
                  # dark: no SSH server. standby: one listens. guiding: someone is coming in.
                  # any SSH session, in or out, lights it
                  "state": "guiding" if (inbound or ssh_out) else "standby" if ssh else "dark",
                  "inbound": inbound,
                  "outbound": ssh_out,
                  "ports": [s["port"] for s in ssh],
                  "why": ("an SSH server is listening on %s" % ", ".join(":%d" % s["port"] for s in ssh))
                  if ssh else "no SSH server is listening on this machine" +
                  (" (on macOS that means Remote Login is off)" if sys.platform == "darwin" else "")}
    live_ports = {s["port"] for s in services}
    for h in history or []:
        if h.get("type") != "closed" or h.get("port") in live_ports:
            continue
        if now - (h.get("ts") or 0) > 6 * 3600:
            continue
        if any(x["port"] == h.get("port") for x in ruins):
            continue
        ruins.append({"port": h.get("port"), "name": h.get("service") or "?",
                      "left_at": h.get("ts"), "text": h.get("text")})

    snap = {
        "schema": SCHEMA, "at": now,
        "ship": ship, "services": services, "workers": workers,
        "sessions": sess_out, "yard": yard, "gate": gate,
        "ruins": ruins[:8], "lighthouse": lighthouse, "traffic": list(traffic or []),
        "islands": list(outbound or []),
        "stats": _stats(main, workers, yard),
    }
    snap["conditions"] = conditions(snap)
    mem = memory_of(snap["services"], history, now)
    for s in snap["services"]:
        s["memory"] = mem.get(s.get("port"))
    return snap


def _net(si, key):
    """Summed interface rate, or None while it is still being measured."""
    vals = [i.get(key) for i in ((si.get("network") or {}).get("interfaces") or [])
            if i.get(key) is not None and not str(i.get("name", "")).startswith("lo")]
    return round(sum(vals)) if vals else None


def _origin_phrase(row):
    try:
        from . import ledger
        return ledger.phrase(row.get("origin"))
    except Exception:
        return ""


def _stats(services, workers, yard):
    return {
        "services": len(services),
        "busy": sum(1 for s in services if s["activity"] == "busy"),
        "active": sum(1 for s in services if s["activity"] in ("busy", "active")),
        "idle": sum(1 for s in services if s["activity"] in ("idle", "long_idle")),
        "measuring": sum(1 for s in services if s["activity"] == "unmeasured"),
        "abandoned": sum(1 for s in services if s["leftover"]),
        "exposed": sum(1 for s in services if s["exposure"] == "reachable"),
        "bound": sum(1 for s in services if s["exposure"] == "bound"),
        "unknown": sum(1 for s in services if s["origin"] in ("unknown", "ambiguous")),
        "attention": sum(1 for s in services if s["risk_band"] in RISKY),
        "agents": sum(1 for w in workers if w["ai"] and w["alive"]),
        "left": sum(1 for s in services if s["lights_left_on"]),
        "containers": sum(1 for c in yard["containers"] if c["running"]),
    }


# ------------------------------------------------------------------ conditions
# Standing state activities: true for as long as the fact is. Priorities are the
# activity library's, so a pet always goes where the most important fact is.
PRIORITY = {
    "SERVICE_EXTERNALLY_REACHABLE": 100,
    "PORT_CONFLICT": 95,
    "SERVICE_UNREACHABLE": 90,
    "HIGH_RISK": 85,
    "SERVICE_BINDS_EXTERNAL_INTERFACE": 70,
    "LISTENING_BUT_UNREACHABLE": 68,
    "STORAGE_PRESSURE": 48,
    "MEMORY_PRESSURE": 62,
    "UNKNOWN_ORIGIN": 60,
    "ATTRIBUTION_AMBIGUOUS": 58,
    "AGENT_LEFT_SERVICE": 55,
    "LEFTOVER": 50,
    "NEW_SERVICE": 45,
    "AGENT_WORKING": 35,
    "CONTAINER_SERVICE_RELATIONSHIP": 32,
    "CONTAINER_STARTED": 30,
    "SERVICE_LONG_IDLE": 25,
    "SERVICE_BUSY": 20,
    "SERVICE_IDLE": 10,
}


def _cond(trigger, subject, meaning, evidence, emotion):
    return {"trigger": trigger, "subject": subject, "meaning": meaning,
            "evidence": evidence, "emotion": emotion,
            "priority": PRIORITY.get(trigger, 5)}


def conditions(snap):
    out = []
    sv = {s["id"]: s for s in snap["services"]}
    for s in snap["services"]:
        if s["system"]:
            continue
        sub = "service:" + s["id"]
        p = ":%d" % s["port"]
        if s["exposure"] == "reachable":
            out.append(_cond("SERVICE_EXTERNALLY_REACHABLE", sub,
                             "%s %s is reachable from beyond this machine" % (p, s["name"]),
                             {"port": s["port"], "bind": s["bind"], "reachable": True,
                              "verified": s["exposure_why"], "origin": s["origin"]}, "alert"))
        elif s["exposure"] == "bound":
            out.append(_cond("SERVICE_BINDS_EXTERNAL_INTERFACE", sub,
                             "%s is bound beyond loopback; reachability is not verified" % p,
                             {"port": s["port"], "bind": s["bind"], "reachable": None}, "cautious"))
        elif s["exposure"] == "unreachable":
            out.append(_cond("LISTENING_BUT_UNREACHABLE", sub,
                             "%s is listening on the network, but the verified path was refused" % p,
                             {"port": s["port"], "bind": s["bind"], "why": s["exposure_why"]}, "puzzled"))
        if s["failure"] == "failed":
            out.append(_cond("SERVICE_UNREACHABLE", sub,
                             "%s is bound but did not answer the probe" % p,
                             {"port": s["port"], "health": s["health"], "detail": s["failure_why"]},
                             "concerned"))
        if s["risk_band"] in RISKY:
            out.append(_cond("HIGH_RISK", sub,
                             "%s is %s risk (%d)" % (p, s["risk_band"].lower(), s["risk"]),
                             {"port": s["port"], "risk": s["risk"], "reasons": s["reasons"]},
                             "alert" if s["risk_band"] == "Critical" else "cautious"))
        if s["origin"] == "unknown":
            out.append(_cond("UNKNOWN_ORIGIN", sub,
                             "nobody knows who started %s. Unknown, not dangerous" % p,
                             {"port": s["port"], "origin": "UNKNOWN", "why": s["origin_why"]},
                             "curious"))
        elif s["origin"] == "ambiguous":
            out.append(_cond("ATTRIBUTION_AMBIGUOUS", sub,
                             "more than one record fits %s, so portlist will not choose" % p,
                             {"port": s["port"], "origin": "AMBIGUOUS"}, "confused"))
        if s["lights_left_on"]:
            out.append(_cond("AGENT_LEFT_SERVICE", sub,
                             "%s exited; %s is still running" % (s["owner_name"], p),
                             {"port": s["port"], "owner": s["owner_name"], "owner_alive": False},
                             "concerned"))
        if s["leftover"]:
            out.append(_cond("LEFTOVER", sub,
                             "%s looks left over" % p,
                             {"port": s["port"], "reasons": s["leftover_why"]}, "curious"))
        elif s["activity"] == "long_idle":
            out.append(_cond("SERVICE_LONG_IDLE", sub, "%s: %s" % (p, s["activity_why"]),
                             {"port": s["port"], "activity": s["activity_why"]}, "sleepy"))
        if s["is_new"] and s["origin"] != "unknown":
            out.append(_cond("NEW_SERVICE", sub, "%s appeared in the last day" % p,
                             {"port": s["port"], "first_seen": s["first_seen"]}, "curious"))
        if s["activity"] == "busy":
            out.append(_cond("SERVICE_BUSY", sub, "%s: %s" % (p, s["activity_why"]),
                             {"port": s["port"], "conns": s["conns"]}, "happy"))
        if s["container"]:
            out.append(_cond("CONTAINER_SERVICE_RELATIONSHIP", sub,
                             "%s is published by container %s" % (p, s["container"]),
                             {"port": s["port"], "container": s["container"]}, "busy"))
    seen = set()
    for s in snap["services"]:
        if s["conflict"] and s["port"] not in seen:
            seen.add(s["port"])
            ids = [s["id"]] + s["conflict"]
            out.append(_cond("PORT_CONFLICT", "port:%d" % s["port"],
                             "%d processes share :%d on different addresses. A client may reach "
                             "a different one than you expect" % (len(ids), s["port"]),
                             {"port": s["port"], "services": ids,
                              "binds": [sv[i]["bind"] for i in ids if i in sv]}, "frustrated"))
    for w in snap["workers"]:
        if w["ai"] and w["alive"] and w["services"]:
            out.append(_cond("AGENT_WORKING", "agent:" + w["key"],
                             "%s is running and holds %d service%s" % (
                                 w["name"], len(w["services"]), "" if len(w["services"]) == 1 else "s"),
                             {"agent": w["name"], "ports": w["ports"]}, "busy"))
    ship = snap["ship"]
    if (ship.get("disk_pct") or 0) >= 90:
        out.append(_cond("STORAGE_PRESSURE", "ship", "the system disk is %.0f%% full" % ship["disk_pct"],
                         {"disk_pct": ship["disk_pct"]}, "concerned"))
    if (ship.get("mem_pct") or 0) >= 90:
        out.append(_cond("MEMORY_PRESSURE", "ship", "memory is %.0f%% used" % ship["mem_pct"],
                         {"mem_pct": ship["mem_pct"]}, "concerned"))
    out.sort(key=lambda c: -c["priority"])
    return out


# ------------------------------------------------------------------ events
FLAP_WINDOW = 600
FLAP_COUNT = 3


class Differ:
    """Two snapshots in, the events between them out.

    The first snapshot produces nothing: "these were already here" is true,
    "fourteen services just arrived" is not. Events are numbered so a page can
    ask for everything after the last one it saw.
    """

    KEEP = 300

    def __init__(self):
        self.prev = None
        self.seq = 0
        self.events = []
        self.starts = {}          # key -> [ts of starts] for flap detection

    def _emit(self, now, trigger, subject, meaning, evidence, out):
        self.seq += 1
        ev = {"seq": self.seq, "ts": now, "trigger": trigger, "subject": subject,
              "meaning": meaning, "evidence": evidence, "source": "scan diff",
              "priority": PRIORITY.get(trigger, EVENT_PRIORITY.get(trigger, 40))}
        out.append(ev)

    def feed(self, snap, now=None):
        now = now or snap.get("at") or time.time()
        out = []
        prev, self.prev = self.prev, snap
        if prev is None:
            return out
        e = lambda *a: self._emit(now, *(a + (out,)))

        # System services come and go (editor helpers especially) and portlist
        # keeps them quiet, so they start no trucks and raise no toasts.
        old = {s["key"]: s for s in prev["services"] if not s["system"]}
        new = {s["key"]: s for s in snap["services"] if not s["system"]}
        started = [k for k in new if k not in old]
        for k in started:
            s = new[k]
            by = s["owner_name"] if s["origin"] in ("known", "recorded") else None
            e("SERVICE_STARTED", "service:" + s["id"],
              ":%d %s started%s" % (s["port"], s["name"], (" by " + by) if by else ""),
              {"port": s["port"], "pid": s["pid"], "origin": s["origin"], "by": by})
            hist = self.starts.setdefault(k, [])
            hist.append(now)
            hist[:] = [t for t in hist if now - t < FLAP_WINDOW]
            if len(hist) >= FLAP_COUNT:
                e("SERVICE_FLAPS", "service:" + s["id"],
                  ":%d started %d times in %d minutes" % (s["port"], len(hist), FLAP_WINDOW // 60),
                  {"port": s["port"], "starts": len(hist)})
        for k in old:
            if k not in new:
                s = old[k]
                e("SERVICE_STOPPED", "service:" + s["id"], ":%d %s stopped listening" % (s["port"], s["name"]),
                  {"port": s["port"], "pid": s["pid"], "uptime": s["uptime"]})
        if len(started) >= 4:
            e("MANY_SERVICES_STARTED", "world", "%d services started at once" % len(started),
              {"count": len(started)})
        for k in new:
            if k not in old:
                continue
            a, b = old[k], new[k]
            sub = "service:" + b["id"]
            p = ":%d" % b["port"]
            if a["pid"] != b["pid"]:
                e("SERVICE_RESTARTED", sub, "%s restarted. Process changed (pid %s to %s), service identity kept"
                  % (p, a["pid"], b["pid"]), {"port": b["port"], "old_pid": a["pid"], "new_pid": b["pid"]})
            if a["exposure"] != b["exposure"]:
                if b["exposure"] == "reachable":
                    e("SERVICE_EXTERNALLY_REACHABLE", sub, "%s became reachable from beyond this machine" % p,
                      {"port": b["port"], "bind": b["bind"], "verified": b["exposure_why"]})
                elif a["exposure"] == "reachable":
                    e("SERVICE_NO_LONGER_EXTERNALLY_REACHABLE", sub, "%s is no longer reachable from outside" % p,
                      {"port": b["port"], "bind": b["bind"]})
                elif b["exposure"] == "bound":
                    e("SERVICE_BINDS_EXTERNAL_INTERFACE", sub, "%s now binds beyond loopback" % p,
                      {"port": b["port"], "bind": b["bind"]})
                elif b["exposure"] == "local":
                    e("SERVICE_LOCAL_ONLY", sub, "%s is back to loopback only" % p, {"port": b["port"]})
            if a["failure"] != b["failure"]:
                if b["failure"] == "failed":
                    e("REACHABILITY_FAILED", sub, "%s stopped answering" % p,
                      {"port": b["port"], "detail": b["failure_why"]})
                elif a["failure"] == "failed":
                    e("SERVICE_RECOVERED", sub, "%s is answering again" % p, {"port": b["port"]})
            if a["activity"] != b["activity"]:
                if b["activity"] == "busy":
                    e("SERVICE_BUSY", sub, "%s got busy: %s" % (p, b["activity_why"]), {"conns": b["conns"]})
                elif b["activity"] in ("idle", "long_idle") and a["activity"] in ("busy", "active"):
                    e("SERVICE_IDLE", sub, "%s went quiet" % p, {"activity": b["activity_why"]})
            if a["origin"] in ("unknown", "ambiguous") and b["origin"] in ("known", "recorded", "system"):
                e("ORIGIN_BECAME_KNOWN", sub, "%s: %s" % (p, b["origin_phrase"] or "origin found"),
                  {"port": b["port"], "origin": b["origin_name"]})
            ra, rb = a["risk_band"] in RISKY, b["risk_band"] in RISKY
            if rb and not ra:
                e("ATTENTION_CREATED", sub, "%s needs attention: %s risk" % (p, b["risk_band"].lower()),
                  {"risk": b["risk"], "reasons": b["reasons"]})
            elif ra and not rb:
                e("ATTENTION_RESOLVED", sub, "%s no longer needs attention" % p, {"risk": b["risk"]})
            if b["lights_left_on"] and not a["lights_left_on"]:
                e("AGENT_EXITED_SERVICE_REMAINS", sub, "%s exited. %s is still running" % (b["owner_name"], p),
                  {"owner": b["owner_name"], "port": b["port"]})

        oc = {s["port"] for s in prev["services"] if s["conflict"]}
        nc = {s["port"] for s in snap["services"] if s["conflict"]}
        for port in nc - oc:
            e("PORT_CONFLICT", "port:%d" % port, "more than one process now listens on :%d" % port, {"port": port})
        for port in oc - nc:
            e("PORT_CONFLICT_RESOLVED", "port:%d" % port, ":%d has one listener again" % port, {"port": port})

        ow = {w["key"]: w for w in prev["workers"]}
        nw = {w["key"]: w for w in snap["workers"]}
        for k, w in nw.items():
            o = ow.get(k)
            if o is None and w["alive"] is not False:
                e("AGENT_STARTED" if w["ai"] else "SESSION_STARTED", "agent:" + k,
                  "%s arrived%s" % (w["name"], " and started " + ", ".join(":%d" % p for p in w["ports"]) if w["ports"] else ""),
                  {"agent": w["name"], "ports": w["ports"]})
            elif o is not None and o["alive"] and w["alive"] is False:
                e("AGENT_EXITED" if w["ai"] else "SESSION_EXITED", "agent:" + k,
                  "%s exited" % w["name"], {"agent": w["name"], "left_running": w["ports"]})

        def cmap(sn):
            return {c["name"]: c for c in sn["yard"]["containers"]}
        oy, ny = cmap(prev), cmap(snap)
        for name, c in ny.items():
            was = oy.get(name)
            if c["running"] and not (was and was["running"]):
                e("CONTAINER_STARTED", "container:" + name, "container %s started" % name,
                  {"image": c["image"], "ports": c["ports"]})
            elif was and was["running"] and not c["running"]:
                failed = "exited (0)" not in (c.get("status") or "").lower() and "exited" in (c.get("status") or "").lower()
                e("CONTAINER_FAILED" if failed else "CONTAINER_STOPPED", "container:" + name,
                  "container %s %s" % (name, "failed: " + c["status"] if failed else "stopped"),
                  {"status": c["status"]})
        for name, c in oy.items():
            if name not in ny and c["running"]:
                e("CONTAINER_STOPPED", "container:" + name, "container %s was removed" % name, {})

        ol = {o["target"]: o for o in prev.get("islands") or []}
        nl = {o["target"]: o for o in snap.get("islands") or []}
        for t, o in nl.items():
            if t not in ol:
                db = o.get("kind") == "db"
                e("DB_SESSION_OPENED" if db else "SSH_SESSION_OPENED", "ssh:%s" % t,
                  "%s session to %s opened" % (o.get("service") if db else "SSH", t),
                  {"target": t, "raddr": o["raddr"], "rport": o["rport"], "service": o.get("service"), "logo": o.get("logo")})
        for t, o in ol.items():
            if t not in nl:
                db = o.get("kind") == "db"
                e("DB_SESSION_CLOSED" if db else "SSH_SESSION_CLOSED", "ssh:%s" % t,
                  "%s session to %s closed" % (o.get("service") if db else "SSH", t), {"target": t, "service": o.get("service")})

        oi = {(o["raddr"], o["rport"]) for o in prev["lighthouse"].get("inbound") or []}
        for o in snap["lighthouse"].get("inbound") or []:
            if (o["raddr"], o["rport"]) not in oi:
                e("SSH_INBOUND_OPENED", "sshin:%s" % o["raddr"], "SSH session from %s arrived" % o["raddr"],
                  {"raddr": o["raddr"], "port": o["lport"]})
        ni = {(o["raddr"], o["rport"]) for o in snap["lighthouse"].get("inbound") or []}
        for k in oi - ni:
            e("SSH_INBOUND_CLOSED", "sshin:%s" % k[0], "SSH session from %s ended" % k[0], {"raddr": k[0]})

        ps, ns = prev["ship"], snap["ship"]
        if (ns.get("disk_pct") or 0) >= 90 > (ps.get("disk_pct") or 0):
            e("STORAGE_PRESSURE", "ship", "the disk crossed 90%", {"disk_pct": ns["disk_pct"]})

        self.events.extend(out)
        self.events = self.events[-self.KEEP:]
        return out

    def since(self, seq):
        return [ev for ev in self.events if ev["seq"] > seq]


EVENT_PRIORITY = {
    "SERVICE_STARTED": 45, "SERVICE_STOPPED": 40, "SERVICE_RESTARTED": 42,
    "SERVICE_FLAPS": 88, "SERVICE_NO_LONGER_EXTERNALLY_REACHABLE": 80,
    "SERVICE_LOCAL_ONLY": 60, "REACHABILITY_FAILED": 90, "SERVICE_RECOVERED": 70,
    "ORIGIN_BECAME_KNOWN": 58, "ATTENTION_CREATED": 86, "ATTENTION_RESOLVED": 72,
    "AGENT_EXITED_SERVICE_REMAINS": 56, "PORT_CONFLICT_RESOLVED": 60,
    "AGENT_STARTED": 40, "SESSION_STARTED": 30, "AGENT_EXITED": 50, "SESSION_EXITED": 30,
    "CONTAINER_STOPPED": 30, "CONTAINER_FAILED": 70, "MANY_SERVICES_STARTED": 50,
    "SSH_SESSION_OPENED": 36, "SSH_SESSION_CLOSED": 30,
    "DB_SESSION_OPENED": 36, "DB_SESSION_CLOSED": 30,
    "SSH_INBOUND_OPENED": 82, "SSH_INBOUND_CLOSED": 60,
}


# ------------------------------------------------------------------ pets
PETS = [
    # name, role, coat
    ("Kelp", "guard", "#41474f"),
    ("Bosun", "inspector", "#e2b07a"),
    ("Pilot", "janitor", "#8c8f96"),
    ("Rivet", "mechanic", "#c8864a"),
    ("Skipper", "courier", "#d9d2c3"),
]

ROLE_TRIGGERS = {
    "guard": {"SERVICE_EXTERNALLY_REACHABLE", "SERVICE_BINDS_EXTERNAL_INTERFACE", "SSH_INBOUND_OPENED",
              "SERVICE_NO_LONGER_EXTERNALLY_REACHABLE", "SERVICE_LOCAL_ONLY", "HIGH_RISK",
              "ATTENTION_CREATED", "ATTENTION_RESOLVED"},
    "inspector": {"UNKNOWN_ORIGIN", "ATTRIBUTION_AMBIGUOUS", "SERVICE_STARTED", "NEW_SERVICE",
                  "PORT_CONFLICT", "PORT_CONFLICT_RESOLVED", "ORIGIN_BECAME_KNOWN",
                  "AGENT_EXITED_SERVICE_REMAINS", "MANY_SERVICES_STARTED"},
    "janitor": {"LEFTOVER", "SERVICE_LONG_IDLE", "SERVICE_STOPPED", "CONTAINER_STOPPED",
                "AGENT_LEFT_SERVICE", "SERVICE_IDLE", "STORAGE_PRESSURE"},
    "mechanic": {"SERVICE_UNREACHABLE", "LISTENING_BUT_UNREACHABLE", "REACHABILITY_FAILED",
                 "SERVICE_RECOVERED", "SERVICE_FLAPS", "SERVICE_RESTARTED", "CONTAINER_FAILED",
                 "MEMORY_PRESSURE"},
    "courier": {"AGENT_WORKING", "CONTAINER_SERVICE_RELATIONSHIP", "CONTAINER_STARTED",
                "AGENT_STARTED", "SESSION_STARTED", "SERVICE_BUSY", "AGENT_EXITED"},
}

# Event-driven reactions that differ from the standing emotion.
EVENT_EMOTION = {
    "SERVICE_NO_LONGER_EXTERNALLY_REACHABLE": "relieved", "SERVICE_LOCAL_ONLY": "relieved",
    "ATTENTION_RESOLVED": "relieved", "SERVICE_RECOVERED": "relieved",
    "ORIGIN_BECAME_KNOWN": "satisfied", "PORT_CONFLICT_RESOLVED": "relieved",
    "SERVICE_STARTED": "curious", "SERVICE_STOPPED": "curious", "SERVICE_FLAPS": "concerned",
    "SERVICE_RESTARTED": "busy", "REACHABILITY_FAILED": "puzzled", "CONTAINER_STARTED": "curious",
    "CONTAINER_STOPPED": "curious", "CONTAINER_FAILED": "concerned", "AGENT_STARTED": "curious",
    "SESSION_STARTED": "curious", "AGENT_EXITED": "curious", "SERVICE_BUSY": "happy",
    "SERVICE_IDLE": "sleepy", "ATTENTION_CREATED": "alert", "MANY_SERVICES_STARTED": "busy",
    "AGENT_EXITED_SERVICE_REMAINS": "concerned", "SSH_INBOUND_OPENED": "alert",
}
EVENT_FRESH = 90           # seconds an event outranks the standing facts
EVENT_BONUS = 12


def plan_pets(snap, events=(), now=None):
    """-> one task per pet: where to go, why, and how to feel about it.

    Each pet takes the highest-priority fact its role cares about. A fresh event
    outranks a standing fact of similar weight, so a change is noticed; once it
    is old it drops away and the pet returns to whatever is still true. With
    nothing to do, a pet patrols and says so.
    """
    now = now or snap.get("at") or time.time()
    fresh = [dict(ev, fresh=True, emotion=EVENT_EMOTION.get(ev["trigger"], "curious"))
             for ev in events if now - ev.get("ts", 0) < EVENT_FRESH]
    pool = list(snap.get("conditions") or []) + fresh
    taken = set()
    tasks = []
    for name, role, coat in PETS:
        mine = [c for c in pool if c["trigger"] in ROLE_TRIGGERS[role]]
        mine.sort(key=lambda c: -(c["priority"] + (EVENT_BONUS if c.get("fresh") else 0)))
        pick = None
        for c in mine:
            if (c["subject"], c["trigger"]) not in taken:
                pick = c
                break
        if pick:
            taken.add((pick["subject"], pick["trigger"]))
            tasks.append({"name": name, "role": role, "coat": coat,
                          "subject": pick["subject"], "trigger": pick["trigger"],
                          "emotion": pick["emotion"], "meaning": pick["meaning"],
                          "evidence": pick["evidence"], "fresh": bool(pick.get("fresh")),
                          "priority": pick["priority"],
                          "queue": len(mine) - 1})
        else:
            tasks.append({"name": name, "role": role, "coat": coat,
                          "subject": None, "trigger": "SYSTEM_QUIET",
                          "emotion": "calm" if role != "janitor" else "sleepy",
                          "meaning": QUIET[role], "evidence": {}, "fresh": False,
                          "priority": 0, "queue": 0})
    return tasks


QUIET = {
    "guard": "nothing is reachable from outside, so the gate stays shut",
    "inspector": "every service has an origin on record and nothing new has arrived",
    "janitor": "nothing looks left over",
    "mechanic": "every service answered its last probe",
    "courier": "no agent is running with services to follow",
}


def chatter(tasks, snap):
    """Pets talking about what they are looking at. Every line is a fact.

    Only pairs that genuinely overlap say anything, and the lines are built from
    the evidence, never from invention.
    """
    by_subject = {}
    for t in tasks:
        if t["subject"]:
            by_subject.setdefault(t["subject"], []).append(t)
    sv = {"service:" + s["id"]: s for s in snap["services"]}
    lines = []
    for sub, ts in by_subject.items():
        roles = {t["role"]: t for t in ts}
        s = sv.get(sub)
        if not s:
            continue
        p = ":%d" % s["port"]
        if "guard" in roles and "inspector" in roles and s["origin"] in ("unknown", "ambiguous"):
            g, i = roles["guard"]["name"], roles["inspector"]["name"]
            lines.append({"subject": sub, "lines": [
                [g, "The gate is open for %s." % p if s["exposure"] == "reachable" else "%s is bound to %s." % (p, s["bind"] or "the network")],
                [i, "Its origin is unknown."],
                [g, "That's not the same thing."],
                [i, "Agreed."]]})
        elif "janitor" in roles and s["lights_left_on"]:
            j = roles["janitor"]["name"]
            lines.append({"subject": sub, "lines": [
                [j, "%s left, and %s is still lit." % (s["owner_name"], p)],
                [j, ("Nobody has used it since." if s["activity"] in ("idle", "long_idle")
                     else "Somebody is still using it." if s["activity"] in ("busy", "active")
                     else "Too early to say whether anyone uses it.")]]})
        elif "mechanic" in roles and s["failure"] != "ok":
            m = roles["mechanic"]["name"]
            lines.append({"subject": sub, "lines": [
                [m, "Knocked on %s. %s." % (p, (s["failure_why"] or "no answer").rstrip("."))]]})
    return lines


# ------------------------------------------------------------------ live
_differ = Differ()
_lock = threading.Lock()
_last_snap = {"t": 0.0, "snap": None}
_sess_cache = {"t": 0.0, "doc": None}


def fleet_harbours(hosts, here=None):
    """-> other machines that report to this one, as distant harbours.

    From the fleet store's summaries: nothing is contacted. A host that has
    stopped reporting stays on the horizon, dark, with how long ago it was seen.
    """
    out = []
    here = (here or "").split(".")[0].lower()
    for h in hosts or []:
        ident = h.get("id") or ""
        if ident in ("127.0.0.1", "localhost", "::1") or (here and (h.get("name") or "").split(".")[0].lower() == here):
            continue
        out.append({"id": ident, "name": h.get("name") or ident, "status": h.get("status"),
                    "age": h.get("age"), "ports": h.get("ports"), "exposed": h.get("exposed"),
                    "critical": h.get("critical"), "high": h.get("high"),
                    "os": (h.get("os") or {}).get("pretty"),
                    "address": ((h.get("addresses") or [{}])[0] or {}).get("ip")})
    out.sort(key=lambda x: ({"online": 0, "stale": 1}.get(x["status"], 2), x["name"]))
    return out[:5]


def _self_cost():
    """What the scanner itself costs, from its own bookkeeping (no extra work)."""
    try:
        from . import scan
        m = scan.self_metrics()
        return {"cpu_pct": m.get("cpu_pct"), "rss": m.get("rss"), "avg_scan_ms": m.get("avg_scan_ms"),
                "scan_duty_pct": m.get("scan_duty_pct")}
    except Exception:
        return None


def collect(force=False):
    """-> a fresh snapshot of this machine, fed through the process-wide differ."""
    from . import scan, collect as col, agents as agents_mod, sessions as sess_mod, history
    rows, host = scan.scan(force=force)
    live = [r for r in rows if not r.get("quiet")]
    try:
        procs = col.processes()
    except Exception:
        procs = None
    try:
        groups = agents_mod.groups(live, procs=procs, stdio=scan.stdio_mcp())
    except Exception:
        groups = []
    try:
        from . import containers as cmod
        cdoc = cmod.inventory()
    except Exception:
        cdoc = {"engine": None, "reachable": False, "containers": [],
                "note": "the container inventory could not be read"}
    # Transcripts change slowly and reading them is the costliest step here,
    # so the session listing is reused for a few polls.
    now = time.time()
    if _sess_cache["doc"] is None or now - _sess_cache["t"] > 10:
        try:
            _sess_cache.update(t=now, doc=sess_mod.listing(limit=24))
        except Exception:
            _sess_cache.update(t=now, doc={})
    sdoc = _sess_cache["doc"]
    try:
        si = scan.system_info()
    except Exception:
        si = {}
    try:
        hist = history.recent(600)
    except Exception:
        hist = []
    try:
        fleet_names, can_inv = set(), False
        try:
            from . import fleet as fleet_mod          # only where there is a fleet to inventory into
            can_inv = True
            for h in fleet_mod.hosts():
                fleet_names.update([h.get("id"), h.get("name")])
        except ImportError:
            pass
        eps = scan.remote_endpoints()
        outbound = sea_destinations(eps, fleet_names, can_inv)
        traffic = traffic_endpoints(eps)
    except Exception:
        outbound, traffic = [], []
    try:
        conns = scan.connections_all(2000)       # cached by the scan; not a second reader
    except Exception:
        conns = []
    snap = build(rows, host, groups, cdoc, sdoc, si, hist, outbound=outbound, conns=conns, traffic=traffic)
    snap["ship"]["self"] = _self_cost()
    try:
        from . import fleet as fleet_mod            # only where a fleet store exists; otherwise none
        snap["fleet"] = fleet_harbours(fleet_mod.hosts(), (host or {}).get("hostname"))
    except Exception:
        snap["fleet"] = []
    try:
        snap["stdio_mcp"] = [{"name": x.get("name"), "pid": x.get("pid")} for x in scan.stdio_mcp()][:12]
    except Exception:
        snap["stdio_mcp"] = []
    _differ.feed(snap)
    _last_snap.update(t=time.time(), snap=snap)
    return snap


_tick = {"thread": None, "seen": 0.0}


def _ticker():
    """Keep the scan fresh while somebody is watching the world.

    The scan refreshes when a request finds it stale, so on its own a stopped
    service lingered for a poll or two: six to nine seconds of a building that
    was no longer there. While a page has asked within the last half minute,
    this rescans back to back instead, and then goes quiet.
    """
    from . import scan
    last_ids, changed_at = None, 0.0
    while time.time() - _tick["seen"] < 30:
        try:
            rows, _ = scan._scan_now(force=True)
            ids = frozenset(r.get("id") for r in rows)
            if ids != last_ids:
                changed_at, last_ids = time.time(), ids
        except Exception:
            pass
        # quick while things are moving, relaxed while nothing is: a quiet
        # machine costs half as much to watch
        time.sleep(2.0 if time.time() - changed_at < 20 else 4.0)
    _tick["thread"] = None


def _watching():
    _tick["seen"] = time.time()
    t = _tick["thread"]
    if t is None or not t.is_alive():
        t = threading.Thread(target=_ticker, name="world-ticker", daemon=True)
        _tick["thread"] = t
        t.start()


def payload(since=0, force=False, keep_fresh=False):
    """-> what /api/world answers: the snapshot, new events, pet plan, chatter.

    It reads the scan every other view reads, cached and shared, and never
    starts a second one. `keep_fresh` is only for `portlist --world` on its
    own, where nothing else in the process is refreshing the scan: a web
    server or a terminal that already refreshes it must not add another loop.

    Locked, because a web server answers from several threads and the differ
    is one sequence: two scans fed at once would number events twice.
    """
    if keep_fresh:
        _watching()
    with _lock:
        snap = collect(force=force)
        recent = _differ.events[-40:]
        new = _differ.since(since)
        seq = _differ.seq
    tasks = plan_pets(snap, recent)
    doc = dict(snap)
    doc["events"] = new
    doc["seq"] = seq
    doc["pets"] = tasks
    doc["chatter"] = chatter(tasks, snap)
    doc["history"] = _history_feed(snap)
    return doc


# ------------------------------------------------------------------ the past
def reconstruct(now_rows, events, at):
    """-> the listeners at time `at`, as far as the history can say.

    Start from what is listening now and walk the recorded opens and closes
    back to `at`: an open after `at` had not happened yet, a close after `at`
    was still listening. Only port, process, service name and exposure are
    recorded, so that is all a past harbour can show.
    """
    live = {}
    for r in now_rows or []:
        if r.get("quiet"):
            continue
        live[(r.get("port"), r.get("pid"))] = {"port": r.get("port"), "pid": r.get("pid"),
                                               "service": r.get("service") or r.get("cmd") or "?",
                                               "exposure": (r.get("exposure") or {}).get("level") or "loopback"}
    for e in sorted(events or [], key=lambda e: -(e.get("ts") or 0)):
        if (e.get("ts") or 0) <= at:
            break
        k = (e.get("port"), e.get("pid"))
        if e.get("type") == "opened":
            live.pop(k, None)
        elif e.get("type") == "closed":
            live[k] = {"port": e.get("port"), "pid": e.get("pid"), "service": e.get("service") or "?",
                       "exposure": e.get("exposure") or "loopback"}
    return sorted(live.values(), key=lambda x: (x["port"] or 0, x["pid"] or 0))


def _past_row(x):
    sid = None
    try:
        from . import catalog
        for sig in catalog.SERVICES:
            if sig.get("name") == x["service"]:
                sid = sig["id"]
                break
    except Exception:
        pass
    level = x["exposure"]
    return {"id": "%s-%s" % (x["port"], x["pid"]), "port": x["port"], "pid": x["pid"],
            "cmd": x["service"], "cmdline": x["service"], "service": x["service"], "service_id": sid,
            "exposure": {"level": level, "addrs": ["127.0.0.1"] if level == "loopback" else ["*"]},
            "activity": {"known": False, "note": "use is not recorded for the past"},
            "conns": 0, "health": "nodata", "risk": 0, "risk_band": "", "reasons": [],
            "leftover": {"likely": False}, "quiet": False, "starter": {}, "origin": {"matched": "none"}}


def past_payload(at):
    """What /api/world?at= answers: the harbour at a moment in the recorded history."""
    from . import scan, history
    rows, host = scan.scan()
    events = history.recent(100000)
    oldest = min((e.get("ts") or 0 for e in events), default=None)
    past = [_past_row(x) for x in reconstruct(rows, events, at)]
    snap = build(past, {"hostname": (host or {}).get("hostname")}, [],
                 {"engine": None, "reachable": False, "containers": [], "note": "containers are not recorded for the past"},
                 {}, {"hostname": (host or {}).get("hostname")}, [], now=at)
    # who started them was not recorded: say that, rather than calling them unknown
    for sv in snap["services"]:
        sv["origin"], sv["origin_why"], sv["origin_phrase"] = "unrecorded", "not recorded for the past", ""
    snap["stats"] = _stats([x for x in snap["services"] if not x["system"]], snap["workers"], snap["yard"])
    snap["conditions"] = conditions(snap)
    doc = dict(snap)
    doc["past"] = {"at": at, "oldest": oldest,
                   "before_history": oldest is not None and at < oldest,
                   "note": "Reconstructed from recorded opens and closes: listeners and their exposure only. "
                           "Use, owners, sessions, traffic and containers are not recorded for the past."}
    doc["events"], doc["seq"] = [], _differ.seq
    doc["pets"] = plan_pets(snap, [], now=at)
    doc["chatter"] = []
    doc["history"] = []
    doc["timeline"] = [{"ts": e.get("ts"), "type": e.get("type"), "port": e.get("port"), "text": e.get("text")}
                       for e in events if e.get("type") in ("opened", "closed")][:2000]
    return doc


def timeline():
    """Recorded opens and closes for the scrubber, newest first. Cheap: one file read."""
    try:
        from . import history
        ev = history.recent(100000)
    except Exception:
        ev = []
    return [{"ts": e.get("ts"), "type": e.get("type"), "port": e.get("port"), "text": e.get("text")}
            for e in ev if e.get("type") in ("opened", "closed")][:2000]


def _history_feed(snap):
    """Recent opens and closes from portlist's own history, for the timeline.

    These are what happened before this page was open, labelled as history so
    they are never mistaken for something happening now.
    """
    try:
        from . import history
        out = []
        for h in history.recent(30):
            out.append({"ts": h.get("ts"), "type": h.get("type"), "port": h.get("port"),
                        "text": h.get("text"), "source": "history"})
        return out
    except Exception:
        return []


def dumps(doc):
    return json.dumps(doc, default=str, separators=(",", ":"))

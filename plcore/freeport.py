"""A port that will still be free in ten minutes.

`is_port_free` answers a question about right now. It does not stop the thing
people actually complain about, which is an agent finding :8000 busy and walking
to 8001, 8002, 8003 until something sticks - straight through the ports three
other projects use, which are free at this instant only because those projects
are not running yet.

Portlist already knows more than a bind test does. The recipe book records which
ports each project's services have taken before, keyed by command signature
rather than by port, so it survives the service moving. That turns "free now"
into "free, and not spoken for".

A suggestion always carries its reasons. "Use 3007" is a guess; "3007: nothing is
listening, no project here has used it, and it is not a registered service port"
is an answer.
"""
import socket

from . import recipes, scan

# Ports somebody else's software expects to own. Binding a dev server on one of
# these works right up until you install the thing that wants it.
WELL_KNOWN = {
    22: "SSH", 25: "SMTP", 53: "DNS", 80: "HTTP", 88: "Kerberos", 110: "POP3",
    143: "IMAP", 389: "LDAP", 443: "HTTPS", 445: "SMB", 587: "SMTP submission",
    631: "printing", 993: "IMAPS", 995: "POP3S",
    1433: "SQL Server", 1521: "Oracle", 2049: "NFS", 2375: "Docker API",
    2376: "Docker API (TLS)", 3306: "MySQL", 3389: "RDP", 4444: "commonly a debugger",
    5000: "AirPlay on macOS", 5432: "PostgreSQL", 5433: "PostgreSQL (second)",
    5672: "RabbitMQ", 5900: "VNC", 6379: "Redis", 6443: "Kubernetes API",
    7337: "Portlist", 8080: "HTTP alternate", 8443: "HTTPS alternate",
    9000: "commonly PHP-FPM or MinIO", 9090: "Prometheus", 9200: "Elasticsearch",
    11211: "memcached", 27017: "MongoDB",
}
# Where to look. Deliberately above the ranges frameworks default to, so a
# suggestion does not collide with the next `npm create` somebody runs.
DEFAULT_RANGE = (4100, 4999)
FLOOR, CEILING = 1024, 65535

# The bands every retry loop walks. Suggesting 8001 because 8000 was busy is not
# a fix: it is the same collision one port later, and it is where the *other*
# agent on this machine is about to look too. A suggestion has to leave the
# crowd, not join the back of it.
CROWDED = ((3000, 3020), (4000, 4010), (5000, 5010), (5173, 5183), (7000, 7010),
           (8000, 8020), (8080, 8100), (8888, 8898), (9000, 9010))


def crowded(port):
    return any(lo <= port <= hi for lo, hi in CROWDED)


def _seed(project):
    """A stable starting point per project, so the same project is offered the
    same port tomorrow. Deterministic, not random: a suggestion that moves every
    time is one nobody can write into a config."""
    import hashlib
    lo, hi = DEFAULT_RANGE
    if not project:
        return lo
    h = hashlib.blake2b(str(project).encode(), digest_size=4).digest()
    return lo + int.from_bytes(h, "big") % (hi - lo + 1)


def bindable(port, host="127.0.0.1"):
    """Can this process actually bind it? The only test that is not a guess."""
    for family, addr in ((socket.AF_INET, (host, port)),):
        s = socket.socket(family, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(addr)
            return True
        except OSError:
            return False
        finally:
            s.close()
    return False


def claims(rows=None, book=None):
    """-> {port: [reasons]} for everything that is taken or spoken for."""
    if rows is None:
        rows, _ = scan.scan()
    if book is None:
        try:
            book = recipes._load()
        except Exception:
            book = {}
    out = {}

    def add(port, why):
        try:
            port = int(port)
        except (TypeError, ValueError):
            return
        out.setdefault(port, [])
        if why not in out[port]:
            out[port].append(why)

    for r in rows:
        add(r["port"], "%s is listening on it"
            % (r.get("service") or r.get("cmd") or "something"))
    for e in (book.values() if isinstance(book, dict) else []):
        name = e.get("name") or e.get("project") or e.get("cmd") or "a remembered service"
        for p in (e.get("ports") or []):
            add(p, "%s has used it before" % name)
        if e.get("last_port"):
            add(e["last_port"], "%s used it last time" % name)
    for p, what in WELL_KNOWN.items():
        add(p, "%s expects it" % what)
    return out


def check(port, rows=None, book=None):
    """-> {port, free, bindable, claimed_by, safe}. Free and safe are different."""
    held = claims(rows, book)
    listening = [r for r in (rows if rows is not None else scan.scan()[0])
                 if r["port"] == port]
    can = bindable(port)
    return {"port": port,
            "free": not listening,
            "bindable": can,
            "claimed_by": held.get(port, []),
            "safe": can and not held.get(port)}


def suggest(preferred=None, count=3, rows=None, book=None, host="127.0.0.1",
            project=None):
    """-> ports that are free now, not spoken for, and out of the crowded bands.

    The starting point is derived from the project, so the same project is
    offered the same port every time. That matters more than it sounds: a
    suggestion that moves on every call cannot be written into a `.env` and
    stops being a suggestion at all.
    """
    if rows is None:
        rows, _ = scan.scan()
    held = claims(rows, book)
    lo, hi = DEFAULT_RANGE
    span = hi - lo + 1
    start = _seed(project)
    # Walk the quiet band from this project's own seed, wrapping once.
    order = [lo + ((start - lo) + i) % span for i in range(span)]
    out = []
    for p in order:
        if p in held or crowded(p) or not bindable(p, host):
            continue
        why = ["nothing is listening on it",
               "no project on this machine has used it",
               "it is not a port other software expects",
               "it is outside the ranges retry loops walk"]
        if project and p == start:
            why.append("it is derived from this project, so it will be offered "
                       "again next time")
        out.append({"port": p, "why": why})
        if len(out) >= count:
            break
    return out


def explain(preferred, rows=None, book=None, project=None):
    """The text `portlist port --free` prints and the MCP tool returns."""
    if rows is None:
        rows, _ = scan.scan()
    book = book if book is not None else (recipes._load() if hasattr(recipes, "_load") else {})
    lines = []
    if preferred:
        st = check(int(preferred), rows, book)
        if st["safe"]:
            return {"ok": True, "port": int(preferred), "suggestions": [],
                    "text": "Port %d is free and nothing on this machine has a claim "
                            "on it. Use it." % int(preferred)}
        lines.append("Port %d is not a safe choice:" % int(preferred))
        if not st["free"]:
            lines.append("  it is in use right now")
        elif not st["bindable"]:
            lines.append("  it cannot be bound from this process")
        for why in st["claimed_by"]:
            lines.append("  %s" % why)
        lines.append("")
    picks = suggest(preferred, 3, rows, book, project=project)
    if not picks:
        lines.append("No port in the search range is both free and unclaimed.")
        return {"ok": False, "port": preferred, "suggestions": [], "text": "\n".join(lines)}
    lines.append("Use %d." % picks[0]["port"])
    for w in picks[0]["why"]:
        lines.append("  %s" % w)
    if len(picks) > 1:
        lines.append("")
        lines.append("Also free: %s"
                     % ", ".join(str(s["port"]) for s in picks[1:]))
    if preferred:
        lines.append("")
        lines.append("Not %d. That is where the next retry loop looks, and where "
                     "the" % (int(preferred) + 1))
        lines.append("other agent on this machine is about to look too.")
    return {"ok": True, "port": preferred, "suggestions": picks, "text": "\n".join(lines)}

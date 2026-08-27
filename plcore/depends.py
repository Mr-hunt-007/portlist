"""Which local service is talking to which other local service.

"What is running" is easy. "Why is this running" is the valuable question, and
half of the answer is what else on this machine needs it. A Postgres nobody
connects to and a Postgres your API holds eight connections into are the same row
in every port list ever written, and they are not the same thing at all.

This is measured from established connections, not guessed from names. An
outbound loopback connection from process A to a port held by service B is B
being used by A, right now. That is evidence.

The one rule that matters here: **absence is not evidence of absence.** A pool
that has gone idle, a client that reconnects per request, a service that has not
been touched since you opened this page - all of them show nothing. So this
reports what it saw, with a count, and never says "nothing depends on this". It
says "no connection right now", which is a different and true statement.
"""

# A dependency on one of these is worth naming in a sentence; a dependency on a
# random high port usually is not. Only used for wording, never for detection.
NAMED = {"database", "cache", "queue", "search", "AI runtime", "AI app",
         "MCP server", "Object store"}


def build(rows, conns):
    """Attach depends_on / used_by to every row. Mutates and returns rows."""
    by_port = {}
    for r in rows:
        by_port.setdefault(r["port"], []).append(r)
    by_pid = {r["pid"]: r for r in rows if r.get("pid") is not None}

    for r in rows:
        r["depends_on"] = []
        r["used_by"] = []

    # pid -> {port: count} for loopback traffic leaving that process
    out = {}
    # port -> {pid: (name, count)} for loopback traffic arriving at that port
    inn = {}
    for c in conns or []:
        if c.get("scope") != "loopback":
            continue
        pid, rport = c.get("pid"), c.get("rport")
        if pid is None or rport is None:
            continue
        if c.get("direction") == "outbound":
            out.setdefault(pid, {})
            out[pid][rport] = out[pid].get(rport, 0) + 1
            inn.setdefault(rport, {})
            slot = inn[rport].setdefault(pid, {"pid": pid, "name": c.get("name"),
                                               "cmdline": c.get("cmdline"), "count": 0})
            slot["count"] += 1

    for pid, ports in out.items():
        src = by_pid.get(pid)
        for port, n in ports.items():
            targets = by_port.get(port) or []
            for t in targets:
                if t.get("pid") == pid:
                    continue                  # a process talking to itself
                if src is not None:
                    src["depends_on"].append(_edge(t, n))
    for port, callers in inn.items():
        for t in (by_port.get(port) or []):
            for caller in callers.values():
                if caller["pid"] == t.get("pid"):
                    continue
                known = by_pid.get(caller["pid"])
                t["used_by"].append({
                    "id": known["id"] if known else None,
                    "pid": caller["pid"],
                    "name": (known.get("service") or known.get("cmd")) if known
                            else (caller.get("name") or "a process"),
                    "port": known["port"] if known else None,
                    "listening": known is not None,
                    "conns": caller["count"],
                    "project": ((known.get("project") or {}).get("name")) if known else None,
                })
    for r in rows:
        r["depends_on"].sort(key=lambda d: -d["conns"])
        r["used_by"].sort(key=lambda d: -d["conns"])
    return rows


def _edge(target, count):
    return {"id": target["id"], "port": target["port"],
            "name": target.get("service") or target.get("cmd") or "something",
            "cat": target.get("service_cat"),
            "project": (target.get("project") or {}).get("name"),
            "conns": count}


def sentence(row):
    """One line for the drawer. Says what was seen, never what was not."""
    dep, used = row.get("depends_on") or [], row.get("used_by") or []
    bits = []
    if dep:
        bits.append("It is connected to " + _list(
            ["%s on :%d" % (d["name"], d["port"]) for d in dep]) + ".")
    if used:
        named = _list(["%s%s" % (u["name"], "" if u["listening"] else " (not listening)")
                       for u in used[:4]])
        more = "" if len(used) <= 4 else " and %d more" % (len(used) - 4)
        bits.append("%s %s using it right now." % (named + more,
                                                   "is" if len(used) == 1 else "are"))
    if not bits:
        # Not "nothing depends on it". An idle pool looks exactly like this.
        return ("No local service is connected to it at this moment, which is not "
                "the same as nothing needing it - an idle connection pool looks "
                "identical from here.")
    return " ".join(bits)


def _list(items):
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]


def chains(rows, limit=12):
    """-> readable A -> B edges, for a panel or a summary. Deduplicated."""
    seen, out = set(), []
    for r in rows:
        a = r.get("service") or r.get("cmd") or ":%d" % r["port"]
        for d in (r.get("depends_on") or []):
            key = (r["id"], d["id"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"from": a, "from_id": r["id"], "from_port": r["port"],
                        "to": d["name"], "to_id": d["id"], "to_port": d["port"],
                        "conns": d["conns"],
                        "project": (r.get("project") or {}).get("name")})
    out.sort(key=lambda e: -e["conns"])
    return out[:limit]

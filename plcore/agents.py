"""What each agent, editor and terminal left running on this machine.

Portlist already worked out who started every service. It just never grouped by
it, and grouping is the whole question people actually have: not "what is on
:3001" but "what has Claude Code got running, and do I still need any of it?"

Two honesty rules, both of which cost more code than ignoring them would.

**Unknown is a group, not a gap.** A reparented process has lost its ancestry and
an unreadable environment gives nothing away, so some services genuinely cannot
be attributed. Those go in a group that says so, rather than being dropped from
the page or quietly filed under the last agent seen. A page that shows six
services under three agents while nine are running is worse than no page.

**Still here is not the same as still running.** The agent that started a service
may itself have exited. That is the single strongest signal that what it left
behind is forgotten, so it is stated per group rather than inferred from a date.
"""
import time

from . import lifecycle

AI = lifecycle.AI_KINDS
UNKNOWN = "unknown"


def _bucket(row):
    """-> (key, name, kind). One row, one owner."""
    who = row.get("starter") or {}
    kind = who.get("class") or ""
    name = who.get("name")
    ident = who.get("kind") or who.get("id")
    if not name:
        return UNKNOWN, "Not attributed", "unknown"
    # Two Claude Code sessions are two owners: the pid is what makes "this one
    # has exited" answerable at all.
    pid = who.get("pid")
    key = "%s:%s" % (ident or name, pid if pid is not None else "-")
    return key, name, kind


def groups(rows, procs=None, stdio=None, now=None):
    """-> one entry per starter, most services first.

    `procs` is the live process table; without it, "has it exited" is reported as
    unknown rather than guessed.
    """
    now = now or time.time()
    out = {}
    for r in rows:
        if r.get("quiet"):
            continue
        key, name, kind = _bucket(r)
        who = r.get("starter") or {}
        g = out.get(key)
        if not g:
            g = {"key": key, "name": name, "class": kind or "unknown",
                 # The starter's own kind, so a surface can pick an icon for it
                 # without parsing the group key back apart.
                 "kind": who.get("kind"),
                 "ai": bool(who.get("ai")) or (who.get("kind") in AI),
                 "pid": who.get("pid"),
                 # starter() already knows: ancestry hits are alive by
                 # construction, an environment hit whose parent is gone is not.
                 "alive": who.get("alive"),
                 "via": who.get("via"), "evidence": who.get("evidence"),
                 "services": [], "projects": [], "ports": [],
                 "mcp": [], "started_at": None}
            out[key] = g
        g["services"].append(_thin(r))
        g["ports"].append(r["port"])
        p = (r.get("project") or {}).get("name")
        if p and p not in g["projects"]:
            g["projects"].append(p)
        started = r.get("started")
        if started and (g["started_at"] is None or started < g["started_at"]):
            g["started_at"] = started

    # A stdio MCP server holds no port, so nothing above saw it - and it is
    # exactly the kind of thing an agent leaves behind.
    for s in (stdio or []):
        who = (s.get("starter") or {})
        name = who.get("name")
        if not name:
            key, name, kind = UNKNOWN, "Not attributed", "unknown"
        else:
            key = "%s:%s" % (who.get("kind") or who.get("id") or name,
                             who.get("pid") if who.get("pid") is not None else "-")
            kind = who.get("class") or ""
        g = out.get(key)
        if not g:
            g = {"key": key, "name": name, "class": kind or "unknown",
                 # The starter's own kind, so a surface can pick an icon for it
                 # without parsing the group key back apart.
                 "kind": who.get("kind"),
                 "ai": bool(who.get("ai")) or (who.get("kind") in AI),
                 "pid": who.get("pid"), "alive": who.get("alive"),
                 "via": who.get("via"), "evidence": who.get("evidence"),
                 "services": [], "projects": [], "ports": [], "mcp": [],
                 "started_at": None}
            out[key] = g
        g["mcp"].append({"pid": s.get("pid"), "name": s.get("name") or s.get("cmd"),
                         "cmd": s.get("cmd"), "dir_short": s.get("dir_short")})

    for g in out.values():
        if g["pid"] is not None and procs is not None:
            g["alive"] = g["pid"] in procs
        # An environment variable names the tool, not the run. Several sessions
        # of the same agent collapse into one bucket here, and a page that said
        # "a Claude Code session left 11 services" when it may have been three
        # would be overstating what was measured.
        g["one_session"] = g["pid"] is not None
        if not g["one_session"] and g["key"] != UNKNOWN:
            g["note"] = ("attributed from the environment, which names the tool "
                         "rather than one particular run - these may come from "
                         "more than one session")
        g["ports"] = sorted(set(g["ports"]))
        g["count"] = len(g["services"])
        g["mcp_count"] = len(g["mcp"])
        g["leftovers"] = sum(1 for s in g["services"] if (s.get("leftover") or {}).get("likely"))
        g["exposed"] = sum(1 for s in g["services"] if s.get("exposure") != "loopback")
        g["idle"] = sum(1 for s in g["services"]
                        if (s.get("activity") or {}).get("known")
                        and not (s.get("activity") or {}).get("ever_busy"))
        g["age"] = round(now - g["started_at"]) if g["started_at"] else None
    order = sorted(out.values(),
                   key=lambda g: (g["key"] == UNKNOWN,      # unattributed last
                                  not g["ai"],              # agents first
                                  -(g["count"] + g["mcp_count"]),
                                  g["name"]))
    return order


def _thin(r):
    """The fields an agent view needs. The full row is one request away."""
    return {"id": r["id"], "port": r["port"], "pid": r.get("pid"),
            "service": r.get("service") or r.get("cmd"),
            "cmd": r.get("cmd"),
            "project": (r.get("project") or {}).get("name"),
            "dir_short": r.get("dir_short"),
            "health": r.get("health"),
            "exposure": (r.get("exposure") or {}).get("level"),
            "risk": r.get("risk"), "risk_band": r.get("risk_band"),
            "uptime": r.get("uptime"), "started": r.get("started"),
            "conns": r.get("conns"),
            "activity": r.get("activity"),
            "container": r.get("container"),
            "leftover": r.get("leftover"),
            "url": r.get("url")}


def summary(gs):
    """The one paragraph at the top of the page."""
    ai = [g for g in gs if g["ai"]]
    return {
        "agents": len(ai),
        "by_agents": sum(g["count"] for g in ai),
        "mcp_by_agents": sum(g["mcp_count"] for g in ai),
        "gone": sum(1 for g in ai if g["alive"] is False),
        "orphaned": sum(g["count"] for g in ai if g["alive"] is False),
        "unattributed": sum(g["count"] for g in gs if g["key"] == UNKNOWN),
        "total": sum(g["count"] for g in gs),
        "leftovers": sum(g["leftovers"] for g in gs),
    }


def sentence(s):
    """Plain English, and it says when it does not know."""
    if not s["total"]:
        return "Nothing is listening on this machine."
    bits = []
    if s["by_agents"]:
        bits.append("%d of %d services were started by %d AI agent%s"
                    % (s["by_agents"], s["total"], s["agents"],
                       "" if s["agents"] == 1 else "s"))
    else:
        bits.append("%d services are listening, none of them started by an agent "
                    "Portlist recognises" % s["total"])
    if s["orphaned"]:
        bits.append("%d of those outlived the session that started %s"
                    % (s["orphaned"], "it" if s["orphaned"] == 1 else "them"))
    if s["unattributed"]:
        bits.append("%d could not be attributed to anything" % s["unattributed"])
    return ". ".join(bits) + "."

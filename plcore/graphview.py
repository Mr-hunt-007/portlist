# -*- coding: utf-8 -*-
"""The graph, in a terminal. View 9.

The same relationships a node-link diagram would show - started by, project,
process, port, reachable from - drawn the way a terminal draws a layered graph
well. Sixteen free-floating nodes in a terminal is not a diagram; a tree with
continuous rules is.

Every edge has a name, and the names are in the header, so the picture and the
words agree:

    started by ─ started work in ─ project ─ runs ─ process ─ listens ─ port
                                                    ─ confirmed on ─ reachable from

One line is one service. A parent is printed on the first line that needs it and
carried down with a rule, which is what makes the sharing visible: four services
in one project, or eleven started by one agent session, is the fact this view
exists to show.
"""
from . import lifecycle, projects


def _starter_name(row):
    who = row.get("starter") or {}
    return (lifecycle.short_starter(who.get("name") or "unattributed"),
            who.get("class") or "", bool(who.get("ai")))


def _project_name(row):
    key = projects.key_for(row)
    return key[1] if key else None


def order(rows):
    """Graph order: by starter, then project, then port. Grouping is the point."""
    def sort_key(r):
        name, _cls, ai = _starter_name(r)
        return (0 if ai else 1, name, _project_name(r) or "~", r.get("port") or 0)
    return sorted(rows, key=sort_key)


def _rule(t, y, x0, x1, tone):
    """Fill the gap between two columns so the line is actually a line.

    Drawn as separate stubs (`──Python pid 6810 ──:8000`) the connectors read as
    prefixes on each column rather than as edges between them, which is the one
    thing a graph has to get right.
    """
    if x1 > x0:
        t.put(y, x0, "─" * (x1 - x0), tone)


def draw(t, h, w):
    if _tone is None:
        _bind()
    rows = t.visible()
    if not rows:
        t.put(6, 2, "nothing is listening", C_DIM)
        return

    wide = w >= 122
    if w < 100:
        # Below this the columns cannot coexist, so the graph becomes headed
        # groups: what a tree looks like when it runs out of width.
        return _narrow(t, h, w, order(rows))

    x_proj = 5
    x_proc = 30 if wide else 28
    x_port = 52 if wide else 48
    x_zone = 84 if wide else 76
    x_note = 104

    # One label for the tree: "STARTED BY" and "PROJECT" as separate headings
    # collided into "STARTPROJECT", and the tree already shows which is which.
    t.put(3, 2, "WHO STARTED IT, AND WHERE", C_DIM, True)
    t.put(3, x_proc, "PROCESS", C_DIM, True)
    t.put(3, x_port, "PORT  AND SERVICE", C_DIM, True)
    t.put(3, x_zone, "REACHABLE FROM", C_DIM, True)
    if wide:
        t.put(3, x_note, "CONFIRMED ON", C_DIM, True)
    # The edge names, under the columns they belong to.
    t.put(4, 2, "started work in ─▸", C_DIM)
    t.put(4, x_proc - 8, "runs ─▸", C_DIM)
    t.put(4, x_port - 9, "listens ─▸", C_DIM)

    # Group into starter -> project -> services, which is the graph's shape.
    groups = []
    for r in order(rows):
        name, cls, ai = _starter_name(r)
        proj = _project_name(r) or "no project"
        if not groups or groups[-1][0] != name:
            groups.append((name, cls, ai, []))
        projs = groups[-1][3]
        if not projs or projs[-1][0] != proj:
            projs.append((proj, []))
        projs[-1][1].append(r)

    y = 6
    for name, cls, ai, projs in groups:
        if y >= h - 3:
            t.put(y, 2, "more, in the list view", C_DIM)
            return
        t.put(y, 2, "◆" if ai else "◇", C_VIOLET if ai else C_DIM, True)
        t.put(y, 4, name[:22], C_NORM, True)
        count = sum(len(svcs) for _p, svcs in projs)
        t.put(y, x_proc, "%s%s%d service%s" % (cls[:16], "  ·  " if cls else "",
                                           count, "" if count == 1 else "s"), C_DIM)
        y += 1

        for pi, (proj, svcs) in enumerate(projs):
            last_proj = pi == len(projs) - 1
            for si, r in enumerate(svcs):
                if y >= h - 3:
                    t.put(y, 2, "more, in the list view", C_DIM)
                    return
                picked = r["id"] == t.sel_id
                if picked:
                    t.put(y, 1, " " * (w - 2), C_SEL)
                dim = C_SEL if picked else C_DIM

                # the project branch, drawn once per project
                if si == 0:
                    t.put(y, x_proj - 3, "└─" if last_proj else "├─", dim)
                    t.put(y, x_proj - 1, " ", dim)
                    t.put(y, x_proj, proj[:20], C_SEL if picked else C_NORM)
                    _rule(t, y, x_proj + len(proj[:20]) + 1, x_proc - 3, dim)
                else:
                    if not last_proj:
                        t.put(y, x_proj - 3, "│", dim)

                # the service branch, drawn once per service under the project
                if len(svcs) > 1:
                    mark = ("┬" if si == 0 else
                            "└" if si == len(svcs) - 1 else "├")
                    t.put(y, x_proc - 3, mark + "─", dim)
                    if si and si < len(svcs) - 1:
                        pass
                elif si == 0:
                    t.put(y, x_proc - 3, "──", dim)

                pid = r.get("pid")
                proc = "%s %s" % ((r.get("cmd") or "?")[:9],
                                  pid if pid is not None else "-")
                t.put(y, x_proc, proc[:18], C_SEL if picked else C_DIM)
                _rule(t, y, x_proc + len(proc[:18]) + 1, x_port - 1, dim)

                t.put(y, x_port, ":%-6s" % r.get("port"),
                      C_SEL if picked else _tone(r), True)
                svc = (r.get("service") or "unidentified")[:22]
                t.put(y, x_port + 8, svc, C_SEL if picked else C_NORM)
                _rule(t, y, x_port + 9 + len(svc), x_zone - 1, dim)

                exp = r.get("exposure") or {}
                t.put(y, x_zone, (exp.get("label") or "?")[:18],
                      C_SEL if picked else _tone(r))
                ver = exp.get("verified") or {}
                if wide and ver.get("accepting") and ver.get("ip"):
                    t.put(y, x_note, ver["ip"][:22], C_SEL if picked else C_AMBER)
                elif wide and (r.get("depends_on") or r.get("used_by")):
                    n = len(r.get("depends_on") or []) + len(r.get("used_by") or [])
                    t.put(y, x_note, "%d local link%s" % (n, "" if n == 1 else "s"), dim)
                y += 1
        y += 1

    ai_rows = [r for r in rows if (r.get("starter") or {}).get("ai")]
    if y < h - 2:
        t.put(y, 2, "◆ an agent session   ◇ something else   "
              "%d of %d services were started by an agent"
              % (len(ai_rows), len(rows)), C_DIM)


def _narrow(t, h, w, ordered):
    """Groups with headers, for terminals too narrow for columns."""
    y = 3
    prev = None
    for i, r in enumerate(ordered):
        if y >= h - 2:
            t.put(y, 2, "%d more" % (len(ordered) - i), C_DIM)
            return
        name, cls, ai = _starter_name(r)
        if name != prev:
            if prev is not None:
                y += 1
            if y >= h - 3:
                return
            t.put(y, 1, "◆" if ai else "◇", C_VIOLET if ai else C_DIM, True)
            t.put(y, 3, name[:22], C_NORM, True)
            if cls and w > 44:
                t.put(y, 26, cls[:16], C_DIM)
            prev = name
            y += 1
        picked = r["id"] == t.sel_id
        if picked:
            t.put(y, 1, " " * (w - 2), C_SEL)
        exp = r.get("exposure") or {}
        t.put(y, 3, ":%-6s" % r.get("port"), C_SEL if picked else _tone(r), True)
        t.put(y, 11, (r.get("service") or "unidentified")[:min(22, w - 32)],
              C_SEL if picked else C_NORM)
        t.put(y, max(34, w - 18), (exp.get("label") or "?")[:16],
              C_SEL if picked else _tone(r))
        y += 1


def _last_project(ordered, i, name, proj):
    """Is this the last *project* under this starter?

    The siblings in this tree are projects, not rows. Asking whether another row
    follows in the same project drew the closing corner first and the tee after
    it, which is a bracket pointing at nothing.
    """
    for r in ordered[i + 1:]:
        n, _c, _a = _starter_name(r)
        if n != name:
            return True
        if _project_name(r) != proj:
            return False
    return True


C_NORM = C_DIM = C_RED = C_AMBER = C_GREEN = C_BLUE = C_SEL = C_VIOLET = 1
_tone = None


def _bind():
    global C_NORM, C_DIM, C_RED, C_AMBER, C_GREEN, C_BLUE, C_SEL, C_VIOLET, _tone
    from . import tui as T
    C_NORM, C_DIM, C_RED = T.C_NORM, T.C_DIM, T.C_RED
    C_AMBER, C_GREEN, C_BLUE = T.C_AMBER, T.C_GREEN, T.C_BLUE
    C_SEL, C_VIOLET = T.C_SEL, T.C_VIOLET
    _tone = T._tone

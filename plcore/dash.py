"""The dashboard: everything about this machine on one screen.

The other views each answer one question. This one is the cockpit: the machine,
what it exposes, who is working on it, what is listening, what the selected
service actually is, and what has happened lately, all at once, so a single
screenshot tells the whole story.

`Tab` walks the sections. `j` and `k` move inside whichever one has focus.

The same rule as everywhere else applies to every number here: it is a
measurement or it is marked as unknown. "12 listening" is counted; "2 need
attention" is scored from reasons the detail pane will list; "unknown origin"
is a count of services that were already running before portlist first looked,
and it is shown precisely so that they are not quietly attributed to whatever
owns the port now.
"""
import math
import time

from . import activity as act_mod, history, ledger

SECTIONS = ("listening", "activity")     # what Tab walks; cards are not focusable

DOT = {"active": "◉", "idle": "○", "running": "●", "unknown": "⚠"}


def _risk_mark(row, frame):
    """A diamond for critical, and it pulses. Everything else stays put."""
    band = (row.get("risk_band") or "").lower()
    if band == "critical":
        return "◆" if (frame // 4) % 2 else "◇"
    return " "


def _short_starter(name):
    """"a Claude Code session" -> "Claude Code". The article and the word
    "session" cost eleven columns and carry nothing."""
    name = str(name or "unattributed")
    for article in ("a ", "an ", "the "):
        if name.lower().startswith(article):
            name = name[len(article):]
            break
    if name.lower().endswith(" session"):
        name = name[:-len(" session")]
    return name


# A ring of twelve segments, hand-placed rather than trigonometric: rounding a
# small ellipse drops several segments onto the same cell and the gauge comes
# out lopsided. Each segment is a twelfth, about 8%, which is as fine as a
# terminal cell can honestly claim. The number in the middle is the reading.
RING = [(-2, 0), (-2, 3), (-1, 5), (0, 6), (1, 5), (2, 3),
        (2, 0), (2, -3), (1, -5), (0, -6), (-1, -5), (-2, -3)]
DIAL_W = 16          # 13 for the ring, 3 so two dials never merge


def _dial(t, y, x, label, pct, frame, key, glow=False):
    """An animated ring gauge. -> the width it used.

    The ring eases toward the reading, so a change sweeps round rather than
    teleporting, and the leading segment pulses. An unmeasured value draws an
    empty ring and says so rather than resting at zero.
    """
    cy, cx = y + 2, x + 6
    shown = t.ease("dial." + key, pct)
    lit = 0 if shown is None else int(round(len(RING) * max(0.0, min(100.0, shown)) / 100.0))
    tone = (C_DIM if pct is None else
            C_RED if pct >= 90 else C_AMBER if pct >= 75 else
            (C_VIOLET if glow else C_GREEN))
    for i, (dy, dx) in enumerate(RING):
        yy, xx = cy + dy, cx + dx
        if pct is None:
            t.put(yy, xx, "\u00b7", C_DIM)
        elif i < lit:
            edge = (i == lit - 1) and (frame // 3) % 2 == 0
            t.put(yy, xx, "\u25c9" if edge else "\u25cf", tone, True)
        else:
            t.put(yy, xx, "\u00b7", C_DIM)
    text = "-" if pct is None else "%d%%" % round(pct)
    t.put(cy, cx - len(text) // 2, text, C_NORM if pct is not None else C_DIM, True)
    t.put(cy + 1, cx - len(label) // 2, label, C_DIM)
    return DIAL_W


def _state(row):
    from .vibe import state_of
    return state_of(row)


def draw(t, h, w):
    """t is the Tui. Draws rows 3..h-2; the header and tabs are already up."""
    if _tone is None:
        _bind()
    rows = t.visible()
    y = 3

    y = _cards(t, y, h, w)
    if y >= h - 4:
        return

    # How much room the table gets depends on whether the split pane fits.
    # 13 rows is enough for a compact pane now that the risk breakdown is
    # anchored: a short pane beats no pane, because the pane is where the
    # score stops being an assertion.
    split = h - y >= 13 and w >= 70
    table_h = (h - y - 3) if not split else max(4, (h - y - 3) // 2)
    y = _listening(t, y, table_h, w, rows)

    if split and y < h - 6:
        _split(t, y, h - 2, w, rows)
    _status(t, h - 2, w, rows)


# ------------------------------------------------------------------- cards
def _cards(t, y, h, w):
    d = t.sysinfo or {}
    cpu = d.get("cpu") or {}
    mem = d.get("memory") or {}
    disks = d.get("disks") or []
    s = t.summary or {}
    groups = [g for g in (t.groups or []) if g.get("count")]
    cont = t.containers or {}

    readings = [("CPU", cpu.get("load_pct")), ("RAM", mem.get("pct")),
                ("DISK", (disks[0].get("pct") if disks else None))]
    machine = []
    bar = 10
    for label, pct in readings:
        machine.append((label, pct, "meter"))
    load = cpu.get("load") or []
    machine.append(("LOAD", " ".join("%.2f" % v for v in load[:3]) if load else "-", "text"))

    unknown = sum(1 for r in t.rows
                  if not r.get("quiet") and not (r.get("origin") or {}).get("observed"))
    exposure = [("LISTENING", s.get("shown", 0), "text"),
                ("EXPOSED", s.get("exposed", 0), "warn" if s.get("exposed") else "text"),
                ("NEEDS WORK", (s.get("critical", 0) + s.get("high", 0)),
                 "bad" if (s.get("critical", 0) + s.get("high", 0)) else "text"),
                ("UNKNOWN ORIGIN", unknown, "dim")]

    agents = []
    for g in groups[:4]:
        agents.append((_short_starter(g.get("name")), g.get("count", 0),
                       "text" if g.get("alive") else "dim"))
    if not agents:
        agents = [("nothing yet", "", "dim")]

    if cont.get("reachable"):
        boxes = cont.get("containers") or []
        projects = {c.get("project") for c in boxes if c.get("project")}
        ports = sum(len(c.get("ports") or []) for c in boxes)
        containers = [("RUNNING", len(boxes), "text"),
                      ("COMPOSE", len(projects), "text"),
                      ("HOST PORTS", ports, "text"),
                      ("ENGINE", cont.get("engine") or "-", "text")]
    else:
        # Not the same thing as zero containers, and it must never read as zero.
        # "The engine did not answer" is not "there are no containers", and the
        # card has to say which one it means.
        containers = [("ENGINE", (cont.get("engine") or "none found") if cont else "none found",
                       "dim"),
                      ("STATE", "no answer" if cont.get("engine") else "-", "dim"),
                      ("COUNT", "unknown", "dim"),
                      ("", "not zero", "dim")]

    cards = [("MACHINE", machine), ("EXPOSURE", exposure),
             ("AGENTS", agents), ("CONTAINERS", containers)]

    # Wide enough for dials: three gauges in place of the machine card, and the
    # other three cards beside them.
    if w >= 118:
        t.put(y, 2, "MACHINE", C_TITLE, True)
        x = 2
        for label, pct in readings:
            x += _dial(t, y + 1, x, label, pct, t.frame, label.lower(),
                       glow=(label == "RAM"))
        if load:
            # The ring spans y+1 through y+5, so LOAD goes below all of it.
            # It used to be drawn at y+5, straight through the bottom segments.
            t.put(y + 6, 2, "LOAD  " + " ".join("%.2f" % v for v in load[:3]), C_DIM)

        rest = [c for c in cards[1:]]
        cw = (w - x - 4) // len(rest)
        for i, (title, items) in enumerate(rest):
            bx = x + 2 + i * cw
            t.put(y, bx, title, C_TITLE, True)
            for j, (label, value, kind) in enumerate(items[:4]):
                tone = {"warn": C_AMBER, "bad": C_RED, "dim": C_DIM}.get(kind, C_NORM)
                t.put(y + 1 + j, bx, str(label)[:14], C_DIM)
                t.put(y + 1 + j, bx + 15, str(value)[:max(0, cw - 17)], tone,
                      kind in ("warn", "bad"))
        return y + 8

    # Four cards need about 31 columns each before their values collide with
    # the next card. Below that, two, then one.
    per = 4 if w >= 130 else 2 if w >= 66 else 1
    cw = (w - 2) // per
    rows_of = [cards[i:i + per] for i in range(0, len(cards), per)]
    for band in rows_of:
        if y + 5 > h - 4:
            break
        for i, (title, items) in enumerate(band):
            x = 2 + i * cw
            t.put(y, x, title, C_TITLE, True)
            for j, item in enumerate(items[:4]):
                label, value, kind = item
                yy = y + 1 + j
                t.put(yy, x, label[:14], C_DIM)
                if kind == "meter":
                    if value is None:
                        t.put(yy, x + 15, "not measured", C_DIM)
                    else:
                        g = t.g
                        fill = int(round(bar * max(0.0, min(100.0, value)) / 100.0))
                        tone = C_RED if value >= 90 else C_AMBER if value >= 75 else C_GREEN
                        t.put(yy, x + 15, g.full * fill, tone, True)
                        t.put(yy, x + 15 + fill, g.empty * (bar - fill), C_DIM)
                        t.put(yy, x + 16 + bar, "%3.0f%%" % value, C_NORM)
                else:
                    tone = {"warn": C_AMBER, "bad": C_RED, "dim": C_DIM}.get(kind, C_NORM)
                    t.put(yy, x + 15, str(value)[:max(0, cw - 17)], tone,
                          kind in ("warn", "bad"))
        y += 6
    return y


# --------------------------------------------------------------- listening
def _listening(t, y, height, w, rows):
    focus = t.section == 0
    t.put(y, 2, "LISTENING", C_TITLE if not focus else C_SEL, True)
    t.put(y, 13, "%d service%s" % (len(rows), "" if len(rows) == 1 else "s"), C_DIM)
    # One character that moves, so a screen left open reads as live rather than
    # frozen. It marks time; it does not claim a reading.
    t.put(y, 26, " .oOo"[(t.frame // 4) % 5] if t.anim else "o", C_GREEN, True)
    t.put(y, 28, "LIVE", C_DIM)
    if focus:
        t.put(y, w - 24, "h/l pane   tab view", C_DIM)
    y += 1

    wide = w >= 96
    cols = [(4, "PORT"), (12, "SERVICE"), (34, "PROJECT")]
    if wide:
        cols += [(52, "STARTED BY"), (72, "REACH"), (88, "RISK")]
    else:
        cols += [(52, "REACH"), (66, "RISK")]
    for x, label in cols:
        t.put(y, x, label, C_DIM, True)
    y += 1

    body = max(1, height - 2)
    idx = next((i for i, r in enumerate(rows) if r["id"] == t.sel_id), 0)
    if idx < t.top:
        t.top = idx
    if idx >= t.top + body:
        t.top = idx - body + 1
    t.top = max(0, min(t.top, max(0, len(rows) - body)))

    for i, r in enumerate(rows[t.top:t.top + body]):
        yy = y + i
        picked = r["id"] == t.sel_id
        if picked:
            t.put(yy, 1, " " * (w - 2), C_SEL)
            t.put(yy, 0, "\u25b8" if (t.frame // 4) % 2 else " ", C_GREEN, True)
        st = _state(r)
        dot = DOT[st]
        if st == "active":
            dot = "◉●"[(t.frame // 4) % 2]
        tone = C_SEL if picked else _tone(r)
        t.put(yy, 2, dot, C_SEL if picked else
              (C_GREEN if st == "active" else C_DIM if st == "idle" else C_NORM))
        t.put(yy, 4, ":%-6s" % r.get("port"), tone)
        t.put(yy, 12, (r.get("service") or "?")[:20], C_SEL if picked else C_NORM)
        proj = (r.get("project") or {}).get("name") or r.get("dir_short") or "-"
        t.put(yy, 34, str(proj)[:16], C_SEL if picked else C_DIM)
        if wide:
            who = _short_starter((r.get("starter") or {}).get("name") or "unattributed")
            t.put(yy, 52, who[:19], C_SEL if picked else C_DIM)
        rx = 72 if wide else 52
        reach = (r.get("exposure") or {}).get("label") or "?"
        t.put(yy, rx, reach[:15], C_SEL if picked else _tone(r))
        t.put(yy, rx + 14, _risk_mark(r, t.frame), C_SEL if picked else C_RED, True)
        t.put(yy, rx + 16, ("%d %s" % (round(r.get("risk", 0)),
                                       (r.get("risk_band") or "")[:8])),
              C_SEL if picked else _tone(r))
        # A badge because it really started listening while you were watching.
        if r["id"] in t.arrived and rx + 28 < w:
            t.put(yy, rx + 28, "NEW" if (t.frame // 4) % 2 else "•  ", C_GREEN, True)
    if t.departed and y + body < len(rows) + y + body:
        gone = len(t.departed)
        t.put(y + body, 2, "· %d service%s stopped listening just now"
              % (gone, "" if gone == 1 else "s"), C_AMBER)
    return y + body


# ------------------------------------------------------- selected + activity
def _split(t, y, bottom, w, rows):
    left = int(w * 0.58)
    for yy in range(y, bottom):
        t.put(yy, left, "│", C_DIM)
    _selected(t, y, bottom, left - 2, rows)
    _activity(t, y, bottom, left + 2, w - left - 3)


def _selected(t, y, bottom, w, rows):
    t.put(y, 2, "SELECTED SERVICE", C_TITLE, True)
    r = next((x for x in rows if x["id"] == t.sel_id), rows[0] if rows else None)
    if not r:
        t.put(y + 2, 2, "nothing is listening", C_DIM)
        return
    y += 2
    if y + 1 >= bottom:
        return
    t.put(y, 2, ("%s :%s" % ((r.get("service") or "?"), r.get("port")))[:w], C_NORM, True)
    t.put(y + 1, 2, str(r.get("dir_short") or r.get("dir") or "-")[:w], C_DIM)
    y += 3
    exp = r.get("exposure") or {}

    # Work out where the risk block goes before spending rows on anything else.
    # A pane that lists the PID but not the reasons behind "71 High" has kept
    # the wrong half.
    reasons = r.get("reasons") or []
    shown = min(len(reasons), 5) or 1
    risk_y = max(y, bottom - shown - 1)
    stop = max(y, risk_y - 1)

    def field(label, value, tone=C_NORM):
        # Every line in this pane is bounded. It used to run past the bottom on
        # a 30-row terminal and print itself over the status bar.
        nonlocal y
        if y >= stop:
            return
        t.put(y, 2, "%-10s" % label, C_DIM)
        t.put(y, 13, str(value)[:max(0, w - 13)], tone)
        y += 1

    field("REACH", exp.get("label") or "?", _tone(r))
    field("PID", "%s   %s" % (r.get("pid") if r.get("pid") is not None else "another user",
                              r.get("cmd") or ""))
    field("LAST USED", act_mod.phrase(r.get("activity") or {}))
    y += 1

    # The breakdown is the point of this pane: a score with its reasons is
    # auditable, a score on its own is just an assertion. So it gets its space
    # first, anchored to the bottom, and ORIGIN takes what is left above it.
    if risk_y >= bottom:            # nothing fits; the detail pane still has it
        return

    o = r.get("origin") or {}
    room = risk_y - y - 1
    if room >= 2:
        t.put(y, 2, "ORIGIN", C_TITLE, True)
        t.put(y + 1, 4, ledger.phrase(o)[:w - 4],
              C_AMBER if (o.get("recorded") and not o.get("carries_context")) else C_NORM)
        if not o.get("observed") and room >= 3:
            t.put(y + 2, 4, "already running when portlist first looked", C_DIM)

    y = risk_y
    t.put(y, 2, "RISK", C_TITLE, True)
    t.put(y, 8, "%d / 100   %s" % (round(r.get("risk", 0)), r.get("risk_band") or ""),
          _tone(r), True)
    y += 1
    for reason in reasons[:shown]:
        if y >= bottom:
            break
        t.put(y, 4, "+%-4d" % reason.get("points", 0), C_DIM)
        t.put(y, 10, str(reason.get("label") or "")[:max(0, w - 10)], C_NORM)
        y += 1
    if not reasons:
        t.put(y, 4, "nothing scored against it", C_DIM)
    elif len(reasons) > shown:
        t.put(y, 4, "and %d more, in the detail pane" % (len(reasons) - shown), C_DIM)


def _activity(t, y, bottom, x, w):
    focus = t.section == 1
    t.put(y, x, "ACTIVITY", C_SEL if focus else C_TITLE, True)
    if focus:
        t.put(y, x + 10, "j/k scrolls", C_DIM)
    y += 2
    try:
        events = history.recent(limit=60)
    except Exception:
        events = []
    room = max(1, (bottom - y) - 8)
    if not events:
        t.put(y, x, "nothing has changed since portlist", C_DIM)
        t.put(y + 1, x, "started watching", C_DIM)
        y += 3
    else:
        t.act_top = max(0, min(getattr(t, "act_top", 0), max(0, len(events) - room)))
        for e in events[t.act_top:t.act_top + room]:
            if y >= bottom - 7:
                break
            fresh = (time.time() - (e.get("ts") or 0)) < 60
            newest = e is events[t.act_top]
            stamp = time.strftime("%H:%M:%S", time.localtime(e.get("ts") or 0))
            mark = "◉●"[(t.frame // 4) % 2] if fresh else "·"
            t.put(y, x, stamp, C_DIM)
            t.put(y, x + 9, mark, C_GREEN if fresh else C_DIM, fresh)
            if newest and fresh:
                t.put(y, x - 1, "\u25b8" if (t.frame // 3) % 2 else " ", C_GREEN, True)
            t.put(y, x + 11, str(e.get("text") or "")[:max(0, w - 11)],
                  C_NORM if fresh else C_DIM)
            y += 1
        y += 1

    if bottom - y >= 4:
        held = max(len(t.hist["cpu"]), len(t.hist["mem"]))
        width = max(10, min(w, held))
        t.put(y, x, "CPU", C_DIM)
        t.spark(y + 1, x, width, t.hist["cpu"], C_GREEN, 100.0)
        t.put(y + 2, x, "MEMORY", C_DIM)
        t.spark(y + 3, x, width, t.hist["mem"], C_VIOLET, 100.0)


def _status(t, y, w, rows):
    s = t.summary or {}
    unknown = sum(1 for r in rows if not (r.get("origin") or {}).get("observed"))
    agents = len([g for g in (t.groups or []) if g.get("count")])
    fw = ((t.sysinfo or {}).get("security") or {}).get("firewall") or {}
    bits = [("●", "%d exposed" % s.get("exposed", 0),
             C_AMBER if s.get("exposed") else C_DIM),
            ("◆", "%d need attention" % (s.get("critical", 0) + s.get("high", 0)),
             C_RED if (s.get("critical", 0) + s.get("high", 0)) else C_DIM),
            ("⚠", "%d unknown origin" % unknown, C_DIM),
            ("◉", "%d agents" % agents, C_BLUE),
            ("", "firewall %s" % ("on" if fw.get("enabled") else
                                  "off" if fw.get("enabled") is False else "unknown"),
             C_GREEN if fw.get("enabled") else C_AMBER)]
    x = 2
    for mark, text, tone in bits:
        if x + len(text) + 4 > w:
            break
        if mark:
            t.put(y, x, mark, tone, True)
            x += 2
        t.put(y, x, text, C_DIM)
        x += len(text) + 4


# tui imports this module, so its colour constants cannot be imported at module
# load time. They are bound on the first draw instead, when tui is complete.
C_NORM = C_DIM = C_RED = C_AMBER = C_GREEN = C_BLUE = C_SEL = C_VIOLET = 1
C_TITLE = 1
_tone = None


def _bind():
    global C_NORM, C_DIM, C_RED, C_AMBER, C_GREEN, C_BLUE, C_SEL, C_VIOLET
    global C_TITLE, _tone
    from . import tui as T
    C_NORM, C_DIM, C_RED = T.C_NORM, T.C_DIM, T.C_RED
    C_AMBER, C_GREEN, C_BLUE = T.C_AMBER, T.C_GREEN, T.C_BLUE
    C_SEL, C_VIOLET = T.C_SEL, T.C_VIOLET
    C_TITLE = T.C_VIOLET
    _tone = T._tone

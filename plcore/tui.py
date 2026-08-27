"""A full-screen terminal view of the machine.

The dashboard is a browser page and the CLI is one answer per command. This is
the third shape: a screen you leave open in a tmux pane while you work, that
redraws itself and stays out of the way.

`curses` is in the standard library, so this costs the project nothing. It is not
available on Windows, and that is reported rather than raised.

This file is read by another project that renders the same model, so keep it
free of anything that assumes a web server exists.

Two rules carried over from every other surface, because they matter more here
than anywhere: a screen redrawing every few seconds must never move under the
cursor, so the selection follows the *service*, not the row index; and it must
never dress a guess as a fact, so an unattributed service says so rather than
being left blank.
"""
import curses
import locale
import subprocess
import sys
import time
import webbrowser

from . import (activity, agents as agents_mod, collect, dash as dash_mod,
               graphview, ledger, scan, sessions as sess_mod, vibe as vibe_mod)

REFRESH = 5.0
ANIM = 0.12          # frame interval while something on screen is moving
HIST = 120           # samples kept for the sparklines, one per animation tick


def _utf8():
    """Box glyphs are only worth it if the terminal can actually print them.

    A mojibake frame is worse than an ASCII one, so this asks rather than
    assumes, and every glyph below has an ASCII twin.
    """
    try:
        enc = (locale.getpreferredencoding(False) or "").lower()
    except Exception:
        enc = ""
    return "utf" in enc and "8" in enc


class Glyphs:
    def __init__(self, unicode_ok):
        if unicode_ok:
            self.tl, self.tr, self.bl, self.br = "\u250c", "\u2510", "\u2514", "\u2518"
            self.h, self.v = "\u2500", "\u2502"
            self.full, self.empty = "\u2588", "\u2591"
            self.spark = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
            self.dot = "\u25cf"
        else:
            self.tl = self.tr = self.bl = self.br = "+"
            self.h, self.v = "-", "|"
            self.full, self.empty = "#", "."
            self.spark = " .:-=+*#%"
            self.dot = "*"


def _size(n):
    """Bytes as one number a human reads at a glance."""
    if not n:
        return "-"
    for unit, step in (("T", 1 << 40), ("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10)):
        if n >= step:
            v = n / float(step)
            return ("%.1f%s" % (v, unit)) if v < 10 else ("%.0f%s" % (v, unit))
    return "%dB" % n


def _dur(seconds):
    """Uptime, largest two units. 3299686 -> '38d 4h'."""
    if not seconds:
        return "-"
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    if d:
        return "%dd %dh" % (d, h)
    if h:
        return "%dh %dm" % (h, m)
    return "%dm" % m

# Art goes where there is room for it: the splash while the first scan runs, and
# the empty state. Never over the table - a decoration that covers a column head
# is not decoration, it is a bug.
SPLASH = [
    r"  ___    __    ___   ____         _   ___   ____ ",
    r" | _ \  /  \  | _ \ |_  _| | |   | | / __| |_  _|",
    r" |  _/ | () | |   /   | |  | |_  | | \__ \   | | ",
    r" |_|    \__/  |_|_\   |_|  |___| |_| |___/   |_| ",
    r"",
    r"      every port, and where it came from          ",
]
# A small plate for an empty view. Same font as the splash, three lines.
EMPTY = [
    r"   .---.   ",
    r"  ( o o )  ",
    r"   '---'   ",
]

# (name, key, what it keeps). A view that groups rather than filters says so with
# a None filter and is built by its own method.
VIEW_KEYS = {}          # filled in below: the key you press -> the view index

VIEWS = [
    # The dashboard is first and answers to 0, so that every other view keeps
    # the number it has always had.
    ("Dashboard", "0", None),
    ("Services", "1", lambda rows: rows),
    ("Exposed", "2", lambda rows: [r for r in rows
                                   if (r.get("exposure") or {}).get("level") != "loopback"]),
    ("Attention", "3", lambda rows: [r for r in rows
                                     if r.get("risk_band") in ("Critical", "High", "Medium")]),
    ("Leftovers", "4", lambda rows: [r for r in rows
                                     if (r.get("leftover") or {}).get("likely")]),
    ("Agents", "5", None),
    ("Containers", "6", None),
    ("Sessions", "7", None),
    ("System", "8", None),
    ("Graph", "9", None),
]

for _i, (_label, _key, _filter) in enumerate(VIEWS):
    VIEW_KEYS[_key] = _i

C_NORM, C_DIM, C_RED, C_AMBER, C_GREEN, C_BLUE, C_HEAD, C_SEL, C_VIOLET = range(1, 10)


def _colours():
    if not curses.has_colors():
        return False
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    curses.init_pair(C_NORM, curses.COLOR_WHITE, bg)
    curses.init_pair(C_DIM, curses.COLOR_BLUE, bg)
    curses.init_pair(C_RED, curses.COLOR_RED, bg)
    curses.init_pair(C_AMBER, curses.COLOR_YELLOW, bg)
    curses.init_pair(C_GREEN, curses.COLOR_GREEN, bg)
    curses.init_pair(C_BLUE, curses.COLOR_CYAN, bg)
    curses.init_pair(C_HEAD, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(C_SEL, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_VIOLET, curses.COLOR_MAGENTA, bg)
    return True


def _tone(row):
    band = row.get("risk_band")
    if band in ("Critical", "High"):
        return C_RED
    if band == "Medium":
        return C_AMBER
    if (row.get("exposure") or {}).get("level") != "loopback":
        return C_AMBER
    return C_GREEN


def _ago(seconds):
    if seconds is None:
        return ""
    s = int(seconds)
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)


def _origin_cell(row):
    """Who started it, in about twenty characters, and never a blank when the
    answer is "we do not know"."""
    o = row.get("origin") or {}
    live, rec = o.get("live"), o.get("recorded")
    if live and o.get("carries_context"):
        name, mark = live.get("name"), ""
    elif o.get("live_is_container") and live:
        name, mark = live.get("name"), ""
    elif rec and rec.get("name"):
        same = (live or {}).get("kind") == rec.get("kind")
        name, mark = rec.get("name"), "" if same else "~"
    elif live and live.get("name"):
        name, mark = live.get("name"), ""
    else:
        return "unknown", C_DIM
    name = str(name).replace("a ", "", 1).replace(" session", "")
    when = _ago(time.time() - o["started_at"]) if o.get("started_at") else ""
    text = "%s%s%s" % (mark, name[:15], (" " + when) if when else "")
    ai = (live or rec or {}).get("ai")
    return text, (C_VIOLET if ai else C_DIM)


class Tui:
    def __init__(self, stdscr):
        self.s = stdscr
        self.colour = _colours()
        self.view = 0
        self.sel_id = None
        self.top = 0
        self.rows = []
        self.host = {}
        self.summary = {}
        self.groups = []
        self.last = 0.0
        self.status = ""
        self.detail = False
        self.query = ""
        self.typing = False
        self.groups = []
        self.containers = None
        self.overlay = None      # ("title", [lines]) drawn over the list
        self.sessions = None
        self.sess_id = None
        self.sysinfo = None
        self.g = Glyphs(_utf8())
        # Animation is a redraw budget, not a decoration budget: it only runs
        # while a moving view is on screen, and `a` turns it off for good.
        self.anim = True
        self.frame = 0
        self.hist = {"cpu": [], "mem": [], "net": []}
        self.eased = {}
        self.sampled = 0.0
        self.vibe = None            # the ambient screen, when it is up
        self.last_key = time.time()
        self.section = 0            # which dashboard pane has focus
        self.act_top = 0            # scroll inside the dashboard activity pane
        # What changed between scans, shared by every screen that shows it.
        # id -> when. The first scan fills `known` and marks nothing: everything
        # is new to the program the moment it starts and none of it is new to
        # the machine.
        self.known = set()
        self.arrived = {}
        self.departed = {}

    # ------------------------------------------------------------- painting
    def attr(self, pair, bold=False):
        a = curses.color_pair(pair) if self.colour else 0
        return a | (curses.A_BOLD if bold else 0)

    def put(self, y, x, text, pair=C_NORM, bold=False):
        h, w = self.s.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        try:
            self.s.addnstr(y, x, text, max(0, w - x - 1), self.attr(pair, bold))
        except curses.error:
            pass

    # Widths that add up, in the order they are given up as the window narrows.
    LAYOUT = [("PORT", 8, 0), ("SERVICE", 24, 0), ("REACHABLE", 15, 3),
              ("RISK", 9, 2), ("PROJECT", 18, 1), ("STARTED BY", 22, 4)]
    ORDER = ["PORT", "SERVICE", "PROJECT", "REACHABLE", "RISK", "STARTED BY"]

    def columns(self, w):
        """-> [(x, width, label)] for this terminal width.

        Port and service are never dropped: a row without them is not a row.
        Everything else goes in reverse order of how much it earns its space.
        """
        keep = {name for name, _wd, _drop in self.LAYOUT}
        budget = w - 2
        while True:
            total = sum(wd for name, wd, _ in self.LAYOUT if name in keep)
            if total <= budget or len(keep) <= 2:
                break
            # drop the least valuable column still present
            worst = max((d, n) for n, _wd, d in self.LAYOUT if n in keep and d)[1]
            keep.discard(worst)
        out, x = [], 1
        for name in self.ORDER:
            if name not in keep:
                continue
            wd = dict((n, wid) for n, wid, _ in self.LAYOUT)[name]
            out.append((x, wd - 1, name))
            x += wd
        return out

    # ------------------------------------------------------- moving parts
    def sample(self):
        """One point per tick for the sparklines.

        `scan.system_info()` is cached and refreshes on its own thread, so this
        costs a dict lookup per frame, not a subprocess.
        """
        now = time.time()
        if now - self.sampled < 0.9:
            return
        self.sampled = now
        try:
            d = scan.system_info()
        except Exception:
            return
        self.sysinfo = d
        cpu = ((d.get("cpu") or {}).get("load_pct"))
        mem = ((d.get("memory") or {}).get("pct"))
        net = (d.get("network") or {}).get("rx_rate")
        for key, value in (("cpu", cpu), ("mem", mem), ("net", net)):
            # None is a sample too: "not measured yet" must not draw as zero.
            self.hist[key].append(value)
            del self.hist[key][:-HIST]

    def ease(self, key, target):
        """Bars sweep to a new value instead of teleporting. Off = exact."""
        if target is None:
            return None
        if not self.anim:
            self.eased[key] = target
            return target
        cur = self.eased.get(key)
        if cur is None or abs(cur - target) < 0.35:
            self.eased[key] = target
            return target
        self.eased[key] = cur + (target - cur) * 0.28
        return self.eased[key]

    def box(self, y, x, h, w, title, pair=C_DIM, title_pair=None):
        """A frame with its title inset in the top rule. -> inner (y, x, w)."""
        g = self.g
        if w < 4 or h < 2:
            return y, x, max(0, w - 2)
        self.put(y, x, g.tl + g.h * (w - 2) + g.tr, pair)
        for i in range(1, h - 1):
            self.put(y + i, x, g.v, pair)
            self.put(y + i, x + w - 1, g.v, pair)
        self.put(y + h - 1, x, g.bl + g.h * (w - 2) + g.br, pair)
        if title:
            label = " %s " % title[:max(0, w - 6)]
            self.put(y, x + 2, label, title_pair or C_BLUE, True)
        return y + 1, x + 2, w - 4

    def meter(self, y, x, width, pct, pair=None):
        """[####....] sized to `width`, coloured by how alarming the value is."""
        g = self.g
        if pct is None:
            self.put(y, x, "-" * min(width, 3) + " not measured", C_DIM)
            return
        pct = max(0.0, min(100.0, float(pct)))
        fill = int(round(width * pct / 100.0))
        tone = pair or (C_RED if pct >= 90 else C_AMBER if pct >= 75 else C_GREEN)
        self.put(y, x, g.full * fill, tone, True)
        self.put(y, x + fill, g.empty * (width - fill), C_DIM)

    def spark(self, y, x, width, values, pair=C_BLUE, scale=None):
        """A sparkline that leaves gaps where nothing was measured."""
        g = self.g
        vals = values[-width:]
        if not vals:
            return
        real = [v for v in vals if v is not None]
        top = scale or (max(real) if real else 0) or 1.0
        out = []
        for v in vals:
            if v is None:
                out.append(" ")
                continue
            step = int(round((len(g.spark) - 1) * min(1.0, v / float(top))))
            out.append(g.spark[max(0, step)])
        self.put(y, x + max(0, width - len(out)), "".join(out), pair, True)

    def refresh_data(self, force=False):
        self.rows, self.host = scan.scan(force=force)
        live = [r for r in self.rows if not r.get("quiet")]
        self.summary = scan.summary(self.rows, self.host)
        try:
            procs = collect.processes()
        except Exception:
            procs = None
        try:
            self.groups = agents_mod.groups(live, procs=procs, stdio=scan.stdio_mcp())
        except Exception:
            self.groups = []
        try:
            from . import containers as cmod
            self.containers = cmod.inventory()
        except Exception:
            self.containers = None
        # Reading transcripts is head+tail only, so this is cheap enough to do
        # on the same beat as everything else.
        try:
            self.sessions = sess_mod.listing(limit=30)
        except Exception:
            self.sessions = None
        try:
            self.sysinfo = scan.system_info()
        except Exception:
            self.sysinfo = None
        self.sampled = 0.0
        self.sample()
        self.note_changes()
        self.last = time.time()

    CHANGE_FOR = 20.0        # seconds an arrival or a departure stays marked

    def note_changes(self):
        """Diff this scan against the last. Real events, never decoration."""
        now = time.time()
        live = {r["id"] for r in self.rows if not r.get("quiet")}
        first = not self.known
        if first:
            self.known = live
            return
        for sid in live - self.known:
            self.arrived[sid] = now
            self.departed.pop(sid, None)
        for sid in self.known - live:
            self.departed[sid] = now
            self.arrived.pop(sid, None)
        self.known = live
        for store in (self.arrived, self.departed):
            for sid, when in list(store.items()):
                if now - when > self.CHANGE_FOR:
                    del store[sid]

    def live_rows(self):
        live = [r for r in self.rows if not r.get("quiet")]
        if not self.query:
            return live
        q = self.query.lower()
        return [r for r in live if q in " ".join(str(x) for x in (
            r.get("port"), r.get("service"), r.get("cmd"),
            (r.get("project") or {}).get("name"), r.get("dir_short"),
            ((r.get("starter") or {}).get("name")))).lower()]

    def items(self):
        """-> a flat list of ("row", row) and ("head", text, tone).

        Grouped views and flat views draw through the same loop, so the cursor,
        the scrolling and the detail pane do not each need two versions.
        """
        live = self.live_rows()
        name = VIEWS[self.view][0]
        keep = VIEWS[self.view][2]
        if name == "Dashboard":
            # The dashboard's table is every listening service, in port order,
            # so the cursor, the search and the detail pane all still work here.
            return [("row", r) for r in sorted(live, key=lambda r: r["port"])]
        if name == "Graph":
            # Graph order, so j and k walk the picture rather than the ports.
            return [("row", r) for r in graphview.order(live)]
        if keep is not None:
            return [("row", r) for r in sorted(keep(live), key=lambda r: r["port"])]
        if name == "Agents":
            out = []
            for g in self.groups:
                if not g["services"] and not g["mcp"]:
                    continue
                state = ("still running" if g["alive"]
                         else "session has exited" if g["alive"] is False
                         else "liveness unknown")
                out.append(("head", "%s  -  %s  -  %d service%s%s"
                            % (g["name"], state, g["count"],
                               "" if g["count"] == 1 else "s",
                               "" if not g["mcp_count"] else
                               ", %d stdio MCP" % g["mcp_count"]),
                            C_VIOLET if g["ai"] else C_DIM))
                # What this starter is on record for, which is a different
                # question from what it still has listening: a session that
                # exited an hour ago still has a history, and the services it
                # started may have gone with it.
                past = ledger.by_starter(g.get("kind"))
                if past:
                    ports_now = {svc["port"] for svc in g["services"]}
                    shown = 0
                    for rec in past:
                        if shown >= 3:
                            break
                        port = rec.get("port")
                        if port in ports_now:
                            continue          # it is in the list underneath
                        ago = _ago(time.time() - (rec.get("ts") or 0))
                        out.append(("head", "    started :%-6s %-18s %s%s ago, since gone"
                                    % (port, (rec.get("service") or "?")[:18],
                                       (rec.get("project") or ""), " " + ago), C_DIM))
                        shown += 1
                    first = past[-1].get("ts")
                    last = past[0].get("ts")
                    if first:
                        out.append(("head", "    %d launch%s on record, first %s ago, most recent %s ago"
                                    % (len(past), "" if len(past) == 1 else "es",
                                       _ago(time.time() - first),
                                       _ago(time.time() - last)), C_DIM))

                by_id = {r["id"]: r for r in live}
                for svc in sorted(g["services"], key=lambda x: x["port"]):
                    r = by_id.get(svc["id"])
                    if r:
                        out.append(("row", r))
            return out
        if name == "Sessions":
            out = []
            doc = self.sessions or {}
            recs = doc.get("sessions") or []
            if self.query:
                q = self.query.lower()
                recs = [r for r in recs if q in " ".join(str(x) for x in (
                    r.get("title"), r.get("project"), r.get("first_prompt"),
                    r.get("tool"))).lower()]
            procs = doc.get("processes") or []
            out.append(("head", "%d agent process%s running  -  %d transcript%s on disk"
                        % (len(procs), "" if len(procs) == 1 else "es",
                           len(recs), "" if len(recs) == 1 else "s"), C_DIM))
            # Which plan each tool is signed in under. One line, because it is
            # the answer to "which account is burning the quota" and nothing more.
            for a in (doc.get("accounts") or []):
                bits = [a.get("plan"), a.get("tier"), a.get("model")]
                bits = [b for b in bits if b]
                out.append(("head", "    %-16s %s"
                            % (a.get("name") or a.get("tool"),
                               " - ".join(bits) if bits
                               else ("signed in" if a.get("signed_in") else "not signed in")),
                            C_DIM))
            for r in recs:
                out.append(("sess", r))
            if not recs:
                out.append(("head", "  no sessions found under ~/.claude/projects "
                                    "or ~/.codex/sessions", C_DIM))
            return out
        if name == "Containers":
            out = []
            doc = self.containers or {}
            if not doc.get("engine"):
                out.append(("head", "No container engine on this machine.", C_DIM))
                return out
            if not doc.get("reachable"):
                out.append(("head", "Cannot see containers - the daemon did not "
                                    "answer. That is not the same as none.", C_AMBER))
                return out
            from . import containers as cmod
            by_port = {}
            for r in live:
                if r.get("container"):
                    by_port.setdefault(r["container"]["id"], r)
            for g in cmod.projects(doc):
                out.append(("head", "%s  -  %d of %d running"
                            % (g["project"] or "no compose project", g["running"],
                               len(g["containers"])), C_BLUE))
                for c in g["containers"]:
                    r = by_port.get(c["id"])
                    if r:
                        out.append(("row", r))
                    else:
                        ports = ", ".join(":%d" % p["host_port"] for p in c["ports"])
                        out.append(("head", "    %-24s %-22s %s %s"
                                    % (c["name"][:24], c["image"][:22], c["state"],
                                       ports), C_DIM))
            if len(out) == 0:
                out.append(("head", "%s is running and has no containers."
                            % doc["engine"], C_DIM))
            return out
        return []

    def visible(self):
        return [it[1] for it in self.items() if it[0] == "row"]

    def draw(self):
        self.s.erase()
        h, w = self.s.getmaxyx()
        if self.vibe:
            self.vibe.draw(h, w)
            self.s.refresh()
            return
        rows = self.visible()

        # header
        s = self.summary
        name = (self.host.get("hostname") or "this machine").split(".")[0]
        # No inverse bar. A solid white strip is the loudest thing a terminal
        # can draw and it was the first thing your eye hit; the name in colour
        # over the terminal's own background reads better and lets the rest of
        # the palette mean something.
        self.put(0, 1, "PORTLIST", C_VIOLET, True)

        # Clauses, dropped whole from the right. Truncating this string instead
        # gives "2 need att", which is not a shorter fact, it is a broken one.
        clauses = [name,
                   "%d listening" % s.get("shown", 0),
                   "%d off-box" % s.get("exposed", 0),
                   "%d need attention" % (s.get("critical", 0) + s.get("high", 0))]
        room = max(0, w - 24)
        headline = clauses[0][:room]
        for clause in clauses[1:]:
            if len(headline) + 2 + len(clause) > room:
                break
            headline += "  " + clause
        self.put(0, 11, headline, C_DIM)
        # The counts inside the headline carry the tone, not the whole bar.
        if s.get("exposed"):
            at = headline.find("%d off-box" % s.get("exposed", 0))
            if at >= 0:
                self.put(0, 11 + at, "%d off-box" % s["exposed"], C_AMBER)
        bad = s.get("critical", 0) + s.get("high", 0)
        if bad:
            at = headline.find("%d need attention" % bad)
            if at >= 0:
                self.put(0, 11 + at, "%d need attention" % bad, C_RED)
        clock = time.strftime("%H:%M:%S")
        self.put(0, max(12, w - len(clock) - 2), clock, C_DIM)
        # One character that moves: proof the screen is live rather than frozen,
        # which is the question you ask of a pane you left open an hour ago.
        if self.anim:
            beat = " .oOo"[(self.frame // 4) % 5]
            self.put(0, max(11, w - len(clock) - 4), beat, C_GREEN, True)
        # A hairline instead of a block: the same separation, a tenth of the ink.
        self.put(2, 0, self.g.h * max(0, w - 1), C_DIM)

        # view tabs. Eight of them do not fit an 80- or even a 110-column
        # terminal, so the counts go first and the labels shorten after that.
        # A clipped tab bar hides the view you are trying to reach.
        x = 1
        live = self.live_rows()
        counts = {}
        for i, (label, key, keep) in enumerate(VIEWS):
            if keep is not None:
                n = len(keep(live))
            elif label == "Agents":
                n = len([g for g in self.groups if g["count"] or g["mcp_count"]])
            elif label == "Sessions":
                n = len((self.sessions or {}).get("sessions") or [])
            elif label == "System":
                n = None
            else:
                doc = self.containers or {}
                n = len(doc.get("containers") or [])
            counts[label] = n

        def bar(with_counts, short):
            out = []
            for label, key, _k in VIEWS:
                name = label[:4] if short else label
                n = counts.get(label)
                out.append(" %s %s%s " % (key, name,
                                          "(%d)" % n if with_counts and n is not None else ""))
            return out

        def numbers():
            # Last resort: the keys are digits anyway, so keep the digits and
            # spell out only the view you are actually in. "Sess" and "Syst"
            # are not names, they are stubs.
            return [(" %s %s " % (key, label) if i == self.view else " %s " % key)
                    for i, (label, key, _k) in enumerate(VIEWS)]

        for opt in (bar(True, False), bar(False, False), numbers()):
            if sum(len(t) + 1 for t in opt) <= w - 2:
                tabs = opt
                break
        else:
            tabs = numbers()
        for i, text in enumerate(tabs):
            on = i == self.view
            if on:
                # The active tab is marked and underlined rather than filled in.
                # A block of solid colour behind text is hard to read and harder
                # to screenshot; a bar and a rule say the same thing quietly.
                self.put(1, x, "\u258c", C_VIOLET, True)
                self.put(1, x + 1, text.strip(), C_NORM, True)
                self.put(2, x, self.g.h * (len(text.strip()) + 1), C_VIOLET, True)
            else:
                self.put(1, x, text, C_DIM)
            x += len(text) + 1

        # Columns sized to the terminal, dropped from the right as it narrows.
        # A fixed layout at 80 columns puts the project on top of the service.
        cols = self.columns(w)          # the header and the row painter share these

        if VIEWS[self.view][0] == "Graph":
            graphview.draw(self, h, w)
            if self.overlay:
                self.draw_overlay(h, w)
            self.draw_footer(h, w)
            self.s.refresh()
            return

        if VIEWS[self.view][0] == "Dashboard":
            dash_mod.draw(self, h, w)
            if self.overlay:
                self.draw_overlay(h, w)
            self.draw_footer(h, w)
            self.s.refresh()
            return

        if VIEWS[self.view][0] == "System":
            self.draw_system(h, w)
            if self.overlay:
                self.draw_overlay(h, w)
            self.draw_footer(h, w)
            self.s.refresh()
            return

        body = h - 6 if not self.detail else (h - 6) // 2
        items = self.items()
        if VIEWS[self.view][0] == "Sessions":
            ids = [it[1].get("id") for it in items if it[0] == "sess"]
            if self.sess_id not in ids:
                self.sess_id = ids[0] if ids else None
            idx = next((i for i, it in enumerate(items)
                        if it[0] == "sess" and it[1].get("id") == self.sess_id), 0)
            if idx < self.top:
                self.top = idx
            if idx >= self.top + body:
                self.top = idx - body + 1
            self.top = max(0, min(self.top, max(0, len(items) - body)))
            self.put(3, 1, "TOOL", C_DIM, True)
            self.put(3, 10, "WHAT IT WAS ABOUT", C_DIM, True)
            self.put(3, 50, "PROJECT", C_DIM, True)
            self.put(3, 70, "CONTEXT", C_DIM, True)
            self.put(3, 79, "LAST USED", C_DIM, True)
            for i, it in enumerate(items[self.top:self.top + body]):
                y = 4 + i
                if it[0] == "head":
                    self.put(y, 1, it[1][:max(0, w - 3)], it[2], True)
                else:
                    self.draw_session(y, w, it[1])
            if self.detail:
                sel = next((it[1] for it in items
                            if it[0] == "sess" and it[1].get("id") == self.sess_id), None)
                if sel:
                    self.draw_session_detail(4 + body + 1, h, w, sel)
            if self.overlay:
                self.draw_overlay(h, w)
            self.draw_footer(h, w)
            self.s.refresh()
            return
        # The column header belongs to the table path and nowhere else. It used
        # to be drawn in the prologue, which meant every view that draws its own
        # header got this one on top: two sets of labels interleaved into
        # "PROJECTBLE  RISKCONTEXTAR". Drawing it here means a new view cannot
        # inherit that bug simply by existing, which it did three times.
        for _x, _width, _label in cols:
            self.put(3, _x, _label[:_width], C_DIM, True)

        if self.sel_id and not any(r["id"] == self.sel_id for r in rows):
            self.sel_id = rows[0]["id"] if rows else None
        if not self.sel_id and rows:
            self.sel_id = rows[0]["id"]
        # Scroll by item, select by service. A header must not be selectable and
        # a refresh must not move the cursor onto a different service.
        idx = next((i for i, it in enumerate(items)
                    if it[0] == "row" and it[1]["id"] == self.sel_id), 0)
        if idx < self.top:
            self.top = idx
        if idx >= self.top + body:
            self.top = idx - body + 1
        self.top = max(0, min(self.top, max(0, len(items) - body)))

        if not items:
            y = 6
            if h > 14:
                for i, line in enumerate(EMPTY):
                    self.put(y + i, max(2, (w - len(line)) // 2), line, C_DIM)
                y += len(EMPTY) + 1
            msg = ("Nothing matches %r." % self.query if self.query
                   else "Nothing in this view.")
            self.put(y, max(2, (w - len(msg)) // 2), msg, C_DIM)

        for i, it in enumerate(items[self.top:self.top + body]):
            y = 4 + i
            if it[0] == "head":
                self.put(y, 1, it[1][:max(0, w - 3)], it[2], True)
                continue
            if it[0] == "sess":
                self.draw_session(y, w, it[1])
                continue
            r = it[1]
            picked = r["id"] == self.sel_id
            if picked:
                self.put(y, 0, " " * (w - 1), C_SEL)
            tone = C_SEL if picked else _tone(r)
            otext, opair = _origin_cell(r)
            cell = {
                "PORT": (":%d" % r["port"], tone, True),
                "SERVICE": (r.get("service") or r.get("cmd") or "unidentified",
                            C_SEL if picked else C_NORM, False),
                "PROJECT": ((r.get("project") or {}).get("name")
                            or r.get("dir_short") or "-",
                            C_SEL if picked else C_DIM, False),
                "REACHABLE": ((r.get("exposure") or {}).get("label") or "?", tone, False),
                "RISK": ("%d %s" % (round(r.get("risk", 0)),
                                    (r.get("risk_band") or "")[:4]), tone, False),
                "STARTED BY": (otext, C_SEL if picked else opair, False),
            }
            for x, width, label in cols:
                text, pair, bold = cell[label]
                self.put(y, x, str(text)[:width], pair, bold)

        if self.detail:
            if VIEWS[self.view][0] == "Sessions":
                sel = next((it[1] for it in items
                            if it[0] == "sess" and it[1].get("id") == self.sess_id), None)
                if sel:
                    self.draw_session_detail(4 + body + 1, h, w, sel)
            else:
                sel = next((r for r in rows if r["id"] == self.sel_id), None)
                if sel:
                    self.draw_detail(4 + body + 1, h, w, [sel], 0)
        if self.overlay:
            self.draw_overlay(h, w)

        self.draw_footer(h, w)
        self.s.refresh()

    def draw_system(self, h, w):
        """This machine, in boxes: what it is, what it is doing, what it exposes.

        Laid out as a grid that collapses to one column when the terminal is
        narrow, because a two-column layout at 80 columns is two columns of
        truncation.
        """
        d = self.sysinfo or {}
        g = self.g
        if not d:
            self.put(6, 2, "reading the machine...", C_DIM)
            return
        osd = d.get("os") or {}
        cpu = d.get("cpu") or {}
        mem = d.get("memory") or {}
        disks = d.get("disks") or []
        net = d.get("network") or {}
        ports = d.get("ports") or {}
        sec = d.get("security") or {}
        wide = w >= 92
        y = 3

        # ---- machine, and the pulse beside it
        left_w = (w - 3) // 2 if wide else w - 2
        iy, ix, iw = self.box(y, 1, 6 if wide else 7, left_w, "machine",
                              C_DIM, C_VIOLET)
        self.put(iy, ix, (d.get("hostname") or "this machine").split(".")[0],
                 C_NORM, True)
        bits = [osd.get("pretty") or osd.get("name") or "?"]
        if cpu.get("model"):
            core = cpu.get("model")
            if cpu.get("performance_cores") and cpu.get("efficiency_cores"):
                core += " (%dP+%dE)" % (cpu["performance_cores"], cpu["efficiency_cores"])
            elif cpu.get("cores"):
                core += " (%d cores)" % cpu["cores"]
            bits.append(core)
        self.put(iy + 1, ix, bits[0][:iw], C_DIM)
        if len(bits) > 1:
            self.put(iy + 2, ix, bits[1][:iw], C_DIM)
        up = "up %s" % _dur(d.get("uptime"))
        procs = (d.get("processes") or {}).get("count")
        if procs:
            up += "   %s   %d processes" % (g.dot, procs)
        self.put(iy + 3, ix, up[:iw], C_BLUE)
        if not wide:
            # No room for the pulse box, but the moving part is the reason to
            # leave this view open. One compact line keeps it.
            self.put(iy + 4, ix, "cpu", C_DIM)
            self.spark(iy + 4, ix + 4, 12, self.hist["cpu"], C_GREEN, 100.0)
            self.put(iy + 4, ix + 17, "%3.0f%%" % (cpu.get("load_pct") or 0), C_NORM, True)
            self.put(iy + 4, ix + 23, "mem", C_DIM)
            self.spark(iy + 4, ix + 27, 12, self.hist["mem"], C_VIOLET, 100.0)
            self.put(iy + 4, ix + 40, "%3.0f%%" % (mem.get("pct") or 0), C_NORM, True)

        if wide:
            px = 1 + left_w + 1
            pw = w - px - 1
            iy, ix, iw = self.box(y, px, 6, pw, "pulse", C_DIM, C_VIOLET)
            rows = [("cpu", self.hist["cpu"], cpu.get("load_pct"), "%", 100.0),
                    ("mem", self.hist["mem"], mem.get("pct"), "%", 100.0),
                    ("net", self.hist["net"], net.get("rx_rate"), "B/s", None)]
            for i, (label, series, now, unit, scale) in enumerate(rows):
                self.put(iy + i, ix, label, C_DIM)
                sw = max(4, iw - 14)
                self.spark(iy + i, ix + 4, sw, series,
                           C_GREEN if label == "cpu" else
                           C_VIOLET if label == "mem" else C_BLUE, scale)
                if now is None:
                    # Two samples are needed for a rate. Say so; do not draw 0.
                    self.put(iy + i, ix + iw - 11, "no rate yet", C_DIM)
                elif unit == "%":
                    self.put(iy + i, ix + iw - 5, "%4.0f%%" % now, C_NORM, True)
                else:
                    self.put(iy + i, ix + iw - 8, "%8s" % (_size(now) + "/s"), C_NORM, True)
            self.put(iy + 3, ix, "one sample a second, %d kept" % HIST, C_DIM)
        y += 6 if wide else 7

        # ---- load: the three meters that answer "is this machine in trouble"
        rows = [("cpu", cpu.get("load_pct"),
                 "%d cores   load %s" % (cpu.get("cores") or 0,
                                         "  ".join("%.1f" % v for v in (cpu.get("load") or [])[:3]))),
                ("memory", mem.get("pct"),
                 ("%s of %s" % (_size(mem.get("used")), _size(mem.get("total"))))
                 + ("   swap %s of %s" % (_size(mem.get("swap_used")),
                                          _size(mem.get("swap_total"))) if wide else ""))]
        for dk in disks[:2]:
            rows.append(("disk %s" % (dk.get("mount") or "?"), dk.get("pct"),
                         "%s free of %s" % (_size(dk.get("free")), _size(dk.get("total")))))
        bh = len(rows) + 2
        if y + bh < h - 2:
            iy, ix, iw = self.box(y, 1, bh, w - 2, "load", C_DIM, C_VIOLET)
            bar = max(10, min(30, iw - 44))
            for i, (label, pct, note) in enumerate(rows):
                self.put(iy + i, ix, label[:9], C_NORM)
                shown = self.ease("m." + label, pct)
                self.meter(iy + i, ix + 10, bar, shown)
                if pct is not None:
                    self.put(iy + i, ix + 11 + bar, "%5.1f%%" % pct, C_NORM, True)
                self.put(iy + i, ix + 18 + bar, note[:max(0, iw - 18 - bar)], C_DIM)
            y += bh

        # ---- three small boxes: what this machine puts on the network
        if y + 6 >= h - 1:
            return
        cw = (w - 4) // 3 if wide else w - 2
        cells = []
        cells.append(("exposure", [
            ("%d listening" % (ports.get("listening") or 0), C_NORM),
            ("%d reachable off this machine" % (ports.get("exposed") or 0),
             C_AMBER if ports.get("exposed") else C_DIM),
            ("%d critical, %d high" % (ports.get("critical") or 0, ports.get("high") or 0),
             C_RED if (ports.get("critical") or ports.get("high")) else C_DIM),
            ("%d AI assets" % (ports.get("ai") or 0), C_VIOLET if ports.get("ai") else C_DIM),
        ]))
        fw = sec.get("firewall") or {}
        con = d.get("containers") or {}
        cells.append(("security", [
            ("firewall %s" % ("on" if fw.get("enabled") else
                              "off" if fw.get("enabled") is False else "unknown"),
             C_GREEN if fw.get("enabled") else C_AMBER),
            ("stealth %s" % ("on" if fw.get("stealth") else "off"), C_DIM),
            ("ssh %s" % ("on" if sec.get("ssh") else "off"),
             C_AMBER if sec.get("ssh") else C_DIM),
            (("%s %s" % (con.get("engine") or "containers",
                         "reachable" if con.get("reachable") else "not answering"))
             if con.get("engine") else "no container engine", C_DIM),
        ]))
        addrs = net.get("addresses") or []
        nlines = [("%s  %s  %s" % (a.get("iface"), a.get("ip"), a.get("scope") or ""), C_NORM)
                  for a in addrs[:3]]
        if not nlines:
            nlines = [("no address on any interface", C_DIM)]
        nlines.append(("%d interfaces" % len(net.get("interfaces") or []), C_DIM))
        cells.append(("network", nlines))

        if wide:
            for i, (title, lines) in enumerate(cells):
                bx = 1 + i * (cw + 1)
                bw = cw if i < 2 else w - bx - 1
                iy, ix, iw = self.box(y, bx, 6, bw, title, C_DIM, C_VIOLET)
                for j, (text, tone) in enumerate(lines[:4]):
                    self.put(iy + j, ix, text[:iw], tone)
        else:
            for title, lines in cells:
                if y + 6 >= h - 1:
                    break
                iy, ix, iw = self.box(y, 1, 6, w - 2, title, C_DIM, C_VIOLET)
                for j, (text, tone) in enumerate(lines[:4]):
                    self.put(iy + j, ix, text[:iw], tone)
                y += 6

    def draw_footer(self, h, w):
        # The dashboard puts its own status line on h-2, so the rule would land
        # on top of it. Views that leave the row free get the separator.
        if VIEWS[self.view][0] != "Dashboard":
            self.put(h - 2, 0, self.g.h * max(0, w - 1), C_DIM)
        keys = ("j/k move   h/l pane   tab view   enter detail   O open   "
                "/ search   f free port   V vibe   q quit")
        if VIEWS[self.view][0] == "System":
            keys = ("0-9 view   a animation %s   f free port   r rescan   "
                    "? keys   q quit" % ("on" if self.anim else "off"))
        if self.typing:
            keys = "search: %s_   (enter to keep, esc to clear)" % self.query
        age = _ago(time.time() - self.last)
        right = self.status or ("updated %s ago" % age if age else "updated")
        # The status is the shorter and the more perishable of the two, so the
        # key list gives way to it rather than the two overwriting each other.
        room = max(0, w - len(right) - 4)
        if len(keys) > room:
            keys = keys[:max(0, room - 1)].rstrip()
        self.put(h - 1, 1, keys, C_DIM)
        self.put(h - 1, max(2, w - len(right) - 2), right,
                 C_GREEN if self.status else C_DIM)

    def draw_session(self, y, w, r):
        picked = r.get("id") == self.sess_id
        if picked:
            self.put(y, 0, " " * (w - 1), C_SEL)
        live = r.get("live")
        age = time.time() - (r.get("last_active") or time.time())
        ctx = r.get("context")
        # Colour by how stale it is, because that is the decision being made:
        # a session nobody has touched in a week is the one to close.
        tone = (C_SEL if picked else
                C_GREEN if age < 3600 else
                C_NORM if age < 86400 else
                C_AMBER if age < 7 * 86400 else C_DIM)
        self.put(y, 1, ("* " if live else "  ") + (r.get("tool") or "?")[:6], tone, live)
        title = (r.get("title") or r.get("first_prompt") or r.get("id") or "?")
        title = " ".join(str(title).split())
        self.put(y, 10, title[:38], C_SEL if picked else C_NORM)
        self.put(y, 50, (r.get("project") or "-")[:18], C_SEL if picked else C_DIM)
        if ctx:
            # A context number nobody can read is decoration. k, one decimal.
            self.put(y, 70, "%6.0fk" % (ctx / 1000.0), tone)
        self.put(y, 79, _ago(age) + " ago", C_SEL if picked else C_DIM)
        if r.get("live_pids") and w > 96:
            # A pid is only worth printing when it is *this* session's pid. Four
            # agents in one directory cannot be told apart from outside, and
            # repeating the same two pids down every row is noise pretending to
            # be information.
            if r.get("ambiguous"):
                note = "%d here" % len(r["live_pids"])
            else:
                note = "pid %d" % r["live_pids"][0]
            self.put(y, 92, note, C_SEL if picked else C_DIM)

    def draw_session_detail(self, y0, h, w, r):
        line = y0
        self.put(y0 - 1, 1, "-" * (w - 3), C_DIM)

        def field(label, value, pair=C_NORM, wrap=False):
            nonlocal line
            if line >= h - 2 or value in (None, ""):
                return
            self.put(line, 1, "%-13s" % label, C_DIM)
            text = " ".join(str(value).split())
            if not wrap:
                self.put(line, 15, text[:max(0, w - 17)], pair)
                line += 1
                return
            room = max(20, w - 17)
            while text and line < h - 2:
                cut = text[:room]
                if len(text) > room:
                    sp = cut.rfind(" ")
                    if sp > room * 0.6:
                        cut = cut[:sp]
                self.put(line, 15, cut, pair)
                text = text[len(cut):].strip()
                line += 1

        field("session", r.get("id"))
        field("tool", "%s%s" % (r.get("tool") or "?",
                                "  " + r["model"] if r.get("model") else ""))
        field("project", r.get("cwd") or r.get("project"))
        ctx = r.get("context")
        if ctx:
            field("context", "%s tokens on the last turn  -  %d turns"
                  % ("{:,}".format(ctx), r.get("turns") or 0),
                  C_AMBER if ctx > 500000 else C_NORM)
        if r.get("last_active"):
            field("last active", "%s  (%s ago)"
                  % (time.strftime("%d %b %H:%M", time.localtime(r["last_active"])),
                     _ago(time.time() - r["last_active"])))
        if r.get("live_pids"):
            field("running", "pid %s%s"
                  % (", ".join(str(p) for p in r["live_pids"]),
                     "  - more than one agent is in this directory, so which of "
                     "them is this session cannot be told from outside"
                     if r.get("ambiguous") else ""),
                  C_GREEN)
            field("close it", "kill %s" % r["live_pids"][0], C_DIM)
        else:
            field("running", "no agent process in that directory", C_DIM)
        field("first prompt", r.get("first_prompt"), C_NORM, wrap=True)
        if r.get("summary"):
            field("where it got", r.get("summary"), C_DIM, wrap=True)
        elif r.get("last_prompt"):
            field("last prompt", r.get("last_prompt"), C_DIM, wrap=True)

    def draw_detail(self, y0, h, w, rows, idx):
        if not rows:
            return
        r = rows[idx]
        o = r.get("origin") or {}
        self.put(y0 - 1, 1, "-" * (w - 3), C_DIM)
        line = y0
        act = r.get("activity") or {}

        def field(label, value, pair=C_NORM):
            nonlocal line
            if line >= h - 2:
                return
            self.put(line, 1, "%-14s" % label, C_DIM)
            self.put(line, 16, str(value)[:max(0, w - 18)], pair)
            line += 1

        field("why", r.get("why") or "-")
        field("origin", ledger.phrase(o),
              C_AMBER if (o.get("recorded") and not o.get("carries_context")) else C_NORM)
        if not o.get("observed") and (o.get("recorded") or o.get("live")):
            field("", "already running when portlist first looked", C_DIM)
        field("last used", activity.phrase(act))
        field("respawns", o.get("respawns", 0))
        field("bound", ", ".join((r.get("exposure") or {}).get("addrs") or []) or "-",
              _tone(r))
        if (r.get("exposure") or {}).get("verified"):
            field("verified", (r["exposure"]["verified"] or {}).get("note", ""), C_AMBER)
        dep = r.get("depends_on") or []
        used = r.get("used_by") or []
        field("depends on", ", ".join("%s :%d" % (d["name"], d["port"]) for d in dep)
              or "no local service right now", C_NORM if dep else C_DIM)
        field("used by", ", ".join("%s" % u["name"] for u in used[:4])
              or "nothing connected right now", C_NORM if used else C_DIM)
        if r.get("container"):
            field("container", r["container"]["summary"], C_BLUE)
        field("stop it", "kill %s" % r.get("pid") if r.get("pid") is not None
              else "another user owns it", C_DIM)

    def draw_overlay(self, h, w):
        """A panel over the list: the free-port answer, or help."""
        title, lines = self.overlay
        bw = min(w - 6, max(len(title) + 6, max((len(l) for l in lines), default=20) + 6))
        bh = min(h - 6, len(lines) + 4)
        x0 = max(1, (w - bw) // 2)
        y0 = max(2, (h - bh) // 2)
        for y in range(y0, y0 + bh):
            self.put(y, x0, " " * bw, C_NORM)
        self.put(y0, x0, "+" + "-" * (bw - 2) + "+", C_BLUE)
        self.put(y0, x0 + 2, " %s " % title, C_BLUE, True)
        for i, line in enumerate(lines[:bh - 3]):
            self.put(y0 + 1 + i, x0 + 1, "|", C_BLUE)
            self.put(y0 + 1 + i, x0 + 3, line[:bw - 5],
                     C_GREEN if line.startswith("Use ") else C_NORM)
            self.put(y0 + 1 + i, x0 + bw - 1, "|", C_BLUE)
        self.put(y0 + bh - 2, x0, "+" + "-" * (bw - 2) + "+", C_BLUE)
        self.put(y0 + bh - 1, x0 + 2, "any key to close", C_DIM)

    def free_port(self):
        """The port suggester, over the list. The answer people actually want
        when they are looking at a port table is "so which one do I use"."""
        from . import freeport
        sel = next((r for r in self.visible() if r["id"] == self.sel_id), None)
        want = sel["port"] if sel else None
        project = (sel.get("dir") if sel else None) or None
        try:
            out = freeport.explain(want, rows=self.rows, project=project)
        except Exception as e:
            self.overlay = ("Free port", ["could not work one out: %s" % e])
            return
        lines = [l for l in out["text"].split("\n")]
        self.overlay = ("A port you can use", lines)
        self.s.clear()

    def splash(self):
        """Something to look at while the first scan runs. It is the slow one."""
        self.s.erase()
        h, w = self.s.getmaxyx()
        art = SPLASH if w >= 60 else ["PORTLIST"]
        y = max(1, h // 2 - len(art) // 2 - 1)
        for i, line in enumerate(art):
            bold = i < 4
            self.put(y + i, max(1, (w - len(line)) // 2), line,
                     C_BLUE if bold else C_DIM, bold)
        msg = "reading this machine..."
        self.put(y + len(art) + 1, max(1, (w - len(msg)) // 2), msg, C_DIM)
        self.s.refresh()

    # --------------------------------------------------------------- driving
    def open_selected(self):
        """Open the selected service in a browser.

        Only for something that actually answers HTTP: handing the browser a raw
        TCP port produces a blank tab and a shrug, which is worse than saying no.
        """
        rows = self.visible()
        r = next((x for x in rows if x["id"] == self.sel_id), None)
        if not r:
            return
        probe = r.get("probe") or {}
        if not (probe.get("http") or probe.get("https")):
            self.status = ":%d does not speak HTTP" % r["port"]
            return
        url = r.get("serves_url") or r.get("url")
        if not url:
            self.status = ":%d has no URL to open" % r["port"]
            return
        try:
            # webbrowser shells out on macOS and Linux; on a headless box it
            # returns False rather than raising, which is worth reporting.
            if not webbrowser.open(url):
                raise RuntimeError("no browser")
            self.status = "opened " + url
        except Exception:
            self.status = "could not open a browser - " + url

    def read_modified(self):
        """-> a (key, mods) pair for a CSI-u or modifyOtherKeys sequence, or None.

        Terminals disagree about modified Enter. Most send plain \n for
        Shift+Enter and Ctrl+Enter alike, which is indistinguishable from Enter
        and so cannot be bound. Newer ones (kitty, WezTerm, foot, recent xterm)
        send `ESC [ 13 ; 2 u` for shift and `ESC [ 13 ; 5 u` for ctrl, and those
        can. macOS Terminal and iTerm never deliver Cmd+Enter at all - the
        application above intercepts it - which is why `O` exists and is what the
        footer advertises.
        """
        buf = ""
        for _ in range(12):
            c = self.s.getch()
            if c == -1:
                break
            if 32 <= c < 127:
                buf += chr(c)
            if buf.endswith("u") or buf.endswith("~"):
                break
        if not buf.startswith("["):
            return None
        body = buf[1:-1]
        parts = [x for x in body.split(";") if x.isdigit()]
        if buf.endswith("u") and len(parts) >= 2:
            return int(parts[0]), int(parts[1])
        if buf.endswith("~") and len(parts) >= 3 and parts[0] == "27":
            return int(parts[2]), int(parts[1])
        return None

    def move(self, delta):
        if VIEWS[self.view][0] == "Sessions":
            ids = [it[1].get("id") for it in self.items() if it[0] == "sess"]
            if not ids:
                return
            i = ids.index(self.sess_id) if self.sess_id in ids else 0
            self.sess_id = ids[max(0, min(len(ids) - 1, i + delta))]
            return
        rows = self.visible()
        if not rows:
            return
        i = next((n for n, r in enumerate(rows) if r["id"] == self.sel_id), 0)
        self.sel_id = rows[max(0, min(len(rows) - 1, i + delta))]["id"]

    def moving(self):
        """Is anything on this screen animated right now?"""
        if self.vibe:
            return self.vibe.interval() is not None
        return (VIEWS[self.view][0] in ("System", "Dashboard")
                and not self.overlay and not self.typing)

    def frame_gap(self):
        """Seconds between frames for whatever is moving."""
        if self.vibe:
            return self.vibe.interval() or ANIM
        return ANIM

    def run(self):
        curses.curs_set(0)
        self.s.nodelay(True)
        self.splash()
        self.refresh_data(force=True)
        while True:
            self.draw()
            waited = 0.0
            painted = 0.0
            while waited < REFRESH:
                ch = self.s.getch()
                if ch != -1:
                    self.last_key = time.time()
                    if self.key(ch) is False:
                        return
                    self.draw()
                    painted = waited
                # Frames are only spent where something actually moves. Every
                # other view redraws on the data beat, as it always did.
                if self.anim and self.moving() and waited - painted >= self.frame_gap():
                    self.frame += 1
                    self.sample()
                    if self.vibe:
                        self.vibe.tick()
                    self.draw()
                    painted = waited
                # It drifts in on its own after a while, but only if motion is
                # wanted at all: turning animation off is a request for a still
                # screen, and this would be the opposite of honouring it.
                if (not self.vibe and self.anim and not self.typing and not self.overlay
                        and vibe_mod.load()["auto"]
                        and time.time() - self.last_key > vibe_mod.IDLE_ENTER):
                    self.enter_vibe()
                    self.draw()
                    painted = waited
                time.sleep(0.05)
                waited += 0.05
            self.status = ""
            self.refresh_data()

    def enter_vibe(self):
        self.vibe = vibe_mod.Vibe(self)
        self.vibe.entered = time.time()
        self.s.clear()

    def leave_vibe(self):
        self.vibe = None
        self.s.clear()

    def key(self, ch):
        if self.vibe:
            # Any key it does not claim brings the list straight back, and that
            # key is swallowed rather than acted on: coming back should never
            # also delete, open or filter something.
            if ch == curses.KEY_RESIZE:
                self.s.erase()
                return True
            if not self.vibe.key(ch):
                self.leave_vibe()
            return True
        if ch == ord("V"):
            self.enter_vibe()
            return True
        if self.overlay:
            self.overlay = None
            self.s.clear()
            return True
        if self.typing:
            if ch in (10, curses.KEY_ENTER):
                self.typing = False
            elif ch == 27:
                self.typing = False
                self.query = ""
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                self.query = self.query[:-1]
            elif 32 <= ch < 127:
                self.query += chr(ch)
            self.top = 0
            return True
        if ch == ord("/"):
            self.typing = True
            self.query = ""
            self.s.clear()
            return True
        if ch in (9, ord("\t"), curses.KEY_BTAB):
            # Tab walks the views in the same order as the number keys, so it is
            # the same journey either way round: 0, 1, 2, 3 and on.
            step = -1 if ch == curses.KEY_BTAB else 1
            self.view = (self.view + step) % len(VIEWS)
            self.top = 0
            self.s.clear()
            return True
        if ch in (ord("h"), curses.KEY_LEFT, ord("l"), curses.KEY_RIGHT):
            # Left and right move between the panes of whichever view has them.
            if VIEWS[self.view][0] == "Dashboard":
                step = -1 if ch in (ord("h"), curses.KEY_LEFT) else 1
                self.section = (self.section + step) % len(dash_mod.SECTIONS)
                self.s.clear()
            return True
        if ch == ord("f"):
            self.free_port()
            return True
        if ch == ord("?"):
            self.overlay = ("Keys", [
                "j / k        move            0  dashboard: everything at once",
                "tab          next view       1  services",
                "h / l        dashboard pane  2  reachable off this machine",
                "O            open in a browser  (shift+enter and ctrl+enter",
                "                                too, where the terminal sends",
                "                                them - macOS never delivers",
                "                                cmd+enter to a program)",
                "enter, o     detail pane",
                "/            search          3  needs attention",
                "f            a free port     4  looks abandoned",
                "r            rescan now      5  grouped by who started it",
                "q            quit            6  containers",
                "a            animation       7  agent sessions, and what they",
                "V            vibe mode          were about",
                "                             9  the graph: who started what,",
                "                                where it runs, what it exposes",
                "                             8  this machine: load, memory,",
                "                                disks, network, exposure",
                "",
                "Nothing here stops anything. The detail pane prints the",
                "command; you run it.",
            ])
            self.s.clear()
            return True
        if ch == 27:
            # Could be a bare Escape, or the start of a modified-key sequence.
            mod = self.read_modified()
            if mod:
                code, mods = mod
                # 13 is Enter. In (mods - 1), bit 0 is shift, bit 2 is ctrl and
                # bit 3 is super/cmd. Any of the three opens the port: which one
                # a terminal can actually deliver varies, so accept them all
                # rather than making the user find out which theirs sends.
                if code == 13 and ((mods - 1) & 0b1101):
                    self.open_selected()
                    return True
                return True
            return False
        if ch in (ord("q"),):
            return False
        if ch == ord("O"):
            self.open_selected()
            return True
        if ch in (ord("j"), curses.KEY_DOWN):
            if VIEWS[self.view][0] == "Dashboard" and self.section == 1:
                self.act_top += 1
            else:
                self.move(1)
        elif ch in (ord("k"), curses.KEY_UP):
            if VIEWS[self.view][0] == "Dashboard" and self.section == 1:
                self.act_top = max(0, self.act_top - 1)
            else:
                self.move(-1)
        elif ch in (curses.KEY_NPAGE, ord(" ")):
            self.move(10)
        elif ch == curses.KEY_PPAGE:
            self.move(-10)
        elif ch in (ord("\n"), curses.KEY_ENTER, ord("o")):
            self.detail = not self.detail
        elif ch == ord("r"):
            self.status = "rescanning..."
            self.draw()
            self.refresh_data(force=True)
            self.status = "rescanned"
        elif ch == ord("a"):
            self.anim = not self.anim
            self.status = "animation %s" % ("on" if self.anim else "off")
        elif chr(ch) in VIEW_KEYS if 32 <= ch < 127 else False:
            self.view = VIEW_KEYS[chr(ch)]
            self.top = 0
            # A grouped view and a flat one have different line lengths, so a
            # partial redraw leaves the tail of the old view on screen. Force a
            # full repaint when the shape of the page changes.
            self.s.clear()
        elif ch == curses.KEY_RESIZE:
            self.s.erase()
        return True


def main():
    """-> exit code. Called from the CLI."""
    # Box and block glyphs are multi-byte; without this curses writes them as
    # question marks. It must happen before initscr, and it is a no-op where
    # the locale is already right.
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    try:
        curses.wrapper(lambda scr: Tui(scr).run())
    except KeyboardInterrupt:
        pass
    except curses.error as e:
        print("the terminal could not be put into full-screen mode: %s" % e)
        return 2
    return 0

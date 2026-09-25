"""Paint portlist's own terminal screens without a terminal, for the playground.

The playground shows `portlist` as it really looks, so it does not imitate the
screens: it runs plcore.tui.Tui against an in-memory window and records what
each view paints, cell by cell, colour by colour. A change to the real screens
shows up in the playground the next time tools/gen_playground.py runs, and CI
fails if nobody ran it.

Frames are stored as lines of [text, tone] runs, and every distinct line once:
a view with the cursor on row three and on row four differs by two lines, so
the table of lines is small even though the list of frames is long.
"""
import curses
import os
import tempfile
import time

W, H = 132, 46          # wide enough that the view bar spells its names out, tall enough to fill the plate
TONES = {0: "n", 1: "n", 2: "d", 3: "r", 4: "a", 5: "g", 6: "b", 7: "h", 8: "s", 9: "v"}


class Screen:
    """The part of a curses window the Tui touches."""

    def __init__(self, h, w):
        self.h, self.w = h, w
        self.erase()

    def erase(self):
        self.cells = [[(" ", 0, False)] * self.w for _ in range(self.h)]

    clear = erase

    def getmaxyx(self):
        return self.h, self.w

    def addnstr(self, y, x, text, n, attr=0):
        pair, bold = (attr >> 8) & 0xFF, bool(attr & curses.A_BOLD)
        row = self.cells[y]
        for i, ch in enumerate(str(text)[:n]):
            if 0 <= x + i < self.w:
                row[x + i] = (ch, pair, bold)

    def addstr(self, y, x, text, attr=0):
        self.addnstr(y, x, text, self.w - x, attr)

    def inch(self, y, x):
        ch, pair, bold = self.cells[y][x]
        return (ord(ch) & 0xFF) | (pair << 8) | (curses.A_BOLD if bold else 0)

    def refresh(self):
        pass

    def noutrefresh(self):
        pass

    def lines(self):
        """-> [[text, tone], ...] per row, trailing blanks dropped."""
        out = []
        for row in self.cells:
            runs, cur, buf = [], None, ""
            for ch, pair, bold in row:
                tone = TONES.get(pair, "n") + ("!" if bold and ch != " " else "")
                if ch == " " and pair not in (7, 8):
                    tone = "_"                     # plain space: carries no colour
                if tone != cur:
                    if buf:
                        runs.append([buf, cur])
                    cur, buf = tone, ""
                buf += ch
            if buf and not (cur == "_" and not buf.strip()):
                runs.append([buf, cur])
            while runs and runs[-1][1] == "_":
                runs.pop()
            out.append([[t, "" if c == "_" else c] for t, c in runs])
        return out


class Clock:
    """time.time and time.strftime pinned to one moment, so the bytes are stable."""

    def __init__(self, now):
        self.now = now

    def __enter__(self):
        self.saved = time.time, time.strftime, time.localtime
        real_strftime, real_gmtime = time.strftime, time.gmtime
        time.time = lambda: self.now
        time.localtime = lambda t=None: real_gmtime(self.now if t is None else t)
        time.strftime = lambda fmt, t=None: real_strftime(fmt, t if t is not None else real_gmtime(self.now))
        return self

    def __exit__(self, *exc):
        time.time, time.strftime, time.localtime = self.saved


def frames(state, now, table=None):
    """Every screen a visitor can reach with the keys the playground answers to.

    `state` carries what a scan would have returned: rows, host, groups,
    containers, sessions, sysinfo, hist, events. Lines go into `table` (shared
    across calls, so several states cost one set of lines); frames refer to
    them by index. Returns {"views": {...}, "vibe": [...]}.
    """
    table = table if table is not None else {"lines": [], "index": {}}
    saved = {n: getattr(curses, n) for n in ("color_pair", "has_colors")}
    curses.color_pair = lambda p: p << 8
    curses.has_colors = lambda: False          # Tui skips init_pair; colour is switched on below
    data = tempfile.mkdtemp(prefix="plplay-")
    saved_env = os.environ.get("PORTLIST_DATA")
    os.environ["PORTLIST_DATA"] = data
    # Nothing from the machine building this may reach a public page: history
    # resolves its files at import time, so it is pointed away by hand, and what
    # it "remembers" is the scenario's own list.
    from plcore import history
    kept = {n: getattr(history, n) for n in ("HOME", "STATE", "EVENTS", "recent")}
    history.HOME, history.STATE, history.EVENTS = data, os.path.join(data, "state.json"), os.path.join(data, "events.jsonl")
    history.recent = lambda limit=200: list(state.get("events") or [])[:limit]
    try:
        with Clock(now):
            return _frames(state, now, table)
    finally:
        for n, v in kept.items():
            setattr(history, n, v)
        for n, f in saved.items():
            setattr(curses, n, f)
        if saved_env is None:
            os.environ.pop("PORTLIST_DATA", None)
        else:
            os.environ["PORTLIST_DATA"] = saved_env


def _frames(state, now, store):
    from plcore import scan, tui as T, vibe as V

    scr = Screen(H, W)
    t = T.Tui(scr)
    t.colour = True
    t.g = T.Glyphs(True)
    t.rows, t.host = state["rows"], state["host"]
    scan._last["stdio_mcp"] = list(state.get("stdio") or [])
    t.summary = scan.summary(t.rows, t.host)
    t.groups, t.containers, t.sessions = state["groups"], state["containers"], state["sessions"]
    t.sess_max = max([r.get("context") or 0 for r in (t.sessions.get("sessions") or [])] or [0])
    t.sysinfo, t.hist = state["sysinfo"], state["hist"]
    t.sampled = now + 10 ** 9          # never sample the building machine
    t.sample = lambda: None
    t.known = {r["id"] for r in t.rows if not r.get("quiet")}
    t.last = now - 1
    t.frame = 0

    table, index = store["lines"], store["index"]

    def snap():
        scr.erase()
        t.draw()
        ids = []
        for line in scr.lines():
            key = repr(line)
            if key not in index:
                index[key] = len(table)
                table.append(line)
            ids.append(index[key])
        return ids

    views = {}
    for i, (label, key, _keep) in enumerate(T.VIEWS):
        t.view, t.top, t.detail = i, 0, False
        v = {"label": label, "key": key}
        if label == "Sessions":
            ids = [it[1].get("id") for it in t.items() if it[0] == "sess"]
            v["frames"] = []
            for sid in ids or [None]:
                t.sess_id, t.top = sid, 0
                t.detail = False
                a = snap()
                t.detail = True
                v["frames"].append([a, snap()])
        elif label == "System":
            v["frames"] = [[snap(), None]]
        else:
            rows = t.visible()
            v["frames"] = []
            for r in rows or [None]:
                t.sel_id = r["id"] if r else None
                t.top = 0
                t.detail = False
                a = snap()
                b = None
                if r and label != "Dashboard":
                    t.detail = True
                    b = snap()
                v["frames"].append([a, b])
            if label == "Dashboard":
                panes = []
                for sec in range(3):
                    t.section, t.sel_id, t.detail = sec, (rows[0]["id"] if rows else None), False
                    panes.append(snap())
                t.section = 0
                v["panes"] = panes
        views[key] = v

    # The ambient screen: every scene once. Pictures are the terminal's graphics
    # layer and never reach a browser, so the scenes are drawn without them.
    t.view = 1
    t.vibe = V.Vibe(t)
    t.vibe.bg = None
    t.vibe.ascii_bg = True             # characters, never the terminal graphics layer
    t.vibe.rotate = False
    scenes = []
    for n, name in enumerate(V.SCENES):
        t.vibe.scene = n
        t.vibe.scene_since = now - 60      # past the arrival wipe
        scenes.append({"name": name, "frame": snap()})
    t.vibe = None
    return {"views": views, "vibe": scenes}

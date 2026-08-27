"""Vibe mode: the screen you leave open on the second monitor.

`V`, or by itself after thirty seconds of no keys. Any key comes straight back.

The rule that shapes every line of this file: **the animation is driven by real
measurements, and nothing else moves.** A dot pulses because a service was
measured busy, not because pulsing looks good. A particle travels an edge
because a loopback connection was actually observed between those two ports. If
nothing has been measured yet, the thing sits still and says so. Ambient motion
that invents activity is a lie told beautifully, and this is a tool for finding
out what is true about a machine.

Four scenes rotate: the machine, the network between local services, the agents
and what they started, and what has actually happened lately.
"""
import curses
import json
import math
import os
import time

from . import history, imgmap, ledger, security

SCENES = ("cockpit", "machine", "network", "agents", "activity", "grid", "room")

# How much of a background each scene will carry. A scene that is mostly empty
# can hold a picture; one that is already lines and nodes cannot, and turning it
# down per scene is the difference between atmosphere and a mess.
SCENE_BG = {"cockpit": 1.0, "machine": 1.0, "grid": 0.55, "room": 1.0,
            "activity": 0.75, "agents": 0.65, "network": 0.40}

# The dial, in steps. Capped well below full on purpose: at full strength the
# picture wins and the data underneath stops being readable, and a setting that
# can make the screen worse should not offer that value.
BG_STEPS = (0, 15, 30, 45, 60)
BG_MAX = 60

# The one scene that brings its own picture. The others are drawings of
# measurements, and a background there is optional decoration behind them.
# Here the picture is the scene, so it opens at the cap that the others treat
# as a limit, and the few readings that fit are placed where the room is dark.
ROOM_PNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "room.png")
ROOM_BG = BG_MAX

def elapsed(stamp):
    """A wall-clock stamp as how long ago it was, or "" when there is none."""
    if not stamp:
        return ""
    s = int(max(0, time.time() - stamp))
    if s < 90:
        return "%ds ago" % s
    if s < 5400:
        return "%dm ago" % (s // 60)
    if s < 172800:
        return "%dh ago" % (s // 3600)
    return "%dd ago" % (s // 86400)


# name -> (frame interval in seconds, seconds a scene holds before the next)
SPEEDS = {
    "static":    (None, None),
    "slow":      (0.50, 24.0),
    "medium":    (0.25, 14.0),
    "cinematic": (0.12, 8.0),
}
SPEED_ORDER = ("static", "slow", "medium", "cinematic")

IDLE_ENTER = 30.0        # seconds of no keypress before it drifts in on its own

# Service state glyphs. Each one is a measurement, not a mood:
#   active  - measured busy inside the last minute
#   idle    - watched long enough to know, and not busy
#   running - listening, but not watched long enough to say anything about use
#   unknown - the process cannot be read at all
GLYPH = {
    "active":  "◉●◉○",     # a real pulse
    "idle":    "○",
    "running": "●",
    "unknown": "⚠",
}


def _pair(tui, name):
    return THEMES[name]


# Roles, mapped onto the colours curses actually has. Keys are read by the
# scenes; a theme that leaves one out inherits "observatory".
THEMES = {
    "observatory": {"accent": "blue", "glow": "norm", "text": "norm",
                    "dim": "dim", "warn": "amber", "bad": "red",
                    "blurb": "clean, dark, technical"},
    "neon":        {"accent": "violet", "glow": "blue", "text": "norm",
                    "dim": "dim", "warn": "amber", "bad": "red",
                    "blurb": "colourful, cyberpunk"},
    "terminal":    {"accent": "green", "glow": "green", "text": "green",
                    "dim": "dim", "warn": "green", "bad": "green",
                    "blurb": "monochrome green"},
    "aurora":      {"accent": "blue", "glow": "violet", "text": "norm",
                    "dim": "dim", "warn": "violet", "bad": "red",
                    "blurb": "soft, ambient"},
    "minimal":     {"accent": "norm", "glow": "norm", "text": "norm",
                    "dim": "dim", "warn": "dim", "bad": "dim",
                    "blurb": "almost still"},
}
THEME_ORDER = ("observatory", "neon", "terminal", "aurora", "minimal")


def _settings_path():
    return os.path.join(security.data_dir(), "vibe.json")


def load():
    try:
        with open(_settings_path()) as f:
            d = json.load(f)
    except Exception:
        d = {}
    try:
        op = int(d.get("bg_opacity", 0))
    except (TypeError, ValueError):
        op = 0
    return {"theme": d.get("theme") if d.get("theme") in THEMES else "observatory",
            "speed": d.get("speed") if d.get("speed") in SPEEDS else "medium",
            "auto": bool(d.get("auto", True)),
            # Off unless somebody asks for it. A tool that quietly starts drawing
            # pictures behind your data has changed what it is without asking.
            "bg": str(d.get("bg") or ""),
            "bg_opacity": max(0, min(BG_MAX, op)),
            # auto flips a picture that is mostly light, so what gets drawn is
            # the ink somebody drew rather than the paper it sits on.
            "bg_invert": (d.get("bg_invert") if d.get("bg_invert") in ("auto", "on", "off")
                          else "auto")}


def save(settings):
    try:
        os.makedirs(security.data_dir(), exist_ok=True)
        with open(_settings_path(), "w") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass


def state_of(row):
    """-> one of GLYPH's keys, from measurement only."""
    if row.get("pid") is None:
        return "unknown"
    act = row.get("activity") or {}
    if not act.get("known"):
        return "running"          # listening; not watched long enough to judge
    idle = act.get("idle_seconds")
    if act.get("ever_busy") and idle is not None and idle < 60:
        return "active"
    return "idle"


class Vibe:
    """Draws the ambient screen. Owns no data: everything comes from the Tui."""

    def __init__(self, tui):
        self.t = tui
        s = load()
        self.theme = s["theme"]
        self.speed = s["speed"]
        self.auto = s["auto"]
        self.bg = s["bg"]
        self.bg_opacity = s["bg_opacity"]
        self.bg_invert = s["bg_invert"]
        self.bg_cache = None          # (path, mtime, cols, rows) -> grid
        self.room_bad = False         # the shipped plate failed to load
        self.bg_grid = None
        self.bg_note = ""
        self.scene = 0
        self.frame = 0
        self.scene_since = time.time()
        self.entered = 0.0
        # Change detection, so an arriving service is visibly an event rather
        # than a row that was suddenly always there. Both maps are id -> when.
        self.seen = {}
        self.gone = {}

    # ------------------------------------------------------------- plumbing
    def interval(self):
        return SPEEDS[self.speed][0]

    def tick(self):
        self.frame += 1
        dwell = SPEEDS[self.speed][1]
        if dwell and time.time() - self.scene_since >= dwell:
            self.scene = (self.scene + 1) % len(SCENES)
            self.scene_since = time.time()

    def key(self, ch):
        """-> True to stay in vibe, False to leave. Any unclaimed key leaves."""
        if ch == ord("t"):
            self.theme = THEME_ORDER[(THEME_ORDER.index(self.theme) + 1) % len(THEME_ORDER)]
        elif ch == ord("s"):
            self.speed = SPEED_ORDER[(SPEED_ORDER.index(self.speed) + 1) % len(SPEED_ORDER)]
        elif ch == ord("n"):
            self.scene = (self.scene + 1) % len(SCENES)
            self.scene_since = time.time()
        elif ch == ord("A"):
            self.auto = not self.auto
        elif ch == ord("b"):
            # Tune it live rather than by editing json.
            steps = list(BG_STEPS)
            here = min(range(len(steps)), key=lambda i: abs(steps[i] - self.bg_opacity))
            self.bg_opacity = steps[(here + 1) % len(steps)]
            self.bg_grid = self.bg_cache = None
        elif ch == ord("B"):
            # The auto guess reads the picture's average brightness, which is
            # right for most of them and wrong for the rest. This is the way to
            # say so without editing json.
            order = ("auto", "on", "off")
            self.bg_invert = order[(order.index(self.bg_invert) + 1) % len(order)]
            self.bg_grid = self.bg_cache = None
        else:
            return False
        save({"theme": self.theme, "speed": self.speed, "auto": self.auto,
              "bg": self.bg, "bg_opacity": self.bg_opacity,
              "bg_invert": self.bg_invert})
        return True

    # ------------------------------------------------------------- painting
    def c(self, role):
        """A theme role -> the Tui's colour constant."""
        from . import tui as T
        names = {"norm": T.C_NORM, "dim": T.C_DIM, "red": T.C_RED, "amber": T.C_AMBER,
                 "green": T.C_GREEN, "blue": T.C_BLUE, "violet": T.C_VIOLET}
        theme = THEMES.get(self.theme, THEMES["observatory"])
        return names[theme.get(role, "norm")]

    def mid(self, y, w, text, role="text", bold=False, off=0):
        self.t.put(y, max(0, (w - len(text)) // 2 + off), text, self.c(role), bold)

    def phase(self, period=4):
        return (self.frame // max(1, period))

    def beat(self):
        """The machine heartbeat. It marks time; it does not claim a reading."""
        return " .oOo"[self.phase(2) % 5] if self.speed != "static" else "o"

    def meter(self, y, x, width, pct, role="accent"):
        g = self.t.g
        if pct is None:
            self.t.put(y, x, "not measured", self.c("dim"))
            return
        fill = int(round(width * max(0.0, min(100.0, pct)) / 100.0))
        tone = "bad" if pct >= 90 else "warn" if pct >= 75 else role
        self.t.put(y, x, g.full * fill, self.c(tone), True)
        self.t.put(y, x + fill, g.empty * (width - fill), self.c("dim"))

    NEW_FOR = 12.0          # seconds an arrival or a departure stays marked

    def notice(self):
        """The scan owns the diff now; this keeps the old names pointing at it."""
        self.seen = {sid: 1.0 for sid in self.t.known}
        self.gone = dict(self.t.departed)
        return

    def _notice_unused(self):
        """Diff the live set against the last frame. Real events, not decoration.

        The first pass establishes a baseline and marks nothing: everything is
        new to *this screen* the moment it opens, and none of it is new to the
        machine. Marking all fourteen services NEW because vibe mode just
        started is the same lie as inventing motion, told in a different way.
        """
        now = time.time()
        live = {r["id"]: r for r in self.t.live_rows()}
        first = not self.seen and not self.gone
        for sid in live:
            if sid not in self.seen:
                self.seen[sid] = 0.0 if first else now
            self.gone.pop(sid, None)
        for sid in list(self.seen):
            if sid not in live:
                self.gone.setdefault(sid, now)
                del self.seen[sid]
        for sid, when in list(self.gone.items()):
            if now - when > self.NEW_FOR:
                del self.gone[sid]

    def fresh(self, sid):
        when = self.t.arrived.get(sid)
        if when is None:
            return None
        age = time.time() - when
        return None if age > self.t.CHANGE_FOR else (age / self.t.CHANGE_FOR)

    def _fresh_unused(self, sid):
        """-> 0.0 to 1.0 for a service that appeared while this screen watched.

        `0.0` in `seen` is the baseline marker: it was already listening, so it
        is not an arrival and never gets marked.
        """
        when = self.seen.get(sid)
        if not when:
            return None
        age = time.time() - when
        return None if age > self.NEW_FOR else (age / self.NEW_FOR)

    # ------------------------------------------------------------ backdrop
    BG_RAMP = " .:-=+*#"

    def _disown(self, own):
        """Stop retrying a picture that will not load, and blame the right one.

        Every failure here used to clear `self.bg`, which is correct for a file
        the user named and wrong for the one that ships with the program: a
        broken install would silently throw away their background instead.
        """
        if own and not self.bg:
            self.room_bad = True
        else:
            self.bg = ""

    def backdrop(self, h, w, scene):
        """Draw the picture behind the scene, if one was asked for.

        Decoding is done once and cached: a 1600x900 PNG takes about half a
        second to unfilter, which is fine on entry and impossible per frame.
        """
        # One scene *is* its picture, the way the grid scene is its tiles, so it
        # always draws the plate that ships with the program and always at the
        # cap. A picture of your own decorates the other six; letting it replace
        # this one meant "room" quietly stopped being the room.
        own = (scene == "room" and not self.room_bad
               and os.path.exists(ROOM_PNG))
        if own:
            path, opacity, invert = ROOM_PNG, ROOM_BG, "off"
        else:
            path, opacity, invert = self.bg, self.bg_opacity, self.bg_invert
        if not path or opacity <= 0:
            return
        cols, rows = max(1, w - 2), max(1, h - 4)
        key = None
        try:
            key = (path, os.path.getmtime(path), cols, rows, invert)
        except OSError as e:
            self.bg_note = "background unreadable: %s" % (e.strerror or "no such file")
            self._disown(own)
            return
        if key != self.bg_cache:
            try:
                flip = {"auto": "auto", "on": True, "off": False}[invert]
                self.bg_grid = imgmap.cells(path, cols, rows, invert=flip)
                self.bg_note = ""
            except imgmap.Unsupported as e:
                self.bg_note = "background: %s" % e
                self._disown(own)
                self.bg_grid = None
                return
            except Exception:
                self.bg_note = "background could not be read"
                self._disown(own)
                self.bg_grid = None
                return
            self.bg_cache = key
        if not self.bg_grid:
            return
        # Opacity is density here, not alpha: a terminal cannot fade a glyph, so
        # a fainter picture is a sparser one drawn in the dimmest colour.
        #
        # And it is painted into the negative space only. Drawn underneath, the
        # scene's own gaps let the picture through between words and every row
        # of text came out speckled. Asking curses what is already in each cell
        # and skipping the ones that are taken costs one inch() per cell and
        # keeps the data perfectly legible, which is the whole bargain.
        strength = (opacity / 100.0) * SCENE_BG.get(scene, 0.7)
        ramp = self.BG_RAMP
        top = len(ramp) - 1
        scr = self.t.s
        margin = 4
        for y, line in enumerate(self.bg_grid):
            yy = y + 2
            width = len(line)
            # Read the row once, then keep the picture a few cells clear of
            # anything already on it. Filling every empty cell put stipple in
            # the gaps *between words*, which does not read as atmosphere, it
            # reads as a dirty screen.
            taken = bytearray(width)
            for x in range(width):
                try:
                    if (scr.inch(yy, x + 1) & 0xFF) != 32:
                        taken[x] = 1
                except curses.error:
                    taken[x] = 1
            near = bytearray(width)
            for x in range(width):
                if taken[x]:
                    for k in range(max(0, x - margin), min(width, x + margin + 1)):
                        near[k] = 1
            for x, v in enumerate(line):
                if near[x]:
                    continue
                step = int(round(v * strength * top * 1.6))
                if step > 0:
                    self.t.put(yy, x + 1, ramp[min(step, top)], self.c("dim"))

    def draw(self, h, w):
        self.notice()
        name = SCENES[self.scene]
        self.mid(1, w, "P O R T L I S T" if w >= 40 else "PORTLIST", "accent", True)
        getattr(self, "_" + name)(h, w)
        self.backdrop(h, w, name)          # into the gaps the scene left
        self.footer(h, w)
        self.wipe(h, w)

    def wipe(self, h, w):
        """A scene arrives left to right. Presentation only: it claims nothing."""
        if self.speed == "static":
            return
        span = 0.45
        since = time.time() - self.scene_since
        if since >= span:
            return
        edge = int(w * (since / span))
        for y in range(2, h - 2):
            self.t.put(y, edge, " " * max(0, w - edge - 1), self.c("dim"))
        self.t.put(min(h - 3, max(2, h // 2)), edge, self.t.g.v, self.c("accent"), True)

    def footer(self, h, w):
        left = "%s   %s   %s" % (SCENES[self.scene], self.theme, self.speed)
        right = time.strftime("%H:%M:%S   %a %d %b")
        self.t.put(h - 2, 2, left, self.c("dim"))
        self.t.put(h - 2, max(3, w - len(right) - 2), right, self.c("dim"))
        if SCENES[self.scene] == "room":
            hint = "any key returns   t theme   s speed   n scene"
        else:
            hint = "any key returns   t theme   s speed   n scene   b background %s" % (
                ("%d%%" % self.bg_opacity) if (self.bg and self.bg_opacity) else "off")
            if self.bg and self.bg_opacity:
                hint += "   B ink %s" % self.bg_invert
        if self.bg_note:
            hint = self.bg_note
        if w > len(hint) + 6:
            self.mid(h - 1, w, hint, "dim")

    # --------------------------------------------------------------- scenes
    def _cockpit(self, h, w):
        """Everything at once: the screenshot the whole thing is designed around."""
        t = self.t
        d = t.sysinfo or {}
        cpu = d.get("cpu") or {}
        mem = d.get("memory") or {}
        disks = d.get("disks") or []
        s = t.summary or {}
        # Risk first, then port: on a screen that shows six of fourteen, the six
        # worth showing are the ones that scored.
        rows = sorted(t.live_rows(),
                      key=lambda r: (-(r.get("risk") or 0), r.get("port") or 0))
        y = 3

        # one strip of meters and counts
        bar = max(8, min(16, (w - 58) // 2))
        x = max(2, (w - (bar * 2 + 54)) // 2)
        t.put(y, x, "CPU", self.c("dim"))
        self.meter(y, x + 4, bar, cpu.get("load_pct"))
        if cpu.get("load_pct") is not None:
            t.put(y, x + 5 + bar, "%3.0f%%" % cpu["load_pct"], self.c("text"), True)
        t.put(y, x + 11 + bar, "MEM", self.c("dim"))
        self.meter(y, x + 15 + bar, bar, mem.get("pct"), "glow")
        if mem.get("pct") is not None:
            t.put(y, x + 16 + bar * 2, "%3.0f%%" % mem["pct"], self.c("text"), True)
        if disks:
            t.put(y + 1, x, "DISK", self.c("dim"))
            self.meter(y + 1, x + 5, bar, disks[0].get("pct"))
            if disks[0].get("pct") is not None:
                t.put(y + 1, x + 6 + bar, "%3.0f%%" % disks[0]["pct"], self.c("text"), True)
        beat = "%s  MACHINE ALIVE" % self.beat()
        t.put(y + 1, x + 11 + bar, beat, self.c("glow"), True)
        y += 3

        # the services, with a state that is measured and a risk mark that is scored
        room = max(3, min(len(rows), (h - y - 12)))
        wide = w >= 78
        for i, r in enumerate(rows[:room]):
            yy = y + i
            st = state_of(r)
            glyph = GLYPH[st]
            mark = glyph[self.phase(3) % len(glyph)] if len(glyph) > 1 else glyph
            arriving = self.fresh(r["id"])
            role = "glow" if st == "active" else "text" if st == "running" else "dim"
            t.put(yy, x, mark, self.c(role), st == "active")
            t.put(yy, x + 2, ":%-6s" % r.get("port"), self.c("accent"))
            t.put(yy, x + 10, (r.get("service") or "?")[:20], self.c("text"))
            if wide:
                proj = (r.get("project") or {}).get("name") or r.get("dir_short") or ""
                t.put(yy, x + 32, str(proj)[:16], self.c("dim"))
                reach = (r.get("exposure") or {}).get("level")
                t.put(yy, x + 50, "LOCAL" if reach == "loopback" else "OFF-BOX",
                      self.c("dim" if reach == "loopback" else "warn"))
            band = (r.get("risk_band") or "")
            if band in ("Critical", "High"):
                t.put(yy, x + 60 if wide else x + 32,
                      ("◆" if self.phase(3) % 2 else "◇") + " " + band.upper(),
                      self.c("bad"), True)
            if arriving is not None:
                # A new service arrives as an event: the marker fades over the
                # first few seconds and then it is just another row.
                t.put(yy, x + 70 if wide else x + 44, "NEW", self.c("glow"), True)
        y += room + 1

        for sid, when in list(self.gone.items())[:2]:
            if y < h - 8:
                t.put(y, x, "· gone", self.c("warn"))
                t.put(y, x + 8, "a service stopped listening %ds ago"
                      % int(time.time() - when), self.c("dim"))
                y += 1

        # the strip along the bottom, and the counts
        if h - y >= 6:
            self._strip(y + 1, h - 4, w, rows)
        agents = len([g for g in (t.groups or []) if g.get("count")])
        cont = len(((t.containers or {}).get("containers")) or [])
        self.mid(h - 4, w, "%d SERVICES   %s   %d AGENTS   %s   %d CONTAINERS   %s   %d OFF-BOX"
                 % (s.get("shown", 0), t.g.dot, agents, t.g.dot, cont, t.g.dot,
                    s.get("exposed", 0)), "text", True)

    def _strip(self, y, bottom, w, rows):
        """A host bar with its busiest ports hanging off it."""
        t = self.t
        picks = rows[:6]
        if not picks or bottom - y < 3:
            return
        span = min(w - 12, 12 * len(picks))
        x0 = (w - span) // 2
        t.put(y, x0, t.g.h * span, self.c("dim"))
        t.put(y, x0 + span // 2 - 3, " HOST ", self.c("accent"), True)
        for i, r in enumerate(picks):
            x = x0 + int((i + 0.5) * span / len(picks))
            t.put(y + 1, x, t.g.v, self.c("dim"))
            st = state_of(r)
            glyph = GLYPH[st]
            mark = glyph[self.phase(3) % len(glyph)] if len(glyph) > 1 else glyph
            t.put(y + 2, x - 1, mark, self.c("glow" if st == "active" else "dim"),
                  st == "active")
            label = str(r.get("port"))
            t.put(y + 3, x - len(label) // 2, label, self.c("text"))

    def _room(self, h, w):
        """The room, and the few numbers that fit inside it.

        Every other scene is a drawing of measurements. This one is a picture,
        and the measurements sit in its dark corners: what is listening, what
        is still open, and how long since anything moved. It is the scene for
        the screen you are not reading, so it says less than the others on
        purpose and nothing on it moves that was not measured.
        """
        t = self.t
        rows = t.live_rows()
        doc = getattr(t, "sessions", None) or {}
        sess = doc.get("sessions") or []
        live = [r for r in sess if r.get("live")]

        self.mid(3, w, "THE ROOM", "dim")

        # Bottom left, where the plate is floor and nothing is drawn.
        y = max(6, h - 9)
        x = 4
        lines = [("listening", "%d" % len(rows) if rows is not None else None),
                 ("off this box", "%d" % sum(
                     1 for r in rows
                     if (r.get("exposure") or {}).get("level") not in (None, "loopback"))),
                 ("agent sessions open", "%d" % len(live) if doc else None)]
        for label, value in lines:
            if y > h - 4:
                break
            self.t.put(y, x, label, self.c("dim"))
            # A reading that could not be taken is drawn as one, not as zero.
            self.t.put(y, x + 24, value if value is not None else "not measured",
                       self.c("accent" if value is not None else "dim"), value is not None)
            y += 1

        if not doc:
            return
        # The oldest thing still open, on the right. It is the one fact this
        # scene exists to nag about from across the room.
        oldest = None
        for r in live:
            when = r.get("last_active")
            if when and (oldest is None or when < oldest[0]):
                oldest = (when, r)
        if not oldest:
            return
        note = "oldest open session   %s" % elapsed(oldest[0])
        if w > len(note) + 8:
            self.t.put(max(6, h - 5), max(4, w - len(note) - 4), note, self.c("dim"))

    def _grid(self, h, w):
        """Every listening service as a tile. The whole surface at a glance.

        The other scenes each answer one question; this one is the inventory,
        laid out so that a machine with four services and a machine with forty
        look obviously different from across a room.
        """
        t = self.t
        rows = sorted(t.live_rows(), key=lambda r: (-(r.get("risk") or 0), r.get("port") or 0))
        self.mid(3, w, "EVERYTHING LISTENING", "dim")
        if not rows:
            self.mid(max(6, h // 2), w, "nothing is listening", "dim")
            return

        tile_w, tile_h = 20, 4
        cols = max(1, min(len(rows), (w - 4) // tile_w))
        x0 = max(2, (w - cols * tile_w) // 2)
        y = 6
        for i, r in enumerate(rows):
            if y + tile_h > h - 4:
                left = len(rows) - i
                self.mid(h - 4, w, "and %d more" % left, "dim")
                break
            cx = x0 + (i % cols) * tile_w
            if i and i % cols == 0:
                y += tile_h
            st = state_of(r)
            glyph = GLYPH[st]
            mark = glyph[self.phase(3) % len(glyph)] if len(glyph) > 1 else glyph
            exp = (r.get("exposure") or {}).get("level")
            off = exp != "loopback"
            band = (r.get("risk_band") or "")
            role = "bad" if band in ("Critical", "High") else "warn" if off else \
                   "glow" if st == "active" else "text"
            t.put(y, cx, mark, self.c(role), st == "active")
            t.put(y, cx + 2, ":%-6s" % r.get("port"), self.c(role), True)
            # Both marks live on the port line. The risk diamond used to sit on
            # the row below, where it landed in the middle of the service name
            # and produced "Python http.se<>ver".
            if band in ("Critical", "High"):
                t.put(y, cx + 9, "◆" if self.phase(3) % 2 else "◇", self.c("bad"), True)
            if off:
                t.put(y, cx + tile_w - 4, "OFF", self.c("warn"), True)
            name = (r.get("service") or "unidentified")[:tile_w - 3]
            t.put(y + 1, cx + 2, name, self.c("dim"))
            proj = (r.get("project") or {}).get("name") or r.get("dir_short") or ""
            t.put(y + 2, cx + 2, str(proj)[:tile_w - 3], self.c("dim"))

        s = t.summary or {}
        self.mid(h - 3, w, "%d listening   %d reachable off this machine   %d need attention"
                 % (s.get("shown", 0), s.get("exposed", 0),
                    s.get("critical", 0) + s.get("high", 0)), "dim")

    def _machine(self, h, w):
        t = self.t
        d = t.sysinfo or {}
        cpu = (d.get("cpu") or {}); mem = (d.get("memory") or {})
        disks = d.get("disks") or []
        s = t.summary or {}

        bar = max(12, min(34, w - 34))
        rows = [("CPU", cpu.get("load_pct")), ("MEM", mem.get("pct"))]
        if disks:
            rows.append(("DISK", disks[0].get("pct")))
        wave = h > 22 and bool(self.t.hist["cpu"])
        # Centre the whole composition rather than hanging it off the top: this
        # screen is looked at from across a desk, not read from the first line.
        block = 3 + len(rows) + 1 + (6 if wave else 0) + 2
        y = max(3, (h - block) // 2)
        alive = "%s  MACHINE IS ALIVE" % self.beat()
        self.mid(y, w, alive, "glow", True); y += 2

        x = max(2, (w - (bar + 20)) // 2)
        for label, pct in rows:
            t.put(y, x, label, self.c("dim"))
            self.meter(y, x + 6, bar, pct)
            if pct is not None:
                t.put(y, x + 8 + bar, "%3.0f%%" % pct, self.c("text"), True)
            y += 1
        load = cpu.get("load") or []
        if load:
            t.put(y, x, "LOAD", self.c("dim"))
            t.put(y, x + 6, "  ".join("%.2f" % v for v in load[:3]), self.c("text"))
        y += 2

        # The wave, newest on the right, with gaps where nothing was measured.
        # The label sits at the left edge of the plot, not centred over it: a
        # centred label above a right-aligned series points at nothing.
        if wave and h > y + 6:
            # The plot is as wide as there are samples, up to the full width.
            # Padding it out to 60 columns and right-aligning 15 samples leaves
            # a gap that reads as missing data rather than as a young history.
            held = max(len(t.hist["cpu"]), len(t.hist["mem"]))
            width = max(12, min(w - 12, 60, held))
            wx = (w - width) // 2
            t.put(y, wx, "CPU", self.c("dim")); y += 1
            t.spark(y, wx, width, t.hist["cpu"], self.c("accent"), 100.0)
            y += 2
            t.put(y, wx, "MEMORY", self.c("dim")); y += 1
            t.spark(y, wx, width, t.hist["mem"], self.c("glow"), 100.0)
            y += 2

        agents = len([g for g in (t.groups or []) if g.get("count")])
        cont = len(((t.containers or {}).get("containers")) or [])
        line = "%d SERVICES   %s   %d AGENTS   %s   %d CONTAINERS" % (
            s.get("shown", 0), t.g.dot, agents, t.g.dot, cont)
        if h > y + 1:
            self.mid(y + 1, w, line, "text", True)

    def _network(self, h, w):
        """The host, its services, and the connections actually observed."""
        t = self.t
        rows = [r for r in t.live_rows()][:8]
        cy, cx = max(5, h // 2 - 1), w // 2
        self.mid(3, w, "LOCAL NETWORK", "dim")
        if not rows:
            self.mid(cy, w, "nothing is listening", "dim")
            return

        radius_y = max(2, min(6, (h - 12) // 2))
        radius_x = max(10, min(30, (w - 26) // 2))
        placed = []
        for i, r in enumerate(rows):
            ang = (2 * math.pi * i / len(rows)) - math.pi / 2
            y = int(round(cy + math.sin(ang) * radius_y))
            x = int(round(cx + math.cos(ang) * radius_x))
            placed.append((r, y, x))

        # spokes first, so nodes sit on top
        for r, y, x in placed:
            self._line(cy, cx, y, x, "dim")

        # a particle only where a loopback connection was really observed
        moving = 0
        for r, y, x in placed:
            if r.get("depends_on") or r.get("used_by"):
                moving += 1
                self._particle(cy, cx, y, x)

        t.put(cy, cx - 2, "HOST", self.c("accent"), True)
        for sid, when in list(self.gone.items())[:3]:
            pass        # departures are reported in the note below, not drawn
        for r, y, x in placed:
            st = state_of(r)
            glyph = GLYPH[st]
            mark = glyph[self.phase(3) % len(glyph)] if len(glyph) > 1 else glyph
            label = ":%s" % r.get("port")
            role = "glow" if st == "active" else "text" if st == "running" else "dim"
            left = x < cx
            t.put(y, x, mark, self.c(role), st == "active")
            t.put(y, x + 2 if not left else x - len(label) - 1, label, self.c("dim"))
            if self.fresh(r["id"]) is not None:
                t.put(y - 1, x - 1, "NEW", self.c("glow"), True)

        note = ("%d connection%s observed between local services"
                % (moving, "" if moving == 1 else "s")) if moving else \
               "no connections observed between them yet"
        self.mid(h - 4, w, note, "dim")
        if self.gone:
            self.mid(h - 3, w, "%d stopped listening in the last few minutes"
                     % len(self.gone), "warn")

    def _line(self, y0, x0, y1, x1, role):
        """A straight run of dots. Bresenham, minus the ends."""
        pts = self._points(y0, x0, y1, x1)
        for y, x in pts[2:-2]:
            self.t.put(y, x, "·" if self.t.g.dot == "●" else ".", self.c(role))

    def _particle(self, y0, x0, y1, x1):
        pts = self._points(y0, x0, y1, x1)[2:-2]
        if not pts:
            return
        y, x = pts[self.frame % len(pts)]
        self.t.put(y, x, self.t.g.dot, self.c("glow"), True)

    @staticmethod
    def _points(y0, x0, y1, x1):
        steps = max(abs(y1 - y0), abs(x1 - x0))
        if steps <= 0:
            return []
        return [(int(round(y0 + (y1 - y0) * i / steps)),
                 int(round(x0 + (x1 - x0) * i / steps))) for i in range(steps + 1)]

    def _agents(self, h, w):
        t = self.t
        groups = [g for g in (t.groups or []) if g.get("count")]
        self.mid(3, w, "WHAT THE AGENTS STARTED", "dim")
        if not groups:
            self.mid(max(5, h // 2), w, "nothing here was started by an agent", "dim")
            return
        y = 5
        x = max(2, (w - 56) // 2)
        for g in groups:
            if y > h - 6:
                break
            # `alive` is whether the starting process is still running. It is a
            # fact about the starter, not about the services, and the two are
            # kept apart everywhere else, so they are kept apart here.
            live = bool(g.get("alive"))
            mark = (GLYPH["active"][self.phase(3) % 4] if live else GLYPH["idle"])
            t.put(y, x, mark, self.c("glow" if live else "dim"), live)
            name = (g.get("name") or "?")
            for article in ("a ", "an ", "the "):     # "A CLAUDE CODE SESSION"
                if name.lower().startswith(article):
                    name = name[len(article):]
                    break
            t.put(y, x + 2, name[:32].upper(), self.c("text"), True)
            tail = "%d service%s" % (g.get("count", 0), "" if g.get("count") == 1 else "s")
            if not live:
                tail += ", starter has exited"
            t.put(y, x + 36, tail, self.c("dim"))
            y += 1
            kids = (g.get("services") or [])[:4]
            for i, svc in enumerate(kids):
                if y > h - 6:
                    break
                last = i == len(kids) - 1 and len(g.get("services") or []) <= 4
                t.put(y, x + 2, "└─" if last else "├─", self.c("dim"))
                t.put(y, x + 5, ":%-6s" % svc.get("port"), self.c("accent"))
                t.put(y, x + 13, str(svc.get("service") or "?")[:20], self.c("text"))
                proj = svc.get("project") or svc.get("dir_short") or ""
                t.put(y, x + 35, str(proj)[:20], self.c("dim"))
                y += 1
            more = len(g.get("services") or []) - len(kids)
            if more > 0 and y <= h - 6:
                t.put(y, x + 5, "and %d more" % more, self.c("dim"))
                y += 1
            y += 1
        if t.sessions:
            n = len([s for s in (t.sessions.get("sessions") or []) if s.get("live")])
            if n and h > y:
                self.mid(min(h - 4, y), w, "%d agent session%s open" % (n, "" if n == 1 else "s"),
                         "dim")

    def _activity(self, h, w):
        t = self.t
        self.mid(3, w, "WHAT HAS ACTUALLY HAPPENED", "dim")
        try:
            events = history.recent(limit=40)
        except Exception:
            events = []
        y = 5
        x = max(2, (w - 58) // 2)
        if not events:
            self.mid(max(6, h // 2), w, "nothing has changed since portlist started watching",
                     "dim")
        room = max(0, h - y - 8)
        for e in events[:room]:
            stamp = time.strftime("%H:%M:%S", time.localtime(e.get("ts") or 0))
            kind = e.get("type") or ""
            role = "warn" if kind == "closed" else "glow" if kind == "opened" else "text"
            fresh = (time.time() - (e.get("ts") or 0)) < 30
            mark = GLYPH["active"][self.phase(3) % 4] if fresh else t.g.dot
            t.put(y, x, stamp, self.c("dim"))
            t.put(y, x + 10, mark, self.c(role), fresh)
            t.put(y, x + 12, (e.get("text") or kind)[:w - x - 14], self.c("text" if fresh else "dim"))
            y += 1
        since = None
        try:
            since = ledger.watching_since()
        except Exception:
            pass
        if since:
            self.mid(h - 4, w, "watching since %s" % time.strftime("%d %b %H:%M",
                                                                  time.localtime(since)), "dim")

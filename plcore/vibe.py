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
import json
import math
import os
import time

from . import history, ledger, security

SCENES = ("machine", "network", "agents", "activity")

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
    return {"theme": d.get("theme") if d.get("theme") in THEMES else "observatory",
            "speed": d.get("speed") if d.get("speed") in SPEEDS else "slow",
            "auto": bool(d.get("auto", True))}


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
        self.scene = 0
        self.frame = 0
        self.scene_since = time.time()
        self.entered = 0.0

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
        else:
            return False
        save({"theme": self.theme, "speed": self.speed, "auto": self.auto})
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

    def draw(self, h, w):
        name = SCENES[self.scene]
        self.mid(1, w, "P O R T L I S T" if w >= 40 else "PORTLIST", "accent", True)
        getattr(self, "_" + name)(h, w)
        self.footer(h, w)

    def footer(self, h, w):
        left = "%s   %s   %s" % (SCENES[self.scene], self.theme, self.speed)
        right = time.strftime("%H:%M:%S   %a %d %b")
        self.t.put(h - 2, 2, left, self.c("dim"))
        self.t.put(h - 2, max(3, w - len(right) - 2), right, self.c("dim"))
        hint = "any key returns   t theme   s speed   n scene   A auto %s" % (
            "on" if self.auto else "off")
        if w > len(hint) + 6:
            self.mid(h - 1, w, hint, "dim")

    # --------------------------------------------------------------- scenes
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
        for r, y, x in placed:
            st = state_of(r)
            glyph = GLYPH[st]
            mark = glyph[self.phase(3) % len(glyph)] if len(glyph) > 1 else glyph
            label = ":%s" % r.get("port")
            role = "glow" if st == "active" else "text" if st == "running" else "dim"
            left = x < cx
            t.put(y, x, mark, self.c(role), st == "active")
            t.put(y, x + 2 if not left else x - len(label) - 1, label, self.c("dim"))

        note = ("%d connection%s observed between local services"
                % (moving, "" if moving == 1 else "s")) if moving else \
               "no connections observed between them yet"
        self.mid(h - 4, w, note, "dim")

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

#!/usr/bin/env python3
"""The README's screenshots, drawn by portlist itself.

    python3 tools/readme_shot.py          # needs playwright + chromium

The pictures are not screen grabs of somebody's laptop: tools/playtui.py paints
the real terminal program for the playground's simulated developer laptop, and
this puts that frame in a window and photographs it. So they never show a real
home directory, and they stay true to the program: re-run this when the screens
change.

Writes docs/dashboard.png (the laptop, :8787 selected), dashboard-server.png
(the staging server, :5432 selected), sessions.png, graph.png and vibe.png.
"""
import html
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import playtui  # noqa: E402

# A terminal a person would actually use for a screenshot, not the playground's
# tall plate: at this height the dashboard has no empty band in the middle.
playtui.W, playtui.H = 132, 36

import gen_playground as gen  # noqa: E402

# The nine curses colours, as a dark terminal theme draws them.
TONES = {"n": "#e7e3dc", "d": "#8b93a1", "r": "#ff6b61", "a": "#f0b35e", "g": "#8fd694",
         "b": "#78cfd6", "v": "#b99cff", "h": "#e7e3dc", "s": "#2f3b4a"}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
html,body{margin:0;background:transparent}
.win{display:inline-block;margin:28px;border-radius:12px;overflow:hidden;background:#141517;
  box-shadow:0 24px 60px rgba(0,0,0,.35),0 0 0 1px rgba(255,255,255,.06)}
.bar{height:34px;display:flex;align-items:center;gap:8px;padding:0 14px;background:#1d1f22;
  font:500 12.5px "IBM Plex Mono",Menlo,monospace;color:#8b93a1}
.bar i{width:12px;height:12px;border-radius:50%%;display:inline-block}
.bar span{flex:1;text-align:center;margin-right:52px}
pre{margin:0;padding:14px 18px 16px;font:14px/1.42 "IBM Plex Mono",Menlo,monospace;color:#e7e3dc;white-space:pre}
.x{font-weight:600}.hl{background:#e7e3dc;color:#141517}.sel{background:#2f3b4a;color:#fff}
</style></head><body><div class="win" id="w"><div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i><span>%s</span></div><pre>%s</pre></div></body></html>"""


def frame_html(lines):
    out = []
    for line in lines:
        runs = []
        for text, tone in line:
            if not tone:
                runs.append(html.escape(text))
                continue
            t, bold = tone[0], tone.endswith("!")
            cls = "x" if bold else ""
            if t == "h":
                cls += " hl"
            elif t == "s":
                cls += " sel"
            style = "" if t in "hs" else ' style="color:%s"' % TONES.get(t, TONES["n"])
            runs.append('<span class="%s"%s>%s</span>' % (cls.strip(), style, html.escape(text)))
        out.append("".join(runs))
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def main():
    from playwright.sync_api import sync_playwright
    # Each picture at the terminal height that fits it: a tall window around a
    # short view is a screenshot of empty space.
    wanted = [(gen.devbox, 36, "dashboard.png", "0", 8787),
              (gen.web1, 36, "dashboard-server.png", "0", 5432),
              (gen.devbox, 19, "sessions.png", "7", None),
              (gen.devbox, 24, "graph.png", "9", None),
              (gen.devbox, 26, "vibe.png", "V", "cockpit")]
    shots, cache = {}, {}
    for build, height, name, view, what in wanted:
        key = (build.__name__, height)
        if key not in cache:
            playtui.H = height
            cache[key] = gen.machine(build())
        m = cache[key]
        tui = m["tui"]
        st = tui["states"][""]
        if view == "V":
            ids = next(s["frame"] for s in st["vibe"] if s["name"] == what)
        elif what:
            # the dashboard lists by port, so a port's place in the listing is its frame
            ids = st["views"][view]["frames"][[r["port"] for r in m["listing"]].index(what)][0]
        else:
            ids = st["views"][view]["frames"][0][0]
        shots[name] = [tui["lines"][i] for i in ids]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(device_scale_factor=2, viewport={"width": 1400, "height": 900})
        for name, lines in shots.items():
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
                f.write(PAGE % ("portlist", frame_html(lines)))
                path = f.name
            pg.goto("file://" + path)
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(400)
            out = os.path.join(ROOT, "docs", name)
            pg.locator("#w").screenshot(path=out, omit_background=True)
            os.unlink(path)
            print("wrote docs/%s (%d KB)" % (name, os.path.getsize(out) // 1024))
        b.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check the website's playground in headless Chromium.

    python3 tools/worldcheck/play.py

Serves docs/ and walks the tutorial on the simulated laptop: lsof, the answer,
the chain, the leftovers, the stop, the views. Then checks what must hold: the
tutorial reaches its end, a stopped process's building comes down in the
harbour, another user's process needs sudo, the staging server's odd listener
is explained with its warnings, and the console stays clean. Exit status 0 is
a pass.
"""
import functools
import http.server
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && python -m playwright install chromium")
        return 2
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "docs")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/play/" % srv.server_address[1]
    fails, errors = [], []

    def check(name, ok, info=""):
        print(("PASS " if ok else "FAIL ") + name + (("  (%s)" % info) if info else ""))
        if not ok:
            fails.append(name)

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(base)
        pg.wait_for_function("() => { const f = document.querySelector('#harbour').contentWindow; try { return f.eval('W.buildings.size') > 0 } catch (e) { return false } }", timeout=20000)
        harbour = lambda js: pg.evaluate("(js) => document.querySelector('#harbour').contentWindow.eval(js)", js)

        def type_(cmd):
            pg.fill("#in", cmd)
            pg.press("#in", "Enter")
            time.sleep(0.4)

        start = harbour("[...W.buildings.values()].filter(b => b.s && b.s.port === 8787).length")
        for c in ("lsof -i :8787", "portlist 8787", "portlist 8787 --short", "portlist --list --leftovers", "kill 4412", "portlist"):
            type_(c)
        pg.keyboard.press("4")
        pg.keyboard.press("q")
        pg.wait_for_function("() => document.querySelector('#harbour').contentWindow.eval(\"[...W.buildings.values()].filter(b => b.s && b.s.port === 8787 && !b.leaving).length\") === 0", timeout=15000)
        out = pg.inner_text("#out")
        check("the answer names who started it and the chain", "a Claude Code session (exited)" in out and "launchd (pid 1)" in out)
        check("lsof only says who holds the port", "python3" in out and "(LISTEN)" in out)
        check("the tutorial reaches its end", pg.evaluate("() => tour.step") == 6, str(pg.evaluate("() => tour.step")))
        check("a stopped process's building comes down", start == 1)

        pg.evaluate("() => pick('web1')")
        pg.wait_for_function("() => document.querySelector('#harbour').contentWindow.eval('W.buildings.size') > 0", timeout=20000)
        type_("kill 1200")
        type_("echo $?")
        out = pg.inner_text("#out")
        check("another user's process needs sudo", "Operation not permitted" in out and out.strip().endswith("1"))
        type_("portlist 4444 --warnings")
        out = pg.inner_text("#out")
        check("the odd listener is explained with its warnings", "LD_PRELOAD" in out and "reachable from beyond this machine" in out)
        type_("sudo kill 1200")
        check("sudo stops it", pg.evaluate("() => S.killed.has(1200)"))
        b.close()
    srv.shutdown()
    check("no console errors", not errors, "; ".join(errors[:3]))
    print("ALL PASS" if not fails else "%d FAILED" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

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

        def selector_check(name, js, expected):
            actual = harbour(js)
            check(name, actual == expected, str(actual))

        # Browser-only tests of the actual renderer selectors, with synthetic
        # evidence. The port and display name alone must never select a logo.
        selector_check("exact attached container image logos", """(() => {
          const c = (image, service = '') => ({name_source:'container', family:'unknown',
            service_id:null, container_image:image, container_service:service});
          return [logoOf(c('traefik:3.0', 'traefik')),
                  logoOf(c('docker.io/pihole/pihole:latest', 'pihole')),
                  logoOf(c('docker.io/library/postgres:16', 'postgres')),
                  logoOf(c('public.ecr.aws/supabase/studio:latest'))];
        })()""", ["traefikproxy", "pihole", "postgresql", "supabase"])
        selector_check("digest and docker.io registry aliases retain exact repository identity", """(() => {
          const c = image => ({name_source:'container', family:'unknown', service_id:null,
            container_image:image, container_service:null});
          return [logoOf(c('index.docker.io/library/postgres@sha256:abcdef')),
                  logoOf(c('registry-1.docker.io/pihole/pihole@sha256:abcdef')),
                  logoOf(c('docker.io/library/traefik@sha256:abcdef')),
                  logoOf(c('sha256:abcdef'))];
        })()""", ["postgresql", "pihole", "traefikproxy", None])
        selector_check("catalog wins; conflicting image and service fail closed", """(() => {
          const c = {name_source:'container', family:'unknown', container_image:'postgres:16',
            container_service:'postgres'};
          return [logoOf({...c, service_id:'redis'}),
                  logoOf({...c, container_image:'traefik:3.0'})];
        })()""", ["redis", None])
        selector_check("unknown, ambiguous and unattached listeners have no brand", """(() => {
          const c = {family:'unknown', service_id:null, container_image:'traefik:3.0',
            container_service:'traefik'};
          return [logoOf({...c, name_source:'unidentified'}),
                  logoOf({...c, name_source:'unidentified', container_ambiguous:true}),
                  logoOf({...c, name_source:'process', cmd:'?'}),
                  logoOf({...c, name_source:'container', container_image:null, container_service:null})];
        })()""", [None] * 4)
        selector_check("registry ports and similar image names are not brand matches", """(() => {
          const c = image => ({name_source:'container', family:'unknown', service_id:null,
            container_image:image, container_service:null});
          return ['registry.local:5000/traefik:3', 'ghcr.io/other/traefik:3',
                  'traefikish:3', 'docker.io/library/traefik-extra:3'].map(x => logoOf(c(x)));
        })()""", [None] * 4)
        selector_check("OpenCode and Unity require exact process evidence", """(() => {
          const c = (cmd, cmdline = cmd) => ({name_source:'process', family:'unknown',
            service_id:null, cmd, cmdline});
          return [logoOf(c('opencode')), logoOf(c('OpenCode')), logoOf(c('opencode-helper')),
                  logoOf(c('Unity', '/Applications/Unity/Hub/Editor/2022.3/Unity.app/Contents/MacOS/Unity -projectPath /tmp/game')),
                  logoOf(c('Unity', 'Unity -adb2 AssetImportWorker -projectPath /tmp/game')),
                  logoOf(c('Unity', 'Unity -projectPath /tmp/game')),
                  logoOf(c('Unity Hub', '/Applications/Unity/Hub/Editor/2022.3/Unity.app/Contents/MacOS/Unity'))];
        })()""", ["opencode", None, None, "unity", "unity", None, None])
        selector_check("Mailpit, Wyoming and exporter use generic emblems", """(() => {
          const c = image => ({name_source:'container', family:'unknown', service_id:null,
            container_image:image, container_service:null});
          return [emblemOf(c('axllent/mailpit:latest')),
                  emblemOf(c('rhasspy/wyoming-piper:1')),
                  emblemOf(c('ghcr.io/other/node-exporter:v1')),
                  emblemOf(c('ghcr.io/other/mailpit:v1'))];
        })()""", ["mail", "waves", "chart", "gear"])

        def type_(cmd):
            pg.fill("#in", cmd)
            pg.press("#in", "Enter")
            time.sleep(0.4)

        start = harbour("[...W.buildings.values()].filter(b => b.s && b.s.port === 8787).length")
        for c in ("lsof -i :8787", "portlist 8787", "portlist 8787 --short", "portlist --list --leftovers", "kill 4412", "portlist"):
            type_(c)
        # the program itself: the recorded screens, after the stop
        scr = lambda: pg.inner_text("#scr")
        check("the program opens on Services, with every view in the bar",
              "PORTLIST" in scr() and all(v in scr() for v in ("0 Dashboard", "5 Agents", "7 Sessions", "9 Graph")))
        check("a stopped service is gone from the program's views", ":8787" not in scr())
        pg.keyboard.press("5")
        check("the agents view counts MCP servers that hold no port", "stdio MCP" in scr())
        pg.keyboard.press("7")
        check("the sessions view lists transcripts", "WHAT IT WAS ABOUT" in scr() and "open right now" in scr())
        pg.keyboard.press("Shift+V")
        check("V opens the ambient screen", "P O R T L I S T" in scr())
        pg.keyboard.press("x")
        pg.keyboard.press("4")
        pg.keyboard.press("q")
        pg.wait_for_function("() => document.querySelector('#harbour').contentWindow.eval(\"[...W.buildings.values()].filter(b => b.s && b.s.port === 8787 && !b.leaving).length\") === 0", timeout=15000)
        out = pg.inner_text("#out")
        check("the answer names who started it and the chain", "a Claude Code session (exited)" in out and "launchd (pid 1)" in out)
        check("lsof only says who holds the port", "python3" in out and "(LISTEN)" in out)
        check("the tutorial reaches its end", pg.evaluate("() => tour.step") == 6, str(pg.evaluate("() => tour.step")))
        check("a stopped process's building comes down", start == 1)

        # life around the services: a beat passes, a container starts, a third submarine surfaces
        pg.wait_for_function("() => S.beat >= 1", timeout=20000)
        pg.wait_for_function("() => document.querySelector('#harbour').contentWindow.eval('W.subs ? W.subs.size : 0') >= 3", timeout=15000)
        check("MCP servers surface as submarines, and the loop moves on", True)

        pg.evaluate("() => pick('web1')")
        # the frame reloads for the new machine: until its page is up there is nothing to ask
        pg.wait_for_function("() => { try { return document.querySelector('#harbour').contentWindow.eval('W.buildings.size') > 0 } catch (e) { return false } }", timeout=20000)
        type_("kill 1200")
        type_("echo $?")
        out = pg.inner_text("#out")
        check("another user's process needs sudo", "Operation not permitted" in out and out.strip().endswith("1"))
        type_("portlist 4444 --warnings")
        out = pg.inner_text("#out")
        check("the odd listener is explained with its warnings", "LD_PRELOAD" in out and "reachable from beyond this machine" in out)
        type_("sudo kill 1200")
        check("sudo stops it", pg.evaluate("() => S.killed.has(1200)"))
        # portlist kill: the card, the right way to stop, the question
        type_("portlist kill 5432")
        out = pg.inner_text("#out")
        check("kill names the systemd unit and needs sudo for another user's process",
              "systemctl stop postgresql.service" in out and "sudo portlist kill 5432" in out and not pg.evaluate("() => S.killed.has(900)"))
        type_("portlist kill 8080")
        type_("y")
        check("a PM2 app stopped by pid comes straight back, and says who restarted it",
              "came back as pid" in pg.inner_text("#out") and not pg.evaluate("() => S.killed.has(2310)"))

        pg.evaluate("() => pick('devbox')")
        pg.wait_for_function("() => { try { return document.querySelector('#harbour').contentWindow.eval('W.buildings.size') > 0 } catch (e) { return false } }", timeout=20000)
        type_("portlist cleanup --dry-run")
        out = pg.inner_text("#out")
        check("cleanup lists the leftover with its evidence and stops nothing",
              "1 listener looks left over" in out and "never seen in use" in out and "nothing was stopped" in out and not pg.evaluate("() => S.killed.size"))
        type_("portlist kill 5432")
        check("kill waits for an answer, naming docker stop for a container", pg.inner_text("#prompt").strip().startswith("Stop it (docker stop shop-db-1)"))
        type_("n")
        check("n keeps it", not pg.evaluate("() => S.killed.has(2211)") and "kept" in pg.inner_text("#out"))
        type_("portlist cleanup")
        type_("y")
        check("cleanup stops what you say yes to", pg.evaluate("() => S.killed.has(4412)") and "stopped 1 (:8787)" in pg.inner_text("#out"))
        type_("portlist report --redact")
        href = pg.get_attribute("#out a[href*='report-devbox']", "href")
        rp = b.new_page()
        rp.goto(base + href)
        body = rp.inner_text("body")
        check("the redacted report opens and gives nothing away", "this-machine" in body and "storefront" not in body and "devbox" not in body, href)
        rp.close()
        b.close()
    srv.shutdown()
    check("no console errors", not errors, "; ".join(errors[:3]))
    print("ALL PASS" if not fails else "%d FAILED" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

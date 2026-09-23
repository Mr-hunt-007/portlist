#!/usr/bin/env python3
"""Check the living harbour in a real browser, against a scripted machine.

    python3 tools/worldcheck/run.py            # needs: pip install playwright
                                               #        python -m playwright install chromium

The page is served by the real worldserve, but the model under it comes from a
script instead of this machine, so every path is exercised on every run:

  0-15 s    a harbour with an exposed database, SSH coming in, an SSH island and
            a MongoDB island, three outbound hosts, two containers, an agent
            that has exited and one still working
  15 s      a burst: six more outbound hosts at once, and a new dev server
  90 s      most traffic closes, a container stops, the dev server and the SSH
            session go away

While it runs, a sampler in the page watches every frame: vehicles overlapping,
jumping or leaving the road; boats on land, piers, the moored ship, the crane
berth or the lighthouse rocks; pets in the water. At the end it checks the
world matches the last snapshot, every entity kind opens an inspector, the
props do not stand in a lane, and the console is clean. Exit status 0 is a pass.
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from plcore import world, worldserve   # noqa: E402

DURATION = float(os.environ.get("WORLDCHECK_SECONDS", "170"))
T0 = time.time()


# ------------------------------------------------------------------ the scripted machine
def row(port, pid, **kw):
    r = {
        "id": "%d-%d" % (port, pid), "port": port, "pid": pid, "cmd": "node",
        "cmdline": "node server.js %d" % port, "dir": "/work/app%d" % port, "dir_short": "~/app",
        "service": "Node / Express", "service_id": "express", "service_cat": "App server",
        "exposure": {"level": "loopback", "addrs": ["127.0.0.1"]},
        "activity": {"known": True, "ever_busy": True, "idle_seconds": 30, "watched_for": 9000},
        "conns": 0, "conns_public": 0, "health": "up", "risk": 0, "risk_band": "Info",
        "reasons": [], "leftover": {"likely": False}, "quiet": False,
        "starter": {"kind": "shell", "name": "a shell", "class": "terminal", "pid": 9},
        "origin": {"live": {"kind": "shell", "name": "a shell", "class": "terminal"},
                   "carries_context": True, "matched": "signature"},
        "depends_on": [], "used_by": [], "url": "http://localhost:%d" % port,
    }
    r.update(kw)
    return r


def exposed():
    return {"level": "all", "label": "All interfaces", "addrs": ["*"],
            "verified": {"ip": "192.168.1.5", "iface": "en0", "accepting": True}}


def host(i, app):
    return {"key": "198.51.100.%d" % i, "address": "198.51.100.%d" % i, "alias": None,
            "apps": [app], "services": ["HTTPS"], "ports": [443], "scope": "public", "count": 1}


def island(name, kind, service, logo, port):
    return {"target": name, "kind": kind, "service": service, "logo": logo, "raddr": "203.0.113.%d" % port,
            "rport": port, "scope": "public", "count": 1, "pids": [700 + port], "client": "ssh" if kind == "ssh" else "mongosh",
            "in_fleet": False, "scan_command": None}


def scripted(t):
    phase = 0 if t < 15 else 1 if t < 90 else 2
    rows = [
        row(3000, 11, conns=4),
        row(5432, 12, service="PostgreSQL", service_id="postgres", service_cat="Database", exposure=exposed(),
            risk=72, risk_band="High", cmdline="postgres -D /var/pg"),
        row(22, 13, service="SSH", service_id="ssh", cmdline="sshd", cmd="sshd"),
        row(8080, 14, service="Bun", service_id="bun", cmd="bun"),
        row(5000, 15, service="AirPlay Receiver", service_id="airplay", quiet=True, cmdline="ControlCenter"),
    ]
    if phase == 1:
        rows.append(row(5173, 16, service="Vite dev server", service_id="vite", cmdline="node vite"))
    groups = [
        {"key": "claude-code:-", "name": "a Claude Code session", "class": "AI agent", "kind": "claude-code",
         "ai": True, "alive": False, "pid": None, "services": [{"id": "8080-14"}], "ports": [8080]},
        {"key": "cursor:77", "name": "Cursor", "class": "AI editor", "kind": "cursor",
         "ai": True, "alive": True, "pid": 77, "services": [{"id": "3000-11"}], "ports": [3000]},
    ]
    traffic = [host(1, "Google Chrome"), host(2, "Python"), host(3, "Code")]
    if phase == 1:
        traffic += [host(10 + i, a) for i, a in enumerate(["Google Chrome", "Docker", "claude.exe", "Slack", "Python", "MongoDB Compass"])]
    if phase == 2:
        traffic = traffic[:2]
    isl = [island("db1.example", "db", "MongoDB", "mongodb", 27017)]
    if phase < 2:
        isl.insert(0, island("box.example", "ssh", "SSH", None, 22))
    conns = [{"direction": "inbound", "lport": 22, "raddr": "203.0.113.9", "rport": 50001, "scope": "public", "pid": 13}]
    containers = {"engine": "docker", "reachable": True, "note": "", "containers": [
        {"id": "a1", "name": "shop-db-1", "image": "postgres:16", "state": "running", "status": "Up 2 hours",
         "project": "shop", "service": "db", "ports": [{"host_port": 5432}]},
        {"id": "a2", "name": "shop-cache-1", "image": "redis:7", "state": "running" if phase < 2 else "exited",
         "status": "Up 2 hours" if phase < 2 else "Exited (0)", "project": "shop", "service": "cache", "ports": []},
    ]}
    sysinfo = {"hostname": "harbour-test.local", "os": {"pretty": "Test OS"}, "uptime": 86400,
               "cpu": {"load_pct": 35.0, "model": "Test CPU", "cores": 8, "load": [2.0, 1.8, 1.5]},
               "memory": {"pct": 61.0, "used": 10 << 30, "total": 16 << 30},
               "disks": [{"mount": "/", "pct": 55.0, "free": 100 << 30, "total": 250 << 30}],
               "processes": {"count": 400}, "network": {"interfaces": []}}
    hostinfo = {"hostname": "harbour-test.local", "lan": [{"ip": "192.168.1.5"}],
                "firewall": {"enabled": True, "name": "Firewall", "stealth": False}}
    return world.build(rows, hostinfo, groups, containers, {"sessions": []}, sysinfo, [],
                       outbound=isl, conns=conns, traffic=traffic)


_differ = world.Differ()


def payload(since=0, **_):
    snap = scripted(time.time() - T0)
    _differ.feed(snap)
    doc = dict(snap)
    doc["events"] = _differ.since(since)
    doc["seq"] = _differ.seq
    doc["pets"] = world.plan_pets(snap, _differ.events[-40:])
    doc["chatter"] = world.chatter(doc["pets"], snap)
    doc["history"] = []
    doc["stdio_mcp"] = []
    return doc


world.payload = payload


# ------------------------------------------------------------------ the page-side sampler
SAMPLER = r"""
(() => {
  const R = window.__wc = { overlaps: [], teleports: [], offRoad: [], grounded: [], petsWet: 0, frames: 0 };
  const last = new Map();
  (function f() {
    R.frames++;
    const g = W.geo;
    if (g) {
      const onSurface = p => (p[0] >= g.gateX - 0.2 && p[0] <= g.W + 0.2 && p[1] >= 0 && p[1] <= g.roadY0 + 1.9)
        || (p[0] >= -0.2 && p[0] <= g.W + 30 && p[1] >= g.RN - 2.2 && p[1] <= g.RS + 2.2);
      const mv = [...W.cars.values()].filter(c => c.stage === 'arriving' || c.stage === 'leaving').concat(W.trucks, W.visitors);
      for (let i = 0; i < mv.length; i++) for (let j = i + 1; j < mv.length; j++) {
        const a = mv[i].pos, b = mv[j].pos;
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 0.45) R.overlaps.push([a.map(v => +v.toFixed(1)), b.map(v => +v.toFixed(1))]);
      }
      for (const c of W.cars.values()) {
        if (c.stage === 'queued') { last.delete(c.key); continue; }
        const q = last.get(c.key);
        if (q && Math.hypot(c.pos[0] - q[0], c.pos[1] - q[1]) > 0.3) R.teleports.push(c.key);
        last.set(c.key, c.pos.slice());
        if (!onSurface(c.pos)) R.offRoad.push(c.pos.map(v => +v.toFixed(1)));
      }
      const hc = [g.head.gx + 0.75, g.head.gy + 0.75];
      for (const b of W.boats.values()) {
        if (b.stage === 'home' || !b.stage) continue;
        const p = boatPos(b);
        for (let i = 0; i < g.cols; i++) if (p[0] > 1 + i * 5 - 0.35 && p[0] < 3.2 + i * 5 + 0.35 && p[1] > -6.6 && p[1] < 0.2) R.grounded.push(b.key + ' pier');
        if (p[0] > 3.1 && p[0] < 5.2 && p[1] > -7.6 && p[1] < -1.4) R.grounded.push(b.key + ' ship');
        if (Math.hypot(p[0] - hc[0], p[1] - hc[1]) < 3) R.grounded.push(b.key + ' rocks');
        if (p[0] >= 0 && p[0] <= g.W && p[1] >= 0 && p[1] <= g.H) R.grounded.push(b.key + ' land');
      }
      for (const p of W.pets.values()) if (!(p.pos[0] >= -0.2 && p.pos[0] <= g.W + 0.2 && p.pos[1] >= -0.2 && p.pos[1] <= g.H + 0.2)) R.petsWet++;
    }
    requestAnimationFrame(f);
  })();
})();
"""

FINAL = r"""
(() => {
  const d = W.snap, out = {};
  out.buildings = [...W.buildings.values()].filter(b => !b.leaving).length;
  out.services = d.services.filter(s => !s.system && s.family !== 'ssh').length;
  out.carsSettled = [...W.cars.values()].every(c => c.stage === 'parked');
  out.cars = [...W.cars.values()].filter(c => c.stage !== 'leaving').length;
  out.traffic = Math.min(d.traffic.length, lotGeo().cap);
  out.islands = [...W.boats.values()].filter(b => !b.leaving).length;
  out.islandsWant = d.islands.length;
  out.lighthouse = d.lighthouse.state;
  out.gateOpen = W.gate.boom > 0.5;
  out.crates = [...W.crates.values()].filter(k => !k.leaving).length;
  out.dormant = leftBehind().length;
  out.layout = layoutCheck();
  const kinds = {}; for (const h of HITS) if (!kinds[h.kind]) kinds[h.kind] = h;
  out.inspectors = {};
  for (const k of ['building', 'gate', 'ship', 'office', 'customs', 'lighthouse', 'pet', 'boat', 'car', 'container', 'toll', 'signal', 'dormant']) {
    if (!kinds[k]) { out.inspectors[k] = 'no hit area'; continue; }
    openInspector(kinds[k]);
    const t = document.querySelector('#insp .ttl');
    out.inspectors[k] = document.querySelector('#insp').classList.contains('on') && t && t.textContent ? 'ok' : 'blank';
  }
  closeInspector();
  return out;
})()
"""


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && python -m playwright install chromium")
        return 2
    srv, url = worldserve.serve(0, keep_fresh=False)
    errors, fails = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(url)
        page.wait_for_function("() => typeof W !== \"undefined\" && W.snap && W.geo", timeout=20000)
        page.evaluate("() => { try { welcomed(); } catch (e) {} fit(false); }")
        page.evaluate(SAMPLER)
        while time.time() - T0 < DURATION:
            time.sleep(5)
            print("  %3ds" % (time.time() - T0), end="\r", flush=True)
        # the last phase must have settled: give traffic its time, then read the world
        page.wait_for_function("() => [...W.cars.values()].every(c => c.stage === 'parked')", timeout=60000)
        wc = page.evaluate("() => window.__wc")
        fin = page.evaluate(FINAL)
        browser.close()
    srv.shutdown()

    def check(name, ok, info=""):
        print(("PASS " if ok else "FAIL ") + name + (("  (" + info + ")") if info else ""))
        if not ok:
            fails.append(name)

    print()
    check("no vehicles overlapping", not wc["overlaps"], "%d samples %s" % (len(wc["overlaps"]), wc["overlaps"][:2]))
    check("no vehicle jumps", not wc["teleports"], ",".join(sorted(set(wc["teleports"]))[:3]))
    check("vehicles stay on the road", not wc["offRoad"], str(wc["offRoad"][:2]))
    check("boats stay in open water", not wc["grounded"], ",".join(sorted(set(wc["grounded"]))))
    check("pets stay on land", wc["petsWet"] == 0, str(wc["petsWet"]))
    check("one building per service", fin["buildings"] == fin["services"], "%d vs %d" % (fin["buildings"], fin["services"]))
    check("traffic settled and matches", fin["carsSettled"] and fin["cars"] == fin["traffic"], "%d cars, %d hosts" % (fin["cars"], fin["traffic"]))
    check("islands match sessions", fin["islands"] == fin["islandsWant"], "%d vs %d" % (fin["islands"], fin["islandsWant"]))
    check("lighthouse guiding for inbound ssh", fin["lighthouse"] == "guiding")
    check("gate open for a reachable service", fin["gateOpen"])
    check("one running crate per running container", fin["crates"] >= 1, str(fin["crates"]))
    check("robot left behind by the exited agent", fin["dormant"] == 1, str(fin["dormant"]))
    check("props clear of lanes, bays and each other", not fin["layout"], str(fin["layout"]))
    bad = {k: v for k, v in fin["inspectors"].items() if v != "ok"}
    check("every entity kind opens an inspector", not bad, json.dumps(bad))
    check("no console errors", not errors, "; ".join(errors[:3]))
    print("\n%d frames sampled. %s" % (wc["frames"], "ALL PASS" if not fails else "%d FAILED" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

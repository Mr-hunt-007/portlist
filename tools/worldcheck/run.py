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
    # the rest go by sea: mail throughout, a push line while busy
    traffic.append(dict(host(40, "Notes"), services=["IMAPS"], ports=[993], kind="mailboat"))
    if phase == 1:
        traffic.append(dict(host(41, "Google Chrome"), services=["Google push"], ports=[5228], kind="fishing"))
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


FLEET = [{"id": "web-1", "name": "web-1", "status": "online", "ports": 6, "exposed": 1, "os": "Ubuntu 24.04", "address": "10.0.0.5"},
         {"id": "old-box", "name": "old-box", "status": "gone", "age": 90000, "ports": 3, "exposed": 0, "os": None, "address": None}]


def past_payload(at):
    # the past as history would give it: just two listeners, nothing else recorded
    rows = [world._past_row({"port": 3000, "pid": 11, "service": "Node / Express", "exposure": "loopback"}),
            world._past_row({"port": 5432, "pid": 12, "service": "PostgreSQL", "exposure": "all"})]
    snap = world.build(rows, {}, [], {"engine": None, "reachable": False, "containers": []}, {}, {}, [], now=at)
    doc = dict(snap)
    doc.update(past={"at": at, "oldest": T0 - 3600, "before_history": False, "note": "Reconstructed."},
               events=[], seq=_differ.seq, pets=world.plan_pets(snap, [], now=at), chatter=[], history=[], fleet=FLEET)
    return doc


def timeline():
    return [{"ts": T0 - 3000, "type": "opened", "port": 3000, "text": "x"}, {"ts": T0 - 600, "type": "closed", "port": 9000, "text": "y"}]


def payload(since=0, **_):
    snap = scripted(time.time() - T0)
    snap["fleet"] = FLEET
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
world.past_payload = past_payload
world.timeline = timeline


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
  out.traffic = Math.min(d.traffic.filter(isCar).length, lotGeo().cap);
  out.vessels = [...W.vessels.values()].filter(v => v.stage !== 'out').length;
  out.vesselsWant = d.traffic.filter(e => !isCar(e)).length;
  out.vesselKinds = [...W.vessels.values()].map(v => v.e.kind).sort().join(',');
  out.islands = [...W.boats.values()].filter(b => !b.leaving).length;
  out.islandsWant = d.islands.length;
  out.lighthouse = d.lighthouse.state;
  out.gateOpen = W.gate.boom > 0.5;
  out.crates = [...W.crates.values()].filter(k => !k.leaving).length;
  out.dormant = leftBehind().length;
  out.layout = layoutCheck();
  out.a11y = document.querySelectorAll('#a11yList button').length;
  out.a11yWant = out.buildings + 5 + out.islands + (d.fleet || []).length;
  const kinds = {}; for (const h of HITS) if (!kinds[h.kind]) kinds[h.kind] = h;
  out.inspectors = {};
  for (const k of ['building', 'gate', 'ship', 'office', 'customs', 'lighthouse', 'pet', 'boat', 'car', 'container', 'toll', 'signal', 'dormant', 'fleet']) {
    if (!kinds[k]) { out.inspectors[k] = 'no hit area'; continue; }
    openInspector(kinds[k]);
    const t = document.querySelector('#insp .ttl');
    out.inspectors[k] = document.querySelector('#insp').classList.contains('on') && t && t.textContent ? 'ok' : 'blank';
  }
  closeInspector();
  return out;
})()
"""


def stop_check(page):
    """Stopping from the harbour, against a throwaway server this run starts:
    refused without confirmation and cross-origin, refused for a pid that is not
    on that port, and done when all is right."""
    import socket
    import subprocess
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    js = """async ([pid, port, confirmed]) => { const r = await fetch('/api/world/stop', { method: 'POST',
      headers: { [HEADER]: TOKEN, 'Content-Type': 'application/json' }, body: JSON.stringify({ pid, port, confirmed }) });
      return r.status; }"""
    out = {"unconfirmed": page.evaluate(js, [proc.pid, port, False]),
           "wrong_port": page.evaluate(js, [proc.pid, port + 1 if port < 65535 else port - 1, True])}
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request("http://" + page.url.split("//", 1)[1].split("/", 1)[0] + "/api/world/stop", method="POST",
                                     data=json.dumps({"pid": proc.pid, "port": port, "confirmed": True}).encode(),
                                     headers={"X-Portlist-Token": page.evaluate("TOKEN"), "Origin": "http://evil.example"})
        urllib.request.urlopen(req, timeout=10)
        out["cross_origin"] = 200
    except urllib.error.HTTPError as e:
        out["cross_origin"] = e.code
    out["stopped"] = page.evaluate(js, [proc.pid, port, True])
    try:
        proc.wait(timeout=8)
        out["exited"] = True
    except subprocess.TimeoutExpired:
        proc.kill()
        out["exited"] = False
    return out


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
        # replay: scrub back, the past harbour replaces the present; Live brings it back
        page.evaluate("() => openScrub(true)")
        page.wait_for_function("() => (W.timeline || []).length > 0", timeout=10000)
        page.evaluate("() => { const sl = document.querySelector('#scrubRange'); const at = +sl.min + 60; sl.value = at; scrubTo(at); }")
        page.wait_for_function("() => W.past && [...W.buildings.values()].filter(b => !b.leaving).length === 2", timeout=15000)
        replay = page.evaluate("() => ({ chip: document.querySelector('#liveT').textContent, banner: document.querySelector('#banner').classList.contains('on'), cars: W.cars.size })")
        page.evaluate("() => openScrub(false)")
        page.wait_for_function("() => !W.past && [...W.buildings.values()].filter(b => !b.leaving).length === " + str(fin["buildings"]), timeout=15000)
        # the newer pieces: spotlight, load weather, the beam holding an arriving ship, sound, a picture
        extra = page.evaluate("""async () => {
          const frames = n => new Promise(r => { let k = 0; const f = () => ++k >= n ? r() : requestAnimationFrame(f); requestAnimationFrame(f); });
          const o = {};
          const hb = HITS.find(h => h.kind === 'building'); openInspector(hb); await frames(40);
          o.spot = W.spot > 0.6 && !!W.spotAt; closeInspector();
          const keep = HIST.cpu.slice(); HIST.cpu.push(96, 97, 95, 98, 96, 97); await frames(240); o.rain = W.rain > 0.5 && W.storm;
          HIST.cpu.length = 0; keep.forEach(v => HIST.cpu.push(v)); HIST.cpu.push(5, 6, 4, 5, 6, 5); await frames(30); o.clears = !W.storm;
          const v = [...W.visitShips.values()][0]; if (v) { v.t = 0.1; await frames(20); o.beam = W.beamLock === true; } else o.beam = 'no ship';
          document.querySelector('#oGame').click(); o.gameOn = W.cfg.drama && W.cfg.sound;
          document.querySelector('#oGame').click(); o.gameOff = !W.cfg.drama && !W.cfg.sound;
          W.cfg.sound = true; audioSync(); sfx('thud'); sfx('start'); sfx('purr'); sfx('horn'); sfx('thunder'); o.sound = !!AU.ctx; W.cfg.sound = false; audioSync();
          // the sandbox, with drama on: every simulation lands, is labelled, and Live takes it all back
          const nb = () => [...W.buildings.values()].filter(b => !b.leaving).length, b0 = nb();
          W.cfg.drama = true;
          simulate('collide'); await frames(30);
          o.simCollide = nb() === b0 + 1 && W.sandbox && document.querySelector('#banner').classList.contains('sim') && document.querySelector('#liveT').textContent === 'sandbox';
          o.brawl = W.t - (W.brawlAt || -9) < 0.5;
          simulate('expose'); await frames(20); o.simExpose = W.snap.gate.state === 'open';
          simulate('ghost'); await frames(20); o.toolbox = HITS.some(h => h.kind === 'dormant') && (W.bossGone || []).length > 0;
          simulate('convoy'); await frames(20); o.convoy = [...W.crates.values()].filter(k => k.c && k.c.status === 'simulated').length === 3;
          simulate('storm'); await frames(10); o.simStorm = W.storm === true;
          simulate('memory'); await frames(5); o.simMemory = W.snap.ship.mem_pct === 92;
          W.train = null; simulate('train'); await frames(5); o.simTrain = !!W.train;
          simulate('boats'); await frames(10); o.simBoats = [...W.vessels.values()].filter(v => v.key.startsWith('sim-boat-')).length === 5;
          const c = W.snap.services.find(s => s.sim); settle(c.pid, c.port); await frames(10);
          o.settled = !W.snap.services.some(s => s.pid === c.pid);
          await new Promise(r => setTimeout(r, 9000)); await frames(5);
          o.bossLine = W.chat.some(x => /Boss went home/.test(x.line)) || (W.bossGone || []).length === 0;
          sandboxOff();
          for (let i = 0; i < 100 && (W.sandbox || W.snap.services.some(s => s.sim) || (W.snap.yard.containers || []).some(k => k.status === 'simulated')); i++) await new Promise(r => setTimeout(r, 200));
          o.back = !W.sandbox && !W.snap.services.some(s => s.sim) && !document.querySelector('#banner').classList.contains('sim') && !(W.snap.traffic || []).some(e => String(e.key).startsWith('sim-boat-'));
          W.cfg.drama = false;
          // the coal carrier: half a bunker brings it in, the excavator loads it, it sails on lower in the water
          W.bulker = null; W.digger = null; W.coal = 0.6; const bstages = new Set(); let bload = 0, digs = new Set();
          const bUntil = performance.now() + 200000;
          while (performance.now() < bUntil && !(bstages.has('out') && !W.bulker)) {
            await frames(2);
            if (W.bulker) { bstages.add(W.bulker.stage); bload = Math.max(bload, W.bulker.load); }
            if (W.digger) digs.add(W.digger.phase);
          }
          o.bulker = ['in', 'load', 'out'].every(k => bstages.has(k)) && bload > 0.3 && ['dig', 'swing', 'dump'].every(k => digs.has(k)) && !W.bulker;
          o.bulkerInfo = [...bstages].join('>') + ' load ' + bload.toFixed(2) + ' digger ' + [...digs].join(',');
          // the coal train: a download starts it; it comes in, tips its wagons and backs out
          const real = sync; sync = d => { d.ship.net_rx = 600000; real(d); }; W.snap.ship.net_rx = 600000; W.trainWait = 0;
          const stages = new Set(); let maxV = 0, lastX = null, jump = 0;
          const until = performance.now() + 120000;
          while (performance.now() < until && !(stages.has('out') && !W.train)) {
            await frames(2);
            if (W.digger && W.digger.mode === 'trim' && ['dig', 'carry', 'dump'].includes(W.digger.phase)) o.trimmed = true;
            if (W.train) { stages.add(W.train.stage); maxV = Math.max(maxV, W.train.v); if (lastX != null) jump = Math.max(jump, Math.abs(W.train.x - lastX)); lastX = W.train.x; o.wagons = W.train.n; }
          }
          sync = real;
          o.train = ['in', 'tip', 'out'].every(k => stages.has(k)) && !W.train && maxV <= 3.21 && jump < 0.3 && W.coal > 0;
          o.trainInfo = [...stages].join('>') + ' v' + maxV.toFixed(2) + ' jump' + jump.toFixed(3) + ' wagons ' + o.wagons;
          return o;
        }""")
        n0 = len(errors)
        stopcheck = stop_check(page)
        # the refusals it asks for on purpose show up as failed loads; nothing else is excused
        errors[n0:] = [e for e in errors[n0:] if "Failed to load resource" not in e]
        with page.expect_download(timeout=15000) as dl:
            page.evaluate("() => snapshot()")
        pic = dl.value
        pic_path = os.path.join(os.environ.get("WORLDCHECK_OUT", "/tmp"), pic.suggested_filename)
        pic.save_as(pic_path)
        with open(pic_path, "rb") as fh:
            head = fh.read(24)
        extra["picture"] = head[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(head[16:20], "big") > 400
        extra["pictureName"] = pic.suggested_filename
        extra["captureOff"] = page.evaluate("() => W.capture === false")
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
    check("replay shows the past and labels it", replay["chip"] == "replay" and replay["banner"] and replay["cars"] == 0, json.dumps(replay))
    check("Live returns to the present", True)
    check("keyboard list covers the harbour", fin["a11y"] >= fin["a11yWant"], "%d buttons, want %d" % (fin["a11y"], fin["a11yWant"]))
    check("clicking something puts it in the spotlight", extra["spot"] is True)
    check("sustained CPU brings rain, and it clears", extra["rain"] is True and extra["clears"] is True, json.dumps(extra))
    check("the lighthouse holds an arriving ssh ship", extra["beam"] is True, str(extra["beam"]))
    check("sound starts and stops without errors", extra["sound"] is True)
    check("game mode turns drama and sound on together, and off", extra["gameOn"] is True and extra["gameOff"] is True)
    check("sandbox: a port collision lands, labelled", extra["simCollide"] is True)
    check("drama: the collision starts a brawl", extra["brawl"] is True)
    check("sandbox: exposure opens the gate", extra["simExpose"] is True)
    check("sandbox: ghosting leaves tools and a cat on the way", extra["toolbox"] is True and extra["bossLine"] is True)
    check("sandbox: a convoy brings three containers", extra["convoy"] is True)
    check("sandbox: settling a shared port stops one side", extra["settled"] is True)
    check("sandbox: storm, full memory, a download and boats all show", extra["simStorm"] is True and extra["simMemory"] is True and extra["simTrain"] is True and extra["simBoats"] is True,
          json.dumps({k: extra[k] for k in ("simStorm", "simMemory", "simTrain", "simBoats")}))
    check("Back to live removes every simulated thing", extra["back"] is True)
    check("the excavator works when the train tips", extra.get("trimmed") is True)
    check("coal train comes in, tips and backs out", extra["train"] is True, extra["trainInfo"])
    check("outbound by sea: vessels match their connections", fin["vessels"] == fin["vesselsWant"] and "mailboat" in fin["vesselKinds"], "%d vs %d (%s)" % (fin["vessels"], fin["vesselsWant"], fin["vesselKinds"]))
    check("coal carrier comes in, is loaded by the excavator, sails on", extra["bulker"] is True, extra["bulkerInfo"])
    check("stop refuses without confirmation, off-port and cross-origin",
          stopcheck["unconfirmed"] == 400 and stopcheck["wrong_port"] == 409 and stopcheck["cross_origin"] == 403, json.dumps(stopcheck))
    check("stop from the harbour ends a real process", stopcheck["stopped"] == 200 and stopcheck["exited"], json.dumps(stopcheck))
    check("a picture downloads as a PNG", extra["picture"] and extra["captureOff"], extra["pictureName"])
    check("no console errors", not errors, "; ".join(errors[:3]))
    print("\n%d frames sampled. %s" % (wc["frames"], "ALL PASS" if not fails else "%d FAILED" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

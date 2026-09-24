window.__b2 = 'running';
(() => {
  polling = true;
  const snap = JSON.parse(JSON.stringify(W.snap)), N = 6, keys = [];
  for (let i = 0; i < N; i++) { keys.push('burst-' + i); snap.traffic.push({ key: 'burst-' + i, address: '198.51.100.' + i, apps: ['Google Chrome'], services: ['HTTPS'], ports: [443], scope: 'public', count: 1 }); }
  syncCars(snap);
  const R = { overlaps: 0, teleports: 0, maxJump: 0, stalls: 0, offRoad: 0 }, last = new Map(), still = new Map();
  const t0 = performance.now(); let tp = t0, step = 0;
  const L = lotGeo(), g = W.geo;
  const onSurface = p => (p[0] >= g.gateX && p[0] <= g.W && p[1] >= 0 && p[1] <= g.roadY0 + 1.8) || (p[0] >= 0 && p[0] <= g.W + 30 && p[1] >= g.RN - 1.8 && p[1] <= g.RS + 1.8);
  (function f() {
    const now = performance.now(), dt = Math.min(0.05, (now - tp) / 1000); tp = now;
    const mv = [...W.cars.values()].filter(c => c.stage === 'arriving' || c.stage === 'leaving');
    for (let i = 0; i < mv.length; i++) for (let j = i + 1; j < mv.length; j++) if (Math.hypot(mv[i].pos[0] - mv[j].pos[0], mv[i].pos[1] - mv[j].pos[1]) < 0.45) { R.overlaps++; (R.where = R.where || []).push(mv[i].stage[0] + mv[j].stage[0] + "@" + mv[i].pos.map(v => v.toFixed(1)) + "/" + mv[j].pos.map(v => v.toFixed(1))); }
    for (const c of W.cars.values()) {
      if (c.stage === 'queued') continue;
      const q = last.get(c.key);
      if (q) { const d = Math.hypot(c.pos[0] - q[0], c.pos[1] - q[1]); R.maxJump = Math.max(R.maxJump, d); if (d > 0.25) R.teleports++; }
      last.set(c.key, c.pos.slice());
      if (!onSurface(c.pos)) R.offRoad++;
      if (c.stage !== 'parked') { const s = (still.get(c.key) || 0) + ((c.v || 0) < 0.02 ? dt : -99); still.set(c.key, Math.max(0, s)); if (s > 8) R.stalls++; }
    }
    if (step === 0 && now - t0 > 10000) { step = 1; R.atClose = [...W.cars.values()].filter(c => keys.slice(0, 3).includes(c.key)).map(c => c.stage).join(','); snap.traffic = snap.traffic.filter(e => !keys.slice(0, 3).includes(e.key)); syncCars(snap); }
    if (step === 1 && now - t0 > 40000) { step = 2; R.parkedAt40 = keys.slice(3).filter(k => W.cars.get(k) && W.cars.get(k).stage === 'parked').length; snap.traffic = snap.traffic.filter(e => !keys.includes(e.key)); syncCars(snap); }
    if (now - t0 < 75000) requestAnimationFrame(f);
    else window.__b2 = JSON.stringify({ closedWhile: R.atClose, parkedAt40: R.parkedAt40 + '/3', stillPresentAtEnd: keys.filter(k => W.cars.has(k)).length, overlaps: R.overlaps, teleports: R.teleports, maxJumpPerFrame: +R.maxJump.toFixed(3), offRoadSamples: R.offRoad, stallsOver8s: R.stalls, where: (R.where || []).slice(0, 5) });
  })();
})();

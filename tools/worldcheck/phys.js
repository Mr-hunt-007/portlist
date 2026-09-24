window.__phys = 'running';
(() => {
  const g = W.geo, hc = [g.head.gx + 0.75, g.head.gy + 0.75];
  const obstacles = [];
  for (let i = 0; i < g.cols; i++) obstacles.push(['pier ' + i, 1 + i * 5 - 0.35, -6.6, 3.2 + i * 5 + 0.35, 0.2]);
  obstacles.push(['moored ship', 3.1, -7.6, 5.2, -1.4], ['crane berth', 8.0, -3.6, 11.1, 0.4], ['land', 0, 0, g.W, g.H]);
  const hitsObstacle = p => { for (const [n, x0, y0, x1, y1] of obstacles) if (p[0] > x0 && p[0] < x1 && p[1] > y0 && p[1] < y1) return n; if (Math.hypot(p[0] - hc[0], p[1] - hc[1]) < 3.0) return 'lighthouse rocks'; return null; };
  const onLand = p => p[0] >= -0.2 && p[0] <= g.W + 0.2 && p[1] >= -0.2 && p[1] <= g.H + 0.2;
  const last = new Map(), R = { boatMax: 0, carMax: 0, truckMax: 0, crash: 0, grounded: [], petsWet: 0, frames: 0, vehiclesClose: 0 };
  const t0 = performance.now(); let tp = t0;
  (function f() {
    const now = performance.now(), dt = (now - tp) / 1000; tp = now; R.frames++;
    for (const b of W.boats.values()) {
      if (b.stage === 'home') continue;
      const p = boatPos(b), k = 'b' + b.key, q = last.get(k);
      if (q && dt > 0) R.boatMax = Math.max(R.boatMax, Math.hypot(p[0] - q[0], p[1] - q[1]) / (W.t - q[2] || dt));
      last.set(k, [p[0], p[1], W.t]);
      const hit = hitsObstacle(p); if (hit) R.grounded.push(b.key + ' in ' + hit);
    }
    const moving = [...W.cars.values()].filter(c => c.stage !== 'parked').map(c => c.pos).concat(W.trucks.map(t => t.pos), W.visitors.map(v => v.pos));
    for (let i = 0; i < moving.length; i++) for (let j = i + 1; j < moving.length; j++) if (Math.hypot(moving[i][0] - moving[j][0], moving[i][1] - moving[j][1]) < 0.5) R.vehiclesClose++;
    for (const c of W.cars.values()) if (c.v != null) R.carMax = Math.max(R.carMax, c.v);
    for (const t of W.trucks) if (t.v != null) R.truckMax = Math.max(R.truckMax, t.v);
    for (const p of W.pets.values()) if (!onLand(p.pos)) R.petsWet++;
    if (now - t0 < 8000) requestAnimationFrame(f);
    else window.__phys = JSON.stringify({ boats: W.boats.size, boatPeak: +R.boatMax.toFixed(2), carPeak: +R.carMax.toFixed(2), truckPeak: +R.truckMax.toFixed(2),
      grounded: [...new Set(R.grounded)], vehicleOverlaps: R.vehiclesClose, petsInWater: R.petsWet, frames: R.frames });
  })();
})();

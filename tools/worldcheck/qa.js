window.__qa = "running"; (async () => {
  const R = [], ok = (name, cond, info) => R.push((cond ? 'PASS ' : 'FAIL ') + name + (info ? '  (' + info + ')' : ''));
  const d = W.snap;
  // truth: the world holds exactly what the snapshot says
  const main = d.services.filter(s => !s.system && !(s.family === 'ssh'));
  ok('one building per service', W.buildings.size === main.length || [...W.buildings.values()].filter(b => !b.leaving).length === main.length, W.buildings.size + ' vs ' + main.length);
  ok('one shed per system service (within capacity)', W.sysB.size <= d.services.filter(s => s.system).length);
  ok('gate boom follows verified reachability', (d.gate.state === 'open') === (W.gate.boom > 0.5 || W.gate.moving), d.gate.state + ' boom ' + W.gate.boom.toFixed(2));
  ok('lighthouse lamp follows ssh server', (d.lighthouse.listening ? 1 : 0) === Math.round(W.lampK));
  ok('one island per ssh or database session', [...W.boats.values()].filter(b => !b.leaving).length === (d.islands || []).length, (d.islands || []).length + ' islands');
  ok('one car per outbound host', [...W.cars.values()].filter(c => c.stage !== 'leaving').length === Math.min((d.traffic || []).length, lotGeo().cap), (d.traffic || []).length + ' hosts');
  ok('lighthouse on for any ssh session', (d.lighthouse.state === 'guiding') === ((d.lighthouse.inbound || []).length + (d.lighthouse.outbound || []).length > 0));
  ok('workers are only live owners', [...W.workers.values()].every(e => e.stage === 'leave' || (e.w && e.w.alive === true)));
  ok('pets have a reason', [...W.pets.values()].every(p => p.task && p.task.trigger && p.task.meaning));
  ok('exposed pill equals gate list', d.stats.exposed === d.gate.reachable.length);
  // interactions
  const kinds = {};
  for (const h of HITS) if (!kinds[h.kind]) kinds[h.kind] = h;
  for (const k of ['building', 'gate', 'ship', 'office', 'customs', 'lighthouse', 'pet', 'boat', 'car', 'cleaner', 'toll', 'signal', 'forklift']) {
    if (!kinds[k]) { ok('clickable ' + k, false, 'no hit area'); continue; }
    openInspector(kinds[k]);
    const t = document.querySelector('#insp .ttl');
    ok('inspector for ' + k, document.querySelector('#insp').classList.contains('on') && t && t.textContent.length > 0, t && t.textContent);
  }
  closeInspector(); ok('inspector closes', !document.querySelector('#insp').classList.contains('on'));
  toggleLegend(true); ok('legend opens', document.querySelector('#legend').classList.contains('on')); toggleLegend(false);
  openSearch(true); document.querySelector('#q').value = String(main[0].port); const hits = runSearch(); ok('search finds a port', hits && hits.length > 0); openSearch(false);
  toggleDrawer(true); ok('attention drawer', document.querySelectorAll('#attnBody .row, #attnBody .empty').length > 0); toggleDrawer(false);
  setScreen(true); ok('ambient mode', document.body.classList.contains('screen')); setScreen(false); setTour(false);
  document.dispatchEvent(new KeyboardEvent('keydown', { key: '?' })); ok('? key', document.querySelector('#legend').classList.contains('on')); toggleLegend(false);
  // overlap: no two drawn signs intersect
  const P = W.signRects || []; let clash = 0;
  for (let i = 0; i < P.length; i++) for (let j = i + 1; j < P.length; j++) { const a = P[i], b = P[j]; if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y) clash++; }
  ok('no overlapping signs', clash === 0, P.length + ' signs, ' + clash + ' overlaps');
  // frame rate over 2s
  const fps = await new Promise(res => { let n = 0; const t0 = performance.now(); (function f() { n++; performance.now() - t0 < 2000 ? requestAnimationFrame(f) : res(n / 2); })(); });
  ok('frame rate', fps >= 30, fps.toFixed(0) + ' fps');
  return R.join('\n');
})().then(r => window.__qa = r, e => window.__qa = "ERROR " + e.stack);

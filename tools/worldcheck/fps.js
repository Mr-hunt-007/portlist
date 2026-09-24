window.__fps = 'running';
(async () => {
  const measure = () => new Promise(res => { let n = 0; const t0 = performance.now(); (function f() { n++; performance.now() - t0 < 2000 ? requestAnimationFrame(f) : res((n / 2).toFixed(0)); })(); });
  const out = [];
  out.push('baseline ' + await measure());
  W.cfg.labels = false; out.push('no signs ' + await measure()); W.cfg.labels = true;
  const oh = window.drawHeadland; window.drawHeadland = () => {}; out.push('no headland ' + await measure()); window.drawHeadland = oh;
  const os = window.drawSky; window.drawSky = () => {}; out.push('no sky ' + await measure()); window.drawSky = os;
  const ow = window.drawWater; window.drawWater = () => {}; out.push('no water ' + await measure()); window.drawWater = ow;
  const og = window.drawGround; window.drawGround = () => {}; out.push('no ground ' + await measure()); window.drawGround = og;
  window.__fps = out.join(' | ');
})();

import Graph from 'graphology';
import Sigma from 'sigma';
import { animateNodes } from 'sigma/utils';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import forceAtlas2 from 'graphology-layout-forceatlas2';

const BG = [14, 20, 32];
function mix(c, a) { // opaque color = c blended over the dark background (WebGL canvas ignores straight alpha)
  let rgb;
  if (c[0] === '#') rgb = [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  else rgb = c.match(/[\d.]+/g).slice(0, 3).map(Number);
  return `rgb(${rgb.map((v, i) => Math.round(BG[i] + (v - BG[i]) * a)).join(',')})`;
}
const D = window.GX_DATA;
const $ = (s) => document.querySelector(s);
const PAL = ['#5ad1e6', '#ff8a5c', '#a78bfa', '#f472b6', '#86efac', '#facc15', '#3b82f6', '#ef4444', '#14b8a6', '#d9f99d', '#fdba74', '#94a3b8'];
const DIM = 'rgb(30,37,50)';
const fmt = (v, d = 2) => (v == null || Number.isNaN(v) ? '–' : (+v).toFixed(d).replace(/\.?0+$/, ''));

function ramp(t) { // dark blue -> cyan -> yellow -> red (turbo-ish)
  const stops = [[0, [40, 60, 140]], [0.35, [40, 190, 220]], [0.65, [250, 210, 60]], [1, [250, 70, 60]]];
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const [a, ca] = stops[i - 1], [b, cb] = stops[i], f = (t - a) / (b - a);
      return `rgb(${ca.map((c, k) => Math.round(c + (cb[k] - c) * f)).join(',')})`;
    }
  }
  return 'rgb(250,70,60)';
}

/* ───────────────────────── Building graph ───────────────────────── */
const B = D.buildings;
const G = new Graph({ type: 'undirected' });
const N = B.nodes.length;
B.nodes.forEach((n, i) => {
  G.addNode(i, { ...n, x: n.ux, y: n.uy, size: 2, color: '#5ad1e6', label: n.a });
});
B.edges.forEach(([s, t, w]) => { if (!G.hasEdge(s, t)) G.addEdge(s, t, { w, size: 0.4 }); });

const state = { color: 'seg', size: 'n', hidden: new Set(), segOff: new Set(), sel: null, hover: null, neigh: null,
  ranges: {}, onlyEarly: false, onlyAnom: false };

const HIST = [
  { k: 'rate', label: 'Incidents / month', log: true },
  { k: 'rep', label: 'Repeat rate (same category ≤ 30 d)' },
  { k: 'close', label: 'Median days to close' },
  { k: 'risk', label: 'Max risk next 30 d (non-heat)' },
];

function colorOf(n) {
  switch (state.color) {
    case 'seg': return PAL[n.seg % PAL.length];
    case 'dom': return PAL[n.dom % PAL.length];
    case 'risk': return ramp(n.risk);
    case 'rep': return ramp(n.rep / 0.8);
    case 'close': return ramp(Math.log1p(n.close) / Math.log1p(60));
    case 'anom': return n.anomR ? '#ff4d4d' : n.anomAll ? '#ffb02e' : 'rgb(40,90,110)';
    case 'early': return n.early ? '#facc15' : 'rgb(35,75,92)';
    default: return '#5ad1e6';
  }
}
function sizeOf(n) {
  if (state.size === 'n') return 1.2 + 1.6 * Math.sqrt(n.n / 10);
  if (state.size === 'risk') return 1 + 9 * n.risk ** 1.5;
  if (state.size === 'anom') return n.anomR ? 7 : n.anomAll ? 3.5 : 1.5;
  return 2.2;
}
function passes(n) {
  if (state.segOff.has(n.seg)) return false;
  if (state.onlyEarly && !n.early) return false;
  if (state.onlyAnom && !n.anomR) return false;
  for (const h of HIST) {
    const r = state.ranges[h.k];
    if (r && (n[h.k] < r[0] || n[h.k] > r[1])) return false;
  }
  const z = $('#zipf').value.trim();
  if (z && !String(n.z).startsWith(z)) return false;
  return true;
}
function recompute() {
  state.hidden.clear();
  G.forEachNode((k, a) => { if (!passes(a)) state.hidden.add(k); });
  $('#count').textContent = `${(N - state.hidden.size).toLocaleString()} / ${N.toLocaleString()} buildings`;
  drawHists();
  renderer.refresh();
}

const renderer = new Sigma(G, $('#gb'), {
  renderEdgeLabels: false, labelColor: { color: '#e6edf3' }, labelSize: 12, labelWeight: '500',
  labelRenderedSizeThreshold: 14, defaultEdgeColor: 'rgb(30,48,68)', zIndex: true,
  minCameraRatio: 0.02, maxCameraRatio: 4, hideEdgesOnMove: false,
  defaultDrawNodeHover: (ctx, d, s) => drawHoverDark(ctx, d, s),
  nodeReducer: (k, a) => {
    const r = { ...a, color: colorOf(a), size: sizeOf(a) };
    if (state.hidden.has(k)) { r.hidden = true; return r; }
    if (state.neigh && !state.neigh.has(k)) { r.color = DIM; r.label = ''; r.zIndex = 0; }
    else if (state.neigh) { r.zIndex = 2; r.size = Math.max(r.size, 4); r.forceLabel = true; }
    if (k === state.sel) { r.highlighted = true; r.size *= 1.6; }
    return r;
  },
  edgeReducer: (e, a) => {
    const [s, t] = G.extremities(e);
    if (state.hidden.has(s) || state.hidden.has(t)) return { ...a, hidden: true };
    if (state.neigh) {
      if (s === state.sel || t === state.sel) return { ...a, color: 'rgb(200,220,235)', size: 1.2, zIndex: 2 };
      return state.layout === 'map' ? { ...a, hidden: true } : { ...a, color: 'rgb(20,26,38)' };
    }
    if (state.layout === 'map') return { ...a, hidden: true };   // similarity edges cut across the borough on the map
    {
    }
    return a;
  },
});

function drawHoverDark(ctx, d, s) {
  const size = s.labelSize, font = s.labelFont;
  ctx.font = `600 ${size}px ${font}`;
  const lines = [d.label || '', d.sub || ''].filter(Boolean);
  const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 14;
  const h = lines.length * (size + 4) + 8;
  ctx.fillStyle = 'rgba(13,17,23,0.92)'; ctx.strokeStyle = 'rgba(90,209,230,0.6)'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.roundRect(d.x + d.size + 4, d.y - h / 2, w, h, 4); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#e6edf3';
  lines.forEach((l, i) => ctx.fillText(l, d.x + d.size + 11, d.y - h / 2 + 4 + (i + 1) * (size + 2)));
}
G.forEachNode((k, a) => G.setNodeAttribute(k, 'sub', `${a.segName} · ${a.n} incidents`));

/* inspector + neighbourhood highlight */
function select(k) {
  state.sel = k;
  if (k == null) { state.neigh = null; $('#insp').classList.remove('on'); renderer.refresh(); return; }
  state.neigh = new Set([k, ...G.neighbors(k)]);
  const n = G.getNodeAttributes(k);
  const cats = n.mix.map(([c, v]) => `<div class="bar"><span>${D.cats[c]}</span><i style="width:${Math.round(v * 100)}%"></i><b>${Math.round(v * 100)}%</b></div>`).join('');
  const nb = G.neighbors(k).slice(0, 8).map((m) => {
    const a = G.getNodeAttributes(m);
    return `<li data-k="${m}">${a.a} <em>${a.z}</em></li>`;
  }).join('');
  $('#insp').innerHTML = `
    <div class="ih"><div><h3>${n.a}</h3><div class="muted">Brooklyn ${n.z} · BBL ${n.id}</div></div><button id="ix">✕</button></div>
    <div class="chip" style="border-color:${PAL[n.seg % PAL.length]}">${n.segName}</div>
    <div class="kv">
      <div><b>${n.n}</b><span>incidents (24 mo)</span></div><div><b>${fmt(n.rate, 1)}</b><span>per month</span></div>
      <div><b>${Math.round(n.rep * 100)}%</b><span>repeat ≤ 30 d</span></div><div><b>${fmt(n.close, 1)}</b><span>median days to close</span></div>
      <div><b>${Math.round(n.risk * 100)}%</b><span>risk next 30 d · ${D.cats[n.riskCat] || '–'}</span></div>
      <div><b>${n.anomAll}</b><span>anomalous weeks${n.anomR ? ' · <em class="hot">recent</em>' : ''}</span></div>
    </div>
    ${n.early ? `<div class="warn">Early warning: ${D.cats[n.earlyCat]} (${Math.round(n.earlyP * 100)}%) although not reported for 90+ days</div>` : ''}
    <h4>Category mix</h4>${cats}
    <h4>Most similar buildings</h4><ul class="nb">${nb}</ul>`;
  $('#insp').classList.add('on');
  $('#ix').onclick = () => select(null);
  $('#insp').querySelectorAll('.nb li').forEach((li) => (li.onclick = () => focus(li.dataset.k)));
  renderer.refresh();
}
function focus(k) {
  select(k);
  const d = renderer.getNodeDisplayData(k);
  if (d) renderer.getCamera().animate({ x: d.x, y: d.y, ratio: 0.12 }, { duration: 600 });
}
renderer.on('clickNode', ({ node }) => select(node));
renderer.on('doubleClickNode', ({ node, event }) => { event.preventSigmaDefault(); focus(node); });
renderer.on('clickStage', () => select(null));

/* layouts */
let fa2 = null;
function stopFA2() { if (fa2) { fa2.kill(); fa2 = null; } $('#fa2').textContent = '▶ Run force layout'; $('#fa2').classList.remove('live'); }
function setLayout(kind) {
  stopFA2(); state.layout = kind; renderer.refresh();
  document.querySelectorAll('[data-layout]').forEach((b) => b.classList.toggle('on', b.dataset.layout === kind));
  const pos = {};
  G.forEachNode((k, a) => {
    if (kind === 'umap') pos[k] = { x: a.ux, y: a.uy };
    else if (kind === 'map') pos[k] = { x: (a.lon + 73.95) * 70, y: (a.lat - 40.65) * 92 };
    else if (kind === 'seg') {
      const cx = Math.cos((a.seg / D.segments.length) * 2 * Math.PI) * 12, cy = Math.sin((a.seg / D.segments.length) * 2 * Math.PI) * 12;
      pos[k] = { x: cx + a.ux * 0.18 + (Math.random() - 0.5), y: cy + a.uy * 0.18 + (Math.random() - 0.5) };
    }
  });
  animateNodes(G, pos, { duration: 900 }, () => renderer.getCamera().animatedReset({ duration: 400 }));
}
document.querySelectorAll('[data-layout]').forEach((b) => (b.onclick = () => setLayout(b.dataset.layout)));
$('#fa2').onclick = () => {
  if (fa2) return stopFA2();
  state.layout = 'force';
  document.querySelectorAll('[data-layout]').forEach((b) => b.classList.remove('on'));
  const settings = forceAtlas2.inferSettings(G);
  fa2 = new FA2Layout(G, { settings: { ...settings, barnesHutOptimize: true, gravity: 0.3, scalingRatio: 4, slowDown: 6, linLogMode: true }, getEdgeWeight: 'w' });
  fa2.start();
  $('#fa2').textContent = '■ Stop force layout'; $('#fa2').classList.add('live');
};

/* encodings */
$('#colorBy').onchange = (e) => { state.color = e.target.value; legend(); renderer.refresh(); };
$('#sizeBy').onchange = (e) => { state.size = e.target.value; renderer.refresh(); };
function legend() {
  const L = $('#legend');
  if (state.color === 'seg' || state.color === 'dom') {
    const items = state.color === 'seg' ? D.segments : D.cats;
    const counts = new Array(items.length).fill(0);
    G.forEachNode((k, a) => counts[state.color === 'seg' ? a.seg : a.dom]++);
    L.innerHTML = items.map((s, i) => counts[i] ? `<div class="li ${state.color === 'seg' && state.segOff.has(i) ? 'off' : ''}" data-i="${i}"><i style="background:${PAL[i % PAL.length]}"></i>${s}<em>${counts[i].toLocaleString()}</em></div>` : '').join('')
      + (state.color === 'seg' ? '<div class="hint">Click a segment to hide / show it</div>' : '');
    if (state.color === 'seg') L.querySelectorAll('.li').forEach((el) => (el.onclick = () => {
      const i = +el.dataset.i; state.segOff.has(i) ? state.segOff.delete(i) : state.segOff.add(i); legend(); recompute();
    }));
  } else if (state.color === 'anom') {
    L.innerHTML = '<div class="li"><i style="background:#ff4d4d"></i>Anomaly in last 8 weeks</div><div class="li"><i style="background:#ffb02e"></i>Anomaly earlier</div><div class="li"><i style="background:#5ad1e6;opacity:.4"></i>No anomaly</div>';
  } else if (state.color === 'early') {
    L.innerHTML = '<div class="li"><i style="background:#facc15"></i>Early-warning candidate</div><div class="li"><i style="background:#5ad1e6;opacity:.4"></i>Other</div>';
  } else {
    const lab = { risk: ['0%', '100% risk'], rep: ['0%', '≥ 80% repeat'], close: ['0 d', '60+ d to close'] }[state.color];
    L.innerHTML = `<div class="grad"></div><div class="gl"><span>${lab[0]}</span><span>${lab[1]}</span></div>`;
  }
}

/* histogram filters (Graphistry-style) */
const hEls = {};
function buildHists() {
  const wrap = $('#hists');
  HIST.forEach((h) => {
    const vals = []; G.forEachNode((k, a) => vals.push(a[h.k]));
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const div = document.createElement('div'); div.className = 'hist';
    div.innerHTML = `<div class="ht"><span>${h.label}</span><em></em></div><canvas width="260" height="46"></canvas>
      <div class="rr"><input type="range" min="0" max="1000" value="0"><input type="range" min="0" max="1000" value="1000"></div>`;
    wrap.appendChild(div);
    const tf = (v) => (h.log ? Math.log1p(v) : v), itf = (u) => (h.log ? Math.expm1(u) : u);
    const a = tf(lo), b = tf(hi);
    const [r0, r1] = div.querySelectorAll('input');
    const upd = () => {
      let x0 = +r0.value, x1 = +r1.value; if (x0 > x1) [x0, x1] = [x1, x0];
      const v0 = itf(a + (b - a) * x0 / 1000), v1 = itf(a + (b - a) * x1 / 1000);
      state.ranges[h.k] = (x0 === 0 && x1 === 1000) ? null : [v0 - 1e-9, v1 + 1e-9];
      div.querySelector('em').textContent = state.ranges[h.k] ? `${fmt(v0, 2)} – ${fmt(v1, 2)}` : 'all';
      recompute();
    };
    r0.oninput = upd; r1.oninput = upd;
    hEls[h.k] = { cv: div.querySelector('canvas'), a, b, tf, em: div.querySelector('em'), r0, r1 };
    div.querySelector('em').textContent = 'all';
  });
}
function drawHists() {
  const BINS = 40;
  HIST.forEach((h) => {
    const e = hEls[h.k]; if (!e) return;
    const all = new Array(BINS).fill(0), vis = new Array(BINS).fill(0);
    G.forEachNode((k, n) => {
      const i = Math.min(BINS - 1, Math.floor((e.tf(n[h.k]) - e.a) / (e.b - e.a + 1e-12) * BINS));
      all[i]++; if (!state.hidden.has(k)) vis[i]++;
    });
    const ctx = e.cv.getContext('2d'), W = e.cv.width, H = e.cv.height, mx = Math.max(...all.map((v) => Math.sqrt(v)));
    ctx.clearRect(0, 0, W, H);
    const bw = W / BINS;
    all.forEach((v, i) => {
      const hA = Math.sqrt(v) / mx * (H - 2), hV = Math.sqrt(vis[i]) / mx * (H - 2);
      ctx.fillStyle = 'rgba(140,150,170,0.25)'; ctx.fillRect(i * bw + 0.5, H - hA, bw - 1, hA);
      ctx.fillStyle = '#5ad1e6'; ctx.fillRect(i * bw + 0.5, H - hV, bw - 1, hV);
    });
  });
}
$('#onlyEarly').onchange = (e) => { state.onlyEarly = e.target.checked; recompute(); };
$('#onlyAnom').onchange = (e) => { state.onlyAnom = e.target.checked; recompute(); };
$('#zipf').oninput = () => recompute();
$('#reset').onclick = () => {
  state.segOff.clear(); state.onlyEarly = state.onlyAnom = false; $('#onlyEarly').checked = $('#onlyAnom').checked = false; $('#zipf').value = '';
  Object.values(hEls).forEach((e) => { e.r0.value = 0; e.r1.value = 1000; e.em.textContent = 'all'; });
  state.ranges = {}; legend(); select(null); recompute();
};

/* search */
const dl = $('#addrs');
const byAddr = new Map();
G.forEachNode((k, a) => { const s = `${a.a} · ${a.z}`; byAddr.set(s, k); });
dl.innerHTML = [...byAddr.keys()].sort().map((s) => `<option value="${s}">`).join('');
$('#search').onchange = (e) => { const k = byAddr.get(e.target.value); if (k != null) focus(k); };

/* hover */
renderer.on('enterNode', () => ($('#gb').style.cursor = 'pointer'));
renderer.on('leaveNode', () => ($('#gb').style.cursor = 'default'));

/* zoom buttons */
$('#zin').onclick = () => renderer.getCamera().animatedZoom({ duration: 300 });
$('#zout').onclick = () => renderer.getCamera().animatedUnzoom({ duration: 300 });
$('#zfit').onclick = () => renderer.getCamera().animatedReset({ duration: 300 });

/* ───────────────────────── Failure-chain graph ───────────────────────── */
const C = D.chains;
const H = new Graph({ type: 'directed' });
C.nodes.forEach((n) => H.addNode(n.id, { ...n, x: n.x, y: n.y, size: 4 + 16 * Math.sqrt(n.vol / C.maxVol), label: n.id, color: PAL[n.comm % PAL.length] }));
C.edges.forEach((e, i) => H.addDirectedEdgeWithKey(i, e.s, e.t, { lift: e.lift, pairs: e.pairs, raw: e.raw, type: 'arrow' }));
const cs = { minLift: 1.5, minPairs: 100, metric: 'lift', sel: null };
let r2 = null;
function chainRenderer() {
  if (r2) return;
  r2 = new Sigma(H, $('#gc'), {
    renderEdgeLabels: false, labelColor: { color: '#e6edf3' }, labelSize: 12, labelRenderedSizeThreshold: 0,
    defaultDrawNodeHover: (ctx, d, s) => drawHoverDark(ctx, d, s), zIndex: true,
    nodeReducer: (k, a) => {
      const r = { ...a };
      if (cs.sel && cs.sel !== k && !H.hasEdge(cs.sel, k) && !H.hasEdge(k, cs.sel)) { r.color = DIM; r.label = ''; }
      return r;
    },
    edgeReducer: (e, a) => {
      const v = cs.metric === 'lift' ? a.lift : a.raw;
      if (v < cs.minLift || a.pairs < cs.minPairs) return { ...a, hidden: true };
      const [s, t] = H.extremities(e);
      const on = cs.sel && (s === cs.sel || t === cs.sel);
      const al = cs.sel ? (on ? 0.9 : 0.04) : Math.min(0.85, 0.15 + (v - 1) / 3);
      return { ...a, size: 0.6 + 2.2 * Math.min(1, (v - 1) / 3), color: on && t === cs.sel ? mix('#ff8a5c', al) : mix('#5ad1e6', al), zIndex: on ? 2 : 1 };
    },
  });
  H.forEachNode((k, a) => H.setNodeAttribute(k, 'sub', `${a.vol.toLocaleString()} incidents · community ${a.comm + 1}`));
  r2.on('clickNode', ({ node }) => { cs.sel = node; chainInfo(); r2.refresh(); });
  r2.on('clickStage', () => { cs.sel = null; chainInfo(); r2.refresh(); });
  chainCount();
}
function chainCount() {
  let k = 0; H.forEachEdge((e, a) => { const v = cs.metric === 'lift' ? a.lift : a.raw; if (v >= cs.minLift && a.pairs >= cs.minPairs) k++; });
  $('#ccount').textContent = `${k} edges shown`;
}
function chainInfo() {
  const el = $('#cinfo');
  if (!cs.sel) { el.innerHTML = '<div class="hint">Click a category to list what tends to follow it (cyan) and what precedes it (orange).</div>'; return; }
  const key = cs.metric === 'lift' ? 'lift' : 'raw';
  const row = (e, dir) => { const a = H.getEdgeAttributes(e); const o = dir === 'out' ? H.target(e) : H.source(e); return { o, ...a }; };
  const outs = H.outEdges(cs.sel).map((e) => row(e, 'out')).filter((r) => r[key] >= cs.minLift && r.pairs >= cs.minPairs).sort((a, b) => b[key] - a[key]).slice(0, 8);
  const ins = H.inEdges(cs.sel).map((e) => row(e, 'in')).filter((r) => r[key] >= cs.minLift && r.pairs >= cs.minPairs).sort((a, b) => b[key] - a[key]).slice(0, 8);
  const li = (r) => `<li>${r.o}<em>×${fmt(r[key], 2)} · ${r.pairs}</em></li>`;
  el.innerHTML = `<h3>${cs.sel}</h3><h4>Followed within 30 days by</h4><ul class="nb">${outs.map(li).join('') || '<li class="muted">nothing above threshold</li>'}</ul>
    <h4>Preceded by</h4><ul class="nb">${ins.map(li).join('') || '<li class="muted">nothing above threshold</li>'}</ul>`;
}
$('#minLift').oninput = (e) => { cs.minLift = +e.target.value; $('#minLiftV').textContent = cs.minLift.toFixed(1); chainCount(); chainInfo(); r2 && r2.refresh(); };
$('#minPairs').oninput = (e) => { cs.minPairs = +e.target.value; $('#minPairsV').textContent = cs.minPairs; chainCount(); chainInfo(); r2 && r2.refresh(); };
$('#metric').onchange = (e) => { cs.metric = e.target.value; chainCount(); chainInfo(); r2 && r2.refresh(); };

/* tabs */
document.querySelectorAll('[data-tab]').forEach((t) => (t.onclick = () => {
  document.querySelectorAll('[data-tab]').forEach((x) => x.classList.toggle('on', x === t));
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('on', v.id === 'v-' + t.dataset.tab));
  if (t.dataset.tab === 'chains') { chainRenderer(); chainInfo(); r2.refresh(); } else renderer.refresh();
}));

/* boot */
buildHists(); legend(); recompute();
window.__gx = { G, H, renderer, state, select, setLayout };

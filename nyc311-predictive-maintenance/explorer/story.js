// Scroll-driven graph for the NYC 311 story page (index.html).
// Each .step element carries data-state='{"graph":"b",...}'; when it scrolls into view the stage switches to that state.
import Graph from 'graphology';
import Sigma from 'sigma';
import { animateNodes } from 'sigma/utils';

const D = window.GX_DATA;
const $ = (s) => document.querySelector(s);
const PAL = ['#5ad1e6', '#ff8a5c', '#a78bfa', '#f472b6', '#86efac', '#facc15', '#3b82f6', '#ef4444', '#14b8a6', '#d9f99d', '#fdba74', '#94a3b8'];
const BG = [14, 20, 32];
function mix(c, a) { // opaque colour blended over the background (WebGL ignores straight alpha)
  const rgb = c[0] === '#' ? [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16)) : c.match(/[\d.]+/g).slice(0, 3).map(Number);
  return `rgb(${rgb.map((v, i) => Math.round(BG[i] + (v - BG[i]) * a)).join(',')})`;
}
function ramp(t) {
  const st = [[0, [40, 60, 140]], [0.35, [40, 190, 220]], [0.65, [250, 210, 60]], [1, [250, 70, 60]]];
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < st.length; i++) if (t <= st[i][0]) {
    const [a, ca] = st[i - 1], [b, cb] = st[i], f = (t - a) / (b - a);
    return `rgb(${ca.map((c, k) => Math.round(c + (cb[k] - c) * f)).join(',')})`;
  }
  return 'rgb(250,70,60)';
}
const DIM = 'rgb(28,36,50)';
const segIndex = Object.fromEntries(D.segments.map((s, i) => [s, i]));

/* ── state ── */
const S = { graph: 'b', layout: 'umap', color: 'plain', size: 'n', focus: null, metric: 'raw', minLift: 1.5, minPairs: 100, only: null };

/* ── buildings graph ── */
const G = new Graph({ type: 'undirected' });
D.buildings.nodes.forEach((n, i) => G.addNode(i, { ...n, x: n.ux, y: n.uy, size: 2, color: '#5ad1e6', label: n.a,
  sub: `${n.segName} · ${n.n} incidents` }));
D.buildings.edges.forEach(([s, t, w]) => { if (!G.hasEdge(s, t)) G.addEdge(s, t, { w, size: 0.35 }); });

function nodeColor(n) {
  const f = S.focus != null ? segIndex[S.focus] : null;
  switch (S.color) {
    case 'seg': return f == null || n.seg === f ? PAL[n.seg % PAL.length] : DIM;
    case 'anom': return n.anomR ? '#ff4d4d' : n.anomAll ? '#ffb02e' : 'rgb(38,74,92)';
    case 'early': return n.early ? '#facc15' : 'rgb(34,58,78)';
    case 'risk': return ramp(n.risk);
    default: return '#5ad1e6';
  }
}
function nodeSize(n) {
  const f = S.focus != null ? segIndex[S.focus] : null;
  if (S.size === 'anom') return n.anomR ? 6.5 : n.anomAll ? 2.6 : 1.1;
  if (S.size === 'early') return n.early ? 5.5 : 1.1;
  const base = 1 + 1.5 * Math.sqrt(n.n / 10);
  return f != null && n.seg !== f ? base * 0.6 : base;
}
const rb = new Sigma(G, $('#gb'), {
  labelColor: { color: '#e6edf3' }, labelSize: 12, labelRenderedSizeThreshold: 99, defaultEdgeColor: 'rgb(28,44,62)',
  zIndex: true, minCameraRatio: 0.05, maxCameraRatio: 3, defaultDrawNodeHover: hoverBox,
  nodeReducer: (k, a) => {
    if (S.only === 'early' && !a.early) return { ...a, hidden: true };
    if (S.only === 'anomR' && !a.anomR) return { ...a, hidden: true };
    const c = nodeColor(a);
    return { ...a, color: c, size: nodeSize(a), zIndex: c === DIM ? 0 : 1 };
  },
  edgeReducer: (e, a) => {
    if (S.layout === 'map' || S.only) return { ...a, hidden: true };
    if (S.color === 'seg' && S.focus != null) {
      const [s, t] = G.extremities(e), f = segIndex[S.focus];
      if (G.getNodeAttribute(s, 'seg') !== f || G.getNodeAttribute(t, 'seg') !== f) return { ...a, color: 'rgb(20,27,40)' };
      return { ...a, color: mix(PAL[f % PAL.length], 0.25) };
    }
    return a;
  },
});

/* ── chain graph ── */
const H = new Graph({ type: 'directed' });
const C = D.chains;
C.nodes.forEach((n) => H.addNode(n.id, { ...n, size: 4 + 15 * Math.sqrt(n.vol / C.maxVol), label: n.id, color: PAL[n.comm % PAL.length],
  sub: `${n.vol.toLocaleString()} incidents` }));
C.edges.forEach((e, i) => H.addDirectedEdgeWithKey(i, e.s, e.t, { lift: e.lift, raw: e.raw, pairs: e.pairs, type: 'arrow' }));
const WATER = /Leak|Mold|Paint|Damp/;
let rc = null;
function chainRenderer() {
  if (rc) return rc;
  rc = new Sigma(H, $('#gc'), {
    labelColor: { color: '#e6edf3' }, labelSize: 12, labelRenderedSizeThreshold: 0, zIndex: true, defaultDrawNodeHover: hoverBox,
    nodeReducer: (k, a) => {
      if (S.focus === 'water' && !WATER.test(k)) return { ...a, color: DIM, label: '' };
      return a;
    },
    edgeReducer: (e, a) => {
      const v = S.metric === 'raw' ? a.raw : a.lift;
      if (v < S.minLift || a.pairs < S.minPairs) return { ...a, hidden: true };
      const [s, t] = H.extremities(e);
      const water = WATER.test(s) && WATER.test(t);
      const strength = Math.min(1, (v - 1) / 3);
      const col = S.focus === 'water' ? (water ? mix('#ff8a5c', 0.35 + 0.6 * strength) : 'rgb(24,32,46)') : mix('#5ad1e6', 0.2 + 0.7 * strength);
      return { ...a, color: col, size: 0.5 + 2.2 * strength, zIndex: water ? 2 : 1 };
    },
  });
  return rc;
}

function hoverBox(ctx, d, s) {
  const size = s.labelSize;
  ctx.font = `600 ${size}px ${s.labelFont}`;
  const lines = [d.label || '', d.sub || ''].filter(Boolean);
  const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 14, h = lines.length * (size + 4) + 8;
  ctx.fillStyle = 'rgba(13,17,23,0.92)'; ctx.strokeStyle = 'rgba(90,209,230,0.6)'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.roundRect(d.x + d.size + 4, d.y - h / 2, w, h, 4); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#e6edf3';
  lines.forEach((l, i) => ctx.fillText(l, d.x + d.size + 11, d.y - h / 2 + 4 + (i + 1) * (size + 2)));
}

/* ── legend ── */
function legend() {
  const L = $('#legend');
  let html = '';
  if (S.graph === 'c') {
    html = S.metric === 'raw'
      ? '<b>Raw lift</b> · compared with the borough average'
      : '<b>Timing lift</b> · compared with the same building’s own rate';
    if (S.focus === 'water') html += '<br><i style="background:#ff8a5c"></i>leak · mold · damp · paint';
  } else if (S.color === 'seg') {
    html = D.segments.map((s, i) => `<span class="${S.focus && S.focus !== s ? 'off' : ''}"><i style="background:${PAL[i % PAL.length]}"></i>${s}</span>`).join('');
  } else if (S.color === 'anom') {
    html = '<span><i style="background:#ff4d4d"></i>anomaly in the last 8 weeks</span><span><i style="background:#ffb02e"></i>anomaly earlier</span>';
  } else if (S.color === 'early') {
    html = '<span><i style="background:#facc15"></i>early-warning building</span>';
  } else html = '<span><i style="background:#5ad1e6"></i>one dot = one building · lines link the 5 most similar</span>';
  L.innerHTML = html;
}

/* ── apply a state ── */
function layoutPositions(kind) {
  const pos = {};
  G.forEachNode((k, a) => {
    pos[k] = kind === 'map' ? { x: (a.lon + 73.95) * 70, y: (a.lat - 40.65) * 92 } : { x: a.ux, y: a.uy };
  });
  return pos;
}
let current = '';
function apply(st) {
  const key = JSON.stringify(st);
  if (key === current) return;
  current = key;
  const prevLayout = S.layout, prevGraph = S.graph;
  Object.assign(S, { graph: 'b', layout: 'umap', color: 'plain', size: 'n', focus: null, metric: 'raw', minLift: 1.5, minPairs: 100, only: null }, st);
  $('#gb').classList.toggle('on', S.graph === 'b');
  $('#gc').classList.toggle('on', S.graph === 'c');
  if (S.graph === 'c') {
    const r = chainRenderer();
    r.resize(); r.refresh();
    if (prevGraph !== 'c') r.getCamera().animatedReset({ duration: 300 });
  } else {
    rb.resize();
    if (S.layout !== prevLayout) animateNodes(G, layoutPositions(S.layout), { duration: 1000 }, () => rb.getCamera().animatedReset({ duration: 400 }));
    rb.refresh();
  }
  const cnt = $('#stagecount');
  if (S.graph === 'c') {
    let k = 0; H.forEachEdge((e, a) => { if ((S.metric === 'raw' ? a.raw : a.lift) >= S.minLift && a.pairs >= S.minPairs) k++; });
    cnt.textContent = `${k} chains shown`;
  } else {
    let k = 0; G.forEachNode((n, a) => { if (!(S.only === 'early' && !a.early) && !(S.only === 'anomR' && !a.anomR)) k++; });
    cnt.textContent = `${k.toLocaleString()} buildings`;
  }
  legend();
}

/* ── scroll steps ── */
const steps = [...document.querySelectorAll('.step')];
const io = new IntersectionObserver((entries) => {
  entries.forEach((en) => {
    if (en.isIntersecting) {
      steps.forEach((s) => s.classList.toggle('active', s === en.target));
      apply(JSON.parse(en.target.dataset.state || '{}'));
    }
  });
}, { rootMargin: window.innerWidth <= 860 ? '-62% 0px -30% 0px' : '-45% 0px -45% 0px' });
steps.forEach((s) => io.observe(s));
apply(JSON.parse(steps[0].dataset.state || '{}'));

/* ── lazy-load the full explorer in the last chapter ── */
const frame = $('#explorer');
if (frame) {
  const fio = new IntersectionObserver((en) => {
    if (en[0].isIntersecting && !frame.src) { frame.src = frame.dataset.src; fio.disconnect(); }
  }, { rootMargin: '400px' });
  fio.observe(frame);
}
window.__story = { G, H, S, apply };

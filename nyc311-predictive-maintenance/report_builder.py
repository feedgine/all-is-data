"""Assemble the standalone HTML report from plotly figures, tables and key numbers."""
import html
import plotly.io as pio

CSS = """
:root{--bg:#fafaf8;--fg:#1d1d1f;--muted:#6b6b70;--card:#fff;--line:#e5e5e2;--accent:#0f6e6e}
@media (prefers-color-scheme: dark){:root{--bg:#141416;--fg:#ececec;--muted:#a0a0a8;--card:#1d1d20;--line:#2e2e33;--accent:#5cc8c8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
main{max-width:1120px;margin:0 auto;padding:32px 16px 80px}
h1{font-size:28px;margin:0 0 6px}h2{font-size:21px;margin:44px 0 8px;padding-top:12px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:22px 0 6px}.sub{color:var(--muted);margin:0 0 20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:22px}.kpi span{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px;margin:14px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--muted);font-weight:600}td.num{text-align:right;font-variant-numeric:tabular-nums}
.note{border-left:3px solid var(--accent);padding:6px 12px;margin:12px 0;background:var(--card)}
ul{padding-left:20px}li{margin:3px 0}code{font-size:13px}
nav a{color:var(--accent);margin-right:14px;text-decoration:none;font-size:14px}
"""


def _table(df):
    cols = list(df.columns)
    out = ['<table><thead><tr>' + ''.join(f'<th>{html.escape(str(c))}</th>' for c in cols) + '</tr></thead><tbody>']
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            num = isinstance(v, (int, float)) and not isinstance(v, bool)
            txt = f'{v:,.2f}'.rstrip('0').rstrip('.') if isinstance(v, float) else str(v)
            cells.append(f'<td class="{"num" if num else ""}">{html.escape(txt)}</td>')
        out.append('<tr>' + ''.join(cells) + '</tr>')
    out.append('</tbody></table>')
    return '<div class="card">' + ''.join(out) + '</div>'


def build(figs, tables, n, path):
    first = [True]

    def fig(name):
        f = figs[name]
        f.update_layout(template='plotly_white', margin=dict(l=50, r=20, t=60, b=50), font=dict(size=12))
        s = pio.to_html(f, full_html=False, include_plotlyjs='inline' if first[0] else False,
                        config={'displaylogo': False, 'responsive': True})
        first[0] = False
        return f'<div class="card">{s}</div>'

    d, a, c, g, p, e = n['data'], n['anomaly'], n['cluster'], n['graph'], n['predict'], n['predict_early']
    kpi = lambda v, l: f'<div class="kpi"><b>{v}</b><span>{l}</span></div>'
    body = f"""
<h1>Predictive maintenance PoC: NYC 311 housing complaints</h1>
<p class="sub">Public stand-in for property-maintenance tickets · HPD complaints, Brooklyn · {d['start']} → {d['end']}</p>
<nav><a href="#s1">Anomalies</a><a href="#s2">Segments</a><a href="#s3">Failure chains</a><a href="#s4">Predictor</a><a href="#s5">Takeaways</a></nav>
<div class="kpis">
{kpi(f"{d['raw_rows']:,}", '311 complaints')}
{kpi(f"{d['incidents']:,}", 'incidents after merging same-day duplicates')}
{kpi(f"{d['buildings']:,}", 'buildings (BBL)')}
{kpi(f"{p['auc']}", f"predictor ROC-AUC on later hold-out (baseline {p['auc_baseline']})")}
{kpi(f"{p['p_at_1000_model']:.0%}", f"hit rate of top-1,000 flags per month (baseline {p['p_at_1000_baseline']:.0%})")}
</div>
<div class="note"><b>Unit of analysis.</b> Several tenants often report the same boiler outage on the same day. A ticket system would merge those,
so one <b>incident</b> = building × complaint type × day. Building ≈ property; complaint type / descriptor ≈ ticket category.</div>
{fig('overview')}

<h2 id="s1">1 · Building anomaly spikes</h2>
<p>Expected weekly count for each building = its share of incidents over the trailing 26 weeks × the borough total that week.
Seasonality is therefore built in: a building is flagged only when it moves against the borough trend.
A week is flagged when a <b>Poisson tail test</b> (p &lt; 1e-4, ≥ 4 incidents) and an <b>Isolation Forest</b> on
multivariate features (volume, category spread, heat share, ratio to expected, open share) both agree.</p>
<div class="kpis">{kpi(f"{a['active_buildings']:,}", 'buildings with a baseline (≥ 8 incidents)')}{kpi(f"{a['poisson_flags']:,}", 'Poisson flags')}{kpi(f"{a['iso_flags']:,}", 'Isolation Forest flags')}{kpi(f"{a['both']:,}", 'flagged by both')}{kpi(f"{a['both_last8w']}", 'flagged in the last 8 weeks')}</div>
<h3>Strongest anomalies, last 8 weeks</h3>
{_table(tables['anomalies'].rename(columns={'n': 'incidents', 'p': 'p-value', 'ratio': 'actual / expected'}))}
<div class="note">Typical pattern: a building with almost no history suddenly files 10–25 incidents in 4–6 categories in one week.
That looks like a tenant or inspection "sweep" (many issues listed at once) or a change of ownership or management. In a property manager's own ticket data,
the same detector would surface properties where something changed, which is a call-the-property-manager trigger, not a work order.</div>
{fig('anomaly_ts')}{fig('anomaly_count')}{fig('anomaly_map')}

<h2 id="s2">2 · Building segments (unsupervised clustering)</h2>
<p>Profile for each of {c['buildings']:,} buildings with ≥ 10 incidents: volume per month, category mix, 30-day repeat rate,
median days to close, open share, heat-season share, reporters per incident, category spread.
Standardised → PCA (90% variance) → KMeans, with k = {c['k']} picked by silhouette. UMAP is used only for the picture. The silhouette is low ({c['silhouette'][c['k']]}):
buildings form a continuum, so read the segments as useful labels for groups of buildings, not as sharply separated types.</p>
{fig('cluster_umap')}{fig('cluster_heat')}
{_table(tables['segments'])}
<div class="note">Segments a property manager can act on: <b>heat-heavy + repeat failures</b> (boiler or riser problems, a capex candidate),
<b>high volume + broad mix</b> (distressed buildings, the property-manager attention list),
<b>water + paint</b> (leaks leading to plaster damage, where a plumbing inspection is cheaper than repeated repairs), and
<b>slow to close</b> (vendor or process bottleneck, a ~46-day median close).</div>

<h2 id="s3">3 · Failure-chain graph</h2>
<p>Nodes = the 30 most common category : descriptor pairs. Edge A → B when B is filed in the same building 1–30 days after A.
<b>Lift</b> compares that with a building-level null: B happening at the same building's own average rate, at random times.
This removes the "busy buildings have lots of everything" effect, so an edge means <i>timing</i>, not just co-location.
Kept: lift ≥ 1.5, ≥ 100 pairs, top 3 outgoing per node → {g['nodes']} nodes, {g['edges']} edges, {g['communities']} Louvain communities.</p>
{fig('graph')}
{_table(tables['chains'].rename(columns={'node_a': 'A (first)', 'node_b': 'B (follows within 30 d)'}))}
<div class="note"><b>Finding.</b> Real sequential chains are mostly electrical (outage → no lighting → lighting), gas/appliance
(cooking gas ↔ range, i.e. a gas shut-off followed by range work) and heat → radiator. The intuitive <i>leak → mold → paint</i> chain
has a raw lift of ~4, but nearly all of it is co-location (the same buildings have all three), not sequence within 30 days.
It shows up in the <i>water + paint</i> segment instead. Without the building-level null, the graph would overstate "predictive" chains.</div>

<h2 id="s4">4 · Repeat-failure predictor (next 30 days)</h2>
<p>Monthly snapshots; one row per (building, category) for every building active in the prior 180 days.
Features: recency and frequency of the category (30/90/180 days), days since the last one, building-wide activity,
related-category signals (leak, plumbing, unsanitary, heat in the last 60 days), and season. Model: gradient-boosted trees.
<b>Train</b> on snapshots May 2025 – Mar 2026, <b>test</b> on May – Sep 2026 ({p['test_rows']:,} rows, {p['test_pos_rate']:.1%} positive).</p>
<div class="kpis">{kpi(p['auc'], f"ROC-AUC (baseline rule {p['auc_baseline']})")}{kpi(p['ap'], f"average precision (baseline {p['ap_baseline']}; random {p['test_pos_rate']:.3f})")}{kpi(f"{p['p_at_1000_model']:.0%}", f"top-1,000/month hit rate (baseline {p['p_at_1000_baseline']:.0%})")}{kpi(e['auc'], f"ROC-AUC on 'not seen in 90 days' rows")}{kpi(f"{e['p_at_500']:.0%}", f"early-warning top-500 hit rate (random {e['pos_rate']:.1%})")}</div>
<p>Baseline = "recent problems recur" (90-day count). The model beats it on every metric. The early-warning slice, where the category
has not been reported for 90+ days, is harder, but its top-500 list is still ~{e['p_at_500'] / e['pos_rate']:.0f}× better than random.</p>
{fig('predict_deciles')}{fig('predict_imp')}
<h3>Per category (hold-out)</h3>{_table(tables['per_cat'])}
<h3>Live watch list: highest risk for the next 30 days (from {d['end']}, excluding heat)</h3>
{_table(tables['watch'].rename(columns={'p': 'P(next 30 d)', 'n90': 'last 90 d', 'days_since': 'days since last'}))}
<h3>Early-warning list: high risk, but the category was not reported in the last 90 days</h3>
{_table(tables['early'].rename(columns={'p': 'P(next 30 d)', 'days_since': 'days since last', 'b_n90': 'building incidents 90 d', 'b_water60': 'leaks 60 d', 'b_plumbing60': 'plumbing 60 d'}))}
<h3>Heat / hot water (validation is summer-only, so treat these with care)</h3>{_table(tables['heat_watch'].rename(columns={'p': 'P(next 30 d)', 'n90': 'last 90 d', 'days_since': 'days since last'}))}

<h2 id="s5">5 · Takeaways for property-maintenance teams</h2>
<ul>
<li><b>Ticket basics are enough.</b> Building + category + created/closed timestamps power all four techniques. No sensors or IoT needed to start.</li>
<li><b>More than a hotspot list.</b> A ranked list of problem buildings is the baseline here. The model adds ~{(p['p_at_1000_model'] - p['p_at_1000_baseline']) * 100:.0f} points
of hit rate on the top-1,000 and, more importantly, an early-warning list that a hotspot view cannot produce.</li>
<li><b>Own ticket data is richer than 311:</b> unit IDs, vendor, cost, free-text descriptions (an LLM can extract the asset, e.g. "boiler" or "riser").
Expect stronger, asset-level chains and cost-weighted prioritisation.</li>
<li><b>Control for "busy buildings".</b> Without a building-level null model, co-occurrence graphs overstate predictive chains (see section 3).</li>
<li><b>Caveats.</b> 311 is tenant-reported and regulator-facing, not an operator's ticket log. Duplicates and inspection sweeps inflate spikes.
Validation covers one summer only. Heat needs a winter hold-out.</li>
</ul>
<p class="sub">Generated from <code>NYC311_predictive_maintenance.ipynb</code> · data: NYC Open Data, dataset erm2-nwe9 · part of <b>all-is-data</b>.</p>
"""
    page = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' \
           f'<title>NYC 311 Predictive Maintenance</title><style>{CSS}</style></head><body><main>{body}</main></body></html>'
    open(path, 'w').write(page)

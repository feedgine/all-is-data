# %% [markdown]
# # Predictive maintenance PoC on NYC 311 (HPD, Brooklyn)
# NYC 311 housing complaints (HPD, Brooklyn, 2024-11-01 → 2026-10-27) used as a public stand-in
# for property-maintenance tickets. One building (BBL) ≈ one property; complaint type/descriptor ≈ ticket category.
#
# Four techniques:
# 1. **Building anomaly spikes**: seasonality-aware Poisson baseline + Isolation Forest
# 2. **Building clustering**: behavioural profile per building → PCA → KMeans, UMAP for display
# 3. **Graph co-occurrence**: "B follows A within 30 days in the same building", with lift → Louvain communities
# 4. **Repeat-failure predictor**: P(building files category X in the next 30 days), time-split validation

# %%
import json, warnings
import numpy as np, pandas as pd
import networkx as nx
import plotly.express as px, plotly.graph_objects as go
from scipy.stats import poisson
from sklearn.ensemble import IsolationForest, HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, roc_auc_score, average_precision_score
import umap
warnings.filterwarnings('ignore')
RNG = 42
OUT = 'docs'
import os; os.makedirs(OUT, exist_ok=True); os.makedirs('build', exist_ok=True)
FIGS = {}   # name -> plotly fig, collected for the HTML report
NOTES = {}  # name -> dict/str of key numbers for the report

# %% [markdown]
# ## 0. Load and build "incidents"
# Raw 311 rows include many duplicates: several tenants report the same boiler outage on the same day.
# A maintenance ticket system would merge those, so the unit here is **one incident = building × complaint type × day**.

# %%
raw = pd.read_csv('data/nyc311_hpd_brooklyn.csv', dtype={'bbl': str, 'incident_zip': str},
                  parse_dates=['created_date', 'closed_date'])
raw['complaint_type'] = raw.complaint_type.str.upper()
raw = raw.dropna(subset=['bbl'])
raw['day'] = raw.created_date.dt.floor('D')
raw['days_to_close'] = (raw.closed_date - raw.created_date).dt.total_seconds() / 86400
grp = raw.groupby(['bbl', 'complaint_type', 'day'])
inc = grp.agg(created=('created_date', 'min'), descriptor=('descriptor', 'first'),
              reports=('unique_key', 'size'), days_to_close=('days_to_close', 'median'),
              is_open=('status', lambda s: (s != 'Closed').any())).reset_index()
addr = raw.groupby('bbl').agg(address=('incident_address', lambda s: s.mode().iat[0]),
                              zip=('incident_zip', 'first'), lat=('latitude', 'median'), lon=('longitude', 'median'))
END = raw.created_date.max().normalize()
START = raw.created_date.min().normalize()
NOTES['data'] = dict(raw_rows=len(raw), incidents=len(inc), buildings=inc.bbl.nunique(),
                     start=str(START.date()), end=str(END.date()))
print(NOTES['data'])

# %%
wk_total = inc.set_index('day').resample('W-MON', label='left', closed='left').size()
fig = go.Figure()
for ct in inc.complaint_type.value_counts().index[:8]:
    s = inc[inc.complaint_type == ct].set_index('day').resample('W-MON', label='left', closed='left').size()
    fig.add_scatter(x=s.index, y=s.values, name=ct.title(), mode='lines', stackgroup='one')
fig.update_layout(title='Weekly incidents by category (top 8): heat dominates Oct–May',
                  yaxis_title='incidents / week', height=420, legend=dict(orientation='h', y=-0.2))
FIGS['overview'] = fig

# %% [markdown]
# ## 1. Building anomaly spikes
# **Baseline:** expected building-week count = building's share of all incidents over the trailing 26 weeks
# × the borough's total that week. That way, seasonality (heat season) is built into the expectation, so
# a building is flagged only when it moves *against* the borough trend.
# **Score:** Poisson upper-tail p-value. **Second opinion:** Isolation Forest on multivariate
# building-week features (count, distinct categories, heat share, ratio to expected, open share).
# We report spikes where both agree.

# %%
inc['week'] = inc.day.dt.to_period('W-SUN').dt.start_time
weeks = pd.Index(sorted(inc.week.unique()), name='week')
bw = inc.groupby(['bbl', 'week']).agg(n=('reports', 'size'), n_types=('complaint_type', 'nunique'),
                                      heat=('complaint_type', lambda s: (s == 'HEAT/HOT WATER').mean()),
                                      open_share=('is_open', 'mean'), reports=('reports', 'sum')).reset_index()
active = bw.groupby('bbl').n.sum()
active = active[active >= 8].index          # buildings with enough history to have a baseline
M = bw[bw.bbl.isin(active)].pivot(index='bbl', columns='week', values='n').reindex(columns=weeks).fillna(0)
tot = M.sum(0)                              # borough-week total (of active buildings)
trail = M.T.rolling(26, min_periods=8).sum().shift(1).T          # trailing 26w, excluding current week
trail_tot = tot.rolling(26, min_periods=8).sum().shift(1)
share = (trail + 0.5) / (trail_tot.values + 0.5 * len(M))       # smoothed share
expected = share * tot.values
pval = pd.DataFrame(poisson.sf(M.values - 1, expected.values), index=M.index, columns=M.columns)
ratio = (M + 0.5) / (expected + 0.5)

long = (M.stack().rename('n').to_frame()
        .join(expected.stack().rename('expected')).join(pval.stack().rename('p'))
        .join(ratio.stack().rename('ratio')).reset_index())
long = long.dropna(subset=['expected'])
long = long.merge(bw[['bbl', 'week', 'n_types', 'heat', 'open_share', 'reports']], on=['bbl', 'week'], how='left').fillna(0)
nz = long[long.n > 0].copy()
X = np.column_stack([np.log1p(nz.n), nz.n_types, nz.heat, np.log(nz.ratio), nz.open_share, np.log1p(nz.reports)])
iso = IsolationForest(n_estimators=300, contamination=0.01, random_state=RNG).fit(X)
nz['iso_score'] = -iso.score_samples(X)
nz['iso_flag'] = iso.predict(X) == -1
nz['poisson_flag'] = (nz.p < 1e-4) & (nz.n >= 4)
nz['anomaly'] = nz.iso_flag & nz.poisson_flag
nz = nz.merge(addr, left_on='bbl', right_index=True, how='left')
NOTES['anomaly'] = dict(building_weeks=len(long), active_buildings=len(M), poisson_flags=int(nz.poisson_flag.sum()),
                        iso_flags=int(nz.iso_flag.sum()), both=int(nz.anomaly.sum()),
                        both_last8w=int(nz[nz.week >= weeks[-8]].anomaly.sum()))
print(NOTES['anomaly'])

# %%
recent = (nz[(nz.week >= weeks[-8]) & nz.anomaly].sort_values('p').drop_duplicates('bbl').head(15))
# what drove each spike (top categories that week)
def drivers(r):
    s = inc[(inc.bbl == r.bbl) & (inc.week == r.week)].complaint_type.value_counts().head(3)
    return ', '.join(f'{k.title()} ×{v}' for k, v in s.items())
recent['drivers'] = recent.apply(drivers, axis=1)
anom_table = recent[['address', 'zip', 'week', 'n', 'expected', 'ratio', 'p', 'drivers']].copy()
anom_table['week'] = anom_table.week.dt.date.astype(str)
anom_table[['expected', 'ratio']] = anom_table[['expected', 'ratio']].round(1)
anom_table['p'] = anom_table.p.map(lambda v: f'{v:.1e}')
anom_table

# %%
top3 = recent.bbl.head(3).tolist()
fig = go.Figure()
for b in top3:
    fig.add_scatter(x=weeks, y=M.loc[b].values, name=f'{addr.address[b]} actual', mode='lines')
    fig.add_scatter(x=weeks, y=expected.loc[b].values, name=f'{addr.address[b]} expected',
                    mode='lines', line=dict(dash='dot'))
    fl = nz[(nz.bbl == b) & nz.anomaly]
    fig.add_scatter(x=fl.week, y=fl.n, mode='markers', marker=dict(size=11, symbol='x'),
                    name=f'{addr.address[b]} anomaly', showlegend=False)
fig.update_layout(title='Top recent anomalies: actual vs seasonal expected (× = flagged week)',
                  yaxis_title='incidents / week', height=440, legend=dict(orientation='h', y=-0.25))
FIGS['anomaly_ts'] = fig

ap = nz[nz.anomaly].groupby('week').size().reindex(weeks, fill_value=0)
fig = go.Figure(go.Bar(x=ap.index, y=ap.values))
fig.update_layout(title='Flagged building-weeks over time (both detectors agree)', yaxis_title='buildings', height=300)
FIGS['anomaly_count'] = fig

fig = px.scatter_map(nz[nz.anomaly].drop_duplicates('bbl'), lat='lat', lon='lon', color=np.log10(nz[nz.anomaly].drop_duplicates('bbl').ratio),
                        hover_name='address', hover_data={'n': True, 'week': True}, zoom=10.3, height=480,
                        color_continuous_scale='OrRd', labels={'color': 'log10 ratio'})
fig.update_layout(map_style='carto-positron', title='Where anomalies happen (any time in the 24 months)', margin=dict(t=40, l=0, r=0, b=0))
FIGS['anomaly_map'] = fig

# %% [markdown]
# ## 2. Building clustering
# Profile for each building with ≥10 incidents: volume, category mix, repeat rate (same category again
# within 30 days), median days to close, still-open share, seasonality (share in heat season), category spread.

# %%
inc = inc.sort_values(['bbl', 'complaint_type', 'day'])
inc['gap'] = inc.groupby(['bbl', 'complaint_type']).day.diff().dt.days
inc['repeat30'] = inc.gap.le(30)
months = (END - START).days / 30.4
bstat = inc.groupby('bbl').agg(n=('day', 'size'), repeat30=('repeat30', 'mean'),
                               close_days=('days_to_close', 'median'), open_share=('is_open', 'mean'),
                               winter=('day', lambda d: d.dt.month.isin([10, 11, 12, 1, 2, 3, 4, 5]).mean()),
                               reports_per_inc=('reports', 'mean'))
mix = pd.crosstab(inc.bbl, inc.complaint_type, normalize='index')
mix = mix.loc[:, inc.complaint_type.value_counts().index[:11]]
mix.columns = ['mix_' + c.split('/')[0].split(' ')[0].lower() for c in mix.columns]
bstat['n_types'] = inc.groupby('bbl').complaint_type.nunique()
prof = bstat.join(mix)
prof = prof[prof.n >= 10].copy()
prof['rate_pm'] = prof.n / months
prof['close_days'] = prof.close_days.fillna(prof.close_days.median()).clip(upper=120)
feat = prof.drop(columns=['n']).copy()
feat['rate_pm'] = np.log1p(feat.rate_pm)
feat['reports_per_inc'] = np.log(feat.reports_per_inc)
Z = StandardScaler().fit_transform(feat)
P = PCA(n_components=0.9, random_state=RNG).fit_transform(Z)
sil = {}
for k in range(4, 11):
    lab = KMeans(k, n_init=10, random_state=RNG).fit_predict(P)
    sil[k] = silhouette_score(P, lab, sample_size=5000, random_state=RNG)
K = max(sil, key=sil.get)
if K < 5:   # prefer an interpretable 5–8 segment cut when silhouettes are close
    alt = {k: v for k, v in sil.items() if 5 <= k <= 8}
    kb = max(alt, key=alt.get)
    if sil[K] - alt[kb] < 0.02: K = kb
prof['cluster'] = KMeans(K, n_init=20, random_state=RNG).fit_predict(P)
emb = umap.UMAP(n_neighbors=30, min_dist=0.15, random_state=RNG).fit_transform(Z)
prof['u1'], prof['u2'] = emb[:, 0], emb[:, 1]
NOTES['cluster'] = dict(buildings=len(prof), k=K, silhouette={k: round(v, 3) for k, v in sil.items()})
print(NOTES['cluster'])

# %%
# auto-name clusters by their most distinctive features (z-score of cluster mean vs all)
zdf = pd.DataFrame(Z, index=prof.index, columns=feat.columns)
cz = zdf.groupby(prof.cluster).mean()
pretty = {'rate_pm': 'high volume', 'repeat30': 'repeat failures', 'close_days': 'slow to close',
          'open_share': 'many open', 'winter': 'heat-season', 'reports_per_inc': 'many tenants per issue',
          'n_types': 'broad mix'}
def name(c):
    s = cz.loc[c].sort_values(ascending=False)
    parts = []
    for f, v in s.head(2).items():
        if v < 0.4: continue
        parts.append(pretty.get(f, f.replace('mix_', '') + '-heavy'))
    if not parts:
        low = cz.loc[c].sort_values().index[0]
        parts = ['low ' + pretty.get(low, low.replace('mix_', '')).replace('high ', '')]
    return ' + '.join(parts)
cnames = {c: f'C{c}: {name(c)}' for c in cz.index}
prof['segment'] = prof.cluster.map(cnames)
summary = prof.groupby('segment').agg(buildings=('n', 'size'), incidents_per_month=('rate_pm', 'median'),
                                      repeat30=('repeat30', 'mean'), close_days=('close_days', 'median'),
                                      heat_mix=('mix_heat', 'mean'), leak_mix=('mix_water', 'mean'),
                                      pests_mix=('mix_unsanitary', 'mean')).round(2).sort_values('buildings', ascending=False)
summary

# %%
pp = prof.join(addr)
fig = px.scatter(pp.sample(min(len(pp), 9000), random_state=RNG), x='u1', y='u2', color='segment',
                 hover_name='address', hover_data={'n': True, 'repeat30': ':.2f', 'u1': False, 'u2': False},
                 opacity=0.6, height=560, title='Building segments (UMAP projection of behaviour profile)')
fig.update_traces(marker=dict(size=4))
fig.update_layout(legend=dict(orientation='h', y=-0.15), xaxis_visible=False, yaxis_visible=False)
FIGS['cluster_umap'] = fig
hm = cz.copy(); hm.index = [cnames[c] for c in hm.index]
hm.columns = [pretty.get(c, c.replace('mix_', 'mix: ')) for c in hm.columns]
fig = px.imshow(hm.round(2), color_continuous_scale='RdBu_r', zmin=-2, zmax=2, aspect='auto',
                title='Segment fingerprints (z-score vs all buildings)', height=420)
FIGS['cluster_heat'] = fig

# %% [markdown]
# ## 3. Graph co-occurrence: failure chains
# Nodes = complaint type : descriptor (top 30). Directed edge A→B when, in the same building, B is filed
# 1–30 days after A. Edge weight = **lift** = observed pairs / pairs expected if B occurred at that same
# building's own average rate, at random times. Keep lift ≥ 1.5, ≥ 100 pairs, top 3 outgoing per node. Communities = Louvain.

# %%
inc['node'] = inc.complaint_type.str.title() + ': ' + inc.descriptor.str.title()
top_nodes = inc.node.value_counts().index[:30]
ev = inc[inc.node.isin(top_nodes)][['bbl', 'day', 'node']].drop_duplicates()
ev = ev.sort_values(['bbl', 'day'])
pairs = ev.merge(ev, on='bbl', suffixes=('_a', '_b'))
pairs = pairs[(pairs.day_b > pairs.day_a) & (pairs.day_b <= pairs.day_a + pd.Timedelta(days=30)) & (pairs.node_a != pairs.node_b)]
pairs = pairs.drop_duplicates(['bbl', 'day_a', 'node_a', 'node_b'])
obs = pairs.groupby(['node_a', 'node_b']).size().rename('pairs')
# Building-conditioned null: in building b, B occurs at its own average rate spread uniformly over time.
# Expected pairs(A→B) = Σ_b  #A_b × P(≥1 B in a 30-day window | b's B rate). This removes the
# "busy buildings have lots of everything" effect, so lift measures *timing* (B follows A), not co-location.
span = (END - START).days
C = pd.crosstab(ev.bbl, ev.node)
R = 1 - np.exp(-C / span * 30)
EXP = pd.DataFrame(C.values.T @ R.values, index=C.columns, columns=C.columns)
E = obs.reset_index()
E['expected'] = EXP.values[EXP.index.get_indexer(E.node_a), EXP.columns.get_indexer(E.node_b)]
E['lift'] = E.pairs / E.expected
cand = E[(E.lift >= 1.5) & (E.pairs >= 100)].sort_values('lift', ascending=False)
edges = cand.groupby('node_a').head(3)          # keep each node's 3 strongest outgoing chains (readable graph)
G = nx.DiGraph()
for r in edges.itertuples(): G.add_edge(r.node_a, r.node_b, weight=r.lift, pairs=r.pairs)
comms = nx.community.louvain_communities(G.to_undirected(), weight='weight', seed=RNG)
comm_of = {n: i for i, c in enumerate(comms) for n in c}
NOTES['graph'] = dict(nodes=G.number_of_nodes(), edges=G.number_of_edges(), communities=len(comms))
print(NOTES['graph'])
chains = edges.head(15)[['node_a', 'node_b', 'pairs', 'lift']].round(2)
chains

# %%
pos = nx.spring_layout(G.to_undirected(), weight='weight', k=1.4, seed=RNG, iterations=200)
palette = px.colors.qualitative.Set2
fig = go.Figure()
maxl = edges.lift.max()
for u, v, d in G.edges(data=True):
    x0, y0 = pos[u]; x1, y1 = pos[v]
    fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref='x', yref='y', axref='x', ayref='y', showarrow=True,
                       arrowhead=2, arrowsize=1, arrowwidth=0.6 + 3 * (d['weight'] - 1.5) / (maxl - 1.5 + 1e-9),
                       arrowcolor='rgba(110,110,110,0.45)', standoff=8, startstandoff=8)
vol = ev.node.value_counts()
for i, c in enumerate(comms):
    nl = list(c)
    fig.add_scatter(x=[pos[n][0] for n in nl], y=[pos[n][1] for n in nl], mode='markers+text',
                    text=[n.split(': ')[1] if len(n) > 26 else n for n in nl], textposition='top center',
                    textfont=dict(size=10),
                    marker=dict(size=[8 + 30 * np.sqrt(vol[n] / vol.max()) for n in nl], color=palette[i % len(palette)],
                                line=dict(width=1, color='white')),
                    hovertext=[f'{n}<br>{vol[n]:,} incidents<br>out: {G.out_degree(n)}  in: {G.in_degree(n)}' for n in nl],
                    hoverinfo='text', name=f'Community {i + 1}')
fig.update_layout(title='Failure-chain graph: A → B = B tends to follow A within 30 days (arrow width = lift)',
                  height=680, xaxis_visible=False, yaxis_visible=False, plot_bgcolor='white',
                  legend=dict(orientation='h', y=-0.05))
FIGS['graph'] = fig

# %% [markdown]
# ## 4. Repeat-failure predictor (next 30 days)
# Monthly snapshots. For each (building, category) with any activity in the prior 180 days, features
# are recency/frequency of that category, the building's other activity, related-category signals and season.
# Label = at least one incident of that category in the next 30 days.
# **Train:** snapshots May 2025 → Mar 2026. **Test:** May → Sep 2026 (strictly later, never seen).

# %%
cats = inc.complaint_type.value_counts().index[:11].tolist()
I = inc[inc.complaint_type.isin(cats)][['bbl', 'complaint_type', 'day', 'reports']]
cut_dates = pd.date_range('2025-05-01', END - pd.Timedelta(days=30), freq='MS')
cut_dates = cut_dates.append(pd.DatetimeIndex([END + pd.Timedelta(days=1)]))   # live scoring snapshot
rows = []
for c in cut_dates:
    past = I[(I.day < c) & (I.day >= c - pd.Timedelta(days=180))]
    fut = I[(I.day >= c) & (I.day < c + pd.Timedelta(days=30))]
    if past.empty: continue
    past = past.assign(w30=past.day >= c - pd.Timedelta(days=30), w90=past.day >= c - pd.Timedelta(days=90))
    g = past.groupby(['bbl', 'complaint_type'])
    f = pd.DataFrame({'n30': g.w30.sum(), 'n90': g.w90.sum(), 'n180': g.size(),
                      'days_since': g.day.max().rsub(c).dt.days, 'reports180': g.reports.sum()})
    bld = past.groupby('bbl')
    bfe = pd.DataFrame({'b_n90': bld.w90.sum(), 'b_types180': bld.complaint_type.nunique(), 'b_n180': bld.size()})
    # related-category signals (from the chain graph's main drivers)
    for rc in ['WATER LEAK', 'PLUMBING', 'UNSANITARY CONDITION', 'HEAT/HOT WATER']:
        s = past[(past.complaint_type == rc) & (past.day >= c - pd.Timedelta(days=60))].groupby('bbl').size()
        bfe['b_' + rc.split('/')[0].split(' ')[0].lower() + '60'] = s
    # full grid: every active building × every category
    grid = pd.MultiIndex.from_product([bfe.index, cats], names=['bbl', 'complaint_type'])
    d = f.reindex(grid).reset_index()
    d[['n30', 'n90', 'n180', 'reports180']] = d[['n30', 'n90', 'n180', 'reports180']].fillna(0)
    d['days_since'] = d.days_since.fillna(400)
    d = d.merge(bfe.fillna(0), left_on='bbl', right_index=True)
    lab = fut.groupby(['bbl', 'complaint_type']).size().rename('y')
    d = d.merge(lab, left_on=['bbl', 'complaint_type'], right_index=True, how='left')
    d['y'] = d.y.notna().astype(int)
    d['cutoff'] = c; d['month'] = c.month
    rows.append(d)
D = pd.concat(rows, ignore_index=True)
D['cat'] = D.complaint_type.astype('category')
D['heat_season'] = D.month.isin([10, 11, 12, 1, 2, 3, 4]).astype(int)
FEATS = ['n30', 'n90', 'n180', 'days_since', 'reports180', 'b_n90', 'b_types180', 'b_n180',
         'b_water60', 'b_plumbing60', 'b_unsanitary60', 'b_heat60', 'month', 'heat_season', 'cat']
live_cut = cut_dates[-1]
train = D[D.cutoff <= '2026-03-01']; test = D[(D.cutoff >= '2026-05-01') & (D.cutoff < live_cut)]
live = D[D.cutoff == live_cut]
clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, max_leaf_nodes=48,
                                     categorical_features=[FEATS.index('cat')], random_state=RNG)
clf.fit(train[FEATS], train.y)
pt = clf.predict_proba(test[FEATS])[:, 1]
base_score = test.n90 + 0.1 * test.n180   # heuristic baseline: "recent problems recur"
def prec_at(y, s, k): return y.values[np.argsort(-np.asarray(s))[:k]].mean()
K_TOP = 1000
NOTES['predict'] = dict(train_rows=len(train), test_rows=len(test), test_pos_rate=round(test.y.mean(), 4),
                        auc=round(roc_auc_score(test.y, pt), 3), ap=round(average_precision_score(test.y, pt), 3),
                        auc_baseline=round(roc_auc_score(test.y, base_score), 3),
                        ap_baseline=round(average_precision_score(test.y, base_score), 3),
                        p_at_1000_model=round(np.mean([prec_at(t.y, clf.predict_proba(t[FEATS])[:, 1], K_TOP) for _, t in test.groupby('cutoff')]), 3),
                        p_at_1000_baseline=round(np.mean([prec_at(t.y, t.n90 + 0.1 * t.n180, K_TOP) for _, t in test.groupby('cutoff')]), 3))
print(NOTES['predict'])

# %%
test = test.assign(p=pt)
per_cat = test.groupby('complaint_type').apply(lambda t: pd.Series({
    'pos_rate': t.y.mean(), 'auc': roc_auc_score(t.y, t.p) if t.y.nunique() > 1 else np.nan,
    'ap': average_precision_score(t.y, t.p) if t.y.nunique() > 1 else np.nan})).round(3).sort_values('ap', ascending=False)
per_cat

# %%
# calibration-style lift chart: deciles of predicted risk vs actual rate
test['decile'] = pd.qcut(test.p.rank(method='first'), 10, labels=False) + 1
dec = test.groupby('decile').agg(pred=('p', 'mean'), actual=('y', 'mean')).reset_index()
fig = go.Figure([go.Bar(x=dec.decile, y=dec.actual, name='actual rate'),
                 go.Scatter(x=dec.decile, y=dec.pred, name='predicted', mode='lines+markers')])
fig.update_layout(title='Hold-out (May–Sep 2026): risk decile vs actual 30-day occurrence', xaxis_title='predicted risk decile',
                  yaxis_title='share with ≥1 incident in next 30 days', height=380)
FIGS['predict_deciles'] = fig

from sklearn.inspection import permutation_importance
smp = test.sample(60000, random_state=RNG)
pi = permutation_importance(clf, smp[FEATS], smp.y, scoring='average_precision', n_repeats=3, random_state=RNG)
imp = pd.Series(pi.importances_mean, index=FEATS).sort_values()
fig = go.Figure(go.Bar(x=imp.values, y=imp.index, orientation='h'))
fig.update_layout(title='What drives the prediction (permutation importance, Δ average precision)', height=420)
FIGS['predict_imp'] = fig

# %%
live = live.assign(p=clf.predict_proba(live[FEATS])[:, 1]).merge(addr, left_on='bbl', right_index=True)
watch = (live.sort_values('p', ascending=False).query('complaint_type != "HEAT/HOT WATER"').head(20)
         [['address', 'zip', 'complaint_type', 'p', 'n90', 'days_since']])
watch['p'] = watch.p.round(2)
watch   # non-heat watch list (heat is predictable but less actionable)

# %%
# Early-warning list: high predicted risk although the category has NOT been reported in the last 90 days.
# These are the interesting ones for predictive maintenance: the signal comes from related categories / building context.
early = (live[(live.n90 == 0) & (live.complaint_type != 'HEAT/HOT WATER')].sort_values('p', ascending=False).head(20)
         [['address', 'zip', 'complaint_type', 'p', 'days_since', 'b_n90', 'b_water60', 'b_plumbing60']])
early['p'] = early.p.round(2)
# how good is the model on exactly this harder sub-population in the hold-out?
hard = test[test.n90 == 0]
NOTES['predict_early'] = dict(rows=len(hard), pos_rate=round(hard.y.mean(), 4), auc=round(roc_auc_score(hard.y, hard.p), 3),
                              ap=round(average_precision_score(hard.y, hard.p), 3),
                              p_at_500=round(np.mean([prec_at(t.y, t.p, 500) for _, t in hard.groupby('cutoff')]), 3))
print(NOTES['predict_early'])
early

# %%
heat_watch = live[live.complaint_type == 'HEAT/HOT WATER'].sort_values('p', ascending=False).head(10)[['address', 'zip', 'p', 'n90', 'days_since']]
heat_watch['p'] = heat_watch.p.round(2)
heat_watch

# %% [markdown]
# ## 5. Export report

# %%
import report_builder
tables = {'anomalies': anom_table, 'segments': summary.reset_index(), 'chains': chains,
          'per_cat': per_cat.reset_index(), 'watch': watch, 'heat_watch': heat_watch, 'early': early}
report_builder.build(FIGS, tables, NOTES, f'{OUT}/report.html')
json.dump(NOTES, open(f'{OUT}/key_numbers.json', 'w'), indent=2, default=str)
watch.to_csv(f'{OUT}/watchlist_next30d.csv', index=False)
# state for the graph explorer (export_graph.py)
import pickle
pickle.dump(dict(prof=prof, Z=Z, nz=nz, live=live, addr=addr, inc=inc, E=E, cnames=cnames, weeks=weeks, ev=ev, END=END),
            open('build/graph_state.pkl', 'wb'))
print('report written')

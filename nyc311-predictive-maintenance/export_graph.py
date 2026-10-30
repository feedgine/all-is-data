"""Export graph data for the Graphistry-style explorer (reads build/graph_state.pkl written by the notebook)."""
import json, pickle, sys
import numpy as np, pandas as pd, networkx as nx
from sklearn.neighbors import NearestNeighbors

S = pickle.load(open('build/graph_state.pkl', 'rb'))
prof, Z, nz, live, addr, inc, E, cnames, weeks, ev, END = (S[k] for k in
    ['prof', 'Z', 'nz', 'live', 'addr', 'inc', 'E', 'cnames', 'weeks', 'ev', 'END'])
RNG = 42
mask = ~prof.index.str.fullmatch(r'0+')          # drop placeholder BBL 0000000000
prof, Z = prof[mask], Z[mask.values if hasattr(mask,'values') else mask]
title = lambda s: s.title().replace('/', ' / ')

# ---------- building similarity graph ----------
cats = inc.complaint_type.value_counts().index[:11].tolist()
cat_idx = {c: i for i, c in enumerate(cats)}
mix = pd.crosstab(inc.bbl, inc.complaint_type, normalize='index').reindex(columns=cats, fill_value=0)

nn = NearestNeighbors(n_neighbors=6).fit(Z)
dist, idx = nn.kneighbors(Z)
bbls = prof.index.tolist()
edges = []
for i in range(len(bbls)):
    for d, j in zip(dist[i, 1:], idx[i, 1:]):
        a, b = (i, int(j)) if i < j else (int(j), i)
        edges.append((a, b, round(float(1 / (1 + d)), 3)))
edges = sorted(set(edges))

nonheat = live[live.complaint_type != 'HEAT/HOT WATER']
risk = nonheat.sort_values('p', ascending=False).drop_duplicates('bbl').set_index('bbl')
early = nonheat[nonheat.n90 == 0].sort_values('p', ascending=False).drop_duplicates('bbl').set_index('bbl')
EARLY_P = 0.30
anom_all = nz[nz.anomaly].groupby('bbl').size()
anom_recent = set(nz[nz.anomaly & (nz.week >= weeks[-8])].bbl)

seg_names = [cnames[c].split(': ', 1)[1] for c in sorted(cnames)]
nodes = []
for b in bbls:
    p = prof.loc[b]; m = mix.loc[b]
    top = m.sort_values(ascending=False).head(5)
    r = risk.p.get(b, 0.0); rc = risk.complaint_type.get(b)
    ep = early.p.get(b, 0.0)
    nodes.append(dict(
        id=b, a=' '.join(str(addr.address[b]).split()), z=str(addr.zip[b]), seg=int(p.cluster), segName=seg_names[int(p.cluster)],
        n=int(p.n), rate=round(float(p.rate_pm), 2), rep=round(float(p.repeat30), 3), close=round(float(p.close_days), 1),
        dom=cat_idx[m.idxmax()], mix=[[cat_idx[c], round(float(v), 3)] for c, v in top.items() if v > 0],
        risk=round(float(r), 3), riskCat=cat_idx.get(rc, -1),
        early=bool(ep >= EARLY_P), earlyP=round(float(ep), 3), earlyCat=cat_idx.get(early.complaint_type.get(b), -1),
        anomAll=int(anom_all.get(b, 0)), anomR=b in anom_recent,
        ux=round(float(p.u1), 3), uy=round(float(p.u2), 3),
        lat=round(float(addr.lat[b]), 5), lon=round(float(addr.lon[b]), 5)))

# ---------- failure-chain graph: timing lift + raw lift ----------
n_build = inc.bbl.nunique(); span = (END - inc.day.min()).days
base = ev.groupby('node').size() / n_build / span * 30
a_cnt = ev.groupby('node').size()
act = ev.groupby('bbl').size()
mult = ev.groupby('node').apply(lambda d: act.loc[d.bbl.unique()].mean() / act.mean())
E = E.copy()
E['raw'] = E.pairs / E.apply(lambda r: a_cnt[r.node_a] * (1 - np.exp(-base[r.node_b] * mult[r.node_a])), axis=1)
EE = E[E.pairs >= 20]
G = nx.DiGraph()
G.add_nodes_from(a_cnt.index)
for r in EE[(EE.lift >= 1.5) & (EE.pairs >= 100)].itertuples(): G.add_edge(r.node_a, r.node_b, weight=r.lift)
comms = nx.community.louvain_communities(G.to_undirected(), weight='weight', seed=RNG)
comm = {n: i for i, c in enumerate(sorted(comms, key=len, reverse=True)) for n in c}
L = nx.Graph(); L.add_nodes_from(a_cnt.index)
for r in EE[(EE.lift >= 1.2) & (EE.pairs >= 60)].itertuples():
    w = L.get_edge_data(r.node_a, r.node_b, {'weight': 0})['weight']
    L.add_edge(r.node_a, r.node_b, weight=max(w, r.lift - 1))
pos = nx.spring_layout(L, weight='weight', k=0.9, seed=RNG, iterations=300)
chains = dict(
    nodes=[dict(id=n, vol=int(a_cnt[n]), comm=comm.get(n, 0), x=round(float(pos[n][0]) * 10, 3), y=round(float(pos[n][1]) * 10, 3)) for n in a_cnt.index],
    edges=[dict(s=r.node_a, t=r.node_b, pairs=int(r.pairs), lift=round(float(r.lift), 3), raw=round(float(r.raw), 3)) for r in EE.itertuples()],
    maxVol=int(a_cnt.max()))

data = dict(cats=[title(c) for c in cats], segments=seg_names,
            buildings=dict(nodes=nodes, edges=edges), chains=chains)
meta = f"{len(nodes):,} buildings · {len(edges):,} similarity edges · {sum(n['early'] for n in nodes)} early-warning · {len(anom_recent & set(bbls))} recent anomalies"
json.dump(dict(data=data, meta=meta), open('build/graph_data.json', 'w'), separators=(',', ':'))
print(meta, '| chain edges', len(chains['edges']), '| communities', len(comms))

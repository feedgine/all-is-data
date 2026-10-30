# NYC 311 predictive maintenance

Can ordinary maintenance tickets predict the next problem in a building?
This example uses **NYC 311 housing complaints** (HPD, Brooklyn, Nov 2024 – Oct 2026) as a public stand-in
for a property manager's ticket log: one building (BBL) ≈ one property, complaint type ≈ ticket category.

![Building similarity graph, coloured by segment](docs/img/explorer-segments.png)

## What's inside

| Technique | Question it answers | Method |
|---|---|---|
| **Anomaly spikes** | Which building is unusual *this week*? | Seasonality-aware Poisson baseline (building share × borough total) + Isolation Forest; flagged when both agree |
| **Building segments** | What kinds of buildings are there? | Behaviour profile (volume, category mix, repeat rate, time to close, seasonality) → PCA → KMeans; UMAP for display |
| **Failure-chain graph** | Does problem B tend to *follow* problem A? | Directed co-occurrence within 30 days, lift against a building-level null model, Louvain communities |
| **30-day risk model** | Which building will file category X next month? | Gradient-boosted trees on recency/frequency features, strict time split (train May 2025–Mar 2026, test May–Sep 2026) |
| **Graph explorer** | Explore all of the above interactively | Graphistry-style WebGL explorer (sigma.js + ForceAtlas2), histogram filters, inspector, map view |

## Key results

- **478,559** complaints (476,816 with a building ID) → **348,648** incidents after merging same-day duplicates, across **29k** buildings.
- **Risk model:** ROC-AUC **0.82** on the later hold-out, against 0.74 for a "recent problems repeat" rule.
  The top 1,000 flags per month are right **58%** of the time (rule: 46%).
- **Early warning:** for categories not reported in the last 90 days, the top-500 list is about **10× better than random**.
  A hotspot list can't produce this at all.
- **Anomalies:** 630 building-weeks flagged by both detectors. The typical pattern is a quiet building suddenly filing
  10–25 issues across many categories (an inspection sweep or a management change).
- **Chains:** once you control for "busy buildings have everything", real sequences are electrical
  (outage → no lighting) and gas → range. The intuitive leak → mold → paint "chain" comes from co-location, not timing.
  The explorer's *raw vs timing lift* toggle shows the difference.

| | |
|---|---|
| ![Anomalies on the map](docs/img/explorer-map-anomalies.png) | ![Failure chains, timing lift](docs/img/chains-timing.png) |
| Anomalies on the map (red = last 8 weeks) | Failure chains after removing co-location |

## Open the outputs

- [`docs/report.html`](docs/report.html): full report with interactive charts, tables and the watch lists.
- [`docs/graph_explorer.html`](docs/graph_explorer.html): WebGL graph explorer (one offline file).

Both are self-contained. Download and open them, or view them through GitHub Pages (see the root README).

## Run it yourself

```bash
pip install -r requirements.txt
python fetch_data.py                                    # ~2–5 min, ~100 MB into data/
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=1500 NYC311_predictive_maintenance.ipynb   # ~4 min → docs/report.html
python export_graph.py                                  # → build/graph_data.json
cd explorer && npm install && npm run build && cd ..
python explorer/assemble.py build/graph_data.json docs/graph_explorer.html
```

Optional: `graphistry_upload.py` pushes the same graph to a [Graphistry](https://www.graphistry.com/) server
(needs an account; it uploads addresses and scores to that server).

## Files

| File | Purpose |
|---|---|
| `fetch_data.py` | Paged download from the NYC Open Data API (SoQL filter: HPD, Brooklyn, since 2024-11-01) |
| `NYC311_predictive_maintenance.ipynb` | The analysis, executed (source mirrored in `analysis.py`) |
| `report_builder.py` | Assembles `docs/report.html` |
| `export_graph.py` | Builds the graph data for the explorer |
| `explorer/` | Explorer front end (`main.js`, `template.html`) and `assemble.py` |
| `docs/` | Generated outputs: report, explorer, key numbers, watch list, screenshots |

## Caveats

311 is tenant-reported and regulator-facing, not an operator's ticket log. Duplicates and inspection sweeps inflate spikes.
The hold-out covers one summer only, so heat predictions need a winter check. Watch lists are model outputs
on public data, not statements about any building's condition.

Data: [NYC Open Data, dataset erm2-nwe9](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9/about_data),
under the [NYC Open Data Terms of Use](https://opendata.cityofnewyork.us/overview/#termsofuse).

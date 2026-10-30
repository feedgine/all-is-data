# all-is-data

**Everything is data.** Viewing the world through quantification, analytics and information theory.

Worked data-visualisation and analytics examples on public datasets. Each example is self-contained:
it has a script to fetch the data, a reproducible notebook, and interactive HTML outputs you can open
in a browser without a server.

## Examples

| Example | Dataset | Techniques | Open |
|---|---|---|---|
| [NYC 311 predictive maintenance](nyc311-predictive-maintenance/) | NYC 311 housing complaints (HPD, Brooklyn, 24 months, 478k rows) | Seasonal anomaly detection · Isolation Forest · UMAP + KMeans clustering · co-occurrence graph with Louvain communities · gradient-boosted 30-day risk model · WebGL graph explorer | [Report](nyc311-predictive-maintenance/docs/report.html) · [Graph explorer](nyc311-predictive-maintenance/docs/graph_explorer.html) |

## Layout

```
all-is-data/
└── <example>/
    ├── README.md        what it shows, findings, how to run
    ├── fetch_data.py    downloads the raw data into data/ (data is not committed)
    ├── *.ipynb          the analysis, executed
    └── docs/            interactive HTML outputs + screenshots
```

## Viewing the HTML outputs

The `.html` files are self-contained (no server, no external calls). Download and open them, or turn on
**GitHub Pages** for this repo (Settings → Pages → deploy from branch `main`, folder `/ (root)`).
They are then served at `https://<user>.github.io/all-is-data/<example>/docs/…`.

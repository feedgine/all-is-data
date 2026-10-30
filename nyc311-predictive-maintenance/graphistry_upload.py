"""Optional: push the same building graph to real Graphistry (Hub or self-hosted).
Needs a Graphistry account and network access to the Graphistry server:
    pip install graphistry pandas
    GRAPHISTRY_USERNAME=... GRAPHISTRY_PASSWORD=... python graphistry_upload.py
Note: this uploads building addresses and risk scores to the Graphistry server you point it at.
"""
import json, os
import pandas as pd
import graphistry

d = json.load(open('build/graph_data.json'))['data']
nodes = pd.DataFrame(d['buildings']['nodes']).drop(columns=['mix']).reset_index(names='nid')
nodes['segment'] = nodes.segName
nodes['dominant_category'] = nodes.dom.map(dict(enumerate(d['cats'])))
edges = pd.DataFrame(d['buildings']['edges'], columns=['src', 'dst', 'similarity'])

graphistry.register(api=3, server=os.getenv('GRAPHISTRY_SERVER', 'hub.graphistry.com'),
                    username=os.environ['GRAPHISTRY_USERNAME'], password=os.environ['GRAPHISTRY_PASSWORD'])
g = (graphistry.edges(edges, 'src', 'dst').nodes(nodes, 'nid')
     .bind(point_title='a', point_size='n', edge_weight='similarity')
     .encode_point_color('segment', as_categorical=True)
     .settings(url_params={'play': 4000, 'bg': '%230b0f17', 'edgeOpacity': 0.25, 'pointSize': 0.6}))
print(g.plot(render=False))   # prints the shareable Graphistry URL

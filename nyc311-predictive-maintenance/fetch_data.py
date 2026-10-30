"""Download the HPD / Brooklyn slice of NYC 311 (dataset erm2-nwe9) into data/.

    python fetch_data.py                      # 2024-11-01 → today, ~480k rows, ~100 MB
    python fetch_data.py --since 2025-01-01 --borough QUEENS

Optional: set SOCRATA_APP_TOKEN to avoid throttling (free token from data.cityofnewyork.us).
"""
import argparse, csv, io, os, sys
import urllib.parse, urllib.request

API = 'https://data.cityofnewyork.us/resource/erm2-nwe9.csv'
COLS = ('unique_key,created_date,closed_date,complaint_type,descriptor,location_type,'
        'incident_zip,incident_address,bbl,status,latitude,longitude')
PAGE = 50_000

ap = argparse.ArgumentParser()
ap.add_argument('--since', default='2024-11-01')
ap.add_argument('--borough', default='BROOKLYN')
ap.add_argument('--agency', default='HPD')
ap.add_argument('--out', default='data/nyc311_hpd_brooklyn.csv')
a = ap.parse_args()

where = f"agency='{a.agency}' AND borough='{a.borough}' AND created_date >= '{a.since}T00:00:00'"
headers = {'X-App-Token': os.environ['SOCRATA_APP_TOKEN']} if os.getenv('SOCRATA_APP_TOKEN') else {}
os.makedirs(os.path.dirname(a.out), exist_ok=True)
offset, total = 0, 0
with open(a.out, 'w', newline='') as f:
    w = None
    while True:
        q = urllib.parse.urlencode({'$select': COLS, '$where': where, '$order': 'unique_key',
                                    '$limit': PAGE, '$offset': offset})
        with urllib.request.urlopen(urllib.request.Request(f'{API}?{q}', headers=headers), timeout=300) as r:
            rows = list(csv.reader(io.TextIOWrapper(r, encoding='utf-8')))
        header, body = rows[0], rows[1:]
        if w is None:
            w = csv.writer(f, quoting=csv.QUOTE_ALL); w.writerow(header)
        w.writerows(body)
        total += len(body); offset += PAGE
        print(f'\r{total:,} rows', end='', file=sys.stderr)
        if len(body) < PAGE:
            break
print(f'\nSaved {total:,} rows to {a.out}', file=sys.stderr)

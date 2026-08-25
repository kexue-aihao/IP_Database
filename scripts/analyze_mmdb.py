#!/usr/bin/env python3
"""Analyze geo_level distribution in China MMDB output files."""

import maxminddb
import os
import collections

OUTDIR = 'E:/IP_Database/output'

files = sorted(f for f in os.listdir(OUTDIR)
               if f.endswith('.mmdb') and f.startswith('china_'))

for fn in files:
    path = os.path.join(OUTDIR, fn)
    try:
        reader = maxminddb.open_database(path)
    except Exception as e:
        print(f'  [SKIP] {fn}: {e}')
        continue

    total = 0
    level_dist = collections.Counter()
    isp_dist = collections.Counter()
    no_coord = 0
    shown = []

    for net, data in reader:
        if not isinstance(data, dict):
            continue
        total += 1
        lvl = str(data.get('geo_level', ''))
        level_dist[lvl] += 1
        isp_dist[str(data.get('isp', ''))] += 1
        if not data.get('latitude'):
            no_coord += 1
        if len(shown) < 3:
            shown.append((str(net), data))

    reader.close()

    print('=' * 70)
    print(fn)
    print(f'  total networks: {total}')
    print(f'  geo_level dist: {dict(level_dist)}')
    print(f'  no_coord: {no_coord} ({100*no_coord/max(total,1):.1f}%)')
    top_isp = isp_dist.most_common(5)
    print(f'  top ISP: {top_isp}')
    for net, d in shown:
        print(f'    sample {net}: prov={d.get("province")}, city={d.get("city")}, '
              f'lvl={d.get("geo_level")}, lat={d.get("latitude")}, lng={d.get("longitude")}')

# Combined files
for fn in ['china_ipv4.mmdb', 'china_ipv6.mmdb']:
    path = os.path.join(OUTDIR, fn)
    if not os.path.exists(path):
        continue
    try:
        reader = maxminddb.open_database(path)
    except Exception as e:
        print(f'  [SKIP] {fn}: {e}')
        continue

    total = 0
    level_dist = collections.Counter()
    no_coord = 0
    for net, data in reader:
        if isinstance(data, dict):
            total += 1
            level_dist[str(data.get('geo_level', ''))] += 1
            if not data.get('latitude'):
                no_coord += 1
    reader.close()
    print('=' * 70)
    print(f'{fn}: total={total}, geo_level={dict(level_dist)}, no_coord={no_coord}')
#!/usr/bin/env python3
"""
S2.1 - v4 ISP 缺失分析

统计 china_ipv4.mmdb 与 high_prec / high_prec_v2 / with_isp 中 isp 字段缺失的记录数与比例，
输出 data/china/v4/v4_isp_gap.json
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, 'scripts'))

import maxminddb

FILES = [
    ('china_ipv4.mmdb', '主库'),
    ('china_ipv4_high_prec.mmdb', 'high_prec'),
    ('china_ipv4_high_prec_v2.mmdb', 'high_prec_v2'),
    ('china_ipv4_with_isp.mmdb', 'with_isp'),
]

def scan(path):
    total = 0
    with_isp = 0
    without_isp = 0
    isp_values = set()
    fields_seen = set()
    with maxminddb.open_database(path) as reader:
        for network, data in reader:
            if data is None:
                continue
            total += 1
            fields_seen.update(data.keys())
            if 'isp' in data and data['isp']:
                with_isp += 1
                isp_values.add(data['isp'])
            else:
                without_isp += 1
    return {
        'total': total,
        'with_isp': with_isp,
        'without_isp': without_isp,
        'with_isp_pct': round(with_isp * 100.0 / total, 4) if total else 0,
        'without_isp_pct': round(without_isp * 100.0 / total, 4) if total else 0,
        'unique_isp_count': len(isp_values),
        'fields': sorted(fields_seen),
    }

def main():
    results = {}
    for fname, label in FILES:
        path = os.path.join(BASE, 'output', fname)
        if not os.path.exists(path):
            results[fname] = {'error': 'file not found'}
            print(f'[SKIP] {fname} not found')
            continue
        stats = scan(path)
        results[fname] = stats
        print(f'{label:14s} total={stats["total"]:>8d} with_isp={stats["with_isp"]:>8d} '
              f'({stats["with_isp_pct"]:.2f}%) missing={stats["without_isp"]:>8d} '
              f'({stats["without_isp_pct"]:.2f}%)')

    out = {
        'task': 'S2.1 v4 ISP 缺失分析',
        'note': 'china_ipv4.mmdb 与 high_prec/with_isp 系列 isp 字段覆盖对比',
        'per_file': results,
        'summary': {}
    }
    base = results.get('china_ipv4.mmdb', {})
    if base:
        out['summary']['main_db_without_isp'] = base.get('without_isp', 0)
        out['summary']['main_db_without_isp_pct'] = base.get('without_isp_pct', 0)
        for key in ('china_ipv4_high_prec.mmdb', 'china_ipv4_high_prec_v2.mmdb', 'china_ipv4_with_isp.mmdb'):
            r = results.get(key, {})
            if 'total' in r:
                out['summary'][f'{key}_without_isp'] = r.get('without_isp', 0)
                out['summary'][f'{key}_without_isp_pct'] = r.get('without_isp_pct', 0)

    os.makedirs(os.path.join(BASE, 'data', 'china', 'v4'), exist_ok=True)
    out_path = os.path.join(BASE, 'data', 'china', 'v4', 'v4_isp_gap.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] written: {out_path}')

if __name__ == '__main__':
    main()

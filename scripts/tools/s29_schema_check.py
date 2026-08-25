# -*- coding: utf-8 -*-
"""
S2.9 - 字段类型/完整性校验 (Field schema validation for S2 China IPv4 rebuild outputs)

Input : output/*.mmdb  (S2 pool covered rebuild products, 8 files)
Output: data/china/v4/v4_schema_check.json

Checks per file:
  - field existence (expected schema keys) with per-key coverage ratio
  - latitude/longitude must be float type (any non-float count = FAIL)
  - lat/lng range sanity (lat in [-90,90], lng in [-180,180])
  - union of observed keys + per-key type distribution & samples
  - MMDB metadata (ip_version, record_size, node_count, db type, build epoch)

Expected schema keys (from repo output schema + S2 pool target):
  country, province, city, district, isp, division_code,
  latitude, longitude, geo_level, idc_vendor,
  is_residential (bool), connection_type
Note: start_ip/end_ip are network bounds in MMDB (not record data keys).
"""
import json
import os
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone

import maxminddb

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE, 'output')
REPORT_DIR = os.path.join(BASE, 'data', 'china', 'v4')
REPORT_PATH = os.path.join(REPORT_DIR, 'v4_schema_check.json')

FILES = [
    'china_ipv4.mmdb',
    'china_ipv4_telecom.mmdb',
    'china_ipv4_unicom.mmdb',
    'china_ipv4_mobile.mmdb',
    'china_ipv4_other.mmdb',
    'china_ipv4_with_isp.mmdb',
    'china_ipv4_high_prec.mmdb',
    'china_ipv4_high_prec_v2.mmdb',
]

EXPECTED_FIELDS = [
    'country', 'province', 'city', 'district',
    'isp', 'division_code',
    'latitude', 'longitude',
    'geo_level', 'idc_vendor',
    'is_residential', 'connection_type',
]

LAT_RANGE = (-90.0, 90.0)
LNG_RANGE = (-180.0, 180.0)


def check_range(v, rng):
    """Return True if numeric value within range."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return rng[0] <= float(v) <= rng[1]
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return False
    return rng[0] <= fv <= rng[1]


def scan_file(path):
    """Scan one MMDB file; return report dict."""
    report = OrderedDict()
    report['path'] = os.path.relpath(path, BASE)
    report['exists'] = True

    f = maxminddb.open_database(path)
    meta = f.metadata()
    report['metadata'] = {
        'ip_version': meta.ip_version,
        'record_size': meta.record_size,
        'node_count': meta.node_count,
        'database_type': meta.database_type,
        'description': {str(k): str(v) for k, v in (meta.description or {}).items()},
        'build_epoch': getattr(meta, 'build_epoch', None),
        'binary_format': '{}.{}'.format(
            getattr(meta, 'binary_format_major_version', '?'),
            getattr(meta, 'binary_format_minor_version', '?')),
    }

    key_present = Counter()          # count of records having each key
    key_absent = Counter()           # count of records NOT having each key
    key_types = {}                   # key -> Counter(type_name -> count)
    key_samples = {}                 # key -> list of first sample values
    latlng = {'latitude': Counter(), 'longitude': Counter()}
    latlng_out_of_range = Counter()
    total = 0

    def track(data, key):
        if key in data:
            key_present[key] += 1
            tname = type(data[key]).__name__
            key_types.setdefault(key, Counter())[tname] += 1
            if key in ('latitude', 'longitude', 'lat', 'lng'):
                latlng[key].update([tname])
                if not isinstance(data[key], bool) and isinstance(data[key], (int, float)):
                    rng = LAT_RANGE if key == 'latitude' else LNG_RANGE
                    if not check_range(data[key], rng):
                        latlng_out_of_range[key] += 1
            if len(key_samples.get(key, [])) < 3:
                key_samples.setdefault(key, []).append(data[key])
        else:
            key_absent[key] += 1

    for _net, data in f:
        total += 1
        for key in data.keys():
            track(data, key)

    f.close()
    report['record_count'] = total

    # ---- per-field detail over the union of expected + observed ----
    observed = set(key_present.keys())
    fields = OrderedDict()
    for key in EXPECTED_FIELDS:
        present = key_present.get(key, 0)
        coverage = present / total if total else 0.0
        fields[key] = {
            'expected': True,
            'present': present > 0,
            'coverage': round(coverage, 6),
            'present_count': present,
            'absent_count': key_absent.get(key, total),
            'type_distribution': dict(key_types.get(key, {})),
            'samples': key_samples.get(key, []),
        }
    for key in sorted(observed - set(EXPECTED_FIELDS)):
        present = key_present.get(key, 0)
        fields[key] = {
            'expected': False,
            'present': True,
            'coverage': round(present / total, 6) if total else 0.0,
            'present_count': present,
            'absent_count': key_absent.get(key, total),
            'type_distribution': dict(key_types.get(key, {})),
            'samples': key_samples.get(key, []),
        }
    report['fields'] = fields

    # ---- lat/lng float check ----
    lat_numeric = latlng['latitude'].get('float', 0) + latlng['latitude'].get('int', 0)
    lng_numeric = latlng['longitude'].get('float', 0) + latlng['longitude'].get('int', 0)
    report['lat_lng_check'] = {
        'latitude': {
            'type_counts': dict(latlng['latitude']),
            'non_numeric_count': key_present.get('latitude', 0) - lat_numeric,
            'out_of_range_count': latlng_out_of_range.get('latitude', 0),
            'numeric_ok': lat_numeric == key_present.get('latitude', 0),
        },
        'longitude': {
            'type_counts': dict(latlng['longitude']),
            'non_numeric_count': key_present.get('longitude', 0) - lng_numeric,
            'out_of_range_count': latlng_out_of_range.get('longitude', 0),
            'numeric_ok': lng_numeric == key_present.get('longitude', 0),
        },
    }

    # ---- verdicts ----
    missing_expected = [k for k in EXPECTED_FIELDS if key_present.get(k, 0) == 0]
    partial_expected = [k for k in EXPECTED_FIELDS
                        if 0 < key_present.get(k, 0) < total]
    report['missing_expected_fields'] = missing_expected
    report['partial_coverage_fields'] = partial_expected
    report['extra_fields'] = sorted(observed - set(EXPECTED_FIELDS))

    lat_ok = report['lat_lng_check']['latitude']['numeric_ok'] and \
        report['lat_lng_check']['latitude']['out_of_range_count'] == 0
    lng_ok = report['lat_lng_check']['longitude']['numeric_ok'] and \
        report['lat_lng_check']['longitude']['out_of_range_count'] == 0
    report['overall'] = {
        'latlng_float_ok': lat_ok and lng_ok,
        'all_expected_fields_present': len(missing_expected) == 0,
        'missing_expected_fields': missing_expected,
    }
    return report


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    result = OrderedDict()
    result['task'] = 'S2.9 字段类型/完整性校验'
    result['pool'] = 'S2 中国 IPv4 主库补丁'
    result['generated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    result['expected_fields'] = EXPECTED_FIELDS
    result['note'] = ('start_ip/end_ip 是 MMDB 网络区间（network 对象），不作为记录数据键校验；'
                      'is_residential 应为 bool；latitude/longitude 应为 float(WGS-84)。')

    files_report = OrderedDict()
    errors = {}
    for fn in FILES:
        path = os.path.join(OUTPUT_DIR, fn)
        if not os.path.exists(path):
            files_report[fn] = {'path': os.path.relpath(path, BASE), 'exists': False,
                                'error': 'file missing'}
            continue
        try:
            files_report[fn] = scan_file(path)
        except Exception as exc:  # pragma: no cover
            errors[fn] = str(exc)
            files_report[fn] = {'path': os.path.relpath(path, BASE), 'exists': True,
                                'error': str(exc)}
    result['files'] = files_report

    # ---- summary ----
    summary = OrderedDict()
    summary['file_count'] = len(FILES)
    summary['issues'] = []
    for fn, rep in files_report.items():
        if rep.get('error'):
            summary['issues'].append({'file': fn, 'level': 'error', 'message': rep['error']})
            continue
        if not rep['overall']['latlng_float_ok']:
            summary['issues'].append({
                'file': fn, 'level': 'fail',
                'message': 'lat/lng 存在非数值或越界: lat={}, lng={}'.format(
                    rep['lat_lng_check']['latitude']['non_numeric_count'],
                    rep['lat_lng_check']['longitude']['non_numeric_count'],
                )})
        for missing in rep['missing_expected_fields']:
            summary['issues'].append({
                'file': fn, 'level': 'warn', 'message': '缺少期望字段: {}'.format(missing)})
    fail_files = {i['file'] for i in summary['issues'] if i['level'] == 'fail'}
    err_files = {i['file'] for i in summary['issues'] if i['level'] == 'error'}
    summary['ok_count'] = len([fn for fn in FILES if fn not in fail_files and fn not in err_files])

    # per-field cross-file matrix
    field_matrix = OrderedDict()
    for key in EXPECTED_FIELDS:
        present_in = [fn for fn, rep in files_report.items()
                      if not rep.get('error') and rep['fields'].get(key, {}).get('present')]
        full_coverage = [fn for fn, rep in files_report.items()
                         if not rep.get('error') and rep['fields'].get(key, {}).get('coverage', 0) >= 1.0]
        field_matrix[key] = {
            'present_in_files': present_in,
            'full_coverage_files': full_coverage,
            'absent_in_files': [fn for fn, rep in files_report.items()
                                if not rep.get('error') and not rep['fields'].get(key, {}).get('present')],
        }
    summary['field_matrix'] = field_matrix
    summary['latlng_float_fail_files'] = [fn for fn, rep in files_report.items()
                                          if not rep.get('error') and not rep['overall']['latlng_float_ok']]
    summary['run_errors'] = errors
    result['summary'] = summary

    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print('Wrote {}'.format(REPORT_PATH))
    print('summary: {}'.format(json.dumps(summary, ensure_ascii=False)))


if __name__ == '__main__':
    main()
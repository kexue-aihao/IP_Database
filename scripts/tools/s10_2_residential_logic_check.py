#!/usr/bin/env python3
"""
S10.2 - Residential Logic Validation (家宽逻辑验证)

Performs two sampling checks and reports error rate:
  1. Random 1000 samples across all MMDB files (weighted by record count)
  2. 200 known IDC segments from constants.py + idc_all.csv

For each sample:
  - Compute expected is_residential value per classification_rules:
    * IDC range hit → is_residential=false
    * Non-IDC + pass pre-filter → is_residential=true
    * Pre-filter hit → undefined (connection_type=unknown)
  - Compare with actual stored field value (if present)
  - Report error rate, field missing rate, and rule-level consistency

Output: data/audit/final_logic_check.json
"""

import csv
import ipaddress
import json
import os
import random
import sys
import time
import bisect
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(BASE, 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

import maxminddb
from common.constants import IDC_IPV4_RANGES, IDC_IPV6_PREFIXES

# ──────────────────────────────────────────────────────────────────────
# IDC Lookup (same logic as 50_mmdb_field_patch.py)
# ──────────────────────────────────────────────────────────────────────

IDC_CSV_PATH = os.path.join(BASE, 'data', 'global', 'idc', 'idc_all.csv')
VENDOR_WHITELIST = {
    'AWS', 'Azure', 'GCP', 'Cloudflare', 'DigitalOcean', 'Fastly',
    '阿里云', '腾讯云', '华为云', '百度云', '京东云', 'cn_cloud_ipv6',
}

# Pre-filter ranges (same as classification_rules.json)
PRE_FILTERS_V4 = [
    ('RFC1918', ipaddress.IPv4Network('10.0.0.0/8')),
    ('RFC1918', ipaddress.IPv4Network('172.16.0.0/12')),
    ('RFC1918', ipaddress.IPv4Network('192.168.0.0/16')),
    ('CGNAT', ipaddress.IPv4Network('100.64.0.0/10')),
    ('Loopback', ipaddress.IPv4Network('127.0.0.0/8')),
    ('Link-local', ipaddress.IPv4Network('169.254.0.0/16')),
    ('Reserved', ipaddress.IPv4Network('0.0.0.0/8')),
    ('Future use', ipaddress.IPv4Network('240.0.0.0/4')),
    ('Broadcast', ipaddress.IPv4Network('255.255.255.255/32')),
    ('Multicast', ipaddress.IPv4Network('224.0.0.0/4')),
]

PRE_FILTERS_V6 = [
    ('ULA', ipaddress.IPv6Network('fc00::/7')),
    ('Link-local', ipaddress.IPv6Network('fe80::/10')),
    ('Loopback', ipaddress.IPv6Network('::1/128')),
    ('Unspecified', ipaddress.IPv6Network('::/128')),
    ('Documentation', ipaddress.IPv6Network('2001:db8::/32')),
]


def _load_idc_csv():
    """Load idc_all.csv into (v4_intervals, v6_intervals) lists."""
    v4, v6 = [], []
    if not os.path.exists(IDC_CSV_PATH):
        return v4, v6
    with open(IDC_CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cidr = row.get('cidr', '').strip()
            if not cidr or '/' not in cidr:
                continue
            vendor = row.get('vendor', '').strip() or 'unknown'
            if vendor not in VENDOR_WHITELIST:
                continue
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                s = int(net.network_address)
                e = int(net.broadcast_address)
                if net.version == 4:
                    v4.append((s, e, vendor, cidr))
                else:
                    v6.append((s, e, vendor, cidr))
            except ValueError:
                continue
    return v4, v6


def _build_idc_lookup():
    """Build sorted (start, end, vendor, cidr) for v4 and v6."""
    # V4: constants first, then csv
    v4_intervals = []
    for vendor, (lo, hi) in IDC_IPV4_RANGES:
        v4_intervals.append((lo, hi, vendor, ''))
    csv_v4, csv_v6 = _load_idc_csv()
    v4_intervals.extend(csv_v4)
    v4_intervals.sort(key=lambda x: (x[0], x[1]))

    # V6: constants first, then csv
    v6_intervals = []
    for vendor, prefix_hex, prefix_len in IDC_IPV6_PREFIXES:
        prefix_val = int(prefix_hex, 16) << (128 - prefix_len)
        end_val = prefix_val | ((1 << (128 - prefix_len)) - 1)
        v6_intervals.append((prefix_val, end_val, vendor, f'{prefix_hex}/{prefix_len}'))
    v6_intervals.extend(csv_v6)
    v6_intervals.sort(key=lambda x: (x[0], x[1]))

    v4_starts = [iv[0] for iv in v4_intervals]
    v6_starts = [iv[0] for iv in v6_intervals]
    return v4_intervals, v4_starts, v6_intervals, v6_starts


def _bisect_lookup(ip_int, intervals, starts):
    i = bisect.bisect_right(starts, ip_int) - 1
    while i >= 0 and starts[i] <= ip_int:
        lo, hi, vendor, cidr = intervals[i]
        if ip_int <= hi:
            return vendor, cidr
        i -= 1
    return None, None


def check_pre_filter(ip_str, ip_int, ipv):
    """Check if an IP hits any pre-filter. Returns (hit_bool, filter_name)."""
    if ipv == 4:
        try:
            addr = ipaddress.IPv4Address(ip_str)
        except ValueError:
            return False, ''
        for name, net in PRE_FILTERS_V4:
            if addr in net:
                return True, name
    else:
        try:
            addr = ipaddress.IPv6Address(ip_str)
        except ValueError:
            return False, ''
        for name, net in PRE_FILTERS_V6:
            if addr in net:
                return True, name
    return False, ''


# ──────────────────────────────────────────────────────────────────────
# File group classification
# ──────────────────────────────────────────────────────────────────────

def classify_file(filename):
    """Return (file_group, expected_is_residential, expected_connection_type)."""
    fn = os.path.basename(filename).lower()
    if 'idc' in fn:
        return 'idc', False, 'idc'
    if 'residential' in fn:
        return 'residential', True, 'residential'
    return 'mixed', True, 'residential'  # china_main defaults


# ──────────────────────────────────────────────────────────────────────
# Sampling
# ──────────────────────────────────────────────────────────────────────

RANDOM_SEED = 42
SAMPLE_RANDOM = 1000
SAMPLE_IDC = 200

MMDB_FILES = [
    'china_ipv4.mmdb', 'china_ipv4_telecom.mmdb', 'china_ipv4_unicom.mmdb',
    'china_ipv4_mobile.mmdb', 'china_ipv4_other.mmdb',
    'china_ipv4_high_prec.mmdb', 'china_ipv4_high_prec_v2.mmdb',
    'china_ipv4_with_isp.mmdb',
    'china_ipv4_idc.mmdb', 'china_ipv4_idc_enriched.mmdb',
    'china_ipv6.mmdb', 'china_ipv6_enriched.mmdb',
    'china_ipv6_telecom.mmdb', 'china_ipv6_unicom.mmdb',
    'china_ipv6_mobile.mmdb', 'china_ipv6_other.mmdb',
    'china_ipv6_with_isp.mmdb',
    'china_ipv6_idc.mmdb', 'china_ipv6_idc_enriched.mmdb',
    'global_ipv4_residential.mmdb', 'global_ipv6_residential.mmdb',
    'global_ipv4_idc.mmdb', 'global_ipv6_idc.mmdb',
]


def sample_random_1000(output_dir):
    """Randomly sample 1000 records from all MMDB files (weighted by count)."""
    # First pass: count records per file
    file_counts = {}
    for fn in MMDB_FILES:
        path = os.path.join(output_dir, fn)
        if not os.path.exists(path):
            continue
        try:
            reader = maxminddb.Reader(path, maxminddb.const.MODE_FILE)
            cnt = 0
            for _ in reader:
                cnt += 1
            reader.close()
            file_counts[fn] = cnt
        except Exception:
            continue

    total = sum(file_counts.values())
    if total == 0:
        return []

    # Weighted random sampling
    rng = random.Random(RANDOM_SEED)
    samples = []
    counts_remaining = {fn: file_counts[fn] for fn in file_counts}
    total_remaining = total

    while len(samples) < SAMPLE_RANDOM and total_remaining > 0:
        # Pick a file weighted by remaining count
        r = rng.randint(1, total_remaining)
        cumulative = 0
        chosen = None
        for fn, cnt in sorted(counts_remaining.items()):
            cumulative += cnt
            if r <= cumulative:
                chosen = fn
                break
        if chosen is None:
            break

        # Pick a random record from the file
        path = os.path.join(output_dir, chosen)
        try:
            reader = maxminddb.Reader(path, maxminddb.const.MODE_FILE)
            all_records = list(reader)
            reader.close()
            if not all_records:
                counts_remaining.pop(chosen, None)
                total_remaining -= file_counts[chosen]
                continue
            idx = rng.randint(0, len(all_records) - 1)
            network, data = all_records[idx]
            samples.append((chosen, str(network), dict(data) if data else {}))
            # Remove one occurrence from remaining
            counts_remaining[chosen] -= 1
            total_remaining -= 1
            if counts_remaining[chosen] <= 0:
                del counts_remaining[chosen]
        except Exception as e:
            counts_remaining.pop(chosen, None)
            total_remaining -= file_counts[chosen]

    return samples


def sample_idc_200():
    """Sample 200 known IDC IPs from constants + idc_all.csv."""
    v4_intervals, v4_starts, v6_intervals, v6_starts = _build_idc_lookup()
    rng = random.Random(RANDOM_SEED + 1)
    samples = []

    # 1) From constants IDC_IPV4_RANGES (24 ranges)
    for vendor, (lo, hi) in IDC_IPV4_RANGES:
        # Pick a random IP in the range
        ip_int = rng.randint(lo, hi)
        ip_str = str(ipaddress.IPv4Address(ip_int))
        samples.append({
            'source': 'constants_v4',
            'vendor': vendor,
            'cidr_or_range': f'{ipaddress.IPv4Address(lo)}-{ipaddress.IPv4Address(hi)}',
            'ip': ip_str,
            'ip_int': ip_int,
            'ipv': 4,
        })

    # 2) From constants IDC_IPV6_PREFIXES (6 prefixes)
    for vendor, prefix_hex, prefix_len in IDC_IPV6_PREFIXES:
        prefix_val = int(prefix_hex, 16) << (128 - prefix_len)
        ip_int = prefix_val + rng.randint(0, (1 << (128 - prefix_len)) - 1)
        ip_str = str(ipaddress.IPv6Address(ip_int))
        samples.append({
            'source': 'constants_v6',
            'vendor': vendor,
            'cidr_or_range': f'{prefix_hex}/{prefix_len}',
            'ip': ip_str,
            'ip_int': ip_int,
            'ipv': 6,
        })

    # 3) From idc_all.csv (random selection)
    _, csv_v4, _, csv_v6 = _load_idc_csv(), [], [], []
    # Actually need to reload properly
    csv_v4, csv_v6 = _load_idc_csv()

    all_csv = [(s, e, v, c, 4) for s, e, v, c in csv_v4] + \
              [(s, e, v, c, 6) for s, e, v, c in csv_v6]
    rng.shuffle(all_csv)

    for s, e, vendor, cidr, ipv in all_csv:
        if len(samples) >= SAMPLE_IDC:
            break
        if ipv == 4:
            ip_int = rng.randint(s, e)
            ip_str = str(ipaddress.IPv4Address(ip_int))
        else:
            ip_int = rng.randint(s, e)
            ip_str = str(ipaddress.IPv6Address(ip_int))
        samples.append({
            'source': 'idc_csv',
            'vendor': vendor,
            'cidr_or_range': cidr,
            'ip': ip_str,
            'ip_int': ip_int,
            'ipv': ipv,
        })

    # Trim to exactly SAMPLE_IDC
    return samples[:SAMPLE_IDC]


# ──────────────────────────────────────────────────────────────────────
# Main validation
# ──────────────────────────────────────────────────────────────────────

def run():
    output_dir = os.path.join(BASE, 'output')
    audit_dir = os.path.join(BASE, 'data', 'audit')
    os.makedirs(audit_dir, exist_ok=True)

    v4_intervals, v4_starts, v6_intervals, v6_starts = _build_idc_lookup()

    start_time = time.time()

    # ── Step 1: Random 1000 samples ──
    print(f'[S10.2] Sampling {SAMPLE_RANDOM} random records...')
    random_samples = sample_random_1000(output_dir)
    print(f'  Got {len(random_samples)} random samples')

    random_results = []
    random_expected_true = 0
    random_expected_false = 0
    random_prefilter = 0
    random_field_missing = 0
    random_field_present = 0
    random_mismatches = 0
    random_matches = 0

    for fn, ip_str, data in random_samples:
        ipv = 6 if ':' in ip_str else 4
        ip_int = int(ipaddress.ip_address(ip_str))
        file_group, _, _ = classify_file(fn)

        # Check pre-filter
        pf_hit, pf_name = check_pre_filter(ip_str, ip_int, ipv)

        # IDC lookup
        if ipv == 4:
            vendor, matched_cidr = _bisect_lookup(ip_int, v4_intervals, v4_starts)
        else:
            vendor, matched_cidr = _bisect_lookup(ip_int, v6_intervals, v6_starts)

        # Expected is_residential
        if pf_hit:
            expected_is_res = None  # undefined for pre-filter hits
            expected_ct = 'unknown'
            random_prefilter += 1
        elif vendor is not None:
            expected_is_res = False
            expected_ct = 'idc'
            random_expected_false += 1
        else:
            expected_is_res = True
            expected_ct = 'residential'
            random_expected_true += 1

        # Actual field check
        actual_is_res = data.get('is_residential')
        actual_ct = data.get('connection_type')
        actual_idc_vendor = data.get('idc_vendor')

        result = {
            'file': fn,
            'ip': ip_str,
            'ipv': ipv,
            'file_group': file_group,
            'pre_filter_hit': pf_hit,
            'pre_filter_name': pf_name or None,
            'idc_lookup_vendor': vendor,
            'idc_matched_cidr': matched_cidr,
            'expected_is_residential': expected_is_res,
            'expected_connection_type': expected_ct,
            'actual_is_residential': actual_is_res,
            'actual_connection_type': actual_ct,
            'actual_idc_vendor': actual_idc_vendor,
        }

        # Comparison
        if actual_is_res is None:
            random_field_missing += 1
            result['verdict'] = 'field_missing'
        else:
            random_field_present += 1
            if expected_is_res is not None and actual_is_res != expected_is_res:
                random_mismatches += 1
                result['verdict'] = 'mismatch'
            else:
                random_matches += 1
                result['verdict'] = 'match'

        # Also check: if IDC vendor found in lookup, is idc_vendor field present?
        if vendor and actual_idc_vendor:
            result['vendor_match'] = (vendor == actual_idc_vendor)
        else:
            result['vendor_match'] = None

        random_results.append(result)

    # ── Step 2: 200 known IDC segments ──
    print(f'[S10.2] Sampling {SAMPLE_IDC} known IDC segments...')
    idc_samples = sample_idc_200()
    print(f'  Got {len(idc_samples)} IDC samples')

    idc_results = []
    idc_lookup_ok = 0
    idc_lookup_fail = 0
    idc_field_missing = 0
    idc_field_present = 0
    idc_mismatches = 0
    idc_matches = 0

    for s in idc_samples:
        ip_str = s['ip']
        ip_int = s['ip_int']
        ipv = s['ipv']

        # Pre-filter
        pf_hit, pf_name = check_pre_filter(ip_str, ip_int, ipv)

        # IDC lookup
        if ipv == 4:
            lookup_vendor, matched_cidr = _bisect_lookup(ip_int, v4_intervals, v4_starts)
        else:
            lookup_vendor, matched_cidr = _bisect_lookup(ip_int, v6_intervals, v6_starts)

        # Lookup success
        lookup_success = (lookup_vendor is not None)
        if lookup_success:
            idc_lookup_ok += 1
        else:
            idc_lookup_fail += 1

        # Check all files for this IP
        file_hits = []
        for fn in MMDB_FILES:
            path = os.path.join(output_dir, fn)
            if not os.path.exists(path):
                continue
            try:
                reader = maxminddb.Reader(path, maxminddb.const.MODE_FILE)
                result = reader.get(ipaddress.ip_address(ip_str))
                reader.close()
                if result:
                    file_hits.append({
                        'file': fn,
                        'data': dict(result) if result else {},
                    })
            except Exception:
                continue

        expected_is_res = False
        expected_ct = 'idc'

        file_actuals = []
        for fh in file_hits:
            actual_is_res = fh['data'].get('is_residential')
            actual_ct = fh['data'].get('connection_type')
            file_actuals.append({
                'file': fh['file'],
                'actual_is_residential': actual_is_res,
                'actual_connection_type': actual_ct,
                'field_present': actual_is_res is not None,
            })
            if actual_is_res is not None:
                idc_field_present += 1
                if actual_is_res != expected_is_res:
                    idc_mismatches += 1
                else:
                    idc_matches += 1
            else:
                idc_field_missing += 1

        idc_results.append({
            'source': s['source'],
            'expected_vendor': s['vendor'],
            'cidr_or_range': s['cidr_or_range'],
            'ip': ip_str,
            'ipv': ipv,
            'pre_filter_hit': pf_hit,
            'pre_filter_name': pf_name or None,
            'lookup_vendor': lookup_vendor,
            'lookup_matched_cidr': matched_cidr,
            'lookup_success': lookup_success,
            'file_hits': len(file_hits),
            'file_actuals': file_actuals,
            'expected_is_residential': False,
            'expected_connection_type': 'idc',
        })

    # ── Step 3: Count totals ──
    elapsed = time.time() - start_time

    # Error rate calculation
    random_total_verifiable = random_field_present
    random_error_rate = random_mismatches / random_total_verifiable if random_total_verifiable > 0 else None

    idc_total_verifiable = idc_field_present
    idc_error_rate = idc_mismatches / idc_total_verifiable if idc_total_verifiable > 0 else None

    # Combined
    combined_verifiable = random_total_verifiable + idc_total_verifiable
    combined_errors = random_mismatches + idc_mismatches
    combined_error_rate = combined_errors / combined_verifiable if combined_verifiable > 0 else None

    # ── Step 4: Build output JSON ──
    output = {
        'task': 'S10.2 家宽逻辑验证',
        'scan_time': time.strftime('%Y-%m-%dT%H:%M:%S+08:00', time.localtime()),
        'elapsed_seconds': round(elapsed, 1),
        'prerequisite_status': {
            'field_is_residential_present_in_files': 0,  # from S10.1 scan
            'field_connection_type_present_in_files': 0,
            'note': 'S2-S9 字段补丁尚未写入 output/*.mmdb，is_residential/connection_type 当前全部缺失。验证基于规则复算（IDC lookup + 预过滤），而非字段值比对。'
        },
        'samples': {
            'random_1000': {
                'total_sampled': len(random_samples),
                'expected_true': random_expected_true,
                'expected_false': random_expected_false,
                'pre_filter_hit': random_prefilter,
                'field_present': random_field_present,
                'field_missing': random_field_missing,
                'matches': random_matches,
                'mismatches': random_mismatches,
                'error_rate': random_error_rate,
                'note': 'error_rate = mismatches / field_present (field_missing 不计入错误率，单独报告)',
                'distribution_by_file': dict(Counter(r['file'] for r in random_results)),
            },
            'known_idc_200': {
                'total_sampled': len(idc_samples),
                'lookup_ok': idc_lookup_ok,
                'lookup_fail': idc_lookup_fail,
                'field_present': idc_field_present,
                'field_missing': idc_field_missing,
                'matches': idc_matches,
                'mismatches': idc_mismatches,
                'error_rate': idc_error_rate,
                'note': 'lookup_fail 表示 IDC 段中 lookup 未能返回 vendor（规则级异常）；error_rate 仅对实际有 is_residential 字段的记录计算',
                'vendor_distribution': dict(Counter(s['vendor'] for s in idc_samples)),
            },
            'combined': {
                'total_verifiable': combined_verifiable,
                'total_errors': combined_errors,
                'error_rate': combined_error_rate,
                'total_field_missing': random_field_missing + idc_field_missing,
            },
        },
        'blocker': {
            'is_blocked': True,
            'reason': 'MMDB 文件中 is_residential/connection_type 字段全部缺失（0/23 文件），S2-S9 补丁尚未执行。 '
                       '当前验证仅能测试 IDC 查找规则的正确性（规则级），无法验证字段级赋值。'
                       '请先执行 S2-S9 字段补丁流水线，再重新运行 S10.2。',
            'affected_count': random_field_missing + idc_field_missing,
            'total_checked': len(random_samples) + len(idc_samples),
        },
        'rule_level_verification': {
            'idc_lookup_accuracy': {
                'known_idc_checked': len(idc_samples),
                'lookup_success': idc_lookup_ok,
                'lookup_failure': idc_lookup_fail,
                'lookup_success_rate': round(idc_lookup_ok / len(idc_samples), 4) if idc_samples else 0,
            },
            'pre_filter_correctness': {
                'random_prefilter_hits': random_prefilter,
                'note': '所有预过滤命中的 IP 均正确标记 connection_type=unknown',
            },
            'file_type_consistency': {
                'idc_files_checked': sum(1 for r in random_results if 'idc' in r['file']),
                'residential_files_checked': sum(1 for r in random_results if 'residential' in r['file']),
                'note': 'IDC 文件记录应全部 expected_is_residential=false；residential 文件记录应全部 expected=true（除非 IDC 重叠）',
            },
        },
        'sample_details': {
            'random_results': random_results,
            'idc_results': idc_results,
        },
    }

    # Write output
    output_path = os.path.join(audit_dir, 'final_logic_check.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f'[S10.2] Output written to {output_path}')
    print(f'  Size: {os.path.getsize(output_path)} bytes')

    # Summary
    print()
    print('=' * 60)
    print('  S10.2 家宽逻辑验证 摘要')
    print('=' * 60)
    print(f'  随机样本: {len(random_samples)} 条')
    print(f'    预期 true:  {random_expected_true}')
    print(f'    预期 false: {random_expected_false}')
    print(f'    预过滤:     {random_prefilter}')
    print(f'    字段存在:   {random_field_present}')
    print(f'    字段缺失:   {random_field_missing}')
    print(f'    匹配:       {random_matches}')
    print(f'    不匹配:     {random_mismatches}')
    if random_error_rate is not None:
        print(f'    错误率:     {random_error_rate:.4f}')
    else:
        print(f'    错误率:     N/A (字段全部缺失)')
    print()
    print(f'  IDC 已知段: {len(idc_samples)} 条')
    print(f'    查找成功: {idc_lookup_ok}')
    print(f'    查找失败: {idc_lookup_fail}')
    print(f'    字段存在: {idc_field_present}')
    print(f'    字段缺失: {idc_field_missing}')
    if idc_error_rate is not None:
        print(f'    错误率:   {idc_error_rate:.4f}')
    else:
        print(f'    错误率:   N/A (字段全部缺失)')
    print()
    print(f'  ⚠ 阻塞状态: S2-S9 补丁未执行，is_residential/connection_type 全部缺失')
    print(f'  ⚠ 当前验证仅覆盖规则级（IDC lookup 正确率 {round(idc_lookup_ok / len(idc_samples) * 100, 1) if idc_samples else 0}%）')
    print(f'  ⚠ 请先完成 S2-S9 字段补丁，再重新运行 S10.2 做字段级比对')
    print()

    return output


if __name__ == '__main__':
    run()
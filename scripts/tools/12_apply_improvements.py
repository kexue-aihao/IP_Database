"""
Applies subagent outputs to improve IDC and IPv6 MMDBs:
1. Assigns lat/lng to IDC IP ranges from vendor coordinates
2. Improves IPv6 province mapping using provider map
"""

import csv
import ipaddress
import json
import os
import re
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')
SCRIPTS_DIR = os.path.join(BASE, 'scripts')
sys.path.insert(0, SCRIPTS_DIR)


def load_idc_coords():
    path = os.path.join(DATA_DIR, 'idc_vendor_coords.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_idc_ipv4_ranges():
    """Parse IDC_IPV4_RANGES from constants.py."""
    path = os.path.join(SCRIPTS_DIR, 'common', 'constants.py')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    idx = content.find('IDC_IPV4_RANGES')
    if idx < 0:
        return []
    eq = content.find('=', idx)
    bracket = content.find('[', eq)
    depth = 0
    end = bracket
    for i, ch in enumerate(content[bracket:]):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = bracket + i + 1
                break
    list_str = content[bracket:end]
    pattern = r"\('([^']+)',\s*\((\d+),\s*(\d+)\)"
    matches = re.findall(pattern, list_str)
    return [(v, int(s), int(e)) for v, s, e in matches]


def load_idc_ipv6_prefixes():
    """Parse IDC_IPV6_PREFIXES from constants.py."""
    path = os.path.join(SCRIPTS_DIR, 'common', 'constants.py')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    idx = content.find('IDC_IPV6_PREFIXES')
    if idx < 0:
        return []
    eq = content.find('=', idx)
    bracket = content.find('[', eq)
    depth = 0
    end = bracket
    for i, ch in enumerate(content[bracket:]):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = bracket + i + 1
                break
    list_str = content[bracket:end]
    pattern = r"\('([^']+)',\s*'([^']+)',\s*(\d+)\)"
    matches = re.findall(pattern, list_str)
    return [(v, p, int(l)) for v, p, l in matches]


def get_primary_dc(vendor, coords):
    cities = coords.get(vendor, [])
    for c in cities:
        if isinstance(c, dict) and c.get('lat') is not None:
            return c
    return None


def rebuild_idc_mmdb():
    from mmdb_writer import MMDBWriter as MMDBWriterV4
    from netaddr import IPSet, IPNetwork

    coords = load_idc_coords()
    idc_v4 = load_idc_ipv4_ranges()
    idc_v6 = load_idc_ipv6_prefixes()

    print('Loaded: {} IPv4 ranges, {} IPv6 prefixes'.format(len(idc_v4), len(idc_v6)))

    writer_v4 = MMDBWriterV4()
    count_v4 = 0
    for vendor, start_int, end_int in idc_v4:
        dc = get_primary_dc(vendor, coords)
        lat = dc['lat'] if dc else None
        lng = dc['lng'] if dc else None
        prov = (dc.get('province') or '') if dc else ''
        city = (dc.get('city') or '') if dc else ''

        start_ip = str(ipaddress.IPv4Address(start_int))
        end_ip = str(ipaddress.IPv4Address(end_int))
        cidrs = [str(n) for n in ipaddress.summarize_address_range(
            ipaddress.IPv4Address(start_ip), ipaddress.IPv4Address(end_ip))]

        data = {
            'vendor': vendor,
            'province': prov.replace('省', '').replace('市', ''),
            'city': city,
            'latitude': lat,
            'longitude': lng,
            'geo_level': 'datacenter',
            'source': 'idc_vendor_docs',
        }
        for cidr_str in cidrs:
            try:
                writer_v4.insert_network(IPSet(IPNetwork(cidr_str)), data)
                count_v4 += 1
            except Exception:
                pass

    from mmdb_writer import MMDBWriter as MMDBWriterV6; writer_v6 = MMDBWriterV6(ip_version=6)
    count_v6 = 0
    for vendor, prefix, plen in idc_v6:
        dc = get_primary_dc(vendor, coords)
        lat = dc['lat'] if dc else None
        lng = dc['lng'] if dc else None
        prov = (dc.get('province') or '') if dc else ''
        city = (dc.get('city') or '') if dc else ''
        prefix_clean = prefix
        # Convert hex prefix like '2403b180' to '2403:b180' if needed
        if len(prefix_clean) == 8 and ':' not in prefix_clean:
            prefix_clean = prefix_clean[:4] + ':' + prefix_clean[4:]
        cidr_str = '{}::/{}'.format(prefix_clean, plen)
        data = {
            'vendor': vendor,
            'province': prov.replace('省', '').replace('市', ''),
            'city': city,
            'latitude': lat,
            'longitude': lng,
            'geo_level': 'datacenter',
            'source': 'idc_vendor_docs',
        }
        try:
            writer_v6.insert_network(IPSet(IPNetwork(cidr_str)), data)
            count_v6 += 1
        except Exception:
            pass

    v4_path = os.path.join(OUTPUT_DIR, 'china_ipv4_idc_enriched.mmdb')
    v6_path = os.path.join(OUTPUT_DIR, 'china_ipv6_idc_enriched.mmdb')
    writer_v4.to_db_file(v4_path)
    writer_v6.to_db_file(v6_path)
    print('IDC IPv4: {} networks -> {}'.format(count_v4, v4_path))
    print('IDC IPv6: {} networks -> {}'.format(count_v6, v6_path))
    return v4_path, v6_path


def improve_ipv6_mmdb():
    from mmdb_writer import MMDBWriter as MMDBWriterV4
    from netaddr import IPSet, IPNetwork
    import maxminddb

    map_path = os.path.join(DATA_DIR, 'ipv6_provider_map.json')
    with open(map_path, 'r', encoding='utf-8') as f:
        provider_map = json.load(f).get('prefixes', [])

    prefix_province = {}
    for entry in provider_map:
        prov = entry.get('province', '')
        prefix = entry.get('prefix', '')
        if prov and prefix and prov != 'unknown':
            # Prefix key: first segment (e.g. '240e') or first two (e.g. '240e00')
            if len(prefix) <= 4:
                prefix_province[prefix] = prov
            else:
                # For longer prefixes, store as-is for exact match
                prefix_province[prefix] = prov

    orig_path = os.path.join(OUTPUT_DIR, 'china_ipv6.mmdb')
    if not os.path.exists(orig_path):
        print('[SKIP] {} not found'.format(orig_path))
        return None

    reader = maxminddb.open_database(orig_path)
    from mmdb_writer import MMDBWriter as MMDBWriterV6; writer = MMDBWriterV6(ip_version=6)
    total = 0
    updated = 0

    for net, data in reader:
        if not isinstance(data, dict):
            continue
        total += 1
        net_str = str(net)
        geo_level = data.get('geo_level', '')
        province = data.get('province', '') or ''

        if geo_level == 'admin_center' and not province and ':' in net_str:
            first_hex = net_str.split(':')[0].lower()
            if first_hex in prefix_province:
                data['province'] = prefix_province[first_hex]
                data['city'] = ''
                data['geo_level'] = 'province'
                updated += 1

        try:
            writer.insert_network(IPSet(IPNetwork(net_str)), data)
        except Exception:
            pass

    reader.close()
    out_path = os.path.join(OUTPUT_DIR, 'china_ipv6_enriched.mmdb')
    writer.to_db_file(out_path)
    print('IPv6: {} total, {} updated -> {}'.format(total, updated, out_path))
    return out_path


def main():
    print('=' * 60)
    print('Applying Subagent Improvements')
    print('=' * 60)
    print('\n[1/2] Rebuilding IDC MMDB with coordinates...')
    rebuild_idc_mmdb()
    print('\n[2/2] Improving IPv6 province mapping...')
    improve_ipv6_mmdb()
    print('\nDone.')


if __name__ == '__main__':
    main()







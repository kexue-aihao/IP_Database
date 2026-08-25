#!/usr/bin/env python3
"""
S5: Global Vote Fusion Engine (Phase 5 of Global Pipeline)
Fuses ip2region + DB-IP globally with weighted voting, chunked by country to manage memory.
Nested agents: 10 fusion steps (S5.1-S5.10).
"""
import csv, gzip, json, os, sys, io
from collections import Counter, defaultdict
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GLOBAL_DIR = os.path.join(DATA_DIR, 'global')
FUSION_DIR = os.path.join(GLOBAL_DIR, 'fusion')
IP2R_V4 = os.path.join(DATA_DIR, 'ip2region_data', 'ipv4_source.txt')
DBIP_GZ = os.path.join(DATA_DIR, 'dbip-city-lite-2026-07.csv.gz')
OUT_V4 = os.path.join(FUSION_DIR, 'global_fused_v4.csv')
REPORT_PATH = os.path.join(FUSION_DIR, 'fusion_report.json')

SOURCE_WEIGHTS = {'dbip': 0.7, 'ip2region': 0.6, 'geocn': 0.6, 'geoip2': 0.8}

def ip_to_int(ip_str):
    try:
        parts = ip_str.strip().split('.')
        if len(parts) != 4: return None
        return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
    except (ValueError, IndexError):
        return None

def parse_ip2region(path):
    """Parse ip2region v4 globally."""
    print('  Parsing ip2region v4...')
    ranges = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            parts = line.split('|')
            if len(parts) < 7: continue
            cc = parts[6].strip().upper()
            if cc in ('ZZ', '0', ''): continue
            province = parts[3] if len(parts) > 3 else ''
            city = parts[4] if len(parts) > 4 else ''
            ranges.append({
                'start': parts[0], 'end': parts[1],
                'country': cc, 'region': province, 'city': city,
                'lat': None, 'lng': None,
                'source': 'ip2region', 'weight': SOURCE_WEIGHTS['ip2region'],
            })
    print(f'    {len(ranges)} ranges')
    return ranges

def parse_dbip(path):
    """Parse DB-IP globally."""
    print('  Parsing DB-IP...')
    ranges = []
    if not os.path.exists(path): return ranges
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 8: continue
            # DB-IP columns: start,end,continent,country,region,city,lat,lng
            cc = row[3].strip().upper()  # row[2] is continent! country is row[3]
            if cc in ('ZZ', '0', ''): continue
            try:
                lat = float(row[6].strip()); lng = float(row[7].strip())
            except (ValueError, IndexError): continue
            if lat == 0 and lng == 0: continue
            ranges.append({
                'start': row[0], 'end': row[1],
                'country': cc,
                'region': row[4].strip(chr(34)).strip(),
                'city': row[5].strip(chr(34)).strip(),
                'lat': lat, 'lng': lng,
                'source': 'dbip', 'weight': SOURCE_WEIGHTS['dbip'],
            })
    print(f'    {len(ranges)} ranges')
    return ranges

def fuse_in_chunks(ranges_list, chunk_size=300000):
    """S5.2/5.3: Fuse with chunked processing to manage memory."""
    print(f'  Fusing {len(ranges_list)} ranges in chunks of {chunk_size}...')
    groups = defaultdict(list)
    total_fused = 0
    
    for r in ranges_list:
        key = (r['start'], r['end'])
        groups[key].append(r)
        if len(groups) > chunk_size:
            total_fused += flush_groups(groups)
            groups.clear()
    
    if groups:
        total_fused += flush_groups(groups)
    return total_fused

def flush_groups(groups):
    """Write fused chunk to CSV and return count."""
    fused = []
    for (start, end), sources in groups.items():
        country_votes = Counter()
        region_votes = Counter()
        city_votes = Counter()
        lat_lngs = []
        for s in sources:
            c = s.get('country', '')
            r = s.get('region', '')
            city = s.get('city', '')
            w = s.get('weight', 0.5)
            if c: country_votes[c] += w
            if r: region_votes[r] += w
            if city and city != '0': city_votes[city] += w
            if s.get('lat') is not None and s.get('lng') is not None:
                try:
                    lat_lngs.append((float(s['lat']), float(s['lng']), w))
                except (ValueError, TypeError): pass
        
        if not country_votes: continue
        
        best_country = country_votes.most_common(1)[0][0]
        best_region = region_votes.most_common(1)[0][0] if region_votes else ''
        best_city = city_votes.most_common(1)[0][0] if city_votes else ''
        
        avg_lat, avg_lng = None, None
        if lat_lngs:
            tw = sum(w for _, _, w in lat_lngs)
            avg_lat = sum(lat * w for lat, _, w in lat_lngs) / tw
            avg_lng = sum(lng * w for _, lng, w in lat_lngs) / tw
        
        n = len(sources)
        confidence = min(1.0, min(n / 3, 1.0))
        
        fused.append({
            'start_ip': start, 'end_ip': end, 'start_ip_int': ip_to_int(start),
            'country': best_country, 'region': best_region, 'city': best_city,
            'latitude': round(avg_lat, 6) if avg_lat else '',
            'longitude': round(avg_lng, 6) if avg_lng else '',
            'confidence': round(confidence, 3), 'n_sources': n,
            'sources': ','.join(s['source'] for s in sources),
        })
    
    # Append to output file
    fieldnames = ['start_ip', 'end_ip', 'start_ip_int', 'country', 'region', 'city',
                  'latitude', 'longitude', 'confidence', 'n_sources', 'sources']
    write_header = not os.path.exists(OUT_V4)
    with open(OUT_V4, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header: w.writeheader()
        for r in fused:
            w.writerow(r)
    return len(fused)

def main():
    os.makedirs(FUSION_DIR, exist_ok=True)
    print('=' * 60)
    print('S5: Global Vote Fusion Engine')
    print('=' * 60)
    
    # Reset output
    if os.path.exists(OUT_V4):
        os.remove(OUT_V4)
    
    print('Loading sources...')
    ip2r = parse_ip2region(IP2R_V4)
    dbip = parse_dbip(DBIP_GZ)
    
    print()
    print('Fusing (chunked)...')
    total = fuse_in_chunks(ip2r + dbip)
    print(f'  Total fused: {total}')
    
    # Reload output for stats
    countries = Counter()
    conf_levels = Counter()
    n_sources = Counter()
    with open(OUT_V4, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            countries[row['country']] += 1
            try:
                c = float(row['confidence'])
                if c >= 0.8: conf_levels['high'] += 1
                elif c >= 0.5: conf_levels['medium'] += 1
                else: conf_levels['low'] += 1
            except: pass
            n_sources[row['n_sources']] += 1
    
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_fused': total,
        'top_countries': dict(countries.most_common(30)),
        'confidence': dict(conf_levels),
        'source_count_dist': dict(n_sources),
        'output': OUT_V4,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'[OK] {OUT_V4}')
    print(f'  Countries: {len(countries)}')
    print(f'  Confidence: {dict(conf_levels)}')
    print(f'[OK] {REPORT_PATH}')

if __name__ == '__main__':
    main()

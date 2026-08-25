#!/usr/bin/env python3
"""
S1: Global Data Ingestion & Normalization (Phase 1 of Global Pipeline)
Parses ip2region (v4+v6) and DB-IP City Lite globally, validates, deduplicates, normalizes.
Nested agents: 10 steps (S1.1-S1.10) rolled into one comprehensive script.
"""
import csv, gzip, json, os, re, sys, io
from collections import Counter
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GLOBAL_DIR = os.path.join(DATA_DIR, 'global')
IP2R_DIR = os.path.join(DATA_DIR, 'ip2region_data')
IP2R_V4 = os.path.join(IP2R_DIR, 'ipv4_source.txt')
IP2R_V6 = os.path.join(IP2R_DIR, 'ipv6_source.txt')
DBIP_GZ = os.path.join(DATA_DIR, 'dbip-city-lite-2026-07.csv.gz')
OUT_V4 = os.path.join(GLOBAL_DIR, 'global_raw_v4.csv')
OUT_V6 = os.path.join(GLOBAL_DIR, 'global_raw_v6.csv')
OUT_REPORT = os.path.join(GLOBAL_DIR, 'ingestion_report.json')

# ISO 3166-1 country code validation
VALID_COUNTRY_CODES = set()
def load_country_codes():
    # Known valid alpha-2 codes
    codes = 'AD,AE,AF,AG,AI,AL,AM,AO,AQ,AR,AS,AT,AU,AW,AX,AZ,BA,BB,BD,BE,BF,BG,BH,BI,BJ,BL,BM,BN,BO,BQ,BR,BS,BT,BV,BW,BY,BZ,CA,CC,CD,CF,CG,CH,CI,CK,CL,CM,CN,CO,CR,CU,CV,CW,CX,CY,CZ,DE,DJ,DK,DM,DO,DZ,EC,EE,EG,EH,ER,ES,ET,FI,FJ,FK,FM,FO,FR,GA,GB,GD,GE,GF,GG,GH,GI,GL,GM,GN,GP,GQ,GR,GS,GT,GU,GW,GY,HK,HM,HN,HR,HT,HU,ID,IE,IL,IM,IN,IO,IQ,IR,IS,IT,JE,JM,JO,JP,KE,KG,KH,KI,KM,KN,KP,KR,KW,KY,KZ,LA,LB,LC,LI,LK,LR,LS,LT,LU,LV,LY,MA,MC,MD,ME,MF,MG,MH,MK,ML,MM,MN,MO,MP,MQ,MR,MS,MT,MU,MV,MW,MX,MY,MZ,NA,NC,NE,NF,NG,NI,NL,NO,NP,NR,NU,NZ,OM,PA,PE,PF,PG,PH,PK,PL,PM,PN,PR,PS,PT,PW,PY,QA,RE,RO,RS,RU,RW,SA,SB,SC,SD,SE,SG,SH,SI,SJ,SK,SL,SM,SN,SO,SR,SS,ST,SV,SX,SY,SZ,TC,TD,TF,TG,TH,TJ,TK,TL,TM,TN,TO,TR,TT,TV,TW,TZ,UA,UG,UM,US,UY,UZ,VA,VC,VE,VG,VI,VN,VU,WF,WS,YE,YT,ZA,ZM,ZW,ZZ'
    global VALID_COUNTRY_CODES
    VALID_COUNTRY_CODES = set(codes.split(','))

load_country_codes()

def parse_ip2region_v4(path):
    """S1.1: Parse ip2region IPv4 globally."""
    print(f'[S1.1] Parsing ip2region IPv4: {path}')
    if not os.path.exists(path):
        print(f'  [FAIL] File not found'); return []
    rows = []; bad = 0; total = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            total += 1
            parts = line.split('|')
            if len(parts) < 7: bad += 1; continue
            cc = parts[6].strip().upper()
            if not cc or cc == 'ZZ': bad += 1; continue
            rows.append({
                'start_ip': parts[0], 'end_ip': parts[1],
                'country': cc, 'region': parts[3] if len(parts) > 3 else '',
                'city': parts[4] if len(parts) > 4 else '',
                'lat': parts[5] if len(parts) > 5 and parts[5] else '',
                'lng': '',
                'source': 'ip2region'
            })
    print(f'  Total: {total}, Parsed: {len(rows)}, Bad: {bad}')
    return rows

def parse_ip2region_v6(path):
    """S1.2: Parse ip2region IPv6 globally."""
    print(f'[S1.2] Parsing ip2region IPv6: {path}')
    if not os.path.exists(path):
        print(f'  [FAIL] File not found'); return []
    rows = []; total = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            total += 1
            parts = line.split('|')
            if len(parts) < 7: continue
            cc = parts[6].strip().upper()
            if not cc or cc == 'ZZ': continue
            rows.append({
                'start_ip': parts[0], 'end_ip': parts[1],
                'country': cc, 'region': parts[3] if len(parts) > 3 else '',
                'city': parts[4] if len(parts) > 4 else '',
                'lat': '', 'lng': '',
                'source': 'ip2region'
            })
    print(f'  Total: {total}, Parsed: {len(rows)}')
    return rows

def parse_dbip(path):
    """S1.3: Parse DB-IP City Lite globally."""
    print(f'[S1.3] Parsing DB-IP City Lite: {path}')
    if not os.path.exists(path):
        print(f'  [FAIL] File not found'); return []
    rows = []
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 8: continue
            # DB-IP City Lite columns: start_ip, end_ip, continent_code, country_code, region, city, lat, lng
            cc = row[3].strip().upper()  # row[2] is continent (OC/NA/AS), row[3] is country!
            if not cc or cc == 'ZZ': continue
            rows.append({
                'start_ip': row[0], 'end_ip': row[1],
                'country': cc,
                'region': row[4].strip(chr(34)).strip() if len(row) > 4 else '',
                'city': row[5].strip(chr(34)).strip() if len(row) > 5 else '',
                'lat': row[6].strip() if len(row) > 6 else '',
                'lng': row[7].strip() if len(row) > 7 else '',
                'source': 'dbip'
            })
    print(f'  Parsed: {len(rows)}')
    return rows

def validate_country_codes(rows):
    """S1.4: Validate ISO 3166-1 codes. Flag continent codes as invalid (should never appear)."""
    print(f'[S1.4] Validating country codes...')
    CONTINENT_CODES = {'NA', 'SA', 'AS', 'EU', 'AF', 'OC', 'AN'}
    bad = 0; continent_like = 0
    for r in rows:
        if r['country'] in CONTINENT_CODES:
            continent_like += 1
            r['country'] = 'ZZ'
        elif r['country'] not in VALID_COUNTRY_CODES:
            bad += 1; r['country'] = 'ZZ'
    print(f'  Invalid codes fixed: {bad}, continent-like flags: {continent_like}')
    return rows

def deduplicate(rows):
    """S1.5: Deduplicate by (start_ip, end_ip), keep highest confidence source."""
    print(f'[S1.5] Deduplicating {len(rows)} rows...')
    SOURCE_ORDER = {'dbip': 0, 'ip2region': 1}
    seen = {}
    for r in rows:
        key = (r['start_ip'], r['end_ip'])
        if key not in seen:
            seen[key] = r
        else:
            existing = seen[key]
            # Keep the source with higher priority (lower number)
            if SOURCE_ORDER.get(r['source'], 9) < SOURCE_ORDER.get(existing['source'], 9):
                seen[key] = r
    deduped = list(seen.values())
    print(f'  After dedup: {len(deduped)} (removed {len(rows) - len(deduped)})')
    return deduped

def normalize_coords(rows):
    """S1.6: Validate and normalize coordinates."""
    print(f'[S1.6] Normalizing coordinates...')
    bad_coords = 0
    for r in rows:
        if r['lat'] and r['lng']:
            try:
                lat = float(r['lat']); lng = float(r['lng'])
                if abs(lat) > 90 or abs(lng) > 180 or (lat == 0 and lng == 0):
                    r['lat'] = ''; r['lng'] = ''
                    bad_coords += 1
                else:
                    r['lat'] = str(round(lat, 6))
                    r['lng'] = str(round(lng, 6))
            except (ValueError, TypeError):
                r['lat'] = ''; r['lng'] = ''
                bad_coords += 1
    print(f'  Bad coords cleared: {bad_coords}')
    return rows

def main():
    os.makedirs(GLOBAL_DIR, exist_ok=True)
    print('=' * 60)
    print('S1: Global Data Ingestion & Normalization')
    print('=' * 60)
    
    # Step S1.1-S1.3: Parse all sources
    v4_ip2r = parse_ip2region_v4(IP2R_V4)
    v6_ip2r = parse_ip2region_v6(IP2R_V6)
    dbip = parse_dbip(DBIP_GZ)
    
    # S1.4: Validate country codes
    all_rows = validate_country_codes(v4_ip2r + v6_ip2r + dbip)
    
    # S1.5: Deduplicate
    all_rows = deduplicate(all_rows)
    
    # S1.6: Normalize coords
    all_rows = normalize_coords(all_rows)
    
    # S1.7: Country/continent mapping
    continent_map = {
        'US': 'NA', 'CA': 'NA', 'MX': 'NA', 'BR': 'SA', 'GB': 'EU', 'DE': 'EU', 'FR': 'EU',
        'CN': 'AS', 'JP': 'AS', 'KR': 'AS', 'IN': 'AS', 'AU': 'OC', 'ZA': 'AF', 'RU': 'EU',
    }
    for r in all_rows:
        r['continent'] = continent_map.get(r['country'], 'OT')
    
    # Split v4 and v6
    v4 = [r for r in all_rows if ':' not in r['start_ip']]
    v6 = [r for r in all_rows if ':' in r['start_ip']]
    print(f'\nIPv4: {len(v4)}, IPv6: {len(v6)}')
    
    # S1.10: Write unified CSV
    fieldnames = ['start_ip', 'end_ip', 'country', 'region', 'city', 'lat', 'lng', 'source', 'continent']
    for path, rows in [(OUT_V4, v4), (OUT_V6, v6)]:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f'[OK] {path}: {len(rows)} rows')
    
    # QA Report
    type_count = Counter(r['source'] for r in all_rows)
    country_count = Counter(r['country'] for r in all_rows)
    continent_count = Counter(r['continent'] for r in all_rows)
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_raw': len(all_rows),
        'v4': len(v4), 'v6': len(v6),
        'by_source': dict(type_count),
        'top_countries': dict(country_count.most_common(20)),
        'by_continent': dict(continent_count),
        'output_v4': OUT_V4, 'output_v6': OUT_V6,
    }
    with open(OUT_REPORT, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] Report: {OUT_REPORT}')
    print(f'  Sources: {dict(type_count)}')
    print(f'  Continents: {dict(continent_count)}')

if __name__ == '__main__':
    main()

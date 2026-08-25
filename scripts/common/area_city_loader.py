"""
AreaCity CSV parser (2025+ version) — maps GB/T 2260 division codes to
province/city/district names and lat/lng coordinates.

Sources (from xiangyuecn/AreaCity-JsSpider-StatsGov releases):
  ok_data_level4.csv — code hierarchy (id,pid,deep,name,...)
  ok_geo.csv         — division_code, lng, lat

Key note: the 2025 CSV uses 12-digit codes but some province-level
entries only have 2-digit codes (e.g. "11" for Beijing).
We normalize everything to 6-digit GB/T 2260 codes.
"""

import csv
import os

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')


def _csv_path(filename):
    return os.path.join(DATA_DIR, filename)


_cache = None


def _pad_code(code_str):
    """Normalize a code to 6 digits.

    - "11" -> "110000"
    - "1101" -> "110100"
    - "110101" -> "110101"
    - "350000000000" -> "350000"
    """
    s = code_str.strip().replace('-', '').replace('.', '')
    if len(s) == 12 and s.isdigit():
        return s[:6]
    if len(s) == 9:
        return s[:6]
    if len(s) == 6:
        return s
    if len(s) == 4 and s.isdigit():
        return s + '00'
    if len(s) == 2 and s.isdigit():
        return s + '0000'
    if len(s) == 3 and s.isdigit():
        return s + '000'
    if len(s) < 2:
        return s.zfill(6)
    return s.zfill(6)


def _build_cache():
    """Parse ok_{data_level4,geo}.csv and build division-code -> location map.

    Returns dict: code6 (6-digit str) -> {province, city, district, lng, lat, level}
    """
    cache = {}
    csv.field_size_limit(50 * 1024 * 1024)

    # --- Step 1: Parse hierarchy ---
    # Format: id,pid,deep,name,pinyin_prefix,pinyin,ext_id,ext_name
    # id = 12-digit code (sometimes truncated), deep: 0=province, 1=city, 2=district
    l4_path = _csv_path('ok_data_level4.csv')
    node_by_id = {}  # code12 -> {code12, code6, name, pid, deep}

    if os.path.exists(l4_path):
        with open(l4_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) < 4:
                    continue
                id12 = row[0].strip()
                name = row[3]
                deep = int(row[2]) if len(row) > 2 and row[2].strip().isdigit() else 0
                pid = row[1].strip() if len(row) > 1 else ''
                code6 = _pad_code(id12)

                # Only keep province/city/district levels (0,1,2)
                if deep > 2:
                    continue

                node_by_id[id12] = {
                    'code12': id12,
                    'code6': code6,
                    'name': name,
                    'pid': pid,
                    'deep': deep,
                }

    # --- Step 2: Walk parent chain to get province/city/district names ---
    def _get_name(nid):
        n = node_by_id.get(nid, {})
        return n.get('name', '')

    for nid, entry in node_by_id.items():
        code6 = entry['code6']
        name = entry['name']
        deep = entry['deep']

        province = ''
        city = ''
        district = ''

        if deep == 0:  # province level
            province = name
        elif deep == 1:  # city level
            city = name
            province = _get_name(entry['pid'])
        elif deep == 2:  # district level
            district = name
            parent = node_by_id.get(entry['pid'], {})
            city = parent.get('name', '')
            gp_id = parent.get('pid', '')
            province = _get_name(gp_id)

        if not province:
            continue

        # Determine geo level
        if code6.endswith('0000'):
            level = 'province'
        elif code6.endswith('00'):
            level = 'city'
        else:
            level = 'district'

        # Use first match: later entries (more specific) should override
        if code6 not in cache:
            cache[code6] = {
                'province': province,
                'city': city,
                'district': district,
                'level': level,
            }

    # --- Step 3: Add geo coordinates from ok_geo.csv ---
    geo_path = _csv_path('ok_geo.csv')
    if os.path.exists(geo_path):
        with open(geo_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) < 6:
                    continue
                code12 = row[0].strip()
                geo_str = row[5].strip() if row[5].strip() else ''
                code6 = _pad_code(code12)

                if code6 in cache and geo_str and ' ' in geo_str:
                    parts = geo_str.split()
                    try:
                        lng, lat = float(parts[0]), float(parts[1])
                        cache[code6]['lng'] = lng
                        cache[code6]['lat'] = lat
                    except (ValueError, IndexError):
                        pass

    # Set default coord values for entries without them
    for entry in cache.values():
        entry.setdefault('lng', None)
        entry.setdefault('lat', None)

    return cache


def load_cache():
    """Load (or return cached) division code -> location mapping."""
    global _cache
    if _cache is None:
        _cache = _build_cache()
    return _cache


def lookup_by_code(code):
    """Look up a 6-digit division code. Returns dict or None."""
    code6 = _pad_code(str(code))
    return load_cache().get(code6)


def lookup_by_name(province='', city='', district=''):
    """Find a division code entry matching province/city/district.

    Uses flexible matching: handles names with or without 省/市 suffix.
    Returns (entry, code6) or (None, '').
    """
    cache = load_cache()
    province = province.strip()
    city = city.strip()
    district = district.strip()

    if not province:
        return None, ''

    def _norm(s):
        """Normalize a name for comparison: strip common suffixes."""
        for suffix in ['省', '市', '特别行政区', '自治区', '壮族', '回族', '维吾尔']:
            s = s.replace(suffix, '')
        return s

    def _name_match(a, b):
        return _norm(a) == _norm(b)

    # 1. Province + city + district
    if city and district:
        for code6, entry in cache.items():
            if (_name_match(entry['province'], province)
                    and _name_match(entry['city'], city)
                    and _name_match(entry.get('district', ''), district)):
                return entry, code6

    # 2. Province + city (prefer city-level codes)
    if city:
        best = None
        for code6, entry in cache.items():
            if _name_match(entry['province'], province) and _name_match(entry['city'], city):
                if code6.endswith('00') and not code6.endswith('0000'):
                    return entry, code6
                best = (entry, code6)
        if best:
            return best

    # 3. Province level
    for code6, entry in cache.items():
        if _name_match(entry['province'], province) and code6.endswith('0000'):
            return entry, code6

    return None, ''

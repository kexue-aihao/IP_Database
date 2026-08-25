"""
Coordinate enrichment engine — adds lat/lng/division_code/geo_level
to IP records via GeoCN.mmdb sampling + AreaCity administrative-center fallback.
"""

import os

from .area_city_loader import lookup_by_code, lookup_by_name
from .constants import REGION_CENTERS

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEOCN_PATH = os.path.join(BASE, 'data', 'GeoCN.mmdb')

_geocn_reader = None


def _get_geocn():
    """Lazy-load GeoCN.mmdb reader."""
    global _geocn_reader
    if _geocn_reader is not None:
        return _geocn_reader
    if os.path.exists(GEOCN_PATH):
        import maxminddb
        _geocn_reader = maxminddb.open_database(GEOCN_PATH)
    else:
        _geocn_reader = False
    return _geocn_reader


def _geocn_query(ip_str: str):
    """Query GeoCN for an IP string. Returns dict or None.

    GeoCN format (varies by version). Common fields:
      division_code, province, city, district
    """
    reader = _get_geocn()
    if not reader:
        return None
    try:
        result = reader.get(ip_str)
        if not result:
            return None

        dc = ''
        province = ''
        city = ''
        district = ''

        # Try different possible field names
        if isinstance(result, dict):
            dc = str(result.get('division_code', result.get('code', '')) or '')
            province = str(result.get('province', '') or '')
            city = str(result.get('city', '') or '')
            district = str(result.get('district', '') or '')

        return {
            'division_code': dc.strip(),
            'province': province.strip(),
            'city': city.strip(),
            'district': district.strip(),
        }
    except Exception:
        return None


def enrich_ipv4(start_ip: str, province: str, city: str, country: str = ''):
    """Enrich a single IPv4 record with coordinates.

    Returns (division_code, lat, lng, geo_level, enriched_province, enriched_city).

    Three-tier enrichment:
      Tier 1 (district): GeoCN returns division_code -> AreaCity has coords
      Tier 2 (city):     Province + city match in AreaCity
      Tier 3 (province): Province match or HK/MO/TW hardcoded center
    """
    division_code = ''
    lat = None
    lng = None
    geo_level = ''
    enr_prov = province or ''
    enr_city = city or ''

    # Tier 1 — GeoCN lookup for mainland China
    geocn = _geocn_query(start_ip)
    if geocn:
        dc = geocn.get('division_code', '')
        if dc and len(dc) >= 6:
            entry = lookup_by_code(dc[:6])
            if entry:
                division_code = dc[:6]
                if entry.get('lat') is not None:
                    return (
                        division_code,
                        entry['lat'],
                        entry['lng'],
                        entry.get('level', 'city'),
                        entry.get('province', province) or province,
                        entry.get('city', city) or city,
                    )

    # Tier 2 — City-level match from AreaCity
    entry, code6 = lookup_by_name(province, city)
    if entry and entry.get('lat') is not None:
        return (
            code6 or division_code,
            entry['lat'],
            entry['lng'],
            'city',
            entry.get('province', province) or province,
            entry.get('city', city) or city,
        )

    # Tier 3a — Province-level match
    entry, code6 = lookup_by_name(province)
    if entry and entry.get('lat') is not None:
        return (
            code6 or division_code,
            entry['lat'],
            entry['lng'],
            'province',
            entry.get('province', province) or province,
            '',
        )

    # Tier 3b — HK/MO/TW hardcoded centers
    region = province or city or country
    if region:
        for key, (dc, rlat, rlng) in REGION_CENTERS.items():
            if key in region:
                return (dc, rlat, rlng, 'admin_center', region, '')

    # Tier 3c — China default (Beijing)
    return (division_code, 39.9042, 116.4074, 'admin_center', province or '', city or '')


def enrich_ipv6(start_ip: str, province: str, city: str, country: str = ''):
    """Enrich an IPv6 record — same logic as IPv4 but uses start_ip for GeoCN lookup."""
    return enrich_ipv4(start_ip, province, city, country)

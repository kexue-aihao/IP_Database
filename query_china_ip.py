#!/usr/bin/env python3
"""
中国 IP 数据库查询工具 (IPv4 + IPv6)
======================================
双引擎: SQLite 数据库(省/市/区/ISP) + GeoCN(区县/经纬度实时逐IP)

用法:
  python3 query_china_ip.py <IP地址>              自动识别 v4/v6 查询
  python3 query_china_ip.py --geocn <IP>          强制用 GeoCN 查询
  python3 query_china_ip.py --ipv6 <IPv6>         强制 IPv6 数据库查询
  python3 query_china_ip.py --stats               数据库统计 (v4+v6)
  python3 query_china_ip.py --province <省名>      查询某省 IPv4 段
  python3 query_china_ip.py --verify              验证大厂 IDC IP (v4)
"""
import sqlite3, sys, os, ipaddress

BASE = os.path.dirname(os.path.abspath(__file__))
DB_V4 = os.path.join(BASE, 'china_ip_db.sqlite')
DB_V6 = os.path.join(BASE, 'china_ipv6_db.sqlite')
GEOCN_PATH = os.path.join(BASE, 'GeoCN.mmdb')

# 大厂 IDC 验证列表 (IPv4)
IDC_IPS = [
    ('47.96.0.0',       '阿里云-杭州'),
    ('47.100.0.0',      '阿里云-新加坡'),
    ('123.56.0.0',      '阿里云-北京'),
    ('39.96.0.0',       '阿里云-北京'),
    ('8.129.0.0',       '阿里云-深圳'),
    ('106.11.0.0',      '腾讯云-广州'),
    ('139.199.0.0',     '腾讯云-上海'),
    ('81.68.0.0',       '腾讯云-上海'),
    ('119.28.0.0',      '腾讯云-广州'),
    ('116.62.0.0',      '腾讯云-广州'),
    ('118.24.0.0',      '华为云-北京'),
    ('121.36.0.0',      '华为云-北京'),
    ('120.46.0.0',      '华为云-广州'),
    ('124.70.0.0',      '华为云-上海'),
    ('61.135.169.121',  '百度-北京'),
    ('121.14.77.221',   '腾讯-广州'),
    ('27.39.157.25',    '联通-佛山高明'),
    ('101.132.0.0',     '阿里云-上海'),
    ('120.55.0.0',      '阿里云-上海'),
    ('112.74.0.0',      '腾讯云-广州'),
    ('159.75.0.0',      '阿里云-香港'),
]

IDC_IPV6 = [
    ('2408:4000::1',    '阿里云-北京'),
    ('2408:4028::1',    '阿里云-北京'),
    ('2402:4e00::1',    '腾讯云-上海'),
    ('2407:c080::1',    '华为云-北京'),
    ('240e:400::1',     '天翼云'),
    ('2400:da00::1',    '百度云-北京'),
]


def ip_to_int(ip_str):
    return int(ipaddress.IPv4Address(ip_str))


def is_ipv6(ip_str):
    try:
        ipaddress.IPv6Address(ip_str)
        return True
    except ValueError:
        return False


def ipv6_to_hex(ip_str):
    return ipaddress.IPv6Address(ip_str).exploded.replace(':', '').lower()


def query_geocn(ip_str):
    """用 GeoCN 实时查询（最精确，逐 IP，支持 v4 和 v6）"""
    try:
        import maxminddb
        reader = maxminddb.open_database(GEOCN_PATH)
        r = reader.get(ip_str)
        reader.close()
        if r:
            code = str(r.get('division_code', ''))
            isp_raw = r.get('isp', b'')
            isp = isp_raw.decode('utf-8', errors='replace') if isinstance(isp_raw, bytes) else str(isp_raw)
            return code, isp
    except Exception:
        pass
    return None, None


def query_db_v4(ip_int):
    """从 IPv4 数据库查询"""
    if not os.path.exists(DB_V4):
        return None
    conn = sqlite3.connect(DB_V4)
    cur = conn.cursor()
    # v4 DB has all columns except idc_vendor
    cur.execute('''
        SELECT start_ip, end_ip, province, city, isp, division_code,
               latitude, longitude, geo_level, '' as idc_vendor
        FROM china_ip
        WHERE start_ip_int <= ? AND end_ip_int >= ?
        LIMIT 1
    ''', (ip_int, ip_int))
    row = cur.fetchone()
    conn.close()
    return row


def query_db_v6(ip_str):
    """从 IPv6 数据库查询"""
    if not os.path.exists(DB_V6):
        return None
    ip_hex = ipv6_to_hex(ip_str)
    conn = sqlite3.connect(DB_V6)
    cur = conn.cursor()
    cur.execute('''
        SELECT start_ip, end_ip, cidr, province, city, district, isp,
               division_code, latitude, longitude, geo_level, idc_vendor, prefix_len
        FROM china_ipv6
        WHERE start_ip_hex <= ? AND end_ip_hex >= ?
        LIMIT 1
    ''', (ip_hex, ip_hex))
    row = cur.fetchone()
    conn.close()
    return row


_DIV_CACHE = None

def _build_div_cache():
    """构建行政区划码映射缓存"""
    import csv
    csv.field_size_limit(10 * 1024 * 1024)

    l4 = os.path.join(BASE, 'ok_data_level4.csv')
    geo_path = os.path.join(BASE, 'ok_geo.csv')
    if not os.path.exists(l4):
        return {}

    geo_map = {}
    if os.path.exists(geo_path):
        with open(geo_path, 'r', encoding='utf-8-sig') as f:
            next(f)
            for row in csv.reader(f):
                if len(row) >= 6:
                    p = row[5].strip().split()
                    if len(p) >= 2:
                        try:
                            geo_map[row[0]] = (float(p[0]), float(p[1]))
                        except ValueError:
                            pass

    divs = {}
    with open(l4, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            did = row['id'].strip()
            divs[did] = {
                'name': row['name'].strip(),
                'pid': row['pid'].strip(),
                'ext_id': row['ext_id'].strip(),
                'deep': int(row['deep']),
            }

    def get_path(did):
        path = {'province': '', 'city': '', 'district': ''}
        cur = did
        while cur in divs:
            d = divs[cur]
            deep_map = {0: 'province', 1: 'city', 2: 'district', 3: 'district'}
            key = deep_map.get(d['deep'])
            if key and not path[key]:
                path[key] = d['name']
            cur = d['pid']
        return path

    result = {}
    for did, info in divs.items():
        ext = info['ext_id'][:6]
        if not ext or ext == '000000':
            continue
        path = get_path(did)
        lng, lat = geo_map.get(did, (None, None))

        if ext[4:] != '00':
            level = 'district'
        elif ext[2:4] != '00':
            level = 'city'
        else:
            level = 'province'

        rank = {'district': 3, 'city': 2, 'province': 1}
        old = result.get(ext)
        if old is None or rank.get(level, 0) > rank.get(old.get('level', ''), 0):
            result[ext] = {
                'province': path['province'],
                'city': path['city'],
                'district': path['district'],
                'lng': lng,
                'lat': lat,
                'level': level,
            }

    return result


def lookup_division(code):
    """通过行政区划码解析省/市/区名称"""
    global _DIV_CACHE
    if _DIV_CACHE is None:
        _DIV_CACHE = _build_div_cache()

    if not code or code == '0' or code == '':
        return {}
    code = str(code).zfill(6)

    if code in _DIV_CACHE:
        return _DIV_CACHE[code].copy()

    for pattern in [code[:4]+'00', code[:2]+'0000']:
        if pattern in _DIV_CACHE:
            return _DIV_CACHE[pattern].copy()

    return {'province': '', 'city': '', 'district': '', 'lng': None, 'lat': None, 'level': 'unknown'}


def query_ip(ip_str):
    """自动识别 v4/v6 并查询"""
    if is_ipv6(ip_str):
        print(f'[检测到 IPv6 地址]')
        return query_ip_v6(ip_str)

    try:
        ip_int = ip_to_int(ip_str)
    except ValueError:
        print(f'错误: 无效 IP 地址: {ip_str}')
        return

    # IPv4 双引擎查询
    gcn_code, gcn_isp = query_geocn(ip_str)
    gcn_info = lookup_division(gcn_code) if gcn_code else {}
    db_row = query_db_v4(ip_int)

    print(f'IP:      {ip_str} (IPv4)')
    if db_row:
        print(f'IP段:    {db_row[0]} - {db_row[1]}')
        parts = [p for p in [db_row[2] or '', db_row[3] or '', db_row[4] or ''] if p]
        idc = db_row[9] if len(db_row) > 9 and db_row[9] else ''
        if idc:
            parts.append(f'[{idc}]')
        print(f'数据库:  {" ".join(parts)}')
        if len(db_row) > 6 and db_row[6] is not None:
            print(f'经纬度:  ({db_row[6]:.4f}, {db_row[7]:.4f}) level={db_row[8] or "?"}')
        if len(db_row) > 5 and db_row[5]:
            print(f'行政区划: {db_row[5]}')

    geo_parts = [p for p in [gcn_info.get('province',''), gcn_info.get('city',''), gcn_info.get('district','')] if p]
    if geo_parts:
        print(f'GeoCN:   {" ".join(geo_parts)} [code={gcn_code}, {gcn_info.get("level","?")}]', end='')
        lng = gcn_info.get('lng')
        lat = gcn_info.get('lat')
        if lng is not None:
            print(f'  ({lng:.4f}, {lat:.4f})', end='')
        print()
    else:
        print(f'GeoCN:   [无区县数据] code={gcn_code or "无"}')

    if gcn_isp:
        print(f'运营商:  {gcn_isp}')


def query_ip_v6(ip_str):
    """IPv6 查询"""
    row = query_db_v6(ip_str)
    if not row:
        print(f'IP:      {ip_str} (IPv6)')
        print('数据库:  未找到匹配记录')
        return

    (start_ip, end_ip, cidr, province, city, district, isp,
     div_code, lat, lng, geo_level, idc_vendor, prefix_len) = row

    print(f'IP:      {ip_str} (IPv6)')
    if cidr:
        print(f'CIDR:    {cidr}')
    print(f'IP段:    {start_ip} - {end_ip}')
    if geo_level != 'country':
        parts = [p for p in [province or '', city or '', district or ''] if p]
        print(f'位置:    {" ".join(parts)} [level={geo_level}]')
    else:
        print(f'位置:    {province or "中国"} [省级]')
    if isp:
        print(f'运营商:  {isp}')
    if idc_vendor:
        print(f'IDC厂商: {idc_vendor}')
    if lat is not None:
        print(f'经纬度:  ({lat:.4f}, {lng:.4f})')
    if div_code:
        print(f'行政区划: {div_code}')


def query_ip_geocn_only(ip_str):
    """强制仅用 GeoCN 查询"""
    code, isp = query_geocn(ip_str)
    if not code:
        print(f'{ip_str} -> 境外/无数据')
        return
    info = lookup_division(code)
    parts = [p for p in [info.get('province',''), info.get('city',''), info.get('district',''), isp] if p]
    lvl = info.get('level', 'unknown')
    lng, lat = info.get('lng'), info.get('lat')
    geo = f' ({lng:.4f},{lat:.4f})' if lng else ''
    print(f'{ip_str} -> {" ".join(parts)} [code={code}, {lvl}]{geo}')


def stats():
    """数据库统计 (IPv4 + IPv6)"""
    print('=' * 56)
    print('  中国 IP 数据库 - 统计信息')
    print('=' * 56)

    # IPv4 统计
    if os.path.exists(DB_V4):
        conn = sqlite3.connect(DB_V4)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM china_ip')
        v4_total = cur.fetchone()[0]
        cur.execute('SELECT COUNT(DISTINCT province) FROM china_ip')
        v4_provinces = cur.fetchone()[0]
        cur.execute('SELECT COUNT(DISTINCT city) FROM china_ip WHERE city != ""')
        v4_cities = cur.fetchone()[0]
        cur.execute('SELECT MIN(start_ip_int), MAX(end_ip_int) FROM china_ip')
        v4_min_i, v4_max_i = cur.fetchone()
        v4_min = str(ipaddress.IPv4Address(v4_min_i))
        v4_max = str(ipaddress.IPv4Address(v4_max_i))

        # Check which columns exist
        cur.execute("PRAGMA table_info(china_ip)")
        v4_cols = {r[1] for r in cur.fetchall()}

        cur.execute('SELECT COUNT(*) FROM china_ip WHERE district != ""')
        v4_dist = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM china_ip WHERE latitude IS NOT NULL')
        v4_geo = cur.fetchone()[0]
        v4_idc = 0  # IDC vendor only exists in MySQL version
        conn.close()

        print(f'\n  [IPv4]')
        print(f'  总 IP 段数:        {v4_total}')
        print(f'  覆盖省份:          {v4_provinces}')
        print(f'  覆盖城市:          {v4_cities}')
        print(f'  有区县数据:        {v4_dist} ({v4_dist/v4_total*100:.1f}%)')
        print(f'  有经纬度:          {v4_geo} ({v4_geo/v4_total*100:.1f}%)')
        print(f'  IDC 标记:          {v4_idc}')
        print(f'  IP 范围:           {v4_min} ~ {v4_max}')
        print(f'  数据源:            ip2region + GeoCN')

    # IPv6 统计
    if os.path.exists(DB_V6):
        conn = sqlite3.connect(DB_V6)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM china_ipv6')
        v6_total = cur.fetchone()[0]
        cur.execute('SELECT geo_level, COUNT(*) FROM china_ipv6 GROUP BY geo_level ORDER BY COUNT(*) DESC')
        v6_levels = cur.fetchall()
        cur.execute('SELECT COUNT(DISTINCT isp) FROM china_ipv6 WHERE isp != ""')
        v6_isps = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM china_ipv6 WHERE idc_vendor != ""')
        v6_idc = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM china_ipv6 WHERE latitude IS NOT NULL')
        v6_geo = cur.fetchone()[0]
        cur.execute('SELECT COUNT(DISTINCT province) FROM china_ipv6 WHERE province != ""')
        v6_provs = cur.fetchone()[0]
        conn.close()

        print(f'\n  [IPv6]')
        print(f'  总分配段数:        {v6_total}')
        print(f'  已识别省份:        {v6_provs}')
        print(f'  已识别运营商:      {v6_isps}')
        print(f'  IDC 标记:          {v6_idc}')
        print(f'  有经纬度:          {v6_geo}')
        print('  精度级别:')
        for lvl, cnt in v6_levels:
            print(f'    {lvl}: {cnt} ({cnt/v6_total*100:.1f}%)')
        print(f'  数据源:            APNIC + GeoCN')

    print(f'\n  数据引擎:')
    print(f'    DB:      SQLite 范围查询')
    print(f'    GeoCN:   实时逐 IP (MaxMind .mmdb)')


def query_province(province_name):
    """查询某省 IPv4 段"""
    if not os.path.exists(DB_V4):
        print('IPv4 数据库不存在')
        return
    conn = sqlite3.connect(DB_V4)
    cur = conn.cursor()
    cur.execute('''
        SELECT start_ip, end_ip, city, isp, division_code, latitude, longitude
        FROM china_ip WHERE province = ? ORDER BY start_ip_int
    ''', (province_name,))
    rows = cur.fetchall()
    if rows:
        print(f'{province_name}: {len(rows)} 个 IP 段\n')
        for r in rows[:20]:
            geo = f'({r[5]:.2f}, {r[6]:.2f})' if r[5] is not None else ''
            print(f'  {r[0]:<16} - {r[1]:<16}  {r[2] or "":<10} {r[3] or "":<12} code={r[4] or ""} {geo}')
        if len(rows) > 20:
            print(f'  ... 共 {len(rows)} 条, 显示前 20')
    else:
        print(f'未找到省份: {province_name}')
    conn.close()


def verify_idc():
    """验证大厂 IDC IP 段 (IPv4)"""
    print('=' * 56)
    print('  大厂 IDC IP 段验证 (IPv4)')
    print('=' * 56)
    for ip_str, desc in IDC_IPS:
        code, isp = query_geocn(ip_str)
        info = lookup_division(code) if code else {}
        db_row = query_db_v4(ip_to_int(ip_str))

        geo_parts = [p for p in [info.get('province',''), info.get('city',''), info.get('district','')] if p]
        geo_str = ' '.join(geo_parts) if geo_parts else '境外/未知'
        db_parts = [p for p in [db_row[2] if db_row else '', db_row[3] if db_row else ''] if p]
        db_str = ' '.join(db_parts) if db_parts else '境外'
        isp_str = isp or (db_row[4] if db_row else '')

        ok = 'OK' if (code and info.get('level') in ('city','district')) else '--'
        print(f'  [{ok}] {ip_str:<16} {desc:<14} -> {geo_str:<18} {isp_str:<8} code={code or "--"}')

    # IPv6 IDC check
    print()
    print('=' * 56)
    print('  大厂 IDC IP 段验证 (IPv6)')
    print('=' * 56)
    for ip_str, desc in IDC_IPV6:
        row = query_db_v6(ip_str)
        if row:
            (sip, eip, cidr, prov, city, dist, isp, dc, lat, lng, gl, idc_v, pl) = row
            loc = ' '.join(p for p in [prov, city, dist] if p)
            ok = 'OK' if idc_v else '--'
            idc_tag = idc_v if idc_v else '(未标记)'
            print(f'  [{ok}] {ip_str:<20s} {desc:<14s} -> {loc:<18s} {idc_tag:<12s}')
        else:
            print(f'  [--] {ip_str:<20s} {desc:<14s} -> 未找到')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    arg = sys.argv[1]

    if arg == '--geocn':
        if len(sys.argv) > 2:
            query_ip_geocn_only(sys.argv[2])
        else:
            print('用法: --geocn <IP>')
    elif arg == '--ipv6':
        if len(sys.argv) > 2:
            query_ip_v6(sys.argv[2])
        else:
            print('用法: --ipv6 <IPv6地址>')
    elif arg == '--province':
        query_province(sys.argv[2]) if len(sys.argv) > 2 else print('需指定省份名')
    elif arg == '--stats':
        stats()
    elif arg == '--verify':
        verify_idc()
    elif arg in ('-h', '--help'):
        print(__doc__)
    else:
        query_ip(arg)

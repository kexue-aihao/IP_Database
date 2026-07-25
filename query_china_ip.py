#!/usr/bin/env python3
"""
中国 IP 数据库查询工具
双引擎: 数据库(省/市/ISP) + GeoCN(区县/经纬度实时逐IP)

用法:
  python3 query_china_ip.py <IP地址>           查询单个 IP
  python3 query_china_ip.py --geocn <IP>      强制用 GeoCN 查询（最精确）
  python3 query_china_ip.py --province         列出所有省份
  python3 query_china_ip.py --stats            数据库统计
  python3 query_china_ip.py --province 广东    查询某省所有 IP 段
  python3 query_china_ip.py --verify           验证大厂 IDC IP
"""
import sqlite3, sys, os, ipaddress

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'china_ip_db.sqlite')
GEOCN_PATH = os.path.join(BASE, 'GeoCN.mmdb')

# 大厂 IDC 验证列表
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
    ('158.247.0.0',     '阿里云-国际'),
    ('103.27.0.0',      '阿里云-新加坡'),
    ('52.80.0.0',       'AWS-北京'),
    ('52.82.0.0',       'AWS-宁夏'),
    ('35.72.0.0',       'GCP-大阪'),
    ('64.233.0.0',      'Google'),
    ('111.13.0.0',      '中国移动-北京'),
    ('202.96.128.86',   '广东电信DNS'),
    ('114.114.114.114', '114DNS-南京'),
    ('223.5.5.5',       '阿里DNS-杭州'),
    ('180.101.49.11',   '百度DNS-南京'),
    ('61.135.169.121',  '百度-北京'),
    ('121.14.77.221',   '腾讯-广州'),
    ('110.242.68.3',    '联通DNS-保定'),
    ('1.2.4.0',         'CNNIC DNS-北京'),
    ('27.39.157.25',    '联通-佛山高明'),
    ('101.132.0.0',     '腾讯云-上海'),
    ('120.55.0.0',      '阿里云-上海'),
    ('112.74.0.0',      '腾讯云-广州'),
    ('159.75.0.0',      '阿里云-香港'),
    ('170.33.0.0',      '谷歌云-台湾'),
]


def ip_to_int(ip_str):
    return int(ipaddress.IPv4Address(ip_str))


def query_geocn(ip_str):
    """用 GeoCN 实时查询（最精确，逐 IP）"""
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


def query_db(ip_int):
    """从数据库查询（省/市/ISP）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT start_ip, end_ip, province, city, isp
        FROM china_ip
        WHERE start_ip_int <= ? AND end_ip_int >= ?
        LIMIT 1
    ''', (ip_int, ip_int))
    row = cur.fetchone()
    conn.close()
    return row


# 编译好的行政区划码映射缓存
_DIV_CACHE = None

def _build_div_cache():
    """构建持久化的 6位码→(province,city,district,lng,lat,level) 缓存"""
    import csv
    csv.field_size_limit(10 * 1024 * 1024)

    l4 = os.path.join(BASE, 'ok_data_level4.csv')
    geo_path = os.path.join(BASE, 'ok_geo.csv')
    if not os.path.exists(l4):
        return {}

    # 加载经纬度
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

    # 加载层级
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

    # 追溯路径
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

    # 构建 6位码索引
    result = {}
    for did, info in divs.items():
        ext = info['ext_id'][:6]
        if not ext or ext == '000000':
            continue
        path = get_path(did)
        lng, lat = geo_map.get(did, (None, None))

        # 用6位码确定等级
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

    # 精确匹配
    if code in _DIV_CACHE:
        return _DIV_CACHE[code].copy()

    # 逐级回退
    for pattern in [code[:4]+'00', code[:2]+'0000']:
        if pattern in _DIV_CACHE:
            return _DIV_CACHE[pattern].copy()

    return {'province': '', 'city': '', 'district': '', 'lng': None, 'lat': None, 'level': 'unknown'}


def query_ip(ip_str):
    """查询 IP — GeoCN 优先，DB 兜底"""
    try:
        ip_int = ip_to_int(ip_str)
    except ValueError:
        print(f'[错误] 无效 IP: {ip_str}')
        return

    # 1) GeoCN 实时查（最精确）
    gcn_code, gcn_isp = query_geocn(ip_str)
    gcn_info = lookup_division(gcn_code) if gcn_code else {}

    # 2) 数据库查（省/市/运营商）
    db_row = query_db(ip_int)

    print(f'IP: {ip_str}')
    if db_row:
        print(f'  IP段: {db_row[0]} - {db_row[1]}')
        print(f'  IP数据库: {db_row[2] or "未知"} {db_row[3] or "未知"} {db_row[4] or ""}')

    if gcn_info.get('district'):
        print(f'  GeoCN:   {gcn_info.get("province","")} {gcn_info.get("city","")} {gcn_info.get("district","")} ', end='')
    elif gcn_info.get('city'):
        print(f'  GeoCN:   {gcn_info.get("province","")} {gcn_info.get("city","")} ', end='')
    elif gcn_info.get('province'):
        print(f'  GeoCN:   {gcn_info.get("province","")} ', end='')
    else:
        print(f'  GeoCN:   ', end='')

    if gcn_code:
        level = gcn_info.get('level', '?')
        print(f'[code={gcn_code}, {level}]')
        lng = gcn_info.get('lng')
        lat = gcn_info.get('lat')
        if lng is not None:
            print(f'    经纬度: ({lng:.4f}, {lat:.4f})')
    else:
        print('[无 GeoCN 数据]')

    if gcn_isp:
        print(f'  运营商: {gcn_isp}')


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


def query_province(province_name):
    conn = sqlite3.connect(DB_PATH)
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


def stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM china_ip')
    total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT province) FROM china_ip')
    provinces = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT city) FROM china_ip WHERE city != ""')
    cities = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT isp) FROM china_ip WHERE isp != ""')
    isps = cur.fetchone()[0]
    cur.execute('SELECT MIN(start_ip_int), MAX(end_ip_int) FROM china_ip')
    min_int, max_int = cur.fetchone()
    min_ip = str(ipaddress.IPv4Address(min_int))
    max_ip = str(ipaddress.IPv4Address(max_int))
    cur.execute('SELECT value FROM meta WHERE key="generated_at"')
    gen_time = cur.fetchone()
    gen_time = gen_time[0] if gen_time else 'unknown'

    dc = getattr(stats, '_district_cache', None)
    if dc is None:
        cur.execute('SELECT COUNT(*) FROM china_ip WHERE latitude IS NOT NULL')
        has_geo = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM china_ip WHERE division_code != ""')
        has_code = cur.fetchone()[0]
        stats._district_cache = (has_geo, has_code)

    has_geo, has_code = stats._district_cache
    conn.close()

    print('=' * 56)
    print('  中国 IP 数据库 - 统计信息')
    print('=' * 56)
    print(f'  总 IP 段数:        {total}')
    print(f'  覆盖省份:          {provinces}')
    print(f'  覆盖城市:          {cities}')
    print(f'  覆盖运营商:        {isps}')
    print(f'  有行政区划码:      {has_code} ({has_code/total*100:.1f}%)')
    print(f'  有经纬度:          {has_geo} ({has_geo/total*100:.1f}%)')
    print(f'  IP 范围:           {min_ip} ~ {max_ip}')
    print(f'  生成时间:          {gen_time}')
    print(f'  数据引擎:')
    print(f'    DB:      ip2region {total} 条 (省/市/ISP 范围)')
    print(f'    GeoCN:   实时逐 IP 查 (区县级精度)')
    db_size = os.path.getsize(DB_PATH)
    print(f'  文件大小:          {db_size / 1024:.1f} KB')


def verify_idc():
    """验证大厂 IDC IP 段"""
    print('=' * 56)
    print('  大厂 IDC IP 段验证')
    print('=' * 56)
    for ip_str, desc in IDC_IPS:
        code, isp = query_geocn(ip_str)
        info = lookup_division(code) if code else {}

        db_row = query_db(ip_to_int(ip_str))

        # 显示
        geo_parts = [p for p in [info.get('province',''), info.get('city',''), info.get('district','')] if p]
        geo_str = ' '.join(geo_parts) if geo_parts else '境外/未知'
        db_parts = [p for p in [db_row[2] if db_row else '', db_row[3] if db_row else ''] if p]
        db_str = ' '.join(db_parts) if db_parts else '境外'
        isp_str = isp or (db_row[4] if db_row else '')

        ok = 'OK' if (code and info.get('level') in ('city','district')) else '--'
        print(f'  [{ok}] {ip_str:<16} {desc:<14} -> {geo_str:<18} {isp_str:<8} code={code or "--"}')


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
    elif arg == '--province':
        query_province(sys.argv[2]) if len(sys.argv) > 2 else print('需指定省份名')
    elif arg == '--stats':
        stats()
    elif arg == '--verify':
        verify_idc()
    else:
        query_ip(arg)

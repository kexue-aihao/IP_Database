#!/usr/bin/env python3
"""
中国 IPv6 完整归属地数据库构建工具
===================================
从 APNIC 授权数据 + GeoCN 区县数据库构建中国 IPv6 IP 段数据库。

数据来源:
  - APNIC: ftp://ftp.apnic.net/pub/stats/apnic/delegated-apnic-latest
  - GeoCN: https://github.com/ljxi/GeoCN (MaxMind .mmdb)
  - AreaCity: 行政区划码 ↔ 省/市/区/经纬度映射

输出:
  - china_ipv6_db.sqlite    SQLite 数据库
  - china_ipv6_db.csv        CSV 导出

覆盖范围:
  - 中国大陆 (CN) 2040+ 个 IPv6 分配段
  - 香港 (HK) 736+ 段
  - 台湾 (TW) 316+ 段
  - 澳门 (MO) 11+ 段
  - 国内大厂 IDC IPv6 段标记

注意:
  IPv6 区县精度级别不如 IPv4 高，大部分只能到 ISP/省级别。
  这是全球 IPv6 地理定位技术的普遍限制。
"""
import csv, ipaddress, os, sys, sqlite3, urllib.request
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE, 'china_ipv6_db.sqlite')
CSV_FILE = os.path.join(BASE, 'china_ipv6_db.csv')
GEOCN_PATH = os.path.join(BASE, 'GeoCN.mmdb')
L4_PATH = os.path.join(BASE, 'ok_data_level4.csv')
GEO_PATH = os.path.join(BASE, 'ok_geo.csv')

# APNIC 数据 URL
APNIC_URL = 'https://ftp.apnic.net/pub/stats/apnic/delegated-apnic-latest'

# ============================================================
# 国内三大运营商 /16 主前缀及其省网部署映射
# 这些映射来自公开的中国 IPv6 部署资料
# ============================================================
# 中国电信 240e::/16 → 各省子网 (部分已知)
TELECOM_PROVINCES = {
    0x240e: '中国电信',  # 默认省级别
}

# 中国联通 2408::/16, 240a::/16
UNICOM_PROVINCES = {
    0x2408: '中国联通',
    0x240a: '中国联通',
}

# 中国移动 2409::/16, 240b::/16, 240c::/16, 240d::/16
MOBILE_PROVINCES = {
    0x2409: '中国移动',
    0x240b: '中国移动',
    0x240c: '中国移动',
    0x240d: '中国移动',
}

# ============================================================
# 国内主要 IDC/云厂商 IPv6 段 (从公开资料整理)
# 格式: (前缀, 厂商, 主要区域)
# ============================================================
IDC_IPV6_RANGES = [
    # 阿里云
    ('2408:4000::/22',           '阿里云',        '北京'),
    ('2403:dc00::/24',           '阿里云',        '上海'),
    # 腾讯云
    ('2402:4e00::/23',           '腾讯云',        '上海'),
    ('2402:4c00::/23',           '腾讯云',        '广州'),
    # 华为云
    ('2407:c080::/32',           '华为云',        '北京'),
    ('2407:c000::/32',           '华为云',        '广州'),
    # 中国电信天翼云
    ('240e:400::/22',            '中国电信天翼云', '全国'),
    ('240e::/24',                '中国电信天翼云', '全国'),
    # 百度云
    ('2400:da00::/32',           '百度云',        '北京'),
    # 京东云
    ('2400:aac0::/32',           '京东云',        '北京'),
    # AWS 中国
    ('2400:6500::/32',           'AWS中国',       '北京'),
    ('2400:6500:1000::/36',      'AWS中国',       '宁夏'),
    # 字节跳动/火山引擎
    ('2408:8700::/32',           '火山引擎',       '北京'),
]

# 已知 ISP 前缀匹配: (cidr, isp_name)
KNOWN_ISP_PREFIXES = [
    ('240e::/16', '中国电信'),
    ('2408::/16', '中国联通'),
    ('2409::/16', '中国移动'),
    ('240a::/16', '中国联通'),
    ('240b::/16', '中国移动'),
    ('240c::/16', '中国移动'),
    ('240d::/16', '中国移动'),
    ('2001:250::/32', 'CERNET'),
    ('2001:da8::/32', 'CERNET2'),
    ('2001:da9::/32', 'CERNET2'),
    ('2001:daa::/32', 'CERNET2'),
    # HK ISP
    ('2001:ce0::/32', '香港宽频'),
    ('2001:ce1::/32', '香港宽频'),
    ('2001:def::/32', '香港电讯盈科'),
    ('2001:df0::/44', '香港互联网交换中心'),
    # TW ISP
    ('2001:b00::/21', '台湾中华电信'),
    ('2001:c08::/32', '台湾远传电信'),
    ('2001:c50::/32', '台湾大哥大'),
    ('2001:e10::/32', '台湾亚太电信'),
]

_ISP_NETWORKS = []
for cidr, name in KNOWN_ISP_PREFIXES:
    try:
        _ISP_NETWORKS.append((ipaddress.IPv6Network(cidr, strict=False), name))
    except ValueError:
        pass


def match_isp_by_prefix(net):
    """通过 IPv6 网络前缀判断运营商"""
    for isp_net, name in _ISP_NETWORKS:
        try:
            if net.subnet_of(isp_net) or isp_net.subnet_of(net):
                return name
        except ValueError:
            continue
    return ''

# 国家/地区名映射
COUNTRY_MAP = {
    'CN': '中国',
    'HK': '中国香港',
    'TW': '中国台湾',
    'MO': '中国澳门',
}

# 澳门只有 11 个 /32，直接放这里
MACAU_RANGES_V6 = [
    ('2001:df5:900::/48', '澳门电讯'),
    ('2001:df6:4f00::/48', '澳门电讯'),
    ('2001:f90::/32', '澳门电讯'),
    ('2001:ff8::/32', '澳门电讯'),
    ('2400:aae0::/32', '澳门电讯'),
    ('2401:20e0::/32', '澳门电讯'),
    ('2401:3280::/32', '澳门电讯'),
    ('2401:75c0::/32', '澳门电讯'),
    ('2401:9100::/32', '澳门电讯'),
    ('2402:9280::/32', '澳门电讯'),
    ('2402:e940::/32', '澳门电讯'),
]


def ipv6_to_hex(ip_str):
    """将 IPv6 地址转为 32 字符零填充十六进制字符串，用于 SQL 比较"""
    ip = ipaddress.IPv6Address(ip_str)
    return ip.exploded.replace(':', '').lower()


def ipv6_range_to_hex(start_ip, end_ip):
    """生成 IPv6 IP 范围的起始/结束十六进制"""
    start_hex = ipv6_to_hex(start_ip)
    end_hex = ipv6_to_hex(end_ip)
    return start_hex, end_hex


def load_division_data():
    """加载行政区划码映射"""
    import csv as _csv
    csv.field_size_limit(10 * 1024 * 1024)

    # 经纬度
    geo_map = {}
    if os.path.exists(GEO_PATH):
        with open(GEO_PATH, 'r', encoding='utf-8-sig') as f:
            next(f)
            for row in _csv.reader(f):
                if len(row) >= 6:
                    p = row[5].strip().split()
                    if len(p) >= 2:
                        try:
                            geo_map[row[0]] = (float(p[0]), float(p[1]))
                        except ValueError:
                            pass

    # 层级信息
    divs = {}
    if os.path.exists(L4_PATH):
        with open(L4_PATH, 'r', encoding='utf-8-sig') as f:
            for row in _csv.DictReader(f):
                did = row['id'].strip()
                divs[did] = {
                    'name': row['name'].strip(),
                    'pid': row['pid'].strip(),
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
        did_code = info['name']  # code is in ext_id
        # We need ext_id, let's find it
        pass

    # Reload with ext_id
    divs2 = {}
    with open(L4_PATH, 'r', encoding='utf-8-sig') as f:
        for row in _csv.DictReader(f):
            did = row['id'].strip()
            ext = row.get('ext_id', '').strip()
            divs2[did] = {
                'name': row['name'].strip(),
                'pid': row['pid'].strip(),
                'ext_id': ext,
                'deep': int(row['deep']),
            }

    for did, info in divs2.items():
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


def lookup_division(code, cache):
    """通过行政区划码解析位置"""
    if not code or code == '0' or code == '':
        return {}
    code = str(code).zfill(6)

    if code in cache:
        return cache[code].copy()

    for pattern in [code[:4] + '00', code[:2] + '0000']:
        if pattern in cache:
            return cache[pattern].copy()

    return {'province': '', 'city': '', 'district': '', 'lng': None, 'lat': None, 'level': 'unknown'}


def query_geocn(ip_str, reader):
    """GeoCN 查询"""
    try:
        r = reader.get(ip_str)
        if r:
            code = str(r.get('division_code', ''))
            isp_raw = r.get('isp', b'')
            isp = isp_raw.decode('utf-8', errors='replace') if isinstance(isp_raw, bytes) else str(isp_raw)
            return code, isp
    except Exception:
        pass
    return None, None


def sample_geocn_for_range(cidr, reader):
    """
    对一个 IPv6 CIDR 范围采样多个 IP 来获取最佳地理位置
    """
    net = ipaddress.IPv6Network(cidr, strict=False)
    addr_int = int(net.network_address)
    space = 1 << (128 - net.prefixlen)

    best_code = None
    isp_set = set()
    sample_offsets = [0]  # always try start IP

    # Add more sample points for large ranges
    if net.prefixlen < 32:
        step = max(0x100000, space // 10)
        for i in range(1, min(30, space // step)):
            sample_offsets.append(i * step)
    elif net.prefixlen < 48:
        step = max(0x1000, space // 10)
        for i in range(1, min(10, space // step)):
            sample_offsets.append(i * step)

    # Ensure offset is within range
    for off in sample_offsets:
        if off >= space:
            continue
        try:
            ip = str(ipaddress.IPv6Address(addr_int + off))
            code, isp = query_geocn(ip, reader)
            if isp:
                isp_set.add(isp)
            if code and code != '0' and code != '':
                code_int = int(code)
                # Higher code = more specific in GeoCN
                if best_code is None or code_int > 0:
                    if code_int > 0:
                        if best_code is None or code_int > int(best_code):
                            best_code = code
        except Exception:
            continue

    return best_code, isp_set


def download_apnic_data():
    """下载 APNIC 授权数据"""
    print('[1/5] 下载 APNIC IPv6 授权数据...')
    try:
        with urllib.request.urlopen(APNIC_URL, timeout=60) as f:
            lines = f.read().decode('utf-8', errors='replace')
        print(f'      下载完成 ({len(lines)//1024} KB)')
        return lines
    except Exception as e:
        print(f'  [错误] 下载失败: {e}')
        sys.exit(1)


def parse_apnic_ipv6(lines):
    """解析 APNIC 数据，提取中国 IPv6 分配"""
    print('[2/5] 解析中国 IPv6 分配段...')
    entries = []
    for line in lines.split('\n'):
        parts = line.split('|')
        if len(parts) >= 7 and parts[1] in ('CN', 'HK', 'TW', 'MO') and parts[2] == 'ipv6':
            cc = parts[1]
            prefix = parts[3]
            mask = int(parts[4])
            # 只保留 /32 及更大的分配（更小的分配太具体，通常是一些特殊用途）
            # 但保留 /48 和 /64 的 HK/TW 分配（因为数量不多）
            if mask <= 48 or cc in ('HK', 'TW', 'MO'):
                cidr = f'{prefix}/{mask}'
                try:
                    net = ipaddress.IPv6Network(cidr, strict=False)
                    entries.append({
                        'cc': cc,
                        'country': COUNTRY_MAP.get(cc, '中国'),
                        'cidr': cidr,
                        'network': net,
                        'prefix_len': mask,
                        'start_ip': str(net.network_address),
                        'end_ip': str(net.broadcast_address),
                    })
                except ValueError:
                    continue

    print(f'      找到 {len(entries)} 个中国 IPv6 分配段')
    cc_counts = defaultdict(int)
    for e in entries:
        cc_counts[e['cc']] += 1
    for cc, cnt in sorted(cc_counts.items()):
        print(f'        [{cc}] {cnt} 段')
    return entries


def enhance_with_geocn(entries):
    """使用 GeoCN 丰富位置数据"""
    print('[3/5] GeoCN 区县数据富化...')
    import maxminddb
    if not os.path.exists(GEOCN_PATH):
        print('  [警告] GeoCN.mmdb 不存在，跳过 GeoCN 富化')
        return entries

    reader = maxminddb.open_database(GEOCN_PATH)
    div_cache = load_division_data()

    enriched = []
    geocn_hits = 0
    isp_guessed = 0

    for i, entry in enumerate(entries):
        cc = entry['cc']
        cidr = entry['cidr']
        net = entry['network']
        addr_int = int(net.network_address)

        # 1) 先检查是否匹配已知 IDC 厂商
        matched_idc = None
        for prefix, vendor, region in IDC_IPV6_RANGES:
            try:
                pnet = ipaddress.IPv6Network(prefix, strict=False)
                if net.subnet_of(pnet) or pnet.subnet_of(net):
                    matched_idc = vendor
                    break
            except ValueError:
                continue

        # 2) GeoCN 采样
        best_code, isp_set = sample_geocn_for_range(cidr, reader)

        # 合并 ISP
        isp = '; '.join(sorted(isp_set)[:3]) if isp_set else ''

        # 3) 判断 ISP（GeoCN → 已知前缀映射）
        isp_determined = ''
        if isp:
            isp_determined = isp
        else:
            isp_determined = match_isp_by_prefix(net)
            if isp_determined:
                isp_guessed += 1

        if not isp_determined:
            if cc == 'HK':
                isp_determined = '香港'
            elif cc == 'TW':
                isp_determined = '台湾'
            elif cc == 'MO':
                isp_determined = '澳门'

        # 4) 通过 division_code 解析行政区划
        geo_info = {}
        if best_code and best_code != '0':
            geo_info = lookup_division(best_code, div_cache)
            if geo_info.get('province'):
                geocn_hits += 1

        entry['isp'] = isp_determined
        entry['idc_vendor'] = matched_idc or ''
        entry['division_code'] = best_code if best_code and best_code != '0' else ''

        # 5) 填充地理数据
        if geo_info:
            entry['province'] = geo_info.get('province', '')
            entry['city'] = geo_info.get('city', '')
            entry['district'] = geo_info.get('district', '')
            entry['latitude'] = geo_info.get('lat')
            entry['longitude'] = geo_info.get('lng')
            entry['geo_level'] = geo_info.get('level', 'country')
        else:
            entry['province'] = ''
            entry['city'] = ''
            entry['district'] = ''
            entry['latitude'] = None
            entry['longitude'] = None
            entry['geo_level'] = 'country'

        # 如果是 HK/TW/MO 且没有更精确数据
        if not entry['province']:
            if cc == 'HK':
                entry['province'] = '香港'
            elif cc == 'MO':
                entry['province'] = '澳门'
            elif cc == 'TW':
                entry['province'] = '台湾'

        # 计算十六进制用于 SQL 查询
        start_hex, end_hex = ipv6_range_to_hex(entry['start_ip'], entry['end_ip'])
        entry['start_ip_hex'] = start_hex
        entry['end_ip_hex'] = end_hex
        entry['count'] = space = 1 << (128 - entry['prefix_len'])

        enriched.append(entry)

        if (i + 1) % 500 == 0:
            print(f'      已处理 {i+1}/{len(entries)} ...')

    reader.close()
    print(f'      GeoCN 命中: {geocn_hits}/{len(enriched)}')
    print(f'      ISP 前缀推断: {isp_guessed}/{len(enriched)}')
    return enriched


def build_database(entries):
    """构建 SQLite 数据库"""
    print('[4/5] 构建 SQLite 数据库...')
    os.makedirs(BASE, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute('DROP TABLE IF EXISTS china_ipv6')
    cur.execute('''
        CREATE TABLE china_ipv6 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ip TEXT NOT NULL,
            end_ip TEXT NOT NULL,
            start_ip_hex TEXT NOT NULL,
            end_ip_hex TEXT NOT NULL,
            prefix_len INTEGER DEFAULT 0,
            country TEXT DEFAULT '中国',
            province TEXT DEFAULT '',
            city TEXT DEFAULT '',
            district TEXT DEFAULT '',
            isp TEXT DEFAULT '',
            division_code TEXT DEFAULT '',
            latitude REAL,
            longitude REAL,
            geo_level TEXT DEFAULT 'country',
            idc_vendor TEXT DEFAULT '',
            cidr TEXT DEFAULT ''
        )
    ''')

    # 索引
    cur.execute('CREATE INDEX IF NOT EXISTS idx_ipv6_start_hex ON china_ipv6(start_ip_hex)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_ipv6_end_hex ON china_ipv6(end_ip_hex)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_ipv6_province ON china_ipv6(province)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_ipv6_idc ON china_ipv6(idc_vendor)')

    batch_size = 200
    records = []
    for e in entries:
        records.append((
            e['start_ip'], e['end_ip'], e['start_ip_hex'], e['end_ip_hex'],
            e['prefix_len'], e['country'], e['province'], e['city'], e['district'],
            e['isp'], e['division_code'], e['latitude'], e['longitude'],
            e['geo_level'], e['idc_vendor'], e['cidr'],
        ))

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        cur.executemany('''
            INSERT INTO china_ipv6
            (start_ip, end_ip, start_ip_hex, end_ip_hex,
             prefix_len, country, province, city, district,
             isp, division_code, latitude, longitude,
             geo_level, idc_vendor, cidr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', batch)

    conn.commit()

    # 元信息
    cur.execute('DROP TABLE IF EXISTS meta')
    cur.execute('''
        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    from datetime import datetime
    cur.executemany('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', [
        ('version', '1.0'),
        ('source', 'APNIC + GeoCN + AreaCity'),
        ('ipv6_entries', str(len(entries))),
        ('geocn_hits', str(sum(1 for e in entries if e.get('division_code')))),
        ('generated_at', datetime.now().isoformat()),
        ('description', '中国 IPv6 完整归属地数据库 (ISP/省/区县级别)'),
    ])
    conn.commit()

    cur.execute('SELECT COUNT(*) FROM china_ipv6')
    db_count = cur.fetchone()[0]
    conn.close()

    print(f'      写入完成: {db_count} 条记录')
    db_size = os.path.getsize(DB_FILE)
    print(f'      数据库大小: {db_size / 1024:.1f} KB')

    # 统计
    levels = defaultdict(int)
    idc_counts = defaultdict(int)
    for e in entries:
        levels[e['geo_level']] += 1
        if e['idc_vendor']:
            idc_counts[e['idc_vendor']] += 1

    lvl_country = levels.get("country", 0)
    lvl_province = levels.get("province", 0)
    lvl_city = levels.get("city", 0)
    lvl_district = levels.get("district", 0)
    print(f'      精度: country={lvl_country}, province={lvl_province}, city={lvl_city}, district={lvl_district}')
    if idc_counts:
        print(f'      大厂 IDC 标记:')
        for v, c in sorted(idc_counts.items(), key=lambda x: -x[1]):
            print(f'        {v}: {c}')


def export_mysql(entries):
    """MySQL Dump 导出"""
    MYSQL_PATH = os.path.join(BASE, 'china_ipv6_complete.sql')
    print('[5/6] 导出 MySQL Dump...')

    lines = []
    lines.append('-- =============================================================')
    lines.append('-- 中国 IPv6 完整归属地数据库 (MySQL 版)')
    lines.append('-- 生成时间: ' + __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    lines.append('-- 数据来源: APNIC + GeoCN + AreaCity')
    lines.append('-- 总记录数: ' + str(len(entries)))
    lines.append('-- =============================================================')
    lines.append('')
    lines.append('SET NAMES utf8mb4;')
    lines.append('SET FOREIGN_KEY_CHECKS = 0;')
    lines.append('')
    lines.append('DROP TABLE IF EXISTS `china_ipv6_locations`;')
    lines.append('CREATE TABLE `china_ipv6_locations` (')
    lines.append('  `id` int(11) NOT NULL AUTO_INCREMENT,')
    lines.append('  `start_ip` varchar(39) NOT NULL COMMENT "起始IPv6",')
    lines.append('  `end_ip` varchar(39) NOT NULL COMMENT "结束IPv6",')
    lines.append('  `cidr` varchar(43) DEFAULT "" COMMENT "CIDR",')
    lines.append('  `prefix_len` int(11) DEFAULT 0 COMMENT "前缀长度",')
    lines.append('  `country` varchar(20) NOT NULL DEFAULT "中国" COMMENT "国家/地区",')
    lines.append('  `province` varchar(30) NOT NULL DEFAULT "" COMMENT "省份",')
    lines.append('  `city` varchar(30) NOT NULL DEFAULT "" COMMENT "城市",')
    lines.append('  `district` varchar(30) NOT NULL DEFAULT "" COMMENT "区县",')
    lines.append('  `isp` varchar(50) NOT NULL DEFAULT "" COMMENT "运营商",')
    lines.append('  `division_code` varchar(6) NOT NULL DEFAULT "" COMMENT "行政区划代码",')
    lines.append('  `latitude` decimal(10,6) DEFAULT NULL COMMENT "纬度",')
    lines.append('  `longitude` decimal(10,6) DEFAULT NULL COMMENT "经度",')
    lines.append('  `geo_level` varchar(10) NOT NULL DEFAULT "" COMMENT "精度",')
    lines.append('  `idc_vendor` varchar(30) NOT NULL DEFAULT "" COMMENT "IDC/云厂商标记",')
    lines.append('  `start_ip_bin` binary(16) DEFAULT NULL COMMENT "起始IP二进制",')
    lines.append('  `end_ip_bin` binary(16) DEFAULT NULL COMMENT "结束IP二进制",')
    lines.append('  PRIMARY KEY (`id`),')
    lines.append('  KEY `idx_ipv6_start_bin` (`start_ip_bin`),')
    lines.append('  KEY `idx_ipv6_end_bin` (`end_ip_bin`),')
    lines.append('  KEY `idx_ipv6_province` (`province`),')
    lines.append('  KEY `idx_ipv6_idc_vendor` (`idc_vendor`)')
    lines.append(') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT="中国IPv6完整归属地数据库";')
    lines.append('')

    # Insert records
    for e in entries:
        lat = f'{e["latitude"]:.6f}' if e.get('latitude') is not None else 'NULL'
        lng = f'{e["longitude"]:.6f}' if e.get('longitude') is not None else 'NULL'
        div_code = e.get('division_code', '') or ''
        idc = e.get('idc_vendor', '') or ''
        isp = e.get('isp', '') or ''
        cidr_val = e.get('cidr', '') or ''

        lines.append(
            "INSERT INTO `china_ipv6_locations` "
            "(`start_ip`, `end_ip`, `cidr`, `prefix_len`, `country`, `province`, "
            "`city`, `district`, `isp`, `division_code`, `latitude`, `longitude`, "
            "`geo_level`, `idc_vendor`, `start_ip_bin`, `end_ip_bin`) VALUES ("
            f"'{e['start_ip']}', '{e['end_ip']}', '{cidr_val}', {e['prefix_len']}, "
            f"'{e['country']}', '{e.get('province','')}', "
            f"'{e.get('city','')}', '{e.get('district','')}', "
            f"'{isp}', '{div_code}', {lat}, {lng}, "
            f"'{e['geo_level']}', '{idc}', "
            f"INET6_ATON('{e['start_ip']}'), INET6_ATON('{e['end_ip']}')"
            ");"
        )

    lines.append('')
    lines.append('SET FOREIGN_KEY_CHECKS = 1;')
    lines.append('')

    content = '\n'.join(lines)
    with open(MYSQL_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f'      写入完成: {len(entries)} 条')
    print(f'      MySQL 文件大小: {os.path.getsize(MYSQL_PATH)/1024:.1f} KB')


def export_csv(entries):
    """CSV 导出"""
    print('[5/6] 导出 CSV...')
    fieldnames = ['start_ip', 'end_ip', 'start_ip_hex', 'end_ip_hex', 'prefix_len',
                  'country', 'province', 'city', 'district', 'isp',
                  'division_code', 'latitude', 'longitude', 'geo_level',
                  'idc_vendor', 'cidr']

    with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in entries:
            row = {k: e.get(k, '') for k in fieldnames}
            row['latitude'] = e.get('latitude', '')
            row['longitude'] = e.get('longitude', '')
            writer.writerow(row)

    csv_size = os.path.getsize(CSV_FILE)
    print(f'      写入完成: {len(entries)} 条, {csv_size/1024:.1f} KB')


def print_summary(entries):
    """打印摘要"""
    print()
    print('=' * 60)
    print('  [OK] 中国 IPv6 数据库构建完成！')
    print('=' * 60)
    print(f'  SQLite: {DB_FILE}')
    print(f'  CSV:    {CSV_FILE}')
    print(f'  总条目: {len(entries)}')

    # 按国家分组
    cc_counts = defaultdict(int)
    for e in entries:
        cc_counts[e['cc']] += 1
    for cc in ['CN', 'HK', 'TW', 'MO']:
        print(f'  [{cc}] {cc_counts.get(cc, 0)} 段')

    # 精度
    levels = defaultdict(int)
    for e in entries:
        levels[e['geo_level']] += 1
    print(f'  精度级别:')
    for lvl in ['district', 'city', 'province', 'country']:
        if levels.get(lvl, 0) > 0:
            print(f'    {lvl}: {levels[lvl]} ({levels[lvl]/len(entries)*100:.1f}%)')

    print()
    print('  查询示例:')
    print('  python3 query_china_ip.py --ipv6 240e:100::1')
    print('  python3 query_china_ip.py --ipv6 2409:8000::1')
    print()


def main():
    print('=' * 60)
    print('  中国 IPv6 全量 IP 数据库构建工具')
    print('=' * 60)

    # 1) 下载 APNIC 数据
    lines = download_apnic_data()

    # 2) 解析
    entries = parse_apnic_ipv6(lines)

    if not entries:
        print('[错误] 未找到中国 IPv6 分配段')
        sys.exit(1)

    # 3) GeoCN 富化
    entries = enhance_with_geocn(entries)

    # 4) 构建 SQLite 数据库
    build_database(entries)

    # 5) 导出 CSV
    export_csv(entries)

    # 6) 导出 MySQL Dump
    export_mysql(entries)

    # 统计
    print_summary(entries)

    # 提示合并 MySQL
    print()
    print('  >> 运行 build_mysql.py 以合成完整数据库 (IPv4 + IPv6) <<')
    print()


if __name__ == '__main__':
    main()

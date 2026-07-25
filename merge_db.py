#!/usr/bin/env python3
"""
合并 IPv4 和 IPv6 数据库为单一数据库文件
=========================================
输出:
  - china_merged.sqlite    合并 SQLite (v4表 + v6表)
  - china_merged.sql       合并 MySQL Dump
"""
import sqlite3, os, ipaddress, csv
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
V4_SQLITE = os.path.join(BASE, 'china_ip_db.sqlite')
V6_SQLITE = os.path.join(BASE, 'china_ipv6_db.sqlite')
V4_SQL = os.path.join(BASE, 'china_ip_complete.sql')
V6_SQL = os.path.join(BASE, 'china_ipv6_complete.sql')
OUT_SQLITE = os.path.join(BASE, 'china_merged.sqlite')
OUT_SQL = os.path.join(BASE, 'china_merged.sql')
L4_PATH = os.path.join(BASE, 'ok_data_level4.csv')
GEO_PATH = os.path.join(BASE, 'ok_geo.csv')


def build_div_cache():
    """构建行政区划码缓存"""
    import csv as _csv
    _csv.field_size_limit(10 * 1024 * 1024)

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

    divs = {}
    if os.path.exists(L4_PATH):
        with open(L4_PATH, 'r', encoding='utf-8-sig') as f:
            for row in _csv.DictReader(f):
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


def merge_sqlite():
    """合并 SQLite 数据库"""
    print('[1/2] 合并 SQLite 数据库...')
    if os.path.exists(OUT_SQLITE):
        os.remove(OUT_SQLITE)

    conn = sqlite3.connect(OUT_SQLITE)
    cur = conn.cursor()

    # ========== IPv4 表 ==========
    print('  创建 IPv4 表...')
    cur.execute('''
        CREATE TABLE china_ipv4 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ip TEXT NOT NULL,
            end_ip TEXT NOT NULL,
            start_ip_int INTEGER NOT NULL,
            end_ip_int INTEGER NOT NULL,
            country TEXT DEFAULT '中国',
            province TEXT DEFAULT '',
            city TEXT DEFAULT '',
            district TEXT DEFAULT '',
            isp TEXT DEFAULT '',
            isp_short TEXT DEFAULT '',
            division_code TEXT DEFAULT '',
            latitude REAL,
            longitude REAL,
            geo_level TEXT DEFAULT '',
            idc_vendor TEXT DEFAULT ''
        )
    ''')
    cur.execute('CREATE INDEX idx_v4_start ON china_ipv4(start_ip_int)')
    cur.execute('CREATE INDEX idx_v4_end ON china_ipv4(end_ip_int)')
    cur.execute('CREATE INDEX idx_v4_province ON china_ipv4(province)')
    cur.execute('CREATE INDEX idx_v4_idc ON china_ipv4(idc_vendor)')

    # 从 IPv4 SQLite 复制数据
    if os.path.exists(V4_SQLITE):
        v4_conn = sqlite3.connect(V4_SQLITE)
        v4_cur = v4_conn.cursor()

        # 检查是否有 idc_vendor
        v4_cur.execute("PRAGMA table_info(china_ip)")
        cols = {r[1] for r in v4_cur.fetchall()}

        if 'idc_vendor' in cols:
            v4_cur.execute('''
                SELECT start_ip, end_ip, start_ip_int, end_ip_int, country,
                       province, city, district, isp, isp_short,
                       division_code, latitude, longitude, geo_level, idc_vendor
                FROM china_ip ORDER BY start_ip_int
            ''')
        else:
            v4_cur.execute('''
                SELECT start_ip, end_ip, start_ip_int, end_ip_int, country,
                       province, city, district, isp, isp_short,
                       division_code, latitude, longitude, geo_level, '' as idc_vendor
                FROM china_ip ORDER BY start_ip_int
            ''')

        rows = v4_cur.fetchall()
        cur.executemany('''
            INSERT INTO china_ipv4
            (start_ip, end_ip, start_ip_int, end_ip_int, country,
             province, city, district, isp, isp_short,
             division_code, latitude, longitude, geo_level, idc_vendor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', rows)
        v4_count = len(rows)
        v4_conn.close()
        print(f'  IPv4 记录: {v4_count}')
    else:
        v4_count = 0
        print('  [警告] china_ip_db.sqlite 不存在')

    # ========== IPv6 表 ==========
    print('  创建 IPv6 表...')

    def ipv6_to_hex(ip_str):
        by = ipaddress.IPv6Address(ip_str).packed
        return by.hex()

    cur.execute('''
        CREATE TABLE china_ipv6 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ip TEXT NOT NULL,
            end_ip TEXT NOT NULL,
            start_ip_hex TEXT NOT NULL DEFAULT '',
            end_ip_hex TEXT NOT NULL DEFAULT '',
            cidr TEXT DEFAULT '',
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
            idc_vendor TEXT DEFAULT ''
        )
    ''')
    cur.execute('CREATE INDEX idx_v6_start_hex ON china_ipv6(start_ip_hex)')
    cur.execute('CREATE INDEX idx_v6_end_hex ON china_ipv6(end_ip_hex)')
    cur.execute('CREATE INDEX idx_v6_cidr ON china_ipv6(cidr)')
    cur.execute('CREATE INDEX idx_v6_province ON china_ipv6(province)')
    cur.execute('CREATE INDEX idx_v6_idc ON china_ipv6(idc_vendor)')

    if os.path.exists(V6_SQLITE):
        v6_conn = sqlite3.connect(V6_SQLITE)
        v6_cur = v6_conn.cursor()
        v6_cur.execute('''
            SELECT start_ip, end_ip, cidr, prefix_len, country,
                   province, city, district, isp,
                   division_code, latitude, longitude, geo_level, idc_vendor
            FROM china_ipv6 ORDER BY cidr
        ''')
        rows = v6_cur.fetchall()
        hex_rows = []
        for r in rows:
            start_hex = ipv6_to_hex(r[0])
            end_hex = ipv6_to_hex(r[1])
            hex_rows.append((r[0], r[1], start_hex, end_hex, r[2], r[3], r[4],
                             r[5], r[6], r[7], r[8],
                             r[9], r[10], r[11], r[12], r[13]))
        cur.executemany('''
            INSERT INTO china_ipv6
            (start_ip, end_ip, start_ip_hex, end_ip_hex, cidr, prefix_len, country,
             province, city, district, isp,
             division_code, latitude, longitude, geo_level, idc_vendor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', hex_rows)
        v6_count = len(rows)
        v6_conn.close()
        print(f'  IPv6 记录: {v6_count}')
    else:
        v6_count = 0
        print('  [警告] china_ipv6_db.sqlite 不存在')

    # 元信息表
    now = datetime.now().isoformat()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cur.executemany('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', [
        ('version', '2.0'),
        ('description', '中国 IP 归属地数据库 (IPv4 + IPv6 合并版)'),
        ('ipv4_entries', str(v4_count)),
        ('ipv6_entries', str(v6_count)),
        ('generated_at', now),
        ('sources', 'ip2region + APNIC + GeoCN + AreaCity'),
    ])
    conn.commit()
    conn.close()

    size = os.path.getsize(OUT_SQLITE)
    print(f'  SQLite 合并完成: {size/1024:.1f} KB')
    return v4_count, v6_count


def merge_mysql(v4_count, v6_count):
    """合并 MySQL Dump"""
    print('[2/2] 合并 MySQL Dump...')
    if os.path.exists(OUT_SQL):
        os.remove(OUT_SQL)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = []
    lines.append('-- =============================================================')
    lines.append('-- 中国 IP 完整归属地数据库 (IPv4 + IPv6 合并版)')
    lines.append(f'-- 生成时间: {now}')
    lines.append(f'-- IPv4 记录: {v4_count}')
    lines.append(f'-- IPv6 记录: {v6_count}')
    lines.append('-- 数据来源: ip2region + APNIC + GeoCN + AreaCity')
    lines.append('-- =============================================================')
    lines.append('')
    lines.append('SET NAMES utf8mb4;')
    lines.append('SET FOREIGN_KEY_CHECKS = 0;')
    lines.append('')

    # ========== IPv4 表 ==========
    lines.append('-- -----------------------------------------')
    lines.append('-- IPv4 中国 IP 归属地表')
    lines.append('-- -----------------------------------------')
    lines.append('DROP TABLE IF EXISTS `china_ipv4_locations`;')
    lines.append('CREATE TABLE `china_ipv4_locations` (')
    lines.append('  `id` int(11) NOT NULL AUTO_INCREMENT,')
    lines.append('  `start_ip` varchar(15) NOT NULL COMMENT "起始IPv4",')
    lines.append('  `end_ip` varchar(15) NOT NULL COMMENT "结束IPv4",')
    lines.append('  `start_ip_int` bigint(20) NOT NULL COMMENT "起始IP整型",')
    lines.append('  `end_ip_int` bigint(20) NOT NULL COMMENT "结束IP整型",')
    lines.append('  `country` varchar(20) NOT NULL DEFAULT "中国" COMMENT "国家",')
    lines.append('  `province` varchar(30) NOT NULL DEFAULT "" COMMENT "省份",')
    lines.append('  `city` varchar(30) NOT NULL DEFAULT "" COMMENT "城市",')
    lines.append('  `district` varchar(30) NOT NULL DEFAULT "" COMMENT "区县",')
    lines.append('  `isp` varchar(50) NOT NULL DEFAULT "" COMMENT "运营商",')
    lines.append('  `division_code` varchar(6) NOT NULL DEFAULT "" COMMENT "行政区划代码",')
    lines.append('  `latitude` decimal(10,6) DEFAULT NULL COMMENT "纬度",')
    lines.append('  `longitude` decimal(10,6) DEFAULT NULL COMMENT "经度",')
    lines.append('  `geo_level` varchar(10) NOT NULL DEFAULT "" COMMENT "精度: province/city/district",')
    lines.append('  `idc_vendor` varchar(30) NOT NULL DEFAULT "" COMMENT "IDC/云厂商标记",')
    lines.append('  PRIMARY KEY (`id`),')
    lines.append('  KEY `idx_v4_start_ip_int` (`start_ip_int`),')
    lines.append('  KEY `idx_v4_end_ip_int` (`end_ip_int`),')
    lines.append('  KEY `idx_v4_province` (`province`),')
    lines.append('  KEY `idx_v4_idc_vendor` (`idc_vendor`)')
    lines.append(') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT="中国IPv4完整归属地数据库";')
    lines.append('')

    # 从 IPv4 SQL 提取数据（单条多行 INSERT）
    if os.path.exists(V4_SQL):
        with open(V4_SQL, 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取 INSERT ... SELECT ... FROM china_ip_locations 之间的数据块
        # v4 SQL 结构: INSERT INTO china_ip_locations VALUES (...), (...), ...;
        # 找到 INSERT 开头
        insert_start = content.find("INSERT INTO `china_ip_locations`")
        if insert_start >= 0:
            insert_end = content.find(';', insert_start)
            if insert_end >= 0:
                insert_block = content[insert_start:insert_end + 1]
                # 替换表名
                insert_block = insert_block.replace(
                    "INSERT INTO `china_ip_locations`",
                    "INSERT INTO `china_ipv4_locations`"
                )
                lines.append(insert_block)
                print(f'  IPv4 INSERT: 已提取 (插入 1 条多行语句)')

        # 也提取 IDC 参考表
        lines.append('')
        lines.append('-- -----------------------------------------')
        lines.append('-- IDC/云厂商 IP 段参考表')
        lines.append('-- -----------------------------------------')
        lines.append('DROP TABLE IF EXISTS `china_idc_ranges`;')
        insert_start = content.find("INSERT INTO `china_idc_ranges`")
        if insert_start >= 0:
            insert_end = content.find('SET FOREIGN_KEY_CHECKS = 1;', insert_start)
            if insert_end < 0:
                insert_end = len(content)
            idc_block = content[insert_start:insert_end].strip()
            lines.append(idc_block)
            print(f'  IDC INSERT: 已提取')

    # ========== IPv6 表 ==========
    lines.append('')
    lines.append('-- -----------------------------------------')
    lines.append('-- IPv6 中国 IP 归属地表')
    lines.append('-- -----------------------------------------')
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
    lines.append('  KEY `idx_v6_start_bin` (`start_ip_bin`),')
    lines.append('  KEY `idx_v6_end_bin` (`end_ip_bin`),')
    lines.append('  KEY `idx_v6_province` (`province`),')
    lines.append('  KEY `idx_v6_idc_vendor` (`idc_vendor`)')
    lines.append(') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT="中国IPv6完整归属地数据库";')
    lines.append('')

    # 从 IPv6 SQL 复制数据
    insert_count = 0
    if os.path.exists(V6_SQL):
        with open(V6_SQL, 'r', encoding='utf-8') as f:
            content = f.read()
        insert_start = content.find("INSERT INTO `china_ipv6_locations`")
        if insert_start >= 0:
            insert_end = content.find('SET FOREIGN_KEY_CHECKS = 1;', insert_start)
            if insert_end < 0:
                insert_end = len(content)
            insert_block = content[insert_start:insert_end].strip()
            lines.append(insert_block)
            print(f'  IPv6 INSERT: 已提取')

    lines.append('')
    lines.append('SET FOREIGN_KEY_CHECKS = 1;')
    lines.append('')

    with open(OUT_SQL, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    size = os.path.getsize(OUT_SQL)
    print(f'  MySQL 合并完成: {size/1024:.1f} KB')


def print_summary(v4_count, v6_count):
    print()
    print('=' * 60)
    print('  合并完成！')
    print('=' * 60)
    print(f'  输出文件:')
    print(f'    SQLite: {OUT_SQLITE} ({os.path.getsize(OUT_SQLITE)/1024:.1f} KB)')
    print(f'    MySQL:  {OUT_SQL} ({os.path.getsize(OUT_SQL)/1024:.1f} KB)')
    print(f'  记录:')
    print(f'    IPv4: {v4_count} 条')
    print(f'    IPv6: {v6_count} 条')
    print()
    print(f'  查询示例:')
    print(f'    python3 query_china_ip.py 27.39.157.25')
    print(f'    python3 query_china_ip.py 2409:8000::1')
    print()


if __name__ == '__main__':
    v4, v6 = merge_sqlite()
    merge_mysql(v4, v6)
    print_summary(v4, v6)

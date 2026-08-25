# -*- coding: utf-8 -*-
import maxminddb, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

tests = [
    ('OLD china_ipv6 2001:da8::', r'E:/v2board/resources/ipdb/backup_20260824/china_ipv6.mmdb', '2001:da8::'),
    ('OLD china_ipv6 240e::', r'E:/v2board/resources/ipdb/backup_20260824/china_ipv6.mmdb', '240e:1f::'),
    ('OLD global v4 res 8.8.8.8', r'E:/v2board/resources/ipdb/backup_global_20260824_122336/global_ipv4_residential.mmdb', '8.8.8.8'),
    ('OLD global v4 res 202.114.0.0', r'E:/v2board/resources/ipdb/backup_global_20260824_122336/global_ipv4_residential.mmdb', '202.114.0.0'),
    ('OLD global v6 res 2001:da8::', r'E:/v2board/resources/ipdb/backup_global_20260824_122336/global_ipv6_residential.mmdb', '2001:da8::'),
]
import os
for label, path, ip in tests:
    print(f'=== {label} ===')
    if not os.path.exists(path):
        print('  (file not found)'); continue
    try:
        r = maxminddb.open_database(path)
        res = r.get(ip)
        if isinstance(res, dict):
            print(' ', json.dumps(res, ensure_ascii=False)[:250])
        else:
            print('  none')
        r.close()
    except Exception as e:
        print(f'  ERR: {e}')
    print()

# Find actual backup_global dir name
import glob
dirs = glob.glob(r'E:/v2board/resources/ipdb/backup_global_*')
print('Backup global dirs:', dirs)
dirs2 = glob.glob(r'E:/v2board/resources/ipdb/backup_*')
print('All backups:', dirs2)

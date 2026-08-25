# -*- coding: utf-8 -*-
import maxminddb, sys, io, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Find the right backup dir
backup = glob.glob(r'E:/v2board/resources/ipdb/backup_global_*')
if not backup:
    print('No global backup found')
    sys.exit(0)
backup = backup[-1]  # latest
print(f'Using backup dir: {backup}')

tests = [
    ('OLD global_v4_res', backup + '/global_ipv4_residential.mmdb', '8.8.8.8'),
    ('OLD global_v4_idc', backup + '/global_ipv4_idc.mmdb', '3.4.12.4'),
    ('OLD global_v6_res', backup + '/global_ipv6_residential.mmdb', '2001:470::'),
    ('OLD global_v6_idc', backup + '/global_ipv6_idc.mmdb', '2406:daba:f000::'),
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
            print(' ', json.dumps(res, ensure_ascii=False)[:300])
        else:
            print('  none')
        r.close()
    except Exception as e:
        print(f'  ERR: {e}')
    print()

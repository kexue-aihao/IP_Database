# -*- coding: utf-8 -*-
import maxminddb, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check(label, path, ips):
    print(f'=== {label} ===')
    r = maxminddb.open_database(path)
    for ip in ips:
        result = r.get(ip)
        if isinstance(result, dict):
            has_isp = 'isp' in result
            keys = list(result.keys())
            print(f'  {ip}: has_isp={has_isp} keys={keys}')
            print(f'    {json.dumps(result, ensure_ascii=False)[:200]}')
    r.close()

check('V4 WITH ISP', r'E:/IP_Database/output/china_ipv4_with_isp.mmdb',
      ['114.114.114.114', '202.114.0.0', '39.134.114.0', '1.1.1.1', '8.8.8.8'])
print()
check('V6 WITH ISP', r'E:/IP_Database/output/china_ipv6_with_isp.mmdb',
      ['2001:da8::', '240e:1f::', '2001:250::', '2409:8a00::'])

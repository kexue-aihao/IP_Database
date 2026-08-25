import csv, maxminddb

anchors = []
with open('E:/IP_Database/data/anchor_ips.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        anchors.append(row)

reader = maxminddb.open_database('E:/IP_Database/output/china_ipv4.mmdb')

print('=== Sample anchor vs MMDB comparisons ===')
for a in anchors[:15]:
    ip = a['start_ip']
    if not ip:
        continue
    result = reader.get(ip)
    if not isinstance(result, dict):
        print(f"IP: {ip} -> NO MATCH in MMDB")
        continue
    print(f"IP: {ip}")
    print(f"  Anchor: prov={a['province']!r}, city={a['city']!r}")
    print(f"  MMDB:   prov={result.get('province')!r}, city={result.get('city')!r}, dist={result.get('district')!r}")
    print(f"  MMDB:   geo_level={result.get('geo_level')!r}, lat={result.get('latitude')}, lng={result.get('longitude')}")
    print()

reader.close()
print('Done')

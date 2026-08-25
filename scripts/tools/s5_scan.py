# -*- coding: utf-8 -*-
"""S5.10 报告辅助：扫描 china_ipv6_idc / china_ipv6_idc_enriched 两个 MMDB 全量记录。"""
import maxminddb
import os
import sys
from collections import Counter

io = sys.stdout

def out(s):
    io.write(s + "\n")

BASE = r"E:\IP_Database\output"

# ---------------- file 1 ----------------
path1 = os.path.join(BASE, "china_ipv6_idc.mmdb")
reader1 = maxminddb.open_database(path1)
meta1 = reader1.metadata()
records1 = []
vendors1 = Counter()
regions1 = Counter()
for net, data in reader1:
    records1.append((net, data))
    vendors1[data.get("vendor", "")] += 1
    regions1[data.get("region", "")] += 1
reader1.close()

out("=== china_ipv6_idc.mmdb ===")
out("file_size=%d" % os.path.getsize(path1))
out("ip_version=%s" % meta1.ip_version)
out("node_count=%d" % meta1.node_count)
out("database_type=%s" % meta1.database_type)
out("record_count=%d" % len(records1))
out("vendors(unique=%d): %s" % (len(vendors1), dict(vendors1)))
out("regions(unique=%d): %s" % (len(regions1), dict(regions1)))
out("-- first 12 records --")
for net, data in records1[:12]:
    out("  %s vendor=%r region=%r start=%s end=%s" % (
        net, data.get("vendor", ""), data.get("region", ""),
        data.get("start_ip", ""), data.get("end_ip", "")))

# ---------------- file 2 ----------------
path2 = os.path.join(BASE, "china_ipv6_idc_enriched.mmdb")
reader2 = maxminddb.open_database(path2)
meta2 = reader2.metadata()
records2 = []
vendors2 = Counter()
provinces2 = Counter()
cities2 = Counter()
sources2 = Counter()
geo_levels2 = Counter()
lat_types = Counter()
for net, data in reader2:
    records2.append((net, data))
    vendors2[data.get("vendor", "")] += 1
    provinces2[data.get("province", "")] += 1
    cities2[data.get("city", "")] += 1
    sources2[data.get("source", "")] += 1
    geo_levels2[data.get("geo_level", "")] += 1
    lat_types[type(data.get("latitude")).__name__] += 1
reader2.close()

out("")
out("=== china_ipv6_idc_enriched.mmdb ===")
out("file_size=%d" % os.path.getsize(path2))
out("ip_version=%s" % meta2.ip_version)
out("node_count=%d" % meta2.node_count)
out("database_type=%s" % meta2.database_type)
out("record_count=%d" % len(records2))
out("vendors(unique=%d): %s" % (len(vendors2), dict(vendors2)))
out("provinces(unique=%d): %s" % (len(provinces2), dict(provinces2)))
out("cities(unique=%d): %s" % (len(cities2), dict(cities2)))
out("sources(unique=%d): %s" % (len(sources2), dict(sources2)))
out("geo_levels(unique=%d): %s" % (len(geo_levels2), dict(geo_levels2)))
out("latitude types: %s" % dict(lat_types))
out("-- first 12 records --")
for net, data in records2[:12]:
    out("  %s vendor=%r province=%r city=%r lat=%r lng=%r geo_level=%r source=%r" % (
        net, data.get("vendor", ""), data.get("province", ""), data.get("city", ""),
        data.get("latitude", ""), data.get("longitude", ""),
        data.get("geo_level", ""), data.get("source", "")))
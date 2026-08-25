#!/usr/bin/env python3
"""Exact record counter for large MMDB files (background run)."""
import json
import os
import sys
import time

import maxminddb

FILES = [
    "china_ipv4_high_prec.mmdb",
    "china_ipv4_high_prec_v2.mmdb",
    "china_ipv4_with_isp.mmdb",
    "global_ipv4_residential.mmdb",
    "global_ipv6_residential.mmdb",
]
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")
RESULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "audit", "exact_counts.json")

results = {}
for fname in FILES:
    fp = os.path.join(OUTPUT_DIR, fname)
    t0 = time.time()
    count = 0
    reader = maxminddb.Reader(fp, maxminddb.const.MODE_FILE)
    for network, record in reader:
        if record is not None:
            count += 1
    reader.close()
    elapsed = time.time() - t0
    results[fname] = {"record_count": count, "scan_seconds": round(elapsed, 1)}
    print(f"{fname}: {count} records in {elapsed:.1f}s", flush=True)

os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
with open(RESULT_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"Wrote {RESULT_PATH}")
print("DONE")
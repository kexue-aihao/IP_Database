# -*- coding: utf-8 -*-
"""
S10.1 全库字段完整性扫描
遍历所有 output/*.mmdb（排除 tmp_v6.mmdb），检查
  isp / idc_vendor / is_residential / connection_type 四字段存在率。
输出：data/audit/final_field_scan.json
"""
import io
import os
import sys
import json
import glob
import maxminddb
import time

OUT_DIR = r"E:\IP_Database"
TARGET_FIELDS = ["isp", "idc_vendor", "is_residential", "connection_type"]

def scan_one(path: str):
    """返回 (record_count, field_coverage_dict, metadata_dict, error_msg)"""
    reader = maxminddb.open_database(path)
    meta = reader.metadata()
    md = {
        "database_type": meta.database_type or "",
        "description": meta.description.get("en") or meta.description.get("zh-CN") or "",
        "node_count": meta.node_count,
        "record_size": meta.record_size,
        "ip_version": meta.ip_version,
        "build_epoch": meta.build_epoch,
    }
    record_count = 0
    coverage = {f: 0 for f in TARGET_FIELDS}
    try:
        for prefix, data in reader:
            record_count += 1
            for f in TARGET_FIELDS:
                if f in data:
                    coverage[f] += 1
    except Exception as e:
        reader.close()
        return record_count, coverage, md, str(e)
    reader.close()
    return record_count, coverage, md, None

def main():
    start = time.time()
    # glob all MMDB files in output
    pattern = os.path.join(OUT_DIR, "output", "*.mmdb")
    all_files = sorted(glob.glob(pattern))
    # Exclude tmp_v6.mmdb
    files = [f for f in all_files if os.path.basename(f).lower() != "tmp_v6.mmdb"]
    print(f"Found {len(all_files)} MMDB files, scanning {len(files)} (excluded tmp_v6.mmdb)")

    results = {}
    scan_order = []

    for fpath in files:
        fname = os.path.basename(fpath)
        scan_order.append(fname)
        fsize = os.path.getsize(fpath)
        print(f"  Scanning: {fname} ({fsize:,} bytes)...", end=" ", flush=True)
        try:
            record_count, coverage, md, err = scan_one(fpath)
        except Exception as e:
            print(f"ERROR: {e}")
            results[fname] = {
                "error": str(e),
                "file_size": fsize,
            }
            continue

        if err:
            print(f"ERROR (partial scan): {err}")
            results[fname] = {
                "error": err,
                "file_size": fsize,
                "records_scanned": record_count,
                "coverage": coverage,
            }
            continue

        # Build per-field presence rate
        field_stats = {}
        for f in TARGET_FIELDS:
            rate = coverage[f] / record_count if record_count > 0 else 0.0
            field_stats[f] = {
                "present": coverage[f],
                "total": record_count,
                "rate": round(rate, 6),
            }

        # Summary: all four fields present? partially? missing?
        present_fields = [f for f in TARGET_FIELDS if coverage[f] == record_count]
        partial_fields = [f for f in TARGET_FIELDS if 0 < coverage[f] < record_count]
        zero_fields = [f for f in TARGET_FIELDS if coverage[f] == 0]

        if len(present_fields) == len(TARGET_FIELDS):
            verdict = "ALL_PRESENT"
        elif len(zero_fields) == len(TARGET_FIELDS):
            verdict = "ALL_MISSING"
        else:
            # At least one field has partial coverage
            verdict = "PARTIAL"

        results[fname] = {
            "file_size": fsize,
            "records": record_count,
            "metadata": md,
            "verdict": verdict,
            "fields": field_stats,
            "present_fields": present_fields,
            "partial_fields": partial_fields,
            "zero_fields": zero_fields,
        }

        print(f"OK ({record_count:,} records, {verdict})")

    elapsed = time.time() - start
    print(f"\nScanned {len(results)} files in {elapsed:.1f}s")

    # Build summary
    summary = {
        "task": "S10.1 全库字段完整性扫描",
        "scan_time": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "elapsed_seconds": round(elapsed, 1),
        "total_files": len(files),
        "files_with_errors": len([f for f in results if "error" in results[f]]),
        "target_fields": TARGET_FIELDS,
        "scan_order": scan_order,
        "files": results,
        "aggregate": {},
    }

    # Compute aggregate stats
    agg = {}
    for f in TARGET_FIELDS:
        total_present = 0
        total_records = 0
        files_with_field = 0
        files_total = 0
        for fname, r in results.items():
            if "error" in r:
                continue
            files_total += 1
            total_records += r["records"]
            if f in r["fields"]:
                total_present += r["fields"][f]["present"]
                if r["fields"][f]["present"] > 0:
                    files_with_field += 1
        agg[f] = {
            "files_with_field": files_with_field,
            "files_total": files_total,
            "total_present": total_present,
            "total_records": total_records,
            "global_rate": round(total_present / total_records, 6) if total_records > 0 else 0.0,
        }
    summary["aggregate"] = agg

    out_path = os.path.join(OUT_DIR, "data", "audit", "final_field_scan.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=False)
    print(f"\nWROTE: {out_path}")
    print("SUMMARY_JSON_OK")

    # Quick console summary
    print("\n=== 快速摘要 ===")
    for fname in scan_order:
        r = results.get(fname)
        if not r:
            continue
        if "error" in r:
            print(f"  [ERR]  {fname}: {r['error']}")
            continue
        parts = [f"rec={r['records']:,}"]
        for f in TARGET_FIELDS:
            fs = r["fields"].get(f, {})
            rate = fs.get("rate", 0)
            parts.append(f"{f}={rate:.1%}")
        print(f"  [{r['verdict']:12s}] {fname:45s} | {' | '.join(parts)}")
    print(f"\nTotal: {len(results)} files in {elapsed:.1f}s")

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
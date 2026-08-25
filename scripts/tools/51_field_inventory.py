#!/usr/bin/env python3
"""S1.1 — Field Inventory Scanner (single-pass exact version)
Scan all output/*.mmdb (excluding tmp_v6.mmdb), record field sets
(coverage, types, sample values), sample records, and EXACT record counts
in one full iteration per file. Write to data/audit/field_inventory.json.

Usage: python scripts/tools/51_field_inventory.py
"""

import glob
import json
import os
import sys
import time
from datetime import datetime, timezone

import maxminddb

EXCLUDE = {"tmp_v6.mmdb"}
OUTPUT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "output"))
AUDIT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "audit"))
MAX_SAMPLE_RECORDS = 5      # full sample records kept per file
MAX_SAMPLE_VALUES = 3       # distinct sample values kept per field

TYPE_MAP = {
    type(None): "null",
    str: "str",
    int: "int",
    float: "float",
    bool: "bool",
    list: "list",
    dict: "dict",
}


def get_type_name(val):
    return TYPE_MAP.get(type(val), type(val).__name__)


def trunc_str(val, limit=60):
    if isinstance(val, str) and len(val) > limit:
        return val[:limit] + "..."
    return val


def scan_mmdb(filepath):
    """Scan a single MMDB file in full; return its inventory."""
    filename = os.path.basename(filepath)
    size_bytes = os.path.getsize(filepath)

    result = {
        "filename": filename,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "metadata": {},
        "record_count": 0,
        "truncated": False,
        "fields": [],
        "samples": [],
    }

    try:
        reader = maxminddb.Reader(filepath, maxminddb.const.MODE_FILE)
    except Exception as e:  # noqa: BLE001
        result["error"] = "Failed to open: %s" % e
        return result

    try:
        meta = reader.metadata()
        result["metadata"] = {
            "node_count": meta.node_count,
            "record_size": meta.record_size,
            "ip_version": meta.ip_version,
            "database_type": meta.database_type,
            "binary_format_major_version": meta.binary_format_major_version,
            "binary_format_minor_version": meta.binary_format_minor_version,
            "build_epoch": meta.build_epoch,
            "languages": meta.languages,
            "description": meta.description,
        }
    except Exception as e:  # noqa: BLE001
        result["metadata_error"] = str(e)

    field_stats = {}  # name -> {"count": int, "types": set, "sample_values": []}
    t0 = time.time()

    for network, record in reader:
        if record is None:
            continue
        result["record_count"] += 1

        # Keep first MAX_SAMPLE_RECORDS full records
        if len(result["samples"]) < MAX_SAMPLE_RECORDS:
            result["samples"].append({
                "network": str(network),
                "record": record,
            })

        if isinstance(record, dict):
            for key, val in record.items():
                stat = field_stats.get(key)
                if stat is None:
                    stat = {"count": 0, "types": set(), "sample_values": []}
                    field_stats[key] = stat
                stat["count"] += 1
                stat["types"].add(get_type_name(val))
                sv = trunc_str(val)
                if len(stat["sample_values"]) < MAX_SAMPLE_VALUES and sv not in stat["sample_values"]:
                    stat["sample_values"].append(sv)

    reader.close()
    result["scan_seconds"] = round(time.time() - t0, 2)

    # Ordered fields list with coverage percentages
    ordered_fields = []
    for fname in sorted(field_stats.keys()):
        stat = field_stats[fname]
        pct = round(stat["count"] / max(result["record_count"], 1) * 100.0, 2)
        ordered_fields.append({
            "name": fname,
            "coverage_pct": pct,
            "records_with_field": stat["count"],
            "types": sorted(stat["types"]),
            "sample_values": stat["sample_values"],
        })
    result["fields"] = ordered_fields
    result["field_count"] = len(ordered_fields)

    if result["record_count"] == 0 and not result.get("error"):
        result["warning"] = "No records found (possible empty database or no-data records only)"

    return result


def main():
    os.makedirs(AUDIT_DIR, exist_ok=True)

    pattern = os.path.join(OUTPUT_DIR, "*.mmdb")
    all_files = sorted(glob.glob(pattern))
    files_to_scan = [f for f in all_files if os.path.basename(f) not in EXCLUDE]

    print("Found %d .mmdb files, scanning %d (excluded: %s)"
          % (len(all_files), len(files_to_scan), sorted(EXCLUDE)), flush=True)

    inventory = {
        "scan_info": {
            "task": "S1.1 Field Inventory Scanner",
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "total_files_found": len(all_files),
            "files_scanned": len(files_to_scan),
            "excluded_files": list(EXCLUDE),
        },
        "files": [],
    }

    scan_start = time.time()
    for fp in files_to_scan:
        fname = os.path.basename(fp)
        sys.stdout.write("  Scanning: %s ... " % fname)
        sys.stdout.flush()
        t0 = time.time()
        file_result = scan_mmdb(fp)
        elapsed = time.time() - t0
        rc = file_result["record_count"]
        nf = file_result["field_count"]
        print("done (%.1fs, %d records, %d fields)" % (elapsed, rc, nf), flush=True)
        inventory["files"].append(file_result)

    total_time = time.time() - scan_start
    inventory["scan_info"]["total_scan_time_seconds"] = round(total_time, 2)

    out_path = os.path.join(AUDIT_DIR, "field_inventory.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)

    print("\nDone. Inventory written to: %s" % out_path)
    print("Total files: %d, total time: %.1fs" % (len(files_to_scan), total_time))


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""S1.1 — Field Inventory Scanner
Scan all output/*.mmdb (excluding tmp_v6.mmdb), record field sets,
sample records, and record counts. Write to data/audit/field_inventory.json.
"""

import json
import os
import sys
import time
import glob
from datetime import datetime, timezone

import maxminddb


EXCLUDE = {"tmp_v6.mmdb"}
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")
AUDIT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "audit")
MAX_SAMPLE_RECORDS = 5
MAX_RECORDS_SCAN = 100000  # Limit for field discovery on large global files

# Type mapping for human-readable types
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


def scan_mmdb(filepath):
    """Scan a single MMDB file and return its inventory."""
    filename = os.path.basename(filepath)
    size_bytes = os.path.getsize(filepath)

    result = {
        "filename": filename,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "metadata": {},
        "record_count": 0,
        "fields": {},
        "samples": [],
    }

    try:
        reader = maxminddb.Reader(filepath, maxminddb.const.MODE_FILE)
    except Exception as e:
        result["error"] = f"Failed to open: {e}"
        return result

    # Read metadata
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
    except Exception as e:
        result["metadata_error"] = str(e)

    # Track field stats: {field: {type, count, sample_values}}
    field_stats = {}
    sample_idx = 0
    truncated = False

    for network, record in reader:
        if record is None:
            continue

        result["record_count"] += 1

        # Stop field discovery after MAX_RECORDS_SCAN records on very large files
        if result["record_count"] > MAX_RECORDS_SCAN:
            truncated = True
            break

        # Collect sample records (first MAX_SAMPLE_RECORDS)
        if len(result["samples"]) < MAX_SAMPLE_RECORDS:
            result["samples"].append({
                "network": str(network),
                "record": record,
            })

        # Collect field names and types
        if isinstance(record, dict):
            for key, val in record.items():
                if key not in field_stats:
                    field_stats[key] = {
                        "count": 0,
                        "types": set(),
                        "sample_values": [],
                    }
                field_stats[key]["count"] += 1
                field_stats[key]["types"].add(get_type_name(val))
                # Collect up to 3 unique sample values per field
                if len(field_stats[key]["sample_values"]) < 3:
                    sv = val
                    # Truncate long strings
                    if isinstance(sv, str) and len(sv) > 50:
                        sv = sv[:50] + "..."
                    if sv not in field_stats[key]["sample_values"]:
                        field_stats[key]["sample_values"].append(sv)

    reader.close()

    result["record_count_exact"] = not truncated
    if truncated:
        result["warning"] = (f"Record scan truncated at {MAX_RECORDS_SCAN} records; "
                             f"actual record count is unknown (field discovery complete)")
        result["record_count"] = MAX_RECORDS_SCAN

    # Build ordered fields list with coverage percentages
    ordered_fields = []
    for fname in sorted(field_stats.keys()):
        stat = field_stats[fname]
        pct = round(stat["count"] / max(result["record_count"], 1) * 100, 2)
        types_list = sorted(stat["types"])
        ordered_fields.append({
            "name": fname,
            "coverage_pct": pct,
            "records_with_field": stat["count"],
            "types": types_list,
            "sample_values": stat["sample_values"],
        })

    result["fields"] = ordered_fields

    if result["record_count"] == 0 and not result.get("error"):
        result["warning"] = "No records found (possible empty database or no-data records only)"

    return result


def main():
    # Ensure audit directory exists
    os.makedirs(AUDIT_DIR, exist_ok=True)

    # Find all .mmdb files in output/
    pattern = os.path.join(OUTPUT_DIR, "*.mmdb")
    all_files = sorted(glob.glob(pattern))

    # Filter out excluded files
    files_to_scan = [f for f in all_files if os.path.basename(f) not in EXCLUDE]

    print(f"Found {len(all_files)} .mmdb files, scanning {len(files_to_scan)} (excluded: {EXCLUDE})")

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
        print(f"  Scanning: {fname} ...", end=" ", flush=True)
        t0 = time.time()
        file_result = scan_mmdb(fp)
        elapsed = time.time() - t0
        rc = file_result["record_count"]
        nf = len(file_result["fields"])
        print(f"done ({elapsed:.1f}s, {rc} records, {nf} fields)")

        inventory["files"].append(file_result)

    total_time = time.time() - scan_start
    inventory["scan_info"]["total_scan_time_seconds"] = round(total_time, 2)

    # Write output
    out_path = os.path.join(AUDIT_DIR, "field_inventory.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Inventory written to: {out_path}")
    print(f"Total files: {len(files_to_scan)}, total time: {total_time:.1f}s")


if __name__ == "__main__":
    main()
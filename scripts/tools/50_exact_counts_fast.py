#!/usr/bin/env python3
"""Fast exact record counter for MMDB files.

Parses the search tree binary directly, matching the reader's layout.
Key insight: mmdb_writer writes the tree from offset 0 (no 16-byte header).
"""
import json
import os
import struct
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


def get_node_parser(record_size_bits: int):
    """Return (parse_fn, node_bytes) where parse_fn(bytes) -> (left_val, right_val)."""
    if record_size_bits == 24:
        # 6 bytes per node: [b1,b2,b3] [b4,b5,b6]
        def parse24(b: bytes) -> tuple[int, int]:
            left = (b[0] << 16) | (b[1] << 8) | b[2]
            right = (b[3] << 16) | (b[4] << 8) | b[5]
            return left, right
        return parse24, 6
    elif record_size_bits == 28:
        # 7 bytes per node: [b1,b2,b3,b4,b5,b6,b7]
        # left  = ((b4>>4)<<24) | (b1<<16) | (b2<<8) | b3  (28 bits, 4 bytes)
        # right = ((b4&0x0F)<<24) | (b5<<16) | (b6<<8) | b7
        def parse28(b: bytes) -> tuple[int, int]:
            left = ((b[3] >> 4) << 24) | (b[0] << 16) | (b[1] << 8) | b[2]
            right = ((b[3] & 0x0F) << 24) | (b[4] << 16) | (b[5] << 8) | b[6]
            return left, right
        return parse28, 7
    elif record_size_bits == 32:
        def parse32(b: bytes) -> tuple[int, int]:
            left = struct.unpack(">I", b[0:4])[0]
            right = struct.unpack(">I", b[4:8])[0]
            return left, right
        return parse32, 8
    else:
        raise ValueError(f"unsupported record_size_bits={record_size_bits}")


def count_records_fast(filepath: str):
    t0 = time.time()

    reader = maxminddb.Reader(filepath, maxminddb.const.MODE_FILE)
    meta = reader.metadata()
    node_count = meta.node_count
    record_size = meta.record_size
    reader.close()

    parse_fn, node_bytes = get_node_parser(record_size)
    tree_bytes = node_count * node_bytes
    tree_start = 0  # mmdb_writer writes tree from offset 0

    file_size = os.path.getsize(filepath)
    total_overhead = tree_start + tree_bytes
    if total_overhead > file_size:
        raise ValueError(
            f"Expected tree {tree_bytes} + header {tree_start} = {total_overhead} "
            f"exceeds file size {file_size}. "
            f"node_count={node_count}, rs={record_size}b, node_bytes={node_bytes}"
        )

    with open(filepath, "rb") as f:
        f.seek(tree_start)
        tree_data = f.read(tree_bytes)

    assert len(tree_data) == tree_bytes, f"read {len(tree_data)} expected {tree_bytes}"

    leaf_count = 0
    empty_count = 0
    internal_count = 0
    for node_idx in range(node_count):
        off = node_idx * node_bytes
        left, right = parse_fn(tree_data[off:off + node_bytes])

        for val in (left, right):
            if val > node_count:
                leaf_count += 1
            elif val == node_count:
                empty_count += 1
            else:
                internal_count += 1

    elapsed = time.time() - t0
    return {
        "record_count": leaf_count,
        "scan_seconds": round(elapsed, 1),
        "node_count": node_count,
        "record_size_bits": record_size,
        "node_bytes": node_bytes,
        "tree_bytes": tree_bytes,
        "file_size": file_size,
        "ip_version": meta.ip_version,
        "leaf_slots": leaf_count,
        "empty_slots": empty_count,
        "internal_slots": internal_count,
    }


def main():
    VALIDATE = {
        "china_ipv4_high_prec.mmdb": 275933,
        "china_ipv4_high_prec_v2.mmdb": 277772,
        "china_ipv4_with_isp.mmdb": 277772,
    }

    results = {}
    for fname in FILES:
        fp = os.path.join(OUTPUT_DIR, fname)
        try:
            r = count_records_fast(fp)
            results[fname] = r
            rc = r["record_count"]
            ok = ""
            if fname in VALIDATE:
                expected = VALIDATE[fname]
                if rc == expected:
                    ok = " [MATCH]"
                else:
                    ok = f" [MISMATCH expected={expected}]"
            print(f"{fname}: {rc} records ({r['scan_seconds']}s, "
                  f"rs={r['record_size_bits']}b, "
                  f"leaf={r['leaf_slots']} empty={r['empty_slots']} internal={r['internal_slots']}){ok}", flush=True)
        except Exception as e:
            results[fname] = {"error": str(e)}
            print(f"{fname}: ERROR {e}", flush=True)

    os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Wrote", RESULT_PATH)
    print("DONE")


if __name__ == "__main__":
    main()
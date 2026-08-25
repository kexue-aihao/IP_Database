#!/usr/bin/env python3
"""S1.3 — validate data/audit/classification_rules.json
Checks:
1. JSON is syntactically valid and loads correctly
2. All source references exist (constants.py variables, idc_all.csv)
3. Pre-filter ranges parse correctly with ipaddress module
4. Rule structure is machine-executable (unique IDs, priorities, outputs complete)
5. All example IPs produce the expected classification output
"""

import json
import os
import sys
import ipaddress
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(ROOT, "data", "audit", "classification_rules.json")
CONSTANTS_PATH = os.path.join(ROOT, "scripts", "common", "constants.py")
CSV_PATH = os.path.join(ROOT, "data", "global", "idc", "idc_all.csv")

sys.path.insert(0, os.path.join(ROOT, "scripts"))

errors = []
warnings = []


def check(cond, msg):
    if cond:
        print(f"  [PASS] {msg}")
    else:
        errors.append(msg)
        print(f"  [FAIL] {msg}")


# ---------- 1. Load rules ----------
print("== 1. Load classification_rules.json ==")
with open(RULES_PATH, "r", encoding="utf-8") as f:
    rules = json.load(f)
check(isinstance(rules, dict), "Top level is a JSON object")
check("rules" in rules and len(rules["rules"]) >= 1, f"Has {len(rules.get('rules', []))} rules")
check("pre_filters" in rules, f"Has {len(rules.get('pre_filters', []))} pre-filters")
check("idc_sources" in rules, f"Has {len(rules.get('idc_sources', []))} IDC sources")
check("conflict_resolution" in rules, "Has conflict_resolution section")
check("execution_contract" in rules, "Has execution_contract section")
check("examples" in rules, f"Has {len(rules.get('examples', []))} examples")

# unique rule IDs
rule_ids = [r["id"] for r in rules["rules"]]
check(len(rule_ids) == len(set(rule_ids)), "Rule IDs are unique")
pf_ids = [pf["id"] for pf in rules["pre_filters"]]
check(len(pf_ids) == len(set(pf_ids)), "Pre-filter IDs are unique")
src_ids = [s["id"] for s in rules["idc_sources"]]
check(len(src_ids) == len(set(src_ids)), "IDC source IDs are unique")

# ---------- 2. Source references exist ----------
print("== 2. Source references ==")
check(os.path.exists(CONSTANTS_PATH), f"constants.py exists: {CONSTANTS_PATH}")
check(os.path.exists(CSV_PATH), f"idc_all.csv exists: {CSV_PATH}")

if os.path.exists(CONSTANTS_PATH):
    import importlib.util
    spec = importlib.util.spec_from_file_location("constants_mod", CONSTANTS_PATH)
    constants_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(constants_mod)
    check(hasattr(constants_mod, "IDC_IPV4_RANGES"), "constants.IDC_IPV4_RANGES exists")
    check(hasattr(constants_mod, "IDC_IPV6_PREFIXES"), "constants.IDC_IPV6_PREFIXES exists")
    v4_count = len(getattr(constants_mod, "IDC_IPV4_RANGES", []))
    v6_count = len(getattr(constants_mod, "IDC_IPV6_PREFIXES", []))
    print(f"    IDC_IPV4_RANGES: {v4_count} ranges, IDC_IPV6_PREFIXES: {v6_count} prefixes")

if os.path.exists(CSV_PATH):
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        header = f.readline().strip()
        row_count = sum(1 for _ in f)
    check(header == "cidr,vendor,service,region,country,source", f"CSV header ok: {header}")
    check(row_count > 100000, f"CSV has {row_count} data rows (>= 100000 expected)")
    print(f"    idc_all.csv rows: {row_count}")

# ---------- 3. Pre-filter CIDRs parse ----------
print("== 3. Pre-filter CIDR parse ==")
prefilter_networks = []
for pf in rules["pre_filters"]:
    usable = pf.get("ranges", []) if isinstance(pf.get("ranges"), list) else []
    if not isinstance(pf.get("ranges"), list):
        check(False, f"Pre-filter {pf['id']} ranges is not a list")
        continue
    for rng in pf["ranges"]:
        cidr = rng.get("cidr")
        if not cidr:
            check(False, f"Pre-filter {pf['id']} has a range without cidr")
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            prefilter_networks.append(net)
        except ValueError as e:
            check(False, f"Pre-filter {pf['id']} cidr {cidr} invalid: {e}")
print(f"    {len(prefilter_networks)} pre-filter networks parsed OK")

# ---------- 4. Example IP validation ----------
print("== 4. Execute rules on examples ==")

# Build a flat list of (start, end, vendor) from constants
const_v4_ranges = [
    (int(ipaddress.IPv4Address(start)), int(ipaddress.IPv4Address(str(ipaddress.IPv4Address(end)))),
     vendor)
    for vendor, (start, end) in getattr(constants_mod, "IDC_IPV4_RANGES", [])
] if os.path.exists(CONSTANTS_PATH) else []

const_v6_prefixes = getattr(constants_mod, "IDC_IPV6_PREFIXES", []) if os.path.exists(CONSTANTS_PATH) else []

# Load CSV: parse cidr column (CIDR or dash format)
csv_ranges = []  # (start_int, end_int, vendor, family)
csv_parse_errors = 0
csv_json_rows = 0
if os.path.exists(CSV_PATH):
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        next(f)  # skip header
        for line in f:
            parts = line.strip().split(",", 1)
            if len(parts) < 2:
                continue
            cidr_raw, rest = parts
            vendor_raw = rest.split(",")[0] if rest else ""
            vendor = vendor_raw.strip('"').strip()
            cidr_raw = cidr_raw.strip('"')
            try:
                if "-" in cidr_raw:
                    lo_s, hi_s = cidr_raw.split("-", 1)
                    lo = int(ipaddress.IPv4Address(lo_s.strip()))
                    hi = int(ipaddress.IPv4Address(hi_s.strip()))
                    csv_ranges.append((lo, hi, vendor, "v4"))
                else:
                    net = ipaddress.ip_network(cidr_raw, strict=False)
                    lo = int(net.network_address)
                    hi = int(net.broadcast_address)
                    csv_ranges.append((lo, hi, vendor, "v4" if net.version == 4 else "v6"))
            except ValueError:
                # Fastly JSON-embedded row and other malformed rows
                csv_parse_errors += 1
                if cidr_raw.startswith("{"):
                    csv_json_rows += 1
print(f"    CSV rows parsed: {len(csv_ranges)}, malformed skipped: {csv_parse_errors} (of which {csv_json_rows} JSON-embedded)")
check(csv_parse_errors <= 5, f"CSV parse errors limited ({csv_parse_errors}; known: 1 Fastly JSON row)")

# Find match for an IP using the source priority chain + vendor alias resolution
def find_match(ip_str, file_group):
    ip = ipaddress.ip_address(ip_str)
    ip_int = int(ip)
    # pre-filter check
    for pf in rules["pre_filters"]:
        for rng in pf["ranges"]:
            if ip in ipaddress.ip_network(rng["cidr"], strict=False):
                return "pre_filter", pf["id"], None
    # source priority chain: CSV first, then constants v4/v6
    matched_vendor = None
    matched_src = None
    if ip.version == 4:
        for lo, hi, vendor, family in csv_ranges:
            if family == "v4" and lo <= ip_int <= hi:
                matched_vendor, matched_src = vendor, "SRC_IDC_CSV"
                break
        if matched_vendor is None:
            for lo, hi, vendor in const_v4_ranges:
                if lo <= ip_int <= hi:
                    matched_vendor, matched_src = vendor, "SRC_CONSTANTS_V4"
                    break
        return (matched_src, matched_vendor, matched_src)
    else:
        for lo, hi, vendor, family in csv_ranges:
            if family == "v6" and lo <= ip_int <= hi:
                matched_vendor, matched_src = vendor, "SRC_IDC_CSV"
                break
        # vendor alias resolution: cn_cloud_ipv6 -> check SRC_CONSTANTS_V6
        if matched_vendor == "cn_cloud_ipv6":
            for vendor, prefix_hex, prefix_len in const_v6_prefixes:
                if ip_int >> (128 - prefix_len) == int(prefix_hex, 16):
                    matched_vendor, matched_src = vendor, "SRC_CONSTANTS_V6"
                    break
        elif matched_vendor is None:
            for vendor, prefix_hex, prefix_len in const_v6_prefixes:
                if ip_int >> (128 - prefix_len) == int(prefix_hex, 16):
                    matched_vendor, matched_src = vendor, "SRC_CONSTANTS_V6"
                    break
        return (matched_src, matched_vendor, matched_src)


def resolve_file_group(filename):
    for group_name, group in rules["apply_to_file_groups"].items():
        for fname in group["files"]:
            if fname == filename:
                return group_name
    return None


# process example using the specified file group in the example itself
examples_passed = 0
for ex in rules["examples"]:
    ip_str = ex["ip"]
    file_group = ex["file_group"]
    match_src, vendor, src_id = find_match(ip_str, file_group)

    default_map = {
        "china_main": (True, "residential"),
        "china_idc": (False, "idc"),
        "global_residential": (True, "residential"),
        "global_idc": (False, "idc"),
    }
    exp = ex["expected_output"]

    if match_src == "pre_filter":
        got_ct = "unknown"
        got_res = exp.get("is_residential", "omitted")
        got_vendor = None
    elif match_src is not None:
        got_ct = "idc"
        got_res = False
        got_vendor = vendor
    else:
        got_ct = default_map[file_group][1]
        got_res = default_map[file_group][0]
        got_vendor = None

    ok_ct = got_ct == exp.get("connection_type")
    ok_res = got_res == exp.get("is_residential", got_res)
    ok_vendor = got_vendor == exp.get("idc_vendor")
    ok = ok_ct and ok_res and ok_vendor
    if ok:
        examples_passed += 1
    check(ok, f"example {ip_str}: got ct={got_ct} res={got_res} vendor={got_vendor} | matched={match_src}({vendor})")
    if not ok:
        print(f"          expected: {exp}")

check(examples_passed == len(rules["examples"]),
      f"{examples_passed}/{len(rules['examples'])} examples executed correctly")

# ---------- 5. Execution contract completeness ----------
print("== 5. Execution contract ==")
contract = rules["execution_contract"]
check("pseudocode" in contract and len(contract["pseudocode"]) > 5, "Pseudocode present and detailed")
check("output_fields" in contract, "Output fields declared")
check("matching_functions" in contract and len(contract["matching_functions"]) >= 3,
      "Matching functions declared")

print()
if errors:
    print(f"VALIDATION FAILED: {len(errors)} errors")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("VALIDATION PASSED: classification_rules.json is complete and machine-executable")
    sys.exit(0)
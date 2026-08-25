#!/usr/bin/env python3
"""
S1.7 - Shared MMDB Field Patch Library

Provides reusable functions for reading, patching, and writing MMDB files
used by the S2-S9 field patch pipeline (repo subagent pool).

API Functions:
  read_mmdb(path, ipv=None)         -> Iterator[(network, dict)]
  read_metadata(path)                -> dict
  add_missing_fields(data, ctx)     -> list[str]  (changed field names)
  normalize_coords(data)            -> dict
  idc_v4_lookup(ip_int)             -> str | None
  idc_v6_lookup(ip)                 -> str | None
  write_mmdb(records, out, ipv, db_type='Patched', desc='Patched MMDB')
  make_ctx(**kwargs)                -> PatchContext

CLI Usage:
  python scripts/tools/50_mmdb_field_patch.py --in X.mmdb --out Y.mmdb
      [--idc-mode auto|all-idc|all-res]
      [--normalize-coords]
      [--drop-legacy]
"""

import argparse
import bisect
import csv
import ipaddress
import os
import pickle
import sys
from collections import Counter

# Path setup ----------------------------------------------------------------
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(BASE, 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

try:
    from mmdb_writer import MMDBWriter
except ImportError:
    MMDBWriter = None  # deferred error in write_mmdb

import maxminddb
from netaddr import IPSet, IPNetwork
from common.constants import IDC_IPV4_RANGES, IDC_IPV6_PREFIXES

# Paths ---------------------------------------------------------------------
IDC_CSV_PATH = os.path.join(BASE, 'data', 'global', 'idc', 'idc_all.csv')

# ====================================================================
# Module-level lazy caches for IDC intervals
# ====================================================================
_IDC_V4_CACHE = None   # list of (start_int, end_int, vendor)
_IDC_V6_CACHE = None   # list of (start_int, end_int, vendor)
_IDC_V4_STARTS = None  # parallel list of start_int for bisect
_IDC_V6_STARTS = None


def _load_idc_csv():
    """Load idc_all.csv into (v4_intervals, v6_intervals) lists."""
    v4, v6 = [], []
    if not os.path.exists(IDC_CSV_PATH):
        return v4, v6
    with open(IDC_CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cidr = row.get('cidr', '').strip()
            if not cidr or '/' not in cidr:
                continue
            vendor = row.get('vendor', '').strip() or 'unknown'
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                s = int(net.network_address)
                e = int(net.broadcast_address)
                if net.version == 4:
                    v4.append((s, e, vendor))
                else:
                    v6.append((s, e, vendor))
            except ValueError:
                continue
    return v4, v6


def _ensure_idc_v4_intervals():
    """Build sorted (start, end, vendor) list for v4:
    constants first (higher priority), then idc_all.csv.
    """
    global _IDC_V4_CACHE, _IDC_V4_STARTS
    if _IDC_V4_CACHE is not None:
        return _IDC_V4_CACHE, _IDC_V4_STARTS

    intervals = []
    for vendor, (lo, hi) in IDC_IPV4_RANGES:
        intervals.append((lo, hi, vendor))
    csv_v4, _ = _load_idc_csv()
    intervals.extend(csv_v4)

    intervals.sort(key=lambda x: (x[0], x[1]))
    starts = [iv[0] for iv in intervals]
    _IDC_V4_CACHE = intervals
    _IDC_V4_STARTS = starts
    return intervals, starts


def _ensure_idc_v6_intervals():
    """Build sorted (start, end, vendor) list for v6 (csv only, no constants)."""
    global _IDC_V6_CACHE, _IDC_V6_STARTS
    if _IDC_V6_CACHE is not None:
        return _IDC_V6_CACHE, _IDC_V6_STARTS

    _, csv_v6 = _load_idc_csv()
    intervals = list(csv_v6)  # no constants v6 ranges with vendor
    intervals.sort(key=lambda x: (x[0], x[1]))
    starts = [iv[0] for iv in intervals]
    _IDC_V6_CACHE = intervals
    _IDC_V6_STARTS = starts
    return intervals, starts


def _bisect_lookup(ip_int, intervals, starts):
    """Binary search for a (start, end, vendor) containing ip_int.
    Returns the matching vendor string or None.
    Uses binary search on sorted intervals - O(log n) worst case.
    Since intervals are sorted by (start, end) and mostly non-overlapping
    (or minimally overlapping), we check the candidate interval and its
    neighbours for overlapping ranges.
    """
    i = bisect.bisect_right(starts, ip_int) - 1
    if i < 0:
        return None
    lo, hi, vendor = intervals[i]
    if lo <= ip_int <= hi:
        return vendor
    # Check a few neighbours for overlapping intervals (max 5)
    for di in (-1, 1, -2, 2, -3, 3, -4, 4, -5, 5):
        j = i + di
        if 0 <= j < len(intervals):
            lo, hi, vendor = intervals[j]
            if lo <= ip_int <= hi:
                return vendor
    return None


# ====================================================================
# 1) IDC Lookup Functions
# ====================================================================

def idc_v4_lookup(ip_int):
    """Look up IPv4 address (as int) against known IDC/cloud vendor ranges.

    Returns vendor string (e.g. '阿里云', 'AWS') or None if not found.
    Constants ranges (curated) are checked before idc_all.csv.
    """
    intervals, starts = _ensure_idc_v4_intervals()
    return _bisect_lookup(int(ip_int), intervals, starts)


def idc_v6_lookup(ip):
    """Look up IPv6 address against known IDC/cloud vendor prefixes.

    Args:
        ip: int, str, or IPv6Address object.

    Returns vendor string or None if not found.
    Checks constants prefixes (IDC_IPV6_PREFIXES) then idc_all.csv intervals.
    """
    if isinstance(ip, int):
        ip_int = ip
    elif isinstance(ip, ipaddress.IPv6Address):
        ip_int = int(ip)
    else:
        ip_int = int(ipaddress.IPv6Address(str(ip)))

    # 1) Check constants prefixes
    for vendor, prefix_hex, prefix_len in IDC_IPV6_PREFIXES:
        prefix_val = int(prefix_hex, 16)
        if prefix_len <= 128:
            shift = 128 - prefix_len
            if (ip_int >> shift) == prefix_val:
                return vendor

    # 2) Check csv intervals
    intervals, starts = _ensure_idc_v6_intervals()
    return _bisect_lookup(ip_int, intervals, starts)


# ====================================================================
# 2) Patch Context
# ====================================================================

def infer_db_kind(filename):
    """Heuristic: 'idc' if filename contains 'idc', 'residential' if 'residential',
    else 'mixed'."""
    fn = os.path.basename(filename).lower()
    if 'idc' in fn:
        return 'idc'
    if 'residential' in fn:
        return 'residential'
    return 'mixed'


class PatchContext:
    """Context for add_missing_fields().

    Properties:
        ip_int       — integer IP address for IDC lookups
        ipv          — 4 or 6
        idc_mode     — 'auto' | 'all-idc' | 'all-res'
        db_kind      — 'idc' | 'residential' | 'mixed' | None
        filename     — source filename (for db_kind inference)
        idc_vendor   — lazy-computed IDC vendor via lookup
    """

    __slots__ = ('ip_int', 'ipv', 'idc_mode', 'db_kind', 'filename',
                 '_idc_vendor', '_looked_up')

    def __init__(self, ip_int, ipv=4, idc_mode='auto',
                 db_kind=None, filename=''):
        self.ip_int = int(ip_int)
        self.ipv = int(ipv)
        self.idc_mode = idc_mode
        self.db_kind = db_kind if db_kind else infer_db_kind(filename)
        self.filename = filename
        self._idc_vendor = None
        self._looked_up = False

    @property
    def is_idc_db(self):
        return self.db_kind == 'idc'

    @property
    def is_res_db(self):
        return self.db_kind == 'residential'

    @property
    def idc_vendor(self):
        if not self._looked_up:
            self._looked_up = True
            if self.ipv == 4:
                self._idc_vendor = idc_v4_lookup(self.ip_int)
            else:
                self._idc_vendor = idc_v6_lookup(self.ip_int)
        return self._idc_vendor


def make_ctx(ip_int, ipv=4, idc_mode='auto', db_kind=None, filename=''):
    """Create a PatchContext from keyword arguments."""
    return PatchContext(ip_int, ipv, idc_mode, db_kind, filename)


def clean_org_name(name):
    """Remove RIR contact/role suffixes from org names (S11 addition).

    RDAP 'fn' often includes role text like ' - network administrator'
    which is not part of the company name. This strips those suffixes.
    """
    import re as _re
    if not name:
        return name
    name = _re.sub(r'\s*[-–—]\s*Network Administrator[s]?$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'\s+Network Administrator[s]?$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'\s*[-–—]\s*network administrator[s]?$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'\s+network administrator[s]?$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'^Sr\.?\s+', '', name)
    name = _re.sub(r'\.?\s*Network Administrator[s]?$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'\s*\.?\s*MNTNER$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'^MNTNER-', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'\s*[-–—]\s*$', '', name)
    name = _re.sub(r'\.+$', '', name)
    name = name.strip()
    if name.lower() in ('network administrator', 'network administrators', 'sr.', 'administrator', 'g.network administrators', 'g', 'mntner', 'domnet'):
        return ''
    if len(name) <= 1:
        return ''
    return name


# ====================================================================
# 3) Read / Metadata Helpers
# ====================================================================

def read_metadata(path):
    """Return a dict with ip_version, database_type, node_count."""
    reader = maxminddb.Reader(path, maxminddb.const.MODE_FILE)
    meta = reader.metadata()
    result = {
        'ip_version': meta.ip_version,
        'database_type': meta.database_type,
        'node_count': meta.node_count,
    }
    reader.close()
    return result


def read_mmdb(path, ipv=None):
    """Iterate over MMDB records yielding (network, data) tuples.

    Args:
        path: path to .mmdb file
        ipv: optional int (4 or 6) to filter by IP version

    Yields:
        (IPv4Network/IPv6Network, dict) for each record.
    """
    reader = maxminddb.Reader(path, maxminddb.const.MODE_FILE)
    try:
        for network, data in reader:
            if data is None:
                continue
            if ipv is not None and network.version != ipv:
                continue
            yield network, dict(data)
    finally:
        reader.close()


# ====================================================================
# 4) Coordinate Normalization
# ====================================================================

def normalize_coords(data):
    """Convert latitude/longitude values from str to float (WGS-84, 6 decimals).

    - Empty or None values → key removed.
    - Non-finite floats (nan, inf) → key removed.
    - String values that fail to parse → key removed.
    - Native floats are preserved (not rounded to avoid unintended precision loss).
    - Converted str values are rounded to 6 decimal places.

    Returns the modified data dict for convenience.
    """
    for k in ('latitude', 'longitude'):
        v = data.get(k)
        if v is None:
            data.pop(k, None)
            continue
        if isinstance(v, str):
            v = v.strip()
            if not v:
                data.pop(k, None)
                continue
            try:
                v = float(v)
            except ValueError:
                data.pop(k, None)
                continue
            data[k] = round(v, 6)
        elif isinstance(v, float):
            import math
            if not math.isfinite(v):
                data.pop(k, None)
        elif isinstance(v, int):
            data[k] = float(v)
    return data


# ====================================================================
# 5) Missing Field Filler
# ====================================================================

def _infer_connection_type(ctx, data):
    """Determine connection_type based on context."""
    # 1) Hard override from mode
    if ctx.idc_mode == 'all-idc':
        return 'idc'
    if ctx.idc_mode == 'all-res':
        return 'residential'

    # 2) Legacy / existing field mapping
    legacy_type = data.get('type')
    if legacy_type in ('idc', 'residential', 'unknown'):
        return legacy_type

    # 3) By db_kind
    if ctx.is_idc_db:
        return 'idc'
    if ctx.is_res_db:
        return 'residential'

    # 4) Auto-detect: IDC lookup
    if ctx.idc_vendor is not None:
        return 'idc'

    return 'residential'


def _infer_is_residential(ctx, connection_type):
    """Determine is_residential from connection_type + context."""
    if connection_type == 'idc':
        return False
    if connection_type == 'residential':
        return True
    # 'unknown' type: heuristic — IDC overlap → False, else True
    if ctx.idc_vendor is not None:
        return False
    return True


def add_missing_fields(data, ctx):
    """Fill missing target-schema fields.

    Fields processed (in order):
        connection_type, is_residential, idc_vendor, isp

    Also maps legacy 'type' → connection_type and 'vendor' → idc_vendor
    when the target field is missing.

    Returns:
        list[str] — names of fields that were added or changed.
    """
    changed = []

    # --- Legacy mapping: type → connection_type ---
    if 'connection_type' not in data:
        leg = data.get('type')
        if leg in ('idc', 'residential', 'unknown'):
            data['connection_type'] = leg
            changed.append('connection_type')

    # --- connection_type ---
    if 'connection_type' not in data:
        ct = _infer_connection_type(ctx, data)
        data['connection_type'] = ct
        changed.append('connection_type')

    ct = data.get('connection_type', 'unknown')

    # --- is_residential ---
    if 'is_residential' not in data:
        val = _infer_is_residential(ctx, ct)
        data['is_residential'] = val
        changed.append('is_residential')

    # --- Legacy mapping: vendor → idc_vendor ---
    if 'idc_vendor' not in data:
        leg_vendor = data.get('vendor')
        if leg_vendor:
            data['idc_vendor'] = leg_vendor
            changed.append('idc_vendor')

    # --- idc_vendor ---
    if 'idc_vendor' not in data:
        v = ctx.idc_vendor  # lazy lookup
        if v:
            data['idc_vendor'] = v
            changed.append('idc_vendor')

    # --- isp ---
    if 'isp' not in data:
        # IDC 库: isp = idc_vendor
        iv = data.get('idc_vendor')
        if iv:
            data['isp'] = iv
            changed.append('isp')

    return changed


# ====================================================================
# 6) MMDB Writer
# ====================================================================

def write_mmdb(records, out_path, ipv=4, db_type='Patched',
               languages=None, description=None, batch_size=1000):
    """Write records to an MMDB file.

    Args:
        records: iterable of (network, data) tuples.
                 network is an ipaddress.IPv4Network or IPv6Network.
        out_path: output path.
        ipv: 4 or 6.
        db_type: database_type metadata string.
        languages: list of language codes (default ['zh-CN']).
        description: dict of language -> description (default {zh-CN: 'Patched'}).
        batch_size: flush interval (not used, kept for future compatibility).

    Returns:
        int — number of networks successfully written.
    """
    if MMDBWriter is None:
        raise ImportError('mmdb_writer not available — install or check sys.path')

    if languages is None:
        languages = ['zh-CN']
    if description is None:
        description = {'zh-CN': 'Patched MMDB Database'}

    writer = MMDBWriter(ip_version=ipv, database_type=db_type,
                        languages=languages, description=description)
    count = 0
    errors = 0
    for network, data in records:
        try:
            writer.insert_network(IPSet(IPNetwork(str(network))), data)
            count += 1
        except Exception as exc:
            errors += 1
            if errors <= 3:
                print(f'  [WARN] insert_network failed for {network}: {exc}',
                      file=sys.stderr)

    writer.to_db_file(out_path)
    if errors:
        print(f'  [WARN] {errors} network(s) failed to insert', file=sys.stderr)
    return count


# ====================================================================
# CLI
# ====================================================================

def build_cli():
    p = argparse.ArgumentParser(
        description='S1.7 - MMDB Field Patch Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('--in', dest='input', required=True,
                   help='Source MMDB file path')
    p.add_argument('--out', dest='output', required=True,
                   help='Output MMDB file path (patched)')
    p.add_argument('--idc-mode', default='auto',
                   choices=['auto', 'all-idc', 'all-res'],
                   help='Connection type override mode (default: auto)')
    p.add_argument('--normalize-coords', action='store_true',
                   help='Convert latitude/longitude from str to float')
    p.add_argument('--drop-legacy', action='store_true',
                   help='Remove legacy "type" and "vendor" fields after mapping')
    p.add_argument('--ipv', type=int, choices=[4, 6], default=None,
                   help='Force IP version (default: auto-detect from source metadata)')
    p.add_argument('--db-type', default=None,
                   help='MMDB database_type string (default: inherit from source)')
    p.add_argument('--asn-map', default=None,
                   help='Path to ASN prefix map pickle (data/bgp/asn_prefix_map.pk) '
                        'for ISP/IDC enrichment via BGP ASN data')
    p.add_argument('--asn-org', default=None,
                   help='Path to ASN org JSON map (data/bgp/asn_org_map.json) '
                        'used to fill isp field from ASN holder names')
    p.add_argument('--idc-org-map', default=None,
                   help='Path to JSON map of ISP -> canonical vendor. '
                        'When provided, records whose `isp` field matches a key '
                        'force-update: connection_type=idc, is_residential=False, idc_vendor=vendor')
    return p


def main():
    parser = build_cli()
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f'[ERROR] Input file not found: {args.input}', file=sys.stderr)
        sys.exit(1)

    # Detect source metadata
    meta = read_metadata(args.input)
    ipv = args.ipv if args.ipv else meta['ip_version']
    db_type = args.db_type if args.db_type else meta.get('database_type', 'Patched')

    print(f'Source: {args.input}')
    print(f'  IP version:      {ipv}')
    print(f'  Database type:   {db_type}')
    print(f'  Node count:      {meta["node_count"]}')
    print(f'  IDC mode:        {args.idc_mode}')
    print(f'  Normalize coords: {args.normalize_coords}')
    print(f'  Drop legacy:     {args.drop_legacy}')
    print()

    # Infer db_kind from output filename (identifies the file group)
    out_filename = os.path.basename(args.output)
    db_kind = infer_db_kind(out_filename)

    # Load ASN enrichment data (S11)
    asn_map_data = None
    asn_org_map = None
    if args.asn_map and os.path.exists(args.asn_map):
        with open(args.asn_map, 'rb') as f:
            asn_map_data = pickle.load(f)
        print(f'  ASN map:      {asn_map_data.get("n_v4", 0)} v4 / {asn_map_data.get("n_v6", 0)} v6 prefixes')
    if args.asn_org and os.path.exists(args.asn_org):
        import json as _json
        with open(args.asn_org, 'r', encoding='utf-8') as f:
            try:
                asn_org_map = _json.load(f)
            except Exception:
                asn_org_map = None
        print(f'  ASN org map:  {len(asn_org_map) if asn_org_map else 0} entries')

    # Load IDC org map (S12: ISP-based IDC operator classification)
    idc_org_map = None
    idc_org_norm = None
    if args.idc_org_map and os.path.exists(args.idc_org_map):
        import json as _json
        with open(args.idc_org_map, 'r', encoding='utf-8') as f:
            try:
                idc_org_map = _json.load(f)
            except Exception:
                idc_org_map = None
        if idc_org_map:
            # Build accent/case-insensitive index
            import unicodedata as _ud
            idc_org_norm = {}
            for k, v in idc_org_map.items():
                nk = _ud.normalize('NFKD', k).encode('ascii', 'ignore').decode().lower().strip()
                if nk:
                    idc_org_norm[nk] = v
            print(f'  IDC org map:  {len(idc_org_map)} ISPs → {len(idc_org_norm)} norm keys')

    # ASN lookup helper
    def asn_lookup(ip_int, ipv):
        if asn_map_data is None:
            return None
        if ipv == 4:
            lst, starts = asn_map_data.get('v4_list', []), asn_map_data.get('v4_starts', [])
        else:
            lst, starts = asn_map_data.get('v6_list', []), asn_map_data.get('v6_starts', [])
        if not lst:
            return None
        i = bisect.bisect_right(starts, ip_int) - 1
        if i < 0:
            return None
        s, e, asn = lst[i]
        if s <= ip_int <= e:
            return asn
        for di in (-1, 1, -2, 2, -3, 3, -4, 4, -5, 5):
            j = i + di
            if 0 <= j < len(lst):
                s, e, asn = lst[j]
                if s <= ip_int <= e:
                    return asn
        return None

    # Normalization cache for S12 ISP matching
    _norm_cache = {}

    # Stats counters
    total = 0
    field_added = Counter()
    legacy_mapped = Counter()
    coords_normalized = 0
    idc_matched = 0
    asn_matched = 0

    def process():
        nonlocal total, coords_normalized, idc_matched, asn_matched
        for network, data in read_mmdb(args.input, ipv=ipv):
            total += 1

            # Compute IP integer for context
            ip_int = int(network.network_address)

            # Build context
            ctx = make_ctx(ip_int, ipv=ipv, idc_mode=args.idc_mode,
                           db_kind=db_kind, filename=args.output)

            # Coordinate normalization
            if args.normalize_coords:
                before = (data.get('latitude'), data.get('longitude'))
                normalize_coords(data)
                after = (data.get('latitude'), data.get('longitude'))
                if before != after:
                    coords_normalized += 1

            # Drop legacy fields before adding (if requested)
            if args.drop_legacy:
                data.pop('type', None)
                data.pop('vendor', None)

            # Add missing fields; track what changed
            changed = add_missing_fields(data, ctx)
            for f in changed:
                field_added[f] += 1
            if 'idc_vendor' in changed and ctx.idc_vendor:
                idc_matched += 1

            # ASN enrichment: fill isp/idc_vendor from BGP ASN data
            if asn_map_data is not None:
                asn = asn_lookup(ip_int, ipv)
                if asn is not None:
                    asn_matched += 1
                    # Fill isp if missing
                    if 'isp' not in data or not data.get('isp'):
                        if asn_org_map:
                            org = asn_org_map.get(str(asn))
                            if org:
                                org = clean_org_name(org)
                            if org and not org.startswith('AS'):
                                data['isp'] = org
                        else:
                            data['isp'] = f'AS{asn}'
                    # Fill idc_vendor if not set and connection_type is idc
                    if data.get('connection_type') == 'idc' and 'idc_vendor' not in data:
                        if asn_org_map:
                            org = asn_org_map.get(str(asn))
                            if org and not org.startswith('AS'):
                                data['idc_vendor'] = org

            # S12: ISP-based IDC operator override
            if idc_org_map is not None:
                isp_val = data.get('isp')
                if isp_val:
                    vendor = None
                    if isp_val in idc_org_map:
                        vendor = idc_org_map[isp_val]
                    elif idc_org_norm is not None:
                        nk = _norm_cache.get(isp_val)
                        if nk is None:
                            import unicodedata as _ud
                            nk = _ud.normalize('NFKD', isp_val).encode('ascii', 'ignore').decode().lower().strip()
                            _norm_cache[isp_val] = nk
                        vendor = idc_org_norm.get(nk)
                    if vendor:
                        if data.get('connection_type') != 'idc':
                            data['connection_type'] = 'idc'
                            field_added['connection_type'] += 1
                        if data.get('is_residential') is not False:
                            data['is_residential'] = False
                            field_added['is_residential'] += 1
                        if data.get('idc_vendor') != vendor:
                            data['idc_vendor'] = vendor
                            field_added['idc_vendor'] += 1

            # Legacy mapping tracking (not via add_missing_fields — already done)
            for leg in ('type', 'vendor'):
                if leg in data and not args.drop_legacy:
                    pass

            yield network, data

    # Write patched MMDB
    print(f'Writing {args.output} ...')
    written = write_mmdb(process(), args.output, ipv=ipv, db_type=db_type)
    print()

    # Summary
    print(f'{"=" * 60}')
    print(f'  Patch Summary')
    print(f'{"=" * 60}')
    print(f'  Records read:      {total}')
    print(f'  Networks written:  {written}')
    print(f'  Coords normalized: {coords_normalized}')
    print(f'  IDC matched:       {idc_matched}')
    print(f'  Fields added:')
    for fname in ['connection_type', 'is_residential', 'idc_vendor', 'isp']:
        cnt = field_added.get(fname, 0)
        print(f'    {fname:<20s} {cnt}')
    print(f'  Output: {os.path.abspath(args.output)}')
    size_kb = os.path.getsize(args.output) / 1024
    print(f'  Size:  {size_kb:.1f} KB')


if __name__ == '__main__':
    main()
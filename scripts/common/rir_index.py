#!/usr/bin/env python3
"""S11.1.9: RIR index loader - rir_v4_lookup(ip)->cc, rir_v6_lookup(ip)->cc"""
import os, bisect, pickle, sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_PATH = os.path.join(BASE, 'data', 'bgp', 'rir_index.pk')

_cache = None
def _load():
    global _cache
    if _cache is None:
        with open(INDEX_PATH, 'rb') as f:
            _cache = pickle.load(f)
    return _cache

def rir_v4_lookup(ip_int):
    idx = _load()
    lst = idx['v4_list']
    starts = idx['v4_starts']
    i = bisect.bisect_right(starts, int(ip_int)) - 1
    if i < 0: return None
    s, e, cc = lst[i]
    if s <= int(ip_int) <= e: return cc
    # check neighbors for overlap
    for di in (-1, 1, -2, 2, -3, 3):
        j = i + di
        if 0 <= j < len(lst):
            s, e, cc = lst[j]
            if s <= int(ip_int) <= e: return cc
    return None

def rir_v6_lookup(ip_int):
    idx = _load()
    lst = idx['v6_list']
    starts = idx['v6_starts']
    i = bisect.bisect_right(starts, int(ip_int)) - 1
    if i < 0: return None
    s, e, cc = lst[i]
    if s <= int(ip_int) <= e: return cc
    for di in (-1, 1, -2, 2, -3, 3):
        j = i + di
        if 0 <= j < len(lst):
            s, e, cc = lst[j]
            if s <= int(ip_int) <= e: return cc
    return None

def asn_to_cc(asn):
    idx = _load()
    return idx.get('asn_cc', {}).get(int(asn))

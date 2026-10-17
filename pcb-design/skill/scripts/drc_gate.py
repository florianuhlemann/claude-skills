#!/usr/bin/env python3
"""DRC gate for the export (v1.1): fail on anything that is not explicitly justified.

  python3 scripts/drc_gate.py <drc.json> <hardware/drc-allowlist.txt>
  python3 scripts/drc_gate.py --self-test

Errors, unconnected items and schematic-parity issues always fail. A warning passes only if a
line "<type>|<item description>" of the allowlist matches it exactly (the justification follows
after " # " on the same line and must point to the design notes). An allowlist line that matches
nothing also fails, so the list cannot go stale. kicad-cli 10 does not apply DRC exclusions from
the .kicad_pro (tested 2026-10-16, both formats), hence this gate.
"""
import json
import sys


def load_allow(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, why = line.partition(" # ")
        if not why.strip():
            sys.exit(f"allowlist entry without justification: {line}")
        out.append(key.strip())
    return out


def gate(d, allow):
    bad, used = [], set()
    for v in d.get("violations", []):
        key = v["type"] + "|" + "; ".join(i["description"] for i in v.get("items", []))
        if v.get("severity") == "warning" and key in allow:
            used.add(key)
        else:
            bad.append(f"{v.get('severity')}: {key}")
    bad += [f"unconnected: {u.get('description', '')}" for u in d.get("unconnected_items", [])]
    bad += [f"parity: {u.get('description', '')}" for u in d.get("schematic_parity", [])]
    bad += [f"stale allowlist entry: {a}" for a in allow if a not in used]
    return bad


def self_test():
    w = {"type": "lib_footprint_mismatch", "severity": "warning", "items": [{"description": "Footprint C15"}]}
    e = {"type": "clearance", "severity": "error", "items": [{"description": "Track"}]}
    allow = ["lib_footprint_mismatch|Footprint C15"]
    assert gate({"violations": [w]}, allow) == []
    assert gate({"violations": [w, e]}, allow), "error not caught"
    assert gate({"violations": []}, allow), "stale entry not caught"
    assert gate({"violations": [dict(w, severity="error")]}, allow), "error on an allowlisted item not caught"
    assert gate({"violations": [w], "unconnected_items": [{"description": "x"}]}, allow), "unconnected not caught"
    print("self-test OK: listed warning passes; error, stale entry, unconnected and an error on a listed item fail")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test(); sys.exit(0)
    d = json.load(open(sys.argv[1]))
    bad = gate(d, load_allow(sys.argv[2]))
    n = len(d.get("violations", []))
    print(f"DRC: {n} violation(s), {n - len([b for b in bad if not b.startswith(('unconnected', 'parity', 'stale'))])} allowlisted")
    for b in bad:
        print("  FAIL", b)
    sys.exit(1 if bad else 0)

#!/usr/bin/env python3
"""Lint: track geometry DRC does not report. Pure-text .kicad_pcb, no pcbnew.

  G1  zero-length segments
  G2  duplicate segments (same ends, layer, width)
  G3  segments off the 45-degree grid (angle mod 45 > tolerance)
  G4  acute corners (< 90 deg between two segments meeting at an endpoint)
      outside pads
  G5  T-junction branches that are not perpendicular to the through track
      (a branch at 45 deg creates an acute angle) outside pads

Usage: check_track_geometry.py <board.kicad_pcb> [--tol 0.5] [--strict] [--self-test]
Exit 0 (reviewed at the layout gate); --strict exits 1 on findings.
"""
import math
import re
import sys
from collections import defaultdict

# ---------------------------------------------------------------- S-expr (same as check_entry_angles)

def parse(text):
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text)
    pos = 0

    def node():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            lst = []
            while tokens[pos] != ")":
                lst.append(node())
            pos += 1
            return lst
        if tok.startswith('"'):
            return tok[1:-1].replace('\\"', '"')
        return tok

    return node()


def children(lst, key):
    return [c for c in lst if isinstance(c, list) and c and c[0] == key]


def child(lst, key):
    cs = children(lst, key)
    return cs[0] if cs else None


def nums(lst, n):
    return [float(x) for x in lst[1:1 + n]]


def rot(px, py, deg):
    t = math.radians(deg)
    return px * math.cos(t) + py * math.sin(t), -px * math.sin(t) + py * math.cos(t)

# ---------------------------------------------------------------- pads (for exclusion)

def load_pads(tree):
    pads = []
    for fp in children(tree, "footprint"):
        at = child(fp, "at")
        if not at:
            continue
        fx, fy = nums(at, 2)
        frot = float(at[3]) if len(at) > 3 else 0.0
        for p in children(fp, "pad"):
            pat, psz = child(p, "at"), child(p, "size")
            if not (pat and psz):
                continue
            px, py = nums(pat, 2)
            pdeg = float(pat[3]) if len(pat) > 3 else frot
            dx, dy = rot(px, py, frot)
            w, h = nums(psz, 2)
            pads.append((fx + dx, fy + dy, w, h, pdeg))
    return pads


def in_any_pad(x, y, pads, margin=0.0):
    for cx, cy, w, h, deg in pads:
        u, v = rot(x - cx, y - cy, -deg)
        if abs(u) <= w / 2 + margin and abs(v) <= h / 2 + margin:
            return True
    return False

# ---------------------------------------------------------------- analysis

def key(p):
    return (round(p[0], 4), round(p[1], 4))


def analyse(tree, tol=0.5):
    pads = load_pads(tree)
    segs = []
    for s in children(tree, "segment"):
        st, en, layer, width = child(s, "start"), child(s, "end"), child(s, "layer"), child(s, "width")
        if not (st and en):
            continue
        segs.append((tuple(nums(st, 2)), tuple(nums(en, 2)), layer[1] if layer else "", float(width[1]) if width else 0.0))
    findings = []
    seen = set()
    for i, (a, b, layer, w) in enumerate(segs):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-4:
            findings.append(("G1", layer, f"zero-length segment at {a}"))
            continue
        k = (tuple(sorted([key(a), key(b)])), layer, round(w, 4))
        if k in seen:
            findings.append(("G2", layer, f"duplicate segment {a}-{b}"))
        seen.add(k)
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 45.0
        dev = min(ang, 45.0 - ang)
        if dev > tol:
            findings.append(("G3", layer, f"off-45 segment {a}-{b} ({dev:.1f} deg off grid)"))
    # endpoints -> segments on the same layer
    ends = defaultdict(list)
    for i, (a, b, layer, w) in enumerate(segs):
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-4:
            continue
        gk = tuple(sorted([key(a), key(b)]))
        ends[(key(a), layer)].append((i, b[0] - a[0], b[1] - a[1], gk))
        ends[(key(b), layer)].append((i, a[0] - b[0], a[1] - b[1], gk))
    for (pt, layer), vecs in ends.items():
        if in_any_pad(pt[0], pt[1], pads, 0.01):
            continue
        for x in range(len(vecs)):
            for y in range(x + 1, len(vecs)):
                _, ax, ay, ka = vecs[x]
                _, bx, by, kb = vecs[y]
                if ka == kb:          # duplicate segment: reported as G2
                    continue
                c = (ax * bx + ay * by) / (math.hypot(ax, ay) * math.hypot(bx, by))
                ang = math.degrees(math.acos(max(-1.0, min(1.0, c))))
                if ang < 90 - tol:
                    findings.append(("G4", layer, f"acute corner {ang:.0f} deg at {pt}"))
    # T-junctions: an endpoint lying on the interior of another segment
    for (pt, layer), vecs in ends.items():
        if in_any_pad(pt[0], pt[1], pads, 0.01):
            continue
        for j, (a, b, l2, w) in enumerate(segs):
            if l2 != layer or any(i == j for i, *_ in vecs):
                continue
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            if L2 < 1e-8:
                continue
            t = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2
            if t <= 0.02 or t >= 0.98:
                continue
            px, py = a[0] + t * dx, a[1] + t * dy
            if math.hypot(px - pt[0], py - pt[1]) > w / 2 + 1e-3:
                continue
            for _, vx, vy, _k in vecs:
                c = (vx * dx + vy * dy) / (math.hypot(vx, vy) * math.sqrt(L2))
                ang = math.degrees(math.acos(max(-1.0, min(1.0, c))))
                ang = min(ang, 180 - ang)
                if ang < 90 - tol:
                    findings.append(("G5", layer, f"T-branch at {ang:.0f} deg to through track at {pt}"))
    # dedupe
    out, s2 = [], set()
    for f in findings:
        if f not in s2:
            s2.add(f)
            out.append(f)
    return len(segs), out


def report(n, findings):
    print(f"segments: {n}; findings: {len(findings)}")
    for rule, layer, detail in findings:
        print(f"{rule:<4}{layer:<8}{detail}")

# ---------------------------------------------------------------- self-test

SELFTEST = """(kicad_pcb (version 20251001)
 (footprint "R" (layer "F.Cu") (at 50 50 0) (property "Reference" "R1")
  (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))
 (segment (start 0 0) (end 10 0) (width 0.2) (layer "F.Cu"))
 (segment (start 10 0) (end 10 10) (width 0.2) (layer "F.Cu"))
 (segment (start 10 10) (end 0 20) (width 0.2) (layer "F.Cu"))
 (segment (start 20 0) (end 30 0) (width 0.2) (layer "F.Cu"))
 (segment (start 30 0) (end 21 -9) (width 0.2) (layer "F.Cu"))
 (segment (start 40 0) (end 40 0) (width 0.2) (layer "F.Cu"))
 (segment (start 0 25) (end 10 25) (width 0.2) (layer "F.Cu"))
 (segment (start 10 25) (end 0 25) (width 0.2) (layer "F.Cu"))
 (segment (start 0 30) (end 10 31) (width 0.2) (layer "F.Cu"))
 (segment (start 0 40) (end 20 40) (width 0.2) (layer "F.Cu"))
 (segment (start 10 40) (end 15 45) (width 0.2) (layer "F.Cu"))
 (segment (start 0 60) (end 20 60) (width 0.2) (layer "F.Cu"))
 (segment (start 10 60) (end 10 70) (width 0.2) (layer "F.Cu"))
 (segment (start 50 50) (end 52 52) (width 0.2) (layer "F.Cu"))
 (segment (start 50 50) (end 48 52) (width 0.2) (layer "F.Cu"))
)"""


def self_test():
    n, f = analyse(parse(SELFTEST))
    rules = defaultdict(list)
    for r, _, d in f:
        rules[r].append(d)
    assert len(rules["G1"]) == 1, f                      # zero-length at (40,0)
    assert len(rules["G2"]) == 1, f                      # duplicate (0,20)-(10,20)
    assert len(rules["G3"]) == 1 and "(0.0, 30.0)" in rules["G3"][0], f   # 5.7 deg segment
    assert len(rules["G4"]) == 1 and "(30.0, 0.0)" in rules["G4"][0], f   # acute 45 deg corner
    assert len(rules["G5"]) == 1 and "(10.0, 40.0)" in rules["G5"][0], f  # 45-deg T-branch
    # 90 and 135 deg corners, perpendicular T, and the 90 deg corner inside pad R1 are clean
    print("self-test OK: G1 zero-length, G2 duplicate, G3 off-45, G4 acute corner, G5 45-deg T-branch flagged; "
          "90/135 deg corners, perpendicular T and in-pad corner clean")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    tol = float(argv[argv.index("--tol") + 1]) if "--tol" in argv else 0.5
    with open(argv[0], encoding="utf-8") as fh:
        n, findings = analyse(parse(fh.read()), tol)
    report(n, findings)
    return 1 if ("--strict" in argv and findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

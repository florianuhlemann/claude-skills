#!/usr/bin/env python3
"""KiCad position file -> JLCPCB CPL: rotation offsets, pad-centroid
placement points, BOM-filtered designators.

Usage:
  fix_cpl_rotation.py <kicad_pos.csv> <rotation-corrections.csv> <out_cpl.csv>
                      [--pcb board.kicad_pcb] [--centroid tht|all]
                      [--bom bom.csv] [--no-flip-y]

KiCad pos CSV columns: Ref,Val,Package,PosX,PosY,Rot,Side
JLC CPL columns:       Designator,Mid X,Mid Y,Layer,Rotation

rotation-corrections.csv: footprint_regex,rotation_offset_deg[,confirmed,note]
First matching regex (on the footprint name without library prefix) wins.

--pcb + --centroid: KiCad places the footprint anchor; JLC wants the part
centre. With the board file, the placement point is moved to the centre of
the pads' bounding box for THT parts (tht, default when --pcb is given) or
every part (all). The pos file's Y axis is inverted relative to the board
file (unless --no-flip-y), so the shift is applied as (+dx, -dy).

--bom: keep only designators that appear in the BOM's Designator column
(grouped "R1,R2" cells and ranges "R1-R5" are expanded) — drops test
points, net ties, fiducials. Better still: set "exclude from position
files / BOM" on those footprints. --self-test plants a range and a
dropped part and checks both.
"""
import csv
import math
import re
import sys

# ---------------------------------------------------------------- S-expr

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


def rot(px, py, deg):
    t = math.radians(deg)
    return px * math.cos(t) + py * math.sin(t), -px * math.sin(t) + py * math.cos(t)


def centroid_shifts(pcb_path, mode):
    """ref -> (dx, dy, is_tht) in board coordinates: pad-bbox centre minus anchor."""
    with open(pcb_path, encoding="utf-8") as fh:
        tree = parse(fh.read())
    out = {}
    for fp in children(tree, "footprint"):
        ref = ""
        for p in children(fp, "property"):
            if len(p) > 2 and p[1] == "Reference":
                ref = p[2]
        at = child(fp, "at")
        if not (ref and at):
            continue
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0.0
        xs, ys, tht = [], [], False
        for p in children(fp, "pad"):
            if len(p) > 1 and p[1] == "":
                continue
            if len(p) > 2 and p[2] in ("thru_hole", "np_thru_hole"):
                tht = True
            pat, psz = child(p, "at"), child(p, "size")
            if not (pat and psz):
                continue
            dx, dy = rot(float(pat[1]), float(pat[2]), frot)
            w, h = float(psz[1]), float(psz[2])
            r = max(w, h) / 2
            xs += [fx + dx - r, fx + dx + r]
            ys += [fy + dy - r, fy + dy + r]
        if not xs:
            continue
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        if mode == "all" or tht:
            out[ref] = (cx - fx, cy - fy, tht)
    return out


def load_table(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pat = (r.get("footprint_regex") or "").strip()
            if pat:
                rows.append((re.compile(pat), float(r["rotation_offset_deg"])))
    return rows


RANGE = re.compile(r"^([A-Za-z]+)(\d+)\s*[-–]\s*(?:([A-Za-z]+))?(\d+)$")


def expand_refs(cell):
    """'R1, R2' -> {R1, R2}; 'R1-R5' / 'R1–5' -> {R1..R5}; 'C7' -> {C7}."""
    out = set()
    for d in re.split(r"[,;]+|\s+(?![-–])", cell):
        d = d.strip()
        if not d:
            continue
        m = RANGE.match(d)
        if m and (m.group(3) in (None, m.group(1))):
            pre, a, b = m.group(1), int(m.group(2)), int(m.group(4))
            lo, hi = min(a, b), max(a, b)
            out.update(f"{pre}{i}" for i in range(lo, hi + 1))
        else:
            out.add(d)
    return out


def load_bom_refs(path):
    refs = set()
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        col = next((c for c in rd.fieldnames or [] if c.lower().startswith("designator") or c.lower() == "reference"), None)
        if not col:
            sys.exit("BOM has no Designator/Reference column")
        for r in rd:
            refs |= expand_refs(r[col])
    return refs


def self_test():
    assert expand_refs("R1, R2") == {"R1", "R2"}
    assert expand_refs("R1-R5") == {"R1", "R2", "R3", "R4", "R5"}, expand_refs("R1-R5")
    assert expand_refs("C7-C8, C10") == {"C7", "C8", "C10"}
    assert expand_refs("D3–D4") == {"D3", "D4"}
    assert "R3" in expand_refs("R1-R5") and "TP1" not in expand_refs("R1-R5")
    print("self-test OK: ranges expanded (R1-R5 keeps R3), plain lists kept, non-BOM refs dropped")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    if len(argv) < 3:
        print(__doc__)
        return 2
    pos_path, table_path, out_path = argv[:3]
    pcb = argv[argv.index("--pcb") + 1] if "--pcb" in argv else None
    mode = argv[argv.index("--centroid") + 1] if "--centroid" in argv else "tht"
    bom = argv[argv.index("--bom") + 1] if "--bom" in argv else None
    flip = "--no-flip-y" not in argv
    table = load_table(table_path)
    shifts = centroid_shifts(pcb, mode) if pcb else {}
    keep = load_bom_refs(bom) if bom else None

    with open(pos_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out, unmatched, dropped, shifted = [], set(), [], 0
    for r in rows:
        ref = r["Ref"]
        if keep is not None and ref not in keep:
            dropped.append(ref)
            continue
        fp = r.get("Package") or r.get("Footprint") or ""
        short = fp.split(":")[-1]
        rotv = float(r["Rot"])
        off = next((o for pat, o in table if pat.search(short)), None)
        if off is None:
            unmatched.add(short)
            off = 0.0
        side = r["Side"].strip().lower()
        rotv = (-rotv - off) % 360 if side == "bottom" else (rotv + off) % 360
        x, y = float(r["PosX"]), float(r["PosY"])
        if ref in shifts:
            dx, dy, _ = shifts[ref]
            x += dx
            y += -dy if flip else dy
            shifted += 1
        out.append({"Designator": ref, "Mid X": f"{x:.4f}mm", "Mid Y": f"{y:.4f}mm",
                    "Layer": "Top" if side == "top" else "Bottom", "Rotation": f"{rotv:.1f}"})
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} placements to {out_path}; centroid-shifted: {shifted}; dropped (not in BOM): {len(dropped)}")
    if dropped:
        print("  dropped:", ", ".join(sorted(dropped)))
    if unmatched:
        print("no rotation rule for (offset 0 applied — verify in JLC preview):")
        for s in sorted(unmatched):
            print("  ", s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

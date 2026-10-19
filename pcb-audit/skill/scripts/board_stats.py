#!/usr/bin/env python3
"""Board statistics read from the .kicad_pcb (no pcbnew): the evidence base of every audit.

Usage:
  board_stats.py <board.kicad_pcb> [--pro <board.kicad_pro>] [--json] [--strict]
  board_stats.py --self-test

Reports
  outline     Edge.Cuts bbox (W x H), loops, outer area, smallest edge arc radius, sharp inside
              corners (a router bit leaves its radius there), outline closed or not
  layers      copper layers in the layer table and in the stackup (thickness), finish, board thickness
  tracks      count and length per copper layer, minimum width overall, per net class (net classes
              and patterns from the .kicad_pro next to the board, or --pro): class width, narrowest
              track used, tracks below the class width
  vias        histogram of size / drill / type
  zones       per net and layer: zones, outline area, fill area, fill pieces (each fill polygon is
              one piece of copper), pieces KiCad marked as islands; zones that were never filled
  planes      copper layers on which a net's fill is split into several pieces
  drills      finished-hole table: vias, round PTH, PTH slots, NPTH
  parts       SMD / THT per side, DNP, board-only, excluded from BOM / position files; THT refs
  dfm         finest SMD pitch and smallest pad gap (mask dam = gap - 2 x mask expansion) with the
              footprint, vias or plated holes under a paste opening, aux origin vs the outline and
              the number of parts that would get negative CPL coordinates from it
Flags (also in --json "flags"): outline open, sharp inside corner, zone not filled, plane split,
track below its class width, aux origin outside the outline / negative CPL coordinates, via or hole
under paste. Exit 0 (evidence, read at the gate); --strict exits 1 when a flag is raised.
Pitfalls: fill areas are only as fresh as the last zone fill saved in the file (an unfilled zone is
flagged, a stale fill is not detectable); net classes live in the .kicad_pro, not in the board.
"""
import fnmatch
import json
import math
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_board import load, outline_bbox, pad_dist, point_in_poly, poly_area, poly_point_dist  # noqa: E402

TOL = 0.02


def r3(v):
    return round(v, 3)

# ---------------------------------------------------------------- outline


def chain_loops(edges):
    """[(vertices, sharp flags, closed)] from Edge.Cuts primitives; sharp = junction of two straight pieces."""
    loops = []
    for e in edges:
        if e.closed:
            loops.append((list(e.pts), [e.kind in ("rect", "poly")] * len(e.pts), True))
    open_ = [e for e in edges if not e.closed and e.ends]
    used = [False] * len(open_)
    for i in range(len(open_)):
        if used[i]:
            continue
        used[i] = True
        chain = [(open_[i], False)]
        start, cur = open_[i].ends
        while math.dist(cur, start) > TOL:
            nxt = None
            for j, e in enumerate(open_):
                if used[j]:
                    continue
                if math.dist(e.ends[0], cur) <= TOL:
                    nxt = (j, False)
                elif math.dist(e.ends[1], cur) <= TOL:
                    nxt = (j, True)
                if nxt:
                    break
            if not nxt:
                break
            used[nxt[0]] = True
            e = open_[nxt[0]]
            chain.append((e, nxt[1]))
            cur = e.ends[0] if nxt[1] else e.ends[1]
        closed = math.dist(cur, start) <= TOL
        verts, sharp = [], []
        for k, (e, rev) in enumerate(chain):
            pts = list(reversed(e.pts)) if rev else list(e.pts)
            prev = chain[k - 1][0] if (k > 0 or closed) else None
            for n, p in enumerate(pts[:-1] if (closed or k < len(chain) - 1) else pts):
                verts.append(p)
                sharp.append(n == 0 and prev is not None and e.kind == "line" and prev.kind == "line")
        loops.append((verts, sharp, closed))
    return loops


def signed_area(pts):
    n = len(pts)
    return sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n)) / 2.0


def outline_stats(b):
    bb = outline_bbox(b)
    loops = chain_loops(b.edges)
    res = {"bbox": None, "loops": len(loops), "closed": all(c for _, _, c in loops) and bool(loops),
           "outer_area_mm2": None, "min_arc_radius": None, "sharp_inside_corners": []}
    if not bb:
        return res, None
    res["bbox"] = {"x0": r3(bb[0]), "y0": r3(bb[1]), "x1": r3(bb[2]), "y1": r3(bb[3]),
                   "w": r3(bb[2] - bb[0]), "h": r3(bb[3] - bb[1])}
    radii = [e.radius for e in b.edges if e.kind == "arc" and e.radius]
    res["min_arc_radius"] = r3(min(radii)) if radii else None
    closed = [(v, s) for v, s, c in loops if c and len(v) >= 3]
    outer = max(closed, key=lambda vs: abs(signed_area(vs[0])))[0] if closed else None
    if outer:
        res["outer_area_mm2"] = round(abs(signed_area(outer)), 1)
    for verts, sharp, c in loops:
        if not c or len(verts) < 3:
            continue
        sa = signed_area(verts)
        is_outer = verts is outer
        n = len(verts)
        for i in range(n):
            if not sharp[i]:
                continue
            p0, p1, p2 = verts[i - 1], verts[i], verts[(i + 1) % n]
            cr = (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])
            if abs(cr) < 1e-9:
                continue
            inside = (cr * sa < 0) if is_outer else (cr * sa > 0)
            if inside:
                res["sharp_inside_corners"].append([r3(p1[0]), r3(p1[1])])
    return res, outer

# ---------------------------------------------------------------- net classes


def netclasses(pro_path):
    if not pro_path or not os.path.exists(pro_path):
        return None
    j = json.load(open(pro_path, encoding="utf-8"))
    ns = j.get("net_settings", {})
    classes = {c.get("name", "Default"): c for c in ns.get("classes", [])}
    assign = ns.get("netclass_assignments") or {}
    patterns = [(p.get("pattern", ""), p.get("netclass", "Default")) for p in (ns.get("netclass_patterns") or [])]

    def cls(net):
        if net in assign:
            a = assign[net]
            return a[0] if isinstance(a, list) and a else a
        for pat, c in patterns:
            if fnmatch.fnmatchcase(net, pat) or fnmatch.fnmatchcase(net.split("/")[-1], pat):
                return c
        return "Default"
    return classes, cls

# ---------------------------------------------------------------- stats


def stats(path, pro=None):
    b = load(path)
    flags = []
    out = {"board": os.path.basename(path)}
    o, outer = outline_stats(b)
    out["outline"] = o
    if not o["closed"]:
        flags.append("outline not closed (or no Edge.Cuts)")
    for c in o["sharp_inside_corners"]:
        flags.append(f"sharp inside corner at ({c[0]}, {c[1]}): the fab's router leaves its bit radius")
    cu_stack = [s for s in b.stackup if s.get("type") == "copper"]
    thick = sum(float(s["thickness"]) for s in b.stackup if "thickness" in s) if b.stackup else None
    out["layers"] = {"copper": b.copper, "count": len(b.copper),
                     "stackup_copper": [{"name": s["name"], "thickness": s.get("thickness")} for s in cu_stack],
                     "finish": b.finish, "board_thickness": r3(thick) if thick else None}
    if cu_stack and len(cu_stack) != len(b.copper):
        flags.append(f"stackup has {len(cu_stack)} copper layers, layer table {len(b.copper)}")
    # tracks
    per_layer = defaultdict(lambda: [0, 0.0])
    for s in b.segs:
        per_layer[s.layer][0] += 1 if s.kind == "segment" else 0.5
        per_layer[s.layer][1] += s.length
    widths = [s for s in b.segs if s.width > 0]
    mn = min((s.width for s in widths), default=None)
    out["tracks"] = {"per_layer": {k: {"count": int(v[0]), "length_mm": round(v[1], 1)} for k, v in per_layer.items()},
                     "min_width": mn, "min_width_nets": sorted({s.net for s in widths if s.width == mn})[:8] if mn else []}
    pro = pro or os.path.splitext(path)[0] + ".kicad_pro"
    nc = netclasses(pro)
    if nc:
        classes, cls = nc
        per = defaultdict(lambda: {"nets": set(), "min_used": None, "below": 0})
        for s in widths:
            c = cls(s.net)
            d = per[c]
            d["nets"].add(s.net)
            d["min_used"] = s.width if d["min_used"] is None else min(d["min_used"], s.width)
            cw = classes.get(c, classes.get("Default", {})).get("track_width")
            if cw and s.width < cw - 1e-6:
                d["below"] += 1
        tbl = {}
        for c, d in per.items():
            cw = classes.get(c, classes.get("Default", {})).get("track_width")
            tbl[c] = {"class_width": cw, "min_used": d["min_used"], "nets": len(d["nets"]), "tracks_below_class": int(d["below"])}
            if d["below"]:
                flags.append(f"net class {c}: {int(d['below'])} track piece(s) below the class width {cw} mm "
                             f"(narrowest {d['min_used']} mm)")
        out["tracks"]["net_classes"] = tbl
    else:
        out["tracks"]["net_classes"] = None
    # vias
    hist = Counter((r3(2 * v.r), v.drill, v.kind) for v in b.vias)
    out["vias"] = [{"size": s, "drill": d, "type": k, "count": n} for (s, d, k), n in sorted(hist.items())]
    # zones and planes
    zt = defaultdict(lambda: {"zones": 0, "outline_mm2": 0.0, "fill_mm2": 0.0, "pieces": 0, "islands": 0})
    for z in b.zones:
        if z.keepout:
            continue
        for L in z.layers if z.layers else [""]:
            layers = b.copper if L in ("*.Cu", "F&B.Cu") else [L]
            for LL in layers:
                d = zt[(z.net, LL)]
                d["zones"] += 1
                d["outline_mm2"] += sum(poly_area(p) for p in z.outlines if len(p) >= 3)
                polys = z.fills.get(LL, [])
                d["fill_mm2"] += sum(poly_area(p) for p, _ in polys if len(p) >= 3)
                d["pieces"] += len(polys)
                d["islands"] += sum(1 for _, isl in polys if isl)
                if not polys:
                    flags.append(f"zone {z.name or z.net or '(no net)'} on {LL} has no fill: refill before trusting copper "
                                 "areas, islands and connectivity")
    out["zones"] = [{"net": n, "layer": L, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in d.items()}}
                    for (n, L), d in sorted(zt.items())]
    out["planes"] = [{"net": n, "layer": L, "pieces": d["pieces"]} for (n, L), d in sorted(zt.items()) if d["pieces"] > 1]
    for p in out["planes"]:
        flags.append(f"plane split: {p['net']} on {p['layer']} is {p['pieces']} separate pieces of copper "
                     "(split plane or kept islands): check each piece is connected and carries what it should")
    # drills
    dr = Counter()
    for v in b.vias:
        dr[("via", v.drill)] += 1
    for p in b.pads:
        if p.drill:
            w, h = p.drill
            kind = "NPTH" if p.kind == "np_thru_hole" else ("PTH slot" if abs(w - h) > 1e-6 else "PTH")
            dr[(kind, f"{w:g}x{h:g}" if kind == "PTH slot" else w)] += 1
    out["drills"] = [{"type": k, "drill": d, "count": n} for (k, d), n in sorted(dr.items(), key=lambda x: (x[0][0], str(x[0][1])))]
    # parts
    parts = Counter()
    tht_refs = []
    for f in b.footprints:
        side = "bottom" if f.layer == "B.Cu" else "top"
        if "board_only" in f.attrs:
            parts["board_only"] += 1
            continue
        kind = "THT" if f.tht else ("SMD" if f.pads else "other")
        parts[f"{kind} {side}"] += 1
        if kind == "THT":
            tht_refs.append(f.ref)
        for a in ("dnp", "exclude_from_bom", "exclude_from_pos_files"):
            if a in f.attrs:
                parts[a] += 1
    out["parts"] = dict(sorted(parts.items()))
    out["parts"]["tht_refs"] = sorted(tht_refs)
    # dfm
    exp = b.setup.get("pad_to_mask_clearance", 0.0)
    pitch, gap = None, None
    for f in b.footprints:
        smd = [p for p in f.pads if p.kind == "smd" and p.copper and p.num != ""]
        if len(smd) < 3:
            continue
        for i in range(len(smd)):
            for j in range(i + 1, len(smd)):
                p, q = smd[i], smd[j]
                if p.num == q.num:
                    continue
                cd = math.hypot(p.cx - q.cx, p.cy - q.cy)
                if cd > 3.0:
                    continue
                if pitch is None or cd < pitch[0] - 1e-9:
                    pitch = (cd, f.ref)
                g = pad_dist(p, q)
                m = (p.mask_margin if p.mask_margin is not None else exp) + (q.mask_margin if q.mask_margin is not None else exp)
                if gap is None or g < gap[0] - 1e-9:
                    gap = (g, f.ref, g - m)
    under = []
    for f in b.footprints:
        for p in f.pads:
            if not (p.kind == "smd" and p.paste):
                continue
            side = "B" if any(l.startswith("B.") for l in p.layers) else "F"
            n = sum(1 for v in b.vias if p.contains(*v.at) and (f"{side}.Cu" in v.layers or "F.Cu" in v.layers and "B.Cu" in v.layers))
            n += sum(1 for q in f.pads if q.kind == "thru_hole" and p.contains(q.cx, q.cy))
            if n:
                under.append(f"{p.ref}.{p.num}: {n}")
    ax, ay = b.aux_origin
    neg = sum(1 for f in b.footprints if "board_only" not in f.attrs and "exclude_from_pos_files" not in f.attrs
              and (f.x - ax < -1e-6 or ay - f.y < -1e-6))
    inside = bool(outer) and (point_in_poly(ax, ay, outer) or poly_point_dist(outer, ax, ay) <= TOL)
    out["dfm"] = {"finest_pitch": {"mm": r3(pitch[0]), "ref": pitch[1]} if pitch else None,
                  "min_pad_gap": {"mm": r3(gap[0]), "ref": gap[1], "mask_dam_mm": r3(gap[2]), "mask_expansion": exp} if gap else None,
                  "paste_over_holes": under,
                  "aux_origin": {"x": ax, "y": ay, "inside_outline": inside, "parts_negative_cpl": neg}}
    for u in under:
        flags.append(f"via/plated hole under a paste opening: {u} (solder wicks, voids)")
    if (ax, ay) != (0.0, 0.0) and not inside:
        flags.append(f"aux origin ({ax:g}, {ay:g}) outside the outline: place it on a board corner so gerbers, "
                     "drills and CPL share it (CPL coordinates negative for " + str(neg) + " part(s))")
    if neg and inside:
        flags.append(f"{neg} part(s) get negative CPL coordinates from the aux origin ({ax:g}, {ay:g})")
    out["flags"] = flags
    return out


def show(s):
    o = s["outline"]
    bb = o["bbox"]
    print(f"Board {s['board']}")
    if bb:
        print(f"  outline   {bb['w']} x {bb['h']} mm (x {bb['x0']}..{bb['x1']}, y {bb['y0']}..{bb['y1']}), {o['loops']} loop(s), "
              f"{'closed' if o['closed'] else 'OPEN'}, outer area {o['outer_area_mm2']} mm2, min edge arc radius "
              f"{o['min_arc_radius']}, sharp inside corners {len(o['sharp_inside_corners'])}")
    L = s["layers"]
    sc = ", ".join(f"{c['name']} {c['thickness']}" for c in L["stackup_copper"]) or "no stackup"
    print(f"  layers    {L['count']} copper ({', '.join(L['copper'])}); stackup: {sc}; finish {L['finish']}; "
          f"thickness {L['board_thickness']}")
    t = s["tracks"]
    print("  tracks    " + "; ".join(f"{k} {v['count']} / {v['length_mm']} mm" for k, v in sorted(t["per_layer"].items()))
          + f"; min width {t['min_width']} mm ({', '.join(t['min_width_nets'])})")
    if t["net_classes"]:
        for c, d in sorted(t["net_classes"].items()):
            print(f"            class {c}: width {d['class_width']}, narrowest used {d['min_used']}, {d['nets']} nets, "
                  f"{d['tracks_below_class']} below class")
    else:
        print("            (no .kicad_pro found: net classes not evaluated; --pro)")
    print("  vias      " + ", ".join(f"{v['count']} x {v['size']}/{v['drill']} {v['type']}" for v in s["vias"]))
    print("  drills    " + ", ".join(f"{d['count']} x {d['type']} {d['drill']}" for d in s["drills"]))
    print("  zones")
    for z in s["zones"]:
        print(f"            {z['net'] or '(no net)':<16}{z['layer']:<8} zones {z['zones']}, outline {z['outline_mm2']} mm2, "
              f"fill {z['fill_mm2']} mm2, pieces {z['pieces']}" + (f", islands {z['islands']}" if z["islands"] else ""))
    p = {k: v for k, v in s["parts"].items() if k != "tht_refs"}
    print("  parts     " + ", ".join(f"{k} {v}" for k, v in p.items()) + f"; THT: {' '.join(s['parts']['tht_refs']) or '-'}")
    d = s["dfm"]
    fp, mg, ao = d["finest_pitch"], d["min_pad_gap"], d["aux_origin"]
    print(f"  dfm       finest pitch {fp['mm'] if fp else '-'} mm ({fp['ref'] if fp else '-'}); min pad gap "
          f"{mg['mm'] if mg else '-'} mm ({mg['ref'] if mg else '-'}), mask dam ~{mg['mask_dam_mm'] if mg else '-'} mm at "
          f"expansion {mg['mask_expansion'] if mg else '-'}; paste over holes: {', '.join(d['paste_over_holes']) or 'none'}; "
          f"aux origin ({ao['x']:g}, {ao['y']:g}) {'inside' if ao['inside_outline'] else 'outside'} the outline, "
          f"{ao['parts_negative_cpl']} part(s) with negative CPL coordinates")
    print(f"\nFlags ({len(s['flags'])}):" + ("" if s["flags"] else " none"))
    for f in s["flags"]:
        print(f"  - {f}")

# ---------------------------------------------------------------- self-test


def fixture(planted):
    corner = ('(gr_line (start 22 15) (end 20 15) (layer "Edge.Cuts")) (gr_line (start 20 15) (end 20 17) (layer "Edge.Cuts"))'
              if planted else '(gr_arc (start 22 15) (mid 20.585786 15.585786) (end 20 17) (layer "Edge.Cuts"))')
    edge = ''.join(f'(gr_line (start {a}) (end {b}) (layer "Edge.Cuts"))' for a, b in
                   (("0 0", "40 0"), ("40 0", "40 15"), ("40 15", "22 15"), ("20 17", "20 30"), ("20 30", "0 30"), ("0 30", "0 0")))
    w = "0.2" if planted else "0.3"
    gnd_fill = ('(filled_polygon (layer "B.Cu") (pts (xy 1 1) (xy 10 1) (xy 10 29) (xy 1 29)))'
                '(filled_polygon (layer "B.Cu") (pts (xy 12 1) (xy 39 1) (xy 39 14) (xy 12 14)))' if planted else
                '(filled_polygon (layer "B.Cu") (pts (xy 1 1) (xy 39 1) (xy 39 14) (xy 19 14) (xy 19 29) (xy 1 29)))')
    f_zone = ('(zone (net_name "GND") (layer "F.Cu") (name "top-gnd") (fill (thermal_gap 0.5)) '
              '(polygon (pts (xy 25 2) (xy 35 2) (xy 35 12) (xy 25 12))))' if planted else "")
    ep_via = '(via (at 10 10) (size 0.45) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND"))' if planted else ""
    aux = "100 100" if planted else "0 30"
    return f"""(kicad_pcb (version 20251001)
 (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
 (setup (stackup (layer "F.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 1" (type "core") (thickness 1.51))
  (layer "B.Cu" (type "copper") (thickness 0.035)) (copper_finish "HAL lead-free")) (pad_to_mask_clearance 0.05)
  (aux_axis_origin {aux}))
 {edge} {corner}
 (footprint "lib:QFN" (layer "F.Cu") (at 10 10)
  (property "Reference" "U1") (property "Value" "MCU") (attr smd)
  (pad "1" smd rect (at -0.75 -1.5) (size 0.25 0.8) (layers "F.Cu" "F.Mask" "F.Paste") (net "/VDD"))
  (pad "2" smd rect (at -0.25 -1.5) (size 0.25 0.8) (layers "F.Cu" "F.Mask" "F.Paste") (net "/A"))
  (pad "3" smd rect (at 0.25 -1.5) (size 0.25 0.8) (layers "F.Cu" "F.Mask" "F.Paste") (net "/B"))
  (pad "4" smd rect (at 0.75 -1.5) (size 0.25 0.8) (layers "F.Cu" "F.Mask" "F.Paste") (net "GND"))
  (pad "5" smd rect (at 0 0) (size 1.6 1.6) (layers "F.Cu" "F.Mask" "F.Paste") (net "GND")))
 (footprint "lib:C_0402" (layer "F.Cu") (at 14 8.5) (property "Reference" "C1") (property "Value" "100n") (attr smd)
  (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Mask" "F.Paste") (net "/VDD"))
  (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Mask" "F.Paste") (net "GND")))
 (footprint "lib:R_0603" (layer "B.Cu") (at 30 8) (property "Reference" "R1") (property "Value" "1k") (attr smd dnp)
  (pad "1" smd rect (at -0.8 0) (size 0.8 0.9) (layers "B.Cu" "B.Mask" "B.Paste") (net "/A"))
  (pad "2" smd rect (at 0.8 0) (size 0.8 0.9) (layers "B.Cu" "B.Mask" "B.Paste") (net "/B")))
 (footprint "lib:Conn" (layer "F.Cu") (at 5 25) (property "Reference" "J1") (property "Value" "CONN") (attr through_hole)
  (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (net "/VDD"))
  (pad "2" thru_hole oval (at 2.54 0) (size 1.7 2.4) (drill oval 1.0 1.6) (layers "*.Cu" "*.Mask") (net "GND")))
 (footprint "lib:Hole" (layer "F.Cu") (at 35 25) (property "Reference" "H1") (property "Value" "M3") (attr board_only exclude_from_bom)
  (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask")))
 (segment (start 9.25 8.5) (end 13.5 8.5) (width {w}) (layer "F.Cu") (net "/VDD"))
 (segment (start 5 25) (end 5 12) (width 0.3) (layer "F.Cu") (net "/VDD"))
 (segment (start 5 12) (end 9.25 8.5) (width 0.3) (layer "F.Cu") (net "/VDD"))
 (segment (start 9.75 8.5) (end 9.75 5) (width 0.15) (layer "F.Cu") (net "/A"))
 (via (at 9.75 5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/A"))
 (via (at 15 8.5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND"))
 (via (at 11.5 10) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND"))
 {ep_via}
 (zone (net_name "GND") (layer "B.Cu") (name "bottom-gnd") (fill yes)
  (polygon (pts (xy 1 1) (xy 39 1) (xy 39 14) (xy 19 14) (xy 19 29) (xy 1 29))) {gnd_fill})
 {f_zone}
)
"""


PRO = {"net_settings": {"classes": [{"name": "Default", "track_width": 0.15, "clearance": 0.15},
                                    {"name": "PWR", "track_width": 0.3, "clearance": 0.2}],
                        "netclass_assignments": None, "netclass_patterns": [{"netclass": "PWR", "pattern": "/VDD"}]}}


def self_test():
    d = tempfile.mkdtemp()
    res = {}
    for name, planted in (("clean", False), ("planted", True)):
        p = os.path.join(d, f"{name}.kicad_pcb")
        open(p, "w", encoding="utf-8").write(fixture(planted))
        json.dump(PRO, open(os.path.join(d, f"{name}.kicad_pro"), "w"))
        res[name] = stats(p)
    c = res["clean"]
    assert c["flags"] == [], c["flags"]
    assert c["outline"]["bbox"]["w"] == 40 and c["outline"]["bbox"]["h"] == 30 and c["outline"]["closed"], c["outline"]
    assert c["outline"]["min_arc_radius"] == 2.0 and not c["outline"]["sharp_inside_corners"], c["outline"]
    assert c["layers"]["count"] == 2 and c["layers"]["finish"] == "HAL lead-free", c["layers"]
    assert c["tracks"]["min_width"] == 0.15 and c["tracks"]["net_classes"]["PWR"]["tracks_below_class"] == 0, c["tracks"]
    assert {(v["size"], v["drill"]): v["count"] for v in c["vias"]} == {(0.6, 0.3): 3}, c["vias"]
    drills = {(x["type"], str(x["drill"])): x["count"] for x in c["drills"]}
    assert drills == {("via", "0.3"): 3, ("PTH", "1.0"): 1, ("PTH slot", "1x1.6"): 1, ("NPTH", "3.2"): 1}, drills
    assert c["parts"]["SMD top"] == 2 and c["parts"]["SMD bottom"] == 1 and c["parts"]["THT top"] == 1 \
        and c["parts"]["board_only"] == 1 and c["parts"]["dnp"] == 1, c["parts"]
    assert c["dfm"]["finest_pitch"] == {"mm": 0.5, "ref": "U1"} and c["dfm"]["min_pad_gap"]["mask_dam_mm"] == 0.15, c["dfm"]
    assert c["dfm"]["aux_origin"]["inside_outline"] and c["dfm"]["aux_origin"]["parts_negative_cpl"] == 0, c["dfm"]
    pl = " | ".join(res["planted"]["flags"])
    for want in ("sharp inside corner at (20.0, 15.0)", "has no fill", "plane split: GND on B.Cu is 2", "class PWR: 1 track",
                 "outside the outline", "CPL coordinates negative for 4", "under a paste opening: U1.5"):
        assert want in pl, (want, pl)
    shutil.rmtree(d, ignore_errors=True)
    print("self-test OK: clean board (L outline with a radiused inside corner, 2 copper layers, classes from the "
          ".kicad_pro) raises no flag; planted board flags the sharp inside corner, an unfilled zone, a split plane, "
          "a track below its class width, the aux origin outside the outline with negative CPL coordinates, "
          "and a via under the exposed pad's paste")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    skip = {argv.index("--pro") + 1} if "--pro" in argv else set()
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and i not in skip]
    if not pos:
        print(__doc__)
        return 2
    s = stats(pos[0], argv[argv.index("--pro") + 1] if "--pro" in argv else None)
    if "--json" in argv:
        print(json.dumps(s, indent=1))
    else:
        show(s)
    return 1 if ("--strict" in argv and s["flags"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

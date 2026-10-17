#!/usr/bin/env python3
"""Footprint silkscreen per the pcb-design skill convention (pin-1 triangle beyond the outer end of
pad 1, outline only on pad-free sides, polarity marks at the outer pad end, reference on F.Fab), for
every footprint in the project library, then the same graphics into the placed footprints of the board.
Used on two boards before being promoted into the skill.

  python3 scripts/fp_silk.py lib   [--lib lib/<name>.pretty]        rewrite F.SilkS (+ F.Fab ref size)
  python3 scripts/fp_silk.py board <pcb> [--lib ...]                 copy lib F.SilkS/F.Fab into the board
  python3 scripts/fp_silk.py check [--lib ...] [--self-test]         lint silk-to-pad clearance

Kinds: inferred from the footprint (twopin / polar2 / ic / conn / conn-nodot / keep) and overridden by
lib/silk-kinds.json ({"<footprint>": "<kind>", ...}); "keep" leaves KiCad's drawing untouched. Footprints
not matched by any rule are kept and listed, so nothing is rewritten silently.

Convention (skill SKILL.md "Footprint silkscreen convention"):
- pin-1 marker on the axis of pad 1, beyond its outer end (away from the body centre), >= 0.2 mm from
  copper, never on a pad or under the body. v1.1.1: a filled TRIANGLE pointing at pad 1
  (KiCad's 0.48 x 0.33 mm arrow, tip 0.26 mm from the pad), not the 0.2.3 dot - the arrow reads better;
- body outline on silk only along the sides that carry no pads, 0.15 mm, >= 0.2 mm from pads;
- connectors (pads inside the body) keep the body rectangle; the arrow sits beyond the end of the row;
- reference text and secondary pin-1 cues on F.Fab, sized to fit inside the body.
Unpolarised two-pin parts get no marker (R, C, L, bidirectional TVS, buzzers, jumpers). Kept as drawn
(documented in design notes): battery holder (+/- at the terminals), test points, mounting holes,
standoffs, net ties.

Pitfalls: footprint graphics in a .kicad_pcb are stored in local, unrotated coordinates, so the lib
items can be copied verbatim (new UUIDs). Board-level texts (gr_text) are not touched.
"""
import glob
import math
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from sexpr import Sym, dump, find, first, parse  # noqa: E402

ROOT = os.getcwd()
LIB = None                              # set by --lib or discovered under <cwd>/lib/*.pretty
KINDS_OVERRIDE = {}
W, CLR = 0.15, 0.2                       # silk width, silk-to-copper clearance
W_MARK = 0.16                            # polarity marks (cathode bar, anode "+"): own width so the board
                                         # silk clean-up (route_pcb.py silkclean) can protect them
PLUS = 0.8                               # anode "+" size
TRI_L, TRI_W, TRI_S = 0.33, 0.48, 0.12    # pin-1 arrow: length, base width, stroke (KiCad stock size)
TRI_GAP = CLR + TRI_S / 2                 # tip to copper
GAP = CLR + W / 2                         # line centre to copper

POLAR_PREFIX = ("D_", "LED_", "CP_", "C_Polarized", "Battery")
KEEP_PREFIX = ("TestPoint", "MountingHole", "Fiducial", "NetTie", "Standoff", "SolderJumper", "Jumper",
               "CP_Elec", "SW_Push_1P1T_XKB")   # KiCad's own drawing is right for these


def infer_kind(name, fp):
    """Best-effort kind from the footprint name and pad layout; override in lib/silk-kinds.json."""
    if name in KINDS_OVERRIDE:
        return KINDS_OVERRIDE[name]
    if name.startswith(KEEP_PREFIX):
        return "keep"
    pads = pads_of(fp)
    tht = any(str(p[2]) == "thru_hole" for p in find(fp, "pad"))
    if len(pads) == 2:
        return "polar2" if name.startswith(POLAR_PREFIX) else "twopin"
    if len(pads) < 2:
        return "keep"
    if tht or name.startswith(("Conn", "PinHeader", "PinSocket", "TerminalBlock", "USB", "AMASS", "Hirose", "JST", "Molex")):
        return "conn"
    return "ic"


GRAPHICS = ("fp_line", "fp_rect", "fp_circle", "fp_poly", "fp_arc", "fp_text")
# Per-instance exceptions (board mode), from lib/silk-kinds.json key "drop": {"C15": "+y"} removes C15's
# local +y outline line where two parts share one line (documented lib_footprint_mismatch).
DROP = {}


def num(x):
    return float(x)


def layer_of(it):
    l = first(it, "layer")
    return str(l[1]) if l else ""


def pads_of(fp):
    out = []
    for p in find(fp, "pad"):
        if str(p[1]).strip('"') == "" or str(p[2]) == "np_thru_hole":
            continue
        at, sz = first(p, "at"), first(p, "size")
        x, y = num(at[1]), num(at[2])
        rot = num(at[3]) if len(at) > 3 else 0.0
        w, h = num(sz[1]), num(sz[2])
        prim = first(p, "primitives")
        if prim:                       # custom pad: extent from its polygon primitives (pad-local frame)
            q = [(num(v[1]), num(v[2])) for g in find(prim, "gr_poly") for v in find(first(g, "pts"), "xy")]
            if q:
                qx, qy = [a for a, _ in q], [c for _, c in q]
                x, y = x + (max(qx) + min(qx)) / 2, y + (max(qy) + min(qy)) / 2
                w, h = max(qx) - min(qx), max(qy) - min(qy)
        if round(rot) % 180 == 90:
            w, h = h, w
        out.append({"n": str(p[1]), "x": x, "y": y, "w": w, "h": h, "shape": str(p[3])})
    return out


def body_of(fp, name):
    pts = []
    for it in fp:
        if not (isinstance(it, list) and str(it[0]) in ("fp_line", "fp_rect", "fp_poly")):
            continue
        if layer_of(it) != "F.Fab":
            continue
        if str(it[0]) == "fp_poly":
            pts += [(num(q[1]), num(q[2])) for q in find(first(it, "pts"), "xy")]
        else:
            pts += [(num(first(it, k)[1]), num(first(it, k)[2])) for k in ("start", "end")]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def side(p, b):
    cx, cy, hw, hh = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[2] - b[0]) / 2, (b[3] - b[1]) / 2
    dx, dy = (p["x"] - cx) / hw, (p["y"] - cy) / hh
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return None                      # exposed pad / centre pad
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "bottom" if dy > 0 else "top"


def uid(*key):
    """Deterministic UUID from the item's geometry, so rebuilding the library does not churn the files."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "fp_silk/" + repr(key)))


def line(x1, y1, x2, y2, w=W):
    return [Sym("fp_line"), [Sym("start"), round(x1, 4), round(y1, 4)], [Sym("end"), round(x2, 4), round(y2, 4)],
            [Sym("stroke"), [Sym("width"), w], [Sym("type"), Sym("solid")]], [Sym("layer"), "F.SilkS"],
            [Sym("uuid"), uid("line", round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4), w)]]


def rect(x1, y1, x2, y2):
    return [Sym("fp_rect"), [Sym("start"), round(x1, 4), round(y1, 4)], [Sym("end"), round(x2, 4), round(y2, 4)],
            [Sym("stroke"), [Sym("width"), W], [Sym("type"), Sym("solid")]], [Sym("fill"), Sym("no")],
            [Sym("layer"), "F.SilkS"], [Sym("uuid"), uid("rect", round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4))]]


def arrow(tx, ty, ux, uy):
    """Filled triangle, tip at (tx, ty), pointing along -u (u = outward direction away from the pad)."""
    bx, by = tx + ux * TRI_L, ty + uy * TRI_L
    px, py = -uy * TRI_W / 2, ux * TRI_W / 2
    pts = [(tx, ty), (bx + px, by + py), (bx - px, by - py)]
    return [Sym("fp_poly"), [Sym("pts")] + [[Sym("xy"), round(x, 4), round(y, 4)] for x, y in pts],
            [Sym("stroke"), [Sym("width"), TRI_S], [Sym("type"), Sym("solid")]], [Sym("fill"), Sym("yes")],
            [Sym("layer"), "F.SilkS"], [Sym("uuid"), uid("arrow", round(tx, 4), round(ty, 4), ux, uy)]]


def silk_for(fp, name, kind):
    pads, b = pads_of(fp), body_of(fp, name)
    items = []
    if kind in ("twopin", "ic", "polar2", "ic-nodot"):
        busy = {side(p, b) for p in pads}
        top = min(b[1] - 0.11, min(p["y"] - p["h"] / 2 for p in pads) - GAP)
        bot = max(b[3] + 0.11, max(p["y"] + p["h"] / 2 for p in pads) + GAP)
        lft = min(b[0] - 0.11, min(p["x"] - p["w"] / 2 for p in pads) - GAP)
        rgt = max(b[2] + 0.11, max(p["x"] + p["w"] / 2 for p in pads) + GAP)
        if "top" not in busy:
            items.append(line(b[0], top, b[2], top))
        if "bottom" not in busy:
            items.append(line(b[0], bot, b[2], bot))
        if "left" not in busy:
            items.append(line(lft, b[1], lft, b[3]))
        if "right" not in busy:
            items.append(line(rgt, b[1], rgt, b[3]))
        if kind == "polar2":           # cathode bar beyond the outer end of pad 1, across the pad axis
            p1 = [p for p in pads if p["n"] == "1"][0]
            sd = side(p1, b)
            gm = CLR + W_MARK / 2
            if sd in ("left", "right"):
                xb = p1["x"] + (-1 if sd == "left" else 1) * (p1["w"] / 2 + gm)
                items.append(line(xb, p1["y"] - p1["h"] / 2, xb, p1["y"] + p1["h"] / 2, W_MARK))
            else:
                yb = p1["y"] + (-1 if sd == "top" else 1) * (p1["h"] / 2 + gm)
                items.append(line(p1["x"] - p1["w"] / 2, yb, p1["x"] + p1["w"] / 2, yb, W_MARK))
            p2 = [p for p in pads if p["n"] == "2"][0]
            s2 = side(p2, b)
            ux, uy = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}[s2]
            ext = p2["w"] / 2 if ux else p2["h"] / 2
            cx, cy = p2["x"] + ux * (ext + gm + PLUS / 2), p2["y"] + uy * (ext + gm + PLUS / 2)
            items.append(line(cx - PLUS / 2, cy, cx + PLUS / 2, cy, W_MARK))
            items.append(line(cx, cy - PLUS / 2, cx, cy + PLUS / 2, W_MARK))
        if kind == "ic":
            p1 = [p for p in pads if p["n"] == "1"][0]
            s = side(p1, b)
            ux, uy = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}[s]
            ext = p1["w"] / 2 if ux else p1["h"] / 2
            d = ext + TRI_GAP
            items.append(arrow(p1["x"] + ux * d, p1["y"] + uy * d, ux, uy))
    else:
        x1, y1, x2, y2 = b[0] - 0.11, b[1] - 0.11, b[2] + 0.11, b[3] + 0.11
        items.append(rect(x1, y1, x2, y2))
        if kind == "conn":
            p1 = [p for p in pads if p["n"] == "1"][0]
            cx = sum(p["x"] for p in pads) / len(pads); cy = sum(p["y"] for p in pads) / len(pads)
            vx, vy = p1["x"] - cx, p1["y"] - cy
            L = math.hypot(vx, vy); ux, uy = vx / L, vy / L
            if abs(ux) >= abs(uy):
                edge = x1 if ux < 0 else x2
                u = (-1.0 if ux < 0 else 1.0, 0.0)
                items.append(arrow(edge + u[0] * (W / 2 + 0.15 + TRI_S / 2), p1["y"], *u))
            else:
                edge = y1 if uy < 0 else y2
                u = (0.0, -1.0 if uy < 0 else 1.0)
                items.append(arrow(p1["x"], edge + u[1] * (W / 2 + 0.15 + TRI_S / 2), *u))
    return items, b


def fit_fab_ref(fp, b):
    bw, bh = b[2] - b[0], b[3] - b[1]
    h = max(0.25, min(1.0, bw / 3.3, bh * 0.6))
    for it in find(fp, "fp_text"):
        if str(it[1]) == "user" and str(it[2]) == "${REFERENCE}" and layer_of(it) == "F.Fab":
            at = first(it, "at")
            at[1], at[2] = round((b[0] + b[2]) / 2, 4), round((b[1] + b[3]) / 2, 4)
            fnt = first(first(it, "effects"), "font")
            sz, th = first(fnt, "size"), first(fnt, "thickness")
            sz[1], sz[2] = round(h, 3), round(h, 3)
            if th:
                th[1] = round(h * 0.15, 3)
            else:
                fnt.append([Sym("thickness"), round(h * 0.15, 3)])


def do_lib():
    for f in sorted(glob.glob(os.path.join(LIB, "*.kicad_mod"))):
        name = os.path.basename(f)[:-10]
        fp = parse(open(f).read())
        kind = infer_kind(name, fp)
        if kind == "keep":
            print(f"kept     {name}")
            continue
        new, b = silk_for(fp, name, kind)
        fp[:] = [it for it in fp if not (isinstance(it, list) and str(it[0]) in GRAPHICS[:-1]
                                         and layer_of(it) == "F.SilkS")]
        fit_fab_ref(fp, b)
        k = max(i for i, it in enumerate(fp) if isinstance(it, list) and str(it[0]) in GRAPHICS) + 1
        fp[k:k] = new
        open(f, "w").write(dump(fp) + "\n")
        print(f"silk     {name}: {kind}, {len(new)} items")


def block_end(s, i):
    depth, j, inq = 0, i, False
    while True:
        c = s[j]
        if inq:
            if c == "\\":
                j += 1
            elif c == '"':
                inq = False
        elif c == '"':
            inq = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1


def do_board(pcb):
    s = open(pcb).read()
    libs = {}
    libname = os.path.basename(LIB)[:-7]
    for f in glob.glob(os.path.join(LIB, "*.kicad_mod")):
        name = os.path.basename(f)[:-10]
        fp = parse(open(f).read())
        if infer_kind(name, fp) == "keep":
            continue
        libs[name] = [it for it in fp if isinstance(it, list) and str(it[0]) in GRAPHICS
                      and layer_of(it) in ("F.SilkS", "F.Fab")]
    out, pos, n = [], 0, 0
    for m in re.finditer(r'\(footprint "' + re.escape(libname) + r':([^"]+)"', s):
        if m.start() < pos:
            continue
        name = m.group(1)
        end = block_end(s, m.start())
        blk = s[m.start():end]
        if name in libs:
            # drop the footprint's own silk/fab graphics (top-level children only)
            kids, i, keep = [], blk.index("(", 1), []
            head = blk[:i]
            while True:
                i = blk.find("(", i)
                if i < 0:
                    break
                e = block_end(blk, i)
                kids.append(blk[i:e]); i = e
            for k in kids:
                tag = k[1:k.find("\n") if "\n" in k[:40] else 40].split()[0]
                lay = re.search(r'\(layer "([^"]+)"\)', k)
                if tag in GRAPHICS and lay and lay.group(1) in ("F.SilkS", "F.Fab") and not k.startswith("(property"):
                    continue
                keep.append(k)
            ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
            for it in libs[name]:
                if ref in DROP and str(it[0]) == "fp_line" and layer_of(it) == "F.SilkS":
                    y1, y2 = num(first(it, "start")[2]), num(first(it, "end")[2])
                    if abs(y1 - y2) < 1e-6 and (y1 > 0) == (DROP[ref] == "+y"):
                        continue
                it = [x if not (isinstance(x, list) and x and x[0] == "uuid") else [Sym("uuid"), str(uuid.uuid4())] for x in it]
                keep.append(dump(it, 2))
            blk = head + "\n\t\t".join(keep) + "\n\t)"
            n += 1
        out.append(s[pos:m.start()]); out.append(blk); pos = end
    out.append(s[pos:])
    open(pcb, "w").write("".join(out))
    print(f"board: {n} footprints updated from lib")


def check(mods=None, quiet=False):
    bad = []
    for f in mods or sorted(glob.glob(os.path.join(LIB, "*.kicad_mod"))):
        name = os.path.basename(f)[:-10]
        fp = parse(open(f).read())
        if infer_kind(name, fp) == "keep":
            continue
        pads = pads_of(fp)
        for it in fp:
            if not (isinstance(it, list) and layer_of(it) == "F.SilkS" and str(it[0]) in GRAPHICS):
                continue
            segs = []
            if str(it[0]) == "fp_line":
                a, c = first(it, "start"), first(it, "end")
                segs.append(((num(a[1]), num(a[2])), (num(c[1]), num(c[2])), W / 2))
            elif str(it[0]) == "fp_rect":
                a, c = first(it, "start"), first(it, "end")
                x1, y1, x2, y2 = num(a[1]), num(a[2]), num(c[1]), num(c[2])
                segs += [((x1, y1), (x2, y1), W / 2), ((x2, y1), (x2, y2), W / 2),
                         ((x2, y2), (x1, y2), W / 2), ((x1, y2), (x1, y1), W / 2)]
            elif str(it[0]) == "fp_poly":
                q = [(num(x[1]), num(x[2])) for x in find(first(it, "pts"), "xy")]
                sw = num(first(first(it, "stroke"), "width")[1]) / 2
                segs += [(q[k], q[(k + 1) % len(q)], sw) for k in range(len(q))]
                cx_, cy_ = sum(a for a, _ in q) / len(q), sum(b for _, b in q) / len(q)
                segs.append(((cx_, cy_), (cx_, cy_), 0.0))   # filled interior
            elif str(it[0]) == "fp_circle":
                a, c = first(it, "center"), first(it, "end")
                r = math.hypot(num(c[1]) - num(a[1]), num(c[2]) - num(a[2]))
                segs.append(((num(a[1]), num(a[2])), (num(a[1]), num(a[2])), r))
            for (p, q, rad) in segs:
                for pd in pads:
                    d = seg_rect_dist(p, q, pd) - rad
                    if d < CLR - 1e-3:
                        bad.append((name, pd["n"], round(d, 3)))
    if not quiet:
        print("silk-to-pad clearance violations:", bad if bad else "none")
    return bad


def seg_rect_dist(p, q, pd):
    best = 1e9
    for k in range(21):
        t = k / 20
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        dx = max(abs(x - pd["x"]) - pd["w"] / 2, 0); dy = max(abs(y - pd["y"]) - pd["h"] / 2, 0)
        best = min(best, math.hypot(dx, dy))
    return best


SOT23 = """(footprint "SOT-23" (version 20241229) (generator "t") (layer "F.Cu")
 (property "Reference" "REF**" (at 0 -2.5 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
 (property "Value" "SOT-23" (at 0 2.5 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
 (fp_line (start -0.7 -1.52) (end 0.7 -1.52) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
 (fp_line (start -0.7 -1.52) (end -0.7 1.52) (stroke (width 0.1) (type solid)) (layer "F.Fab"))
 (fp_line (start -0.7 1.52) (end 0.7 1.52) (stroke (width 0.1) (type solid)) (layer "F.Fab"))
 (fp_line (start 0.7 1.52) (end 0.7 -1.52) (stroke (width 0.1) (type solid)) (layer "F.Fab"))
 (fp_line (start 0.7 -1.52) (end -0.7 -1.52) (stroke (width 0.1) (type solid)) (layer "F.Fab"))
 (fp_text user "${REFERENCE}" (at 0 0 0) (layer "F.Fab") (effects (font (size 0.5 0.5) (thickness 0.075))))
 (pad "1" smd roundrect (at -1 -0.95) (size 0.9 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25))
 (pad "2" smd roundrect (at -1 0.95) (size 0.9 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25))
 (pad "3" smd roundrect (at 1 0) (size 0.9 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25))
)
"""


def self_test():
    import shutil, tempfile
    global LIB
    t = tempfile.mkdtemp(); LIB = os.path.join(t, "t.pretty"); os.makedirs(LIB)
    src = os.path.join(LIB, "SOT-23.kicad_mod"); open(src, "w").write(SOT23)
    # positive path: rewrite per convention, then the check must be clean
    do_lib()
    fp = parse(open(src).read())
    assert infer_kind("SOT-23", fp) == "ic"
    polys = [it for it in fp if isinstance(it, list) and str(it[0]) == "fp_poly" and layer_of(it) == "F.SilkS"]
    assert len(polys) == 1, "pin-1 triangle missing"
    tip = min(((num(q[1]), num(q[2])) for q in find(first(polys[0], "pts"), "xy")), key=lambda p: -p[0])
    assert tip[0] < -1.45 and abs(tip[1] + 0.95) < 1e-6, f"triangle tip not on pad-1 axis beyond its outer end: {tip}"
    lines = [it for it in fp if isinstance(it, list) and str(it[0]) == "fp_line" and layer_of(it) == "F.SilkS"]
    assert len(lines) == 2, f"expected two outline lines (pad-free sides), got {len(lines)}"
    assert not check([src], quiet=True), "clean footprint reported violations"
    # negative control: plant an arrow on pad 1 -> must be detected
    dst = os.path.join(t, "bad.kicad_mod"); p1 = [p for p in pads_of(fp) if p["n"] == "1"][0]
    fp.append(arrow(p1["x"], p1["y"], -1.0, 0.0)); open(dst, "w").write(dump(fp))
    assert check([dst], quiet=True), "negative control not detected"
    shutil.rmtree(t)
    print("self-test OK: SOT-23 rewritten (triangle at pad 1 beyond the outer end, 2 outline lines, clean check); planted arrow on pad 1 detected")


def discover_lib():
    libs = glob.glob(os.path.join(ROOT, "lib", "*.pretty"))
    if len(libs) != 1:
        sys.exit(f"pass --lib: found {libs} under {ROOT}/lib")
    return libs[0]


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--self-test" in args:
        self_test(); sys.exit(0)
    if not args:
        print(__doc__); sys.exit(2)
    cmd = args[0]
    LIB = args[args.index("--lib") + 1] if "--lib" in args else discover_lib()
    kj = os.path.join(os.path.dirname(LIB), "silk-kinds.json")
    if os.path.exists(kj):
        import json
        d = json.load(open(kj)); DROP.update(d.pop("drop", {})); KINDS_OVERRIDE.update(d)
    if cmd == "lib":
        do_lib()
    elif cmd == "board":
        do_board(args[1])
    elif cmd == "check":
        sys.exit(1 if check() else 0)
    else:
        print(__doc__); sys.exit(2)

#!/usr/bin/env python3
"""Fab-file alignment check on the files that get ordered: gerbers and Excellon drills.

DRC checks the board, not the export: drills written with a different origin than the gerbers, a
missing layer or a cropped outline pass every DRC. This reads the files themselves (Tier A).

Usage:
  check_fab_files.py <gerber-dir | gerbers.zip> [--board <board.kicad_pcb>] [--size WxH]
        [--tol 0.05] [--size-tol 0.1] [--json]
  check_fab_files.py --self-test | --write-fixtures DIR

Checks (exit 1 on any failure):
  F1  every plated drill has a flash centred on it within --tol on both outer copper layers (a
      region whose bounding-box centre is within --tol counts too: KiCad plots some custom pads as
      G36 regions); blind drill files need only the outer layer they reach. A miss names what is
      there instead: copper off-centre, or none. When most misses share one offset, the offset is
      printed: drills and gerbers were written with different origins.
  F2  every hole (PTH and NPTH, radius included) lies inside the outline's bounding box
  F3  outline bbox equals --size (W x H) and/or the board's Edge.Cuts bbox within --size-tol
  F4  with --board: finished-hole table (count per diameter: round PTH, slots, NPTH) equals the
      board's; every board hole has a drill at its position and every drill a board hole (frames
      matched on the outline bbox)
  F5  top and bottom copper, outline and at least one drill file present
Reads RS-274X (FS/MO, C/R/O/P apertures, aperture macros by name, D01/D02/D03, G36/G37 regions,
G01/G02/G03 with G75, X2 attributes as %TF...% or G04 #@! comments) and Excellon (METRIC/INCH,
decimal or LZ/TZ integers, tools from the header, G85 and routed M15/M16 slots, PTH/NPTH from the
file attribute or the file name). Copper layer and drill type come from the X2 file function, else
from KiCad/Protel file names (-F_Cu, .gtl, -B_Cu, .gbl, Edge_Cuts, .gm1/.gko, -PTH, -NPTH).
Pitfalls: a hole on the board edge (castellation) fails F2 by design, list it as justified;
F4 compares finished-hole diameters as written in the drill file (KiCad writes the board values);
a custom pad whose shape is not centred on its hole, or a via/pad whose unconnected outer ring was
removed (remove_unused_layers without keep_end_layers), shows as an F1 miss: read each one.
"""
import json
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict

# ---------------------------------------------------------------- Gerber


class Gerber:
    def __init__(self, name, text):
        self.name, self.func = name, None
        self.flashes, self.regions, self.draws = [], [], []   # flashes (x, y, aperture), regions [pts], draws [pts]
        self.apertures = {}
        self._parse(text)

    def _num(self, s, axis):
        neg = s.startswith("-")
        s = s.lstrip("+-")
        if self.zero == "T":
            s = s.ljust(self.ints + self.decs, "0")
        v = int(s) / 10 ** self.decs if s else 0.0
        v = -v if neg else v
        return v * (25.4 if self.inch else 1.0)

    def _parse(self, text):
        self.zero, self.ints, self.decs, self.inch = "L", 4, 6, False
        x = y = 0.0
        mode, region, contour, ap, last_op = 1, False, [], None, None
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c == "%":
                j = text.find("%", i + 1)
                if j < 0:
                    break
                self._extended(text[i + 1:j])
                i = j + 1
                continue
            if c.isspace():
                i += 1
                continue
            j = text.find("*", i)
            if j < 0:
                break
            word = text[i:j].strip()
            i = j + 1
            if word.startswith("G04"):
                m = re.search(r"TF\.FileFunction,([^*]*)", word)
                if m and not self.func:
                    self.func = m.group(1)
                continue
            toks = re.findall(r"([GXYIJDM])([+-]?\d+)", word)
            coords, op = {}, None
            for k, v in toks:
                if k == "G":
                    g = int(v)
                    if g in (1, 2, 3):
                        mode = g
                    elif g == 36:
                        region, contour = True, []
                    elif g == 37:
                        if len(contour) >= 3:
                            self.regions.append(contour)
                        region, contour = False, []
                elif k == "D":
                    d = int(v)
                    if d >= 10:
                        ap = d
                    else:
                        op = d
                elif k in "XYIJ":
                    coords[k] = v
                elif k == "M" and int(v) == 2:
                    i = n
            if op is None and ("X" in coords or "Y" in coords):
                op = last_op
            if op is None:
                continue
            last_op = op
            nx = self._num(coords["X"], "X") if "X" in coords else x
            ny = self._num(coords["Y"], "Y") if "Y" in coords else y
            if op == 3 and not region:
                self.flashes.append((nx, ny, ap))
            elif op == 2:
                if region and len(contour) >= 3:
                    self.regions.append(contour)
                contour = [(nx, ny)] if region else []
                if not region:
                    self.draws.append([(nx, ny)])
            elif op == 1:
                if mode == 1:
                    pts = [(nx, ny)]
                else:
                    ci = self._num(coords.get("I", "0"), "X")
                    cj = self._num(coords.get("J", "0"), "Y")
                    pts = arc_pts((x, y), (nx, ny), (x + ci, y + cj), mode == 2)
                if region:
                    if not contour:
                        contour = [(x, y)]
                    contour += pts
                else:
                    if not self.draws or self.draws[-1][-1] != (x, y):
                        self.draws.append([(x, y)])
                    self.draws[-1] += pts
            x, y = nx, ny

    def _extended(self, block):
        stmts = [s.strip() for s in block.split("*") if s.strip()]
        if not stmts:
            return
        s = stmts[0]
        if s.startswith("FS"):
            m = re.match(r"FS([LT])([AI])X(\d)(\d)Y(\d)(\d)", s)
            if m:
                self.zero, self.ints, self.decs = m.group(1), int(m.group(3)), int(m.group(4))
        elif s.startswith("MO"):
            self.inch = s[2:4] == "IN"
        elif s.startswith("AD"):
            m = re.match(r"ADD(\d+)([A-Za-z_.$][\w.$]*)(?:,(.*))?", s)
            if m:
                params = [p for p in (m.group(3) or "").split("X") if p]
                self.apertures[int(m.group(1))] = (m.group(2), params)
        elif s.startswith("TF.FileFunction,") and not self.func:
            self.func = s[len("TF.FileFunction,"):]

    def flash_radius(self, ap):
        """Radius of the circle a standard aperture covers for sure (0 for macros)."""
        t, p = self.apertures.get(ap, ("", []))
        try:
            v = [float(q) * (25.4 if self.inch else 1.0) for q in p]
        except ValueError:
            return 0.0
        if t == "C" and v:
            return v[0] / 2
        if t in ("R", "O") and len(v) >= 2:
            return min(v[0], v[1]) / 2
        if t == "P" and v:
            return v[0] / 2 * math.cos(math.pi / max(3, int(v[1]) if len(v) > 1 else 3))
        return 0.0


def arc_pts(a, b, c, cw):
    r = math.dist(a, c)
    a0 = math.atan2(a[1] - c[1], a[0] - c[0])
    a1 = math.atan2(b[1] - c[1], b[0] - c[0])
    if cw:
        sw = -((a0 - a1) % (2 * math.pi)) or -2 * math.pi
    else:
        sw = ((a1 - a0) % (2 * math.pi)) or 2 * math.pi
    n = max(8, int(abs(sw) / (math.pi / 32)))
    return [(c[0] + r * math.cos(a0 + sw * k / n), c[1] + r * math.sin(a0 + sw * k / n)) for k in range(1, n + 1)]

# ---------------------------------------------------------------- Excellon


class Drill:
    def __init__(self, name, text):
        self.name, self.func, self.holes = name, None, []   # holes: dict x, y, d, plated, end, tool
        self.span = None
        self._parse(text)

    def _num(self, s):
        if "." in s:
            v = float(s)
        else:
            neg = s.startswith("-")
            s = s.lstrip("+-")
            if self.zeros == "LZ":
                s = s.ljust(self.ints + self.decs, "0")
            v = int(s) / 10 ** self.decs if s else 0.0
            v = -v if neg else v
        return v * (25.4 if self.inch else 1.0)

    def _parse(self, text):
        self.inch, self.zeros, self.ints, self.decs = False, "TZ", 3, 3
        tools, tool_plated, pending_attr, fmt_seen = {}, {}, None, False
        header, cur, x, y, down, start = True, None, 0.0, 0.0, False, None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith(";"):
                m = re.search(r"TF\.FileFunction,([^\s*]*)", line)
                if m:
                    self.func = m.group(1)
                m = re.search(r"TA\.AperFunction,(\w+)", line)
                if m:
                    pending_attr = m.group(1)
                m = re.search(r"FORMAT=\{(\d):(\d)", line)
                if m:
                    self.ints, self.decs, fmt_seen = int(m.group(1)), int(m.group(2)), True
                continue
            up = line.upper()
            if up.startswith(("METRIC", "INCH")):
                self.inch = up.startswith("INCH")
                if "LZ" in up:
                    self.zeros = "LZ"
                if not fmt_seen:
                    self.ints, self.decs = (2, 4) if self.inch else (3, 3)
                continue
            if up in ("%", "M95"):
                header = False
                continue
            m = re.match(r"T(\d+)C([\d.]+)", up)
            if m:
                tools[int(m.group(1))] = float(m.group(2)) * (25.4 if self.inch else 1.0)
                if pending_attr:
                    tool_plated[int(m.group(1))] = pending_attr.lower() != "nonplated"
                pending_attr = None
                continue
            m = re.match(r"T(\d+)$", up)
            if m:
                cur = int(m.group(1))
                continue
            if up == "M15":
                down, start = True, (x, y)
                continue
            if up in ("M16", "M17"):
                down = False
                continue
            if up in ("G05", "G90", "M30", "M48", "FMAT,2", "G00") or header:
                continue
            m = re.match(r"(G0[01])?(?:X([+-]?[\d.]+))?(?:Y([+-]?[\d.]+))?(G85)?(?:X([+-]?[\d.]+))?(?:Y([+-]?[\d.]+))?$", up)
            if not m or cur is None or (m.group(2) is None and m.group(3) is None):
                continue
            nx = self._num(m.group(2)) if m.group(2) else x
            ny = self._num(m.group(3)) if m.group(3) else y
            d = tools.get(cur, 0.0)
            plated = tool_plated.get(cur)
            if m.group(4):          # G85 slot in one line
                ex = self._num(m.group(5)) if m.group(5) else nx
                ey = self._num(m.group(6)) if m.group(6) else ny
                self.holes.append({"x": nx, "y": ny, "d": d, "plated": plated, "end": (ex, ey), "tool": cur})
                x, y = ex, ey
                continue
            if m.group(1) == "G01" and down:
                self.holes.append({"x": start[0], "y": start[1], "d": d, "plated": plated, "end": (nx, ny), "tool": cur})
            elif m.group(1) != "G00" and not down:
                self.holes.append({"x": nx, "y": ny, "d": d, "plated": plated, "end": None, "tool": cur})
            x, y = nx, ny
        f = (self.func or "").lower()
        fname = os.path.basename(self.name).lower()
        default = not ("nonplated" in f or "npth" in f or (not f and "npth" in fname))
        for h in self.holes:
            if h["plated"] is None:
                h["plated"] = default
        m = re.match(r"(?:non)?plated,(\d+),(\d+)", f)
        self.span = (int(m.group(1)), int(m.group(2))) if m else None


def centre(h):
    if h["end"]:
        return ((h["x"] + h["end"][0]) / 2, (h["y"] + h["end"][1]) / 2)
    return (h["x"], h["y"])

# ---------------------------------------------------------------- files


def classify(name, text):
    low = os.path.basename(name).lower()
    head = text[:4000]
    if low.endswith((".gbrjob", ".json", ".pdf", ".csv", ".txt", ".md", ".step", ".stp", ".zip", ".png", ".rpt")):
        return None
    if re.search(r"^\s*M48", head, re.M) or low.endswith((".drl", ".xln", ".exc")):
        return "drill"
    if "%FS" in head or "%MO" in head:
        return "gerber"
    return None


def read_dir(src):
    files = {}
    if os.path.isfile(src) and zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                if not n.endswith("/") and "__MACOSX" not in n:
                    files[n] = z.read(n).decode("utf-8", "replace")
    else:
        for root, _, names in os.walk(src):
            for n in names:
                p = os.path.join(root, n)
                if zipfile.is_zipfile(p):
                    files.update({f"{n}/{k}": v for k, v in read_dir(p).items()})
                    continue
                try:
                    files[os.path.relpath(p, src)] = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    pass
    return files


def layer_role(g):
    f = (g.func or "").lower()
    low = os.path.basename(g.name).lower()
    if f.startswith("copper"):
        m = re.match(r"copper,l(\d+),(top|inr|bot)", f)
        if m:
            return {"top": "top", "bot": "bottom", "inr": "inner"}[m.group(2)], int(m.group(1))
    if f.startswith("profile"):
        return "outline", None
    if f and not f.startswith("copper"):
        return "other", None
    if re.search(r"(f_cu|\.gtl$)", low):
        return "top", 1
    if re.search(r"(b_cu|\.gbl$)", low):
        return "bottom", None
    if re.search(r"(in\d+_cu|\.g\d+$)", low):
        return "inner", None
    if re.search(r"(edge_cuts|\.gm1$|\.gko$|outline)", low):
        return "outline", None
    return "other", None

# ---------------------------------------------------------------- checks


class Grid:
    def __init__(self, pts, cell=0.5):
        self.cell, self.g = cell, defaultdict(list)
        for p in pts:
            self.g[(int(p[0] // cell), int(p[1] // cell))].append(p)

    def near(self, x, y, r):
        k = int(math.ceil(r / self.cell))
        cx, cy = int(x // self.cell), int(y // self.cell)
        for i in range(cx - k, cx + k + 1):
            for j in range(cy - k, cy + k + 1):
                yield from self.g.get((i, j), ())


def copper_at(g, grid, x, y, tol):
    """('flash'|'region', dist) when centred within tol, else ('off-centre'|'none', nearest flash distance)."""
    best = None
    for p in grid.near(x, y, max(tol, 2.0)):
        d = math.hypot(p[0] - x, p[1] - y)
        if best is None or d < best[0]:
            best = (d, p)
    if best and best[0] <= tol:
        return "flash", best[0]
    for r in g.regions:
        xs, ys = [p[0] for p in r], [p[1] for p in r]
        if min(xs) - tol <= x <= max(xs) + tol and min(ys) - tol <= y <= max(ys) + tol:
            if math.hypot((min(xs) + max(xs)) / 2 - x, (min(ys) + max(ys)) / 2 - y) <= tol:
                return "region", 0.0
    inside = (best and best[0] <= g.flash_radius(best[1][2])) or any(_in_poly(x, y, r) for r in g.regions)
    return ("off-centre" if inside else "none"), (round(best[0], 3) if best else None)


def _in_poly(x, y, poly):
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def board_holes(path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pcb_board import load, outline_bbox
    b = load(path)
    holes = [("via", v.drill, v.drill, v.at) for v in b.vias]
    for p in b.pads:
        if p.drill:
            w, h = p.drill
            kind = "NPTH" if p.kind == "np_thru_hole" else ("slot" if abs(w - h) > 1e-6 else "PTH")
            holes.append((kind, min(w, h), max(w, h), (p.cx, p.cy)))
    return holes, outline_bbox(b)


def check(src, board=None, size=None, tol=0.05, size_tol=0.1):
    files = read_dir(src)
    gerbers, drills, ignored = [], [], []
    for name, text in sorted(files.items()):
        kind = classify(name, text)
        if kind == "gerber":
            gerbers.append(Gerber(name, text))
        elif kind == "drill":
            drills.append(Drill(name, text))
        else:
            ignored.append(name)
    roles = defaultdict(list)
    for g in gerbers:
        roles[layer_role(g)[0]].append(g)
    ncopper = max([layer_role(g)[1] or 0 for g in gerbers if layer_role(g)[0] in ("top", "bottom", "inner")] + [0])
    ncopper = max(ncopper, len(roles["top"][:1]) + len(roles["bottom"][:1]) + len(roles["inner"]))
    res = {"src": src, "fail": [], "notes": [], "misses": [], "outside": [], "table": []}
    fail = res["fail"]
    for need in ("top", "bottom", "outline"):
        if not roles[need]:
            fail.append(f"F5 no {need} {'copper' if need != 'outline' else 'layer'} gerber found")
    if not drills:
        fail.append("F5 no drill file found")
    res["files"] = {"top": [g.name for g in roles["top"]], "bottom": [g.name for g in roles["bottom"]],
                    "inner": [g.name for g in roles["inner"]], "outline": [g.name for g in roles["outline"]],
                    "drills": [f"{d.name} ({len(d.holes)} holes)" for d in drills], "ignored": ignored}
    holes = [h for d in drills for h in d.holes]
    pth = [(h, d) for d in drills for h in d.holes if h["plated"]]
    # F1
    stats = {"pth": len(pth), "top_ok": 0, "bottom_ok": 0, "region": 0}
    sides = [("top", roles["top"][0] if roles["top"] else None), ("bottom", roles["bottom"][0] if roles["bottom"] else None)]
    grids = {s: Grid([f for f in g.flashes]) for s, g in sides if g}
    for h, d in pth:
        x, y = centre(h)
        for side, g in sides:
            if not g:
                continue
            if d.span and ((side == "top" and d.span[0] != 1) or (side == "bottom" and d.span[1] != max(ncopper, d.span[1]))):
                stats[f"{side}_ok"] += 1
                continue
            how, dist = copper_at(g, grids[side], x, y, tol)
            if how in ("flash", "region"):
                stats[f"{side}_ok"] += 1
                stats["region"] += how == "region"
            else:
                res["misses"].append({"x": round(x, 3), "y": round(y, 3), "d": h["d"], "layer": side, "found": how,
                                      "nearest_flash_mm": dist, "file": d.name})
    if res["misses"]:
        fail.append(f"F1 {len(res['misses'])} plated drill/layer pair(s) without a centred flash")
        top = roles["top"][0] if roles["top"] else None
        if top and top.flashes:
            sample = [m for m in res["misses"]][:60]
            votes = Counter()
            for m in sample:
                for f in top.flashes:
                    votes[(round(m["x"] - f[0], 2), round(m["y"] - f[1], 2))] += 1
            (dx, dy), cnt = votes.most_common(1)[0]
            if cnt >= max(3, 0.6 * len(sample)) and math.hypot(dx, dy) > tol:
                res["shift"] = {"dx": dx, "dy": dy, "votes": cnt, "of": len(sample)}
                fail.append(f"F1 systematic: {cnt} of {len(sample)} missed drills sit ({dx:+.3f}, {dy:+.3f}) mm from copper: "
                            "drills and gerbers were exported with different origins")
    res["f1"] = stats
    # F2 / F3
    bb = None
    pts = [p for g in roles["outline"] for d in g.draws for p in d]
    if pts:
        bb = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        res["outline"] = {"w": round(bb[2] - bb[0], 3), "h": round(bb[3] - bb[1], 3),
                          "x0": round(bb[0], 3), "y0": round(bb[1], 3), "x1": round(bb[2], 3), "y1": round(bb[3], 3)}
        for h in holes:
            r = h["d"] / 2
            ends = [(h["x"], h["y"])] + ([h["end"]] if h["end"] else [])
            if any(px - r < bb[0] - 1e-6 or px + r > bb[2] + 1e-6 or py - r < bb[1] - 1e-6 or py + r > bb[3] + 1e-6 for px, py in ends):
                res["outside"].append({"x": round(h["x"], 3), "y": round(h["y"], 3), "d": h["d"], "plated": h["plated"]})
        if res["outside"]:
            fail.append(f"F2 {len(res['outside'])} hole(s) not inside the outline bbox")
        if size:
            w, hh = size
            if abs(res["outline"]["w"] - w) > size_tol or abs(res["outline"]["h"] - hh) > size_tol:
                fail.append(f"F3 outline {res['outline']['w']} x {res['outline']['h']} mm, documented {w:g} x {hh:g} mm")
    # F4
    if board:
        bh, bbb = board_holes(board)
        want = Counter((k if k != "via" else "PTH", round(d1, 3), round(d2, 3) if k == "slot" else None) for k, d1, d2, _ in bh)
        got = Counter()
        for h in holes:
            if h["end"]:
                L = math.dist((h["x"], h["y"]), h["end"]) + h["d"]
                got[("slot", round(h["d"], 3), round(L, 3))] += 1
            else:
                got[("PTH" if h["plated"] else "NPTH", round(h["d"], 3), None)] += 1
        for k in sorted(set(want) | set(got), key=str):
            ok = want[k] == got[k]
            res["table"].append({"type": k[0], "drill": k[1], "length": k[2], "board": want[k], "files": got[k], "ok": ok})
        if not all(r["ok"] for r in res["table"]):
            fail.append("F4 drill table differs from the board's holes")
        if bbb:
            res["board_outline"] = {"w": round(bbb[2] - bbb[0], 3), "h": round(bbb[3] - bbb[1], 3)}
            if bb and (abs(res["board_outline"]["w"] - res["outline"]["w"]) > size_tol
                       or abs(res["board_outline"]["h"] - res["outline"]["h"]) > size_tol):
                fail.append(f"F3 outline {res['outline']['w']} x {res['outline']['h']} mm, board Edge.Cuts "
                            f"{res['board_outline']['w']} x {res['board_outline']['h']} mm")
            elif bb:
                def to_g(p):      # board (y down) -> file frame (y up), matched on the outline bbox
                    return (p[0] - bbb[0] + bb[0], bb[3] - (p[1] - bbb[1]))
                fg = Grid([centre(h) for h in holes])
                bg = Grid([to_g(p) for *_, p in bh])
                lost = [p for *_, p in bh if not any(math.dist(q, to_g(p)) <= tol for q in fg.near(*to_g(p), tol))]
                stray = [centre(h) for h in holes if not any(math.dist(q, centre(h)) <= tol for q in bg.near(*centre(h), tol))]
                res["board_lost"] = [(round(p[0], 3), round(p[1], 3)) for p in lost][:20]
                res["file_stray"] = [(round(p[0], 3), round(p[1], 3)) for p in stray][:20]
                if lost or stray:
                    fail.append(f"F4 {len(lost)} board hole(s) without a drill at their position, {len(stray)} drill(s) "
                                "without a board hole (frames matched on the outline bbox)")
    return res


def show(r):
    f = r["files"]
    print(f"Fab files: {r['src']}")
    print(f"  copper top {', '.join(f['top']) or '-'}; bottom {', '.join(f['bottom']) or '-'}; inner {len(f['inner'])}; "
          f"outline {', '.join(f['outline']) or '-'}")
    print(f"  drills {'; '.join(f['drills']) or '-'}")
    if "outline" in r:
        o = r["outline"]
        print(f"  outline bbox {o['w']} x {o['h']} mm" + (f"; board Edge.Cuts {r['board_outline']['w']} x {r['board_outline']['h']} mm"
                                                        if "board_outline" in r else ""))
    s = r["f1"]
    print(f"  F1 plated drills {s['pth']}: centred copper on top {s['top_ok']}/{s['pth']}, bottom {s['bottom_ok']}/{s['pth']}"
          + (f" ({s['region']} by region)" if s["region"] else ""))
    for m in r["misses"][:25]:
        print(f"     miss {m['layer']:<6} drill {m['d']:.3f} at ({m['x']:.3f}, {m['y']:.3f}): {m['found']}"
              + (f", nearest flash {m['nearest_flash_mm']} mm" if m["nearest_flash_mm"] is not None else ""))
    if len(r["misses"]) > 25:
        print(f"     ... {len(r['misses']) - 25} more")
    print(f"  F2 holes outside the outline bbox: {len(r['outside'])}")
    for h in r["outside"][:10]:
        print(f"     {'PTH' if h['plated'] else 'NPTH'} {h['d']:.3f} at ({h['x']:.3f}, {h['y']:.3f})")
    if r["table"]:
        print("  F4 drill table (finished holes)   type    drill   length   board   files")
        for t in r["table"]:
            print(f"     {'ok ' if t['ok'] else 'DIFF'}                          {t['type']:<7} {t['drill']:<7} "
                  f"{t['length'] if t['length'] else '-':<8} {t['board']:<7} {t['files']}")
    for k, label in (("board_lost", "board hole without drill"), ("file_stray", "drill without board hole")):
        for p in r.get(k, [])[:10]:
            print(f"     {label} at {p}")
    print("\n" + ("Result: OK" if not r["fail"] else "Result: FAIL\n" + "\n".join(f"  - {x}" for x in r["fail"])))

# ---------------------------------------------------------------- fixtures

BOARD_H = 20.0
VIAS = [(5, 5), (10, 5), (15, 5)]
THT = (5, 15)
SLOT = (7.54, 15)
REGION_PAD = (25, 15)
NPTH = (26, 4)
SMD = (20, 10)


def _c(v):
    return str(int(round(v * 1e6)))


def gerber_copper(func, frame):
    out = ["%TF.GenerationSoftware,KiCad,Pcbnew,10.0*%", f"%TF.FileFunction,{func}*%", "%FSLAX46Y46*%",
           "G04 Gerber Fmt 4.6, Leading zero omitted, Abs format (unit mm)*", "%MOMM*%", "%LPD*%", "G01*",
           "G04 Aperture macros list*", "%AMRoundRect*", "0 Rectangle with rounded corners*", "0 $1 Rounding radius*",
           "4,1,4,$2,$3,$4,$5,$6,$7,$8,$9,$2,$3,0*", "1,1,$1+$1,$2,$3*", "1,1,$1+$1,$4,$5*", "1,1,$1+$1,$6,$7*",
           "1,1,$1+$1,$8,$9*", "20,1,$1+$1,$2,$3,$4,$5,0*", "20,1,$1+$1,$4,$5,$6,$7,0*", "20,1,$1+$1,$6,$7,$8,$9,0*",
           "20,1,$1+$1,$8,$9,$2,$3,0*%", "G04 Aperture macros list end*",
           "%TA.AperFunction,ViaPad*%", "%ADD10C,0.600000*%", "%TD*%",
           "%TA.AperFunction,ComponentPad*%", "%ADD11R,1.700000X1.700000*%", "%ADD12O,1.700000X2.400000*%", "%TD*%",
           "%TA.AperFunction,SMDPad,CuDef*%",
           "%ADD13RoundRect,0.150000X-0.300000X-0.250000X0.300000X-0.250000X0.300000X0.250000X-0.300000X0.250000X0*%",
           "%TD*%"]
    for code, pts in ((10, VIAS), (11, [THT]), (12, [SLOT])) + (((13, [SMD]),) if "Top" in func else ()):
        out.append(f"D{code}*")
        for p in pts:
            x, y = frame(p)
            out.append(f"X{_c(x)}Y{_c(y)}D03*")
    cx, cy = frame(REGION_PAD)        # custom pad drawn as a region, as KiCad does without aperture macros
    out += ["G36*", f"X{_c(cx - 0.8)}Y{_c(cy - 0.8)}D02*", f"X{_c(cx + 0.8)}Y{_c(cy - 0.8)}D01*",
            f"X{_c(cx + 0.8)}Y{_c(cy + 0.8)}D01*", f"X{_c(cx - 0.8)}Y{_c(cy + 0.8)}D01*", f"X{_c(cx - 0.8)}Y{_c(cy - 0.8)}D01*", "G37*"]
    x0, y0 = frame((1, 1))            # a zone fill: contains the vias but is centred on none of them
    x1, y1 = frame((29, 9))
    out += ["G36*", f"X{_c(x0)}Y{_c(y0)}D02*", f"X{_c(x1)}Y{_c(y0)}D01*", f"X{_c(x1)}Y{_c(y1)}D01*",
            f"X{_c(x0)}Y{_c(y1)}D01*", f"X{_c(x0)}Y{_c(y0)}D01*", "G37*", "M02*"]
    return "\n".join(out) + "\n"


def gerber_outline(frame, w=30.0, h=BOARD_H, r=1.0):
    def P(x, y):
        a, b = frame((x, y))
        return f"X{_c(a)}Y{_c(b)}"

    def ij(sx, sy, cx, cy):
        a, b = frame((sx, sy))
        c, d = frame((cx, cy))
        return f"I{_c(c - a)}J{_c(d - b)}"
    out = ["%TF.FileFunction,Profile,NP*%", "%FSLAX46Y46*%", "%MOMM*%", "%ADD10C,0.100000*%", "D10*", "G75*",
           f"{P(r, 0)}D02*", "G01*", f"{P(w - r, 0)}D01*", f"G02{P(w, r)}{ij(w - r, 0, w - r, r)}D01*",
           "G01*", f"{P(w, h - r)}D01*", f"G02{P(w - r, h)}{ij(w, h - r, w - r, h - r)}D01*",
           "G01*", f"{P(r, h)}D01*", f"G02{P(0, h - r)}{ij(r, h, r, h - r)}D01*",
           "G01*", f"{P(0, r)}D01*", f"G02{P(r, 0)}{ij(0, r, r, r)}D01*", "M02*"]
    return "\n".join(out) + "\n"


def excellon(plated, frame, nudge=None):
    out = ["M48", "; DRILL file {KiCad 10.0} date 2026-10-19", "; FORMAT={-:-/ absolute / metric / decimal}",
           f"; #@! TF.FileFunction,{'Plated,1,2,PTH' if plated else 'NonPlated,1,2,NPTH'}", "FMAT,2", "METRIC"]

    def P(p):
        if nudge and p == nudge[0]:
            p = (p[0] + nudge[1][0], p[1] + nudge[1][1])
        x, y = frame(p)
        return f"X{x:.3f}Y{y:.3f}"
    if plated:
        out += ["; #@! TA.AperFunction,Plated,PTH,ViaDrill", "T1C0.300", "; #@! TA.AperFunction,Plated,PTH,ComponentDrill",
                "T2C1.000", "%", "G90", "G05", "T1"] + [P(v) for v in VIAS] + ["T2", P(THT), P(REGION_PAD),
                f"G00{P((SLOT[0], SLOT[1] - 0.3))}", "M15", f"G01{P((SLOT[0], SLOT[1] + 0.3))}", "M16", "G05"]
    else:
        out += ["; #@! TA.AperFunction,NonPlated,NPTH,ComponentDrill", "T1C3.200", "%", "G90", "G05", "T1", P(NPTH)]
    return "\n".join(out + ["M30"]) + "\n"


BOARD_FIX = f"""(kicad_pcb (version 20251001)
 (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
 (gr_rect (start 0 0) (end 30 {BOARD_H:g}) (layer "Edge.Cuts"))
 {' '.join(f'(via (at {x} {y}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND"))' for x, y in VIAS)}
 (footprint "lib:J" (layer "F.Cu") (at {THT[0]} {THT[1]}) (property "Reference" "J1")
  (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (net "A"))
  (pad "2" thru_hole oval (at 2.54 0) (size 1.7 2.4) (drill oval 1.0 1.6) (layers "*.Cu" "*.Mask") (net "B")))
 (footprint "lib:TP" (layer "F.Cu") (at {REGION_PAD[0]} {REGION_PAD[1]}) (property "Reference" "TP1")
  (pad "1" thru_hole custom (at 0 0) (size 1.6 1.6) (drill 1.0) (layers "*.Cu" "*.Mask") (net "A")))
 (footprint "lib:H" (layer "F.Cu") (at {NPTH[0]} {NPTH[1]}) (property "Reference" "H1")
  (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask")))
)
"""


def write_fixtures(d, variant="clean"):
    """clean | shifted (one via drill 0.3 mm off) | origin (drills absolute, gerbers at the aux origin) |
    outside (NPTH beyond the outline)."""
    os.makedirs(d, exist_ok=True)
    kicad = lambda p: (p[0], -p[1])                     # noqa: E731  absolute origin: y up
    aux = lambda p: (p[0], BOARD_H - p[1])              # noqa: E731  aux origin at the lower-left corner
    gframe = aux if variant == "origin" else kicad
    dframe = kicad
    files = {"board-F_Cu.gbr": gerber_copper("Copper,L1,Top", gframe), "board-B_Cu.gbr": gerber_copper("Copper,L2,Bot", gframe),
             "board-Edge_Cuts.gbr": gerber_outline(gframe),
             "board-PTH.drl": excellon(True, dframe, ((10, 5), (0.3, 0)) if variant == "shifted" else None),
             "board-NPTH.drl": excellon(False, dframe, ((26, 4), (5, 0)) if variant == "outside" else None),
             "board-job.gbrjob": '{"Header": {}}'}
    for n, t in files.items():
        open(os.path.join(d, n), "w", encoding="utf-8").write(t)
    open(os.path.join(d, "board.kicad_pcb.fixture"), "w", encoding="utf-8").write(BOARD_FIX)
    return d


def self_test():
    root = tempfile.mkdtemp()
    bp = os.path.join(root, "board.kicad_pcb")
    open(bp, "w", encoding="utf-8").write(BOARD_FIX)
    r = check(write_fixtures(os.path.join(root, "clean")), bp, (30, 20))
    assert not r["fail"], r["fail"]
    assert r["f1"] == {"pth": 6, "top_ok": 6, "bottom_ok": 6, "region": 2}, r["f1"]
    assert r["outline"]["w"] == 30 and r["outline"]["h"] == 20, r["outline"]
    assert all(t["ok"] for t in r["table"]) and len(r["table"]) == 4, r["table"]
    zp = os.path.join(root, "gerbers.zip")                  # the package as shipped: a zip
    with zipfile.ZipFile(zp, "w") as z:
        for n in os.listdir(os.path.join(root, "clean")):
            z.write(os.path.join(root, "clean", n), n)
    assert not check(zp, bp, (30, 20))["fail"]
    r = check(write_fixtures(os.path.join(root, "shifted"), "shifted"), bp)
    assert len(r["misses"]) == 2 and {m["layer"] for m in r["misses"]} == {"top", "bottom"}, r["misses"]
    assert r["misses"][0]["found"] == "off-centre" and abs(r["misses"][0]["nearest_flash_mm"] - 0.3) < 1e-6, r["misses"]
    assert any(x.startswith("F4") for x in r["fail"]) and "shift" not in r, r["fail"]
    r = check(write_fixtures(os.path.join(root, "origin"), "origin"), bp)
    assert r["f1"]["top_ok"] == 0 and r.get("shift", {}).get("dy") == -20.0, (r["f1"], r.get("shift"))
    r = check(write_fixtures(os.path.join(root, "outside"), "outside"), None, (30, 21))
    assert len(r["outside"]) == 1 and any(x.startswith("F3") for x in r["fail"]), r
    shutil.rmtree(root, ignore_errors=True)
    print("self-test OK: clean set passes (flashes, RoundRect macro, region-drawn pad, routed slot, zip input, drill "
          "table and positions vs the board); one via drill 0.3 mm off is caught on both layers; drills exported "
          "with the absolute origin against gerbers at the aux origin are caught with the 20 mm shift named; an "
          "NPTH beyond the outline and a wrong documented size fail")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    if "--write-fixtures" in argv:
        d = argv[argv.index("--write-fixtures") + 1]
        for v in ("clean", "shifted", "origin", "outside"):
            print(write_fixtures(os.path.join(d, v), v))
        print(f"board for --board: {os.path.join(d, 'clean', 'board.kicad_pcb.fixture')}")
        return 0
    opts = {"--board": None, "--size": None, "--tol": "0.05", "--size-tol": "0.1"}
    pos, i = [], 0
    while i < len(argv):
        if argv[i] in opts and i + 1 < len(argv):
            opts[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            pos.append(argv[i])
            i += 1
    if not pos:
        print(__doc__)
        return 2
    size = None
    if opts["--size"]:
        m = re.match(r"([\d.]+)\s*[xX*]\s*([\d.]+)", opts["--size"])
        size = (float(m.group(1)), float(m.group(2))) if m else None
    r = check(pos[0], opts["--board"], size, float(opts["--tol"]), float(opts["--size-tol"]))
    if "--json" in argv:
        print(json.dumps(r, indent=1, default=str))
    else:
        show(r)
    return 1 if r["fail"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

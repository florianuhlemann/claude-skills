#!/usr/bin/env python3
"""Shared .kicad_pcb reader and copper walker for the pcb-audit scripts. Pure text, no pcbnew; KiCad 7-10.

  from pcb_board import load
  b = load("hardware/<board>.kicad_pcb")
  b.footprints  [Footprint] ref, value, lib, layer, x, y, rot, attrs, props, pads
  b.fps         {ref: Footprint} (the last of duplicate refs; b.duplicate_refs lists them)
  b.pads        [Pad] absolute centre and polygon (custom pads: anchor + primitives), net,
                func (pinfunction), ptype (pintype), kind (smd/thru_hole/np_thru_hole/connect),
                drill (w, h) or None, paste, mask_margin
  b.segs        [Seg(a, b, layer, net, width, length, kind)]; an arc is two chords start-mid and
                mid-end, each carrying half the true arc length
  b.vias        [Via(at, r, net, layers, drill, kind)]
  b.zones       [Zone] net, layers, outlines, fills {layer: [(pts, island)]}, filled, keepout
  b.edges       [Edge] Edge.Cuts primitives (board and footprint graphics) as point lists
  b.copper      copper layers in stack order; b.stackup, b.finish, b.aux_origin, b.setup
Walkers on the track graph (zones are ignored on purpose: a zone is not a route):
  track_path(start, goal, pads, segs, vias) -> 'track' | 'via' | 'none'      (check_decoupling D5)
  route(starts, goals, pads, segs, vias, allow_vias=True) -> Route or None   (net_path, check_decoupling)
  NetGraph(net, pads, segs, vias).route(...) / .reach_vias(starts)            (one graph, many queries)

Usage:   python3 pcb_board.py --self-test
Pitfalls: pad (at x y angle) stores the ABSOLUTE pad angle and footprint-relative unrotated x/y;
          a filled zone is stored as one fractured polygon per island, so a fill polygon is a piece
          of copper; '(fill yes' marks a filled zone, its absence a zone that was never filled.
"""
import heapq
import math
import os
import shutil
import sys
from collections import defaultdict, namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import Sym, find, first, parse  # noqa: E402

TOL = 0.01
Seg = namedtuple("Seg", "a b layer net width length kind")
Via = namedtuple("Via", "at r net layers drill kind")
Route = namedtuple("Route", "length vias by_layer hops start goal")

# ---------------------------------------------------------------- small helpers


def rot(px, py, deg):
    t = math.radians(deg)
    return px * math.cos(t) + py * math.sin(t), -px * math.sin(t) + py * math.cos(t)


def nums(e, n):
    return [float(x) for x in e[1:1 + n]]


def xy(e):
    return tuple(nums(e, 2))


def net_of(node, table):
    """KiCad <= 9: (net 3 "GND"); KiCad 10: (net "GND")."""
    if not node or len(node) < 2:
        return ""
    if len(node) >= 3:
        return str(node[2])
    v = node[1]
    if isinstance(v, Sym) and str(v).isdigit():
        return table.get(str(v), str(v))
    return str(v)


def val(e, key, default=None):
    n = first(e, key)
    return n[1] if n and len(n) > 1 else default

# ---------------------------------------------------------------- geometry


def point_seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def seg_param(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    return 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def poly_point_dist(poly, x, y):
    if point_in_poly(x, y, poly):
        return 0.0
    n = len(poly)
    return min(point_seg_dist(x, y, poly[i], poly[(i + 1) % n]) for i in range(n))


def poly_area(pts):
    n = len(pts)
    return abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2.0


def segs_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) > 0) != (o(a, b, d) > 0) and (o(c, d, a) > 0) != (o(c, d, b) > 0)


def pad_dist(p, q):
    """Edge-to-edge distance between two pads (0 when they overlap)."""
    n, m = len(p.poly), len(q.poly)
    for i in range(n):
        for j in range(m):
            if segs_cross(p.poly[i], p.poly[(i + 1) % n], q.poly[j], q.poly[(j + 1) % m]):
                return 0.0
    if point_in_poly(*p.poly[0], q.poly) or point_in_poly(*q.poly[0], p.poly):
        return 0.0
    return min(min(poly_point_dist(q.poly, *v) for v in p.poly), min(poly_point_dist(p.poly, *v) for v in q.poly))


def arc_geom(a, m, b):
    """Centre, radius, start angle and signed sweep (rad) of the arc a -> m -> b; None if collinear."""
    (ax, ay), (bx, by), (cx, cy) = a, m, b
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    s1, s2, s3 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (s1 * (by - cy) + s2 * (cy - ay) + s3 * (ay - by)) / d
    uy = (s1 * (cx - bx) + s2 * (ax - cx) + s3 * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    t0 = math.atan2(ay - uy, ax - ux)
    tm = (math.atan2(by - uy, bx - ux) - t0) % (2 * math.pi)
    te = (math.atan2(cy - uy, cx - ux) - t0) % (2 * math.pi)
    if te < 1e-12:
        te = 2 * math.pi
    sweep = te if tm <= te else -(2 * math.pi - te)
    return (ux, uy), r, t0, sweep


def arc_length(a, m, b):
    g = arc_geom(a, m, b)
    if not g:
        return math.dist(a, m) + math.dist(m, b)
    return abs(g[1] * g[3])


def arc_points(a, m, b, n=16):
    g = arc_geom(a, m, b)
    if not g:
        return [a, m, b]
    (ux, uy), r, t0, sw = g
    return [(ux + r * math.cos(t0 + sw * k / n), uy + r * math.sin(t0 + sw * k / n)) for k in range(n + 1)]


def bezier_points(p, n=16):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p[:4]
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        out.append((u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
                    u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3))
    return out

# ---------------------------------------------------------------- objects


class Pad:
    def __init__(self, ref, num, cx, cy, w, h, deg, shape, net, layers, kind="smd", drill=None,
                 func="", ptype="", local_rect=None, mask_margin=None):
        self.ref, self.num, self.cx, self.cy = ref, num, cx, cy
        self.w, self.h, self.deg, self.shape, self.net = w, h, deg, shape, net
        self.layers, self.kind, self.drill, self.func, self.ptype = layers, kind, drill, func, ptype
        self.local_rect, self.mask_margin = local_rect, mask_margin
        self.paste = any(l.endswith(".Paste") for l in layers)
        self.copper = kind != "np_thru_hole" and any(l.endswith(".Cu") for l in layers)
        self.poly = self._poly()
        xs, ys = [q[0] for q in self.poly], [q[1] for q in self.poly]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

    def _poly(self):
        hw, hh = self.w / 2, self.h / 2
        if self.local_rect:
            x0, y0, x1, y1 = self.local_rect
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        elif self.shape == "circle":
            pts = [(hw * math.cos(2 * math.pi * k / 24), hw * math.sin(2 * math.pi * k / 24)) for k in range(24)]
        elif self.shape == "oval" and abs(hw - hh) > 1e-9:
            r = min(hw, hh)
            pts = []
            if hw > hh:
                for cx, a0 in ((hw - r, -90), (-(hw - r), 90)):
                    pts += [(cx + r * math.cos(math.radians(a0 + 15 * k)), r * math.sin(math.radians(a0 + 15 * k))) for k in range(13)]
            else:
                for cy, a0 in ((hh - r, 0), (-(hh - r), 180)):
                    pts += [(r * math.cos(math.radians(a0 + 15 * k)), cy + r * math.sin(math.radians(a0 + 15 * k))) for k in range(13)]
        elif self.shape == "oval":
            pts = [(hw * math.cos(2 * math.pi * k / 24), hw * math.sin(2 * math.pi * k / 24)) for k in range(24)]
        else:   # rect, roundrect, trapezoid, chamfered: rectangle
            pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        out = []
        for u, v in pts:
            dx, dy = rot(u, v, self.deg)
            out.append((self.cx + dx, self.cy + dy))
        return out

    def on(self, layer):
        return any(l == layer or (l == "*.Cu" and layer.endswith(".Cu"))
                   or (l == "F&B.Cu" and layer in ("F.Cu", "B.Cu")) for l in self.layers)

    def contains(self, x, y, tol=TOL):
        x0, y0, x1, y1 = self.bbox
        if x < x0 - tol or x > x1 + tol or y < y0 - tol or y > y1 + tol:
            return False
        return point_in_poly(x, y, self.poly) or poly_point_dist(self.poly, x, y) <= tol

    def name(self):
        return f"{self.ref}.{self.num}"


class Footprint:
    def __init__(self, ref, value, lib, layer, x, y, rot_, attrs, props):
        self.ref, self.value, self.lib, self.layer = ref, value, lib, layer
        self.x, self.y, self.rot, self.attrs, self.props = x, y, rot_, attrs, props
        self.pads = []

    @property
    def tht(self):
        return "through_hole" in self.attrs or any(p.kind == "thru_hole" for p in self.pads)


class Zone:
    def __init__(self, net, layers, outlines, fills, filled, keepout, name, hatch):
        self.net, self.layers, self.outlines, self.fills = net, layers, outlines, fills
        self.filled, self.keepout, self.name, self.hatch = filled, keepout, name, hatch


class Edge:
    def __init__(self, kind, pts, ends=None, radius=None, closed=False):
        self.kind, self.pts, self.ends, self.radius, self.closed = kind, pts, ends, radius, closed


class Board:
    pass

# ---------------------------------------------------------------- loader

GRAPHICS = ("line", "arc", "circle", "rect", "poly", "curve")


def _pts(e):
    return [xy(p) for p in find(first(e, "pts") or [], "xy")]


def _edges(items, prefix, xf):
    out = []
    for g in items:
        if not (isinstance(g, list) and g and isinstance(g[0], str) and g[0].startswith(prefix)):
            continue
        kind = g[0][len(prefix):]
        if kind not in GRAPHICS or str(val(g, "layer", "")) != "Edge.Cuts":
            continue
        if kind == "line":
            a, b = xf(xy(first(g, "start"))), xf(xy(first(g, "end")))
            out.append(Edge("line", [a, b], (a, b)))
        elif kind == "arc":
            if first(g, "mid"):
                a, m, b = (xf(xy(first(g, k))) for k in ("start", "mid", "end"))
            else:   # KiCad 5: (start = centre) (end = arc start) (angle deg)
                c, s0 = xy(first(g, "start")), xy(first(g, "end"))
                ang = math.radians(float(val(g, "angle", 90)))
                r0, t0 = math.dist(c, s0), math.atan2(s0[1] - c[1], s0[0] - c[0])
                pm = (c[0] + r0 * math.cos(t0 + ang / 2), c[1] + r0 * math.sin(t0 + ang / 2))
                pe = (c[0] + r0 * math.cos(t0 + ang), c[1] + r0 * math.sin(t0 + ang))
                a, m, b = xf(s0), xf(pm), xf(pe)
            g2 = arc_geom(a, m, b)
            out.append(Edge("arc", arc_points(a, m, b, 32), (a, b), g2[1] if g2 else None))
        elif kind == "circle":
            c, e = xy(first(g, "center")), xy(first(g, "end"))
            r = math.dist(c, e)
            out.append(Edge("circle", [xf((c[0] + r * math.cos(2 * math.pi * k / 64), c[1] + r * math.sin(2 * math.pi * k / 64)))
                                       for k in range(64)], radius=r, closed=True))
        elif kind == "rect":
            (x0, y0), (x1, y1) = xy(first(g, "start")), xy(first(g, "end"))
            out.append(Edge("rect", [xf(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))], closed=True))
        elif kind == "poly":
            out.append(Edge("poly", [xf(p) for p in _pts(g)], closed=True))
        elif kind == "curve":
            pts = _pts(g)
            if len(pts) >= 4:
                c = [xf(p) for p in bezier_points(pts)]
                out.append(Edge("curve", c, (c[0], c[-1])))
    return out


def _custom_rect(pad, w, h):
    """Bounding rectangle (pad frame) of a custom pad's anchor and primitives."""
    prims = first(pad, "primitives")
    if not prims:
        return None
    pts = [(-w / 2, -h / 2), (w / 2, h / 2)]
    for g in prims[1:]:
        if not isinstance(g, list):
            continue
        k, wd = g[0], float(val(g, "width", 0) or 0) / 2
        if k == "gr_poly":
            q = _pts(g)
        elif k in ("gr_line", "gr_rect"):
            q = [xy(first(g, "start")), xy(first(g, "end"))]
        elif k == "gr_circle":
            c, e = xy(first(g, "center")), xy(first(g, "end"))
            r = math.dist(c, e)
            q = [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
        elif k == "gr_arc" and first(g, "mid"):
            q = arc_points(xy(first(g, "start")), xy(first(g, "mid")), xy(first(g, "end")), 8)
        else:
            continue
        pts += [(x - wd, y - wd) for x, y in q] + [(x + wd, y + wd) for x, y in q]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def load(path):
    t = parse(open(path, encoding="utf-8").read())
    b = Board()
    b.path = path
    table = {}
    for n in find(t, "net"):
        if len(n) >= 3:
            table[str(n[1])] = str(n[2])
    b.net_table = table
    # layers, stackup, setup
    lays = first(t, "layers") or []
    names = [str(e[1]) for e in lays[1:] if isinstance(e, list) and len(e) > 1]
    inner = sorted((n for n in names if n.startswith("In") and n.endswith(".Cu")), key=lambda n: int(n[2:-3]))
    b.copper = [n for n in ("F.Cu",) if n in names] + inner + [n for n in ("B.Cu",) if n in names]
    setup = first(t, "setup") or []
    st = first(setup, "stackup")
    b.stackup, b.finish = [], None
    if st:
        for L in find(st, "layer"):
            d = {"name": str(L[1])}
            for k in ("type", "thickness", "material", "epsilon_r"):
                if val(L, k) is not None:
                    d[k] = str(val(L, k))
            b.stackup.append(d)
        b.finish = val(st, "copper_finish")
        b.finish = str(b.finish) if b.finish is not None else None
    ao = first(setup, "aux_axis_origin")
    b.aux_origin = xy(ao) if ao else (0.0, 0.0)
    b.setup = {k: float(val(setup, k)) for k in ("pad_to_mask_clearance", "solder_mask_min_width")
               if val(setup, k) is not None}
    # footprints and pads
    b.footprints, b.pads, b.edges = [], [], _edges(t, "gr_", lambda p: p)
    for fp in find(t, "footprint"):
        props = {str(p[1]): str(p[2]) for p in find(fp, "property") if len(p) > 2}
        ref = props.get("Reference", "")
        value = props.get("Value", "")
        for p in find(fp, "fp_text"):
            if len(p) > 2 and p[1] == "reference" and not ref:
                ref = str(p[2])
            if len(p) > 2 and p[1] == "value" and not value:
                value = str(p[2])
        at = first(fp, "at")
        if not at:
            continue
        fx, fy = nums(at, 2)
        frot = float(at[3]) if len(at) > 3 else 0.0
        attr = first(fp, "attr")
        attrs = {str(x) for x in attr[1:]} if attr else set()
        if first(fp, "dnp") and str(val(fp, "dnp", "yes")) != "no":
            attrs.add("dnp")
        f = Footprint(ref, value, str(fp[1]) if len(fp) > 1 and not isinstance(fp[1], list) else "",
                      str(val(fp, "layer", "F.Cu")), fx, fy, frot, attrs, props)

        def xf(p, fx=fx, fy=fy, frot=frot):
            dx, dy = rot(p[0], p[1], frot)
            return fx + dx, fy + dy
        b.edges += _edges(fp, "fp_", xf)
        for p in find(fp, "pad"):
            num = str(p[1]) if len(p) > 1 and not isinstance(p[1], list) else ""
            kind = str(p[2]) if len(p) > 2 and not isinstance(p[2], list) else "smd"
            shape = str(p[3]) if len(p) > 3 and not isinstance(p[3], list) else "rect"
            pat, psz = first(p, "at"), first(p, "size")
            if not (pat and psz):
                continue
            px, py = nums(pat, 2)
            pdeg = float(pat[3]) if len(pat) > 3 else 0.0   # file stores the absolute pad angle
            dx, dy = rot(px, py, frot)
            w, h = nums(psz, 2)
            lay = first(p, "layers")
            layers = [str(x) for x in lay[1:]] if lay else []
            drill = None
            dr = first(p, "drill")
            if dr:
                dn = [float(x) for x in dr[1:] if not isinstance(x, list) and str(x) != "oval"]
                if dn:
                    drill = (dn[0], dn[1] if len(dn) > 1 else dn[0])
            mm = val(p, "solder_mask_margin")
            pad = Pad(ref, num, fx + dx, fy + dy, w, h, pdeg, shape, net_of(first(p, "net"), table), layers,
                      kind, drill, str(val(p, "pinfunction", "")), str(val(p, "pintype", "")),
                      _custom_rect(p, w, h) if shape == "custom" else None, float(mm) if mm is not None else None)
            f.pads.append(pad)
            b.pads.append(pad)
        b.footprints.append(f)
    b.fps, seen, dup = {}, set(), set()
    for f in b.footprints:
        if f.ref in seen:
            dup.add(f.ref)
        seen.add(f.ref)
        b.fps[f.ref] = f
    b.duplicate_refs = sorted(dup)
    # tracks
    b.segs = []
    for kind in ("segment", "arc"):
        for s in find(t, kind):
            st_, en, lay = first(s, "start"), first(s, "end"), first(s, "layer")
            if not (st_ and en):
                continue
            net, layer = net_of(first(s, "net"), table), str(lay[1]) if lay else ""
            width = float(val(s, "width", 0) or 0)
            a, e = xy(st_), xy(en)
            mid = first(s, "mid") if kind == "arc" else None
            if mid:
                m = xy(mid)
                L = arc_length(a, m, e)
                b.segs += [Seg(a, m, layer, net, width, L / 2, "arc"), Seg(m, e, layer, net, width, L / 2, "arc")]
            else:
                b.segs.append(Seg(a, e, layer, net, width, math.dist(a, e), "segment"))
    b.vias = []
    for v in find(t, "via"):
        at, sz, lay = first(v, "at"), first(v, "size"), first(v, "layers")
        if not at:
            continue
        layers = [str(x) for x in lay[1:]] if lay else ["F.Cu", "B.Cu"]
        vk = next((str(x) for x in v[1:] if isinstance(x, Sym) and str(x) in ("blind", "micro", "through")), None)
        vk = vk or str(val(v, "type", "through"))
        drill = float(val(v, "drill", 0) or 0)
        b.vias.append(Via(xy(at), float(sz[1]) / 2 if sz else 0.3, net_of(first(v, "net"), table), layers, drill, vk))
    b.zones = []
    for z in find(t, "zone"):
        nn = first(z, "net_name")
        net = str(nn[1]) if nn and len(nn) > 1 else net_of(first(z, "net"), table)
        lay = first(z, "layers") or first(z, "layer")
        layers = [str(x) for x in lay[1:]] if lay else []
        fills = defaultdict(list)
        for fpoly in find(z, "filled_polygon"):
            L = str(val(fpoly, "layer", layers[0] if layers else ""))
            fills[L].append((_pts(fpoly), first(fpoly, "island") is not None))
        fl = first(z, "fill")
        filled = bool(fl) and len(fl) > 1 and str(fl[1]) == "yes"
        hatch = bool(fl) and str(val(fl, "mode", "")) == "hatch"
        b.zones.append(Zone(net, layers, [_pts(pg) for pg in find(z, "polygon")], dict(fills), filled or bool(fills),
                            first(z, "keepout") is not None, str(val(z, "name", "") or ""), hatch))
    return b


def outline_bbox(board):
    pts = [p for e in board.edges for p in e.pts]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

# ---------------------------------------------------------------- walkers


def via_on(via, layer):
    _, _, _, layers = via[:4]
    if layer in layers:
        return True
    return "F.Cu" in layers and "B.Cu" in layers   # through via spans every copper layer


def track_path(start, goal, pads, segs, vias):
    """Follow tracks from pad `start` on its net; 'track' if `goal` is reached without passing a via,
    'via' if a via blocked every track route that would have continued, 'none' if no track route exists."""
    net = start.net
    S = [s for s in segs if s[3] == net]
    other_pads = [p for p in pads if p.net == net and p is not start and p is not goal]
    blocking = [v for v in vias if v[2] == net and not goal.contains(v[0][0], v[0][1], v[1])
                and not start.contains(v[0][0], v[0][1])]   # via in the pin pad: noted by the auditor, not a block

    def touches(seg, pt):
        return point_seg_dist(pt[0], pt[1], seg[0], seg[1]) <= TOL

    def via_hit(seg):
        return [v for v in blocking if via_on(v, seg[2]) and point_seg_dist(v[0][0], v[0][1], seg[0], seg[1]) <= v[1] + TOL]

    seen, queue, via_seen = set(), [], False
    for i, s in enumerate(S):
        if start.on(s[2]) and (start.contains(*s[0]) or start.contains(*s[1])):
            seen.add(i); queue.append(i)
    if not queue:
        return "none"
    while queue:
        i = queue.pop()
        s = S[i]
        if via_hit(s):
            via_seen = True
            continue
        for e in (s[0], s[1]):
            if goal.on(s[2]) and goal.contains(*e):
                return "track"
        hubs = [p for p in other_pads if p.on(s[2]) and (p.contains(*s[0]) or p.contains(*s[1]))]
        for j, o in enumerate(S):
            if j in seen:
                continue
            same_layer = o[2] == s[2]
            joined = same_layer and (touches(o, s[0]) or touches(o, s[1]) or touches(s, o[0]) or touches(s, o[1]))
            if not joined:
                joined = any(p.on(o[2]) and (p.contains(*o[0]) or p.contains(*o[1])) for p in hubs)
            if joined:
                seen.add(j); queue.append(j)
    return "via" if via_seen else "none"


class NetGraph:
    """Track graph of one net: segment pieces (split at T-joins and vias), vias (one node per layer,
    joined at a cost of one via), pads (one node per layer; plated holes join their layers for free).
    Zones are not part of it. Build once per net, query many times."""

    def __init__(self, net, pads, segs, vias, allow_vias=True):
        self.net, self.allow_vias = net, allow_vias
        S = [s for s in segs if s[3] == net]
        self.P = [p for p in pads if p.net == net and p.copper]
        self.V = [v for v in vias if v[2] == net]
        self.coords, self.adj = [], defaultdict(list)
        cuts = [[0.0, 1.0] for _ in S]
        by_layer, cell = defaultdict(list), 1.0
        for i, s in enumerate(S):
            by_layer[s[2]].append(i)
        for layer, idx in by_layer.items():     # split points: T-joins of other ends, via centres on a segment
            buckets = defaultdict(list)
            for e in [S[i][k] for i in idx for k in (0, 1)] + [v[0] for v in self.V if via_on(v, layer)]:
                buckets[(int(e[0] // cell), int(e[1] // cell))].append(e)
            for i in idx:
                a, b_ = S[i][0], S[i][1]
                near = [e for gx in range(int((min(a[0], b_[0]) - TOL) // cell), int((max(a[0], b_[0]) + TOL) // cell) + 1)
                        for gy in range(int((min(a[1], b_[1]) - TOL) // cell), int((max(a[1], b_[1]) + TOL) // cell) + 1)
                        for e in buckets.get((gx, gy), ())]
                eps = TOL / max(S[i].length, 1e-9)
                for e in near:
                    if point_seg_dist(e[0], e[1], a, b_) <= TOL:
                        t = seg_param(e[0], e[1], a, b_)
                        if eps < t < 1 - eps:
                            cuts[i].append(t)
        fine = defaultdict(list)

        def node(layer, p):
            gx, gy = round(p[0] / (4 * TOL)), round(p[1] / (4 * TOL))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for nid in fine[(layer, gx + dx, gy + dy)]:
                        if math.dist(self.coords[nid][1], p) <= TOL:
                            return nid
            self.coords.append((layer, p))
            fine[(layer, gx, gy)].append(len(self.coords) - 1)
            return len(self.coords) - 1

        for i, s in enumerate(S):
            ts = sorted(set(round(t, 9) for t in cuts[i]))
            pts = [(s[0][0] + t * (s[1][0] - s[0][0]), s[0][1] + t * (s[1][1] - s[0][1])) for t in ts]
            for k in range(len(ts) - 1):
                self._edge(node(s[2], pts[k]), node(s[2], pts[k + 1]), s.length * (ts[k + 1] - ts[k]), 0, ("seg", s[2]))
        coarse = defaultdict(list)
        for nid, (layer, p) in enumerate(self.coords):
            coarse[(layer, int(p[0] // cell), int(p[1] // cell))].append(nid)

        def around(layer, x0, y0, x1, y1):
            for gx in range(int(x0 // cell), int(x1 // cell) + 1):
                for gy in range(int(y0 // cell), int(y1 // cell) + 1):
                    yield from coarse.get((layer, gx, gy), ())
        self.hub = {}
        layers = {c[0] for c in self.coords}
        self.via_nodes = defaultdict(list)
        for vi, v in enumerate(self.V):
            (vx, vy), r = v[0], v[1] + TOL
            here = []
            for L in sorted(layers):
                if not via_on(v, L):
                    continue
                hits = [n for n in around(L, vx - r, vy - r, vx + r, vy + r) if math.dist(self.coords[n][1], v[0]) <= r]
                if hits:
                    vn = self._virtual(("via", vi, L), L, v[0])
                    self.via_nodes[vi].append(vn)
                    here.append(vn)
                    for n in hits:
                        self._edge(vn, n, 0.0, 0, ("via-pad", vi))
            if allow_vias:
                for x in range(len(here)):
                    for y in range(x + 1, len(here)):
                        self._edge(here[x], here[y], 0.0, 1, ("via", vi))
        self.pad_nodes = defaultdict(list)
        self.pad_index = {id(p): pi for pi, p in enumerate(self.P)}
        for pi, p in enumerate(self.P):
            x0, y0, x1, y1 = p.bbox
            here = []
            for L in sorted(layers):
                if not p.on(L):
                    continue
                hits = [n for n in around(L, x0 - TOL, y0 - TOL, x1 + TOL, y1 + TOL) if p.contains(*self.coords[n][1])]
                if hits:
                    pn = self._virtual(("pad", pi, L), L, (p.cx, p.cy))
                    self.pad_nodes[pi].append(pn)
                    here.append(pn)
                    for n in hits:
                        self._edge(pn, n, 0.0, 0, ("pad", pi))
            for x in range(len(here)):          # a plated hole joins its layers like a via, without counting
                for y in range(x + 1, len(here)):
                    self._edge(here[x], here[y], 0.0, 0, ("hole", pi))

    def _edge(self, u, v, length, via, label):
        self.adj[u].append((v, length, via, label))
        self.adj[v].append((u, length, via, label))

    def _virtual(self, key, layer, p):
        if key not in self.hub:
            self.hub[key] = len(self.coords)
            self.coords.append((layer, p))
        return self.hub[key]

    def nodes_of(self, pads):
        return {n for p in pads if id(p) in self.pad_index for n in self.pad_nodes[self.pad_index[id(p)]]}

    def dijkstra(self, src, dst=None):
        dist, prev = {n: (0.0, 0) for n in src}, {}
        heap = [(0.0, 0, n) for n in src]
        heapq.heapify(heap)
        while heap:
            d, nv, u = heapq.heappop(heap)
            if (d, nv) > dist.get(u, (math.inf, 0)):
                continue
            if dst is not None and u in dst:
                return dist, prev, u
            for v, L, via, label in self.adj[u]:
                nd = (d + L, nv + via)
                if nd < dist.get(v, (math.inf, 0)):
                    dist[v] = nd
                    prev[v] = (u, L, via, label)
                    heapq.heappush(heap, (nd[0], nd[1], v))
        return dist, prev, None

    def route(self, starts, goals):
        src, dst = self.nodes_of(starts), self.nodes_of(goals)
        if not src or not dst:
            return None
        dist, prev, goal = self.dijkstra(src, dst)
        return None if goal is None else self._trace(dist, prev, goal)

    def reach_vias(self, starts):
        """{via index: (length mm, vias passed)} for every via reachable from `starts` by tracks."""
        dist, _, _ = self.dijkstra(self.nodes_of(starts))
        out = {}
        for vi, ns in self.via_nodes.items():
            best = min((dist[n] for n in ns if n in dist), default=None)
            if best is not None:
                out[vi] = (round(best[0], 3), best[1])
        return out

    def _trace(self, dist, prev, goal):
        hops, layer_len = [], defaultdict(float)
        n = goal
        while n in prev:
            u, L, via, label = prev[n]
            if label[0] == "seg":
                layer_len[label[1]] += L
                if hops and hops[-1][0] == "seg" and hops[-1][1] == label[1]:
                    hops[-1] = ("seg", label[1], hops[-1][2] + L)
                else:
                    hops.append(("seg", label[1], L))
            elif label[0] == "via" and via:
                hops.append(("via", self.V[label[1]][0]))
            elif label[0] in ("pad", "hole"):
                name = self.P[label[1]].name()
                if not (hops and hops[-1] == ("pad", name)):
                    hops.append(("pad", name))
            n = u
        hops.reverse()
        first_pad = next((h[1] for h in hops if h[0] == "pad"), None)
        last_pad = next((h[1] for h in reversed(hops) if h[0] == "pad"), None)
        return Route(round(dist[goal][0], 4), dist[goal][1], dict(layer_len), hops, first_pad, last_pad)


def route(starts, goals, pads, segs, vias, allow_vias=True):
    """Shortest routed copper path (tracks and arcs, true arc length) from any pad in `starts` to any pad
    in `goals` on their net. Pads of the net (THT on every layer) and vias join tracks; a via is counted
    when the path changes layer through it. Zones are ignored. Returns Route or None."""
    return NetGraph(starts[0].net, pads, segs, vias, allow_vias).route(starts, goals)


def fmt_hops(r):
    out = []
    for h in r.hops:
        if h[0] == "seg":
            out.append(f"{h[1]} {h[2]:.2f}")
        elif h[0] == "via":
            out.append(f"via ({h[1][0]:.2f},{h[1][1]:.2f})")
        else:
            out.append(h[1])
    return " > ".join(out)

# ---------------------------------------------------------------- self-test

FIXTURE = """(kicad_pcb (version 20251001) (generator "pcbnew")
 (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (4 "In1.Cu" power) (25 "Edge.Cuts" user))
 (setup (stackup (layer "F.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 1" (type "prepreg") (thickness 0.2))
   (copper_finish "ENIG")) (pad_to_mask_clearance 0.05) (aux_axis_origin 10 30))
 (net 0 "") (net 1 "/A")
 (gr_rect (start 10 10) (end 40 30) (layer "Edge.Cuts"))
 (footprint "lib:R" (layer "F.Cu") (at 20 20 90)
  (property "Reference" "R1") (property "Value" "1k")
  (pad "1" smd rect (at -1 0 90) (size 1 0.6) (layers "F.Cu" "F.Mask" "F.Paste") (net 1 "/A") (pinfunction "~") (pintype "passive"))
  (pad "2" smd rect (at 1 0 90) (size 1 0.6) (layers "F.Cu" "F.Mask" "F.Paste") (net "/A")))
 (footprint "lib:U" (layer "F.Cu") (at 30 20)
  (property "Reference" "U1") (property "Value" "X")
  (pad "1" smd custom (at 0 0) (size 0.1 0.1) (layers "F.Cu" "F.Mask") (net "/A")
   (primitives (gr_poly (pts (xy -0.1 -0.1) (xy 1.0 -0.1) (xy 1.0 0.1) (xy -0.1 0.1)) (width 0) (fill yes))))
  (pad "2" thru_hole circle (at 0 3) (size 1.6 1.6) (drill 1.0) (layers "*.Cu" "*.Mask") (net "/A")))
 (segment (start 20 21) (end 25 21) (width 0.25) (layer "F.Cu") (net "/A"))
 (segment (start 23 21) (end 23 25) (width 0.25) (layer "F.Cu") (net "/A"))
 (arc (start 25 21) (mid 26.414214 21.585786) (end 27 23) (width 0.25) (layer "F.Cu") (net "/A"))
 (segment (start 27 23) (end 30 23) (width 0.25) (layer "F.Cu") (net "/A"))
 (segment (start 20 19) (end 22 19) (width 0.25) (layer "F.Cu") (net "/A"))
 (via (at 22 19) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/A"))
 (segment (start 22 19) (end 30.9 19) (width 0.25) (layer "B.Cu") (net "/A"))
 (via (at 30.9 19) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/A"))
 (segment (start 30.9 19) (end 30.9 20) (width 0.25) (layer "F.Cu") (net "/A"))
 (zone (net 1) (net_name "/A") (layer "In1.Cu") (fill yes) (polygon (pts (xy 10 10) (xy 40 10) (xy 40 30) (xy 10 30)))
  (filled_polygon (layer "In1.Cu") (pts (xy 10 10) (xy 40 10) (xy 40 30) (xy 10 30))))
)
"""


def self_test():
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.kicad_pcb")
    open(p, "w", encoding="utf-8").write(FIXTURE)
    b = load(p)
    assert b.copper == ["F.Cu", "In1.Cu", "B.Cu"] and b.finish == "ENIG" and b.aux_origin == (10.0, 30.0), (b.copper, b.finish)
    r1 = b.fps["R1"]
    p1 = next(x for x in r1.pads if x.num == "1")
    assert abs(p1.cx - 20) < 1e-6 and abs(p1.cy - 21) < 1e-6, (p1.cx, p1.cy)       # rotated 90: (-1,0) -> (0,+1)
    assert {x.net for x in b.pads} == {"/A"}, "numbered and named net forms"
    u1 = next(x for x in b.fps["U1"].pads if x.num == "1")
    assert u1.contains(30.9, 20.0) and not u1.contains(31.2, 20.0), "custom pad covers its primitives"
    arcs = [x for x in b.segs if x.kind == "arc"]
    assert len(arcs) == 2 and abs(sum(x.length for x in arcs) - math.pi) < 1e-3, arcs     # quarter arc, r = 2
    assert outline_bbox(b) == (10.0, 10.0, 40.0, 30.0)
    r = route([p1], [next(x for x in b.fps["U1"].pads if x.num == "2")], b.pads, b.segs, b.vias)
    assert r and abs(r.length - (5 + math.pi + 3)) < 1e-3 and r.vias == 0, r    # R1.1 > trunk > arc > U1.2 (THT)
    q = route([next(x for x in r1.pads if x.num == "2")], [u1], b.pads, b.segs, b.vias)
    assert q and q.vias == 2 and abs(q.length - (2 + 8.9 + 1)) < 1e-3, q
    assert route([next(x for x in r1.pads if x.num == "2")], [u1], b.pads, b.segs, b.vias, allow_vias=False) is None
    assert track_path(next(x for x in r1.pads if x.num == "2"), u1, b.pads, b.segs, b.vias) == "via"
    # T-join: the stub (23,21)-(23,25) joins the trunk mid-segment and is reachable
    stub_end = Pad("TP", "1", 23, 25, 0.5, 0.5, 0, "circle", "/A", ["F.Cu"])
    t2 = route([p1], [stub_end], b.pads + [stub_end], b.segs, b.vias)
    assert t2 and abs(t2.length - 7.0) < 1e-3, t2
    shutil.rmtree(d, ignore_errors=True)
    print("self-test OK: both net forms, rotated pads, custom pad primitives, arc length, outline bbox, "
          "route through an arc and a THT pad, two-via route refused when vias are not allowed, T-join")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        sys.exit(0)
    print(__doc__)
    sys.exit(2)

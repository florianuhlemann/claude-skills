#!/usr/bin/env python3
"""Routed copper length between two pads of one net, read from the board file (no pcbnew).

Every length claim in a review document (critical loop, crystal trace, sense line, decoupling
"pad to pin") is checked against the copper that is routed, never against a straight line.

Usage:
  net_path.py <board.kicad_pcb> <REF.PAD> <REF.PAD> [--no-via] [--json]
  net_path.py <board.kicad_pcb> --pairs pairs.txt [--tol 0.5] [--json]
        pairs.txt: one pair per line "<REF.PAD> <REF.PAD> [claimed_mm] [label ...]", '#' comments
  net_path.py --self-test

Length = tracks and arcs (true arc length) along the shortest route, pads of the same net passed
through (copper is copper), THT pads join their layers, a via is counted when the route changes
layer through it. Zones are ignored: a connection made only by a zone is reported as "not
connected by tracks", with "zone only" when both pads touch a fill of the net on a common layer,
or "through the plane" naming, for each end, the first via its tracks reach that sits in a fill
of the net and the track length to it (pin > via > plane > via > cap).
Straight-line centre and pad-edge distances are printed next to it for comparison.
Exit 0 when every pair is connected by tracks and within its claim (+ --tol mm), 1 otherwise,
2 on usage.
Pitfalls: REF.PAD uses the pad NUMBER (U1.6, not U1.VIN); pads sharing a number (split exposed
pads) are all taken as the end point.
"""
import json
import math
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_board import NetGraph, fmt_hops, load, pad_dist, point_in_poly, poly_point_dist  # noqa: E402

SPEC = re.compile(r"^([A-Za-z_#][\w#]*?)[.:](.+)$")


def pads_of(b, spec):
    m = SPEC.match(spec)
    if not m:
        raise SystemExit(f"bad pad '{spec}': use REF.PAD (pad number)")
    ref, num = m.groups()
    f = b.fps.get(ref)
    ps = [p for p in (f.pads if f else []) if p.num == num and p.copper]
    if not ps:
        raise SystemExit(f"pad {ref}.{num} not on the board")
    return ps


def zone_touch(b, pad):
    """Layers on which a filled zone of the pad's net touches the pad."""
    out = set()
    for z in b.zones:
        if z.net != pad.net or z.keepout:
            continue
        for layer, polys in z.fills.items():
            if not pad.on(layer):
                continue
            for pts, _ in polys:
                if len(pts) < 3:
                    continue
                if point_in_poly(pad.cx, pad.cy, pts) or any(point_in_poly(x, y, pts) for x, y in pad.poly) \
                        or min(poly_point_dist(pad.poly, x, y) for x, y in pts) <= 0.02:
                    out.add(layer)
                    break
    return out


def fill_layers_at(b, net, x, y, r):
    """Layers on which a fill of `net` reaches the circle (x, y, r): solid, or by a thermal spoke."""
    out = set()
    for z in b.zones:
        if z.net != net or z.keepout:
            continue
        for layer, polys in z.fills.items():
            if any(len(pts) >= 3 and poly_point_dist(pts, x, y) <= r + 0.02 for pts, _ in polys):
                out.add(layer)
    return out


_GRAPHS = {}


def graph(b, net, allow_vias):
    key = (id(b), net, allow_vias)
    if key not in _GRAPHS:
        _GRAPHS[key] = NetGraph(net, b.pads, b.segs, b.vias, allow_vias)
    return _GRAPHS[key]


def plane_link(b, g, A, B):
    """How two ends that no track joins reach a fill: [(end, length to via, via xy, layers)]."""
    out = []
    for name, ends in (("from", A), ("to", B)):
        reach = g.reach_vias(ends)
        best = None
        for vi, (L, nv) in sorted(reach.items(), key=lambda kv: kv[1]):
            v = g.V[vi]
            layers = fill_layers_at(b, v[2], v[0][0], v[0][1], v[1])
            if layers:
                best = (name, L, v[0], sorted(layers))
                break
        out.append(best)
    return out


def measure(b, a_spec, b_spec, allow_vias=True):
    A, B = pads_of(b, a_spec), pads_of(b, b_spec)
    res = {"from": a_spec, "to": b_spec, "net": A[0].net}
    if A[0].net != B[0].net or not A[0].net:
        res.update(status="different nets", detail=f"{a_spec} on {A[0].net or '-'}, {b_spec} on {B[0].net or '-'}")
        return res
    pa, pb = min(((p, q) for p in A for q in B), key=lambda pq: math.hypot(pq[0].cx - pq[1].cx, pq[0].cy - pq[1].cy))
    res["centre_mm"] = round(math.hypot(pa.cx - pb.cx, pa.cy - pb.cy), 2)
    res["edge_mm"] = round(pad_dist(pa, pb), 2)
    g = graph(b, A[0].net, allow_vias)
    r = g.route(A, B)
    if r:
        res.update(status="routed", routed_mm=round(r.length, 2), vias=r.vias,
                   by_layer={k: round(v, 2) for k, v in r.by_layer.items()}, path=fmt_hops(r))
    else:
        common = zone_touch(b, pa) & zone_touch(b, pb)
        if common:
            detail = "zone only (both pads touch the fill on " + ", ".join(sorted(common)) + ")"
        else:
            links = plane_link(b, graph(b, A[0].net, True), A, B)
            if all(links):
                detail = "through the plane: " + "; ".join(
                    f"{a_spec if l[0] == 'from' else b_spec} reaches via ({l[2][0]:.2f},{l[2][1]:.2f}) after {l[1]:.2f} mm "
                    f"of track, which sits in the fill on {', '.join(l[3])}" for l in links)
                res["plane"] = [{"end": l[0], "track_mm": l[1], "via": l[2], "fill_layers": l[3]} for l in links]
            else:
                detail = ("no via-free track route" if not allow_vias else
                          "no track route, and no zone fill reached from both ends (unrouted?)")
        res.update(status="not connected by tracks", detail=detail)
    return res


def show(res, claim=None, tol=0.5):
    head = f"{res['from']} -> {res['to']}  net {res['net'] or '-'}"
    if res["status"] != "routed":
        print(f"{head}\n  {res['status'].upper()}: {res.get('detail', '')}")
        return False
    layers = ", ".join(f"{k} {v:.2f}" for k, v in sorted(res["by_layer"].items()))
    print(f"{head}\n  routed copper {res['routed_mm']:.2f} mm, {res['vias']} via(s) ({layers}); "
          f"straight line: centre {res['centre_mm']:.2f} mm, pad edge {res['edge_mm']:.2f} mm")
    print(f"  path: {res['path']}")
    if claim is not None:
        ok = res["routed_mm"] <= claim + tol
        print(f"  claimed {claim:g} mm: {'ok' if ok else 'EXCEEDED by %.2f mm' % (res['routed_mm'] - claim)}")
        return ok
    return True

# ---------------------------------------------------------------- self-test

FIX = """(kicad_pcb (version 20251001)
 (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
 (footprint "lib:IC" (layer "F.Cu") (at 20 20)
  (property "Reference" "U1")
  (pad "6" smd rect (at 0 0) (size 0.6 0.3) (layers "F.Cu") (net "/VA"))
  (pad "4" smd rect (at 0 2) (size 0.6 0.3) (layers "F.Cu") (net "/NB"))
  (pad "9" smd rect (at 0 4) (size 0.6 0.3) (layers "F.Cu") (net "/Z"))
  (pad "11" smd rect (at 0 6) (size 0.6 0.3) (layers "F.Cu") (net "/P")))
 (footprint "lib:C" (layer "F.Cu") (at 24.5 26)
  (property "Reference" "C3")
  (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "/P")))
 (segment (start 20 26) (end 20 27) (width 0.25) (layer "F.Cu") (net "/P"))
 (via (at 20 27) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/P"))
 (segment (start 24 26) (end 24 27.5) (width 0.25) (layer "F.Cu") (net "/P"))
 (via (at 24 27.5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/P"))
 (zone (net_name "/P") (layer "B.Cu") (fill yes) (polygon (pts (xy 19 26.5) (xy 25 26.5) (xy 25 28.5) (xy 19 28.5)))
  (filled_polygon (layer "B.Cu") (pts (xy 19 26.5) (xy 25 26.5) (xy 25 28.5) (xy 19 28.5))))
 (footprint "lib:C" (layer "F.Cu") (at 23 20)
  (property "Reference" "C1")
  (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "/VA"))
  (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "/NB")))
 (footprint "lib:C" (layer "F.Cu") (at 23 24)
  (property "Reference" "C2")
  (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "/Z")))
 (segment (start 20 20) (end 20 17) (width 0.25) (layer "F.Cu") (net "/VA"))
 (via (at 20 17) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/VA"))
 (segment (start 20 17) (end 26 17) (width 0.25) (layer "B.Cu") (net "/VA"))
 (via (at 26 17) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/VA"))
 (arc (start 26 17) (mid 24.585786 17.585786) (end 24 19) (width 0.25) (layer "F.Cu") (net "/VA"))
 (segment (start 24 19) (end 22.5 20) (width 0.25) (layer "F.Cu") (net "/VA"))
 (segment (start 20 22) (end 23.5 20) (width 0.25) (layer "F.Cu") (net "/NB"))
 (zone (net_name "/Z") (layer "F.Cu") (fill yes) (polygon (pts (xy 19 23) (xy 24 23) (xy 24 25) (xy 19 25)))
  (filled_polygon (layer "F.Cu") (pts (xy 19 23) (xy 24 23) (xy 24 25) (xy 19 25))))
)
"""


def self_test():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "b.kicad_pcb")
    open(p, "w", encoding="utf-8").write(FIX)
    b = load(p)
    r = measure(b, "U1.6", "C1.1")
    arc = math.pi / 2 * 2                                    # quarter arc, r = 2
    want = 3 + 6 + arc + math.hypot(1.5, 1)
    assert r["status"] == "routed" and abs(r["routed_mm"] - want) < 0.01 and r["vias"] == 2, r
    assert r["centre_mm"] == 2.5 and r["routed_mm"] > 4 * r["centre_mm"], r   # straight line understates 4x
    assert measure(b, "U1.6", "C1.1", allow_vias=False)["status"] == "not connected by tracks"
    z = measure(b, "U1.9", "C2.1")
    assert z["status"] == "not connected by tracks" and z["detail"].startswith("zone only"), z
    assert measure(b, "U1.4", "C1.1")["status"] == "different nets"
    pl = measure(b, "U1.11", "C3.1")                         # pin > via > B.Cu plane > via > cap
    assert pl["detail"].startswith("through the plane") and [x["track_mm"] for x in pl["plane"]] == [1.0, 1.5], pl
    pf = os.path.join(d, "pairs.txt")
    open(pf, "w").write(f"# loop claimed in a review document\nU1.6 C1.1 {want - 2:.2f} supply-cap loop\nU1.4 C1.2 5\n")
    assert run_pairs(b, pf, 0.5, quiet=True) == 1                         # stale claim caught
    open(pf, "w").write(f"U1.6 C1.1 {want:.2f}\nU1.4 C1.2 5\n")
    assert run_pairs(b, pf, 0.5, quiet=True) == 0
    shutil.rmtree(d, ignore_errors=True)
    print(f"self-test OK: two-via route with an arc measured {r['routed_mm']:.2f} mm against a {r['centre_mm']} mm "
          "straight line; via-free search refuses it; zone-only and pin > via > plane > via > cap connections named; different nets caught; "
          "a claim 2 mm short of the routed copper fails --pairs, the true claim passes")


def run_pairs(b, path, tol, as_json=False, quiet=False):
    rc, out = 0, []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        claim = None
        if len(parts) > 2:
            try:
                claim = float(parts[2])
            except ValueError:
                claim = None
        res = measure(b, parts[0], parts[1])
        res["claim_mm"] = claim
        res["label"] = " ".join(parts[3:] if claim is not None else parts[2:])
        ok = res["status"] == "routed" and (claim is None or res["routed_mm"] <= claim + tol)
        res["ok"] = ok
        rc |= 0 if ok else 1
        out.append(res)
        if not (as_json or quiet):
            if res["label"]:
                print(f"[{res['label']}]")
            show(res, claim, tol)
    if as_json:
        print(json.dumps(out, indent=1))
    elif not quiet:
        print(f"\n{len(out)} pair(s), {sum(1 for r in out if not r['ok'])} not connected by tracks or over the claim "
              f"(tolerance {tol:g} mm)")
    return rc


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    tol = float(argv[argv.index("--tol") + 1]) if "--tol" in argv else 0.5
    skip = {argv.index(o) + 1 for o in ("--tol", "--pairs") if o in argv}
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and i not in skip]
    if "--pairs" in argv and pos:
        return run_pairs(load(pos[0]), argv[argv.index("--pairs") + 1], tol, "--json" in argv)
    if len(pos) != 3:
        print(__doc__)
        return 2
    res = measure(load(pos[0]), pos[1], pos[2], "--no-via" not in argv)
    if "--json" in argv:
        print(json.dumps(res, indent=1))
        return 0 if res["status"] == "routed" else 1
    return 0 if show(res) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

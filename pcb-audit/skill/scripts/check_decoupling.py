#!/usr/bin/env python3
"""Decoupling audit: does each capacitor serve the pin it was added for?

The schematic states the intent in one symbol field per capacitor,
Decouples = "<ref>:<pin number>[,<ref>:<pin number>...]" (pin numbers, not
names) or "bulk" for a rail cap that serves no single pin. The ratsnest
cannot show the assignment (it draws the shortest line to the same net);
this script checks it against the netlist and, when a board is given, the
copper.

Usage:
  kicad-cli sch export netlist -o build/net.kicad_net hardware/<board>.kicad_sch
  check_decoupling.py build/net.kicad_net [hardware/<board>.kicad_pcb]
        [--max-dist 2.0] [--gnd-via-dist 1.0] [--cap-refs REGEX] [--gnd-net REGEX]
        [--json] [--self-test] [--write-fixtures DIR]

Netlist checks (gate 4, board optional):
  D1 major    unassigned cap: a capacitor shares a net with a supply pin
              (a Decouples target or a power_in pin of a part with > 2 pins,
              ground nets excluded) and carries no Decouples field
  D2 blocker  assigned to a pin on another net (also: target does not exist,
              value malformed, cap or pin missing on the board)
  D3 major    coverage: a supply pin with no cap assigned to it (listed, since
              a datasheet may allow pins to share a cap; justify in the report)
Board checks (gate 6):
  D4 major    assigned cap pad <-> target pad, edge-to-edge > --max-dist mm
  D5 blocker  cap feeds the pin through the plane: from the target pad, tracks
              and arcs on the same net (endpoints or T-joins within 0.01 mm,
              other pads of the net pass, zones ignored) never reach the cap's
              pad without passing a via
  D6 major    nearest same-net cap pad to the target pin is not the assigned cap
  D7 minor    no via on the cap's return-pad net within --gnd-via-dist mm
              (edge to edge) of the return pad

Exit 1 on any blocker or major, 0 otherwise, 2 on usage. The Decouples field is
read from the netlist comp in both forms KiCad writes:
(property (name "Decouples") (value "U1:12")) and (fields (field (name "Decouples") "U1:12")).
"""
import json
import math
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import Sym, find, first, parse  # noqa: E402

SEV_ORDER = {"blocker": 0, "major": 1, "minor": 2, "note": 3}
DEF_CAP = r"^C\d+$"
DEF_GND = r"(^|/)(A|D|P|S)?(GND|VSS)\w*$|(^|/)0V$"
TOL = 0.01

# ---------------------------------------------------------------- netlist


def load_netlist(path):
    t = parse(open(path, encoding="utf-8").read())
    comps = {}
    for c in find(first(t, "components") or [], "comp"):
        ref = first(c, "ref")[1]
        val = first(c, "value")
        fields = {}
        for p in find(c, "property"):
            n, v = first(p, "name"), first(p, "value")
            if n and v and len(n) > 1 and len(v) > 1:
                fields[str(n[1])] = str(v[1])
        fl = first(c, "fields")
        for f in find(fl or [], "field"):
            n = first(f, "name")
            vals = [x for x in f[1:] if not isinstance(x, list)]
            if n and len(n) > 1 and vals:
                fields.setdefault(str(n[1]), str(vals[-1]))
        comps[ref] = {"value": str(val[1]) if val and len(val) > 1 else "", "fields": fields, "pins": {}}
    nets = {}
    for n in find(first(t, "nets") or [], "net"):
        name = str(first(n, "name")[1])
        nets[name] = []
        for nd in find(n, "node"):
            ref, pin = str(first(nd, "ref")[1]), str(first(nd, "pin")[1])
            pt, pf = first(nd, "pintype"), first(nd, "pinfunction")
            info = {"net": name, "type": str(pt[1]) if pt else "", "func": str(pf[1]) if pf else ""}
            comps.setdefault(ref, {"value": "", "fields": {}, "pins": {}})["pins"][pin] = info
            nets[name].append((ref, pin))
    return comps, nets


def short(net):
    return net.split("/")[-1] if net else "-"

# ---------------------------------------------------------------- board


def rot(px, py, deg):
    t = math.radians(deg)
    return px * math.cos(t) + py * math.sin(t), -px * math.sin(t) + py * math.cos(t)


def nums(e, n):
    return [float(x) for x in e[1:1 + n]]


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


class Pad:
    def __init__(self, ref, num, cx, cy, w, h, deg, shape, net, layers):
        self.ref, self.num, self.cx, self.cy = ref, num, cx, cy
        self.w, self.h, self.deg, self.shape, self.net = w, h, deg, shape, net
        self.layers = layers
        self.poly = self._poly()

    def _poly(self):
        hw, hh = self.w / 2, self.h / 2
        if self.shape == "circle":
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
        else:   # rect, roundrect, trapezoid, custom (anchor size): rectangle
            pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        out = []
        for u, v in pts:
            dx, dy = rot(u, v, self.deg)
            out.append((self.cx + dx, self.cy + dy))
        return out

    def on(self, layer):
        return any(l == layer or (l == "*.Cu" and layer.endswith(".Cu")) for l in self.layers)

    def contains(self, x, y, tol=TOL):
        return point_in_poly(x, y, self.poly) or poly_point_dist(self.poly, x, y) <= tol


def load_board(path):
    t = parse(open(path, encoding="utf-8").read())
    table = {}
    for n in find(t, "net"):
        if len(n) >= 3:
            table[str(n[1])] = str(n[2])
    fps = {}
    for fp in find(t, "footprint"):
        ref = ""
        for p in find(fp, "property"):
            if len(p) > 2 and p[1] == "Reference":
                ref = str(p[2])
        for p in find(fp, "fp_text"):
            if len(p) > 2 and p[1] == "reference" and not ref:
                ref = str(p[2])
        at = first(fp, "at")
        if not (ref and at):
            continue
        fx, fy = nums(at, 2)
        frot = float(at[3]) if len(at) > 3 else 0.0
        pads = []
        for p in find(fp, "pad"):
            num = str(p[1]) if len(p) > 1 else ""
            pat, psz = first(p, "at"), first(p, "size")
            if num == "" or not (pat and psz):
                continue
            px, py = nums(pat, 2)
            pdeg = float(pat[3]) if len(pat) > 3 else 0.0   # file stores the absolute pad angle
            dx, dy = rot(px, py, frot)
            w, h = nums(psz, 2)
            shape = str(p[3]) if len(p) > 3 else "rect"
            lay = first(p, "layers")
            layers = [str(x) for x in lay[1:]] if lay else []
            if not any(l.endswith(".Cu") for l in layers):
                continue
            pads.append(Pad(ref, num, fx + dx, fy + dy, w, h, pdeg, shape, net_of(first(p, "net"), table), layers))
        fps[ref] = pads
    segs = []
    for kind in ("segment", "arc"):
        for s in find(t, kind):
            st, en, lay = first(s, "start"), first(s, "end"), first(s, "layer")
            if not (st and en):
                continue
            net, layer = net_of(first(s, "net"), table), str(lay[1]) if lay else ""
            a, b = tuple(nums(st, 2)), tuple(nums(en, 2))
            mid = first(s, "mid") if kind == "arc" else None
            if mid:
                m = tuple(nums(mid, 2))
                segs += [(a, m, layer, net), (m, b, layer, net)]
            else:
                segs.append((a, b, layer, net))
    vias = []
    for v in find(t, "via"):
        at, sz, lay = first(v, "at"), first(v, "size"), first(v, "layers")
        if not at:
            continue
        layers = [str(x) for x in lay[1:]] if lay else ["F.Cu", "B.Cu"]
        vias.append((tuple(nums(at, 2)), float(sz[1]) / 2 if sz else 0.3, net_of(first(v, "net"), table), layers))
    return fps, segs, vias

# ---------------------------------------------------------------- geometry


def point_seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


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


def via_on(via, layer):
    _, _, _, layers = via
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

# ---------------------------------------------------------------- analysis


def analyse(net_path, pcb_path=None, max_dist=2.0, gnd_via_dist=1.0, cap_refs=DEF_CAP, gnd_net=DEF_GND):
    comps, nets = load_netlist(net_path)
    is_cap_ref = re.compile(cap_refs)
    is_gnd = re.compile(gnd_net, re.I)
    findings, rows = [], []

    def add(check, sev, cap, target, msg):
        findings.append({"check": check, "severity": sev, "cap": cap, "target": target, "message": msg})

    caps = {r for r, c in comps.items() if is_cap_ref.match(r) or "Decouples" in c["fields"]}
    assign, bulk = {}, set()
    for r in sorted(caps):
        raw = comps[r]["fields"].get("Decouples", "").strip()
        if not raw:
            continue
        if raw.lower() == "bulk":
            bulk.add(r)
            continue
        assign[r] = []
        for item in [x.strip() for x in raw.split(",") if x.strip()]:
            m = re.fullmatch(r"([A-Za-z_#][\w#]*):([\w.+-]+)", item)
            if not m:
                add("D2", "blocker", r, item, f"Decouples value '{item}' is not <ref>:<pin number>")
                continue
            tref, tpin = m.groups()
            if tref not in comps or tpin not in comps[tref]["pins"]:
                add("D2", "blocker", r, item, f"Decouples names {tref} pin {tpin}, which is not in the netlist")
                continue
            assign[r].append((tref, tpin))
    targets = {t for ts in assign.values() for t in ts}
    supply = set(targets)
    for ref, c in comps.items():
        if len(c["pins"]) > 2 and ref not in caps:
            for pin, info in c["pins"].items():
                if info["type"] == "power_in" and not is_gnd.search(info["net"]):
                    supply.add((ref, pin))
    supply_nets = {comps[r]["pins"][p]["net"] for r, p in supply}

    def cap_nets(r):
        return {i["net"] for i in comps[r]["pins"].values()}

    # D1 unassigned caps
    for r in sorted(caps):
        if r in assign or r in bulk:
            continue
        hit = sorted(cap_nets(r) & supply_nets)
        if hit:
            add("D1", "major", r, "-", f"unassigned cap on supply net {', '.join(short(n) for n in hit)}: "
                "set Decouples=<ref>:<pin> or bulk")
            rows.append({"cap": r, "decouples": "-", "net": short(hit[0]), "verdict": "major"})
    # D2 wrong net
    for r, ts in assign.items():
        for tref, tpin in ts:
            tnet = comps[tref]["pins"][tpin]["net"]
            if tnet not in cap_nets(r):
                add("D2", "blocker", r, f"{tref}:{tpin}", f"assigned to a pin on another net: {tref}.{tpin} is on "
                    f"{short(tnet)}, {r} is on {', '.join(sorted(short(n) for n in cap_nets(r)))}")
    # D3 coverage
    for tref, tpin in sorted(supply):
        if (tref, tpin) in targets:
            continue
        info = comps[tref]["pins"][tpin]
        sib = sorted(f"{c}->{a}:{b}" for c, ts in assign.items() for a, b in ts
                     if a == tref and comps[a]["pins"][b]["net"] == info["net"])
        extra = f"; same-net caps of {tref}: {', '.join(sib)}" if sib else ""
        add("D3", "major", "-", f"{tref}:{tpin}", f"no cap assigned to {tref}.{tpin} (pin {info['func'] or '?'}, "
            f"net {short(info['net'])}){extra} — datasheet allows sharing? justify, else add a cap")

    board = None
    if pcb_path:
        fps, segs, vias = load_board(pcb_path)
        all_pads = [p for ps in fps.values() for p in ps]
        board = (fps, segs, vias, all_pads)
    for r, ts in sorted(assign.items()):
        for tref, tpin in ts:
            tnet = comps[tref]["pins"][tpin]["net"]
            row = {"cap": r, "decouples": f"{tref}:{tpin}", "net": short(tnet), "edge_mm": None, "centre_mm": None,
                   "path": "-", "nearest": "-", "gnd_via_mm": None}
            mine = [f for f in findings if f["cap"] == r and f["target"] == f"{tref}:{tpin}"]
            if board and not mine:
                fps, segs, vias, all_pads = board
                tp = next((p for p in fps.get(tref, []) if p.num == tpin), None)
                if tp is None:
                    add("D2", "blocker", r, f"{tref}:{tpin}", f"{tref} pad {tpin} not on the board (update PCB from schematic)")
                elif r not in fps:
                    add("D2", "blocker", r, f"{tref}:{tpin}", f"{r} not on the board (update PCB from schematic)")
                else:
                    cp = [p for p in fps[r] if p.net == tp.net]
                    ret = [p for p in fps[r] if p.net != tp.net]
                    if not cp:
                        add("D2", "blocker", r, f"{tref}:{tpin}", f"board: {r} has no pad on {short(tp.net)} "
                            f"(pad nets differ from the netlist; update PCB from schematic)")
                    else:
                        c = min(cp, key=lambda p: pad_dist(p, tp))
                        d = pad_dist(c, tp)
                        row["edge_mm"] = round(d, 2)
                        row["centre_mm"] = round(math.hypot(c.cx - tp.cx, c.cy - tp.cy), 2)
                        if d > max_dist + 1e-9:
                            add("D4", "major", r, f"{tref}:{tpin}", f"{r} pad {c.num} is {d:.2f} mm (edge) from "
                                f"{tref}.{tpin}, limit {max_dist:g} mm")
                        path = track_path(tp, c, all_pads, segs, vias)
                        row["path"] = path
                        if path != "track":
                            how = ("every track route from the pin passes a via first" if path == "via"
                                   else "no track connects pin and cap (zone only or unrouted)")
                            add("D5", "blocker", r, f"{tref}:{tpin}", f"cap feeds the pin through the plane: {how}")
                        others = [(pad_dist(p, tp), p.ref) for ref2, ps in fps.items()
                                  if (is_cap_ref.match(ref2) or ref2 in caps) for p in ps if p.net == tp.net]
                        if others:
                            nd, nref = min(others)
                            row["nearest"] = nref
                            mine_refs = {c2 for c2, ts2 in assign.items() if (tref, tpin) in ts2}
                            if nref not in mine_refs and nd < d - 1e-6:
                                add("D6", "major", r, f"{tref}:{tpin}", f"nearest cap to {tref}.{tpin} is {nref} "
                                    f"({nd:.2f} mm), assigned {r} ({d:.2f} mm)")
                        if ret:
                            rp = ret[0]
                            vd = [max(0.0, poly_point_dist(rp.poly, v[0][0], v[0][1]) - v[1]) for v in vias if v[2] == rp.net]
                            gd = min(vd) if vd else None
                            row["gnd_via_mm"] = None if gd is None else round(gd, 2)
                            if gd is None or gd > gnd_via_dist + 1e-9:
                                add("D7", "minor", r, f"{tref}:{tpin}", f"no {short(rp.net)} via within {gnd_via_dist:g} mm "
                                    f"of {r} pad {rp.num}" + ("" if gd is None else f" (nearest {gd:.2f} mm)"))
            mine = [f for f in findings if f["cap"] == r and f["target"] == f"{tref}:{tpin}"]
            row["verdict"] = min((f["severity"] for f in mine), key=SEV_ORDER.get) if mine else "ok"
            rows.append(row)
    for r in sorted(bulk):
        rows.append({"cap": r, "decouples": "bulk", "net": ", ".join(sorted(short(n) for n in cap_nets(r))), "verdict": "ok"})
    findings.sort(key=lambda f: (SEV_ORDER[f["severity"]], f["check"], f["cap"], f["target"]))
    summary = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_ORDER}
    summary.update({"caps": len(caps), "assigned": len(assign), "bulk": len(bulk), "supply_pins": len(supply),
                    "board": bool(pcb_path), "no_field_anywhere": not assign and not bulk})
    return rows, findings, summary


def fmt(v):
    return "-" if v is None else f"{v:.2f}"


def report(rows, findings, summary, max_dist):
    if summary["no_field_anywhere"]:
        print("note: no capacitor carries a Decouples field — the assignment cannot be checked; "
              "every cap on a supply net is listed as unassigned (reduced coverage)")
    print(f"{'Cap':<6}{'Decouples':<12}{'Net':<12}{'Edge/ctr mm':<14}{'Path':<7}{'Nearest':<9}{'GND via':<9}Verdict")
    for r in rows:
        dist = "-" if r.get("edge_mm") is None else f"{fmt(r['edge_mm'])}/{fmt(r['centre_mm'])}"
        print(f"{r['cap']:<6}{r['decouples']:<12}{r['net'][:11]:<12}{dist:<14}{r.get('path', '-'):<7}"
              f"{r.get('nearest', '-'):<9}{fmt(r.get('gnd_via_mm')):<9}{r['verdict']}")
    if not summary["board"]:
        print("(no board given: D4-D7 layout checks not run)")
    if findings:
        print("\nFindings:")
        for f in findings:
            who = f["cap"] if f["target"] == "-" else (f["target"] if f["cap"] == "-" else f"{f['cap']} -> {f['target']}")
            print(f"  {f['check']} {f['severity']:<8}{who}: {f['message']}")
    print(f"\n{summary['caps']} caps, {summary['assigned']} assigned, {summary['bulk']} bulk, {summary['supply_pins']} supply pins; "
          f"blocker {summary['blocker']}, major {summary['major']}, minor {summary['minor']}  (max-dist {max_dist:g} mm)")

# ---------------------------------------------------------------- self-test fixtures

NETLIST = """(export (version "E")
 (components
  (comp (ref "U1") (value "MCU") (footprint "lib:QFN"))
  (comp (ref "U2") (value "LDO") (footprint "lib:SOT-23-5"))
  (comp (ref "U3") (value "SENSOR") (footprint "lib:SOT-23-5"))
  (comp (ref "C1") (value "100n") (footprint "lib:C_0402")
   (property (name "Decouples") (value "{C1}")))
  (comp (ref "C2") (value "100n") (footprint "lib:C_0402")
   (fields (field (name "Footprint") "lib:C_0402") (field (name "Decouples") "{C2}")))
  (comp (ref "C3") (value "10u") (footprint "lib:C_0805")
   (property (name "Decouples") (value "bulk")))
  (comp (ref "C4") (value "100n") (footprint "lib:C_0402")
   (property (name "Decouples") (value "U2:1")))
  (comp (ref "C5") (value "100n") (footprint "lib:C_0402")
   (property (name "Decouples") (value "U3:1")))
  {EXTRA})
 (nets
  (net (code "1") (name "/VDD") (node (ref "U1") (pin "1") (pinfunction "VDD") (pintype "power_in"))
   (node (ref "U1") (pin "3") (pinfunction "VDD") (pintype "power_in"))
   (node (ref "C1") (pin "1")) (node (ref "C2") (pin "1")) (node (ref "C3") (pin "1")) {EXTRA_VDD})
  (net (code "2") (name "GND") (node (ref "U1") (pin "2") (pinfunction "GND") (pintype "power_in"))
   (node (ref "U2") (pin "2") (pinfunction "GND") (pintype "power_in"))
   (node (ref "U3") (pin "2") (pinfunction "GND") (pintype "power_in"))
   (node (ref "C1") (pin "2")) (node (ref "C2") (pin "2")) (node (ref "C3") (pin "2"))
   (node (ref "C4") (pin "2")) (node (ref "C5") (pin "2")) {EXTRA_GND})
  (net (code "3") (name "/SIG") (node (ref "U1") (pin "4") (pinfunction "PA0") (pintype "bidirectional")) {EXTRA_SIG})
  (net (code "4") (name "/VIN") (node (ref "U2") (pin "1") (pinfunction "VIN") (pintype "power_in")) (node (ref "C4") (pin "1")))
  (net (code "5") (name "/VS") (node (ref "U3") (pin "1") (pinfunction "VDD") (pintype "power_in")) (node (ref "C5") (pin "1")))))
"""


def cap0402(ref, x, y, rotd, n1, n2):
    return (f' (footprint "C_0402" (layer "F.Cu") (at {x} {y} {rotd})\n  (property "Reference" "{ref}")\n'
            f'  (pad "1" smd roundrect (at -0.5 0 {rotd}) (size 0.6 0.6) (layers "F.Cu" "F.Mask" "F.Paste") (net "{n1}"))\n'
            f'  (pad "2" smd roundrect (at 0.5 0 {rotd}) (size 0.6 0.6) (layers "F.Cu" "F.Mask" "F.Paste") (net "{n2}")))\n')


def ic(ref, x, y, pins):
    s = f' (footprint "IC" (layer "F.Cu") (at {x} {y})\n  (property "Reference" "{ref}")\n'
    for num, px, py, net in pins:
        s += f'  (pad "{num}" smd rect (at {px} {py}) (size 1.0 0.4) (layers "F.Cu" "F.Mask") (net "{net}"))\n'
    return s + " )\n"


def seg(a, b, net, layer="F.Cu"):
    return f' (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.25) (layer "{layer}") (net "{net}"))\n'


def via(p, net):
    return f' (via (at {p[0]} {p[1]}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "{net}"))\n'


def fixtures(clean):
    """Clean: every cap at its pin, track pin -> cap pad, GND via at the return pad.
    Planted: C1/C2 assignment swapped, C4 reached only through a via, C5 zone-fed without
    GND via, C6 unassigned on VDD, C7 assigned to a signal pin, U1.5 (second VDD pin) without a cap."""
    c1, c2 = ("U1:1", "U1:3") if clean else ("U1:3", "U1:1")
    extra = extra_vdd = extra_gnd = extra_sig = ""
    if not clean:
        extra = ('(comp (ref "C6") (value "1u") (footprint "lib:C_0402"))\n'
                 '  (comp (ref "C7") (value "100n") (footprint "lib:C_0402") (property (name "Decouples") (value "U1:4")))')
        extra_vdd = ('(node (ref "C6") (pin "1")) (node (ref "C7") (pin "1")) '
                     '(node (ref "U1") (pin "5") (pinfunction "VDD") (pintype "power_in"))')
        extra_gnd = '(node (ref "C6") (pin "2")) (node (ref "C7") (pin "2"))'
    net = (NETLIST.replace("{C1}", c1).replace("{C2}", c2).replace("{EXTRA}", extra)
           .replace("{EXTRA_VDD}", extra_vdd).replace("{EXTRA_GND}", extra_gnd).replace("{EXTRA_SIG}", extra_sig))
    b = '(kicad_pcb (version 20251001)\n (net 0 "") (net 1 "/VDD") (net 2 "GND") (net 3 "/SIG") (net 4 "/VIN") (net 5 "/VS")\n'
    # U1: pin 1 at (19.5,10), pin 3 at (19.5,14) (left side), GND pin 2 at (19.5,12), SIG pin 4 at (22.5,12)
    b += ic("U1", 20, 12, [("1", -0.5, -2, "/VDD"), ("2", -0.5, 0, "GND"), ("3", -0.5, 2, "/VDD"), ("4", 2.5, 0, "/SIG")])
    b += cap0402("C1", 17.0, 10, 0, "GND", "/VDD")        # C1 pad 2 (VDD) at 17.5,10 -> 1.0 mm edge gap to U1.1
    b += seg((17.5, 10), (19.5, 10), "/VDD") + via((16.5, 10.9), "GND")
    b += f' (footprint "C_0402" (layer "F.Cu") (at 17.0 14 180)\n  (property "Reference" "C2")\n' \
         '  (pad "1" smd roundrect (at -0.5 0 180) (size 0.6 0.6) (layers "F.Cu" "F.Mask") (net 1))\n' \
         '  (pad "2" smd roundrect (at 0.5 0 180) (size 0.6 0.6) (layers "F.Cu" "F.Mask") (net 2 "GND")))\n'
    # C2 rotated 180: pad 1 (VDD) lands at 17.5,14; numbered-net form; both joins are T-joins onto a vertical bar
    b += seg((19.5, 14), (18.5, 14), "/VDD") + seg((18.5, 13), (18.5, 16), "/VDD") + seg((18.5, 15), (17.5, 14), "/VDD")
    b += via((16.5, 14.9), "GND")
    b += cap0402("C3", 30, 30, 0, "/VDD", "GND")          # bulk, far away
    b += ic("U2", 40, 12, [("1", -0.5, 0, "/VIN"), ("2", 0.5, 0, "GND")])
    b += cap0402("C4", 37.0, 12, 0, "GND", "/VIN") + via((36.5, 12.9), "GND")
    if clean:
        b += seg((37.5, 12), (39.5, 12), "/VIN")
    else:  # pin -> via -> track -> cap: the via comes first
        b += seg((39.5, 12), (38.5, 12), "/VIN") + via((38.5, 12), "/VIN") + seg((38.5, 12), (37.5, 12), "/VIN")
    b += ic("U3", 40, 20, [("1", -0.5, 0, "/VS"), ("2", 0.5, 0, "GND")])
    b += cap0402("C5", 37.0, 20, 0, "GND", "/VS")
    if clean:
        b += seg((37.5, 20), (39.5, 20), "/VS") + via((36.5, 20.9), "GND")
    else:  # no track: fed through the plane only, and no GND via at its return pad
        b += via((39.5, 21.0), "/VS") + via((37.5, 20.9), "/VS")
    if not clean:
        b += cap0402("C6", 10, 30, 0, "/VDD", "GND") + via((9.5, 30.9), "GND")
        b += cap0402("C7", 10, 40, 0, "/VDD", "GND") + via((9.5, 40.9), "GND")
    return net, b + ")\n"


def write_fixtures(d):
    os.makedirs(d, exist_ok=True)
    paths = {}
    for name, clean in (("clean", True), ("planted", False)):
        net, pcb = fixtures(clean)
        np_, bp = os.path.join(d, f"{name}.kicad_net"), os.path.join(d, f"{name}.kicad_pcb")
        open(np_, "w", encoding="utf-8").write(net)
        open(bp, "w", encoding="utf-8").write(pcb)
        paths[name] = (np_, bp)
    return paths


def self_test():
    paths = write_fixtures(tempfile.mkdtemp())
    rows, f, s = analyse(*paths["clean"])
    assert not f, f
    assert s["assigned"] == 4 and s["bulk"] == 1, s
    byc = {r["cap"]: r for r in rows}
    assert byc["C1"]["path"] == "track" and byc["C2"]["path"] == "track", rows   # C2: rotated, numbered net, T-join
    assert byc["C1"]["edge_mm"] == 1.2 and byc["C2"]["edge_mm"] == 1.2, rows
    rows, f, s = analyse(*paths["planted"])
    got = {(x["check"], x["cap"], x["target"]) for x in f}
    sev = {(x["check"], x["cap"], x["target"]): x["severity"] for x in f}
    need = [("D1", "C6", "-"), ("D2", "C7", "U1:4"), ("D4", "C1", "U1:3"), ("D5", "C1", "U1:3"), ("D6", "C1", "U1:3"),
            ("D6", "C2", "U1:1"), ("D5", "C4", "U2:1"), ("D5", "C5", "U3:1"), ("D7", "C5", "U3:1"), ("D3", "-", "U1:5")]
    for k in need:
        assert k in got, (k, sorted(got))
    assert sev[("D5", "C4", "U2:1")] == "blocker" and sev[("D7", "C5", "U3:1")] == "minor", sev
    assert not any(k[0] == "D3" and k[2] != "U1:5" for k in got), got   # signal pins, GND and covered pins stay out
    # netlist only (gate 4): D1/D2 still caught, no layout checks
    _, f2, s2 = analyse(paths["planted"][0])
    assert not s2["board"] and {"D1", "D2"} <= {x["check"] for x in f2} and not {"D4", "D5", "D6", "D7"} & {x["check"] for x in f2}
    print("self-test OK: clean variant passes (property and fields forms, rotated cap, numbered nets, T-join); "
          "planted variant flags unassigned C6, C7 on another net, uncovered U1.5, swapped C1/C2 (distance, plane path, "
          "nearest cap), via-first C4, zone-fed C5 without GND via")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    if "--write-fixtures" in argv:
        d = argv[argv.index("--write-fixtures") + 1]
        for name, (n, b) in write_fixtures(d).items():
            print(f"{name}: {n} {b}")
        return 0
    pos = []
    opts = {"--max-dist": 2.0, "--gnd-via-dist": 1.0, "--cap-refs": DEF_CAP, "--gnd-net": DEF_GND}
    i = 0
    while i < len(argv):
        if argv[i] in opts and i + 1 < len(argv):
            opts[argv[i]] = argv[i + 1] if argv[i] in ("--cap-refs", "--gnd-net") else float(argv[i + 1])
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            pos.append(argv[i]); i += 1
    if not pos:
        print(__doc__)
        return 2
    rows, findings, summary = analyse(pos[0], pos[1] if len(pos) > 1 else None, opts["--max-dist"],
                                      opts["--gnd-via-dist"], opts["--cap-refs"], opts["--gnd-net"])
    if "--json" in argv:
        print(json.dumps({"rows": rows, "findings": findings, "summary": summary}, indent=1))
    else:
        report(rows, findings, summary, opts["--max-dist"])
    return 1 if summary["blocker"] or summary["major"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

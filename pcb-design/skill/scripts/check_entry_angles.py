#!/usr/bin/env python3
"""Lint: traces must leave pads cleanly — outward, along the pad, turning
only outside the pad. Pure-text .kicad_pcb parser, no pcbnew. KiCad 9/10.

Rules (each with a positive self-test case built from a real miss):
  R1  two-pin parts: the exit points OUTWARD (away from the other pad),
      <= 45 deg off the pad axis. Backwards exits are never axial.
  R2  multi-pin parts (ICs, connectors): the exit runs along the pad's
      long axis, outward from the footprint centre, <= 15 deg, GND included.
      Exception: an end-of-row pad may exit straight out of its free side.
      Square/round pads have no long axis and are exempt from R2.
  R3  no bend inside a pad (a segment with both ends inside a pad);
      round pads (test points, THT) are entered on a line through the
      centre. The exit is evaluated on the segment crossing the pad
      outline, never on "the first segment >= x mm".

Usage:
  check_entry_angles.py <board.kicad_pcb> [--two-pin-max 45] [--ic-max 15]
        [--ignore-refs REGEX] [--ignore-net REGEX] [--strict] [--self-test]

Exit code 0 (the list is reviewed at the layout gate with justifications);
--strict exits 1 on any finding.
"""
import math
import re
import sys

EPS = 1e-6

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


def nums(lst, n):
    return [float(x) for x in lst[1:1 + n]]


def net_key(netnode):
    """KiCad <=9: (net 3 "GND"); KiCad 10: (net "GND"). Return the name if
    present, else the number as string, else '' ."""
    if not netnode or len(netnode) < 2:
        return ""
    if len(netnode) >= 3:
        return str(netnode[2])
    v = netnode[1]
    return str(v)

# ---------------------------------------------------------------- geometry

def rot(px, py, deg):
    t = math.radians(deg)
    return px * math.cos(t) + py * math.sin(t), -px * math.sin(t) + py * math.cos(t)


def ang_between(ax, ay, bx, by):
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    if la == 0 or lb == 0:
        return 0.0
    c = (ax * bx + ay * by) / (la * lb)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


class Pad:
    def __init__(self, num, cx, cy, w, h, deg, shape, net, layers):
        self.num, self.cx, self.cy, self.w, self.h = num, cx, cy, w, h
        self.deg, self.shape, self.net, self.layers = deg, shape, net, layers
        self.round = shape == "circle" or (shape == "oval" and abs(w - h) < 1e-6)
        self.r = max(w, h) / 2.0
        self.aspect = max(w, h) / max(min(w, h), 1e-9)

    def inside(self, x, y, margin=0.0):
        u, v = rot(x - self.cx, y - self.cy, -self.deg)
        if self.round:
            return math.hypot(u, v) <= self.r + margin
        return abs(u) <= self.w / 2 + margin and abs(v) <= self.h / 2 + margin

    def long_axis(self):
        """Unit vector of the long axis in board coords, or None."""
        if self.round or self.aspect < 1.3:
            return None
        if self.w >= self.h:
            return rot(1.0, 0.0, self.deg)
        return rot(0.0, 1.0, self.deg)

    def on_layer(self, layer):
        if not self.layers or not layer:
            return True
        return any(l == layer or l.startswith("*") for l in self.layers)

# ---------------------------------------------------------------- analysis

def load(tree):
    segs = []
    for s in children(tree, "segment"):
        st, en, net, layer = child(s, "start"), child(s, "end"), child(s, "net"), child(s, "layer")
        if not (st and en):
            continue
        segs.append((tuple(nums(st, 2)), tuple(nums(en, 2)), net_key(net), layer[1] if layer else ""))
    nets = {}
    for n in children(tree, "net"):
        if len(n) >= 3:
            nets[str(n[1])] = str(n[2])
    fps = []
    for fp in children(tree, "footprint"):
        ref = ""
        for p in children(fp, "property"):
            if len(p) > 2 and p[1] == "Reference":
                ref = p[2]
        at = child(fp, "at")
        if not (ref and at):
            continue
        fx, fy = nums(at, 2)
        frot = float(at[3]) if len(at) > 3 else 0.0
        pads = []
        for p in children(fp, "pad"):
            num = str(p[1]) if len(p) > 1 else ""
            if num == "":          # paste aperture / NPTH peg: not a pin (S-7)
                continue
            pat, psz = child(p, "at"), child(p, "size")
            if not (pat and psz):
                continue
            px, py = nums(pat, 2)
            pdeg = float(pat[3]) if len(pat) > 3 else frot
            dx, dy = rot(px, py, frot)
            w, h = nums(psz, 2)
            shape = p[3] if len(p) > 3 else "rect"
            lay = child(p, "layers")
            net = net_key(child(p, "net"))
            pads.append(Pad(num, fx + dx, fy + dy, w, h, pdeg, shape, net, set(lay[1:]) if lay else set()))
        if pads:
            fps.append((ref, fx, fy, pads))
    return segs, nets, fps


def same_net(a, b, nets):
    if a == b:
        return True
    return nets.get(a, a) == nets.get(b, b)


def analyse(tree, two_pin_max=45.0, ic_max=15.0, ignore_refs=r"^(H|MH|FID)\d*$", ignore_net=None):
    segs, nets, fps = load(tree)
    skip = re.compile(ignore_refs)
    ign = re.compile(ignore_net, re.I) if ignore_net else None
    findings = []
    checked = 0
    for ref, fx, fy, pads in fps:
        if skip.match(ref):
            continue
        checked += 1
        two_pin = len(pads) == 2
        for pad in pads:
            netname = nets.get(pad.net, pad.net)
            if ign and ign.search(netname):
                continue
            exits = []
            for (sx, sy), (ex, ey), snet, slayer in segs:
                if not same_net(snet, pad.net, nets) or not pad.on_layer(slayer):
                    continue
                si, ei = pad.inside(sx, sy), pad.inside(ex, ey)
                if si and ei:
                    if math.hypot(ex - sx, ey - sy) > 1e-4:
                        findings.append(("R3", ref, pad.num, netname, "bend/jog inside pad", 0.0))
                    continue
                if si:
                    exits.append(((sx, sy), (ex - sx, ey - sy)))
                elif ei:
                    exits.append(((ex, ey), (sx - ex, sy - ey)))
            for (ix, iy), (vx, vy) in exits:
                # R3b: round pads entered through the centre
                if pad.round:
                    lv = math.hypot(vx, vy)
                    if lv > 0:
                        d = abs((pad.cx - ix) * vy - (pad.cy - iy) * vx) / lv
                        if d > max(0.05, 0.1 * pad.r):
                            findings.append(("R3", ref, pad.num, netname,
                                             f"round pad not entered through centre (offset {d:.2f} mm)", d))
                if two_pin:
                    other = pads[0] if pads[1] is pad else pads[1]
                    ox, oy = pad.cx - other.cx, pad.cy - other.cy
                    a = ang_between(ox, oy, vx, vy)
                    if a > two_pin_max + EPS:
                        tag = "backwards" if a > 90 else "off-axis"
                        findings.append(("R1", ref, pad.num, netname, f"{tag} exit {a:.1f} deg", a))
                else:
                    axis = pad.long_axis()
                    if axis is None:
                        continue
                    ax, ay = axis
                    # outward along the long axis = away from footprint centre
                    if (pad.cx - fx) * ax + (pad.cy - fy) * ay < 0:
                        ax, ay = -ax, -ay
                    a = ang_between(ax, ay, vx, vy)
                    if a <= ic_max + EPS:
                        continue
                    # exception: end-of-row pad exiting straight out of its free side
                    px_, py_ = -ay, ax
                    has_plus = has_minus = False
                    for q in pads:
                        if q is pad:
                            continue
                        dx, dy = q.cx - pad.cx, q.cy - pad.cy
                        along, across = dx * ax + dy * ay, dx * px_ + dy * py_
                        if abs(along) <= max(pad.w, pad.h) / 2 and 0 < abs(across) <= 3.0:
                            if across > 0:
                                has_plus = True
                            else:
                                has_minus = True
                    free_ok = False
                    if not has_plus and ang_between(px_, py_, vx, vy) <= ic_max + EPS:
                        free_ok = True
                    if not has_minus and ang_between(-px_, -py_, vx, vy) <= ic_max + EPS:
                        free_ok = True
                    if not free_ok:
                        findings.append(("R2", ref, pad.num, netname,
                                         f"pin exit {a:.1f} deg off the pad axis (turn outside the pad)", a))
    findings.sort(key=lambda f: (f[0], -f[5]))
    return checked, findings


def report(checked, findings):
    print(f"footprints checked: {checked}; findings: {len(findings)}")
    if findings:
        print(f"{'Rule':<5}{'Ref':<7}{'Pad':<5}{'Net':<18}Detail")
        for rule, ref, pad, net, detail, _ in findings:
            print(f"{rule:<5}{ref:<7}{pad:<5}{net[:17]:<18}{detail}")
        print("\nReview at the layout gate: rotate, re-route, or justify in docs/design-notes.md.")

# ---------------------------------------------------------------- self-test

SELFTEST = """(kicad_pcb (version 20251001)
 (net 0 "") (net 1 "SIG_A") (net 2 "SIG_B") (net 3 "GND") (net 4 "VCC") (net 5 "TPN")
 (footprint "R_0603" (layer "F.Cu") (at 10 10 0)
  (property "Reference" "R11")
  (pad "" smd rect (at 0 0) (size 0.4 0.4) (layers "F.Paste"))
  (pad "1" smd roundrect (at -0.8 0) (size 0.9 1.0) (layers "F.Cu") (net "SIG_A"))
  (pad "2" smd roundrect (at 0.8 0) (size 0.9 1.0) (layers "F.Cu") (net "SIG_B")))
 (segment (start 9.2 10) (end 5 10) (width 0.2) (layer "F.Cu") (net "SIG_A"))
 (segment (start 10.8 10) (end 9.8 9) (width 0.2) (layer "F.Cu") (net "SIG_B"))
 (footprint "R_0603" (layer "F.Cu") (at 30 10 0)
  (property "Reference" "R12")
  (pad "1" smd roundrect (at -0.8 0) (size 0.9 1.0) (layers "F.Cu") (net 1 "SIG_A"))
  (pad "2" smd roundrect (at 0.8 0) (size 0.9 1.0) (layers "F.Cu") (net 2 "SIG_B")))
 (segment (start 30.8 10) (end 31.8 9) (width 0.2) (layer "F.Cu") (net 2))
 (footprint "TSSOP-4" (layer "F.Cu") (at 20 20 0)
  (property "Reference" "U3")
  (pad "1" smd roundrect (at -2.9 -0.975) (size 1.5 0.45) (layers "F.Cu") (net 3 "GND"))
  (pad "2" smd roundrect (at -2.9 -0.325) (size 1.5 0.45) (layers "F.Cu") (net 4 "VCC"))
  (pad "3" smd roundrect (at -2.9 0.325) (size 1.5 0.45) (layers "F.Cu") (net 1 "SIG_A"))
  (pad "4" smd roundrect (at -2.9 0.975) (size 1.5 0.45) (layers "F.Cu") (net 2 "SIG_B")))
 (segment (start 17.1 19.025) (end 15.5 17.5) (width 0.2) (layer "F.Cu") (net 3))
 (segment (start 17.1 19.675) (end 15 19.675) (width 0.2) (layer "F.Cu") (net 4))
 (segment (start 17.1 20.975) (end 17.1 23) (width 0.2) (layer "F.Cu") (net 2))
 (segment (start 17.1 20.325) (end 17.1 22) (width 0.2) (layer "F.Cu") (net 1))
 (footprint "TestPoint" (layer "F.Cu") (at 40 40 0)
  (property "Reference" "TP2")
  (pad "1" smd circle (at 0 0) (size 1.5 1.5) (layers "F.Cu") (net 5 "TPN")))
 (segment (start 40 40) (end 40.4 40.4) (width 0.2) (layer "F.Cu") (net 5))
 (segment (start 40.4 40.4) (end 43 40.4) (width 0.2) (layer "F.Cu") (net 5))
 (footprint "TestPoint" (layer "F.Cu") (at 50 40 0)
  (property "Reference" "TP3")
  (pad "1" smd circle (at 0 0) (size 1.5 1.5) (layers "F.Cu") (net 5 "TPN")))
 (segment (start 50 40) (end 53 40) (width 0.2) (layer "F.Cu") (net 5))
 (footprint "TestPoint" (layer "F.Cu") (at 60 40 0)
  (property "Reference" "TP4")
  (pad "1" smd circle (at 0 0) (size 1.5 1.5) (layers "F.Cu") (net 5 "TPN")))
 (segment (start 60.3 40.6) (end 63 40.6) (width 0.2) (layer "F.Cu") (net 5))
)"""


def self_test():
    checked, f = analyse(parse(SELFTEST))
    got = {(r, ref, pad) for r, ref, pad, *_ in f}
    # R11: KiCad-10 string nets, unnumbered paste pad ignored (S-1, S-7);
    # pad 1 exits straight (ok), pad 2 exits 45 deg BACKWARDS over the body (S-14) -> R1
    assert ("R1", "R11", "2") in got, f
    assert ("R1", "R11", "1") not in got, f
    # R12: exactly 45 deg outward -> allowed (S-2)
    assert not any(ref == "R12" for _, ref, *_ in f), f
    # U3: GND pin leaves diagonally -> R2 (S-15); VCC axial ok; pad 4 end-of-row free side ok;
    # pad 3 inner pin sideways -> R2
    assert ("R2", "U3", "1") in got, f
    assert ("R2", "U3", "2") not in got, f
    assert ("R2", "U3", "4") not in got, f
    assert ("R2", "U3", "3") in got, f
    # TP2: jog inside the pad -> R3 (S-16); TP3 straight through centre ok; TP4 off-centre -> R3
    assert ("R3", "TP2", "1") in got, f
    assert not any(ref == "TP3" for _, ref, *_ in f), f
    assert ("R3", "TP4", "1") in got, f
    print(f"self-test OK ({checked} footprints): R1 backwards (R11), R2 diagonal GND / inner sideways (U3), "
          "R3 in-pad jog + off-centre (TP2/TP4) flagged; exact 45 deg, axial, end-of-row free side, through-centre clean")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    opts = {"--two-pin-max": 45.0, "--ic-max": 15.0, "--ignore-refs": r"^(H|MH|FID)\d*$", "--ignore-net": None}
    for k in list(opts):
        if k in argv:
            v = argv[argv.index(k) + 1]
            opts[k] = v if k in ("--ignore-refs", "--ignore-net") else float(v)
    with open(argv[0], encoding="utf-8") as fh:
        tree = parse(fh.read())
    checked, findings = analyse(tree, opts["--two-pin-max"], opts["--ic-max"], opts["--ignore-refs"], opts["--ignore-net"])
    report(checked, findings)
    return 1 if ("--strict" in argv and findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

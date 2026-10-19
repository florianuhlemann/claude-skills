#!/usr/bin/env python3
# Purpose: gate-4 audit (pcb-audit) — check the exported KiCad netlist pin by pin against datasheet-derived
#          expectations, then run the project's own value checks (dividers, thresholds, power, structure)
#          on the resistor values that are actually IN the netlist. Framework promoted from two boards;
#          the expectations and checks are per project and are written independently of any generator.
# Usage:   kicad-cli sch export netlist -o build/net.kicad_net hardware/<board>.kicad_sch
#          python3 audit_netlist.py build/net.kicad_net [--expect docs/netlist-expect.json]
#                                           [--checks scripts/netlist_checks.py] [--corrupt] [--self-test]
#          docs/netlist-expect.json:  {"U1": {"1": "BST", "2": "VBAT", ...}, "Q1": {"4": "GATE_Q1"}, ...}
#                                     (pin -> net name; hierarchical prefixes are stripped)
#          scripts/netlist_checks.py: def checks(comps, pins, fps, chk, two_terminal, rval): ...
#                                     chk(cond, "message") records ok/FAIL; comps ref->value,
#                                     pins (ref, pin)->net, fps ref->footprint
# Pitfalls: --self-test corrupts one expected connection and must FAIL (negative control); if the project
#           checks module exists it is also run against the corrupted netlist and must flag something, so a
#           checks file that tests nothing is caught too.
import importlib.util
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import find, first, parse  # noqa: E402


def load(path):
    text = open(path, encoding="utf-8").read()
    t = parse(text)
    comps, pins, fps = {}, {}, {}
    for c in find(first(t, "components"), "comp"):
        ref = first(c, "ref")[1]
        comps[ref] = first(c, "value")[1]
        fp = first(c, "footprint")
        fps[ref] = fp[1] if fp else ""
    for n in find(first(t, "nets"), "net"):
        name = first(n, "name")[1].split("/")[-1]
        for nd in find(n, "node"):
            pins[(first(nd, "ref")[1], first(nd, "pin")[1])] = name
    return comps, pins, fps


def rval(v):
    """'4k7' / '4.7k' / '10R' / '0.1' -> ohms (also works for F/H strings)."""
    v = v.strip().replace("Ω", "").replace("ohm", "")
    v = re.sub(r"^(\d+)([kKmMR])(\d+)$", lambda m: f"{m.group(1)}.{m.group(3)}{m.group(2)}", v)
    v = v.rstrip("RrFfHh")
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6}
    for k, m in mult.items():
        if v.endswith(k):
            return float(v[:-1]) * m
    return float(v)


def two_terminal(pins, net_a, net_b, prefix=None):
    """Refs of two-pin parts bridging net_a and net_b (pins 1/2 in either order)."""
    out = []
    refs = {r for (r, p) in pins}
    for r in refs:
        if prefix and not r.startswith(prefix):
            continue
        a, b = pins.get((r, "1")), pins.get((r, "2"))
        if {a, b} == {net_a, net_b} and len({k for k in pins if k[0] == r}) == 2:
            out.append(r)
    return sorted(out)


def run(comps, pins, fps, expect, checks_path):
    fails, notes = [], []

    def chk(cond, msg):
        (notes if cond else fails).append(("ok   " if cond else "FAIL ") + msg)

    for ref, pinmap in expect.items():
        for pin, net in pinmap.items():
            actual = pins.get((ref, pin))
            chk(actual == net, f"{ref}.{pin} = {net} (netlist: {actual})")
    if checks_path and os.path.exists(checks_path):
        spec = importlib.util.spec_from_file_location("netlist_checks", checks_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.checks(comps, pins, fps, chk, two_terminal, rval)
    return fails, notes


NET_FIXTURE = """(export (version "E")
 (components
  (comp (ref "U1") (value "LM358") (footprint "lib:SOIC-8"))
  (comp (ref "R1") (value "4k7") (footprint "lib:R_0603"))
  (comp (ref "R2") (value "10k") (footprint "lib:R_0603")))
 (nets
  (net (code "1") (name "/pwr/VCC") (node (ref "U1") (pin "8")) (node (ref "R1") (pin "1")))
  (net (code "2") (name "GND") (node (ref "U1") (pin "4")) (node (ref "R2") (pin "2")))
  (net (code "3") (name "MID") (node (ref "R1") (pin "2")) (node (ref "R2") (pin "1")) (node (ref "U1") (pin "3")))))
"""


def self_test():
    import json
    import tempfile
    d = tempfile.mkdtemp()
    nl = os.path.join(d, "net.xml"); open(nl, "w").write(NET_FIXTURE)
    comps, pins, fps = load(nl)
    import math
    assert rval("4k7") == 4700 and rval("10k") == 10000 and rval("0.1") == 0.1 and math.isclose(rval("100n"), 1e-7)
    assert two_terminal(pins, "VCC", "MID") == ["R1"] and two_terminal(pins, "MID", "GND") == ["R2"]
    expect = {"U1": {"8": "VCC", "4": "GND", "3": "MID"}}
    ck = os.path.join(d, "checks.py")
    open(ck, "w").write(
        "def checks(comps, pins, fps, chk, two_terminal, rval):\n"
        "    t = rval(comps[two_terminal(pins, 'VCC', 'MID')[0]]); b = rval(comps[two_terminal(pins, 'MID', 'GND')[0]])\n"
        "    chk(abs(b / (t + b) - 0.68) < 0.01, f'divider ratio {b/(t+b):.3f} = 0.68')\n")
    fails, notes = run(comps, pins, fps, expect, ck)
    assert not fails and len(notes) == 4, (fails, notes)
    # negative controls: a swapped pin and a wrong value must both FAIL
    bad = dict(pins); bad[("U1", "3")] = "GND"
    f1, _ = run(comps, bad, fps, expect, ck)
    assert any("U1.3" in f for f in f1), f1
    badc = dict(comps); badc["R1"] = "47k"
    f2, _ = run(badc, pins, fps, expect, ck)
    assert any("divider" in f for f in f2), f2
    print("self-test OK: 4 checks pass on the fixture; swapped U1.3 and a wrong R1 are both caught")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    if not argv or argv[0].startswith("-"):
        print(open(__file__).read().split("import importlib")[0])
        return 2
    import json
    net = argv[0]
    exp_path = argv[argv.index("--expect") + 1] if "--expect" in argv else "docs/netlist-expect.json"
    ck_path = argv[argv.index("--checks") + 1] if "--checks" in argv else "scripts/netlist_checks.py"
    comps, pins, fps = load(net)
    expect = json.load(open(exp_path, encoding="utf-8")) if os.path.exists(exp_path) else {}
    if not expect:
        print(f"note: no expectations at {exp_path} — only project checks run; write the pin map from docs/parts/")
    fails, notes = run(comps, pins, fps, expect, ck_path)
    for n in notes + fails:
        print(n)
    print(f"\n{len(notes)} ok, {len(fails)} FAIL  ({len(expect)} parts expected, "
          f"{'checks: ' + ck_path if os.path.exists(ck_path) else 'no project checks module'})")
    if "--corrupt" in argv:   # negative control on the real project: swap one expected pin, must FAIL
        ref, pinmap = next(iter(expect.items())); pin = next(iter(pinmap))
        bad = dict(pins); bad[(ref, pin)] = "__CORRUPT__"
        f, _ = run(comps, bad, fps, expect, ck_path)
        print("negative control:", "PASS (corruption detected)" if f else "FAIL (verifier blind)")
        return 0 if f else 1
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

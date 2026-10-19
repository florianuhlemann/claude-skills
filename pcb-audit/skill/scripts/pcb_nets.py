#!/usr/bin/env python3
"""Pad -> net map read from the board file, and its parity with the schematic's netlist export.

Tier A substitute for DRC schematic parity, and the netlist to audit when the project ships none:
the board is the artefact that gets built.

Usage:
  pcb_nets.py <board.kicad_pcb> [--json]                      REF.PAD  net  pinfunction  pintype
  pcb_nets.py <board.kicad_pcb> --netlist build/net.kicad_net  parity: exit 1 on any difference
  pcb_nets.py <board.kicad_pcb> --write-net build/pcb.kicad_net
        writes a netlist in the kicad-cli S-expression form (comps with value, footprint and every
        footprint property, Decouples included; nets with pinfunction/pintype from the pads), so
        audit_netlist.py and check_decoupling.py run on the board unchanged:
          audit_netlist.py build/pcb.kicad_net --corrupt
          check_decoupling.py build/pcb.kicad_net hardware/<board>.kicad_pcb
  pcb_nets.py --self-test

Parity classes (each one a difference, exit 1):
  missing footprint  netlist component not on the board
  missing pad        netlist pin with no pad of that number on the board
  extra pad          board pad on a net, pin not in the netlist
  net differs        same pin, different net (after a whole-net rename is taken out)
  renamed net        a board net and a netlist net with exactly the same pins, different names
  pad on two nets    pads sharing one number sit on different nets
  value / footprint  footprint Value or library id differs from the netlist component
Listed, not counted: board-only footprints without netted pads (mounting holes, logos), duplicate
refs. Single-pin "unconnected-(...)" nets equal an unnetted pad.
Pitfalls: a board that was not updated from the schematic shows up here, not in DRC run on the
board alone; without a netlist export this cannot prove schematic = board, only audit the board.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_board import load as load_pcb  # noqa: E402
from sexpr import find, first, parse  # noqa: E402


def norm(net):
    return None if not net or net.startswith("unconnected-") else net


def board_map(b):
    """{(ref, pin): net} plus pads-on-two-nets and per-footprint info."""
    pins, two, info = {}, [], {}
    for f in b.footprints:
        if not f.ref:
            continue
        info[f.ref] = f
        by_num = {}
        for p in f.pads:
            if p.num == "" or not p.copper:
                continue
            by_num.setdefault(p.num, set()).add(p.net or "")
        for num, nets in by_num.items():
            real = {n for n in nets if norm(n)}
            if len(real) > 1:
                two.append((f.ref, num, sorted(real)))
            pins[(f.ref, num)] = sorted(real)[0] if real else None
    return pins, two, info


def netlist_map(path):
    t = parse(open(path, encoding="utf-8").read())
    comps = {}
    for c in find(first(t, "components") or [], "comp"):
        ref = str(first(c, "ref")[1])
        v, fp = first(c, "value"), first(c, "footprint")
        comps[ref] = (str(v[1]) if v and len(v) > 1 else "", str(fp[1]) if fp and len(fp) > 1 else "")
    pins = {}
    for n in find(first(t, "nets") or [], "net"):
        name = str(first(n, "name")[1])
        nodes = find(n, "node")
        for nd in nodes:
            key = (str(first(nd, "ref")[1]), str(first(nd, "pin")[1]))
            pins[key] = None if len(nodes) == 1 and name.startswith("unconnected-") else norm(name)
    return comps, pins


def parity(b, net_path):
    bpins, two, info = board_map(b)
    comps, npins = netlist_map(net_path)
    diffs, notes = [], []
    for ref in sorted(set(comps) - set(info)):
        diffs.append(("missing footprint", ref, "netlist component not on the board"))
    for ref in sorted(set(info) - set(comps)):
        netted = sorted(f"{ref}.{p}" for (r, p), n in bpins.items() if r == ref and n)
        if netted:
            for name in netted:
                diffs.append(("extra pad", name, f"on {bpins[tuple(name.split('.', 1))]}, footprint not in the netlist"))
        else:
            notes.append(f"board-only footprint {ref} (no netted pads)")
    for ref in sorted(set(comps) & set(info)):
        nv, nf = comps[ref]
        f = info[ref]
        if nv and f.value and nv != f.value:
            diffs.append(("value differs", ref, f"board {f.value}, netlist {nv}"))
        if nf and f.lib and nf != f.lib:
            diffs.append(("footprint differs", ref, f"board {f.lib}, netlist {nf}"))
    for ref, num, nets in two:
        diffs.append(("pad on two nets", f"{ref}.{num}", ", ".join(nets)))
    # whole-net renames: same member set, different name
    bnets, nnets = {}, {}
    for k, n in bpins.items():
        if n and k[0] in comps:
            bnets.setdefault(n, set()).add(k)
    for k, n in npins.items():
        if n and k[0] in info:
            nnets.setdefault(n, set()).add(k)
    renamed = {}
    for bn, members in bnets.items():
        for nn, nmem in nnets.items():
            if bn != nn and members == nmem:
                renamed[bn] = nn
                diffs.append(("renamed net", bn, f"netlist name {nn}, {len(members)} pads"))
    for key in sorted(set(npins) | set(k for k in bpins if k[0] in comps)):
        if key[0] not in info:
            continue
        name = f"{key[0]}.{key[1]}"
        if key not in bpins:
            diffs.append(("missing pad", name, f"netlist {npins[key] or 'unconnected'}, no such pad on the board"))
        elif key not in npins:
            if bpins[key]:
                diffs.append(("extra pad", name, f"on {bpins[key]}, pin not in the netlist"))
        elif bpins[key] != npins[key] and renamed.get(bpins[key]) != npins[key]:
            diffs.append(("net differs", name, f"board {bpins[key] or 'unconnected'}, netlist {npins[key] or 'unconnected'}"))
    for r in b.duplicate_refs:
        notes.append(f"duplicate ref {r} on the board")
    return diffs, notes


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_net(b, out):
    lines = ['(export (version "E")', f' (design (source {q(os.path.basename(b.path))}) '
             '(tool "pcb_nets.py (pcb-audit): pad nets read from the board file"))', " (components"]
    for f in b.footprints:
        if not f.ref or "board_only" in f.attrs:
            continue
        props = "".join(f"\n   (property (name {q(k)}) (value {q(v)}))" for k, v in f.props.items()
                        if k not in ("Reference", "Value", "Footprint"))
        lines.append(f"  (comp (ref {q(f.ref)}) (value {q(f.value)}) (footprint {q(f.lib)}){props})")
    lines.append(" )")
    lines.append(" (nets")
    nets = {}
    for f in b.footprints:
        if not f.ref or "board_only" in f.attrs:
            continue
        seen = set()
        for p in f.pads:
            if p.num == "" or not p.copper or not p.net or p.num in seen:
                continue
            seen.add(p.num)
            nets.setdefault(p.net, []).append(p)
    for code, (name, pads) in enumerate(sorted(nets.items()), 1):
        nodes = " ".join(f"(node (ref {q(p.ref)}) (pin {q(p.num)})" + (f" (pinfunction {q(p.func)})" if p.func else "")
                         + (f" (pintype {q(p.ptype)})" if p.ptype else "") + ")" for p in pads)
        lines.append(f"  (net (code {q(code)}) (name {q(name)}) {nodes})")
    lines.append(" ))")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return len(nets)

# ---------------------------------------------------------------- self-test

BOARD = """(kicad_pcb (version 20251001)
 (net 0 "") (net 1 "/VDD") (net 2 "GND")
 (footprint "lib:MCU" (layer "F.Cu") (at 20 20)
  (property "Reference" "U1") (property "Value" "MCU")
  (pad "1" smd rect (at -1 0) (size 0.5 0.3) (layers "F.Cu") (net 1 "/VDD") (pinfunction "VDD") (pintype "power_in"))
  (pad "2" smd rect (at 1 0) (size 0.5 0.3) (layers "F.Cu") (net "GND") (pinfunction "GND") (pintype "power_in"))
  (pad "3" smd rect (at 0 1) (size 0.5 0.3) (layers "F.Cu") (net "/SIG") (pinfunction "PA0") (pintype "bidirectional"))
  (pad "4" smd rect (at 0 -1) (size 0.5 0.3) (layers "F.Cu") (net "unconnected-(U1-NC-Pad4)") (pinfunction "NC"))
  (pad "5" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "GND"))
  (pad "5" smd rect (at 0.5 0.5) (size 0.3 0.3) (layers "F.Cu") (net "GND")))
 (footprint "lib:C_0402" (layer "F.Cu") (at 17 20)
  (property "Reference" "C1") (property "Value" "100n") (property "Decouples" "U1:1")
  (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "/VDD"))
  (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "GND")))
 (footprint "lib:R_0402" (layer "F.Cu") (at 23 20)
  (property "Reference" "R1") (property "Value" "10k")
  (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "/SIG"))
  (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu") (net "/VDD")))
 (footprint "lib:MountingHole" (layer "F.Cu") (at 5 5) (attr board_only exclude_from_pos_files exclude_from_bom)
  (property "Reference" "H1") (property "Value" "M3")
  (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask")))
)
"""

NET = """(export (version "E")
 (components
  (comp (ref "U1") (value "MCU") (footprint "lib:MCU"))
  (comp (ref "C1") (value "100n") (footprint "lib:C_0402") (property (name "Decouples") (value "U1:1")))
  (comp (ref "R1") (value "{R1V}") (footprint "lib:R_0402")){EXTRA})
 (nets
  (net (code "1") (name "{VDD}") (node (ref "U1") (pin "1") (pinfunction "VDD") (pintype "power_in")) (node (ref "C1") (pin "1"))
   (node (ref "R1") (pin "2")))
  (net (code "2") (name "GND") (node (ref "U1") (pin "2") (pinfunction "GND") (pintype "power_in")) (node (ref "U1") (pin "5"))
   (node (ref "C1") (pin "2")))
  (net (code "3") (name "/SIG") (node (ref "U1") (pin "{SIGPIN}")) (node (ref "R1") (pin "1")))
  (net (code "4") (name "unconnected-(U1-NC-Pad4)") (node (ref "U1") (pin "4")))))
"""


def _net(**kw):
    v = {"R1V": "10k", "VDD": "/VDD", "SIGPIN": "3", "EXTRA": ""}
    v.update(kw)
    s = NET
    for k, x in v.items():
        s = s.replace("{" + k + "}", x)
    return s


def self_test():
    import importlib.util
    d = tempfile.mkdtemp()
    bp = os.path.join(d, "b.kicad_pcb")
    open(bp, "w", encoding="utf-8").write(BOARD)
    b = load_pcb(bp)

    def run(**kw):
        p = os.path.join(d, "n.kicad_net")
        open(p, "w", encoding="utf-8").write(_net(**kw))
        return parity(b, p)

    diffs, notes = run()
    assert not diffs, diffs
    assert any("H1" in n for n in notes), notes
    cases = {
        "net differs": dict(SIGPIN="5"),            # U1.3 moved to pin 5 in the schematic
        "renamed net": dict(VDD="/3V3"),
        "missing pad": dict(SIGPIN="7"),            # the symbol has a pin the footprint lacks
        "value differs": dict(R1V="4k7"),
        "missing footprint": dict(EXTRA='\n  (comp (ref "U9") (value "X") (footprint "lib:X"))'),
    }
    for kind, kw in cases.items():
        diffs, _ = run(**kw)
        assert any(x[0] == kind for x in diffs), (kind, diffs)
    diffs, _ = run(VDD="/3V3")
    assert not any(x[0] == "net differs" for x in diffs), diffs         # a rename is one line, not one per pin
    diffs, _ = run(SIGPIN="5")
    assert {x[0] for x in diffs} >= {"net differs", "extra pad"}, diffs  # U1.3 now only on the board
    # Tier A netlist from the board: audit_netlist and check_decoupling read it unchanged
    out = os.path.join(d, "pcb.kicad_net")
    write_net(b, out)
    here = os.path.dirname(os.path.abspath(__file__))
    mods = {}
    for name in ("audit_netlist", "check_decoupling"):
        spec = importlib.util.spec_from_file_location(name, os.path.join(here, name + ".py"))
        mods[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mods[name])
    comps, pins, fps = mods["audit_netlist"].load(out)
    assert pins[("U1", "1")] == "VDD" and pins[("U1", "5")] == "GND" and comps["R1"] == "10k" and "H1" not in comps, pins
    assert pins[("U1", "4")].startswith("unconnected-"), "single-pin unconnected net kept as kicad-cli writes it"
    rows, f, s = mods["check_decoupling"].analyse(out)
    assert s["assigned"] == 1 and not [x for x in f if x["check"] in ("D1", "D2")], (rows, f)
    assert parity(b, out)[0] == [], parity(b, out)                  # board vs its own export: no difference
    shutil.rmtree(d, ignore_errors=True)
    print("self-test OK: clean netlist matches; net differs, renamed net (one line), value differs, missing "
          "footprint, missing pad and extra pad caught; board-only H1 listed; --write-net read by audit_netlist and check_decoupling")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--netlist", "--write-net"))]
    if not pos:
        print(__doc__)
        return 2
    b = load_pcb(pos[0])
    if "--write-net" in argv:
        out = argv[argv.index("--write-net") + 1]
        n = write_net(b, out)
        print(f"wrote {out}: {sum(1 for f in b.footprints if f.ref and 'board_only' not in f.attrs)} components, {n} nets "
              "(from the board's pad nets)")
        return 0
    if "--netlist" in argv:
        diffs, notes = parity(b, argv[argv.index("--netlist") + 1])
        if "--json" in argv:
            print(json.dumps({"differences": [dict(zip(("kind", "item", "detail"), x)) for x in diffs], "notes": notes}, indent=1))
        else:
            for k, item, det in diffs:
                print(f"  {k:<18}{item:<22}{det}")
            for n in notes:
                print(f"  note              {n}")
            print(f"parity board <-> netlist: {len(diffs)} difference(s)")
        return 1 if diffs else 0
    pins, two, info = board_map(b)
    rows = []
    for f in b.footprints:
        seen = set()
        for p in f.pads:
            if p.num == "" or not p.copper or p.num in seen:
                continue
            seen.add(p.num)
            rows.append({"pad": f"{p.ref}.{p.num}", "net": p.net or "", "pinfunction": p.func, "pintype": p.ptype})
    if "--json" in argv:
        print(json.dumps({"pads": rows, "pads_on_two_nets": two}, indent=1))
    else:
        for r in rows:
            print(f"{r['pad']:<14}{r['net']:<32}{r['pinfunction']:<14}{r['pintype']}")
        nets = {r["net"] for r in rows if norm(r["net"])}
        print(f"\n{len(info)} footprints, {len(rows)} pads, {len(nets)} nets, "
              f"{sum(1 for r in rows if not norm(r['net']))} pads unconnected" + (f"; pads on two nets: {two}" if two else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Copy 3D models (and selected F.Fab graphics) from the project library onto a placed board.

  sync_models.py <board.kicad_pcb> [--lib lib/<name>.pretty] [--graphics FP1,FP2]   (KiCad's Python)

Default --lib: the single *.pretty under <project>/lib/. --graphics names footprints whose
F.Silk/F.Fab drawings are copied too (after fp_silk.py lib). Run unpiped (wx asserts).

Updates the routed board in place without re-running placement or routing: for every
footprint, the (model ...) entries are replaced by the library footprint's. For the
footprints in GRAPHICS, the board copy's graphic items are replaced by the library's too
(only drawings: pads, fields, nets and tracks are not touched).
"""
import os
import sys

import pcbnew

LIB = None
GRAPHICS = set()


def default_lib(board_path):
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(board_path)), ".."))
    libs = [d for d in os.listdir(os.path.join(root, "lib")) if d.endswith(".pretty")] if os.path.isdir(os.path.join(root, "lib")) else []
    if len(libs) != 1:
        sys.exit(f"pass --lib: found {libs} under {root}/lib")
    return os.path.join(root, "lib", libs[0])


def main(path):
    global LIB
    LIB = LIB or default_lib(path)
    board = pcbnew.LoadBoard(path)
    cache = {}
    later = []
    for fp in board.GetFootprints():
        name = fp.GetFPID().GetLibItemName().wx_str()
        if name not in cache:
            cache[name] = pcbnew.FootprintLoad(LIB, name)
        lib = cache[name]
        if lib is None:
            print(f"{fp.GetReference()}: {name} not in the library, skipped")
            continue
        ms = fp.Models()
        old = [m.m_Filename for m in ms]
        while len(ms):
            ms.pop()
        for m in lib.Models():
            ms.append(m)
        new = [m.m_Filename for m in ms]
        if old != new:
            print(f"{fp.GetReference():<4} models: {[os.path.basename(f) for f in new]}")
        if name in GRAPHICS:
            later.append((fp, name))
    # graphics last: after Remove()/Add() on a footprint the SWIG wrappers of other board
    # objects stop resolving in KiCad 10's Python, so nothing else is touched afterwards
    for fp, name in later:
        ref = pcbnew.FootprintLoad(LIB, name)   # own copy, moved onto the board footprint
        ref.SetPosition(fp.GetPosition())
        ref.SetOrientation(fp.GetOrientation())
        new_items = [item.Duplicate() for item in ref.GraphicalItems()]
        for item in [i for i in fp.GraphicalItems()]:
            fp.Remove(item)
        for item in new_items:
            fp.Add(item)
        print(f"graphics synced from the library: {name} ({len(new_items)} items)")
    board.Save(path)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--lib" in args:
        LIB = args[args.index("--lib") + 1]
    if "--graphics" in args:
        GRAPHICS = set(args[args.index("--graphics") + 1].split(","))
    main(args[0])

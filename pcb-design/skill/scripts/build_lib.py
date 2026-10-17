#!/usr/bin/env python3
# Purpose: build the project library (lib/<name>.kicad_sym, lib/<name>.pretty, lib/3d/, hardware/*-lib-table)
#          from KiCad 10 stock symbols/footprints/models plus exact-part models, driven by lib/manifest.json.
#          Stock symbols are copied standalone (extends resolved); renamed where the stock part is a
#          pin-compatible sibling; footprints copied with their 3D models moved under ${KIPRJMOD}/../lib/3d/;
#          EasyEDA/vendor models attached with an explicit offset/rotation table.
# Usage:   python3 scripts/build_lib.py [project-dir] [--kicad /path/to/SharedSupport] [--self-test]
#          Project-specific edits (hole sizes, hand-made footprints) live in lib/lib_patches.py:
#          def patch(pretty_dir, manifest) -> None   (called after the stock copy, before models)
# Pitfalls: a renamed symbol keeps the stock pin map — the manifest records which datasheet table the mapping
#           was checked against; EasyEDA z is NOT the seating height (set every z from a side-view render);
#           re-running regenerates everything that is not in lib_patches.py.
#
# lib/manifest.json
# {
#   "name": "myboard",
#   "symbols":   {"Device": ["R", "C", "LED"], "power": ["GND", "PWR_FLAG", "+3V3"],
#                 "Amplifier_Operational": ["LM358"]},
#   "rename":    {"LM358": {"to": "LM358_ST", "descr": "ST LM358DT dual op-amp, SOIC-8",
#                           "checked": "pins per ST DS1083 p. 2 = stock LM358 symbol"}},
#   "power_derived": {"+3V3": {"VBAT": "battery bus", "VSYS": "system rail"}},
#   "footprints": {"Resistor_SMD": ["R_0603_1608Metric"], "Package_SO": ["SOIC-8_3.9x4.9mm_P1.27mm"]},
#   "models":    {"SOIC-8_3.9x4.9mm_P1.27mm": {"file": "easyeda/LM358DR_C7950.step",
#                                              "offset": [0, 0, 0], "rotate": [0, 0, 0],
#                                              "source": "EasyEDA C7950, z from side render 2026-10-17"}}
# }
import copy
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import Sym, dump, find, first, parse  # noqa: E402

KICAD_CANDIDATES = [
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport",
    os.path.expanduser("~/Applications/KiCad/KiCad.app/Contents/SharedSupport"),
    "/usr/share/kicad", "/usr/local/share/kicad", "/snap/kicad/current/usr/share/kicad",
    "C:/Program Files/KiCad/10.0/share/kicad",
]
D3 = "${KIPRJMOD}/../lib/3d/"
MODEL_RE = r'\t?\(model "[^"]+"(?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)\s*'


def find_kicad(explicit=None):
    for c in ([explicit] if explicit else []) + [os.environ.get("KICAD_SHARE")] + KICAD_CANDIDATES:
        if c and os.path.isdir(os.path.join(c, "symbols")):
            return c
    sys.exit("KiCad share dir not found — pass --kicad <SharedSupport|/usr/share/kicad> or set KICAD_SHARE")


# ----------------------------------------------------------------------------- symbols

def flatten(syms, name):
    """Standalone copy of symbol `name` with any `extends` resolved."""
    s = copy.deepcopy(syms[name])
    ext = first(s, "extends")
    if not ext:
        return s
    parent = flatten(syms, ext[1])
    out = [Sym("symbol"), name]
    child_props = {p[1]: p for p in find(s, "property")}
    for item in parent[2:]:
        if isinstance(item, list) and item and item[0] == "property" and item[1] in child_props:
            out.append(child_props.pop(item[1]))
        elif isinstance(item, list) and item and item[0] == "symbol":
            unit = copy.deepcopy(item)
            unit[1] = re.sub("^" + re.escape(ext[1]), name, unit[1])
            out.append(unit)
        else:
            out.append(item)
    for p in child_props.values():
        out.insert(2, p)
    return out


def rename(sym, new, descr):
    old = sym[1]
    sym[1] = new
    for u in find(sym, "symbol"):
        u[1] = re.sub("^" + re.escape(old), new, u[1])
    for p in find(sym, "property"):
        if p[1] == "Value":
            p[2] = new
        if p[1] == "Description":
            p[2] = descr
        if p[1] == "Datasheet":
            p[2] = ""
    return sym


def derive_power(sym, pname, descr):
    d = parse(dump(sym).replace('"' + sym[1], '"' + pname).replace(sym[1] + '"', pname + '"'))
    for p in find(d, "property"):
        if p[1] == "Value":
            p[2] = pname
        if p[1] == "Description":
            p[2] = f'Power symbol, global net "{pname}": {descr}'
    return d


def build_symbols(m, kicad, lib_dir, symbol_text=None):
    out = [Sym("kicad_symbol_lib"), [Sym("version"), Sym("20241209")],
           [Sym("generator"), "build_lib.py"], [Sym("generator_version"), "1"]]
    for lib, names in m.get("symbols", {}).items():
        text = symbol_text(lib) if symbol_text else open(f"{kicad}/symbols/{lib}.kicad_sym", encoding="utf-8").read()
        syms = {s[1]: s for s in find(parse(text), "symbol")}
        for n in names:
            if n not in syms:
                sys.exit(f"symbol {n} not in {lib}.kicad_sym")
            s = flatten(syms, n)
            if n in m.get("rename", {}):
                r = m["rename"][n]
                if not r.get("checked"):
                    sys.exit(f"rename {n} -> {r.get('to')} needs a 'checked' note (datasheet table)")
                s = rename(s, r["to"], r.get("descr", ""))
            out.append(s)
            for pname, descr in m.get("power_derived", {}).get(n, {}).items():
                out.append(derive_power(s, pname, descr))
    os.makedirs(lib_dir, exist_ok=True)
    with open(os.path.join(lib_dir, f"{m['name']}.kicad_sym"), "w", encoding="utf-8") as f:
        f.write(dump(out) + "\n")
    return [s[1] for s in out if isinstance(s, list) and s and s[0] == "symbol"]


def tables(name, hw):
    os.makedirs(hw, exist_ok=True)
    open(os.path.join(hw, "sym-lib-table"), "w", encoding="utf-8").write(
        f'(sym_lib_table\n\t(version 7)\n\t(lib (name "{name}") (type "KiCad") '
        f'(uri "${{KIPRJMOD}}/../lib/{name}.kicad_sym") (options "") (descr "Project library"))\n)\n')
    open(os.path.join(hw, "fp-lib-table"), "w", encoding="utf-8").write(
        f'(fp_lib_table\n\t(version 7)\n\t(lib (name "{name}") (type "KiCad") '
        f'(uri "${{KIPRJMOD}}/../lib/{name}.pretty") (options "") (descr "Project library"))\n)\n')


# ----------------------------------------------------------------------------- footprints

def copy_model(path, kicad, lib_dir):
    m = re.match(r"\$\{KICAD\d*_3DMODEL_DIR\}/(.+)", path)
    if not m:
        return path
    os.makedirs(os.path.join(lib_dir, "3d"), exist_ok=True)
    src = os.path.join(kicad, "3dmodels", m.group(1))
    if os.path.exists(src):
        shutil.copy(src, os.path.join(lib_dir, "3d", os.path.basename(src)))
    else:
        print(f"   note: stock model missing: {m.group(1)} (KiCad ships no model, or the pack is not installed)")
    return D3 + os.path.basename(m.group(1))


def stock_footprint(kicad, lib, name, lib_dir, keep_models=True):
    text = open(f"{kicad}/footprints/{lib}.pretty/{name}.kicad_mod", encoding="utf-8").read()
    if not keep_models:
        return re.sub(MODEL_RE, "", text)
    return re.sub(r'\(model "([^"]+)"', lambda mm: f'(model "{copy_model(mm.group(1), kicad, lib_dir)}"', text)


def attach_model(text, rel_file, off, rot):
    text = re.sub(MODEL_RE, "", text)
    item = (f'\t(model "{D3}{rel_file}"\n\t\t(offset (xyz {off[0]:g} {off[1]:g} {off[2]:g})) '
            f'(scale (xyz 1 1 1)) (rotate (xyz {rot[0]:g} {rot[1]:g} {rot[2]:g})))\n')
    return text.rstrip().rstrip(")").rstrip() + "\n" + item + ")\n"


def build_footprints(m, kicad, lib_dir, project):
    pretty = os.path.join(lib_dir, f"{m['name']}.pretty")
    os.makedirs(pretty, exist_ok=True)
    models = m.get("models", {})
    for lib, names in m.get("footprints", {}).items():
        for n in names:
            txt = stock_footprint(kicad, lib, n, lib_dir, keep_models=n not in models)
            open(os.path.join(pretty, f"{n}.kicad_mod"), "w", encoding="utf-8").write(txt)
    patches = os.path.join(lib_dir, "lib_patches.py")
    if os.path.exists(patches):
        import importlib.util
        spec = importlib.util.spec_from_file_location("lib_patches", patches)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.patch(pretty, m)
        print("   lib_patches.py applied")
    for n, spec_ in models.items():
        p = os.path.join(pretty, f"{n}.kicad_mod")
        if not os.path.exists(p):
            sys.exit(f"models: footprint {n} not in the library (add it to footprints or lib_patches.py)")
        if not os.path.exists(os.path.join(lib_dir, "3d", spec_["file"])):
            print(f"   WARNING: model file lib/3d/{spec_['file']} missing for {n}")
        txt = attach_model(open(p, encoding="utf-8").read(), spec_["file"],
                           spec_.get("offset", [0, 0, 0]), spec_.get("rotate", [0, 0, 0]))
        open(p, "w", encoding="utf-8").write(txt)
    return sorted(f[:-10] for f in os.listdir(pretty) if f.endswith(".kicad_mod"))


# ----------------------------------------------------------------------------- self-test

SYM_FIXTURE = """(kicad_symbol_lib (version 20241209) (generator "t")
 (symbol "Base" (pin_numbers (hide yes)) (in_bom yes) (on_board yes)
  (property "Reference" "U" (at 0 0 0)) (property "Value" "Base" (at 0 0 0)) (property "Description" "base part" (at 0 0 0))
  (symbol "Base_0_1" (rectangle (start -5 5) (end 5 -5)))
  (symbol "Base_1_1" (pin input line (at -7 0 0) (length 2) (name "IN" (effects)) (number "1" (effects)))))
 (symbol "Child" (extends "Base") (property "Value" "Child" (at 0 0 0)) (property "Description" "child part" (at 0 0 0)))
)"""


def self_test():
    import tempfile
    tmp = tempfile.mkdtemp()
    m = {"name": "t", "symbols": {"Fake": ["Child", "Base"]},
         "rename": {"Child": {"to": "ChildX", "descr": "renamed", "checked": "fixture"}}}
    names = build_symbols(m, None, os.path.join(tmp, "lib"), symbol_text=lambda lib: SYM_FIXTURE)
    txt = open(os.path.join(tmp, "lib", "t.kicad_sym"), encoding="utf-8").read()
    assert "ChildX" in names and "Base" in names, names
    assert "extends" not in txt, "extends not resolved"
    assert '"ChildX_1_1"' in txt and '"IN"' in txt, "child did not inherit the parent's units/pins"
    assert txt.count('(property "Description" "renamed"') == 1
    # rename without a 'checked' note must refuse
    try:
        build_symbols({"name": "t2", "symbols": {"Fake": ["Child"]}, "rename": {"Child": {"to": "Y"}}},
                      None, os.path.join(tmp, "lib2"), symbol_text=lambda lib: SYM_FIXTURE)
        raise AssertionError("rename without 'checked' was accepted")
    except SystemExit:
        pass
    fp = '(footprint "X" (layer "F.Cu")\n\t(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))\n\t(model "${KICAD9_3DMODEL_DIR}/A.3dshapes/old.step"\n\t\t(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n)\n'
    out = attach_model(fp, "easyeda/new.step", [1, 2, 3], [0, 0, 90])
    assert "old.step" not in out and "easyeda/new.step" in out and "(xyz 1 2 3)" in out and out.count("(model ") == 1, out
    shutil.rmtree(tmp)
    print("self-test OK: extends resolved, rename + derived description, unchecked rename refused, model replaced")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    project = os.path.abspath(argv[0]) if argv and not argv[0].startswith("-") else os.getcwd()
    kicad = find_kicad(argv[argv.index("--kicad") + 1] if "--kicad" in argv else None)
    lib_dir = os.path.join(project, "lib")
    mp = os.path.join(lib_dir, "manifest.json")
    if not os.path.exists(mp):
        sys.exit(f"{mp} missing — see the header of this script for the format")
    m = json.load(open(mp, encoding="utf-8"))
    print(f"KiCad share: {kicad}")
    names = build_symbols(m, kicad, lib_dir)
    tables(m["name"], os.path.join(project, "hardware"))
    print(f"{len(names)} symbols: " + ", ".join(names))
    fps = build_footprints(m, kicad, lib_dir, project)
    print(f"{len(fps)} footprints: " + ", ".join(fps))
    print("next: fp_silk.py lib (silk convention), then validate land patterns and models per the gate-5 checklist")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# Scripted KiCad generation and automation

How to produce and edit KiCad 10 files without the GUI, and the traps
that cost real time. Read before writing any script that touches
`.kicad_sch`, `.kicad_pcb` or the pcbnew API.

## kicad-cli location

Not necessarily in PATH. `source scripts/kicad_env.sh` sets `KICAD_CLI`
and `KICAD_PYTHON` (macOS: `/Applications/KiCad/KiCad.app/Contents/MacOS/
kicad-cli`; pcbnew's bundled Python is a separate interpreter — KiCad
10 ships its own, check `KiCad.app/Contents/Frameworks/Python.framework`).
Never assume the system `python3` can `import pcbnew`.

## Schematic generation (S-expressions)

- **Grid**: every symbol, label and wire endpoint on 2.54 mm (1.27 mm
  at most). Off-grid endpoints produce hundreds of ERC
  `endpoint_off_grid` warnings and unconnected-looking wires.
- **Escape quotes**: an unescaped `"` in a value (`1.3"`) corrupts the
  S-expression silently; symptoms appear elsewhere (hierarchical labels
  "not connecting"). Escape or avoid inch marks.
- **Field angles follow symbol rotation**, otherwise text is sideways.
- **Keep the title block area free** on the sheet.
- **Deterministic UUIDs**: derive every symbol/sheet/pin UUID with
  `uuid5(namespace, f"{sheet}/{reference}")`. Random UUIDs mean a
  regenerated schematic breaks every symbol-to-footprint link and
  schematic parity; from then on only surgical text edits are possible
  and the generator is dead.
- Mirror every manual edit back into the generator's data table, or
  retire the generator explicitly — never let the two drift.
- **PWR_FLAG** on `power_in` pins fed only passively (boost SW pin,
  AVDD behind RC) or ERC complains.
- **Open-collector → power output** (e.g. a QOD pin to VOUT) raises an
  ERC error; route through 0 Ω where the datasheet allows.
- **Kelvin / sense points** as net ties in the schematic so layout can
  keep them.
- **Self-audit tool**: export the netlist (`kicad-cli sch export
  netlist`) and check pin by pin against the datasheet summary — the
  most effective schematic check available without a GUI.

## Board generation and edits (pcbnew API, KiCad 10)

- **Removals last.** After `board.Remove()` / `fp.Remove()`, SWIG
  wrappers of *other* objects can stop resolving (`GetFPID`,
  `GraphicalItems`, `SetValue` fail). Do all reads and modifications
  first, removals last, **one process per job**.
- **One zone per process.** Creating several zones in one process has
  scrambled their outlines. Create one net's zone per run, copying
  polygon points explicitly.
- **Silent death in pipes.** Scripts can die on a wx assert when output
  is piped (`| grep`). The board is then not saved, and a following
  `kicad-cli pcb drc --save-board` reports 0 violations on the *old*
  board. Run unpiped, write logs to files, and **verify the edit
  itself** (grep the `.kicad_pcb`, count zones/footprints/tracks)
  before running DRC.
- `Duplicate()` signature changed (needs `addToParentGroup`). Check
  signatures against the running version, not the docs you remember.
- Pre-route critical loops by script (boost/buck loop, Kelvin
  connections), place GND fan-out vias and stitching by script, then
  let the autorouter handle the remainder.

## Autorouting (Freerouting)

Only for non-critical nets, after placement and after manual routing
of power loops, RF, matched groups and FMEA-relevant nets. It does no
impedance or length control and **never rotates a part** — orientation
is fixed at placement review. Needs Java ≥ 21 and ~64 MB: **ask before
downloading**. Flow: `kicad-cli pcb export dsn` → headless run → import
`.ses` → re-check zone fills and unconnected items → DRC.

## Verify the verifier

Every automated check gets a **negative control** before it is
believed: make it fail on purpose once (lower the lid into the board,
compare a part against its own shifted copy, feed a known error line
to the error filter, count zones before/after). Cases that have
reported false "OK":

- OpenSCAD `intersection()` on KiCad's STL (not a closed mesh) → silently
  empty → "no collision". Use a signed-distance check on point samples
  or a repaired mesh.
- Shell variable not word-split (zsh) → both inputs pointed at a
  non-existent file → "no overlap".
- `grep -i error` matching "NoError" → everything "failed".
- Zone script died in a pipe → DRC on the old board → "0 violations".

Add a `--self-test` flag where feasible; note in `docs/design-notes.md`
which checks have a control.

A verifier can also pass **by not looking**: the first entry-angle lint
folded the angle (backwards counted as axial), ignored IC pins and GND,
skipped parts with unnumbered pads, and let bends hide inside pads
behind a minimum-length filter. Encode the rule's purpose ("the trace
leaves the pad cleanly, outward, along the pad"), not one formula; when
a person catches a miss, add it as a positive self-test case before
fixing the code. Measured checks beat ticked checklists ("C13–C15 at
1–2 mm" survived four revisions at 6 mm).

Re-orienting parts after routing is expensive but local: ~30 scripted
edit batches with DRC after each, netlist untouched; the hard spots are
where bottom-layer signals already claimed the via positions.

## 3D models

Order: KiCad's packaged models → LCSC/EasyEDA for the exact part
(watermarks, no colours, occasionally off by a fraction of a mm) →
vendor STEP (403 for `curl`; fetch in the browser or ask the user;
vendor assemblies may carry hidden offsets). After import check
pin-on-pad, F.Fab outline and seating plane/height against the
datasheet. Placeholder boxes only when listed with their dimensions.

## Fetching datasheets

Datasheets:
`scripts/lcsc_detail.py <Cxxxxx>` returns parameters and the datasheet
URL; `scripts/pdf_grep.sh <pdf> <pattern>` prints matching page
numbers for citations in `docs/parts/`.

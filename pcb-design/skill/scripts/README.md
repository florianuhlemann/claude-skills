# Scripts

All scripts are shipped with the skill and self-contained (Python 3 standard library; `sexpr.py` is the
shared S-expression module). Nothing has to be imported from an earlier project. Every script with a
`--self-test` carries its own negative control; `preflight.sh` runs them all.

## Step 0

| Script | Purpose |
|---|---|
| `preflight.sh [project]` | Reports required/optional tools (kicad-cli, pcbnew Python, poppler, java, JLC API), runs every self-test, checks the project for manifest, key-values, regenerate hook, DRC allowlist. |
| `kicad_env.sh` | `source` it: `KICAD_CLI`, `KICAD_PYTHON` (macOS bundle path included). |

## Sourcing and datasheets (gates 2–3)

| Script | Purpose |
|---|---|
| `jlc_search.py "<kw or Cxxxx>"` | JLC parts API: LCSC code, Basic/Preferred/Extended, assembly type (economic / STD-ONLY?), stock, price; `--economic`, `--basic`, `--json`, `--datasheet DIR` downloads the PDF. Fails loudly with the manual procedure when the API is unreachable. |
| `pdf_grep.sh <pdf> <regex>` | Page numbers + matching lines for citations in `docs/parts/`. |

## Schematic (gate 4)

| Script | Purpose |
|---|---|
| `audit_netlist.py net.xml` | Pin-by-pin audit against `docs/netlist-expect.json` + project value checks in `scripts/netlist_checks.py`; `--corrupt` negative control; `--self-test`. |

## Library (gate 5)

| Script | Purpose |
|---|---|
| `build_lib.py [project]` | Builds `lib/<name>.kicad_sym`, `.pretty`, `3d/`, lib tables from `lib/manifest.json` (format in the header); renames need a datasheet "checked" note; `lib/lib_patches.py` hook for project edits; `--self-test`. |
| `fp_silk.py lib / check / board <pcb>` | Applies the footprint silk convention (pin-1 triangle, pad-free-side outlines, polarity marks, F.Fab reference), lints silk-to-pad clearance, syncs graphics into a placed board; kinds inferred, overrides in `lib/silk-kinds.json`; `--self-test`. |
| `sync_models.py <pcb> [--lib] [--graphics]` | Copies the library's 3D models (and selected graphics) onto a routed board without re-placing (pcbnew Python, run unpiped). |
| `sexpr.py` | Shared S-expression parse/dump (`Sym`, `find`, `first`). |

## Layout (gate 6)

| Script | Purpose |
|---|---|
| `check_entry_angles.py <pcb>` | Pad-exit lint R1–R3 (two-pin outward ≤ 45°, IC pins along the long axis turning outside the pad, no bend inside a pad, round pads through the centre); `--self-test`. |
| `check_track_geometry.py <pcb>` | Zero-length, duplicates, off-45°, acute corners, 45° T-branches outside pads; `--self-test`. |

## Production (gate 7)

| Script | Purpose |
|---|---|
| `export_production.sh <project> <rev>` | Tag check, regenerate hook + diff, stale-value lint, revision check, ERC, DRC (json + report, zones refilled) gated by `drc_gate.py` when `hardware/drc-allowlist.txt` exists, claims list, layout lints, gerbers with the copper layer list from the board, drills, BOM split JLC/hand-fit, position → CPL, PDFs, STEP, renders. |
| `drc_gate.py drc.json allowlist` | Errors, unconnected and parity always fail; a warning passes only with an exact allowlist line carrying a justification; stale lines fail; `--self-test`. (kicad-cli 10 ignores the project's DRC exclusions.) |
| `fix_cpl_rotation.py` | Position CSV → JLC CPL: rotation table, THT centroid (`--pcb`), BOM filter with ranges expanded (`--bom`); `--self-test`. |
| `lint_stale_values.py <project>` | Previous values from `docs/key-values.md` must not survive anywhere (CHANGELOG, retrospective, `docs/history/`, history-marked lines exempt); `--claims` lists untraced claims. |

## Project tooling (not shipped — lives in the project repo)

Schematic/board generators (`gen_schematic.py`, `gen_pcb.py`, `placement.py`, `route_pcb.py`,
`regenerate.sh`), routing helpers (`finish_route.py`, `exit_fix.py`, `fix_pad_exits.py`, via nudging,
`power_pours.py`), analysis with project geometry (`resistance_budget.py`, `return_path.py`,
`net_render.py`, `place_check.py`, `calc_*.py`), mechanical/model tools (`enclosure_fitcheck.py`,
`stl_to_glb.py`, `step_*.py`, `make_models.py`, `gen_qfn_step.py`). Copy them between projects as
needed; when one proves generic across two boards, promote it here with a self-test.

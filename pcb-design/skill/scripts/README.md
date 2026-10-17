# Scripts

## Shipped with the skill

| Script | Purpose |
|---|---|
| `kicad_env.sh` | `source` it: finds `kicad-cli` (macOS bundle path included) and pcbnew's Python → `KICAD_CLI`, `KICAD_PYTHON`. |
| `export_production.sh <project> <rev>` | Full production chain: tag check, `scripts/regenerate.sh` hook + diff, stale-value lint, revision check, ERC, DRC (all severities, parity, zones refilled), claims list, layout lints, gerbers with the layer list read from the board (2L/4L), drills, BOM split into `bom.csv` (JLC) / `bom_handfit.csv` (`Fit=hand`), position (SMD + THT) → CPL, assembly/schematic PDFs, STEP, renders. Aborts on any violation. |
| `fix_cpl_rotation.py` | KiCad position CSV → JLC CPL: rotation table applied, THT placement points moved to the pad centroid (`--pcb`), designators filtered to the BOM (`--bom`, ranges `R1-R5` expanded); lists packages without a rule. `--self-test`. |
| `lint_stale_values.py <project>` | Fails if a "Previous values" entry from `docs/key-values.md` still appears in docs or KiCad text; CHANGELOG, retrospective and history-marked lines are exempt. `--claims` lists every untraced protection/distance/direction sentence for the claims pass. |
| `pdf_grep.sh <pdf> <regex>` | Page numbers + matching lines of a datasheet, for citations in `docs/parts/`. |
| `check_entry_angles.py <board.kicad_pcb>` | Pad-exit lint, KiCad 9/10: R1 two-pin exits outward ≤ 45°; R2 IC/connector pins along the long axis, turning outside the pad (GND included, end-of-row free side allowed); R3 no bend inside a pad, round pads through the centre. Unnumbered pads ignored. `--self-test` holds one positive case per real miss. |
| `check_track_geometry.py <board.kicad_pcb>` | Track-geometry lint: zero-length and duplicate segments, off-45° segments, acute corners and 45° T-branches outside pads. `--self-test`. |

## Sourcing / library helpers to import from the first board's project repo (copy into this folder, keep the names)

| Script | Purpose | Notes |
|---|---|---|
| `jlc_search.py` | JLC parts API search: Basic/Preferred/Extended status, JLC stock, and assembly type (`componentProductType`; 2 observed on a standard-only part — verify against the parts page) | Undocumented endpoint, LCSC search is behind Akamai — fragile; fall back to manual search. |
| `lcsc_detail.py <Cxxxxx>` | Parameters + datasheet URL for an LCSC number; downloads to `docs/datasheets/` | |
| `stock_check.py` | Re-checks stock, category and assembly type for the BOM against `quantity` + attrition; fails on any standard-only part unless the project accepted standard PCBA | Every gate and order day. |
| `sexpr.py`, `build_lib.py` | Copy KiCad stock symbols with `extends` resolved; footprints + 3D models with `${KIPRJMOD}` paths into `lib/` | |

Everything else (schematic/board generators, `regenerate.sh`, pours,
passive auto-orientation, `finish_route.py` (deterministic finisher for
autorouter leftovers), via-nudging/keep-out helpers, mesh solver, `fix_pad_exits.py` (moves in-pad bends past the pad
end), `fp_silk.py` (applies the silk convention to a library — candidate
for promotion once a second board confirms it), model sync, any
mechanical checks) is **project tooling**: keep it in the project repo
and copy between projects as needed; the skill does not maintain it.
Each imported script gets a 3-line header: purpose, usage, pitfalls.

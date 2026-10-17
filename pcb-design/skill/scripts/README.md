# Scripts

Fifteen scripts, all shipped with the skill. Python 3 standard library
and bash; `sexpr.py` is the shared S-expression module; only
`sync_models.py` needs KiCad's bundled Python (`pcbnew`). Every Python
script that checks something carries a `--self-test` with a planted
failure; `preflight.sh` runs them all. The project files a script reads
are part of the skill's project structure (`SKILL.md`) and documented in
the script's header.

| Script | When | Purpose |
|---|---|---|
| `preflight.sh` | step 0 | Is kicad-cli found, is the JLC parts API reachable, which optional tools exist; prints the manual fallback for each missing one. |
| `kicad_env.sh` | always | `source` it: sets `KICAD_CLI` and `KICAD_PYTHON` (macOS bundle path included). |
| `jlc_search.py "<kw or Cxxxx>"` | gates 2–3 | JLC parts API: LCSC code, Basic/Preferred/Extended, assembly type, stock, price; `--economic`, `--basic`, `--json`, `--datasheet DIR` downloads the PDF. Fails loudly with the manual procedure when the API is unreachable. |
| `pdf_grep.sh <pdf> <regex>` | gate 3 | Page numbers and matching lines for citations in `docs/parts/`. |
| `audit_netlist.py net.xml` | gate 4 | Pin-by-pin audit against `docs/netlist-expect.json` plus the project's value checks in `scripts/netlist_checks.py` (optional); `--corrupt` negative control. |
| `build_lib.py [project]` | gate 5 | Builds `lib/<name>.kicad_sym`, `.pretty`, `3d/` and the lib tables from `lib/manifest.json` (format in the header); renames need a datasheet "checked" note; `lib/lib_patches.py` hook for project edits. |
| `fp_silk.py lib / check / board <pcb>` | gates 5–6 | Applies the footprint silk convention to the library, lints silk-to-pad clearance, syncs graphics into a placed board; kinds inferred, overrides in `lib/silk-kinds.json`. |
| `sync_models.py <pcb> [--lib] [--graphics]` | gates 5–6 | Copies the library's 3D models (and selected graphics) onto a routed board without re-placing. pcbnew Python, run unpiped. |
| `sexpr.py` | — | Shared S-expression parse/dump used by the scripts above. |
| `check_entry_angles.py <pcb>` | gate 6 | Pad-exit lint R1–R3 (two-pin outward ≤ 45°, IC pins along the long axis turning outside the pad, no bend inside a pad, round pads through the centre). |
| `check_track_geometry.py <pcb>` | gate 6 | Zero-length and duplicate segments, off-45° segments, acute corners, 45° T-branches outside pads. |
| `drc_gate.py drc.json allowlist` | gates 6–7 | Errors, unconnected items and parity always fail; a warning passes only with an exact allowlist line carrying a justification; stale lines fail. Needed because kicad-cli 10 ignores the project's DRC exclusions. |
| `lint_stale_values.py <project>` | before every tag | "Previous values" from `docs/key-values.md` must not survive anywhere (CHANGELOG, retrospective, `docs/history/` exempt); `--claims` lists untraced protection/distance/direction claims. |
| `fix_cpl_rotation.py` | gate 7 | KiCad position CSV → JLC CPL: rotation table, THT placement at the pad centroid (`--pcb`), BOM filter with designator ranges expanded (`--bom`). Called by the export chain. |
| `export_production.sh <project> <rev>` | gate 7 | Tag check, optional `scripts/regenerate.sh` hook, stale-value lint, revision check, ERC, DRC gated by the allowlist, claims list, layout lints, gerbers (copper layers read from the board), drills, BOM split JLC / hand-fit, CPL, PDFs, STEP, renders. |

## Not shipped

Schematic/board generators and the `regenerate.sh` hook, routing
finishers, pour and resistance-budget tools: they depend on one board's
geometry and stay in that project. The export chain calls
`scripts/regenerate.sh` only if the project has one.

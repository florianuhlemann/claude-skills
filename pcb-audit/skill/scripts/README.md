# Scripts

Nine files, all shipped with the skill. Python 3 standard library and
bash, no pcbnew. Every script that checks something carries a
`--self-test` with a planted failure that must be caught; `preflight.sh`
runs them all. Run a script's negative control once on the real project
too before trusting a clean result (`audit_netlist.py --corrupt`, or plant
one fault by hand in a copy).

Netlist input is the kicad-cli S-expression export:
`kicad-cli sch export netlist -o build/net.kicad_net hardware/<board>.kicad_sch`.

| Script | Gate | Purpose |
|---|---|---|
| `preflight.sh` | step 0 | python3 and kicad-cli found, optional tools, every self-test. |
| `kicad_env.sh` | always | `source` it: sets `KICAD_CLI` (and `KICAD_PYTHON` when pcbnew is importable). Copy of the pcb-design script. |
| `audit_netlist.py <net>` | 4 | Pin-by-pin audit against `docs/netlist-expect.json` plus the project's value checks in `scripts/netlist_checks.py` (optional); `--corrupt` negative control on the real project. |
| `check_decoupling.py <net> [<pcb>]` | 4, 6 | `Decouples` field audit: D1 unassigned cap, D2 assigned to a pin on another net, D3 supply pin without a cap; with the board D4 pad-to-pin distance (`--max-dist`, default 2.0 mm edge to edge), D5 cap reached from the pin only through a via or the plane, D6 nearest same-net cap is not the assigned one, D7 no return-net via within `--gnd-via-dist` (1.0 mm). Table per cap, `--json`, exit 1 on blocker/major. `--write-fixtures DIR` writes the self-test's clean and planted cases for a run by hand. |
| `check_entry_angles.py <pcb>` | 6 | Pad-exit lint R1–R3 (two-pin outward ≤ 45°, IC pins along the long axis turning outside the pad, no bend inside a pad, round pads through the centre). |
| `check_track_geometry.py <pcb>` | 6 | Zero-length and duplicate segments, off-45° segments, acute corners, 45° T-branches outside pads. |
| `drc_gate.py drc.json allowlist` | 6, 7 | Errors, unconnected items and parity always fail; a warning passes only with an exact allowlist line carrying a justification; stale lines fail. Needed because kicad-cli 10 ignores the project's DRC exclusions. |
| `lint_stale_values.py <project>` | 7 | "Previous values" from `docs/key-values.md` must not survive anywhere (CHANGELOG, retrospective, `docs/history/` exempt); `--claims` lists untraced protection/distance/direction claims. No self-test: plant one previous value in a copy to see it fire. |
| `sexpr.py` | — | Shared S-expression parse/dump used by `audit_netlist.py` and `check_decoupling.py`. Copy of the pcb-design module. |

`drc_gate.py` and `lint_stale_values.py` are sourced here; pcb-design ships
copies (identical apart from one header line) for its export chain. `sexpr.py` and `kicad_env.sh`
are copies of pcb-design's files (header line names the source). Change a
shared script in both skills in the same release.

The layout lints print a list and exit 0; the list is reviewed item by
item at the gate (`--strict` exits 1 on any finding).

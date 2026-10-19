# Scripts

Fourteen files, all shipped with the skill. Python 3 standard library and
bash, no pcbnew, no KiCad needed except where marked Tier B. Every script
that checks something carries a `--self-test` with a planted failure that
must be caught; `preflight.sh` runs them all and prints the tier. Run a
script's negative control once on the real project too before trusting a
clean result (`audit_netlist.py --corrupt`, or plant one fault by hand in
a copy). Paths: `scripts/` is this skill's folder (`<skill dir>/scripts/`),
not the project's; run each script with the project as working directory.

**Tier A** (always): the scripts read the project files directly: the
`.kicad_pcb`, a netlist export, gerbers and drills. **Tier B** (with
kicad-cli) adds fresh ERC, DRC with schematic parity and netlist exports:
`kicad-cli sch export netlist -o build/net.kicad_net hardware/<board>.kicad_sch`.
Without an export, `pcb_nets.py --write-net` writes the board's pad nets
in the same form, and `audit_netlist.py` and `check_decoupling.py` run on
it unchanged.

| Script | Gate | Tier | Purpose |
|---|---|---|---|
| `preflight.sh` | step 0 | — | python3, kicad-cli (optional), optional tools, every self-test; prints Tier A or B. |
| `board_stats.py <pcb> [--pro] [--json]` | every audit | A | Evidence base: outline bbox, loops, edge arc radii, sharp inside corners; copper layers, stackup, finish; tracks per layer and the narrowest per net class (`.kicad_pro`); via histogram; zones per net and layer with outline and fill area, fill pieces and islands, unfilled zones; finished-hole table; parts SMD/THT per side, DNP, board-only; DFM: finest pitch, smallest pad gap and mask dam, vias under paste, aux origin and negative CPL coordinates. Flags listed; `--strict` exits 1 on a flag. |
| `pcb_nets.py <pcb> [--netlist <net>] [--write-net <out>] [--json]` | 4, 6 | A | Pad → net map from the board. `--netlist`: parity with the export (missing/extra footprints and pads, net differs, renamed net, value or footprint differs, pads of one number on two nets), exit 1 on any difference. `--write-net`: the board's pad nets as a kicad-cli-style netlist, footprint properties (`Decouples`) and pin types included. |
| `net_path.py <pcb> <REF.PAD> <REF.PAD> [--no-via]`, `--pairs <file> [--tol]` | 6, 7 | A | Routed copper length (tracks and arcs, true arc length), via count and path between two pads of a net; straight-line distances beside it; "zone only" or "through the plane" (which via each end reaches, after how much track) when no track joins them. `--pairs` checks a list of claimed lengths, exit 1 on a claim exceeded or a pair not connected by tracks. |
| `check_fab_files.py <dir or zip> [--board <pcb>] [--size WxH]` | 7 | A | Fab-file alignment on the files that get ordered: F1 a centred flash (or region) on both outer layers at every plated drill, with the common offset named when drills and gerbers use different origins; F2 holes inside the outline bbox; F3 outline = documented size and board Edge.Cuts; F4 drill table and positions = the board's holes; F5 layers present. Reads RS-274X and Excellon. `--write-fixtures DIR` writes the self-test's clean and planted sets. |
| `audit_netlist.py <net>` | 4 | A/B | Pin-by-pin audit against `docs/netlist-expect.json` plus the project's value checks in `scripts/netlist_checks.py` (optional); `--corrupt` negative control on the real project. Input: the kicad-cli export or `pcb_nets.py --write-net`. |
| `check_decoupling.py <net> [<pcb>]` | 4, 6 | A/B | `Decouples` field audit: D1 unassigned cap, D2 assigned to a pin on another net, D3 supply pin without a cap; with the board D4 pad-to-pin distance (`--max-dist`, default 2.0 mm edge to edge), D5 cap reached from the pin only through a via or the plane, D6 nearest same-net cap is not the assigned one, D7 no return-net via within `--gnd-via-dist` (1.0 mm); routed copper length and via count per row. Table per cap, `--json`, exit 1 on blocker/major. `--write-fixtures DIR` writes the self-test's clean and planted cases; the self-test asserts both pairs pass `pcb_nets.py` parity. |
| `check_entry_angles.py <pcb>` | 6 | A | Pad-exit lint R1–R3 (two-pin outward ≤ 45°, IC pins along the long axis turning outside the pad, no bend inside a pad, round pads through the centre). |
| `check_track_geometry.py <pcb>` | 6 | A | Zero-length and duplicate segments, off-45° segments, acute corners, 45° T-branches outside pads. |
| `drc_gate.py drc.json allowlist` | 6, 7 | B | Errors, unconnected items and parity always fail; a warning passes only with an exact allowlist line carrying a justification; stale lines fail. Needed because kicad-cli 10 ignores the project's DRC exclusions. Exit 2 with usage on `-h`, a missing argument or an input it cannot read. |
| `lint_stale_values.py <project>` | 7 | A | "Previous values" from `docs/key-values.md` must not survive anywhere (CHANGELOG, retrospective, `docs/history/` exempt); `--claims` lists untraced protection/distance/direction claims. No self-test: plant one previous value in a copy to see it fire. |
| `pcb_board.py` | — | A | Shared board reader (footprints, pads with custom-pad primitives, tracks and arcs, vias, zones and fills, Edge.Cuts, stackup) and the copper walkers: `track_path` (via-free reach, check_decoupling D5) and `NetGraph`/`route` (shortest routed path, vias reached). Used by the five board scripts above. |
| `kicad_env.sh` | Tier B | B | `source` it: sets `KICAD_CLI` (and `KICAD_PYTHON` when pcbnew is importable). Copy of the pcb-design script. |
| `sexpr.py` | — | — | Shared S-expression parse/dump used by the scripts that read KiCad files. Copy of the pcb-design module. |

`drc_gate.py` and `lint_stale_values.py` are sourced here; pcb-design ships
copies (identical apart from one header line) for its export chain.
`sexpr.py` and `kicad_env.sh` are copies of pcb-design's files (header line
names the source). Change a shared script in both skills in the same
release.

The layout lints and `board_stats.py` print a list and exit 0; the list is
reviewed item by item at the gate (`--strict` exits 1 on any finding).

# pcb-audit

Independent audit of an existing KiCad 10 project for JLCPCB, gate by gate: requirements and single-fault table, live part checks, datasheet claims traced to pages and to the right test condition, ERC and pin-by-pin netlist audit, decoupling assignment, footprints and hole tolerances, DRC with a justified allowlist, routed copper lengths, layout lints, fab-file alignment, stale values and claims, revision parity, BOM/CPL consistency. Each audit writes a short report, `docs/audits/gate<N>-<date>.md`, that opens with six standing questions (correct? manufacturable? would it work? borderline? decisions to revisit? signed off but not true on this revision?) and lists findings with ID, evidence, severity, when to act, and a verdict. Works stand-alone on any KiCad 10 project and as the gate review of the [pcb-design](../pcb-design/) workflow.

**Works without KiCad.** Tier A reads the files themselves: board, netlist export, gerbers and drills, BOM and CPL. Tier B adds kicad-cli re-runs of ERC and DRC with schematic parity. `scripts/preflight.sh` says which applies, and the report names what was taken as given.

What the scripts check that DRC does not:
- `check_decoupling.py`: each decoupling capacitor serves the pin its `Decouples` field names (right net, at the pin, pin → cap → via rather than through the plane, nearest cap is the assigned one).
- `net_path.py`: routed copper length and vias between two pads, checked against every length a review document claims.
- `check_fab_files.py`: a flash under every drill on both outer layers, all holes inside the outline, the outline equal to the documented size, and the drill table equal to the board's. A drill-origin offset passes every DRC.
- `pcb_nets.py`: the board's pad nets against the netlist export (parity without KiCad), or as the netlist to audit when none ships.
- `board_stats.py`: layers, stackup, finish, track classes, vias, fills and plane pieces, drill table, parts, and DFM evidence.

## Install

**Claude app:** download [`pcb-audit.skill`](pcb-audit.skill) (click the file, then **Download**) and add it under **Settings → Capabilities → Skills → Upload skill**.

**Claude Code:** copy the [`skill/`](skill/) folder into `~/.claude/skills/pcb-audit/`.

## Browse the source

- [`skill/SKILL.md`](skill/SKILL.md): the skill itself: stance, tiers, report format, per-gate checks.
- [`skill/references/`](skill/references/): per-gate audit procedure with the sign-off sweep, report template, lessons learned.
- [`skill/scripts/`](skill/scripts/): check scripts with self-tests, documented in [`scripts/README.md`](skill/scripts/README.md).
- [`CHANGELOG.md`](CHANGELOG.md)

The `.skill` file is a zip of the `skill/` folder.

# pcb-audit

Independent audit of an existing KiCad 10 project for JLCPCB, gate by gate: requirements and single-fault table, live part checks, datasheet claims traced to pages, ERC and pin-by-pin netlist audit, decoupling assignment, footprints, DRC with a justified allowlist, layout lints, stale values and claims, revision parity, BOM/CPL consistency. Each audit writes `docs/audits/gate<N>-<date>.md` with finding IDs, evidence, severity and a verdict. Works stand-alone on any KiCad 10 project and as the gate review of the [pcb-design](../pcb-design/) workflow.

New in this skill: the `Decouples` field convention and `check_decoupling.py`, which checks that each decoupling capacitor serves the pin it was added for (right net, at the pin, fed pin → cap → via rather than through the plane, nearest cap is the assigned one) — something the ratsnest cannot show.

## Install

**Claude app:** download [`pcb-audit.skill`](pcb-audit.skill) (click the file, then **Download**) and add it under **Settings → Capabilities → Skills → Upload skill**.

**Claude Code:** copy the [`skill/`](skill/) folder into `~/.claude/skills/pcb-audit/`.

## Browse the source

- [`skill/SKILL.md`](skill/SKILL.md): the skill itself, stance, per-gate checks, findings format.
- [`skill/references/`](skill/references/): per-gate audit procedure, report template, lessons learned.
- [`skill/scripts/`](skill/scripts/): check scripts with self-tests, documented in [`scripts/README.md`](skill/scripts/README.md).
- [`CHANGELOG.md`](CHANGELOG.md)

The `.skill` file is a zip of the `skill/` folder.

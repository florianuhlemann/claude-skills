# pcb-design

Gated workflow for designing PCBs in KiCad 10 for JLCPCB fabrication and economic assembly: requirements → architecture → datasheet read → schematic → library → layout → production → retrospective. Ships design rules, LCSC sourcing, checklists, doc templates and `kicad-cli` scripts for ERC/DRC, library build, production export and CPL rotation fixes. Its checking counterpart is the separate **pcb-audit** skill, which audits the project at every gate.

## Install

**Claude app:** download [`pcb-design.skill`](pcb-design.skill) (click the file, then **Download**) and add it under **Settings → Capabilities → Skills → Upload skill**.

**Claude Code:** copy the [`skill/`](skill/) folder into `~/.claude/skills/pcb-design/`.

## Browse the source

- [`skill/SKILL.md`](skill/SKILL.md): the skill itself, rules and workflow.
- [`skill/references/`](skill/references/): JLCPCB rules, calculations, checklists, doc templates, lessons learned.
- [`skill/scripts/`](skill/scripts/): sourcing, library and export scripts, documented in [`scripts/README.md`](skill/scripts/README.md).
- [`skill/assets/`](skill/assets/): KiCad design rules file and rotation corrections.
- [`CHANGELOG.md`](CHANGELOG.md)

The `.skill` file is a zip of the `skill/` folder.

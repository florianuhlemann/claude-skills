# claude-skills

Skills I built for use with [Claude](https://claude.ai) (Claude Code and the Claude app).

Each skill lives in its own folder with a short README, a ready-to-upload `.skill` file, and the readable source in `skill/`.

## Skills

| Skill | What it does |
|---|---|
| [pcb-design](pcb-design/) | Gated workflow for designing PCBs in KiCad 10 for JLCPCB fabrication and assembly, with design rules, LCSC sourcing, checklists and `kicad-cli` scripts. |
| [pcb-audit](pcb-audit/) | In preparation: independent audit of an existing KiCad project before ordering. No release yet. |

## Install

**Claude app:** open a skill's folder, download its `.skill` file and add it under **Settings → Capabilities → Skills → Upload skill**.

**Claude Code:** copy the skill's `skill/` folder into `~/.claude/skills/<skill-name>/`.

Each skill's README has the exact links.

## License

[CC BY-SA 4.0](LICENSE). In short:

- You may use, copy and adapt these skills, commercially or not, as long as you give credit and don't present them as your own work.
- Anything you build on top of them must be shared under this same license. No closed or proprietary forks.

Copyright © 2026 Florian Uhlemann.

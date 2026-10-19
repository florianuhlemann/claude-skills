# claude-skills

Public repository of Claude skills. One folder per skill:

```
<skill>/
  README.md        install links, what the skill does
  CHANGELOG.md     version history (outside the bundle)
  <skill>.skill    zip of skill/, with a top-level <skill>/ folder inside
  skill/           SKILL.md (frontmatter: name, description, metadata.version), references/, scripts/, assets/
```

## Roles

The top-level session is the **repo manager**. It owns git (branch, commits,
pushes, pull requests), the root README, this file, `tools/`, and the
version/release decision for each skill. It does not edit a skill's content
itself.

Each skill has a **sub-agent** in `.claude/agents/<skill>.md`, running on
Opus. Content work on a skill (SKILL.md, references, scripts, assets,
bundle, changelog entry) is delegated to that agent with a brief:
what to change, which version to target, and any user feedback verbatim.
The agent edits only its own folder, rebuilds the bundle, runs the checks,
and reports back. The manager reviews the diff, commits and opens the PR.

| Skill | Agent | State |
|---|---|---|
| `pcb-design/` | `.claude/agents/pcb-design.md` | design and deliver: gates 1–8, library, layout, production chain |
| `pcb-audit/` | `.claude/agents/pcb-audit.md` | check: per-gate audit of an existing project, run at every ⏸ gate of pcb-design |

The two skills install separately, so each ships every script it runs. A
script both need exists in both folders, byte-identical apart from a header
line naming the source skill; the check scripts (`drc_gate.py`,
`lint_stale_values.py`) are sourced in `pcb-audit`, infrastructure
(`sexpr.py`, `kicad_env.sh`) in `pcb-design`. Whoever changes a shared
script briefs the other agent to refresh its copy in the same release. The
findings format (`A<gate>-<nn>`, severities, status words) and the
`Decouples` field convention are shared vocabulary and change only in both
skills at once.

## Rules that apply to every skill

- **No personal data** in anything under a skill folder except the
  copyright line in `LICENSE` and the root README: no names, e-mail
  addresses, project names, board names, customer names, file paths from a
  private machine. Earlier boards are "the first board", "the second
  board". `tools/check_private.sh <skill>` must pass before a commit.
- **Version** in `skill/SKILL.md` frontmatter (`metadata.version`) and a
  dated entry at the top of `CHANGELOG.md` for every change that ships.
- **Bundle** rebuilt with `tools/build_skill.sh <skill>` whenever anything
  under `skill/` changes; never edit the `.skill` zip by hand.
- **Scripts** are Python 3 standard library or bash (the one exception is
  `sync_models.py`, which needs KiCad's bundled Python for `pcbnew` and says
  so in its header), carry a `--self-test` where they check something, and `python3 -m py_compile` / `bash -n` must
  be clean. Everything a skill's workflow needs ships inside the skill;
  a script that is not needed is deleted, not parked elsewhere.
- Commit messages describe the skill and version ("pcb-design 0.6.0: …").
- `__pycache__/` and `.DS_Store` are ignored and must not be committed.

## Tools

- `tools/build_skill.sh <skill>`: rebuilds `<skill>/<skill>.skill` from `<skill>/skill/`.
- `tools/check_private.sh <skill>`: greps the skill folder for e-mail
  addresses and for the terms in `.private-terms.txt` (git-ignored, one
  regex per line, kept locally so the terms themselves never land in the
  public repo).
- `tools/check_skill.sh <skill>`: syntax check of all scripts, self-tests,
  frontmatter/version sanity, bundle freshness, privacy check. Run before
  every commit that touches a skill.

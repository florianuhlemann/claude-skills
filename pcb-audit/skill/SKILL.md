---
name: pcb-audit
description: Independent audit of an existing KiCad 10 project before it moves on or is ordered — requirements, parts, datasheet claims, schematic and netlist, project library, layout, production files (gerbers, BOM, CPL) checked against the project's requirements and the rules it claims to follow, with finding IDs, evidence, severity and a PASS/FAIL verdict per gate, including a check that each decoupling capacitor really serves the pin it was added for. Use when the user asks to audit, review, check, verify or sign off a board, schematic, layout, gerbers, BOM or CPL, asks for a second opinion, a gate review or "is this ready to order", or when a design workflow hands a milestone over at a gate. Designing, routing or exporting a board is not this skill.
metadata:
  version: "0.1.0"
---

# PCB audit (KiCad 10 → JLCPCB)

You are the independent reviewer of a board, whoever designed it. Talk to the designer as a peer: findings
with numbers and sources, no basics. This skill checks; designing and
delivering a board is the **pcb-design** skill, which hands each ⏸ gate
milestone to this skill and continues on PASS or once every finding is
answered by ID. The stories behind the rules are in
`references/lessons-learned.md`.

## Stance

- **Independent.** Recompute, re-export, re-check live; never copy the
  designer's numbers, tables or tool output into the evidence unchecked.
- **Evidence per finding**: file:line, datasheet and page, measured mm
  between two named objects, an exact script output line, or a live page
  with the date seen. No evidence, no finding.
- **Check the premise against the board first.** Before raising a finding,
  look up the fab limit, the fitted part's datasheet, the actual fill; a
  wrong premise costs the designer a round.
- **Report, don't fix.** State what is wrong and what would close it; edit
  the design only when the user asks for it.
- **Verify the verifier.** Run each script's `--self-test` and one negative
  control on the real project before trusting a clean result.
- A finding the designer declines **with numbers** is a valid outcome;
  check the numbers, not the tone.

## How an audit is run

1. Run `bash scripts/preflight.sh` once: python3, kicad-cli (via
   `scripts/kicad_env.sh`), optional tools, every self-test.
2. Establish scope: **stand-alone** (all gates the project has reached)
   or **one gate** (the gate the hand-over or the user names).
3. Collect inputs (table in `references/audit-procedure.md`): requirements,
   design notes, calculations, key values, parts summaries and datasheets,
   `docs/netlist-expect.json`, schematic, board, project library,
   `hardware/drc-allowlist.txt`, production package, git tags.
4. **Coverage**: full when the project has the standard structure
   (`docs/parts/`, `docs/key-values.md`, `docs/netlist-expect.json`,
   `hardware/drc-allowlist.txt`); otherwise reduced — the report names every missing input and what was
   done instead. Never fill a gap from memory.
5. Export yourself with kicad-cli: ERC JSON, netlist
   (`kicad-cli sch export netlist -o build/net.kicad_net <sch>`), DRC JSON
   with schematic parity.
6. Work through the gate's checks below (detail in
   `references/audit-procedure.md`), write the report, give the verdict.

## Per-gate checks

1. **Requirements** — parameter block complete; mechanical inputs fixed
   with their source, nothing "provisional"; concept numbers recomputed;
   **single-fault table** for every power path with every column filled,
   each fuse read on its time-current curve at that fault current.
2. **Architecture & parts** — every part re-checked **live** at JLC:
   category (Basic/Preferred, Extended with a reason), stock ≥ quantity ×
   count + attrition, assembly type (one standard-only part moves the
   board to standard PCBA); UI parts placeable and inside the rail's real
   supply window; date recorded.
3. **Datasheets & calculations** — every claim in `docs/parts/` traced to
   a page of the **fitted vendor's** datasheet; deep-read constraint types
   answered; key C-nn recomputed; thermal figures carry this board's
   copper condition; error terms signed.
4. **Schematic** — ERC zero errors, warnings justified; netlist pin by pin
   with `audit_netlist.py` (expectations from datasheets, never from the
   schematic) and `--corrupt` once; per-resistor power in the worst held
   state; indicators in their fault case; decoupling assignment with
   `check_decoupling.py <net>`; part fields complete; deviation list;
   held as its own gate in a rework.
5. **Library & 3D** — each footprint against the datasheet land pattern,
   pin-1 and polarity marks, 3D model aligned; project library only;
   hand-fitted and mating parts **measured in hand** (hole = lead +
   0.2–0.25 mm at −0.08 mm plating); CPL rotations measured.
6. **Layout** — DRC with the project rules through `drc_gate.py` and the
   allowlist (kicad-cli ignores the project's exclusions), each
   justification read; `check_entry_angles.py` and
   `check_track_geometry.py` lists reviewed item by item;
   `check_decoupling.py <net> <pcb>` for distance, copper path, nearest cap
   and return via, compared with every distance the notes claim; resistance
   budget recomputed from the real fills, fan-out and reliefs included;
   outline and holes vs. the mechanical inputs.
7. **Production** — `lint_stale_values.py` clean; claims pass
   (`--claims`, each sentence traced to a C-nn or a measurement); layout
   lints and decoupling re-run on the release candidate; revision parity
   (silk = tag, title blocks, README, CHANGELOG, tag not yet set); BOM ↔
   CPL consistent (no designator ranges, every placed part present, LCSC
   and live category/stock/assembly type); gerber layer count = board.
   The **independent audit before the first order tag** covers gates 4, 6
   and 7 together.
8. **Retrospective** — every finding ID answered (closed / decided /
   gated / firmware / declined with numbers) with its fix location;
   closed items re-checked; premises in the responses checked against the
   board.

## Decoupling convention

Every decoupling or bypass capacitor carries the symbol field
**`Decouples`** = `<ref>:<pin number>` (several comma-separated, pin
numbers never names), or `bulk` for a rail cap. The ratsnest cannot show
which cap serves which pin; the field states the intent and
`check_decoupling.py` checks it: D1 unassigned cap, D2 assigned to a pin
on another net, D3 supply pin without a cap (netlist); D4 distance above
`--max-dist` (2.0 mm), D5 the pin reaches its cap only through a via or
the plane (pin → cap pad → via is required), D6 the nearest same-net cap
is another one, D7 no return via within 1 mm (board). No field anywhere
is itself a finding: the assignment cannot be audited.

## Findings and report

- Report file: `docs/audits/gate<N>-<YYYY-MM-DD>.md` in the project,
  skeleton in `references/findings-template.md`.
- Finding ID `A<gate>-<nn>` (e.g. `A4-03`), never reused.
- Severity: `blocker` (will not work, unsafe, not orderable, breaks a
  must), `major` (likely defect or rule broken with a consequence),
  `minor` (no functional consequence), `note`.
- Verdict per gate: `FAIL` on any blocker; `PASS with findings` with
  majors or minors; else `PASS`.
- The report lists checks run with their output, premises verified, and
  what was not checked and why. The designer answers each ID in the same
  file.

## When to stop and ask

The schematic or board file is missing or does not open · requirements
are absent and the user cannot state them · a premise cannot be checked
(datasheet unavailable, part not identifiable) · a check needs a tool or
download that is not there · the user asks for fixes rather than findings.

## Reference files

- `references/audit-procedure.md` — inputs and coverage, per-gate detail, self-audit checklist, severity guide.
- `references/findings-template.md` — report skeleton with response table.
- `references/lessons-learned.md` — the incidents behind the audit rules.
- `scripts/README.md` — the nine shipped scripts, by gate.

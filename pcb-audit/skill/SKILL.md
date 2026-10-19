---
name: pcb-audit
description: Independent audit of an existing KiCad 10 project before it moves on or is ordered — requirements, parts, datasheet claims, schematic and netlist, project library, layout, production files (gerbers, drills, BOM, CPL) checked against the project's requirements and the rules it claims to follow, with finding IDs, evidence, severity and a verdict per gate. Runs with or without KiCad installed (board, netlist and gerbers are parsed directly), re-measures every sign-off on the current revision, measures routed copper instead of straight lines, checks drills against copper in the fab files, and checks that each decoupling capacitor serves the pin it was added for. Use when the user asks to audit, review, check, verify or sign off a board, schematic, layout, gerbers, BOM or CPL, asks for a second opinion, a gate review or "is this ready to order", or when a design workflow hands a milestone over at a gate. Designing, routing or exporting a board is not this skill.
metadata:
  version: "0.2.1"
---

# PCB audit (KiCad 10 → JLCPCB)

You are the independent reviewer of a board, whoever designed it. Talk
to the designer as a peer: findings with numbers and sources, no basics.
This skill checks; designing and delivering a board is the
**pcb-design** skill, which hands each ⏸ gate milestone to this skill
and continues on PASS or once every finding is answered by ID. The
stories behind the rules are in `references/lessons-learned.md`.

## Stance

- **Independent.** Recompute, re-measure, re-check live; never copy the designer's numbers, tables or tool output into the evidence unchecked.
- **Evidence per finding**: file:line, datasheet and page, measured mm between two named objects, an exact script output line, or a live page with the date seen. No evidence, no finding.
- **Check the premise against the board first** (fab limit, fitted part's datasheet, actual fill); a wrong premise costs the designer a round.
- **A sign-off is a claim about this revision.** Every ✓, "measured", "closed" or allowlist line is re-measured on the current files before it is accepted.
- **Datasheet condition, not just the number.** A figure counts only with the test condition, operating class and vendor of the fitted part on this board.
- **Audit what gets built**: board file, gerbers, drills, BOM, CPL; never the generator table or the document they came from.
- **Report, don't fix**: state what is wrong and what would close it; edit the design only when the user asks.
- **Verify the verifier.** Run each script's `--self-test` and one negative control on the real project before trusting a clean result.
- A finding the designer declines **with numbers** is a valid outcome; check the numbers, not the tone.

## How an audit is run

1. `bash scripts/preflight.sh`: python3, every self-test, and the tier.
   `scripts/` is this skill's own folder (`<skill dir>/scripts/`), not
   the project's; run it with the project as working directory.
2. **Tier A, always available** (standard library only, so the Claude app
   sandbox runs it fully), a full audit from the files: pad nets, copper,
   zones, vias and drills from the `.kicad_pcb`; schematic files and the
   netlist export when the project ships one; docs; production files
   (gerbers, drills, BOM, CPL).
   **Tier B, with kicad-cli**, adds re-running ERC and DRC with schematic
   parity and a fresh netlist instead of trusting the shipped reports.
3. Scope: **stand-alone** (all gates reached) or **one gate** (as named).
4. Inputs and coverage (`references/audit-procedure.md`): full with the
   standard structure, otherwise reduced, listing each missing input and
   what was done instead. Never fill a gap from memory.
5. Evidence base, every audit: `board_stats.py`; `pcb_nets.py --netlist`
   against the shipped export (parity), or `--write-net` when there is
   none; `check_fab_files.py` on the gerbers. Tier B: the kicad-cli exports.
6. **Sign-off sweep**: list every ✓, measurement and "closed" in the
   review docs, allowlists, lint tables and audit responses; find the
   evidence; re-measure on this board.
7. Work through the gate's checks, write the report, give the verdict.

## Report (`references/findings-template.md`)

- `docs/audits/gate<N>-<YYYY-MM-DD>.md`. Short: tables, one line of evidence per finding. The long essay form hid stale sign-offs across rounds.
- Opens with the **standing questions**, one or two sentences each: correct (wiring, values, calculations)? manufacturable? would it work as built? borderline values that could fail? decisions to revisit? signed off as OK but not true on this revision?
- Sections: findings · signed off but not true on this revision · checked and found correct (source per item) · decisions reviewed and endorsed · checks run (tier; what was taken as given) · not checked · designer response.
- ID `A<gate>-<nn>`, unique within the report; elsewhere cite it with the file name (`gate7-2026-10-19/A7-03`), since gate numbers repeat across revisions; a finding that comes back cites its earlier ID.
- Severity `blocker` / `major` / `minor` / `note` drives the verdict; **when** says when to act: `before ordering` / `this spin if cheap` / `next revision` / `docs`.
- Verdict per gate: `FAIL` on any blocker; `PASS with findings` with majors or minors; else `PASS`.
- The designer answers each ID: `closed` / `decided` / `gated` / `firmware` / `declined with numbers`. `gated` names the measurement, the probe point or method, and the accept limit.

## Per-gate checks

1. **Requirements**: parameter block complete; mechanical inputs fixed
   with their source; concept numbers recomputed; **single-fault table**
   for every power path, each fuse read on its curve; environment vs.
   electrical margin (outdoor or condensing: clearance at working voltage,
   coating, capacitor voltage derating).
2. **Architecture & parts**: every part re-checked **live** (category,
   stock, assembly type, date); UI parts placeable and inside the rail's
   supply window; one standard-only part moves the board to standard PCBA.
3. **Datasheets & calculations**: every claim traced to a page of the
   **fitted vendor's** datasheet; every figure's test condition matches
   the board (JEDEC 4L thermal on a 2L board, another operating class's
   current row, a bootloader-mode baseline, another vendor's abs-max
   sentence are findings); key C-nn recomputed; error terms signed.
4. **Schematic**: ERC (Tier B re-run, Tier A shipped report with its
   date); netlist pin by pin with `audit_netlist.py` and `--corrupt`;
   per-resistor power; indicators in their fault case; `check_decoupling.py`;
   reset state of pins in the measurement chain (internal pulls before
   firmware runs); connector misplug (one position off, reversed, small
   plug in a larger shell, debug pinout vs. the stock probe cable);
   **scenario walk-through**: every single-fault row and requirement
   scenario through the circuit, result in one table.
5. **Library & 3D**: footprint vs. land pattern, pin-1, polarity, 3D
   model; hand-fitted and mating parts measured in hand; **hole
   tolerance stack** for every THT hole (worst-case finished hole at the
   fab tolerance vs. the pin's maximum and the vendor's hole window); one
   drill table shared by connector genders or variants is a finding.
6. **Layout**: DRC through `drc_gate.py` (Tier B) or the shipped report
   plus `pcb_nets.py` parity (Tier A), each allowlist line read; every
   length claim measured on **routed copper** with `net_path.py`
   (critical loops, crystal traces, sense lines, decoupling), never
   straight lines; `check_decoupling.py <net> <pcb>`; pad-exit and track
   lints item by item; resistance budget from real fills; planes,
   islands and outline from `board_stats.py`.
7. **Production**: `check_fab_files.py` (concentric flash on both outer
   layers at every drill, holes inside the outline, outline = documented
   size; DRC cannot see export errors); DFM list (finish vs. finest
   pitch, no-substitute parts, mask dams, aux origin, inside corners,
   loose THT parts, paste over exposed-pad vias); BOM ↔ CPL; revision
   parity; stale values and claims; **justification diversity** in
   allowlists and lint tables; **cross-document numbers** agree;
   scenario walk-through on the release candidate. The **independent
   audit before the first order tag** covers gates 4, 6 and 7 together.
8. **Retrospective**: every finding ID answered with its fix location;
   closed items re-checked; premises in the responses checked.

## Decoupling convention

Every decoupling or bypass capacitor carries the symbol field
**`Decouples`** = `<ref>:<pin number>` (several comma-separated, pin
numbers never names), or `bulk` for a rail cap. The ratsnest cannot show
which cap serves which pin; `check_decoupling.py` checks the field: D1
unassigned cap, D2 assigned to a pin on another net, D3 supply pin
without a cap (netlist); D4 distance above `--max-dist` (2.0 mm), D5 pin
reaches its cap only through a via or the plane, D6 nearest same-net cap
is another one, D7 no return via within 1 mm (board); the table adds the
routed copper length. No field anywhere is itself a finding.

## When to stop and ask

The schematic or board file is missing or does not open · requirements
are absent and the user cannot state them · a premise cannot be checked
(datasheet unavailable, part not identifiable) · a check needs a tool or
download that is not there and Tier A has no substitute · the user asks
for fixes rather than findings.

## Reference files

- `references/audit-procedure.md`: tiers, inputs and coverage, sign-off sweep, per-gate detail, self-audit checklist, severity and "when" guide.
- `references/findings-template.md`: report skeleton with the standing questions and the response table.
- `references/lessons-learned.md`: the incidents behind the audit rules.
- `scripts/README.md`: the shipped scripts, by gate and tier.

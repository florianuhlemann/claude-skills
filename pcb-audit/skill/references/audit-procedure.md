# Audit procedure, gate by gate

What to check at each gate, against which document, with which script.
Every item that fails becomes a finding with evidence
(`findings-template.md`); every item not checked is listed under "Not
checked" with the reason. Paths are those of a project that follows the
pcb-design structure; on another project, find the equivalent file or
record the gap (see "Coverage" below).

## Contents

- Inputs and coverage
- Before any gate: premises, provenance, negative controls
- Gate 1 requirements · Gate 2 architecture and parts · Gate 3 datasheets and calculations
- Gate 4 schematic · Gate 5 library and 3D · Gate 6 layout · Gate 7 production · Gate 8 audit response and retrospective
- Independent audit before the first order tag
- Self-audit checklist (shared with pcb-design)
- Severity guide

## Inputs and coverage

| Input | Used at gate | If missing |
|---|---|---|
| `docs/requirements.md` (parameter block, must/should/could, mechanical inputs, single-fault table) | 1, all | reduced: requirements taken from the user in the audit request, stated in the report |
| `docs/design-notes.md`, `docs/calculations.md` (C-nn), `docs/key-values.md` | 2–8 | reduced: claims checked against the board only, no traceability check |
| `docs/parts/<mpn>.md`, `docs/datasheets/` | 3, 4 | reduced: datasheets fetched by the auditor, list which |
| `docs/netlist-expect.json` (+ `scripts/netlist_checks.py`) | 4 | reduced: auditor writes a pin map for the ICs it audits, from the datasheets, and says so |
| `hardware/*.kicad_sch`, `*.kicad_pcb`, `*.kicad_pro`, `.kicad_dru` | 4–7 | no schematic/board audit possible: stop and ask |
| `hardware/drc-allowlist.txt` | 6, 7 | every DRC warning becomes a finding until justified |
| `lib/` (manifest, footprints, 3D) | 5 | footprints checked as placed on the board |
| `production/rev<X>/` (gerbers, drill, bom, cpl, pdf, step, erc/drc reports), `production/README.md` | 7 | gate 7 limited to what the user supplies |
| git history and tags | 7, 8 | revision parity checked from title blocks and silk only |

**Full coverage** means every row present. Otherwise the report header
says "reduced coverage", lists the missing rows and what was done instead.
Never fill a gap from memory or from what the design "probably" does.

Exports the auditor makes itself (never reuse the designer's copies
without checking their date against the source files):

```
source scripts/kicad_env.sh
"$KICAD_CLI" sch erc --severity-all --format json -o build/erc.json hardware/<board>.kicad_sch
"$KICAD_CLI" sch export netlist -o build/net.kicad_net hardware/<board>.kicad_sch
"$KICAD_CLI" pcb drc --severity-all --schematic-parity --format json -o build/drc.json hardware/<board>.kicad_pcb
```

Flag spelling differs between KiCad releases: `kicad-cli <cmd> --help`.
Without kicad-cli, ask the designer for these files with their creation
date and say so in the report.

## Before any gate: premises, provenance, negative controls

- **Check each premise against the board before writing a finding.** A
  fab minimum, a datasheet drawing, a neck in a fill, a pin function: look
  it up in the source (JLC's capabilities page, the fitted part's
  datasheet, the board file) and quote it in the evidence. A finding whose
  premise is wrong costs the designer a round; six such findings were
  declined with numbers on one board.
- **Provenance:** expectations come from datasheets, never from a
  generator or from the schematic itself. A `netlist-expect.json` written
  from the schematic checks nothing.
- **Verify the verifier:** run each script's `--self-test`, and the
  negative control on the real project (`audit_netlist.py --corrupt`, or one
  planted fault in a copy). A clean result from a check that was never seen
  failing is not evidence.
- **Lint lists are read item by item.** A list driven to zero or
  justified by one blanket sentence is a finding.
- **Measurements beat drawings and drawings beat memory.** Measure on the
  board file; ask the owner to measure a part in hand where it matters.

## Gate 1 — requirements

Against: `docs/requirements.md`, concept documents, the user's request.

- Parameter block complete (quantity, layers, assembly sides, THT, hand
  assembly, operating range, `calc_ambient`, part rating, supply/cell,
  safety limits, interface connectors, mechanical inputs, safety analysis
  yes/no); each value stated, none "TBD".
- Purpose, users, interfaces, rails, must/should/could; per-channel
  indication asked for multi-channel loads.
- Mechanical inputs fixed (outline, holes, keep-outs, edge-facing ports,
  display mount, battery access, labels), with their source; anything
  "provisional" is a major.
- **Single-fault table** for every power path, every column filled
  (switch shorts · opens · load back-drives · fuse at this fault current on
  its time-current curve · input reversed · what drives the node when the
  load runs on its own). Each cell names a consequence and either the
  protection with its number or an accepted risk. A fuse "covers" a fault
  only if the fault current sits on the fast side of its curve: read the
  curve. Missing path or empty cell = major; a protection that does not
  cover its fault = blocker.
- Assumption audit: every number in a concept document recomputed (rail
  vs. cell current, leakage vs. µA budgets, "protection" that does not
  protect, measurements the chosen parts cannot make).

## Gate 2 — architecture and parts

Against: `docs/design-notes.md` (block diagram, candidate table), the live
JLC parts pages.

- Each candidate has an LCSC number. Re-check **live**, do not copy the
  designer's table: category (Basic / Preferred / Extended, Extended with a
  written reason), stock ≥ `quantity` × count + attrition, assembly type
  (economic vs. standard-only: one standard-only part moves the whole board
  to standard PCBA). Record the date and the values seen in the evidence.
  The parts API may be blocked: search jlcpcb.com/parts by hand.
- UI and display parts: JLC-placeable or a costed hand plan; supply
  window inside the rail's actual min…max over temperature.
- Every rail's consumers sum to the regulator's rating with margin; cost
  stated in one line; placement sketch if the form factor is open.

## Gate 3 — datasheets and calculations

Against: `docs/parts/<mpn>.md`, `docs/datasheets/`, `docs/calculations.md`.

- Every claim in a parts summary traced to a datasheet page (`pdftotext
  -layout <pdf> - | grep -n`, or page by page); the PDF is the **fitted
  vendor's** (ST ≠ TI for a "pin-compatible" part).
- The deep-read constraint types are each answered "applies / value /
  checked": common-mode range in every state (sources off included),
  current-source compliance, settling and turn-on times (units: µs/pF is
  not ms), internal monitor accuracy, wake sources per low-power mode,
  back-feed / pass-through, burn-out sources vs. filters and gain,
  forbidden internal pulls, ESD/abs-max on off-board pins, soldering notes,
  module ranges vs. controller IC, MCU bonded and strapping pins, thermal
  R_θJA with its copper condition, error terms with a sign.
- Calculations: spot-recompute every C-nn that a protection, a rating or a
  key value depends on; thermal figures recomputed for this board's
  layers and copper (JEDEC 4L numbers on a 2L board are a finding).
- `docs/key-values.md` exists, each value used in more than one place is
  listed with its C-nn.

## Gate 4 — schematic

Against: `docs/parts/`, `docs/netlist-expect.json`, reference circuits,
the single-fault table.

1. **ERC** zero errors; every warning justified in writing.
2. **Netlist pin by pin:** `audit_netlist.py build/net.kicad_net`
   (expectations from `docs/parts/`, provenance checked), then `--corrupt`
   once — it must report "corruption detected". Remaining pins by hand
   against the reference circuit **and** the deep-read constraints.
3. **Per-resistor power:** V²/R (or I²R) in the worst held state vs. the
   package rating derated at `calc_ambient`. **Per-indicator fault case:**
   the LED is visibly lit/dark in the fault it exists for, with the real
   V_F and gain. Duplicated parts: own gate resistor, current sharing.
4. **Decoupling assignment:** `check_decoupling.py build/net.kicad_net`
   (no board yet: D1–D3). Every cap on a supply net carries `Decouples`
   (`<ref>:<pin number>` or `bulk`), each assigned cap is on its pin's net,
   each supply pin has its cap or a datasheet reason for sharing.
5. Part fields complete (LCSC, MPN, manufacturer, category with date,
   assembly type, stock, value/tolerance/rating/dielectric/package,
   `Fit`), no standard-only part unless accepted at gate 2.
6. Deviation list exists (pin, reference value, actual, reason); safety
   argument re-run if any value in it changed; placeholders recomputed.
7. In a rework, the schematic is audited as its own gate before layout
   changes are looked at.

## Gate 5 — library and 3D

Against: datasheet land patterns and drawings, the parts in hand.

- Project library only: every symbol and footprint in the board resolves
  to `lib/` (or the project's own library), not to a global library.
- Per footprint: pad size, pitch, courtyard against the datasheet land
  pattern, source named in the footprint description; pin-1 marker points
  at pad 1; polarity mark at the right end; nothing on silk between pads.
- 3D model present and aligned (pins on pads, outline on F.Fab, height);
  a model that disagrees with the datasheet stays open — "cosmetic" is not
  a closure.
- **Hand-fitted and mating parts measured in hand** (lead/tail diameter,
  square-pin diagonal, peg positions): hole = largest measured lead +
  0.2–0.25 mm; at JLC's −0.08 mm plating tolerance still ≥ +0.1 mm
  clearance; mating gender confirmed on the real counterpart; reliefs on
  hand-soldered pads.
- CPL rotation of each JLC-placed part measured from JLC's footprint and
  recorded as "measured".

## Gate 6 — layout

Against: the board file, `docs/calculations.md`, the mechanical inputs.

1. **DRC** with the project's `.kicad_dru`, schematic parity on:
   `drc_gate.py build/drc.json hardware/drc-allowlist.txt` must pass. Read
   each allowlist justification; one that does not hold is a finding.
   kicad-cli 10 ignores DRC exclusions stored in the project, so a clean
   GUI DRC is not evidence.
2. **Pad exits:** `check_entry_angles.py`; **track geometry:**
   `check_track_geometry.py`. Each listed item has a justification in the
   design notes or becomes a finding.
3. **Decoupling at the pin:** `check_decoupling.py build/net.kicad_net
   hardware/<board>.kicad_pcb` (D4–D7: distance, copper path pin → cap pad
   → via, nearest cap is the assigned one, return via). Compare with every
   distance the design notes claim; a claimed "1–2 mm" that measures 6 mm
   is a finding on the claim as well.
4. **Resistance budget:** for each power path, recompute from the real
   fills including pin fan-out and thermal reliefs; measure the narrowest
   neck on the board. Compare with `calculations.md`.
5. Outline, holes, cut-outs, edge-facing ports match the mechanical
   inputs; body-to-edge ≥ 2.5 mm; silk revision = planned tag; silk text ≥
   1.0 mm, nothing over pads; test points labelled by function.
6. Continuous GND under every signal, inner GND unbroken, stitching grid,
   RF fenced and impedance per stack; matched groups only above the
   threshold with the skew recorded; 2-layer boards: converter keep-outs,
   FB/sense routing, return paths, SW-to-sensitive distances.
7. Real 3D models everywhere; placeholders listed.

## Gate 7 — production

Against: `production/rev<X>/`, `production/README.md`, `CHANGELOG.md`,
git tags, the live JLC pages.

- ERC/DRC reports in the package are from the current files (dates,
  re-run and compare); `drc_gate.py` passes.
- **Stale values:** `lint_stale_values.py <project>` clean.
- **Claims pass:** `lint_stale_values.py <project> --claims`; each listed
  sentence traced to a C-nn or a measurement, or the claim is a finding.
  This replaces the layout lints and claims list that the export chain
  used to print: run gate 6 items 2–3 again on the release candidate.
- **Revision parity:** silk revision = tag about to be set; title blocks,
  README, CHANGELOG and package folder name carry the same revision and
  date; the tag does not exist yet.
- **BOM/CPL consistency:** every BOM designator appears in the CPL and
  vice versa (DNP, hand-fit and excluded parts accounted for); no
  designator ranges (`R1-R5`) left in either file; LCSC on every JLC line;
  category, stock and assembly type re-checked live; standard-only and
  Extended parts counted in the README; THT parts in the CPL; rotations
  checked in JLC's preview on order day.
- Gerbers: copper layer count equals the board's; drill files present;
  STEP exported; hand-fit BOM and plan present if any part is hand-fitted.

## Gate 8 — audit response and retrospective

Against: the designer's response table, the board.

- Every finding ID answered: `closed` (fix in the files, check re-run),
  `decided`, `gated` (names the gate and criterion), `firmware`, or
  `declined with numbers`. A decline with numbers that refute the premise
  is a valid answer; the auditor checks the numbers, not the tone.
- Re-run the checks behind each `closed` item; an ID without an answer
  keeps the gate open.
- After release: `docs/retrospective.md` exists; lessons recorded.

## Independent audit before the first order tag

Run gates 4, 6 and 7 together on the release candidate before the first
tag, not after each tag. Three audits after three tags, merged into one,
would have saved two releases.

## Self-audit checklist (shared with pcb-design)

Copied verbatim from pcb-design's self-audit checklist (0.6.0); keep
identical. The auditor confirms each step was done and repeats 1 and
1a itself.

1. Export the netlist; `audit_netlist.py` checks every pin in `docs/netlist-expect.json` (written from `docs/parts/`, never from a generator) and runs the project's `scripts/netlist_checks.py` if present; run `--corrupt` once (negative control). Then compare the remaining pins by hand against the reference circuit **and** the deep-read constraint list.
1a. **Per-resistor power check**: V²/R (or I²R) in the worst held state vs. package rating derated at `calc_ambient` — a 1 kΩ 0603 gate pull-down at 159 mW passed three readings. **Per-indicator failure case**: the LED must be visibly dark/lit in the fault it exists for (open load, blown fuse), computed with the real V_F and gain.
1b. Duplicated parts (paralleled FETs, extra channels): re-run the paralleling checks (own gate resistor per device, current sharing, sense). Placeholders marked "finalised in schematic" are recomputed now.
2. Write the deviation list (pin, reference value, actual, reason); fix or justify.
3. Re-run the safety argument if any value in it changed.
4. Put the lists into `docs/design-notes.md` under the component; update `docs/key-values.md`.

## Severity guide

| Severity | Use when | Examples |
|---|---|---|
| `blocker` | The board will not work, is unsafe, cannot be ordered, or breaks a must requirement | wrong pin wired; protection that does not cover its fault; cap assigned to a pin on another net; DRC error; part not orderable |
| `major` | Likely defect or a rule broken with a consequence; answered before the next gate | decoupling 6 mm from its pin; unjustified DRC warning; untraced protection claim; Extended part without reason |
| `minor` | Deviation without functional consequence | missing GND via at a cap; silk label below 1.0 mm; naming |
| `note` | Observation, no action required | alternative part with better stock |

Verdict per gate: any blocker → `FAIL`; majors or minors only → `PASS
with findings`; notes only or nothing → `PASS`.

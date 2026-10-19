# Audit procedure, gate by gate

What to check at each gate, against which document, with which script.
Every item that fails becomes a finding with evidence
(`findings-template.md`); every item not checked is listed under "Not
checked" with the reason. Paths are those of a project that follows the
pcb-design structure; on another project, find the equivalent file or
record the gap (see "Coverage" below).

## Contents

- Two tiers: with and without kicad-cli
- Inputs and coverage
- Before any gate: premises, provenance, negative controls
- Sign-off sweep
- Gate 1 requirements · Gate 2 architecture and parts · Gate 3 datasheets and calculations
- Gate 4 schematic · Gate 5 library and 3D · Gate 6 layout · Gate 7 production · Gate 8 audit response and retrospective
- Independent audit before the first order tag
- Self-audit checklist
- Severity, "when" and status guide

## Two tiers: with and without kicad-cli

An auditor working in a sandbox (the Claude app, a reviewer's laptop)
usually has no KiCad; the designer has. Both are full audits. Tier A is
the files themselves and is always run; Tier B adds what only KiCad can
recompute. `bash scripts/preflight.sh` prints the tier.

| Check | Tier A: files, always | Tier B: with kicad-cli, in addition |
|---|---|---|
| Netlist | shipped export (date against the `.kicad_sch` files) compared with the board: `pcb_nets.py <pcb> --netlist <net>`; no export shipped: `pcb_nets.py <pcb> --write-net build/pcb.kicad_net` and audit that (the board as built; schematic = board is then not provable, say so) | fresh export from the schematic, then the same parity run against it |
| ERC | shipped report read: date, severity settings, errors and warnings; taken as given | re-run, compared with the shipped report |
| DRC | shipped report read (date, rules file, exclusions); parity from `pcb_nets.py`; fab minimums from `board_stats.py` (narrowest track per class, via and drill table); clearance itself taken as given | re-run with the project rules and schematic parity through `drc_gate.py` |
| Copper, zones, lengths | `board_stats.py`, `net_path.py`, `check_decoupling.py`, pad-exit and geometry lints: all read the board file | same |
| Fab files | `check_fab_files.py` on the shipped gerbers/drills (folder or `gerbers.zip`), `--board` and `--size` | same; a fresh export does not replace the files that will be ordered |
| BOM / CPL | CSVs read and cross-checked against the board | same |
| Live parts data | JLC/LCSC pages when reachable; otherwise the project's dated table, named as taken as given | same |

The report's "Checks run" names the tier and, for each item taken as
given, what it was and its date: shipped ERC/DRC reports, live stock not
reachable, physical checks not possible (part in hand, render review).

Tier B exports (never reuse the designer's copies without checking their
date against the source files):

```
source scripts/kicad_env.sh
"$KICAD_CLI" sch erc --severity-all --format json -o build/erc.json hardware/<board>.kicad_sch
"$KICAD_CLI" sch export netlist -o build/net.kicad_net hardware/<board>.kicad_sch
"$KICAD_CLI" pcb drc --severity-all --schematic-parity --format json -o build/drc.json hardware/<board>.kicad_pcb
```

Flag spelling differs between KiCad releases: `kicad-cli <cmd> --help`.

## Inputs and coverage

| Input | Used at gate | If missing |
|---|---|---|
| `docs/requirements.md` (parameter block, must/should/could, mechanical inputs, single-fault table) | 1, all | reduced: requirements taken from the user in the audit request, stated in the report |
| `docs/design-notes.md`, `docs/calculations.md` (C-nn), `docs/key-values.md` | 2–8 | reduced: claims checked against the board only, no traceability check |
| `docs/parts/<mpn>.md`, `docs/datasheets/` | 3, 4 | reduced: datasheets fetched by the auditor, list which |
| `docs/netlist-expect.json` (+ `scripts/netlist_checks.py`) | 4 | reduced: auditor writes a pin map for the ICs it audits, from the datasheets, and says so |
| netlist export (`*.kicad_net`, in the package or `build/`) | 4, 6 | Tier A: `pcb_nets.py --write-net`; parity not provable, say so |
| `hardware/*.kicad_sch`, `*.kicad_pcb`, `*.kicad_pro`, `.kicad_dru` | 4–7 | no schematic/board audit possible: stop and ask |
| `hardware/drc-allowlist.txt` | 6, 7 | every DRC warning becomes a finding until justified |
| review documents (`docs/review/`, layout and lint tables, earlier `docs/audits/`) | sweep, 6–8 | nothing to sweep; record it |
| `lib/` (manifest, footprints, 3D) | 5 | footprints checked as placed on the board |
| `production/rev<X>/` (gerbers, drill, bom, cpl, pdf, step, erc/drc reports), `production/README.md` | 7 | gate 7 limited to what the user supplies |
| git history and tags | 7, 8 | revision parity checked from title blocks and silk only |

**Full coverage** means every row present. Otherwise the report header
says "reduced coverage", lists the missing rows and what was done instead.
Never fill a gap from memory or from what the design "probably" does.

## Before any gate: premises, provenance, negative controls

- **Check each premise against the board before writing a finding.** A
  fab minimum, a datasheet drawing, a neck in a fill, a pin function: look
  it up in the source (the fab's capabilities page, the fitted part's
  datasheet, the board file) and quote it in the evidence. A finding whose
  premise is wrong costs the designer a round; six such findings were
  declined with numbers on one board.
- **Provenance:** expectations come from datasheets, never from a
  generator or from the schematic itself. A `netlist-expect.json` written
  from the schematic checks nothing.
- **Audit what gets built.** Board file, gerbers and drills, BOM, CPL.
  When the schematic or board is generated from tables, audit the
  generated file; the table is the designer's intent, not the product.
- **Verify the verifier:** run each script's `--self-test`, and the
  negative control on the real project (`audit_netlist.py --corrupt`, or one
  planted fault in a copy). A clean result from a check that was never seen
  failing is not evidence.
- **Lint lists are read item by item.** A list driven to zero or
  justified by one blanket sentence is a finding.
- **Measurements beat drawings and drawings beat memory.** Measure on the
  board file; ask the owner to measure a part in hand where it matters.

## Sign-off sweep

The strongest findings in late audit rounds were sign-offs that had been
true once. Before the gate checks, list every claim the project makes
about itself and re-measure it on the current files.

**Where to look:** `docs/review/` and layout reports (distance and loop
tables, deviation acceptances), `docs/calculations.md` rows marked ✓,
`docs/key-values.md`, `hardware/drc-allowlist.txt`, lint tables, earlier
audit reports and their response tables, CHANGELOG lines saying
"closed" or "fixed", `production/README.md` "verified" items.

**Per sign-off:** what is claimed · the evidence behind it (which
revision, measured how) · the measurement now (tool and output) ·
verdict. A failed one goes to "Signed off as OK but not true on this
revision" with the original claim, the new number and where the claim
is repeated.

Classes seen so far:

- a measurement from an earlier revision cited after a re-route (a
  loop length accepted with its number, the board re-routed twice
  since): every length on a re-routed board is re-measured with
  `net_path.py`
- a distance measured as a straight line (decoupling "pad to pin"
  table): routed copper with `net_path.py` or the routed column of
  `check_decoupling.py`, via count included
- a tick against a nominal value while the worst case is outside (a
  drill ✓ whose finished hole at the fab's tolerance leaves the
  vendor's window): gate 5 tolerance stack
- a lint table "closed" with template sentences (see justification
  diversity below)
- a claim traced to a C-nn whose input value has since changed
- an audit item marked `closed` whose check was never re-run
- right conclusion, wrong number or reason: the conclusion stands, the
  number is corrected so the next reader does not design around it

**Justification diversity.** Count distinct justification strings
against rows in every allowlist and lint table; a handful of sentences
over a hundred rows is class waving, a finding unless the project says
once, by class, why the lint does not apply and changes the lint:

```
sed -n 's/.* # //p' hardware/drc-allowlist.txt | sort | uniq -c | sort -rn | head
awk -F'|' 'NF > 3 { print $(NF-1) }' docs/review/<lint-table>.md | sort | uniq -c | sort -rn | head
```

**Cross-document numbers.** The same quantity stated in several
documents (board size, a margin, a drop, a loop length, a current
budget) must agree. Reading task: list each quantity with every place
it appears and its value there; a mismatch is a finding on every copy
but the one that is measured. `lint_stale_values.py` sees only
key-values entries.

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
- **Environment vs. electrical margin.** An outdoor, unheated or
  condensing installation needs the electrical side to match: clearance
  between nets at their working voltage (electrochemical migration on an
  uncoated board), conformal coating or a decision against it, capacitor
  voltage derating at the real supply, high-impedance inputs vs. surface
  leakage, contact materials vs. the sense current and voltage.
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
  Not reachable from the sandbox: take the project's dated table, say so.
- UI and display parts: JLC-placeable or a costed hand plan; supply
  window inside the rail's actual min…max over temperature.
- Every rail's consumers sum to the regulator's rating with margin; cost
  stated in one line; placement sketch if the form factor is open.

## Gate 3 — datasheets and calculations

Against: `docs/parts/<mpn>.md`, `docs/datasheets/`, `docs/calculations.md`.

- Every claim in a parts summary traced to a datasheet page (`pdftotext
  -layout <pdf> - | grep -n`, or page by page); the PDF is the **fitted
  vendor's**, and a family sheet stands only for the values it states for
  the ordered variant (a load capacitance from a shop listing is not a
  datasheet value).
- **Datasheet condition, not just the number.** For every figure a
  calculation uses, the row's test condition and the vendor variant must
  match the fitted part on this board. Findings seen so far: a thermal
  resistance measured on a four-layer JEDEC board (or on 1 in² of 2 oz)
  used on a two-layer 1 oz board; a supply-current row for another
  operating class or bus voltage; a baseline current from the
  bootloader-mode row used for the running application; an
  absolute-maximum sentence from one vendor's datasheet applied to the
  part of another vendor whose table says otherwise; a typical value used
  where the worst case sets the margin.
- The deep-read constraint types are each answered "applies / value /
  checked": common-mode range in every state (sources off included),
  current-source compliance, settling and turn-on times (units: µs/pF is
  not ms), internal monitor accuracy, wake sources per low-power mode,
  back-feed / pass-through, burn-out sources vs. filters and gain,
  forbidden internal pulls, ESD/abs-max on off-board pins, soldering notes,
  module ranges vs. controller IC, MCU bonded and strapping pins, thermal
  R_θJA with its copper condition, error terms with a sign, and where the
  datasheet contradicts itself (a table against a note), which wins and why.
- Calculations: spot-recompute every C-nn that a protection, a rating or a
  key value depends on, with the values actually in the netlist.
- `docs/key-values.md` exists, each value used in more than one place is
  listed with its C-nn.

## Gate 4 — schematic

Against: `docs/parts/`, `docs/netlist-expect.json`, reference circuits,
the single-fault table.

1. **ERC** zero errors; every warning justified in writing. Tier A: the
   shipped report, its date against the schematic files, taken as given.
2. **Netlist pin by pin:** `audit_netlist.py build/net.kicad_net`
   (expectations from `docs/parts/`, provenance checked), then `--corrupt`
   once — it must report "corruption detected". Tier A without an export:
   the same on `pcb_nets.py --write-net` output. Remaining pins by hand
   against the reference circuit **and** the deep-read constraints.
3. **Per-resistor power:** V²/R (or I²R) in the worst held state vs. the
   package rating derated at `calc_ambient`. **Per-indicator fault case:**
   the LED is visibly lit/dark in the fault it exists for, with the real
   V_F and gain. Duplicated parts: own gate resistor, current sharing.
4. **Decoupling assignment:** `check_decoupling.py build/net.kicad_net`
   (no board yet: D1–D3). Every cap on a supply net carries `Decouples`
   (`<ref>:<pin number>` or `bulk`), each assigned cap is on its pin's net,
   each supply pin has its cap or a datasheet reason for sharing.
5. **Reset state of pins in the measurement chain.** Before firmware runs,
   MCU pins sit with their reset pulls (often pull-downs on every GPIO);
   compute the node voltage of each sense input with every reset pull on
   it (inputs and drive pins on the same node) against V_IL/V_IH. A node
   biased into a valid level by reset pulls is a board finding even when
   the fix is firmware (then status `firmware`, with the line in the
   firmware notes).
6. **Connector misplug.** For every connector a person plugs: one
   position off, reversed, a smaller plug in a larger shell (it seats and
   may not latch), a debug header against the pinout of the stock probe
   cable, a supply pin on a debug connector against a live bus. Each case:
   what is connected to what, and whether anything is damaged.
7. **Scenario walk-through.** Every single-fault row and every
   requirement scenario (power-up, normal use, each fault, power loss,
   reverse connection, the load running on its own) walked through the
   circuit with the values in the netlist; one table: scenario · path ·
   result with numbers · OK or finding ID.
8. Part fields complete (LCSC, MPN, manufacturer, category with date,
   assembly type, stock, value/tolerance/rating/dielectric/package,
   `Fit`); no standard-only part unless accepted at gate 2; a part whose
   choice depends on one vendor's abs-max or behaviour is marked
   no-substitute in the BOM.
9. Deviation list exists (pin, reference value, actual, reason); safety
   argument re-run if any value in it changed; placeholders recomputed.
10. In a rework, the schematic is audited as its own gate before layout
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
  square-pin diagonal, peg positions); mating gender confirmed on the real
  counterpart; reliefs on hand-soldered pads.
- **Hole tolerance stack, every THT hole** (`board_stats.py` drill table):

  | Ref | Pin max (diagonal for square pins) | Drill | Finished min…max at the fab's tolerance | Vendor hole window | Clearance min…max per side | Verdict |
  |---|---|---|---|---|---|---|

  JLC finished PTH: about −0.08/+0.13 mm, check the capabilities page on
  the day. Finished minimum ≥ pin maximum + 0.1 mm for hand insertion;
  machine insertion wants lead + 0.2–0.3 mm; press-fit and retention pins
  must stay inside the vendor's window at both ends of the band. One
  drill table shared across connector genders or variants (male and
  female of one series, two pin sizes in one footprint family) is a
  finding class: each variant is checked against its own drawing.
- CPL rotation of each JLC-placed part measured from JLC's footprint and
  recorded as "measured"; polarised parts without a row are a finding.

## Gate 6 — layout

Against: the board file, `docs/calculations.md`, the mechanical inputs.

1. **DRC.** Tier B: project `.kicad_dru`, schematic parity on,
   `drc_gate.py build/drc.json hardware/drc-allowlist.txt` must pass;
   kicad-cli 10 ignores DRC exclusions stored in the project, so a clean
   GUI DRC is not evidence. Tier A: the shipped report with its date and
   rules, `pcb_nets.py --netlist` for parity, `board_stats.py` for track,
   via and drill minimums against the fab. Read each allowlist
   justification; one that does not hold is a finding; check diversity.
2. **Pad exits:** `check_entry_angles.py`; **track geometry:**
   `check_track_geometry.py`. Each listed item has a justification in the
   design notes or becomes a finding.
3. **Routed copper for every length claim.** `net_path.py <pcb> A B`, or
   `--pairs` with the claimed numbers from the review documents: critical
   loops named by a datasheet ("trace between pin X and C < 5 mm"),
   crystal and load-cap traces (both sides: asymmetry is stray load),
   sense and feedback lines, decoupling. A straight-line or pad-edge
   number in a review document is a finding when the routed copper is
   longer than the claim or passes vias; "through the plane" in the
   output means the connection is pin > via > plane.
4. **Decoupling at the pin:** `check_decoupling.py build/net.kicad_net
   hardware/<board>.kicad_pcb` (D4–D7: distance, copper path pin → cap pad
   → via, nearest cap is the assigned one, return via; routed length per
   row). Compare with every distance the design notes claim.
5. **Resistance budget:** for each power path, recompute from the real
   fills including pin fan-out and thermal reliefs; measure the narrowest
   neck on the board. Compare with `calculations.md`.
6. **Planes and fills** (`board_stats.py`): fill pieces per net and layer,
   islands, unfilled zones; continuous reference under every signal, inner
   planes unbroken, stitching grid, RF fenced and impedance per stack;
   matched groups only above the threshold with the skew recorded;
   2-layer boards: converter keep-outs, FB/sense routing, return paths,
   SW-to-sensitive distances.
7. Outline, holes, cut-outs, edge-facing ports match the mechanical
   inputs; body-to-edge ≥ 2.5 mm or the parts below listed for the DFM
   answer; silk revision = planned tag; silk text ≥ 1.0 mm, nothing over
   pads; test points labelled by function. Real 3D models everywhere.

## Gate 7 — production

Against: `production/rev<X>/`, `production/README.md`, `CHANGELOG.md`,
git tags, the live JLC pages.

- **Fab-file alignment** (`check_fab_files.py production/rev<X>/gerbers.zip
  --board hardware/<board>.kicad_pcb --size <W>x<H>`): every plated drill
  has a concentric flash on both outer copper layers, every hole is inside
  the outline, the outline equals the documented board size, the drill
  table and positions equal the board's. DRC cannot see export-stage
  errors; one board shipped drills offset by a whole origin shift.
- ERC/DRC reports in the package are from the current files (dates; Tier
  B: re-run and compare); `drc_gate.py` passes.
- **Stale values:** `lint_stale_values.py <project>` clean.
- **Claims pass:** `lint_stale_values.py <project> --claims`; each listed
  sentence traced to a C-nn or a measurement, or the claim is a finding.
  Run gate 6 items 2–4 again on the release candidate.
- **Cross-document numbers** and **justification diversity** (sign-off
  sweep) on the release candidate.
- **Scenario walk-through** of gate 4 repeated on the release candidate
  when any value or connection changed since.
- **Revision parity:** silk revision = tag about to be set; title blocks,
  README, CHANGELOG and package folder name carry the same revision and
  date; the tag does not exist yet.
- **BOM/CPL consistency:** every BOM designator appears in the CPL and
  vice versa (DNP, hand-fit and excluded parts accounted for); no
  designator ranges (`R1-R5`) left in either file; LCSC on every JLC line;
  category, stock and assembly type re-checked live; standard-only and
  Extended parts counted in the README; THT parts in the CPL; rotations
  checked in JLC's preview on order day.
- **DFM list** (evidence mostly from `board_stats.py`):

  | Item | Check |
  |---|---|
  | Surface finish | HASL on the finest pitch (0.5 mm and below, QFN/DFN pads 0.2–0.25 mm wide) is a finding; ENIG or a written reason |
  | No-substitute parts | a design that relies on one vendor's abs-max, input range or pinout marks that line no-substitute in the BOM and README |
  | Mask dams | smallest pad gap minus twice the mask expansion against the fab's minimum dam at the finest pitch |
  | Aux origin | inside the outline, on a corner; no negative CPL coordinates; gerbers, drills and CPL from the same origin |
  | Outline inside corners | sharp inside corners get the router bit's radius; the case and nearby parts tolerate it |
  | Loose THT parts | single pins, terminals and parts without a feeder package on the economic line: the quote confirms placement, or the hand-solder fallback is written down |
  | Paste over exposed-pad vias | vias or plated holes under a paste opening: tented, plugged, windowed paste, or accepted with X-ray |
  | Body-to-edge | parts closer than the fab's rule listed by ref for the DFM answer |
  | Copper layer count | gerber copper layers = board layers; drill files present; STEP exported; hand-fit BOM and plan present if any part is hand-fitted |

- **Generators:** when the schematic, board or production files come
  from a generator, audit the file that gets built, never the table it
  was generated from; differences between the two are findings on the
  generator's output.

## Gate 8 — audit response and retrospective

Against: the designer's response table, the board.

- Every finding ID answered: `closed` (fix in the files, check re-run),
  `decided`, `gated` (measurement, probe point or method, accept limit),
  `firmware`, or `declined with numbers`. A decline with numbers that
  refute the premise is a valid answer; the auditor checks the numbers,
  not the tone.
- Re-run the checks behind each `closed` item; an ID without an answer
  keeps the gate open. Cite earlier IDs with their report file name.
- After release: `docs/retrospective.md` exists; lessons recorded.

## Independent audit before the first order tag

Run gates 4, 6 and 7 together on the release candidate before the first
tag, not after each tag. Three audits after three tags, merged into one,
would have saved two releases.

## Self-audit checklist

Taken over from pcb-design 0.6.0; pcb-design removed it in 0.7.0, so
this is now its only copy. The auditor confirms each step was done and repeats
1 and 1a itself.

1. Export the netlist; `audit_netlist.py` checks every pin in `docs/netlist-expect.json` (written from `docs/parts/`, never from a generator) and runs the project's `scripts/netlist_checks.py` if present; run `--corrupt` once (negative control). Then compare the remaining pins by hand against the reference circuit **and** the deep-read constraint list.
1a. **Per-resistor power check**: V²/R (or I²R) in the worst held state vs. package rating derated at `calc_ambient` — a 1 kΩ 0603 gate pull-down at 159 mW passed three readings. **Per-indicator failure case**: the LED must be visibly dark/lit in the fault it exists for (open load, blown fuse), computed with the real V_F and gain.
1b. Duplicated parts (paralleled FETs, extra channels): re-run the paralleling checks (own gate resistor per device, current sharing, sense). Placeholders marked "finalised in schematic" are recomputed now.
2. Write the deviation list (pin, reference value, actual, reason); fix or justify.
3. Re-run the safety argument if any value in it changed.
4. Put the lists into `docs/design-notes.md` under the component; update `docs/key-values.md`.

## Severity, "when" and status guide

| Severity | Use when | Examples |
|---|---|---|
| `blocker` | The board will not work, is unsafe, cannot be ordered, or breaks a must requirement | wrong pin wired; protection that does not cover its fault; cap assigned to a pin on another net; DRC error; drills not on their pads in the fab files; part not orderable; abs-max exceeded in a normal state |
| `major` | Likely defect or a rule broken with a consequence; answered before the next gate | decoupling 6 mm from its pin; unjustified DRC warning; untraced protection claim; sign-off not true on this revision with a margin consequence; Extended part without reason |
| `minor` | Deviation without functional consequence | missing GND via at a cap; silk label below 1.0 mm; a stale number with no margin consequence |
| `note` | Observation, no action required | alternative part with better stock |

Verdict per gate: any blocker → `FAIL`; majors or minors only → `PASS
with findings`; notes only or nothing → `PASS`.

**When** (one per finding, independent of severity):

| When | Meaning |
|---|---|
| `before ordering` | changes copper, a part or the order, or a measurement the order depends on |
| `this spin if cheap` | worth doing if the board is touched anyway; otherwise next revision with a check on the first board |
| `next revision` | accepted for this build, recorded for the next |
| `docs` | text, tables or numbers only |

**Status words** (designer's answer): `closed` · `decided` · `gated` ·
`firmware` · `declined with numbers`. A `gated` answer names the
measurement, the probe point or method, and the accept limit
("input spike at the regulator's VIN pin, probe on the pin with a short
ground spring, first full-load turn-off, accept ≤ the recommended
maximum"); "measure on board 1" alone is not an answer.

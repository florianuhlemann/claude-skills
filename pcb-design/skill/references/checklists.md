# Checklists

Gate-1 catalog, self-audit, deep-read constraint types, handover and
audit-response are **mandatory**. Pre-layout and layout lists are
guidelines: work through them, write the result into
`docs/design-notes.md`, note explicitly what was skipped and why.

## Gate 1 — fixed question catalog (ask in one round)

1. Purpose, users, where and how the device is used.
2. Form factor and size envelope; what drives it (holder, cell, display, pocket).
3. **Mechanical inputs** from the case owner: board outline, mounting-hole positions, keep-outs, ports that must face an edge, how a display is mechanically fixed, battery access and polarity marking, label text. (Case design itself is out of scope.)
4. Interface connectors (type, mating part, wire gauge, polarity).
5. Power: cell chemistry / supply, the *design* cell, forbidden cells, charging yes/no, runtime target.
6. Temperature: operating range for life, ambient for calculations.
7. Quantity (assembled boards), and whether a later batch is likely.
8. Layer count: 4L default — is 2L acceptable for this board?
9. Assembly: economic PCBA sides, THT allowed, hand assembly allowed (with costed plan)?
10. Safety limits (max test current, no-fire thresholds, isolation, what must never happen) and whether a full safety analysis is wanted. **The single-fault table below is filled regardless.**
10a. Multi-channel loads: per-channel indication or diagnostics wanted? (A "total current" requirement hid an expected one-LED-per-channel.)
11. Firmware constraints (language, debug interface, update path).
12. Anything the concept document assumes numerically → **assumption audit**: recompute every number (rail vs. cell current, leakage against µA budgets, "protection" that does not protect, measurement schemes that are not physically possible with the chosen parts).

## Single-fault table (gate 1, every power path, always)

| Path | Switch shorts | Switch opens | Load back-drives (motor/generator, no one-way clutch?) | Fuse at this fault current (time-current curve) | Input reversed | Node driven by …when load runs on its own |
|---|---|---|---|---|---|---|

Each cell: consequence, protection that actually covers it (with the
number), or "accepted risk R-n". A fuse "covers" a fault only if the
fault current sits on the fast side of its curve.

## Deep-read constraint types (per active IC, `docs/parts/<mpn>.md`)

Read beyond the reference circuit — the feature descriptions, cautions,
EC-table footnotes. Tick each type as "applies / value / checked":

- input common-mode range in **every** operating state (incl. sources off)
- current-source compliance / output headroom
- settling, start-up and turn-on times (read the unit: µs/pF ≠ ms)
- internal monitors' accuracy ("coarse", "not for precision")
- wake-up / interrupt sources per low-power mode (only certain pins wake)
- pass-through / back-feed / reverse-current conditions (Vin > Vout + x)
- burn-out / open-detect current sources vs. external filters and gain
- reference and internal pull-up/-down behaviour that the design forbids
- ESD, latch-up, absolute-max on every pin that leaves the board
- soldering process notes (wave vs. reflow, SMT standoffs/nuts)
- module datasheets: operating ranges mislabeled as absolute max → cross-check with the controller IC
- MCU: bonded/shared pins in small packages vs. alternate-function table; strapping/boot pins
- **fitted vendor** — the summary quotes the datasheet of the part on the BOM (ST ≠ TI for "pin-compatible" op-amps: input range vs. V+, footnotes)
- thermal: R_θJA **with its copper condition** (board, layers, copper weight, area); if it differs from this board, recompute (JEDEC 4L numbers on a 2L board are fiction)
- every error term with a **sign**: DC-bias direction of timing caps, bias-current direction, hysteresis as specified (not as remembered)

## Pre-layout checklist (schematic)

Power
- [ ] Decoupling per power pin; bulk at every regulator in/out, DC-bias derated.
- [ ] Regulator stability caps per datasheet; dissipation at Vin max, Iout max, `calc_ambient`.
- [ ] Input protection: reverse polarity, overvoltage, fuse. **Sub-1.5 V inputs:** no LCSC P-FET is specified for R_DS(on) below −1.5 V — use a low-side N-FET with the gate from a diode-OR of VBAT and the boosted rail, plus a Schottky bypass for start-up. A keyed holder is not reverse-polarity protection.
- [ ] Low-quiescent battery devices: rail currents converted to **cell current** (V_out/V_in/η); FB-pin leakage vs. divider impedance; PFM reference offset (~+3 %); quiescent current of everything permanently on the rail; Zener/TVS leakage at the working voltage.
- [ ] Supply window of every part (incl. display/UI modules) inside the rail's **actual** min…max over temperature.
- [ ] USB-C CC, VBUS not back-fed; battery charger window and thermistor/firmware limits.

MCU / digital
- [ ] Boot/reset handling; debug header; unused pins; crystal load caps; I²C pull-ups once per bus; level shifting; ESD on every external signal.
- [ ] Wake sources match the chosen low-power mode; bonded pins checked.

Measurement / precision front end
- [ ] PGA/ADC common mode in every state; IDAC compliance; C0G in filters; target resolution vs. datasheet noise table; burn-out sources vs. filters at max gain.

Radio / RF, sensors, mechanical, user
- [ ] Matching per reference; antenna keep-out noted; addresses unique; interrupts on capable pins; LEDs calculated; test points on every rail, **named by function**; mounting holes from the mechanical inputs.

Documentation
- [ ] Part fields complete (LCSC, MPN, manufacturer, category with date, assembly type, stock, value/tolerance/rating/package); no standard-only part unless standard PCBA was accepted at gate 2; title blocks; `docs/key-values.md` started; firmware notes section started in design-notes.

## Self-audit (mandatory before each gate)

1. Export the netlist; `audit_netlist.py` checks every pin in `docs/netlist-expect.json` (written from the datasheet summaries, independently of any generator) and runs `scripts/netlist_checks.py`; run `--corrupt` once (negative control). Then compare the remaining pins by hand against the reference circuit **and** the deep-read constraint list.
1a. **Per-resistor power check**: V²/R (or I²R) in the worst held state vs. package rating derated at `calc_ambient` — a 1 kΩ 0603 gate pull-down at 159 mW passed three readings. **Per-indicator failure case**: the LED must be visibly dark/lit in the fault it exists for (open load, blown fuse), computed with the real V_F and gain.
1b. Duplicated parts (paralleled FETs, extra channels): re-run the paralleling checks (own gate resistor per device, current sharing, sense). Placeholders marked "finalised in schematic" are recomputed now.
2. Write the deviation list (pin, reference value, actual, reason); fix or justify.
3. Re-run the safety argument if any value in it changed.
4. Put the lists into `docs/design-notes.md` under the component; update `docs/key-values.md`.

## Hand-fitted and mating parts (phase 5, `Fit=hand` and anything that mates)

- [ ] The part is **measured in hand** (lead/tail diameter, square-pin side → diagonal, peg positions); the drawing is checked against the part, not the other way round.
- [ ] Hole = largest measured lead + 0.2–0.25 mm; worst case at the fab's plating tolerance (JLC −0.08 mm) still ≥ +0.1 mm clearance.
- [ ] Thermal reliefs on every hand-soldered pad (solid 55 A pads are unsolderable by hand); the hand-assembly plan names the soldering of each pad.
- [ ] Mating gender confirmed on the real counterpart; polarity marked on silk **and** in the interfaces table.
- [ ] CPL rotation of every JLC-placed LCSC part measured from JLC's footprint (pad numbering and geometry), recorded in `rotation-corrections.csv` with "measured", preview still checked on order day.

## 2-layer boards (when `layers` = 2)

- [ ] B.Cu keep-out around every switching converter (input loop, SW node, FB) set **before the first router run**; no B.Cu signals under the converter.
- [ ] FB, sense, Kelvin and reference nets hand-routed and locked before autorouting; FB stays short and away from SW/L.
- [ ] Return paths checked where the ground is not a plane (mesh/solver or at least a drawn current path per high-current loop); no slotting of the ground under signals.
- [ ] SW-node-to-sensitive-net distances measured and listed at the layout gate.
- [ ] Thermal numbers recomputed for 2L copper (no JEDEC 4L R_θJA); hot parts get the copper area the calculation demands.
- [ ] Via keep-outs under every silk label and marker before routing; via nudging preferred over label moves.

## Footprint validation (phase 5, per footprint in `lib/`)

- [ ] Pads: size, pitch, courtyard against the datasheet land pattern; source noted in the footprint description.
- [ ] Pin-1 silk **triangle pointing at pad 1**, on its axis just beyond the outer end, tip ≥ 0.2 mm from copper/mask, not under the body; connectors: beyond the row end.
- [ ] Silk outline only on pad-free sides, 0.15 mm, ≥ 0.2 mm from pads; no rectangle around the body touching pad corners; a shared line between neighbours is allowed and documented.
- [ ] Test points, net ties, fiducials: "exclude from BOM" and "exclude from position files" set.
- [ ] Polarity bar/"+" at the outer pad end for polarised two-pin parts.
- [ ] Reference and secondary pin-1 cues on F.Fab, inside the body outline; nothing on silk between pads.
- [ ] 3D model present and aligned (pin-on-pad, F.Fab outline, seating plane/height).
- [ ] Render of the footprint alone (top view) reviewed once before use — a wrong marker is cheaper to see than to describe.

## Layout checklist

- [ ] Outline, holes, cut-outs, edge-facing ports from the mechanical inputs — nothing "provisional".
- [ ] Body-to-edge ≥ 2.5 mm; rails expected under ~70 × 70 mm.
- [ ] Placement review done before routing (F.Fab + ratsnest): two-pin parts in line with their connections, no avoidable crossings; dense areas planned on a courtyard map, not slot by slot; no hand route splits a net's cluster.
- [ ] Silk markers counted per footprint before and after any silk clean-up (pin-1 triangles, polarity bars) — a clean-up once deleted markers and left bars that read as polarity.
- [ ] Short loops for switching regulators; decoupling at pins with GND vias, power pad toward the IC pin; **decoupling distance measured pad-to-pin and listed per IC supply pin**.
- [ ] Resistance budget from the real fills, including the pin fan-out and thermal reliefs; SW-to-sensitive-net distances listed.
- [ ] Pad exits per the layout rules (two-pin outward ≤ 45°; IC/connector pins along the long axis, turning outside the pad, GND included; no bend inside a pad; round pads through the centre) — `check_entry_angles.py` list attached with justifications.
- [ ] Track geometry on the 45° grid, no acute corners / 45° T-branches outside pads, no zero-length or duplicate segments — `check_track_geometry.py` list attached.
- [ ] Silk revision string equals the planned release tag.
- [ ] **Power paths:** own net class per segment; pours/wide traces everywhere, necks only at fine-pitch pads; resistance budget per path (`calculations.md`) met.
- [ ] Continuous GND under every signal; inner GND unbroken; RF fenced, 50 Ω.
- [ ] Matched groups only above the frequency threshold; skew recorded.
- [ ] GND stitching grid per conventions.
- [ ] Vias within conventions; thermal vias under hot parts.
- [ ] Silkscreen: name/rev/date, connector labels, pin 1, polarity, user controls, **test points by function**, text ≥ 1.0 mm, nothing over pads.
- [ ] Real 3D models everywhere; placeholders listed and resolved before the production tag.
- [ ] Scripted edits verified in the file (counts, grep) before DRC.
- [ ] DRC with `jlcpcb-4layer.kicad_dru`: zero errors; every remaining warning listed in `hardware/drc-allowlist.txt` with its justification (`drc_gate.py` passes, no stale entries).
- [ ] `fp_silk.py check` clean; silk markers counted per footprint after any clean-up.
- [ ] Economic-PCBA side/THT/standoff rules verified against JLC's current page.

## Handover checklist (production gate)

- [ ] Independent audit of the release candidate done **before** the first order tag; premises checked against the board.
- [ ] ERC and DRC clean (reports in `production/rev<X>/`); stale-value lint clean; **claims pass** done (`lint_stale_values.py --claims`: each listed sentence traced to a C-nn or a measurement).
- [ ] Outputs up to date: generators re-run, no diff under `hardware/`; schematic ↔ board field parity after regeneration.
- [ ] Export chain outputs complete; CPL includes THT parts; rotations checked in JLC preview; table updated.
- [ ] BOM: every line LCSC + live category + live assembly type + stock ≥ `quantity` × qty + attrition; thin parts flagged; extended and standard-only parts listed with reasons; Basic/Preferred/Extended and standard-only counts in README.
- [ ] Hand-assembled parts (if any) with their plan and cost in README.
- [ ] `production/README.md` (isometric render at the top, release link, what it does), `bom_handfit.csv` with the hand-assembly plan, `CHANGELOG.md`, revision/date in **all** title blocks and silk, firmware notes current, STEP exported for the case owner, git tag on `main`.
- [ ] Order-day re-check scheduled: stock, category, DFM, preview.

## Audit response (after every external review)

One table per audit in `docs/design-notes.md`:

| ID | Finding | Status (closed / decided / gated / firmware) | Fix location (file, section, rev) |

Closed means the fix is in the files and the self-audit re-ran;
"gated" names the gate (e.g. pre-order sample test) and the criterion;
"declined" carries the numbers that refute the premise (fab minimum
actually 0.2 mm, the quoted drawing belongs to another part, the neck
does not exist in the fill). An audit reads as authoritative; it isn't.

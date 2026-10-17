---
name: pcb-design
description: House rules for designing printed circuit boards in KiCad 10 for JLCPCB fabrication and economic assembly — gated workflow (requirements → architecture → datasheet deep read → schematic → library → layout → production → retrospective), project parameters, 4-layer stackup, via/stitching rules, LCSC sourcing with live category and stock checks, project-local library, single-source key values, calculations and FMEA, kicad-cli ERC/DRC/export chain, 3D renders. Use this skill whenever the user mentions a PCB, circuit board, schematic, KiCad, JLCPCB, LCSC, footprint, gerber, BOM, stackup, layout, routing, or asks to "design a circuit/board for…", even if only a component, module, or MCU is named and the word "PCB" never appears. Also use it when reviewing, auditing, fixing, or preparing an existing KiCad project for production, and when writing a project retrospective for a board. Enclosure/case CAD design is out of scope — the skill only collects the mechanical constraints a board must respect.
metadata:
  version: "0.5.0"
---

# PCB design (KiCad 10 → JLCPCB)

This skill encodes how the user wants boards designed. Treat them as an
experienced engineer and talk to them as a peer: state trade-offs,
numbers and sources, skip the basics unless asked.

Each rule prevents a specific, expensive mistake that has actually
happened: a display module JLC cannot place, a cell path routed at
0.3 mm, a 3D model 1.2 mm off, a value changed in four of seven
documents, a "passing" check that checked nothing. When a rule gets in
the way, explain why and ask — see "When to stop and ask".

**Scope.** The skill owns rules, checklists, documentation and the
production chain. It does not own enclosure/case design (the board
delivers a STEP and its mechanical constraints; the case is someone
else's job), firmware, or project-specific generators — those live in
the project repo. `references/lessons-learned.md` has the history; read
it once per project. **Step 0 of every project: `bash scripts/preflight.sh`**
— it reports which tools and helpers exist on this machine and what the
skill does without each (every shipped script also self-tests there).

## Project parameters (set at gate 1, live in `docs/requirements.md`)

Defaults ship with the skill; the project overrides them. Every other
rule refers to these parameters, never to a hard-coded number.

| Parameter | Default | Ask at gate 1 |
|---|---|---|
| `quantity` | 2 assembled boards | yes |
| `layers` | 4 (SIG/GND/GND/SIG) | yes — 2L acceptable for simple low-speed boards |
| `assembly_sides` | per JLC economic rules at the time | yes |
| `tht_allowed` | yes, single side, JLC-fitted | yes |
| `hand_assembly_allowed` | no | yes — if yes, each hand-fitted part needs a costed plan |
| `operating_range` | −20 … +60 °C | yes |
| `calc_ambient` | +60 °C | yes |
| `part_rating` | industrial −40 … +85 °C | yes |
| `cell_chemistry` / supply | — | yes, incl. the *design* cell and forbidden cells |
| `safety_limits` | — | yes (max test current, no-fire thresholds, isolation…) |
| `mechanical_inputs` | — | yes — outline, hole positions, keep-outs, edge-facing ports, display mount (see gate 1) |
| `interface_connectors` | — | yes |
| `safety_analysis` | ask | yes, if the board can hurt someone or something. **A one-page single-fault table is mandatory for every power path even when the full FMEA is declined** (see Conditional: safety). |
| `fit` per part | jlc | hand-fitted parts carry `Fit=hand` (symbol field) and are measured in hand at gate 5 |

## Fixed conventions (apply unless the project parameters say otherwise)

| Topic | Rule |
|---|---|
| Tool | KiCad **10.0.7**. Use `kicad-cli` for every check and export; `source scripts/kicad_env.sh` finds it (macOS bundle path included). If a sub-command differs from what you expect, run `kicad-cli <cmd> --help`. |
| Fab / assembly | JLCPCB, **economic PCBA**. Read `references/jlcpcb-rules.md` before part selection and before layout, then **verify on jlcpcb.com** — rules, categories and fees change (extended-part fee changed 2025-12-19; former Basic parts became Extended). Never state a category from memory: check live, record the date. |
| Layers | `layers` parameter; 4L default, **SIG / GND / GND / SIG** on JLC's standard 4L stack. Power as pours on outer layers. GND-outside only as explicit opt-in. **2L boards** follow the 2-layer checklist (`references/checklists.md`): the plane discipline 4L gives for free has to be done by hand — B.Cu keep-out around every converter before routing, FB/sense/Kelvin nets hand-routed, return paths checked, SW-to-sensitive-net distances listed. |
| Vias | Default **0.3 mm hole / 0.6 mm pad**; minimum **0.3 / 0.45 mm**; never below 0.3 mm hole. |
| GND stitching | ~10 mm grid; ~5 mm or λ/20 of the highest frequency (whichever smaller) around RF and along edges; a GND via at every decoupling cap. |
| Length matching | **Only where it matters:** differential pairs (USB ±0.15 mm); clocked buses only above ~10 MHz or edge rate < 5 ns (then ±0.5 mm). A 250 kHz SPI gets no serpentines. RF lines short, 50 Ω. Record what was matched and why. |
| Impedance | USB 90 Ω diff, RF 50 Ω, from JLC's impedance calculator for the actual stack; into net classes and `docs/design-notes.md`. |
| Power paths | Current-carrying nets get **their own net class per segment**: wide (or pour) everywhere, necked **only** at fine-pitch pads. A resistance budget per path (mΩ vs. the source's own resistance) is calculated from the real fills and checked at the layout gate; it **includes the last millimetres into the IC pins and every thermal relief** — a 0.4 × 2.35 mm thread feeding a buck VIN passed the pour-to-pour estimate once. One fine-pitch pad never sets the width of a whole net. |
| Parts | LCSC number before a part enters the schematic. Three live checks per part, none from memory: **category** (Basic / Preferred first, Extended only with written justification), **stock** ≥ `quantity` × per-board count + attrition, and **assembly type** — JLC marks each part "Economic & Standard" or "Standard only"; **one standard-only part moves the whole board to standard PCBA**, so it is replaced or the cost accepted at gate 2, never discovered at order time. **UI parts (displays, buttons, connectors) must be JLC-placeable or have a costed hand-assembly plan, and their supply window must sit inside the rail's actual range — decided at gate 2.** |
| Temperature | `part_rating`, `operating_range`, `calc_ambient`. Battery charging within the cell datasheet window. **Every thermal figure names its copper condition** (layer count, copper weight, area) and is recomputed for *this* board — a datasheet R_θJA for 1 in² of 2 oz or a JEDEC 4L board is not a number for a 107 mm² 1 oz 2L board. |
| Silkscreen | Board name, revision, date; connector names and pin 1; polarity; LEDs/buttons/jumpers by function; **test points labelled by function** (`VBAT`, `3V3`, `SWDIO`), not by refdes. No reference designators (assembly drawing has them). Text ≥ 1.0 mm. |
| Documentation | Written as you go. `docs/key-values.md` is the single source of truth for every number that appears in more than one place; others reference it. Undocumented = not done. |
| Git | `main` + tags from day one (`rev0.1`… at production gates, `v1.0` at release); commit at every gate. |

## Workflow with review gates

Stop at every ⏸ gate, present, wait. Rework after layout costs ten
times rework at the schematic.

1. **Requirements** — `docs/requirements.md` with the parameter block,
   purpose, interfaces, rails, must/should/could. Ask the **fixed
   gate-1 question catalog** (`references/checklists.md`) in one round.
   Collect the **mechanical inputs** from whoever owns the case: board
   outline, mounting-hole positions, keep-outs, which ports must face
   an edge (piezo, antenna, sensors, terminals), how a display is
   mechanically fixed, battery access and polarity marking, label text.
   Holes and outline are fixed here, not "provisional" in layout. A
   concept document is **not** a requirement: list every quantitative
   assumption in it and recompute it (**assumption audit**). ⏸
2. **Architecture & parts** — block diagram (Mermaid) in
   `docs/design-notes.md`; candidate parts with LCSC number, live
   category, live stock, supply window vs. rail; a rough placement
   sketch when the form factor is open; cost order of magnitude in one
   line. UI/display decision per the Parts convention. ⏸
3. **Datasheets, deep read, calculations** — PDFs into
   `docs/datasheets/` (`scripts/lcsc_detail.py` gives the URL,
   `scripts/pdf_grep.sh` finds pages). For each active IC write
   `docs/parts/<mpn>.md` from a **deep read**, not just the reference
   circuit: feature descriptions, cautions, EC-table footnotes, wake
   sources, pass-through conditions, common-mode and compliance
   ranges, settling, monitor accuracy, soldering notes (constraint
   types in `references/checklists.md`). Module datasheets often label
   operating ranges as "absolute maximum" — cross-check with the
   controller IC. Read the datasheet of the **fitted vendor's** part, not
   a pin-compatible one (an ST part was designed to a TI sentence once).
   Every error term carries a **direction**, not only a magnitude;
   every fuse is checked on its time-current curve against each fault
   current it is claimed to cover; every indicator is calculated for
   the failure case it exists for, not only the nominal one. Fill
   `docs/calculations.md` (incl. the power-budget
   table), start `docs/key-values.md` and the **firmware notes**
   section of `docs/design-notes.md` (what firmware must do for the
   hardware to be safe and correct; updated at every gate). A device
   with a long sequence spec may keep a separate `docs/firmware-brief.md`
   with the section as a pointer.
4. **Schematic** — hierarchical sheets per block. If files are
   generated by script, follow `references/kicad-generation.md`
   (grid, escaping, deterministic UUIDs). ERC via `kicad-cli`, zero
   errors. Pre-layout checklist (guideline, documented). **Self-audit**
   = reference circuit **and** deep-read constraints, pin by pin
   against the exported netlist — `scripts/audit_netlist.py` with the
   pin map in `docs/netlist-expect.json` (written from `docs/parts/`,
   never from the generator) and the project's value checks in
   `scripts/netlist_checks.py`; `--corrupt` is the negative control —
   **with a per-resistor power check**
   (V²/R vs. package rating at `calc_ambient`); placeholders marked
   "finalised in schematic" are recomputed now; a duplicated part
   re-runs the paralleling checks. Safety analysis if the parameter says
   so; the single-fault table always. **The schematic gate is held
   separately even during a rework** — never schematic and layout in
   one presentation. ⏸ *Schematic PDF + checklist + deviation list +
   single-fault table (+ FMEA).*
5. **Library & 3D models** — project library only (`lib/`), footprints
   validated against the land pattern; **real 3D models** for every
   part with a height or a mating counterpart, checked for pin-on-pad,
   F.Fab outline and seating plane against the datasheet height.
   Placeholder boxes only when listed explicitly with their
   dimensions and resolved before the production tag. **Hand-fitted
   and mating parts (connectors, switches, plugs) are measured in
   hand**: hole = largest measured lead + 0.2–0.25 mm, checked at the
   fab's plating tolerance (JLC −0.08 mm), diagonal for square pins;
   thermal reliefs on every hand-soldered pad. A model that disagrees
   with the datasheet is never closed as "cosmetic" — it is the first
   hint that nobody has measured the part. Each LCSC part's CPL
   rotation is measured from JLC's footprint (pad number **and**
   geometry) when the part is chosen, not taken from the generic table.
   ⏸ *Only for hand-made footprints, placeholders, measured parts, or
   model/datasheet disagreements.*
6. **Layout** — outline and holes from the mechanical inputs,
   placement by block, then a **placement review before any routing**:
   plot F.Fab + ratsnest; every two-pin part sits in line with its
   connections (pad axis along the ratsnest), rows of passives share
   one orientation, no avoidable crossings. Orientation follows the
   connections, never the schematic; late additions obey the same
   rule instead of the nearest free gap. Then power pours and
   current-path net classes, RF/high-speed, then the rest.
   Autorouting only for non-critical nets, after placement review and
   manual routing of power loops, RF, matched groups and FMEA-relevant
   nets (it never rotates a part). DRC with
   `assets/jlcpcb-4layer.kicad_dru`, all severities reported, zero
   errors; justified warnings go into `hardware/drc-allowlist.txt`
   (kicad-cli ignores the project's DRC exclusions — `drc_gate.py`
   enforces the list and fails on stale entries); `check_entry_angles.py` and `check_track_geometry.py` run and
   their lists reviewed. ⏸ *Renders (top/bottom/iso) + DRC + resistance
   budget + measured decoupling distances + skew table + lint lists
   with justifications.*
7. **Production** — **before the first order tag, an independent audit
   of the release candidate** (three audits after three tags merged
   into one would have saved two releases). Then
   `scripts/export_production.sh` (refuses on ERC/DRC violations and on
   an existing tag; regenerates and diffs if the project has
   generators; stale-value lint; claims list; layer list from the
   board; hand-fit BOM split; STEP for the case owner); **claims pass**:
   every sentence that states a protection, distance or direction is
   traced to a C-nn or a measurement; `production/README.md` with the
   isometric render at the top; revision + date in title blocks and
   silk; `CHANGELOG.md`; tag. CPL rotations checked in JLC's preview;
   stock, category and assembly type re-checked **on order day**. ⏸
8. **Audits & retrospective** — answer every external audit with an
   ID-by-ID table (finding · status closed/decided/gated/firmware ·
   fix location). **Check every audit premise against the board before
   acting** — six suggestions on one project were wrong on their
   numbers (fab minimums, a different part's drawing, necks that did
   not exist); declining with numbers is a valid status. After release write `docs/retrospective.md`, propose
   skill changes, append general lessons to
   `references/lessons-learned.md`.

## Project structure

```
<board-name>/
├── hardware/            KiCad project, .kicad_dru
├── lib/                 project symbol + footprint libs, 3d/ models (${KIPRJMOD} paths)
├── docs/
│   ├── requirements.md  parameter block, mechanical inputs
│   ├── key-values.md    single source of truth for shared numbers
│   ├── design-notes.md  architecture, decisions, deviations, firmware notes, audit responses
│   ├── calculations.md  C-nn entries + power-budget table
│   ├── interfaces.md    pinout table per connector
│   ├── fmea.md          only if safety_analysis = yes
│   ├── datasheets/      <manufacturer>_<mpn>.pdf
│   ├── parts/           <mpn>.md deep-read summaries with page refs
│   └── retrospective.md after release
├── production/rev<X>/   gerbers.zip, bom.csv, cpl.csv, assembly pdfs, step, erc/drc reports
├── production/README.md
├── renders/rev<X>/
├── scripts/             project copies of skill scripts, project-specific generators
├── rotation-corrections.csv
└── CHANGELOG.md
```

## Component sourcing and project library

- Search via `scripts/jlc_search.py` (JLC parts API; shows category,
  assembly type, stock, price; `--datasheet docs/datasheets` downloads
  the PDF). If the API is unreachable (preflight says so), search
  manually on jlcpcb.com/parts and record the same fields — do not stop.
- Record per part as **symbol fields**: `LCSC`, `MPN`, `Manufacturer`,
  `JLC_Category` (live, with date), `JLC_Assembly` (Economic / Standard
  only, live), `Stock_at_selection`, `Datasheet`. The BOM export reads
  these fields; the production README counts standard-only parts (target 0).
- Extended parts: list with reason in design notes; count
  Basic/Preferred/Extended in the production README.
- Project library only, built by `scripts/build_lib.py` from
  `lib/manifest.json` (stock symbols with `extends` resolved, renames
  only with a "checked against datasheet table" note, stock footprints
  with models moved under `${KIPRJMOD}`, exact-part models with an
  explicit offset/rotation table); project-specific edits (hole sizes,
  hand-made footprints) in `lib/lib_patches.py`. Then
  `scripts/fp_silk.py lib` applies the silk convention and
  `fp_silk.py check` lints it. Hand-made footprints: render the
  datasheet drawing (`pdftoppm`), read the numbers, write the source
  into the footprint description. After library changes on a routed
  board: `sync_models.py` (pcbnew Python) and `fp_silk.py board`.
- **Footprint silkscreen convention** (every footprint in `lib/`, incl.
  ones copied from KiCad): pin-1 marker is a **filled silk triangle
  pointing at pad 1** (KiCad stock size ≈ 0.48 × 0.33 mm), on the axis
  of pad 1 **just beyond its outer end**, tip ≥ 0.2 mm from copper and
  mask (stroke included), never on a pad or under the body; for
  connectors beyond the end of the row. Body outline on silk only along
  the sides that carry no pads (two lines for a TSSOP/SOIC/SOT-23, not
  a rectangle hugging the pad corners), 0.15 mm width, ≥ 0.2 mm from
  pads; two adjacent parts may share one outline line (document the
  resulting `lib_footprint_mismatch` DRC note). Polarised two-pin
  parts: bar or "+" at the outer pad end the same way. The reference
  designator and any secondary pin-1 cue live on **F.Fab**, inside the
  body outline. Decoupling at ≤ 0.65 mm pin pitch: use 0402 so two caps
  fit adjacent pins without outline collisions.
- 3D models: KiCad's packaged models first, then LCSC/EasyEDA for the
  exact part, then vendor STEP (vendor sites block `curl` — fetch in
  the browser or ask). Re-align every imported model; a model that
  disagrees with the datasheet is an open point until a second source
  settles it.
- Passives: value, tolerance, rating, dielectric (C0G for measurement
  filters), package (0603 default).

## Schematic conventions

Hierarchical sheets per block; flow left → right; named nets
(`UPPER_SNAKE`, `nRESET`); power symbols per rail; PWR_FLAG also on
`power_in` pins fed only passively (boost SW pin, AVDD behind an RC);
open-collector outputs on power nets through 0 Ω where the datasheet
allows; Kelvin points as net ties; a short note per IC (decoupling,
config pins, reference page); test points on every rail and key
signal, named by function; debug header mandatory; title block with
board name, revision, date. Small-package STM32: check bonded pins
against the alternate-function table.

## Layout rules

- Outline, holes, keep-outs, connectors and edge-facing ports from the
  mechanical inputs; placement by block; routing last.
- Decoupling within 1–2 mm of the pin — **measured pad-to-pin and listed
  per IC supply pin at the layout gate**, not ticked ("1–2 mm" was
  claimed for four revisions while it was 6 mm). Power pad toward the IC
  pin, GND pad at its via.
- **Pad exits** (lint `check_entry_angles.py`, rules R1–R3):
  two-pin parts leave the pad **outward** (away from the other pad),
  ≤ 45° off the pad axis — a backwards 45° over the body is not axial;
  IC and connector pins exit **along the pad's long axis, outward, and
  turn only outside the pad**, GND fan-outs included (an end-of-row pin
  may exit straight out of its free side); **no bend inside a pad**;
  round pads and test points are entered on a straight line through
  the centre. Series parts pass the signal straight through; passive
  rows share one orientation.
- **Track geometry** (lint `check_track_geometry.py`): every segment on
  the 45° grid; no acute corners or 45° T-branches outside pads; no
  zero-length or duplicate segments.
- Power: pours or wide traces per the current-path net classes and
  the resistance budget; thermal vias under hot parts; copper area per
  dissipation calculation at `calc_ambient`.
- Every signal over continuous GND; inner GND unbroken; RF short,
  50 Ω, fenced. Matched groups only above the frequency threshold.
- Component body to board edge ≥ 2.5 mm (JLC assembly); JLC adds rails
  to boards under ~70 × 70 mm.
- SMT standoffs/nuts: no wave soldering next to them — align the THT
  soldering process with the assembly plan.
- Silkscreen per conventions; nothing over pads or vias.
- After every **scripted** board edit, verify the edit itself in the
  file (object counts, grep) before trusting DRC.

## Verification

- ERC/DRC via `kicad-cli` after every meaningful change: zero errors,
  all severities reported, warnings justified in writing.
- Self-audit at every gate: reference circuit **plus** deep-read
  constraints, against the exported netlist.
- **Verify the verifier:** any automated check written for the project
  (overlap check, zone count, error filter…) gets a negative control
  once — make it fail on purpose, then trust it. Record that it has one.
- Stale-value lint (`scripts/lint_stale_values.py`) before every tag:
  greps docs and KiCad text for previous values listed in
  `docs/key-values.md`. It finds **old** numbers, not **wrong** ones —
  the **claims pass** (`--claims`) lists every sentence that asserts a
  protection, distance or direction; each is traced to a C-nn or a
  measurement or rewritten before the tag.
- **Measurements beat drawings**: plug resistance, motor current,
  connector tails, pin diagonals — when the owner can measure it, the
  measurement is the input, and the drawing is the thing to check.
- Layout lints (`check_entry_angles.py`, `check_track_geometry.py`;
  pure text, no pcbnew) before the layout gate; lists reviewed with
  justifications item by item, not driven to zero at any cost and not
  waved through with one class justification. A lint encodes the
  **purpose** of a rule, not one formula for it; every miss a person
  catches becomes a positive self-test case; every tool that fixes or
  routes has a planted-failure test, not only an exact re-check.
  Measured checks beat ticked checklists.

## Production outputs

`scripts/export_production.sh <project> <rev>` (read it first): finds
kicad-cli, **refuses a revision whose tag already exists**, runs the
stale-value lint, ERC + DRC (all severities, schematic parity, **zones
refilled and saved** so gerbers never carry stale fills), the layout
lints, then gerbers/drills, BOM with LCSC fields, position file for SMD
and THT → `cpl.csv` (rotation table applied, THT placement points moved
to the pad centroid, designators filtered to the BOM), assembly PDFs,
schematic PDF, STEP, renders. Test points, net ties and fiducials get
"exclude from BOM / position files" in their footprint attributes.
**The silk revision equals the release tag** — a docs-only release
still bumps the board revision. Then `production/README.md`, changelog,
tag. CPL rotations are a silent killer: check every distinct package in
JLC's order preview and record confirmed ones in the table.

## Conditional: safety-relevant boards

**Always, for every power path**, a one-page single-fault table at
gate 1 (in `docs/requirements.md` or `design-notes.md`): switch shorts
· switch opens · load drives back (motors and generators push current
into FET body diodes when the engine runs them) · fuse sees fault
current X (time-current curve, not the rating) · input reversed ·
what drives this node when the load runs on its own. Declining the
full FMEA does not decline this table — a declined FMEA cost one
project a back-driven motor and a fuse that covered nothing.

If the board switches real current, drives actuators or igniters,
charges batteries, or can hurt someone or destroy an attached device
when it fails: say so at gate 1 and ask about the full analysis. If yes: single-fault analysis
with a **structural argument** ("every current returns through
R_REF"), FMEA table, stored-energy check (∫i²dt vs. minimum fire
pulse), the state "arbitrary firmware + one hardware fault",
protection elements with calculations; reviewed at the schematic gate
and re-checked after every value change. If no, skip entirely.

## When to stop and ask

Unclear or conflicting requirement · extended part unavoidable · stock
or category problem · DRC needs a constraint change · a UI part is not
JLC-placeable or outside the rail window · 3D model and datasheet
disagree · a trade-off touches cost, safety or a stated requirement ·
JLC's live rules differ from `references/jlcpcb-rules.md` · a large
download or new tool (Freerouting, JDK) is needed · any deviation from
the fixed conventions looks better for this board. Present options with
numbers, recommend one, wait.

## Reference files

- `references/jlcpcb-rules.md` — fab and economic-PCBA constraints (verified 2026-10-16), export settings, surcharges.
- `references/checklists.md` — gate-1 catalog, single-fault table, deep-read constraint types, pre-layout, hand-fitted parts, 2-layer boards, layout, handover, audit response.
- `references/calculations.md` — template, standard set, power budget, low-Iq battery, resistance budget, igniter energy.
- `references/doc-templates.md` — key-values, parts summary, interfaces, production README, changelog, FMEA, firmware notes, audit table.
- `references/kicad-generation.md` — scripted schematic/board generation pitfalls, Freerouting scope, verify-the-verifier.
- `references/lessons-learned.md` — history; append after each retrospective.
- `assets/jlcpcb-4layer.kicad_dru`, `assets/rotation-corrections.csv`
- `scripts/README.md` — the fifteen shipped scripts (all self-contained; nothing to import from earlier projects) and what stays project tooling.

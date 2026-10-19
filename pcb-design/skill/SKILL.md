---
name: pcb-design
description: House rules for designing printed circuit boards in KiCad 10 for JLCPCB fabrication and economic assembly — gated workflow (requirements → architecture → datasheet read → schematic → library → layout → production → retrospective), project parameters, 4-layer stackup, via/stitching rules, live LCSC sourcing (category, stock), project-local library, single-source key values, calculations and FMEA, kicad-cli ERC/DRC/export chain, 3D renders. Use this skill whenever the user mentions a PCB, circuit board, schematic, KiCad, JLCPCB, LCSC, footprint, gerber, BOM, stackup, layout, routing, or asks to "design a circuit/board for…", even if only a component, module, or MCU is named and the word "PCB" never appears. Also use it to prepare an existing KiCad project for production or to write a board retrospective. Enclosure/case CAD is out of scope; the skill only collects the board's mechanical constraints.
metadata:
  version: "0.7.2"
---

# PCB design (KiCad 10 → JLCPCB)

Treat the user as an experienced engineer and talk to them as a peer:
trade-offs, numbers, sources; skip the basics unless asked. Every rule
below prevents a mistake that has actually happened on a board
(`references/lessons-learned.md` has the stories). When a rule gets in
the way, say why and ask — see "When to stop and ask".

**Scope.** Laying out, designing and delivering the board: rules,
checklists, documentation, production chain; checking is the gate
audit's (see Workflow). Not in scope: enclosure/case design (the board
delivers a STEP and its mechanical constraints), firmware,
project-specific generators or routing tools. Built for Claude Code with
a local KiCad 10; the Claude app (no kicad-cli, pcbnew or JLC API) gets
rules and documents only. `scripts/` means `<skill dir>/scripts/`.
Before the first gate run `bash scripts/preflight.sh` once: it reports
whether kicad-cli and the JLC API answer, and what to do by hand if not.

## Project parameters (gate 1, `docs/requirements.md`)

Every rule refers to these, never to a hard-coded number.

| Parameter | Default |
|---|---|
| `quantity` | 2 assembled boards |
| `layers` | 4 (SIG/GND/GND/SIG); 2L acceptable for simple low-speed boards |
| `assembly_sides`, `tht_allowed` | per JLC economic rules at the time; THT single side, JLC-fitted |
| `hand_assembly_allowed` | no; if yes, each hand-fitted part carries `Fit=hand` and a costed plan |
| `operating_range` / `calc_ambient` / `part_rating` | −20…+60 °C / +60 °C / industrial −40…+85 °C |
| `cell_chemistry` / supply, `safety_limits`, `interface_connectors`, `mechanical_inputs` | asked at gate 1 |
| `safety_analysis` | ask; **the one-page single-fault table per power path is mandatory regardless** |

## Fixed conventions

| Topic | Rule |
|---|---|
| Tool | KiCad **10.0.7**, `kicad-cli` for every check and export (`source scripts/kicad_env.sh`). Sub-command differs? `kicad-cli <cmd> --help`. |
| Fab | JLCPCB **economic PCBA**. `references/jlcpcb-rules.md`, then verify live on jlcpcb.com; never state a category or fee from memory, record the date. |
| Layers | 4L SIG/GND/GND/SIG on JLC's standard stack, power as pours on outer layers. 2L boards follow the 2-layer checklist. |
| Vias | 0.3 mm hole / 0.6 mm pad default; minimum 0.3 / 0.45; never below 0.3 mm hole. |
| GND stitching | ~10 mm grid; ~5 mm or λ/20 around RF and along edges; a GND via at every decoupling cap. |
| Length matching | Only differential pairs (USB ±0.15 mm) and buses above ~10 MHz or edge < 5 ns (±0.5 mm). Record what was matched and why. |
| Impedance | USB 90 Ω, RF 50 Ω from JLC's calculator for the actual stack; into net classes and design notes. |
| Power paths | Own net class per segment, wide or poured everywhere, necked only at fine-pitch pads. Resistance budget per path (mΩ vs. the source's own resistance) computed from the real fills, including pin fan-out and thermal reliefs. |
| Parts | LCSC number before a part enters the schematic. Three live checks: **category** (Basic/Preferred; Extended with written reason), **stock** ≥ `quantity` × count + attrition, **assembly type** (one standard-only part moves the whole board to standard PCBA — resolve at gate 2). UI parts must be JLC-placeable or carry a costed hand plan, and sit inside the rail's real supply window. |
| Temperature | Battery charging within the cell window. Every thermal figure names its copper condition (layers, weight, area) and is recomputed for this board. |
| Silkscreen | Name, revision, date; connector names and pin 1; polarity; controls and test points labelled **by function**; no refdes; text ≥ 1.0 mm. |
| Documentation | Written as you go. `docs/key-values.md` is the single source for every number used in more than one place. Undocumented = not done. |
| Git | `main` + tags from day one (`rev0.1`… at production gates, `v1.0` at release); commit at every gate. |

## Workflow — stop at every ⏸, present, hand to the audit, wait

Rework after layout costs ten times rework at the schematic. Details
and the checklists for each gate are in `references/checklists.md`.
At every ⏸ hand the milestone to the **pcb-audit** skill (per-gate
audit, report in `docs/audits/`); continue on PASS or once every finding
is answered by ID — `closed` / `decided` / `gated` (measurement, probe
point, accept limit) / `firmware` / `declined with numbers`, with fix location.

1. **Requirements** — parameter block, purpose, interfaces, rails,
   must/should/could; the fixed gate-1 question catalog in one round;
   mechanical inputs from the case owner (outline, holes, keep-outs,
   edge-facing ports, display mount, battery access, labels) — fixed
   here, never "provisional"; assumption audit of any concept document;
   single-fault table per power path. ⏸ *audit gate 1.*
2. **Architecture & parts** — block diagram in `docs/design-notes.md`;
   candidate parts with LCSC number, live category, stock and assembly
   type, supply window vs. rail; placement sketch if the form factor is
   open; cost in one line. ⏸ *audit gate 2.*
3. **Datasheets & calculations** — PDFs into `docs/datasheets/`
   (`jlc_search.py --datasheet`, `pdf_grep.sh` for page refs). One
   `docs/parts/<mpn>.md` per active IC from a **deep read** of the
   fitted vendor's datasheet (constraint types in the checklists). Fill
   `docs/calculations.md` with power budget, start `docs/key-values.md`
   and the firmware-notes section of design-notes.
4. **Schematic** — hierarchical sheets per block; ERC zero errors;
   pre-layout checklist; `Decouples` on every decoupling cap;
   `docs/netlist-expect.json` written from `docs/parts/` (never from a
   generator); deviation list against reference circuit and deep-read
   constraints. Held as its own gate even in a rework. ⏸ *audit gate 4:
   schematic PDF, netlist, checklist, deviations, single-fault table
   (+ FMEA).*
5. **Library & 3D** — project library only (`lib/`, built by
   `build_lib.py` from `lib/manifest.json`), footprints checked against
   the land pattern, silk convention applied and linted with
   `fp_silk.py`, real 3D models for anything with a height or a mating
   part; hand-fitted and mating parts **measured in hand** (hole =
   largest lead + 0.2–0.25 mm at JLC's −0.08 mm plating tolerance).
   ⏸ *audit gate 5, only for hand-made footprints, placeholders or
   model/datasheet disagreements.*
6. **Layout** — outline and holes from the mechanical inputs, placement
   by block, **placement review before any routing** (F.Fab + ratsnest:
   two-pin parts in line with their connections, passive rows in one
   orientation). Then pours and current-path classes, RF/high-speed,
   the rest; autorouting only for non-critical nets afterwards. DRC with
   `assets/jlcpcb-4layer.kicad_dru`, zero errors, warnings justified in
   `hardware/drc-allowlist.txt` (`drc_gate.py`). ⏸ *audit gate 6:
   renders, DRC, allowlist, resistance budget, skew table.*
7. **Production** — `scripts/export_production.sh`;
   `production/README.md` with the isometric render first; revision +
   date in title blocks and silk (silk revision = tag); changelog.
   ⏸ *audit gate 7 of the release candidate **before** the first order
   tag*, then tag. Stock, category and assembly type re-checked **on
   order day**, CPL rotations in JLC's preview.
8. **Audits & retrospective** — every audit, external ones included,
   answered ID by ID as above. After release: `docs/retrospective.md`,
   lessons appended to `references/lessons-learned.md`, proposed skill
   changes.

## Project structure

```
<board>/
├── hardware/           KiCad project, .kicad_dru, drc-allowlist.txt
├── lib/                manifest.json, lib_patches.py, silk-kinds.json → symbols,
│                       footprints, 3d/ (${KIPRJMOD} paths), built by build_lib.py
├── docs/               requirements, key-values, design-notes, calculations,
│                       interfaces, (fmea), datasheets/, parts/, netlist-expect.json,
│                       audits/, retrospective
├── production/rev<X>/  gerbers.zip, bom.csv, cpl.csv, pdfs, step, erc/drc
├── production/README.md · renders/rev<X>/ · scripts/ · rotation-corrections.csv · CHANGELOG.md
```

## Sourcing, library, silkscreen

- Search with `scripts/jlc_search.py` (category, assembly type, stock,
  price). API down: search jlcpcb.com/parts by hand, record the same
  fields and the date — do not stop.
- Symbol fields per part: `LCSC`, `MPN`, `Manufacturer`,
  `JLC_Category` (with date), `JLC_Assembly`, `Stock_at_selection`,
  `Datasheet`, `Fit`. The BOM export reads them; the production README
  counts Extended and standard-only parts.
- Project library only: `build_lib.py` copies stock symbols (`extends`
  resolved, renames only with a "checked against datasheet" note) and
  footprints into `lib/` with models under `${KIPRJMOD}`, from
  `lib/manifest.json`; project edits in `lib/lib_patches.py`; hand-made
  footprints cite the datasheet drawing in their description. Then
  `fp_silk.py lib` applies the silk convention and `fp_silk.py check`
  lints it; after library changes on a routed board `sync_models.py`
  and `fp_silk.py board`. 3D models: KiCad's packaged
  models → LCSC/EasyEDA → vendor STEP (sites block `curl`; ask the user
  to fetch). Re-align every imported model; a model that disagrees with
  the datasheet stays open until a second source settles it.
- **Footprint silk:** pin-1 marker is a filled triangle pointing at
  pad 1, on its axis just beyond the outer end, ≥ 0.2 mm from copper;
  body outline only on pad-free sides (0.15 mm, ≥ 0.2 mm from pads);
  polarity bar/"+" at the outer pad end; refdes and secondary pin-1 cues
  on F.Fab inside the body. Decoupling at ≤ 0.65 mm pitch uses 0402.
- Passives: value, tolerance, rating, dielectric (C0G in measurement
  filters), package (0603 default).

## Schematic and layout rules

- Hierarchical sheets, flow left → right, `UPPER_SNAKE` nets, power
  symbols per rail, PWR_FLAG on passively fed `power_in` pins, Kelvin
  points as net ties, a note per IC, test points on every rail and key
  signal, debug header, title block. Small-package MCUs: check bonded
  pins against the alternate-function table.
- **Decoupling:** every cap sharing a net with an IC supply pin carries
  the symbol field `Decouples` = `<ref>:<pin number>` (`U1:12,U1:34`;
  pin numbers, never names) or `Decouples=bulk` — the ratsnest cannot
  show which cap serves which pin, the field does. In layout the
  assigned cap sits within 1–2 mm of its pin, power pad toward it,
  copper pin → cap pad → via/plane (never pin → via with the cap hanging
  on the plane), GND via at the cap; measured at the audit, not ticked.
- **Pad exits:** two-pin parts leave outward ≤ 45° off the pad axis; IC
  and connector pins exit along the long axis and turn only outside the
  pad, GND included; no bend inside a pad; round pads through the centre.
- **Track geometry:** 45° grid, no acute corners or 45° T-branches
  outside pads, no zero-length or duplicate segments.
- Every signal over continuous GND, inner GND unbroken, RF short and
  fenced. Body-to-edge ≥ 2.5 mm; JLC adds rails under ~70 × 70 mm. No
  wave soldering next to SMT standoffs. Nothing on silk over pads or
  vias.
- After every scripted board edit, verify the edit in the file before
  trusting DRC (`references/kicad-generation.md`).

## Verification

- ERC/DRC via `kicad-cli` after every meaningful change: zero errors,
  all severities reported, warnings justified in writing.
- **Verify the verifier:** every automated step (DRC gate, silk lint,
  generator) gets a negative control once (make it fail on purpose),
  then is trusted.
- `lint_stale_values.py` finds **old** numbers from `key-values.md`
  before every tag.
- **Measurements beat drawings and drawings beat memory**: when the
  owner can measure it, the measurement is the input.

## Conditional: safety-relevant boards

Always, for every power path, the one-page single-fault table at gate 1
(switch shorts · opens · load back-drives · fuse at this fault current
on its time-current curve · input reversed · what drives the node when
the load runs on its own). If the board switches real current, drives
actuators or igniters, charges batteries, or can hurt someone or
destroy a connected device: say so at gate 1 and ask about the full
analysis — single-fault argument with a structural proof, FMEA table,
stored-energy check, "arbitrary firmware + one hardware fault",
protection elements with calculations, re-checked after every value
change. If declined, only the table remains.

## When to stop and ask

Unclear or conflicting requirement · extended or standard-only part
unavoidable · stock or category problem · DRC needs a constraint change
· UI part not placeable or outside the rail window · 3D model and
datasheet disagree · trade-off touching cost, safety or a stated
requirement · JLC's live rules differ from the reference · a large
download or new tool is needed · any deviation from the fixed
conventions looks better for this board. Options with numbers,
recommend one, wait.

## Reference files

- `references/checklists.md` — gate-1 catalog, single-fault table, deep-read constraint types, pre-layout, hand-fitted parts, 2-layer, footprint validation, layout, handover, audit response.
- `references/jlcpcb-rules.md` — fab and economic-PCBA constraints (verified 2026-10-16), export settings, surcharges.
- `references/calculations.md` — template, standard set, power budget, low-Iq battery, resistance budget, igniter energy.
- `references/doc-templates.md` — parts summary, key-values, interfaces, production README, changelog, FMEA, firmware notes, audit table.
- `references/kicad-generation.md` — scripted schematic/board generation and pcbnew pitfalls, Freerouting scope, verify-the-verifier.
- `references/lessons-learned.md` — the boards behind the rules; append after each retrospective.
- `assets/jlcpcb-4layer.kicad_dru`, `assets/rotation-corrections.csv`
- `scripts/README.md` — the twelve shipped scripts, by gate.

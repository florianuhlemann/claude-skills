# JLCPCB fabrication and economic-PCBA rules

Last reconciled with jlcpcb.com/capabilities and the SMT page:
**2026-10-16** (during the first board). JLC changes
capabilities, part categories and fees without notice — reconcile again
before part selection and before layout, record the date in
`docs/design-notes.md`, and update this file when something differs.
Never state a part category or a fee from memory.

## Board (standard 4-layer stackup)

| Item | Value used by this skill | Note |
|---|---|---|
| Stackup | JLC04161H-7628 (or current standard 4L) | ~0.2 mm prepreg outer, ~1.0 mm core; outer 1 oz, inner 0.5 oz. Use JLC's impedance calculator for the stack offered at order time. |
| Thickness | 1.6 mm | |
| Min trace / clearance | 0.127 / 0.127 mm design default | JLC allows ~0.09 mm on multilayer; use only for escapes, after checking. |
| Via default / minimum | 0.3/0.6 mm · 0.3/0.45 mm | Minimum pad = hole + 0.15 mm (0.45 mm for the 0.3 mm hole), as in `jlcpcb-4layer.kicad_dru`; JLC itself fabricates down to hole + 0.1 mm, which this skill does not use. Hole < 0.3 mm with pad ≤ 0.4 mm costs extra; this skill never goes below 0.3 mm hole. |
| Hole to hole | ≥ 0.5 mm | |
| PTH finished-hole tolerance | about −0.08 / +0.13 mm | Size hand-fitted holes against the **minimum**: measured lead + 0.2–0.25 mm. |
| 2 oz copper min trace/space | 0.2 mm (8 mil), not 0.16 | An audit quoted 0.16 mm; check the capabilities page before accepting a copper-weight change. |
| Copper to edge | ≥ 0.3 mm (0.5 mm default) | |
| Hole to edge | ≥ 0.5 mm | |
| Solder mask dam | ≥ 0.2 mm (green) | Stay green. |
| Silkscreen | Line ≥ 0.15 mm, **text height ≥ 1.0 mm** | 0.8 mm test-point labels were rejected in practice. Silk over pads is removed silently. |
| Finish | HASL-LF default; ENIG for pitch ≤ 0.5 mm, exposed contacts, or measurement boards | Justify ENIG in the design notes. |
| Size tiers | Check at order time | Cheapest tier historically ≤ 100 × 100 mm. |
| Rails | JLC adds edge rails/panel frame for boards under ~70 × 70 mm | Expect them; they are removed after assembly but affect the body-to-edge rule. |

## Economic PCBA (verified 2026-10-16 — re-verify every project)

- **THT is supported**: single side, 2–50 pcs, standard stackup only,
  JLC-fitted. (Older versions of this file said SMD-only — wrong.)
- **Component body to board edge ≥ 2.5 mm** (otherwise add rails
  yourself or accept JLC's).
- Minimum IC pitch **0.4 mm**; minimum **BGA pitch 0.5 mm** (a 0.4 mm
  BGA such as some TPS6109x variants is not placeable economically).
- Smallest passive package 0402.
- Fiducials: not required by JLC (they panelise). Optional; harmless.
- Stacked parts (part on part) and some large/odd parts: manual
  placement with surcharge, or not at all.
- **Wave soldering is not applicable next to SMT standoffs/nuts** —
  if the board has both THT and SMT standoffs, clarify the THT
  soldering process with the assembly plan (hand/selective).
- Assembly side(s): check the current rule for economic; design for
  what is offered.
- Minimum order 2 boards; JLC adds **attrition** per part — stock must
  cover `quantity` × per-board count **plus** attrition.
- Package and part restrictions (BGA, shields, batteries, connectors)
  can change — read the SMT page.

## Parts and categories

Three independent properties per part, all checked live on the parts
page (jlcpcb.com/parts) and recorded with the date:
1. **Category** — Basic / Preferred extended / Extended (fees).
2. **Stock** — against `quantity` × per-board count + attrition.
3. **Assembly type** — "Economic & Standard" or **"Standard only"**.
   Economic PCBA cannot place a standard-only part at all; a single one
   on the BOM forces the whole order to standard PCBA (higher setup
   and per-board cost, different side/THT rules). Treat a standard-only
   part like an extended part: replace it, or accept standard assembly
   for the board explicitly at gate 2 with the cost noted. The JLC
   parts API exposes this as a `componentProductType` field — in one
   project the value `2` appeared on a standard-only part (working
   hypothesis, not documented by JLC); `jlc_search.py` should surface
   the field, and the parts-page label is the authority.

- **Basic**: no setup fee. **Preferred extended**: fee waived.
  **Extended**: setup fee per reel per order (fee structure changed
  2025-12-19). Parts migrate between categories — e.g. some 10 nF
  X7R/C0G capacitors that were Basic are now Extended. **Check the
  category live** (`scripts/jlc_search.py` or the parts page) and
  record `JLC_Category` with the date in the symbol field.
- Passive default 0603; 0402 only where density demands.
- Symbol fields: `LCSC`, `MPN`, `Manufacturer`, `JLC_Category`,
  `Stock_at_selection` (with date), `Datasheet`.
- Re-check stock and category **on order day** — thin parts (a few
  hundred in stock) should be flagged from gate 2 on and watched.

## CPL / rotation

JLC's orientation convention differs from KiCad's for many packages.
Start from `assets/rotation-corrections.csv`, apply with
`scripts/fix_cpl_rotation.py`, **check every distinct package in the
order preview**, add fixes to the project table and, if general, back
to the skill. THT parts are in the CPL too (position export must not
use `--smd-only`).

## Gerber / drill export settings JLC accepts

- RS-274X, no X2 attributes, no netlist attributes, subtract mask from
  silk, Protel extensions.
- Layers: F.Cu, In1.Cu, In2.Cu, B.Cu, F.Paste, B.Paste, F.Silkscreen,
  B.Silkscreen, F.Mask, B.Mask, Edge.Cuts.
- Drill: Excellon, PTH/NPTH separate, decimal.
- One origin for gerbers, drills and the position file: the drill/place
  (aux) origin (`--use-drill-file-origin` / `--drill-origin plot`). It
  lies inside the board or at a corner, so the CPL has no negative
  coordinates. Mixed origins put every hole off its pad and pass DRC.
- One `gerbers.zip` per revision.

## Surcharges to avoid

Via hole < 0.3 mm · blind/buried vias · non-green mask · thick copper ·
odd thickness · extended parts (minimise, list) · boards above the
cheapest size tier · castellations, edge plating, impedance-control
service · manual placement of odd parts · hand assembly without a plan.

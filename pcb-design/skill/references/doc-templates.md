# Documentation templates

Copy the relevant template into the project's `docs/` and fill it.
Keep tables terse; put reasoning in design-notes.

## docs/parts/<mpn>.md

```markdown
# <Manufacturer> <MPN> — <one-line function>

- LCSC: Cxxxxx · Category: Basic / Preferred / Extended · Assembly: Economic / Standard only · Package: …
- Datasheet: docs/datasheets/<file>.pdf (rev/date …)
- Stock at selection: … (date)

## Pinout (p.N)
| Pin | Name | Function | Note |

## Absolute maximum (p.N)
| Parameter | Value |

## Recommended operating (p.N)
| Parameter | Min | Typ | Max |

## Reference circuit (p.N)
Components and values from the typical application; layout
guidelines (p.N) in one or two sentences.

## Used in this design
Deviations from the reference circuit (list, with reasons) — mirrors
the self-audit in design-notes.
```

## Power-budget table (section in docs/calculations.md)

```markdown
## Power budget (at calc_ambient)
| Rail | Source | Vnom | Consumer | I typ | I peak | Note |
|---|---|---|---|---|---|---|
| Regulator | Vin range | Iout max | η / Pdiss | Tj at calc_ambient | Margin | Calc |
Cell current: … (C-nn) → runtime … (C-nn)
```
## docs/interfaces.md

```markdown
# Interfaces — <board> rev <X>

## J1 — USB-C (power + data)
Mating: <connector MPN / cable spec>
| Pin | Signal | Voltage | Dir | Note |

## J2 — <name>
…
```

## Project README.md (top of the repo)

```markdown
# <board> — <one line what it does>
![iso render](renders/rev<X>/iso.png)
Release: v<X> · [production package](production/rev<X>/) · [changelog](CHANGELOG.md)

- what it does (3–5 bullets)
- interfaces (link to docs/interfaces.md)
- status / open before order
```
The render comes first: the board is visible before any text.

## production/README.md

```markdown
# <board> rev <X> — production package (<date>)

Fab: JLCPCB · 4 layers · JLC04161H-7628 · 1.6 mm · 1 oz outer / 0.5 oz inner
Mask: green · Silk: white · Finish: HASL-LF (or ENIG, reason) · Qty: 2
Assembly: economic · side(s): … · parts: … basic / … preferred / … extended · standard-only: 0 (see design-notes)
Files: gerbers.zip, bom.csv, cpl.csv, assembly.pdf, board.step, erc.rpt, drc.rpt
Order notes: <anything typed into the order form>
Preview checked: rotations OK for packages …
Git tag: rev<X>
```

## CHANGELOG.md

```markdown
# Changelog — <board>

## rev 0.3 — 2026-10-15
- Replaced AP2112 LDO with TPS62840 buck (C-07/C-08 thermal fail)
- Added fiducials
- JLC order #…

## rev 0.2 — …
```

## FMEA (only when the safety analysis was requested)

```markdown
# FMEA — <board> rev <X>

Scope: … Single-fault criterion: no single component or firmware
fault may lead to <hazard>.

| # | Component / function | Failure mode | Effect | Detection | Mitigation | Residual risk | Status |
|---|---|---|---|---|---|---|---|
| F-01 | Q3 output switch | short D-S | channel energised | current sense via R-shunt, MCU | series second switch Q4, shunt crowbar | low | implemented |
```

## docs/key-values.md (single source of truth)

```markdown
# Key values — <board>

| Key | Current value | Previous values | Where used | Calc |
|---|---|---|---|---|
| R_REF (R7) | 1.2 kΩ 0.1 % | 1.0 kΩ | sch, fmea, firmware notes, calculations | C-04 |
| I_test design | 1–5 mA | — | requirements, firmware notes | C-02 |
| I_fault max single | 4.7 mA | 7.7 mA (double) | fmea, README | C-09 |
```
Other documents write "R_REF (see key-values)" or quote the key name.
`scripts/lint_stale_values.py` greps all docs and schematic text for
every entry in "Previous values" and fails if one is found.

## Firmware notes (section in docs/design-notes.md)

```markdown
## Firmware notes (updated at every gate)
- Pins/peripherals that firmware must configure a specific way, and why
- Power modes and the pins that can wake from each
- Safety musts / must-nots (from FMEA)
- Measurement sequences, settling times, limits
- Calibration / self-test hooks
```
## Mechanical inputs (section in requirements.md)

```markdown
## Mechanical inputs (from the case owner; case design is out of scope)
- Board outline: …  - Mounting holes: positions, screw, standoff type
- Keep-outs: …     - Edge-facing ports: …
- Display mount: … - Battery access / polarity marking / forbidden cells: …
- Label text: …    - Deliverable to case owner: STEP from production/rev<X>/
```
## Audit response table

| ID | Finding | Status | Fix location / numbers |
|---|---|---|---|
| A-03 | PGA CM margin 80 mV (Eq. 15) | closed | sch R7 1.2k; calculations C-04; fmea §3; key-values |
| A-02 | use 2 oz copper, min 0.16 mm | declined | JLC 2 oz minimum is 0.2 mm; HotRod pads are 0.20 mm |

## docs/retrospective.md (after release)

Timeline · what worked · what didn't · recurring problems · where skill
defaults didn't fit · concrete changes for the next board · concrete
changes for the skill (→ `references/lessons-learned.md`).

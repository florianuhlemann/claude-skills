# Lessons learned (append after every retrospective)

## Board 1 (2026-10, four revisions 0.1 → 1.0)

Handheld battery-powered precision measurement instrument (MCU + 24-bit
ADC, single cell, display module), 4L ENIG, economic PCBA with THT.

**What paid off:** gated phases (all big course corrections happened
at gates); calculations and FMEA with a structural safety argument
that survived four independent audits; kicad-cli for everything; live
stock checks from gate 2; ID-by-ID audit responses; negative controls
on automated checks.

**Where the effort really went:** mechanics (no enclosure concept until
after layout), the display module (not JLC-placeable, no mount,
supply window outside the rail — in every single audit), placeholder
3D models, a power path routed at 0.3 mm because one WSON pad set the
net class, and documentation drift (R_REF "1 kΩ" in four places,
a firmware brief cited that didn't exist, title block one rev behind).

**What the self-audit missed:** secondary datasheet constraints —
PGA common mode (ADS1220 Eq. 15), burn-out sources saturating at
G = 128, "coarse" reference monitor, load-switch t_on in µs/pF,
only WKUP pins wake from Standby, boost pass-through above
VOUT + 0.5 V, "wave soldering not applicable" for SMT standoffs.
None exotic; all in feature/caution sections.

**Placement:** 27 of 41 two-pin parts had a trace leaving ≥ 60° off
the pad axis (R6/R7/R17 at the ADS1220 worst) — rotations were set from
the schematic before routing, the autorouter routed around them, and
no check looked at flow. → placement review before routing, orientation
rule, entry-angle lint (v0.2.2).

**Lints that passed by not looking (v1.1.0 → v1.1.1):** backwards 45°
exits counted as axial; IC pin and GND exits never checked; parts with
unnumbered paste pads skipped; in-pad jogs hidden behind a 0.3 mm
minimum length; 45° T-branches and off-grid segments invisible to DRC.
The owner saw all of it at a glance. → rules R1–R3, geometry lint,
positive self-test per miss (v0.3.0). A docs-only release shipped with
the old revision on the silk → silk revision = tag, export refuses an
existing tag.

**Tooling:** KiCad 10 pcbnew via Python — removals last, one zone per
process, never pipe, verify the file after each edit; schematic
generator with random UUIDs became unusable after layout; vendor CAD
sites block curl; JLC rules differ from memory (THT allowed, 2.5 mm
body-to-edge, 1.0 mm silk, rails under 70 × 70 mm).

**Defaults that didn't fit:** temperature (0…55 °C calc, 0…35 use),
quantity 10, SPI serpentines at 250 kHz (removed), test points with no
labels (now: label by function).

**Resulting skill changes (v0.2/0.2.1):** project parameters; mechanical
inputs collected at gate 1 (case design itself kept out of scope); UI parts must be placeable and in
the supply window at gate 2; deep read with constraint types; power
paths with resistance budget and per-segment net classes; key-values
table with stale-value lint; firmware brief from gate 3; deterministic
UUIDs; verify-the-verifier; `main` + tags from day one; retrospective
as the last phase.

## Board 2 (2026-10-16/17, six tags before the first build)

2L 1 oz, buck + paralleled FETs driving high-current heater loads and a motor,
hand-fitted XT30/WAGO, commercial-grade op-amps, FMEA declined.

**Numbers:** three audits, 51 findings, no wiring error in any of them;
the rework was thermal assumptions, layout, production data,
connectors, and documentation claims. Six audit premises were wrong
and were declined with numbers.

**Late catches and their pattern:** requirement/safety questions a
one-page single-fault table would have asked (back-driven motor, a
fuse that covered nothing, per-channel LEDs) · numbers from the wrong
context (R_θJA for other copper, JEDEC 4L on a 2L board, a TI sentence
for an ST part, error terms without sign, a 1 kΩ 0603 at 159 mW) ·
layout done the autorouter's way (FB/sense on B.Cu slotting the only
plane, a 0.4 mm thread into the buck VIN, SW bridge under C_IN) ·
production and mechanical data trusted from tables and drawings (CPL
rotations, XT30 tails 1.55–1.59 mm vs. a 1.7 mm hole, WAGO square-pin
diagonal, 16 parts silently dropped by a designator-range bug).

**What worked:** single sources of truth that reproduced a full
re-route; measured checks (fills-based resistance budget, mesh solver,
111-check netlist audit with negative control, transient simulation);
checking audit premises before acting; the owner's render review and
the owner's measurements; a README with the isometric render first.

**Resulting skill changes (v0.4.0):** mandatory single-fault table;
per-channel-indication question; thermal figures with copper
condition; fitted-vendor deep read; signed error terms; fuse curves;
per-resistor power and indicator fault-case checks; measured
hand-fitted parts and holes at plating tolerance; 2-layer checklist;
keep-outs before routing, finisher instead of reruns, 45°-safe via
nudging; outputs-up-to-date hook; audit before the first order tag;
claims pass; designator ranges fixed with a self-test; layer list from
the board; hand-fit BOM split; README hero render.

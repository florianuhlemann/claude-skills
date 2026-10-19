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

## The stories behind the rules

Each line is the incident that produced a rule in `SKILL.md`; the rule
itself is stated there in one sentence.

- **Single-fault table even when the FMEA is declined** — a declined
  FMEA left one project with a back-driven motor pushing current into
  FET body diodes and a fuse whose rating covered none of the fault
  currents.
- **Per-channel-indication question at gate 1** — a "total current"
  requirement hid an expected one-LED-per-channel; found at the audit.
- **Fitted vendor's datasheet** — an ST op-amp was designed to a TI
  sentence from a "pin-compatible" datasheet; input range vs. V+ differed.
- **Thermal figures name their copper condition** — a datasheet R_θJA
  for 1 in² of 2 oz and a JEDEC 4L board were used on a 107 mm² 1 oz 2L
  board.
- **Resistance budget includes pin fan-out and reliefs** — a 0.4 ×
  2.35 mm thread feeding a buck VIN passed the pour-to-pour estimate.
- **Per-resistor power check** — a 1 kΩ 0603 gate pull-down at 159 mW
  passed three readings.
- **Decoupling distance measured, not ticked** — "1–2 mm" was claimed
  for four revisions while it was 6 mm.
- **Hand-fitted parts measured in hand** — XT30 tails of 1.55–1.59 mm
  were given a 1.7 mm hole from the drawing; WAGO square pins need the
  diagonal; "cosmetic" model disagreements were the first hint.
- **Placement review before routing** — 27 of 41 two-pin parts had
  traces leaving ≥ 60° off the pad axis because rotations came from the
  schematic and the autorouter routed around them.
- **Lints with positive self-test cases** — the first entry-angle lint
  folded the angle (backwards counted as axial), skipped IC pins, GND
  and unnumbered pads, and hid in-pad bends behind a minimum-length
  filter; the owner saw every miss at a glance.
- **Silk revision equals the tag** — a docs-only release shipped with
  the previous revision on the silk.
- **Designator ranges in the CPL** — `R1-R5` in the BOM silently dropped
  16 parts from the placement file.
- **Independent audit before the first order tag** — three audits after
  three tags, merged into one, would have saved two releases.
- **Check audit premises first** — six findings quoted a fab minimum of
  0.16 mm (JLC: 0.2 mm), another part's drawing, and necks that did not
  exist in the fill.
- **Schematic gate held separately in reworks** — schematic and layout
  changes presented together let a wiring change through unreviewed.
- **kicad-cli ignores project DRC exclusions** — tested on KiCad 10;
  hence the allowlist file and `drc_gate.py`.
- **Display module in every audit** — not JLC-placeable, no mount,
  supply window outside the rail: the UI-part rule at gate 2.
- **Value changed in four of seven documents** — R_REF "1 kΩ" survived
  in places after the change to 1.2 kΩ: `key-values.md` and the
  stale-value lint.
- **A "passing" check that checked nothing** — a zone script died in a
  pipe, DRC ran on the old board and reported 0 violations: verify the
  verifier, verify the edit in the file.
- **One origin for gerbers, drills and CPL** — a production package
  shipped with every drill offset from its pad by the board's aux
  origin: gerbers used the drill/place origin, drills the absolute one.
  DRC passed, since it checks the board, not the export; a fab-file
  alignment check on the gerbers and drills caught it.
- **A sign-off is a claim about one revision** — a loop length measured
  on one revision was cited as the accepted value for three more
  revisions after a re-route had tripled it. The audit re-measures on
  the revision in front of it; a `gated` answer names what is measured,
  where, and the limit.

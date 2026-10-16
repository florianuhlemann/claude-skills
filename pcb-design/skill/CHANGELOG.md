# pcb-design skill — changelog

## 0.3.0 — 2026-10-16
From the first board's retrospective (v1.0 → v1.1.1), proposals S-1 … S-18.
- `check_entry_angles.py` rebuilt around the rule's purpose: R1 two-pin exits **outward** ≤ 45° (angle no longer folded — backwards exits flagged; exact 45° accepted), R2 IC/connector pins along the pad's long axis turning outside the pad, GND included, end-of-row free side allowed, R3 no bend inside a pad and round pads entered through the centre; exits evaluated on the segment crossing the pad outline (no min-length filter); KiCad 10 string nets; unnumbered paste/NPTH pads ignored; one positive self-test case per real miss (R11, U3 GND, TP2, R12 at 45°). (S-1, S-2, S-7, S-14, S-15, S-16)
- New `check_track_geometry.py`: zero-length, duplicates, off-45° segments, acute corners, 45° T-branches outside pads, with self-test. (S-9, S-17)
- `lint_stale_values.py`: CHANGELOG, retrospective and history-marked lines exempt. (S-3)
- `export_production.sh`: refuses an existing release tag (silk revision = tag, docs-only releases bump too), DRC with `--refill-zones --save-board`, runs the layout lints and keeps their reports, CPL via `--pcb --centroid tht --bom`. (S-4, S-10)
- `fix_cpl_rotation.py`: THT placement points moved to the pad centroid, designators filtered to the BOM. Rule: test points/net ties/fiducials excluded via footprint attributes. (S-4)
- `rotation-corrections.csv`: WSON-6 DRV 0°, vertical 1×2 header +90°, Hirose DF13 vertical +180°, new `confirmed` column. (S-5)
- Text: pin-1 marker is now a filled triangle pointing at pad 1 (replaces the 0.2.3 dot); shared outline line allowed; 0402 for decoupling at ≤ 0.65 mm pitch; decoupling distance measured and listed per IC supply pin; firmware notes may be a separate brief with a pointer; verify-the-verifier extended ("a verifier can pass by not looking"). (S-6, S-11, S-12, S-13)
- Not shipped by scope rule: `fp_silk.py` library rewriter (candidate for promotion after a second board) and `fix_pad_exits.py` — listed as project tooling in `scripts/README.md`. (S-8, S-18)

## 0.2.3 — 2026-10-16
- Footprint silkscreen convention (from the first board's U2 good / Q1 bad comparison): pin-1 dot beyond the outer end of pad 1 on its axis, away from the body centre, clear of copper; silk outline only on pad-free sides; polarity marks at the outer pad end; reference and secondary pin-1 cues on F.Fab inside the body, nothing between pads.
- New "Footprint validation" checklist for phase 5, including a one-time render review per footprint.

## 0.2.2 — 2026-10-16
From the first board's part-orientation note (R6/R7/R17 turned against their traces; 27 of 41 two-pin parts affected).
- Workflow step 6: **placement review before routing** (F.Fab + ratsnest, two-pin parts in line with their connections, no avoidable crossings); orientation follows connections, not the schematic; late additions obey the same rule; autorouter only after the review and never for critical blocks (it never rotates parts).
- Layout rules + checklist: two-pin parts along their signal path, ≤ 45° exit angle (GND fan-out excepted) or justified; passive rows share one orientation; decoupling caps power pad toward the pin, GND pad at the via.
- New `scripts/check_entry_angles.py`: pure-text `.kicad_pcb` lint for trace exits off the pad axis, with `--self-test` negative control; its list is a layout-gate deliverable reviewed with justifications, not forced to zero. Passive auto-orientation deliberately not shipped (placement tooling, wrong for decoupling/Kelvin cases).

## 0.2.1 — 2026-10-16
Scope reduction after review of 0.2.0: the skill owns rules, checklists, docs and the production chain — not tooling or mechanics.
- Enclosure/case design removed from scope: no `mechanical/` folder, fit checks, label placer or model-sync tooling. Gate 1 collects **mechanical inputs** (outline, holes, keep-outs, edge-facing ports, display mount, battery access, labels); production exports STEP for the case owner. `references/mechanical-and-3d.md` deleted; the 3D-model rules moved (shortened) into SKILL.md and `kicad-generation.md`.
- Firmware brief → "firmware notes" section in design-notes; power budget → table in calculations. Docs set is now requirements, key-values, design-notes, calculations, interfaces, parts/, datasheets/ (+ fmea when asked).
- Quote step reduced to one line; git policy reduced to one line; audit response reduced to the table shape.
- Scripted generation is knowledge only (`kicad-generation.md`); the skill ships no generators. Freerouting section shortened.
- `scripts/README.md` import list trimmed to sourcing/library helpers (`jlc_search`, `lcsc_detail`, `stock_check`, `sexpr`/`build_lib`); everything else is project tooling.

## 0.2.0 — 2026-10-16
Based on the first board's retrospectives (mid-project and v1.0).
- Project parameters block (quantity, layers, assembly sides, THT, hand assembly, temperatures, cell, safety, enclosure) replaces hard-coded "2 boards" and temperature defaults; fixed gate-1 question catalog; assumption audit of concept documents.
- Enclosure concept at gate 1, placement study at gate 2, mounting holes never "provisional"; new `references/mechanical-and-3d.md` (model sourcing routes, alignment method, fit check with negative control, placeholders policy).
- UI/display parts must be JLC-placeable (or costed hand plan) and inside the rail's supply window — decided at gate 2.
- Datasheet **deep read** with a constraint-type checklist; self-audit extended beyond the reference circuit; netlist pin-by-pin check.
- Power paths: per-segment net classes, resistance budget calculation, pours by default.
- Length matching gets a frequency threshold (> ~10 MHz / < 5 ns edges); test points labelled by function; silk text ≥ 1.0 mm.
- `docs/key-values.md` single source of truth + `scripts/lint_stale_values.py`; `docs/firmware-brief.md` from gate 3; audit-response table; retrospective as phase 8 and `references/lessons-learned.md`.
- Git: `main` + tags from day one, commit at every gate.
- JLC rules corrected (verified 2026-10-16): THT on economic PCBA, 0.4 mm IC / 0.5 mm BGA pitch, 2.5 mm body-to-edge, rails under 70 × 70 mm, wave-solder caution for SMT standoffs, categories and fees checked live only.
- New `references/kicad-generation.md`: grid, quote escaping, field angles, PWR_FLAG cases, deterministic UUIDs, pcbnew API pitfalls (removals last, one zone per process, pipes), Freerouting scope and approval, verify-the-verifier.
- `export_production.sh`: finds kicad-cli via `kicad_env.sh`, DRC all severities, position export includes THT, lint and revision check before export.
- New scripts `kicad_env.sh`, `pdf_grep.sh`, `lint_stale_values.py`; `scripts/README.md` lists helper scripts to import from the project repo.
- Pushed back / kept: fiducials optional (not removed); a single manual quote is fine, only the automation is dropped; autorouting only for non-critical nets after manual routing of power/RF/matched/FMEA nets.

## 0.1.0 — 2026-10-15
Initial version.

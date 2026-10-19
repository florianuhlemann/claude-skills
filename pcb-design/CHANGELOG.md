# pcb-design skill — changelog

## 0.7.0 — 2026-10-19
Split: pcb-design lays out, designs and delivers the board; all checking moves to the new sibling skill pcb-audit, which audits the milestone at every ⏸ gate.
- `SKILL.md`: every ⏸ hands the milestone to pcb-audit (report in `docs/audits/`); the designer continues on PASS or once every finding is answered by ID (`closed` / `decided` / `gated` / `firmware` / `declined with numbers`). Self-audit, independent audit, audit premises, layout-lint and claims-pass text removed (now in pcb-audit). Frontmatter no longer triggers on reviewing, auditing or fixing, so the two skills do not both fire. 229 → 228 lines.
- New **`Decouples` field convention**: every cap sharing a net with an IC supply pin carries `Decouples` = `<ref>:<pin number>` (`U1:12,U1:34`; pin numbers, never names) or `bulk`; it travels in the exported netlist. Layout: the assigned cap at its pin, power pad toward it, copper pin → cap pad → via/plane, GND via at the cap; distance and path measured by pcb-audit's decoupling check, not ticked. Why: on a shared VDD net the ratsnest draws only the shortest line, so it cannot show which cap serves which pin.
- `references/checklists.md`: "Self-audit" section removed (moved to pcb-audit); pre-layout item for `Decouples`; layout decoupling item points at the measured check; script names dropped from the pad-exit and track-geometry items; handover asks for the gate-7 audit before the first order tag; audit response uses the shared status words and `A<gate>-<nn>` IDs. `doc-templates.md` audit table and `kicad-generation.md` netlist note updated to match.
- Scripts: `audit_netlist.py`, `check_entry_angles.py`, `check_track_geometry.py` removed (they live in pcb-audit). `drc_gate.py` and `lint_stale_values.py` are now copies of pcb-audit's source, marked by a header line. `export_production.sh` no longer runs the claims list and the two layout lints (the gate-7 audit replaces them); stale-value lint, ERC, DRC gate and CPL fix unchanged. `preflight.sh` self-tests only the remaining scripts. Twelve scripts ship.

## 0.6.0 — 2026-10-17
Trim. The rules and the script set are unchanged; SKILL.md is half the size.
- `SKILL.md` cut to roughly half: one sentence per rule, details and checklists only in `references/`; the incidents behind the rules moved to `references/lessons-learned.md` ("The stories behind the rules").
- All fifteen scripts stay in the bundle; `scripts/README.md` lists them by gate and names the project files each one reads. The project structure in SKILL.md now shows those files (`lib/manifest.json`, `lib/lib_patches.py`, `lib/silk-kinds.json`, `docs/netlist-expect.json`, `hardware/drc-allowlist.txt`).
- Dangling references removed (`lcsc_detail.py`, the list of unshipped project scripts); checklists and `kicad-generation.md` no longer name the moved scripts.
- `CHANGELOG.md` moved out of the bundle (this file); the skill zip no longer carries the history.

## 0.5.0 — 2026-10-17
Self-contained: a fresh account/machine no longer needs scripts from earlier projects.
- New `scripts/preflight.sh` (step 0): required/optional tools, JLC API reachability, every self-test, project files.
- Promoted from the two project repos: `jlc_search.py` (+ assembly type column, `--economic`, `--datasheet` download, loud manual fallback), `sexpr.py`, `drc_gate.py` (kicad-cli ignores project DRC exclusions → allowlist with justifications, stale entries fail), `sync_models.py` (`--lib`, `--graphics`).
- Generalized and promoted: `build_lib.py` (driven by `lib/manifest.json` + `lib/lib_patches.py`; renames require a "checked" note; self-test), `fp_silk.py` (kinds inferred with `lib/silk-kinds.json` overrides, library discovered, synthetic self-test), `audit_netlist.py` (pin map in `docs/netlist-expect.json`, project checks module, `--corrupt` negative control, self-test).
- `export_production.sh`: DRC as JSON + report, gated by `drc_gate.py` when `hardware/drc-allowlist.txt` exists.
- `lint_stale_values.py`: `docs/history/` exempt.
- SKILL.md: step 0 preflight; library build, silk and netlist-audit workflow named explicitly; DRC allowlist rule. `scripts/README.md` rewritten by gate; project tooling listed as not shipped.

## 0.4.0 — 2026-10-17
From the second board's retrospective (gate 1 → v0.6.2, three audits, no wiring errors — all rework was context, mechanics and claims).
- **Single-fault table mandatory** for every power path at gate 1 even when the full FMEA is declined (switch shorts/opens, load back-drives, fuse on its curve, input reversed); gate-1 question on per-channel indication.
- Gate 3: every thermal figure names its copper condition and is recomputed for this board's layers/copper; deep read of the **fitted vendor's** datasheet; error terms with a sign; fuse time-current curves; indicators calculated for their fault case. Gate 4 self-audit: per-resistor power check, duplicated-part paralleling re-check, placeholders recomputed; schematic gate held separately even in reworks.
- Gate 5: hand-fitted/mating parts **measured in hand**, hole = max lead + 0.2–0.25 mm at JLC's −0.08 mm plating tolerance, diagonal for square pins, reliefs on hand-soldered pads; CPL rotation measured per LCSC part; "cosmetic" is not a closure for model/datasheet disagreement. New `Fit` symbol field.
- New **2-layer checklist** (B.Cu keep-out around converters before routing, FB/sense/Kelvin by hand, return paths, SW distances, 2L thermal).
- Gate 6: courtyard map for dense areas, no hand route splits a net cluster, via keep-outs under silk before routing, finisher instead of autorouter reruns, fixers move vias on 45° and never drop them, resistance budget from real fills incl. pin fan-out and thermal reliefs, lints justified item by item, silk markers counted before/after clean-up.
- Gate 7: independent audit **before** the first order tag; **claims pass** (`lint_stale_values.py --claims`); `export_production.sh` runs `scripts/regenerate.sh` and fails on any diff under `hardware/`, reads the copper layer list from the board (2L/4L), splits the BOM into JLC and hand-fit, disables reference ranges; `production/README.md` and project README with the isometric render first.
- Gate 8: audit premises checked against the board before acting; "declined with numbers" is a status.
- `fix_cpl_rotation.py`: designator ranges (`R1-R5`) expanded — the old filter silently dropped 16 parts; `--self-test` added.
- `jlcpcb-rules.md`: PTH tolerance, 2 oz minimum 0.2 mm. `kicad-generation.md`: EasyEDA model offsets/rotation, generator↔board drift rule, autorouter leftovers. `lessons-learned.md`: board 2.
- Project tooling, not shipped: `finish_route.py`, `exit_fix.py`, via nudging, mesh solver, `regenerate.sh` (the hook is generic; the script is per project).

## 0.3.1 — 2026-10-16
- Per-part **assembly type** (Economic & Standard vs. Standard only) added as the third live check beside category and stock: one standard-only part forces the whole board to standard PCBA, so it is resolved at gate 2. New symbol field `JLC_Assembly`; parts summary, production README, checklists and `stock_check.py` spec updated; `componentProductType` noted as an observed API field, not a documented mapping.

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

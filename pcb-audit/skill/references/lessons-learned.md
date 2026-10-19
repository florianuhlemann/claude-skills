# Lessons learned (audit-relevant)

The incidents behind this skill's rules, copied verbatim from pcb-design's
lessons learned (0.6.0, "The stories behind the rules"); keep identical.
New audit lessons go into both skills in the same release.

- **Decoupling distance measured, not ticked** — "1–2 mm" was claimed
  for four revisions while it was 6 mm.
- **Independent audit before the first order tag** — three audits after
  three tags, merged into one, would have saved two releases.
- **Check audit premises first** — six findings quoted a fab minimum of
  0.16 mm (JLC: 0.2 mm), another part's drawing, and necks that did not
  exist in the fill.
- **Lints with positive self-test cases** — the first entry-angle lint
  folded the angle (backwards counted as axial), skipped IC pins, GND
  and unnumbered pads, and hid in-pad bends behind a minimum-length
  filter; the owner saw every miss at a glance.
- **Designator ranges in the CPL** — `R1-R5` in the BOM silently dropped
  16 parts from the placement file.
- **Schematic gate held separately in reworks** — schematic and layout
  changes presented together let a wiring change through unreviewed.
- **kicad-cli ignores project DRC exclusions** — tested on KiCad 10;
  hence the allowlist file and `drc_gate.py`.
- **A "passing" check that checked nothing** — a zone script died in a
  pipe, DRC ran on the old board and reported 0 violations: verify the
  verifier, verify the edit in the file.

From the second board ("Numbers"), copied verbatim:

**Numbers:** three audits, 51 findings, no wiring error in any of them;
the rework was thermal assumptions, layout, production data,
connectors, and documentation claims. Six audit premises were wrong
and were declined with numbers.

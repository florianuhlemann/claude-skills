# Audit report template

One file per audited gate and day: `docs/audits/gate<N>-<YYYY-MM-DD>.md`
in the project (a second audit on the same day appends `-2`). An audit of
several gates at once (the pre-tag audit) writes one file per gate, or one
file with one section per gate, each with its own verdict. The auditor
writes the report and does not edit the design; the designer answers in
the response table at the bottom.

Finding IDs: `A<gate>-<nn>`, numbered from 01 per gate and never reused;
a re-audit continues the numbering and refers to the earlier ID when a
finding comes back. Severities: `blocker` / `major` / `minor` / `note`.
Verdict: any blocker → `FAIL`; majors or minors → `PASS with findings`;
otherwise `PASS`.

Evidence is something the designer can open: `file:line`, datasheet name
and page, a measured value in mm with the two objects measured between,
a script output line quoted exactly, a live page with the date seen.
"Looks wrong" is not evidence.

```markdown
# Audit — gate <N> (<gate name>) — <YYYY-MM-DD>

| | |
|---|---|
| Project revision | <git commit / tag / file dates> |
| Gate | <N> <name>; requested <stand-alone / as the gate review of a pcb-design project> |
| Requirements used | docs/requirements.md @ <commit> (or: stated by the user in the request) |
| Coverage | full / reduced — missing: <inputs>; done instead: <…> |
| Tools | KiCad <version>, kicad-cli <yes/no>, scripts self-tested <date> |

**Verdict: <PASS / PASS with findings / FAIL>** — <n> blocker, <n> major, <n> minor, <n> note.

<One paragraph: what the gate delivers, what was checked, the finding that matters most.>

## Findings

| ID | Severity | Finding | Evidence | Rule / requirement |
|---|---|---|---|---|
| A<N>-01 | blocker | <what is wrong, one sentence> | <file:line, page, mm, script line> | <requirement ID, rule, datasheet section> |
| A<N>-02 | major | … | … | … |

<Per finding, when one line is not enough: premise checked (source and
value), why it matters (consequence with a number), what would close it
(the criterion, not the fix).>

## Checks run

| Check | Command / source | Result | Output |
|---|---|---|---|
| ERC | kicad-cli sch erc … | 0 errors, 2 warnings | build/erc.json |
| Netlist | audit_netlist.py build/net.kicad_net | 84 ok, 0 FAIL; --corrupt detected | (pasted) |
| Decoupling | check_decoupling.py build/net.kicad_net [board] | table below | |
| … | | | |

<Paste the check_decoupling.py table and every lint list here; one line
per listed item: justified (where) or finding ID.>

## Premises verified

| Premise | Source checked | Value |
|---|---|---|
| <fab minimum, datasheet limit, pin function, part category> | <page / URL / board file> | <value, date> |

## Not checked

<Item — reason (input missing, tool missing, out of scope for this gate).>

## Designer response (filled by the designer)

| ID | Status | Fix location / numbers |
|---|---|---|
| A<N>-01 | closed / decided / gated / firmware / declined with numbers | <file, section, rev; or the numbers that refute the premise> |
```

The gate stays open until every ID has a status. `closed` means the fix
is in the files and the check that found it was re-run; `gated` names the
gate and the criterion; `declined with numbers` carries the numbers that
refute the premise, and the auditor checks those numbers before accepting.

# Audit report template

One file per audited gate and day: `docs/audits/gate<N>-<YYYY-MM-DD>.md`
in the project (a second audit on the same day appends `-2`). An audit of
several gates at once (the pre-tag audit) writes one file per gate, or one
file with one section per gate, each with its own verdict. The auditor
writes the report and does not edit the design; the designer answers in
the response table at the bottom.

**Keep it short.** Tables, one line of evidence per finding, a short
note under the table only where one line cannot carry the premise or the
consequence. Long essay reports hid stale sign-offs across rounds: the
same accepted number was carried forward three times because nobody
could find it again. Detail that does not change a verdict or a "when"
goes out.

**IDs.** `A<gate>-<nn>`, numbered from 01 per gate within this report and
unique in it. Gate numbers repeat across revisions, so outside the report
an ID is cited with the report file name: `gate7-2026-10-19/A7-03`. A
finding that comes back cites its earlier ID that way.

**Severity** (`blocker` / `major` / `minor` / `note`) drives the verdict:
any blocker → `FAIL`; majors or minors → `PASS with findings`; otherwise
`PASS`. **When** says when to act, independent of severity:
`before ordering` / `this spin if cheap` / `next revision` / `docs`.

**Evidence** is something the designer can open: `file:line`, datasheet
name and page, a measured value in mm with the two objects measured
between (routed copper, not a straight line, for any length), a script
output line quoted exactly, a live page with the date seen. "Looks wrong"
is not evidence.

```markdown
# Audit — gate <N> (<gate name>) — <YYYY-MM-DD>

| | |
|---|---|
| Project revision | <git commit / tag / file dates> |
| Gate | <N> <name>; requested <stand-alone / as the gate review of a pcb-design project> |
| Requirements used | docs/requirements.md @ <commit> (or: stated by the user in the request) |
| Coverage | full / reduced — missing: <inputs>; done instead: <…> |
| Tier | A (files) / B (kicad-cli <version>); scripts self-tested <date> |

**Verdict: <PASS / PASS with findings / FAIL>** — <n> blocker, <n> major, <n> minor, <n> note; <n> before ordering.

## Standing questions

| Question | Answer |
|---|---|
| Correct (wiring, values, calculations)? | <one or two sentences, with IDs> |
| Manufacturable? | |
| Would it work as built? | |
| Borderline values that could fail? | |
| Decisions to revisit? | |
| Signed off as OK but not true on this revision? | |

## Findings

| ID | Severity | When | Finding | Evidence | Rule / requirement |
|---|---|---|---|---|---|
| A<N>-01 | blocker | before ordering | <what is wrong, one sentence> | <file:line, page, routed mm, script line> | <requirement ID, rule, datasheet section> |
| A<N>-02 | major | this spin if cheap | … | … | … |

<Only where one line is not enough: premise checked (source and value),
consequence with a number, what would close it (the criterion, not the
fix).>

## Signed off as OK but not true on this revision

| Claim (where) | Evidence then | Measured now | Finding |
|---|---|---|---|
| <"loop < 5 mm, 2 vias" — review document, CHANGELOG> | <revision, method> | <net_path.py: routed mm, vias> | A<N>-0x |

## Checked and found correct

| Item | Source checked |
|---|---|
| <pin map of U1, all pins> | <datasheet, table/page; netlist export or pcb_nets.py> |
| <C-05 recomputed with the netlist values> | <calculations.md, datasheet page> |

## Decisions reviewed and endorsed

| Decision | Why it stands |
|---|---|
| <architecture or part choice the designer need not revisit> | <one line with the number> |

## Checks run

| Check | Command / source | Result |
|---|---|---|
| Tier | preflight.sh | A / B |
| Parity | pcb_nets.py <pcb> --netlist <net> | 0 differences |
| Netlist | audit_netlist.py <net> --corrupt | <n> ok, 0 FAIL; corruption detected |
| Board | board_stats.py <pcb> | flags: … |
| Fab files | check_fab_files.py <gerbers.zip> --board <pcb> --size WxH | OK / misses |
| Lengths | net_path.py <pcb> --pairs <claims.txt> | <n> pairs, <n> over the claim |
| Decoupling | check_decoupling.py <net> <pcb> | table below |
| Taken as given | <shipped ERC report, date>; <shipped DRC report, date>; <live stock not reachable: project table of date>; <physical check not possible: …> | |

<Paste the check_decoupling.py table and every lint list here; one line
per listed item: justified (where) or finding ID; distinct justification
strings / rows.>

## Premises verified

| Premise | Source checked | Value |
|---|---|---|
| <fab minimum, datasheet limit, pin function, part category> | <page / URL / board file> | <value, date> |

## Not checked

<Item — reason (input missing, tool missing, out of scope for this gate).>

## Designer response (filled by the designer)

| ID | Status | Fix location / numbers |
|---|---|---|
| A<N>-01 | closed / decided / gated / firmware / declined with numbers | <file, section, rev; for gated: measurement, probe point or method, accept limit; for declined: the numbers that refute the premise> |
```

The gate stays open until every ID has a status. `closed` means the fix
is in the files and the check that found it was re-run; `gated` names the
measurement, the probe point or method and the accept limit (and the gate
or build where it is taken); `declined with numbers` carries the numbers
that refute the premise, and the auditor checks those numbers before
accepting.

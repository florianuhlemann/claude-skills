#!/usr/bin/env python3
"""Fail if any 'Previous values' entry from docs/key-values.md still occurs
in the project's documentation or schematic text.

Usage: lint_stale_values.py <project-dir> [--also <extra-regex>]...

key-values.md table columns: Key | Current value | Previous values | Where used | Calc
Previous values are split on ';' or ','. Short/ambiguous tokens (< 3 chars)
are skipped. CHANGELOG.md, docs/retrospective.md and lines that quote history
("was", "until rev", "→", "(history)", "rev 0.x") are exempt. Add --also to
grep extra patterns (e.g. an old revision string).
"""
import re
import sys
from pathlib import Path

SCAN_GLOBS = ["docs/**/*.md", "production/**/*.md", "README.md",
              "hardware/**/*.kicad_sch", "hardware/**/*.kicad_pcb"]
# CHANGELOG.md and the retrospective keep superseded values on purpose.
SKIP_FILES = {"CHANGELOG.md", "docs/retrospective.md", "docs/key-values.md"}
# Lines that deliberately quote history are exempt.
HISTORY = re.compile(r"\b(was|were|until rev|previously|superseded|history)\b|→|\(history\)|\brev 0\.\d", re.I)


def previous_values(kv_path: Path):
    toks = []
    for line in kv_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() in ("key", "---") or set(cells[0]) <= {"-"}:
            continue
        for v in re.split(r"[;,]", cells[2]):
            v = v.strip()
            if len(v) >= 3 and v not in ("—", "-", "n/a"):
                toks.append((cells[0], v))
    return toks


def main(argv):
    if not argv:
        print(__doc__); return 2
    proj = Path(argv[0]); extra = []
    i = 1
    while i < len(argv):
        if argv[i] == "--also" and i + 1 < len(argv):
            extra.append(("--also", argv[i + 1])); i += 2
        else:
            i += 1
    kv = proj / "docs" / "key-values.md"
    if not kv.exists():
        print("no docs/key-values.md — create it (see doc-templates.md)"); return 1
    pats = [(k, re.compile(re.escape(v))) for k, v in previous_values(kv)]
    pats += [(k, re.compile(v)) for k, v in extra]
    hits = 0
    for g in SCAN_GLOBS:
        for f in proj.glob(g):
            if f == kv or str(f.relative_to(proj)) in SKIP_FILES:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if HISTORY.search(line):
                    continue
                for key, pat in pats:
                    if pat.search(line):
                        print(f"{f.relative_to(proj)}:{n}: stale '{pat.pattern}' ({key}): {line.strip()[:120]}")
                        hits += 1
    if hits:
        print(f"\n{hits} stale value occurrence(s) — fix or move the value out of 'Previous values'")
        return 1
    print("stale-value lint: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

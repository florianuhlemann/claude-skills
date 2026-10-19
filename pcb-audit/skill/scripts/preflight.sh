#!/usr/bin/env bash
# Preflight for the pcb-audit skill: which tier this machine audits at, and every script's negative control.
# Run once before the first audit:   bash scripts/preflight.sh
# Exit 0 when python3 is found and every self-test passes. kicad-cli is optional: without it the audit runs
# at Tier A (files parsed directly), which is a full audit except for re-running ERC/DRC; the report says so.
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
ok=1
say()  { printf '  %-24s %s\n' "$1" "$2"; }
opt()  { if command -v "$1" >/dev/null 2>&1; then say "$1" "ok"; else say "$1" "missing (optional) — $2"; fi; }

echo "== Required"
if command -v python3 >/dev/null 2>&1; then say python3 "ok"; else say python3 "MISSING — every check script is Python 3"; ok=0; fi

echo "== Optional"
tier=A
if source "$SCRIPTS/kicad_env.sh" >/dev/null 2>&1; then say "kicad-cli" "ok ($KICAD_CLI)"; tier=B
else say "kicad-cli" "not found — Tier A: ERC/DRC are not re-run; shipped reports are taken as given (say so)"; fi
opt pdftotext "datasheet page references (poppler); search the PDFs by hand otherwise"
opt git       "revision parity: tags, silk revision vs. tag, diff since the last audit"

echo "== Check scripts (self-tests: planted failures must be caught)"
for s in pcb_board.py pcb_nets.py net_path.py board_stats.py check_fab_files.py audit_netlist.py \
         check_decoupling.py check_entry_angles.py check_track_geometry.py drc_gate.py; do
  if python3 -I "$SCRIPTS/$s" --self-test >/dev/null 2>&1; then say "$s" "self-test ok"; else say "$s" "SELF-TEST FAILED — run it directly"; ok=0; fi
done

echo "== Tier"
if [ "$tier" = B ]; then
  echo "  Tier B: kicad-cli re-runs ERC, DRC with schematic parity and a fresh netlist; Tier A checks run as well."
else
  echo "  Tier A: board, netlist export, schematic files, docs and production files are parsed directly"
  echo "  (pcb_nets.py, board_stats.py, net_path.py, check_fab_files.py, check_decoupling.py, lints)."
  echo "  Not possible here: re-running ERC and DRC. Name the shipped ERC/DRC reports as taken as given."
fi

[ $ok = 1 ] && echo "preflight: OK (Tier $tier)" || { echo "preflight: required items missing"; exit 1; }

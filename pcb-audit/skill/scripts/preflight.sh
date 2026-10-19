#!/usr/bin/env bash
# Preflight for the pcb-audit skill: what this machine can check, and every script's negative control.
# Run once before the first audit:   bash scripts/preflight.sh
# Exit 0 when python3 and kicad-cli are found and every self-test passes. Without kicad-cli the audit
# runs on exported files (netlist, DRC/ERC JSON, gerbers) the designer provides; say so in the report.
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
ok=1
say()  { printf '  %-24s %s\n' "$1" "$2"; }
opt()  { if command -v "$1" >/dev/null 2>&1; then say "$1" "ok"; else say "$1" "missing (optional) — $2"; fi; }

echo "== Required"
if command -v python3 >/dev/null 2>&1; then say python3 "ok"; else say python3 "MISSING — every check script is Python 3"; ok=0; fi
if source "$SCRIPTS/kicad_env.sh" >/dev/null 2>&1; then say "kicad-cli" "ok ($KICAD_CLI)"
else say "kicad-cli" "MISSING — install KiCad 10, or ask for net.kicad_net, ERC/DRC JSON and the board file (reduced coverage)"; ok=0; fi

echo "== Optional"
opt pdftotext "datasheet page references (poppler); search the PDFs by hand otherwise"
opt git       "revision parity: tags, silk revision vs. tag, diff since the last audit"
opt unzip     "reading gerbers.zip in the production package"

echo "== Check scripts (self-tests: planted failures must be caught)"
for s in audit_netlist.py check_decoupling.py check_entry_angles.py check_track_geometry.py drc_gate.py; do
  if python3 -I "$SCRIPTS/$s" --self-test >/dev/null 2>&1; then say "$s" "self-test ok"; else say "$s" "SELF-TEST FAILED — run it directly"; ok=0; fi
done

[ $ok = 1 ] && echo "preflight: OK" || { echo "preflight: required items missing"; exit 1; }

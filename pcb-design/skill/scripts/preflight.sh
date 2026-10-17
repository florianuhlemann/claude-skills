#!/usr/bin/env bash
# Preflight for the pcb-design skill on a fresh machine: reports what is available and what the
# skill will do without it. Run once at the start of every project (step 0), from the project root.
#   bash scripts/preflight.sh [project-dir]
# Exit 0 if the required tools are present; the optional ones only print notes.
PROJ="${1:-.}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
ok=1
say()  { printf '  %-16s %s\n' "$1" "$2"; }
need() { if command -v "$1" >/dev/null 2>&1; then say "$1" "ok ($(command -v "$1"))"; else say "$1" "MISSING — $2"; ok=0; fi; }
opt()  { if command -v "$1" >/dev/null 2>&1; then say "$1" "ok"; else say "$1" "missing (optional) — $2"; fi; }

echo "== Required"
need python3 "all skill scripts are Python 3"
need git     "commit at every gate, tags at production gates"
need zip     "gerbers.zip for JLC"
if source "$SCRIPTS/kicad_env.sh" >/dev/null 2>&1; then say "kicad-cli" "ok ($KICAD_CLI)"; else say "kicad-cli" "MISSING — install KiCad 10; ERC/DRC/exports/renders all need it"; ok=0; fi
[ -n "${KICAD_PYTHON:-}" ] && say "pcbnew python" "ok ($KICAD_PYTHON)" || say "pcbnew python" "not found (optional) — sync_models.py and pcbnew tooling need it; everything else is pure Python"

echo "== Optional"
opt pdftotext "pdf_grep.sh page references (poppler); search PDFs by hand otherwise"
opt pdftoppm  "rendering datasheet drawings for hand-made footprints (poppler)"
opt java      "Freerouting (>= 21) — autorouting is optional and must be approved first"
opt curl      "datasheet / model downloads; browser fallback"
if python3 - <<'PY' >/dev/null 2>&1
import json, urllib.request
req = urllib.request.Request("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList",
      data=json.dumps({"keyword": "0603 10k", "currentPage": 1, "pageSize": 1}).encode(),
      headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
urllib.request.urlopen(req, timeout=10).read()
PY
then say "jlc api" "reachable"; else say "jlc api" "unreachable — jlc_search.py will fail; search jlcpcb.com/parts by hand, record category, assembly type, stock, date"; fi

echo "== Skill scripts (self-tests)"
for s in check_entry_angles.py check_track_geometry.py fix_cpl_rotation.py build_lib.py fp_silk.py audit_netlist.py drc_gate.py; do
  if python3 "$SCRIPTS/$s" --self-test >/dev/null 2>&1; then say "$s" "self-test ok"; else say "$s" "SELF-TEST FAILED — run it directly"; ok=0; fi
done

echo "== Project ($PROJ)"
[ -f "$PROJ/lib/manifest.json" ]          && say "lib/manifest"  "present" || say "lib/manifest"  "absent — build_lib.py needs lib/manifest.json (format in its header)"
[ -f "$PROJ/docs/key-values.md" ]         && say "key-values"    "present" || say "key-values"    "absent — create from references/doc-templates.md at gate 3"
[ -x "$PROJ/scripts/regenerate.sh" ]      && say "regenerate"    "hook present (export enforces no-diff)" || say "regenerate"    "no generator hook (fine for hand-edited projects)"
[ -f "$PROJ/hardware/drc-allowlist.txt" ] && say "drc allowlist" "present (drc_gate.py is used)" || say "drc allowlist" "absent — export fails on any DRC violation until one exists"

[ $ok = 1 ] && echo "preflight: OK" || { echo "preflight: required items missing"; exit 1; }

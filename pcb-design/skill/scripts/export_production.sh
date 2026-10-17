#!/usr/bin/env bash
# Production export chain for the pcb-design skill (KiCad 10 kicad-cli). v0.5
#
# Usage: export_production.sh <project-dir> <rev>
#   project-dir contains hardware/<name>.kicad_pro|.kicad_sch|.kicad_pcb,
#   rotation-corrections.csv and the skill's fix_cpl_rotation.py in scripts/.
#
# Runs ERC + DRC first and aborts on errors, then exports gerbers, drills,
# BOM (LCSC fields), position file -> JLC CPL, assembly PDF, STEP and
# 3D renders (top / bottom / isometric).
#
# kicad-cli sub-commands drift between major versions. If anything here
# fails, run `kicad-cli <cmd> --help` and adapt — do not silently drop
# an output.
set -euo pipefail

PROJ="${1:?project dir}"; REV="${2:?rev, e.g. 0.3}"
HW="$PROJ/hardware"
NAME="$(basename "$(ls "$HW"/*.kicad_pro | head -n1)" .kicad_pro)"
SCH="$HW/$NAME.kicad_sch"; PCB="$HW/$NAME.kicad_pcb"
OUT="$PROJ/production/rev$REV"; RND="$PROJ/renders/rev$REV"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT" "$RND"
# shellcheck source=kicad_env.sh
source "$SCRIPTS/kicad_env.sh" >/dev/null
kicad-cli() { "$KICAD_CLI" "$@"; }

echo "== Stale-value lint"
python3 "$SCRIPTS/lint_stale_values.py" "$PROJ" || { echo "stale values in docs — fix before exporting"; exit 1; }

echo "== Release tag"
if git -C "$PROJ" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "$PROJ" tag -l | grep -qx "rev$REV\|v$REV"; then
    [ "${FORCE:-0}" = 1 ] || { echo "tag rev$REV / v$REV already exists — bump the revision (silk revision = release tag). FORCE=1 to override"; exit 1; }
  fi
fi

echo "== Outputs up to date (generators)"
if [ -x "$PROJ/scripts/regenerate.sh" ]; then
  "$PROJ/scripts/regenerate.sh" || { echo "regenerate.sh failed"; exit 1; }
  if git -C "$PROJ" rev-parse --is-inside-work-tree >/dev/null 2>&1 && [ -n "$(git -C "$PROJ" status --porcelain -- hardware)" ]; then
    echo "regeneration changed files under hardware/ — generators and board have drifted; reconcile before tagging"
    git -C "$PROJ" status --porcelain -- hardware; exit 1
  fi
fi

echo "== Revision consistency"
grep -L "rev *$REV\|Rev *$REV\|$REV" "$HW"/*.kicad_sch "$PCB" 2>/dev/null | while read -r f; do
  echo "WARNING: '$REV' not found in $f (title block / silk?)"; done

echo "== ERC"
kicad-cli sch erc --severity-all --exit-code-violations \
  --format report --output "$OUT/erc.rpt" "$SCH" \
  || { echo "ERC violations — fix before exporting"; exit 1; }

echo "== DRC"
# kicad-cli 10 does not apply the .kicad_pro DRC exclusions (tested 2026-10-16): justified warnings live in
# hardware/drc-allowlist.txt ("<type>|<item description> # reason -> design-notes §") and drc_gate.py enforces it.
kicad-cli pcb drc --severity-all --refill-zones --save-board --schematic-parity \
  --format json --output "$OUT/drc.json" "$PCB" >/dev/null || true
kicad-cli pcb drc --severity-all --schematic-parity --format report --output "$OUT/drc.rpt" "$PCB" >/dev/null || true
if [ -f "$HW/drc-allowlist.txt" ]; then
  python3 "$SCRIPTS/drc_gate.py" "$OUT/drc.json" "$HW/drc-allowlist.txt" \
    || { echo "DRC gate failed — fix, or justify the warning in hardware/drc-allowlist.txt"; exit 1; }
else
  python3 - "$OUT/drc.json" <<'PY' || { echo "DRC violations — fix, or create hardware/drc-allowlist.txt with justified warnings"; exit 1; }
import json, sys
d = json.load(open(sys.argv[1])); n = len(d.get("violations", [])) + len(d.get("unconnected_items", [])) + len(d.get("schematic_parity", []))
print(f"DRC: {n} violation(s)"); sys.exit(1 if n else 0)
PY
fi

echo "== Gerbers"
GERB="$OUT/gerbers"; mkdir -p "$GERB"
# copper layer list from the board itself (2L boards have no In*.Cu)
INNER="$(grep -oE '"In[0-9]+\.Cu"' "$PCB" | tr -d '"' | sort -t n -k 2 -n -u | paste -sd, -)"
LAYERS="F.Cu,${INNER:+$INNER,}B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
echo "   layers: $LAYERS"
kicad-cli pcb export gerbers \
  --layers "$LAYERS" \
  --subtract-soldermask --use-drill-file-origin --no-x2 --no-netlist \
  --output "$GERB/" "$PCB"

echo "== Drills"
kicad-cli pcb export drill --format excellon --excellon-separate-th \
  --excellon-units mm --excellon-zeros-format decimal \
  --drill-origin absolute --generate-map --map-format gerberx2 \
  --output "$GERB/" "$PCB"
(cd "$OUT" && rm -f gerbers.zip && zip -qr gerbers.zip gerbers)

echo "== BOM"
kicad-cli sch export bom \
  --fields 'Reference,Value,Footprint,LCSC,MPN,Manufacturer,JLC_Category,JLC_Assembly,Fit,${QUANTITY}' \
  --labels "Designator,Value,Footprint,LCSC Part #,MPN,Manufacturer,Category,Assembly,Fit,Quantity" \
  --group-by "Value,Footprint,LCSC" --exclude-dnp --ref-range-delimiter "" \
  --output "$OUT/bom_all.csv" "$SCH"
# split: Fit == hand -> bom_handfit.csv (owner solders), rest -> bom.csv (JLC places)
python3 - "$OUT" <<'PY'
import csv, sys, pathlib
out = pathlib.Path(sys.argv[1]); rows = list(csv.DictReader(open(out/"bom_all.csv", newline="", encoding="utf-8")))
fn = rows[0].keys() if rows else []
hand = [r for r in rows if (r.get("Fit") or "").strip().lower() == "hand"]
jlc = [r for r in rows if r not in hand]
for name, rs in (("bom.csv", jlc), ("bom_handfit.csv", hand)):
    with open(out/name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fn); w.writeheader(); w.writerows(rs)
std = [r["Designator"] for r in jlc if "standard" in (r.get("Assembly") or "").lower() and "economic" not in (r.get("Assembly") or "").lower()]
print(f"   JLC lines: {len(jlc)}  hand-fit lines: {len(hand)}  standard-only: {len(std)} {std if std else ''}")
PY

echo "== Claims pass (trace each line to a C-nn or a measurement before tagging)"
python3 "$SCRIPTS/lint_stale_values.py" "$PROJ" --claims > "$OUT/claims_to_trace.txt" || true
tail -n 1 "$OUT/claims_to_trace.txt"

echo "== Layout lints (reviewed at the gate; reports kept with the package)"
python3 "$SCRIPTS/check_entry_angles.py" "$PCB" > "$OUT/lint_pad_exits.txt" || true
python3 "$SCRIPTS/check_track_geometry.py" "$PCB" > "$OUT/lint_track_geometry.txt" || true
head -n 1 "$OUT/lint_pad_exits.txt" "$OUT/lint_track_geometry.txt"

echo "== Position -> CPL"
# SMD *and* THT: JLC economic PCBA fits THT parts, so they belong in the CPL.
kicad-cli pcb export pos --format csv --units mm --side both \
  --exclude-dnp --use-drill-file-origin --output "$OUT/pos_kicad.csv" "$PCB"
python3 "$SCRIPTS/fix_cpl_rotation.py" "$OUT/pos_kicad.csv" \
  "$PROJ/rotation-corrections.csv" "$OUT/cpl.csv" --pcb "$PCB" --centroid tht --bom "$OUT/bom.csv"

echo "== Assembly drawing (fab layers + ref designators)"
kicad-cli pcb export pdf --layers "F.Fab,Edge.Cuts" --include-border-title \
  --output "$OUT/assembly_top.pdf" "$PCB"
kicad-cli pcb export pdf --layers "B.Fab,Edge.Cuts" --mirror --include-border-title \
  --output "$OUT/assembly_bottom.pdf" "$PCB"

echo "== Schematic PDF"
kicad-cli sch export pdf --output "$OUT/schematic.pdf" "$SCH"

echo "== STEP"
kicad-cli pcb export step --subst-models --output "$OUT/$NAME.step" "$PCB"

echo "== Renders"
kicad-cli pcb render --side top    --width 2400 --height 1800 --quality high --output "$RND/top.png" "$PCB"
kicad-cli pcb render --side bottom --width 2400 --height 1800 --quality high --output "$RND/bottom.png" "$PCB"
kicad-cli pcb render --side top --rotate "-30,0,-30" --zoom 0.9 --width 2400 --height 1800 --quality high --output "$RND/iso.png" "$PCB"

echo "== Done: $OUT  renders: $RND"
echo "Next: check cpl.csv rotations in the JLC order preview, fill production/README.md, CHANGELOG.md, git tag rev$REV"

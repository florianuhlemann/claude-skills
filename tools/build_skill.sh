#!/usr/bin/env bash
# Rebuild <skill>/<skill>.skill from <skill>/skill/ with a top-level <skill>/ folder inside the zip.
set -euo pipefail
skill="${1:?usage: tools/build_skill.sh <skill>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/$skill/skill"
[ -f "$src/SKILL.md" ] || { echo "no $src/SKILL.md" >&2; exit 1; }
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/$skill"
cp -R "$src"/. "$stage/$skill/"
find "$stage" -name '__pycache__' -type d -prune -exec rm -rf {} + 
find "$stage" -name '.DS_Store' -delete
out="$root/$skill/$skill.skill"
rm -f "$out"
( cd "$stage" && zip -qrX "$out" "$skill" )
echo "$out: $(unzip -l "$out" | tail -1 | awk '{print $2}') files, $(stat -c %s "$out") bytes"

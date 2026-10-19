#!/usr/bin/env bash
# Pre-commit check for one skill: syntax, self-tests, frontmatter, bundle freshness, privacy.
set -uo pipefail
skill="${1:?usage: tools/check_skill.sh <skill>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/$skill/skill"
rc=0
fail() { echo "FAIL: $*"; rc=1; }

[ -f "$dir/SKILL.md" ] || { echo "no $dir/SKILL.md"; exit 1; }
name="$(sed -n 's/^name: *//p' "$dir/SKILL.md" | head -1)"
ver="$(sed -n 's/^ *version: *"\{0,1\}\([0-9][0-9.]*\)"\{0,1\}/\1/p' "$dir/SKILL.md" | head -1)"
[ "$name" = "$skill" ] || fail "frontmatter name '$name' != folder '$skill'"
[ -n "$ver" ] || fail "no metadata.version in SKILL.md"
grep -q '^description: ' "$dir/SKILL.md" || fail "no description in frontmatter"
if [ -f "$root/$skill/CHANGELOG.md" ] && [ -n "$ver" ]; then
  grep -q "^## $ver " "$root/$skill/CHANGELOG.md" || fail "CHANGELOG.md has no entry for $ver"
fi

for f in $(find "$dir" -name '*.py' -not -path '*/__pycache__/*'); do
  python3 -I -m py_compile "$f" 2>/dev/null || fail "py_compile $f"
done
for f in $(find "$dir" -name '*.sh'); do
  bash -n "$f" || fail "bash -n $f"
done
for f in $(grep -lE -- '--self-test' "$dir"/scripts/*.py 2>/dev/null); do
  python3 -I "$f" --self-test >/dev/null 2>&1 || fail "self-test $f"
done
find "$dir" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

bundle="$root/$skill/$skill.skill"
if [ -f "$bundle" ]; then
  tmp="$(mktemp -d)"; unzip -qo "$bundle" -d "$tmp"
  [ -d "$tmp/$skill" ] || fail "bundle has no top-level $skill/ folder"
  diff -rq "$dir" "$tmp/$skill" >/dev/null 2>&1 || fail "bundle is stale: run tools/build_skill.sh $skill"
  rm -rf "$tmp"
else
  echo "note: no $bundle (fine for an unreleased skill)"
fi

"$root/tools/check_private.sh" "$skill" || rc=1
[ $rc = 0 ] && echo "check_skill: $skill OK ($ver)"
exit $rc

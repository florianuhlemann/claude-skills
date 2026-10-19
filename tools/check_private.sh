#!/usr/bin/env bash
# Fail if a skill folder contains an e-mail address or any term from .private-terms.txt (git-ignored).
set -uo pipefail
skill="${1:?usage: tools/check_private.sh <skill>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
terms="${PRIVATE_TERMS_FILE:-$root/.private-terms.txt}"
rc=0
hits="$(grep -rEIn --exclude-dir=__pycache__ --exclude='*.skill' '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}' "$root/$skill" | grep -vE 'noreply@|example\.(com|org)' || true)"
if [ -n "$hits" ]; then echo "e-mail addresses:"; echo "$hits"; rc=1; fi
if [ -f "$terms" ]; then
  while IFS= read -r t; do
    [ -z "$t" ] || [ "${t:0:1}" = "#" ] && continue
    h="$(grep -rEIin --exclude-dir=__pycache__ --exclude='*.skill' -- "$t" "$root/$skill" || true)"
    if [ -n "$h" ]; then echo "private term /$t/:"; echo "$h"; rc=1; fi
  done < "$terms"
else
  echo "note: $terms not found; only e-mail addresses were checked" >&2
fi
if [ -f "$root/$skill/$skill.skill" ]; then
  tmp="$(mktemp -d)"; unzip -qo "$root/$skill/$skill.skill" -d "$tmp"
  z="$(grep -rEIn '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}' "$tmp" | grep -vE 'noreply@|example\.(com|org)' || true)"
  if [ -f "$terms" ]; then
    while IFS= read -r t; do
      [ -z "$t" ] || [ "${t:0:1}" = "#" ] && continue
      z="$z$(grep -rEIin -- "$t" "$tmp" || true)"
    done < "$terms"
  fi
  rm -rf "$tmp"
  if [ -n "$z" ]; then echo "inside the bundle:"; echo "$z"; rc=1; fi
fi
[ $rc = 0 ] && echo "check_private: $skill clean"
exit $rc

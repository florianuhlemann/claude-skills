#!/usr/bin/env bash
# Print page numbers (and the matching lines) of a PDF that contain a pattern,
# for page references in docs/parts/<mpn>.md.
#   pdf_grep.sh <file.pdf> <regex> [context-chars]
set -euo pipefail
PDF="${1:?pdf}"; PAT="${2:?pattern}"
command -v pdftotext >/dev/null || { echo "needs poppler (pdftotext)"; exit 1; }
N=$(pdfinfo "$PDF" | awk '/^Pages:/{print $2}')
for ((p=1; p<=N; p++)); do
  if pdftotext -f "$p" -l "$p" -layout "$PDF" - 2>/dev/null | grep -Eiq -- "$PAT"; then
    echo "== p.$p"
    pdftotext -f "$p" -l "$p" -layout "$PDF" - 2>/dev/null | grep -Ei -- "$PAT" | sed 's/^ *//' | head -n 5
  fi
done

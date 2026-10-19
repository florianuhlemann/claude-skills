#!/usr/bin/env bash
# Copy of pcb-design/scripts/kicad_env.sh (pcb-design 0.7.0); keep identical.
# Source this: sets KICAD_CLI and KICAD_PYTHON for the local KiCad 10 install.
#   source scripts/kicad_env.sh
if command -v kicad-cli >/dev/null 2>&1; then
  KICAD_CLI="$(command -v kicad-cli)"
else
  for c in /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli \
           "$HOME/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli" \
           /usr/bin/kicad-cli /usr/local/bin/kicad-cli /snap/bin/kicad.kicad-cli \
           "/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"; do
    [ -x "$c" ] && KICAD_CLI="$c" && break
  done
fi
if [ -z "${KICAD_CLI:-}" ]; then
  echo "kicad-cli not found — set KICAD_CLI manually" >&2
  return 1 2>/dev/null || exit 1
fi
# pcbnew's Python (macOS bundle); adjust if KiCad 10 moved it.
if [ -z "${KICAD_PYTHON:-}" ]; then
  for p in /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
           /usr/bin/python3; do
    [ -x "$p" ] && "$p" -c "import pcbnew" 2>/dev/null && KICAD_PYTHON="$p" && break
  done
fi
export KICAD_CLI KICAD_PYTHON
echo "KICAD_CLI=$KICAD_CLI"; echo "KICAD_PYTHON=${KICAD_PYTHON:-<not found: pcbnew import failed>}"

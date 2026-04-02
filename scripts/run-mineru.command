#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SH_SCRIPT="$SCRIPT_DIR/run-mineru.sh"

if [[ ! -x "$SH_SCRIPT" ]]; then
  echo "Error: launcher script is not executable: $SH_SCRIPT" >&2
  echo "Press Enter to close..."
  read -r _
  exit 1
fi

if "$SH_SCRIPT" "$@"; then
  exit 0
fi

echo
echo "Launcher failed. Press Enter to close..."
read -r _
exit 1

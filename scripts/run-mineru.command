#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SH_SCRIPT="$SCRIPT_DIR/run-mineru.sh"

if [[ ! -f "$SH_SCRIPT" ]]; then
  echo "Error: launcher script is missing: $SH_SCRIPT" >&2
  echo "Run the canonical entrypoint instead: python -m mineru_batch_cli run ..." >&2
  echo "Press Enter to close..."
  read -r _
  exit 1
fi

sh "$SH_SCRIPT" "$@"
status=$?
if [[ $status -eq 0 ]]; then
  exit 0
fi

echo
echo "Launcher failed (exit code $status)."
echo "Run the canonical entrypoint instead: python -m mineru_batch_cli run ..."
echo "Press Enter to close..."
read -r _
exit "$status"

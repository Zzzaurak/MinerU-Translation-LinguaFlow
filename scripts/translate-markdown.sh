#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: translate-markdown.sh [options] [-- <extra-cli-args>]

Options:
  --input DIR                Input directory (default: inbox)
  --output DIR               Output directory (default: out)
  --config PATH              JSON config path (optional)
  --continue-on-error VALUE  true | false (default: true)
  -h, --help                 Show this help

Notes:
  - Uses project-local Python: ./.venv/bin/python
  - Delegates to: python -m mineru_batch_cli translate
  - Extra unknown args are forwarded to CLI translate command
EOF
}

INPUT_DIR="inbox"
OUTPUT_DIR="out"
CONTINUE_ON_ERROR="true"
CONFIG_PATH=""
EXTRA_ARGS=()

resolve_dir_path() {
  local raw="$1"
  if [[ "$raw" = /* ]]; then
    printf '%s\n' "$raw"
  else
    printf '%s\n' "$PWD/$raw"
  fi
}

resolve_file_path() {
  local raw="$1"
  if [[ "$raw" = /* ]]; then
    printf '%s\n' "$raw"
  else
    printf '%s\n' "$PWD/$raw"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      [[ $# -ge 2 ]] || { echo "Error: --input requires a value" >&2; exit 2; }
      INPUT_DIR="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || { echo "Error: --output requires a value" >&2; exit 2; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --config)
      [[ $# -ge 2 ]] || { echo "Error: --config requires a value" >&2; exit 2; }
      CONFIG_PATH="$2"
      shift 2
      ;;
    --continue-on-error)
      [[ $# -ge 2 ]] || { echo "Error: --continue-on-error requires a value" >&2; exit 2; }
      CONTINUE_ON_ERROR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        EXTRA_ARGS+=("$1")
        shift
      done
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: Python not found in venv: $PYTHON_BIN" >&2
  echo "Hint: create virtual environment and install deps first." >&2
  exit 1
fi

if [[ ! -d "$PROJECT_ROOT/src" ]]; then
  echo "Error: src directory not found under project root: $PROJECT_ROOT" >&2
  exit 1
fi

INPUT_DIR="$(resolve_dir_path "$INPUT_DIR")"
OUTPUT_DIR="$(resolve_dir_path "$OUTPUT_DIR")"

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "Error: Input directory does not exist: $INPUT_DIR" >&2
  exit 1
fi

if [[ -n "$CONFIG_PATH" ]]; then
  CONFIG_PATH="$(resolve_file_path "$CONFIG_PATH")"
  if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "Error: Config file not found: $CONFIG_PATH" >&2
    exit 1
  fi
fi

CMD=(
  "$PYTHON_BIN" -m mineru_batch_cli translate
  --input "$INPUT_DIR"
  --output "$OUTPUT_DIR"
  --continue-on-error "$CONTINUE_ON_ERROR"
)

if [[ -n "$CONFIG_PATH" ]]; then
  CMD+=(--config "$CONFIG_PATH")
fi

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  CMD+=("${EXTRA_ARGS[@]}")
fi

cd "$PROJECT_ROOT"
PYTHONPATH=src "${CMD[@]}"

#!/usr/bin/env sh

# Boundary contract:
# - Authoritative entrypoint is Python module: python -m mineru_batch_cli
# - This script only does arg parsing/path resolution/forwarding
# - Do not implement translation business logic in shell

set -eu
(set -o pipefail >/dev/null 2>&1) && set -o pipefail

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
  - Python resolution order: MINERU_PYTHON_BIN, ./.venv/bin/python, python3, python
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
  raw="$1"
  case "$raw" in
    /*) printf '%s\n' "$raw" ;;
    *) printf '%s\n' "$PWD/$raw" ;;
  esac
}

resolve_file_path() {
  raw="$1"
  case "$raw" in
    /*) printf '%s\n' "$raw" ;;
    *) printf '%s\n' "$PWD/$raw" ;;
  esac
}

resolve_existing_dir_path() {
  raw="$1"
  case "$raw" in
    /*)
      if [ -d "$raw" ]; then
        printf '%s\n' "$raw"
        return 0
      fi
      echo "Error: Input directory does not exist: $raw" >&2
      return 1
      ;;
  esac

  if resolved_dir="$(cd "$raw" 2>/dev/null && pwd)"; then
    printf '%s\n' "$resolved_dir"
    return 0
  fi

  echo "Error: Input directory does not exist: $raw" >&2
  return 1
}

candidate_is_usable() {
  candidate="$1"
  [ -x "$candidate" ] || return 1
  PYTHONPATH="$PROJECT_ROOT/src" "$candidate" -c 'import sys' >/dev/null 2>&1 || return 1
  PYTHONPATH="$PROJECT_ROOT/src" "$candidate" -m mineru_batch_cli --help >/dev/null 2>&1 || return 1
  return 0
}

resolve_python_bin() {
  if [ -n "${MINERU_PYTHON_BIN:-}" ]; then
    if candidate_is_usable "$MINERU_PYTHON_BIN"; then
      printf '%s\n' "$MINERU_PYTHON_BIN"
      return 0
    fi
    echo "Error: MINERU_PYTHON_BIN is set but not usable: $MINERU_PYTHON_BIN" >&2
    echo "Hint: point MINERU_PYTHON_BIN to a working Python interpreter." >&2
    return 1
  fi

  venv_python="$PROJECT_ROOT/.venv/bin/python"
  if candidate_is_usable "$venv_python"; then
    printf '%s\n' "$venv_python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3_bin="$(command -v python3)"
    if candidate_is_usable "$python3_bin"; then
      printf '%s\n' "$python3_bin"
      return 0
    fi
  fi

  if command -v python >/dev/null 2>&1; then
    python_bin="$(command -v python)"
    if candidate_is_usable "$python_bin"; then
      printf '%s\n' "$python_bin"
      return 0
    fi
  fi

  echo "Error: no usable Python interpreter found." >&2
  echo "Hint: set MINERU_PYTHON_BIN, create .venv (python -m venv .venv), and install project dependencies." >&2
  return 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --input)
      [ "$#" -ge 2 ] || { echo "Error: --input requires a value" >&2; exit 2; }
      INPUT_DIR="$2"
      shift 2
      ;;
    --output)
      [ "$#" -ge 2 ] || { echo "Error: --output requires a value" >&2; exit 2; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --config)
      [ "$#" -ge 2 ] || { echo "Error: --config requires a value" >&2; exit 2; }
      CONFIG_PATH="$2"
      shift 2
      ;;
    --continue-on-error)
      [ "$#" -ge 2 ] || { echo "Error: --continue-on-error requires a value" >&2; exit 2; }
      CONTINUE_ON_ERROR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if [ ! -d "$PROJECT_ROOT/src" ]; then
  echo "Error: src directory not found under project root: $PROJECT_ROOT" >&2
  exit 1
fi

INPUT_DIR="$(resolve_existing_dir_path "$INPUT_DIR")"
OUTPUT_DIR="$(resolve_dir_path "$OUTPUT_DIR")"

if [ ! -d "$INPUT_DIR" ]; then
  echo "Error: Input directory does not exist: $INPUT_DIR" >&2
  exit 1
fi

if [ -n "$CONFIG_PATH" ]; then
  CONFIG_PATH="$(resolve_file_path "$CONFIG_PATH")"
  if [ ! -f "$CONFIG_PATH" ]; then
    echo "Error: Config file not found: $CONFIG_PATH" >&2
    exit 1
  fi
fi

PYTHON_BIN="$(resolve_python_bin)"

cd "$PROJECT_ROOT"
if [ -n "$CONFIG_PATH" ]; then
  PYTHONPATH=src "$PYTHON_BIN" -m mineru_batch_cli translate --input "$INPUT_DIR" --output "$OUTPUT_DIR" --continue-on-error "$CONTINUE_ON_ERROR" --config "$CONFIG_PATH" "$@"
else
  PYTHONPATH=src "$PYTHON_BIN" -m mineru_batch_cli translate --input "$INPUT_DIR" --output "$OUTPUT_DIR" --continue-on-error "$CONTINUE_ON_ERROR" "$@"
fi

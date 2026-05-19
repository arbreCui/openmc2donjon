#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
DONJON_DIR="$ROOT/Donjon"
DATA_DIR="${OPENMC2DONJON_DATA_DIR:-$DONJON_DIR/data/openmc2donjon}"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-/Users/wen/openmc-workspace/openmc2donjon/src}"
RUN_DIR="${RUN_DIR:-$DATA_DIR/burn}"
PYTHON_BIN="${PYTHON_BIN:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${OPENMC2DONJON_BURNUP_HELPER:-$SCRIPT_DIR/burnup_axis_smoke.py}"
PREFLIGHT="${OPENMC2DONJON_PREFLIGHT:-$SCRIPT_DIR/validate_mgxs_input_contract.py}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

usage() {
  cat <<'EOF'
usage: run_burnup_axis_smoke.sh

Generate a tiny two-state BURN-axis MULTICOMPO and run DONJON NCR twice:
once at BURN=0 and once at BURN=10. This is a consumer smoke for the
experimental multi-state serializer, not an accepted physics benchmark.

Environment:
  OPENMC2DONJON_ROOT      default /Users/wen/dragon-5.1
  OPENMC2DONJON_DATA_DIR  default $OPENMC2DONJON_ROOT/Donjon/data/openmc2donjon
  OPENMC2DONJON_SRC       default /Users/wen/openmc-workspace/openmc2donjon/src
  RUN_DIR                 default $OPENMC2DONJON_DATA_DIR/burn
  PYTHON_BIN              default openmc-dev python if present, else python3
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
}

result_for_deck() {
  local deck="$1"
  local stem
  stem="$(basename "$deck" .x2m)"
  printf '%s/Darwin_arm64/%s.result' "$DONJON_DIR" "$stem"
}

deck_arg() {
  local deck="$1"
  if [[ "$deck" == "$DONJON_DIR/data/"* ]]; then
    printf '%s' "${deck#"$DONJON_DIR/data/"}"
  else
    printf '%s' "$deck"
  fi
}

run_deck() {
  local label="$1"
  local deck="$2"
  local result
  result="$(result_for_deck "$deck")"
  rm -f "$result"

  echo
  echo "== $label =="
  echo "./rdonjon -q $(deck_arg "$deck")"
  cd "$DONJON_DIR"
  ./rdonjon -q "$(deck_arg "$deck")"
  cd "$ROOT"

  require_path "$result"
  if ! grep -qi "normal end of execution" "$result"; then
    echo "DONJON listing did not reach normal end: $result" >&2
    exit 1
  fi
  grep -E "openmc2donjon burnup-axis smoke|normal end" "$result" | tail -n 6 || true
  echo "PASS $label"
}

echo "== openmc2donjon BURN-axis DONJON consumer smoke =="
echo "root: $ROOT"
echo "data: $DATA_DIR"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

require_path "$DONJON_DIR/rdonjon"
require_path "$PYTHON_BIN"
require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$DATA_DIR"
require_path "$HELPER"
require_path "$PREFLIGHT"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" "$HELPER" fixture \
  --run-dir "$RUN_DIR" \
  --package-src "$PACKAGE_SRC"

h5_path="$RUN_DIR/xs.h5"
mco_path="$RUN_DIR/xs.mco"

echo
echo "== BURN-axis HDF5 preflight =="
"$PYTHON_BIN" "$PREFLIGHT" "$h5_path" \
  --format multicompo \
  --output "$mco_path" \
  --require-transport-dataset \
  --require-volume \
  --check

"$PYTHON_BIN" "$HELPER" convert \
  --run-dir "$RUN_DIR" \
  --package-src "$PACKAGE_SRC"

deck_b0="$RUN_DIR/burn_b0.x2m"
deck_b10="$RUN_DIR/burn_b10.x2m"

run_deck "BURN=0 NCR read" "$deck_b0"
result_b0="$(result_for_deck "$deck_b0")"

run_deck "BURN=10 NCR read" "$deck_b10"
result_b10="$(result_for_deck "$deck_b10")"

"$PYTHON_BIN" "$HELPER" validate \
  --run-dir "$RUN_DIR" \
  --package-src "$PACKAGE_SRC" \
  --result "$result_b0" \
  --result "$result_b10"

echo
echo "openmc2donjon BURN-axis DONJON consumer smoke: PASS"

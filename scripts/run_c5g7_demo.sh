#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${OPENMC2DONJON_DATA_DIR:-$REPO_ROOT/examples/donjon_openmc2donjon}"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_demo}"
PYTEST_CACHE="${PYTEST_CACHE:-/private/tmp/openmc2donjon_pytest_cache}"
C5G7_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_C5G7_SCATTER_ROW_BALANCE_FAIL:-1e-8}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi
PYTEST_PYTHON="${PYTEST_PYTHON:-$PYTHON_BIN}"

RUN_TESTS=1
RUN_DONJON=0

usage() {
  cat <<'EOF'
usage: scripts/run_c5g7_demo.sh [--skip-tests] [--run-donjon]

Run the portable C5G7 converter demo from the repository snapshot.

Default:
  - package tests
  - converter CLI smoke on the C5G7 accepted HDF5
  - LCM ASCII readback of fresh MULTICOMPO and MACROLIB outputs

Optional:
  --run-donjon  also run the DONJON handoff smoke. This requires
                OPENMC2DONJON_ROOT to point at a DRAGON/DONJON checkout and
                OPENMC2DONJON_DATA_DIR to be that checkout's
                Donjon/data/openmc2donjon directory.

Environment:
  OPENMC2DONJON_DATA_DIR  default examples/donjon_openmc2donjon
  OPENMC2DONJON_SRC       default src
  OPENMC2DONJON_ROOT      required only with --run-donjon
  PYTHON_BIN              default openmc-dev python if present, else python3
  PYTEST_PYTHON           default PYTHON_BIN
  RUN_DIR                 default /private/tmp/openmc2donjon_c5g7_demo
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      RUN_TESTS=0
      shift
      ;;
    --run-donjon)
      RUN_DONJON=1
      shift
      ;;
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

require_executable() {
  local exe="$1"
  if [[ "$exe" == */* ]]; then
    if [[ ! -x "$exe" ]]; then
      echo "missing executable: $exe" >&2
      exit 1
    fi
  elif ! command -v "$exe" >/dev/null 2>&1; then
    echo "missing executable on PATH: $exe" >&2
    exit 1
  fi
}

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

MGXS="$DATA_DIR/c5g7_assembly_p1_adf_production.h5"
OUT_MCO="$RUN_DIR/c5g7_demo.mco"
OUT_MAC="$RUN_DIR/c5g7_demo.macrolib.txt"
CHECK_JSON="$RUN_DIR/c5g7_demo_check_summary.json"

echo "== openmc2donjon C5G7 demo =="
echo "repo: $REPO_ROOT"
echo "data: $DATA_DIR"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

require_executable "$PYTHON_BIN"
require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$MGXS"

if [[ "$RUN_TESTS" -eq 1 ]]; then
  echo
  echo "== Package tests =="
  "$PYTEST_PYTHON" -m pytest -q -o "cache_dir=$PYTEST_CACHE" "$REPO_ROOT/tests"
fi

echo
echo "== C5G7 HDF5 preflight =="
"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --summary-json "$CHECK_JSON" \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL"

echo
echo "== Converter smoke =="
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" -o "$OUT_MCO"
"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$MGXS" -o "$OUT_MAC"

"$PYTHON_BIN" - "$OUT_MCO" "$OUT_MAC" <<'PY'
from pathlib import Path
import sys
from openmc2donjon import lcm_ascii

for raw in sys.argv[1:]:
    path = Path(raw)
    blocks = lcm_ascii.read_lcm_ascii(path)
    names = [block.name for block in blocks if block.name]
    if not blocks or names[:1] != ["SIGNATURE"]:
        raise SystemExit(f"{path}: invalid LCM ASCII output")
    print(f"readback {path.name}: blocks={len(blocks)} first={names[:8]}")
PY

if [[ "$RUN_DONJON" -eq 1 ]]; then
  : "${OPENMC2DONJON_ROOT:?OPENMC2DONJON_ROOT is required with --run-donjon}"
  DONJON_DATA_DIR="$OPENMC2DONJON_ROOT/Donjon/data/openmc2donjon"
  require_path "$DONJON_DATA_DIR"
  if [[ "$(cd "$DATA_DIR" && pwd)" != "$(cd "$DONJON_DATA_DIR" && pwd)" ]]; then
    cat >&2 <<EOF
--run-donjon requires OPENMC2DONJON_DATA_DIR to point at:
  $DONJON_DATA_DIR

Current OPENMC2DONJON_DATA_DIR resolves to:
  $(cd "$DATA_DIR" && pwd)

This is needed because rdonjon consumes input decks relative to Donjon/data.
EOF
    exit 2
  fi

  echo
  echo "== DONJON handoff smoke =="
  OPENMC2DONJON_SRC="$PACKAGE_SRC" \
  OPENMC2DONJON_DATA_DIR="$DATA_DIR" \
  OPENMC2DONJON_CAPTURE_LOG=0 \
    bash "$DATA_DIR/run_handoff_smoke.sh"
fi

echo
echo "C5G7 demo: PASS"

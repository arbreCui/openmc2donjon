#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_release_check}"
PYTEST_CACHE="${PYTEST_CACHE:-/private/tmp/openmc2donjon_pytest_cache}"
C5G7_STATEPOINT="${C5G7_STATEPOINT:-/Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5}"
C5G7_ACCEPTED_H5="$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5"

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
REQUIRE_STATEPOINT_EXPORT=0

usage() {
  cat <<'EOF'
usage: scripts/release_check.sh [--skip-tests] [--run-donjon] [--require-statepoint-export]

Run the release/handoff checks for the accepted C5G7 assembly-wise baseline.

Default:
  - package tests
  - CLI help/version smoke
  - C5G7 converter readback smoke
  - accepted baseline manifest validation
  - C5G7 statepoint exporter parity check when C5G7_STATEPOINT exists

Options:
  --skip-tests                 skip pytest
  --run-donjon                 run the full DONJON C5G7 acceptance decks
  --require-statepoint-export  fail if C5G7_STATEPOINT is unavailable

Environment:
  PYTHON_BIN        default openmc-dev python if present, else python3
  PYTEST_PYTHON     default PYTHON_BIN
  RUN_DIR           default /private/tmp/openmc2donjon_release_check
  C5G7_STATEPOINT   saved OpenMC assembly P1 statepoint path
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
    --require-statepoint-export)
      REQUIRE_STATEPOINT_EXPORT=1
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

echo "== openmc2donjon release check =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "run_donjon: $RUN_DONJON"

require_executable "$PYTHON_BIN"
require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$C5G7_ACCEPTED_H5"

if [[ "$RUN_TESTS" -eq 1 ]]; then
  echo
  echo "== Package tests =="
  require_executable "$PYTEST_PYTHON"
  "$PYTEST_PYTHON" -m pytest -q -o "cache_dir=$PYTEST_CACHE" "$REPO_ROOT/tests"
else
  echo
  echo "== Package tests skipped =="
fi

echo
echo "== CLI smoke =="
"$PYTHON_BIN" -m openmc2donjon.cli --version
"$PYTHON_BIN" -m openmc2donjon.cli --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.export_cli --version
"$PYTHON_BIN" -m openmc2donjon.export_cli --help >/dev/null

echo
echo "== C5G7 converter smoke =="
RUN_DIR="$RUN_DIR/c5g7_demo" bash "$REPO_ROOT/scripts/run_c5g7_demo.sh" --skip-tests

echo
echo "== Accepted baseline manifest =="
"$PYTHON_BIN" "$REPO_ROOT/examples/donjon_openmc2donjon/validate_accepted_baseline.py"

echo
echo "== C5G7 statepoint exporter parity =="
if [[ -e "$C5G7_STATEPOINT" ]]; then
  exported_h5="$RUN_DIR/c5g7_exporter_statepoint.h5"
  C5G7_ADF_SOURCE="$C5G7_ACCEPTED_H5" \
  "$PYTHON_BIN" -m openmc2donjon.export_cli \
    --recipe "$REPO_ROOT/scripts/c5g7_export_recipe.py" \
    --statepoint "$C5G7_STATEPOINT" \
    -o "$exported_h5"
  "$PYTHON_BIN" - "$C5G7_ACCEPTED_H5" "$exported_h5" <<'PY'
import sys
from pathlib import Path

import h5py
import numpy as np

reference = Path(sys.argv[1])
candidate = Path(sys.argv[2])
fields = (
    "total",
    "absorption",
    "fission",
    "nu_fission",
    "chi",
    "scatter_matrix",
    "transport_total",
    "adf",
)

with h5py.File(reference, "r") as ref, h5py.File(candidate, "r") as cand:
    ref_names = set(ref["mixtures"])
    cand_names = set(cand["mixtures"])
    if ref_names != cand_names:
        raise SystemExit(f"mixture names differ: {ref_names ^ cand_names}")
    max_abs = 0.0
    missing = []
    for name in sorted(ref_names):
        ref_group = ref["mixtures"][name]
        cand_group = cand["mixtures"][name]
        for field in fields:
            ref_has = field in ref_group
            cand_has = field in cand_group
            if ref_has != cand_has:
                missing.append((name, field))
                continue
            if ref_has:
                diff = np.max(np.abs(ref_group[field][:] - cand_group[field][:]))
                max_abs = max(max_abs, float(diff))
    if missing:
        raise SystemExit(f"missing fields differ: {missing}")
    if max_abs != 0.0:
        raise SystemExit(f"statepoint exporter parity failed: max_abs_diff={max_abs}")
    print(f"statepoint exporter parity OK: max_abs_diff={max_abs}")
PY
else
  if [[ "$REQUIRE_STATEPOINT_EXPORT" -eq 1 ]]; then
    echo "missing C5G7_STATEPOINT: $C5G7_STATEPOINT" >&2
    exit 1
  fi
  echo "skipped; C5G7_STATEPOINT not found: $C5G7_STATEPOINT"
fi

if [[ "$RUN_DONJON" -eq 1 ]]; then
  echo
  echo "== Full DONJON acceptance =="
  RUN_DIR="$RUN_DIR/top_acceptance" \
  PYTHON_BIN="$PYTHON_BIN" \
  PYTEST_PYTHON="$PYTEST_PYTHON" \
  OPENMC2DONJON_CAPTURE_LOG=0 \
    bash "$REPO_ROOT/examples/donjon_openmc2donjon/run_acceptance.sh" --skip-tests
else
  echo
  echo "== Full DONJON acceptance skipped =="
fi

echo
echo "openmc2donjon release check: PASS"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_sph_loop_minicase}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

CASE_DIR="$RUN_DIR/case"
MGXS="$CASE_DIR/inputs/mgxs_library.h5"
CONFIG="$CASE_DIR/loop_config.json"
EXPECTED="$CASE_DIR/expected_sph.h5"
SUMMARY="$CASE_DIR/sph_loop/sph_loop_summary.json"
BUNDLE_DIR="$CASE_DIR/sph_loop/bundle"

echo "== openmc2donjon minimal SPH loop minicase =="

"$PYTHON_BIN" "$SCRIPT_DIR/make_inputs.py" \
  --output-dir "$CASE_DIR" \
  --config "$CONFIG" \
  --driver "$SCRIPT_DIR/fake_low_order_solver.py" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail 1e-12

"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$CONFIG" \
  --summary-json "$SUMMARY" \
  --bundle-dir "$BUNDLE_DIR" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli validate-bundle "$BUNDLE_DIR/manifest.json"

"$PYTHON_BIN" - "$SUMMARY" "$EXPECTED" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii


summary_path = Path(sys.argv[1])
expected_path = Path(sys.argv[2])
summary = json.loads(summary_path.read_text(encoding="utf-8"))

assert summary["decision"] == "openmc2donjon_sph_loop_passed"
assert summary["acceptance_passed"] is True
assert summary["converged"] is True
assert summary["completed_iterations"] == 2
assert len(summary["solves"]) == 3
assert len(summary["workflows"]) == 2
assert len(summary["postprocesses"]) == 2
assert summary["final_solve"]["iteration"] == 2
assert summary["final_ascii"].endswith("corrected.macrolib.txt")

with h5py.File(expected_path, "r") as h5:
    expected_sph = h5["expected_sph"][:]

with h5py.File(summary["final_sph_sidecar"], "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected_sph)
    assert h5.attrs["sph_kind"] == "sph-loop-minicase-iter2"

macrolib = read_macrolib_ascii(summary["final_ascii"])
np.testing.assert_allclose(macrolib.sph, expected_sph)

print(
    "SPH loop minicase OK: "
    f"final_sph={float(expected_sph[0, 0]):.8g} "
    f"summary={summary_path}"
)
PY

echo "openmc2donjon minimal SPH loop minicase: PASS"

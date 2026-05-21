#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_donjon_sph_loop_adapter}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

INPUT_DIR="$RUN_DIR/inputs"
MGXS="$INPUT_DIR/mgxs_library.h5"
REFERENCE_FLUX="$INPUT_DIR/reference_flux.h5"
FLUX_MAP="$INPUT_DIR/flux_map.h5"
EXPECTED="$INPUT_DIR/reference_expected.h5"
CONFIG="$RUN_DIR/donjon_sph_loop_config.json"
LOOP_DIR="$RUN_DIR/sph_loop"
SUMMARY="$LOOP_DIR/sph_loop_summary.json"

echo "== openmc2donjon DONJON SPH loop adapter smoke =="

"$PYTHON_BIN" "$SCRIPT_DIR/make_inputs.py" \
  --output-dir "$INPUT_DIR"

"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail 1e-12

"$PYTHON_BIN" "$SCRIPT_DIR/make_config.py" \
  --output "$CONFIG" \
  --output-dir "$LOOP_DIR" \
  --mgxs "$MGXS" \
  --reference-flux "$REFERENCE_FLUX" \
  --flux-map "$FLUX_MAP" \
  --driver "$SCRIPT_DIR/fake_donjon_driver.py" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$CONFIG" \
  --summary-json "$SUMMARY" \
  --force

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
assert summary["iterations"] == 2
assert summary["output_format"] == "macrolib"
assert len(summary["solves"]) == 3
assert len(summary["workflows"]) == 2
assert len(summary["postprocesses"]) == 2
assert summary["final_solve"]["iteration"] == 2
assert summary["final_ascii"].endswith("corrected.macrolib.txt")

with h5py.File(expected_path, "r") as h5:
    expected_sph = h5["expected_sph"][:]
    expected_ids = h5["scalar_flux_ids"][:]

with h5py.File(summary["final_sph_sidecar"], "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected_sph)
    assert h5.attrs["sph_kind"] == "donjon-sph-loop-adapter-smoke-iter2"

macrolib = read_macrolib_ascii(summary["final_ascii"])
np.testing.assert_allclose(macrolib.sph, expected_sph)

first_workflow = summary["workflows"][0]
with h5py.File(first_workflow["donjon_volume_flux_h5"], "r") as h5:
    np.testing.assert_array_equal(h5["scalar_flux_ids"][:], expected_ids)
    np.testing.assert_allclose(h5["donjon_volume_flux"][:], expected_sph * 0.0 + [[40.0, 400.0], [60.0, 300.0]])

print(
    "DONJON SPH loop adapter OK: "
    f"final_sph={float(expected_sph[0, 0]):.8g} "
    f"summary={summary_path}"
)
PY

echo "openmc2donjon DONJON SPH loop adapter smoke: PASS"

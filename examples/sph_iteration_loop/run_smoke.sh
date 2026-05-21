#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_sph_iteration_loop}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

INPUT_DIR="$RUN_DIR/inputs"
MGXS="$INPUT_DIR/mgxs_library.h5"
PREVIOUS_SPH="$INPUT_DIR/previous_sph.csv"
REFERENCE_FLUX="$INPUT_DIR/reference_flux.csv"
LOW_ORDER_FLUX="$INPUT_DIR/low_order_flux.h5"
REFERENCE="$INPUT_DIR/reference_expected.h5"
NEXT_SPH_TABLE="$RUN_DIR/next_sph.csv"
SPH_SIDECAR="$RUN_DIR/next_sph_sidecar.h5"
AUGMENTED_H5="$RUN_DIR/mgxs_with_next_sph.h5"
MACROLIB="$RUN_DIR/out.macrolib.txt"
CHECK_SUMMARY="$RUN_DIR/check_summary.json"
ITERATION_SUMMARY="$RUN_DIR/sph_iteration_summary.json"
SPH_SIDECAR_SUMMARY="$RUN_DIR/sph_sidecar_summary.json"
SPH_AUGMENT_SUMMARY="$RUN_DIR/sph_augment_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon SPH iteration loop smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

echo
echo "== Build example inputs =="
"$PYTHON_BIN" "$REPO_ROOT/examples/sph_iteration_loop/make_inputs.py" \
  --output-dir "$INPUT_DIR"

echo
echo "== MGXS input contract =="
"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail 1e-12 \
  --summary-json "$CHECK_SUMMARY"

echo
echo "== Build next SPH table =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-update-table "$MGXS" \
  -o "$NEXT_SPH_TABLE" \
  --reference-flux "$REFERENCE_FLUX" \
  --low-order-flux "$LOW_ORDER_FLUX::volume_flux" \
  --previous-sph "$PREVIOUS_SPH" \
  --damping 1.0 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --summary-json "$ITERATION_SUMMARY" \
  --force

echo
echo "== Canonicalize next SPH table =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$MGXS" \
  -o "$SPH_SIDECAR" \
  --mode table \
  --table "$NEXT_SPH_TABLE" \
  --sph-kind sph-iteration-example \
  --sph-real true \
  --sph-applied false \
  --summary-json "$SPH_SIDECAR_SUMMARY" \
  --force

echo
echo "== Inject and convert next SPH =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED_H5" \
  --summary-json "$SPH_AUGMENT_SUMMARY" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$AUGMENTED_H5" -o "$MACROLIB" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-sph \
  --scatter-row-balance-fail 1e-12

echo
echo "== Validate SPH iteration payloads =="
"$PYTHON_BIN" - "$REFERENCE" "$NEXT_SPH_TABLE" "$SPH_SIDECAR" "$AUGMENTED_H5" "$MACROLIB" "$ITERATION_SUMMARY" "$SPH_SIDECAR_SUMMARY" "$SPH_AUGMENT_SUMMARY" <<'PY'
import csv
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

(
    reference_path,
    table_path,
    sidecar_path,
    augmented_path,
    macrolib_path,
    iteration_summary_path,
    sidecar_summary_path,
    augment_summary_path,
) = [Path(value) for value in sys.argv[1:]]

with h5py.File(reference_path, "r") as ref:
    expected = ref["expected_sph"][:]

rows = list(csv.DictReader(table_path.open("r", encoding="utf-8", newline="")))
if len(rows) != expected.size:
    raise SystemExit(f"unexpected SPH table row count: {len(rows)}")

with h5py.File(sidecar_path, "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected)
    if h5.attrs["sph_kind"] != "sph-iteration-example":
        raise SystemExit("SPH sidecar kind mismatch")

with h5py.File(augmented_path, "r") as h5:
    for mix_index, name in enumerate(("ASM_LEFT", "ASM_RIGHT")):
        np.testing.assert_allclose(h5[f"mixtures/{name}/sph"][:], expected[mix_index])

macrolib = read_macrolib_ascii(macrolib_path)
np.testing.assert_allclose(macrolib.sph, expected)

expected_decisions = {
    iteration_summary_path: "openmc2donjon_sph_iteration_table_passed",
    sidecar_summary_path: "openmc2donjon_sph_sidecar_passed",
    augment_summary_path: "openmc2donjon_sph_augment_passed",
}
for path, decision in expected_decisions.items():
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["decision"] != decision:
        raise SystemExit(f"{path.name}: expected {decision}, got {payload['decision']}")

print(
    "SPH iteration loop OK: "
    f"mixtures={expected.shape[0]} groups={expected.shape[1]} "
    f"sph_range={float(np.min(expected)):.6g}..{float(np.max(expected)):.6g}"
)
PY

echo
echo "openmc2donjon SPH iteration loop smoke: PASS"

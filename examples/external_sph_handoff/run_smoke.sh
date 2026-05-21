#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_external_sph_handoff}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

INPUT_DIR="$RUN_DIR/inputs"
MGXS="$INPUT_DIR/mgxs_library.h5"
SPH_TABLE="$INPUT_DIR/external_solver_sph.csv"
REFERENCE="$INPUT_DIR/reference_expected.h5"
SPH_SIDECAR="$RUN_DIR/sph_sidecar.h5"
AUGMENTED_H5="$RUN_DIR/mgxs_with_sph.h5"
MCOMPO="$RUN_DIR/out.mcompo.txt"
MACROLIB="$RUN_DIR/out.macrolib.txt"
EXTRACTED_SIDECAR="$RUN_DIR/sph_from_macrolib.h5"
CHECK_SUMMARY="$RUN_DIR/check_summary.json"
SPH_SIDECAR_SUMMARY="$RUN_DIR/sph_sidecar_summary.json"
SPH_AUGMENT_SUMMARY="$RUN_DIR/sph_augment_summary.json"
EXTRACTED_SUMMARY="$RUN_DIR/sph_from_macrolib_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon external SPH handoff smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

echo
echo "== Build example inputs =="
"$PYTHON_BIN" "$REPO_ROOT/examples/external_sph_handoff/make_inputs.py" \
  --output-dir "$INPUT_DIR"

echo
echo "== MGXS input contract =="
"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail 1e-12 \
  --summary-json "$CHECK_SUMMARY"

echo
echo "== Canonicalize external SPH table =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$MGXS" \
  -o "$SPH_SIDECAR" \
  --mode table \
  --table "$SPH_TABLE" \
  --sph-kind external-sph-example \
  --sph-real true \
  --sph-applied false \
  --summary-json "$SPH_SIDECAR_SUMMARY" \
  --force

echo
echo "== Inject SPH sidecar =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED_H5" \
  --summary-json "$SPH_AUGMENT_SUMMARY" \
  --force

echo
echo "== Convert augmented handoff =="
"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED_H5" -o "$MCOMPO" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-sph \
  --scatter-row-balance-fail 1e-12

"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$AUGMENTED_H5" -o "$MACROLIB" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-sph \
  --scatter-row-balance-fail 1e-12

echo
echo "== Extract SPH from generated macrolib =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$MGXS" \
  -o "$EXTRACTED_SIDECAR" \
  --mode macrolib \
  --macrolib "$MACROLIB" \
  --summary-json "$EXTRACTED_SUMMARY" \
  --force

echo
echo "== Validate generated payloads =="
"$PYTHON_BIN" - "$REFERENCE" "$SPH_SIDECAR" "$AUGMENTED_H5" "$MCOMPO" "$MACROLIB" "$EXTRACTED_SIDECAR" "$CHECK_SUMMARY" "$SPH_SIDECAR_SUMMARY" "$SPH_AUGMENT_SUMMARY" "$EXTRACTED_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon.macrolib import read_macrolib_ascii

(
    reference_path,
    sidecar_path,
    augmented_path,
    mcompo_path,
    macrolib_path,
    extracted_sidecar_path,
    check_summary_path,
    sidecar_summary_path,
    augment_summary_path,
    extracted_summary_path,
) = [Path(value) for value in sys.argv[1:]]

with h5py.File(reference_path, "r") as ref:
    expected = ref["sph"][:]

with h5py.File(sidecar_path, "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected)
    if h5.attrs["sph_kind"] != "external-sph-example":
        raise SystemExit("SPH sidecar kind mismatch")
    if not bool(h5.attrs["sph_real"]):
        raise SystemExit("SPH sidecar should be marked real")
    if bool(h5.attrs["sph_applied"]):
        raise SystemExit("SPH sidecar should be marked unapplied")
    if "source_table" not in h5.attrs:
        raise SystemExit("SPH sidecar did not record table provenance")

with h5py.File(augmented_path, "r") as h5:
    for mix_index, name in enumerate(("ASM_LEFT", "ASM_RIGHT")):
        np.testing.assert_allclose(h5[f"mixtures/{name}/sph"][:], expected[mix_index])

macrolib = read_macrolib_ascii(macrolib_path)
np.testing.assert_allclose(macrolib.sph, expected)
if macrolib.state_vector[13] != 1:
    raise SystemExit("macrolib SPH state-vector flag is not set")

with h5py.File(extracted_sidecar_path, "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected)
    if h5.attrs["sph_kind"] != "macrolib-nsph":
        raise SystemExit("extracted SPH sidecar kind mismatch")

expected_decisions = {
    check_summary_path: "mgxs_input_contract_passed",
    sidecar_summary_path: "openmc2donjon_sph_sidecar_passed",
    augment_summary_path: "openmc2donjon_sph_augment_passed",
    extracted_summary_path: "openmc2donjon_sph_sidecar_passed",
}
for path, decision in expected_decisions.items():
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["decision"] != decision:
        raise SystemExit(f"{path.name}: expected {decision}, got {payload['decision']}")

for path in (mcompo_path, macrolib_path):
    blocks = lcm_ascii.read_lcm_ascii(path)
    names = [block.name for block in blocks if block.name]
    if names[:1] != ["SIGNATURE"]:
        raise SystemExit(f"{path}: invalid LCM ASCII output")
    if "NSPH" not in names:
        raise SystemExit(f"{path}: missing NSPH payload")
    print(f"readback {path.name}: blocks={len(blocks)}")

print(
    "external SPH handoff OK: "
    f"mixtures={expected.shape[0]} groups={expected.shape[1]} "
    f"sph_range={float(np.min(expected)):.6g}..{float(np.max(expected)):.6g}"
)
PY

echo
echo "openmc2donjon external SPH handoff smoke: PASS"

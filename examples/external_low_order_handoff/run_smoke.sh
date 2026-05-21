#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_external_low_order_handoff}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FACES="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"
FACE_WIDTHS="1.0"

INPUT_DIR="$RUN_DIR/inputs"
MGXS="$INPUT_DIR/mgxs_library.h5"
RAW_DRIVER="$INPUT_DIR/external_solver_raw_driver.h5"
SURFACE_FLUX="$INPUT_DIR/openmc_surface_flux.h5"
REFERENCE="$INPUT_DIR/reference_expected.h5"
CANONICAL_DRIVER="$RUN_DIR/low_order_driver.h5"
HOMOGENEOUS_FACE_FLUX="$RUN_DIR/homogeneous_face_flux.h5"
ADF_SIDECAR="$RUN_DIR/adf_sidecar.h5"
AUGMENTED_H5="$RUN_DIR/mgxs_with_adf.h5"
MCOMPO="$RUN_DIR/out.mcompo.txt"
MACROLIB="$RUN_DIR/out.macrolib.txt"
CHECK_SUMMARY="$RUN_DIR/check_summary.json"
LOW_ORDER_SUMMARY="$RUN_DIR/low_order_driver_summary.json"
LOW_ORDER_CHECK_SUMMARY="$RUN_DIR/low_order_driver_check_summary.json"
HOMOGENEOUS_SUMMARY="$RUN_DIR/homogeneous_face_flux_summary.json"
FACE_FLUX_CHECK_SUMMARY="$RUN_DIR/face_flux_check_summary.json"
ADF_SIDECAR_SUMMARY="$RUN_DIR/adf_sidecar_summary.json"
ADF_AUGMENT_SUMMARY="$RUN_DIR/adf_augment_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon external low-order handoff smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

echo
echo "== Build example inputs =="
"$PYTHON_BIN" "$REPO_ROOT/examples/external_low_order_handoff/make_inputs.py" \
  --output-dir "$INPUT_DIR"

echo
echo "== MGXS input contract =="
"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail 1e-12 \
  --summary-json "$CHECK_SUMMARY"

echo
echo "== Canonicalize external low-order driver =="
"$PYTHON_BIN" -m openmc2donjon.cli make-low-order-driver "$MGXS" \
  -o "$CANONICAL_DRIVER" \
  --raw-driver "$RAW_DRIVER" \
  --faces "$FACES" \
  --source-label "external low-order handoff example" \
  --summary-json "$LOW_ORDER_SUMMARY" \
  --force

echo
echo "== Check low-order contract =="
"$PYTHON_BIN" -m openmc2donjon.cli check-low-order-driver \
  "$MGXS" "$CANONICAL_DRIVER" \
  --faces "$FACES" \
  --face-widths "$FACE_WIDTHS" \
  --summary-json "$LOW_ORDER_CHECK_SUMMARY"

echo
echo "== Reconstruct homogeneous face flux =="
"$PYTHON_BIN" -m openmc2donjon.cli make-homogeneous-face-flux "$MGXS" \
  -o "$HOMOGENEOUS_FACE_FLUX" \
  --volume-flux "$CANONICAL_DRIVER" \
  --net-current "$CANONICAL_DRIVER" \
  --faces "$FACES" \
  --face-widths "$FACE_WIDTHS" \
  --summary-json "$HOMOGENEOUS_SUMMARY" \
  --force

echo
echo "== Check face-flux numerator/denominator contract =="
"$PYTHON_BIN" -m openmc2donjon.cli check-face-flux "$MGXS" \
  --surface-flux "$SURFACE_FLUX::detector/surface_phi" \
  --homogeneous-face-flux "$HOMOGENEOUS_FACE_FLUX::homogeneous_face_flux" \
  --faces "$FACES" \
  --summary-json "$FACE_FLUX_CHECK_SUMMARY"

echo
echo "== Build and inject ADF sidecar =="
"$PYTHON_BIN" -m openmc2donjon.cli make-adf-sidecar "$MGXS" \
  -o "$ADF_SIDECAR" \
  --mode flux-ratio \
  --surface-flux "$SURFACE_FLUX::detector/surface_phi" \
  --homogeneous-face-flux "$HOMOGENEOUS_FACE_FLUX::homogeneous_face_flux" \
  --faces "$FACES" \
  --adf-kind external-low-order-example \
  --adf-real true \
  --adf-source-label "external low-order handoff example" \
  --summary-json "$ADF_SIDECAR_SUMMARY" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli augment-adf "$MGXS" \
  --adf-source "$ADF_SIDECAR" \
  -o "$AUGMENTED_H5" \
  --faces "$FACES" \
  --summary-json "$ADF_AUGMENT_SUMMARY" \
  --force

echo
echo "== Convert augmented handoff =="
"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED_H5" -o "$MCOMPO" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces "$FACES" \
  --scatter-row-balance-fail 1e-12

"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$AUGMENTED_H5" -o "$MACROLIB" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces "$FACES" \
  --scatter-row-balance-fail 1e-12

echo
echo "== Validate generated payloads =="
"$PYTHON_BIN" - "$REFERENCE" "$CANONICAL_DRIVER" "$HOMOGENEOUS_FACE_FLUX" "$ADF_SIDECAR" "$AUGMENTED_H5" "$MCOMPO" "$MACROLIB" "$CHECK_SUMMARY" "$LOW_ORDER_SUMMARY" "$LOW_ORDER_CHECK_SUMMARY" "$HOMOGENEOUS_SUMMARY" "$FACE_FLUX_CHECK_SUMMARY" "$ADF_SIDECAR_SUMMARY" "$ADF_AUGMENT_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
from openmc2donjon import lcm_ascii

(
    reference_path,
    driver_path,
    homogeneous_path,
    sidecar_path,
    augmented_path,
    mcompo_path,
    macrolib_path,
    check_summary_path,
    low_order_summary_path,
    low_order_check_summary_path,
    homogeneous_summary_path,
    face_flux_check_summary_path,
    sidecar_summary_path,
    augment_summary_path,
) = [Path(value) for value in sys.argv[1:]]

with h5py.File(reference_path, "r") as ref:
    expected_volume = ref["canonical_volume_flux"][:]
    expected_current = ref["canonical_net_current_density"][:]
    expected_homogeneous = ref["homogeneous_face_flux"][:]
    expected_adf = ref["adf"][:]

with h5py.File(driver_path, "r") as h5:
    np.testing.assert_allclose(h5["volume_flux"][:], expected_volume)
    np.testing.assert_allclose(h5["net_current_density"][:], expected_current)
    if h5["net_current_density"].attrs["sign_convention"] != "positive outward":
        raise SystemExit("canonical driver did not store positive outward current")

with h5py.File(homogeneous_path, "r") as h5:
    np.testing.assert_allclose(h5["homogeneous_face_flux"][:], expected_homogeneous)

with h5py.File(sidecar_path, "r") as h5:
    np.testing.assert_allclose(h5["adf"][:], expected_adf)
    if h5.attrs["adf_kind"] != "external-low-order-example":
        raise SystemExit("ADF sidecar kind mismatch")
    if h5.attrs["adf_real"] != "true":
        raise SystemExit("ADF sidecar should be marked real")

with h5py.File(augmented_path, "r") as h5:
    for mix_index, name in enumerate(("ASM_LEFT", "ASM_RIGHT")):
        for face_index, face in enumerate(("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")):
            np.testing.assert_allclose(
                h5[f"mixtures/{name}/adf/{face}"][:],
                expected_adf[mix_index, face_index],
            )

expected_decisions = {
    check_summary_path: "mgxs_input_contract_passed",
    low_order_summary_path: "openmc2donjon_low_order_driver_passed",
    low_order_check_summary_path: "openmc2donjon_low_order_driver_contract_passed",
    homogeneous_summary_path: "openmc2donjon_homogeneous_face_flux_passed",
    face_flux_check_summary_path: "openmc2donjon_face_flux_contract_passed",
    sidecar_summary_path: "openmc2donjon_adf_sidecar_passed",
    augment_summary_path: "openmc2donjon_adf_augment_passed",
}
for path, decision in expected_decisions.items():
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["decision"] != decision:
        raise SystemExit(f"{path.name}: expected {decision}, got {payload['decision']}")

low_order_summary = json.loads(low_order_summary_path.read_text(encoding="utf-8"))
if low_order_summary["volume_flux_dataset"] != "solver/scalar_flux":
    raise SystemExit("raw-driver volume dataset path was not recorded")
if low_order_summary["net_current_dataset"] != "solver/boundary_current_density":
    raise SystemExit("raw-driver current dataset path was not recorded")
if low_order_summary["net_current_sign_convention_input"] != "positive inward":
    raise SystemExit("positive-inward current convention was not detected")
if low_order_summary["net_current_sign_multiplier"] != -1.0:
    raise SystemExit("positive-inward current was not converted to outward")

face_flux_summary = json.loads(face_flux_check_summary_path.read_text(encoding="utf-8"))
if face_flux_summary["surface_flux_dataset"] != "detector/surface_phi":
    raise SystemExit("explicit surface-flux dataset path was not recorded")
if face_flux_summary["invalid_count"] != 0:
    raise SystemExit("example face-flux ratio should not require invalid-fill")

for path in (mcompo_path, macrolib_path):
    blocks = lcm_ascii.read_lcm_ascii(path)
    names = [block.name for block in blocks if block.name]
    if names[:1] != ["SIGNATURE"]:
        raise SystemExit(f"{path}: invalid LCM ASCII output")
    for required in ("ADF", "HADF", "FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX"):
        if required not in names:
            raise SystemExit(f"{path}: missing {required}")
    print(f"readback {path.name}: blocks={len(blocks)}")

print(
    "external low-order handoff OK: "
    f"mixtures={expected_adf.shape[0]} faces={expected_adf.shape[1]} "
    f"groups={expected_adf.shape[2]}"
)
PY

echo
echo "openmc2donjon external low-order handoff smoke: PASS"

#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
DATA_DIR="$REPO_ROOT/examples/donjon_openmc2donjon"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_from_openmc_adf_smoke}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
C5G7_STATEPOINT="${C5G7_STATEPOINT:-/Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5}"

ACCEPTED_H5="$DATA_DIR/c5g7_assembly_p1_adf_production.h5"
FACE_FLUX_H5="$DATA_DIR/c5g7_homogeneous_face_flux_donjon.h5"
FACES="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"

RUN_LOG="$RUN_DIR/from_openmc_adf.log"
MGXS_H5="$RUN_DIR/mgxs_library.h5"
MCOMPO="$RUN_DIR/out.mcompo.txt"
SUMMARY_JSON="$RUN_DIR/run_summary.json"
CHECK_SUMMARY="$RUN_DIR/check_summary.json"
MANIFEST_JSON="$RUN_DIR/manifest.json"
SIDECAR_SUMMARY="$RUN_DIR/adf_sidecar_summary.json"
FACE_FLUX_CHECK_SUMMARY="$RUN_DIR/face_flux_check_summary.json"
ADF_SUMMARY="$RUN_DIR/adf_summary.json"

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
}

require_path "$PACKAGE_SRC/openmc2donjon/from_openmc_cli.py"
require_path "$ACCEPTED_H5"
require_path "$FACE_FLUX_H5"
require_path "$C5G7_STATEPOINT"
mkdir -p "$RUN_DIR"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon C5G7 from-OpenMC flux-ratio ADF smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "statepoint: $C5G7_STATEPOINT"
echo "accepted_h5: $ACCEPTED_H5"
echo "face_flux_h5: $FACE_FLUX_H5"

set +e
C5G7_ADF_SOURCE="" "$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$REPO_ROOT/scripts/c5g7_export_recipe.py" \
  --statepoint "$C5G7_STATEPOINT" \
  --run-dir "$RUN_DIR" \
  --force-run-dir \
  --build-flux-ratio-adf \
  --adf-surface-flux "$FACE_FLUX_H5::openmc_surface_flux" \
  --homogeneous-face-flux "$FACE_FLUX_H5::homogeneous_face_flux" \
  --adf-faces "$FACES" \
  --adf-invalid-fill 1.0 \
  --adf-clip-min 0.5 \
  --adf-clip-max 2.0 \
  --adf-kind production \
  --adf-real true \
  --adf-source-label "OpenMC mu-surface flux over DONJON mixed-dual current face-flux reconstruction" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail "${OPENMC2DONJON_C5G7_EXPORT_SCATTER_ROW_BALANCE_FAIL:-1e-2}" \
  2>&1 | tee "$RUN_LOG"
status="${PIPESTATUS[0]}"
set -e
if [[ "$status" -ne 0 ]]; then
  echo "C5G7 from-OpenMC flux-ratio ADF smoke failed; log: $RUN_LOG" >&2
  exit "$status"
fi

"$PYTHON_BIN" - "$ACCEPTED_H5" "$MGXS_H5" "$MCOMPO" "$SUMMARY_JSON" "$CHECK_SUMMARY" "$SIDECAR_SUMMARY" "$FACE_FLUX_CHECK_SUMMARY" "$ADF_SUMMARY" "$MANIFEST_JSON" "$FACE_FLUX_H5" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import (
    FROM_OPENMC_SUMMARY_SCHEMA,
    validate_from_openmc_summary,
)

accepted = Path(sys.argv[1])
candidate = Path(sys.argv[2])
mcompo = Path(sys.argv[3])
summary_path = Path(sys.argv[4])
check_summary_path = Path(sys.argv[5])
sidecar_summary_path = Path(sys.argv[6])
face_flux_check_summary_path = Path(sys.argv[7])
adf_summary_path = Path(sys.argv[8])
manifest_path = Path(sys.argv[9])
face_flux = Path(sys.argv[10])
faces = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8").rstrip("\x00")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8").rstrip("\x00")
    return str(value)


def _adf_matrix(mixture, faces: tuple[str, ...]) -> np.ndarray:
    obj = mixture["adf"]
    if hasattr(obj, "keys"):
        return np.stack([np.asarray(obj[face][:], dtype=float) for face in faces])
    return np.asarray(obj[:], dtype=float)


def _dataset_payloads(h5: h5py.File) -> dict[str, np.ndarray]:
    payloads: dict[str, np.ndarray] = {}

    def visit(name: str, obj) -> None:
        if not isinstance(obj, h5py.Dataset):
            return
        if "/adf" in f"/{name}":
            return
        payloads[name] = np.asarray(obj[:])

    h5.visititems(visit)
    return payloads


def _root_attrs_without_adf(h5: h5py.File) -> dict[str, object]:
    return {
        str(key): value
        for key, value in h5.attrs.items()
        if not str(key).startswith("adf")
    }


def _attrs_equal(left: object, right: object) -> bool:
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return np.array_equal(np.asarray(left), np.asarray(right))
    return left == right


summary = json.loads(summary_path.read_text(encoding="utf-8"))
check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
sidecar_summary = json.loads(sidecar_summary_path.read_text(encoding="utf-8"))
face_flux_check_summary = json.loads(face_flux_check_summary_path.read_text(encoding="utf-8"))
adf_summary = json.loads(adf_summary_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

schema_errors = validate_from_openmc_summary(summary)
if schema_errors:
    raise SystemExit("from-OpenMC summary schema failed: " + "; ".join(schema_errors))
if summary.get("schema") != FROM_OPENMC_SUMMARY_SCHEMA:
    raise SystemExit(f"from-OpenMC summary schema mismatch: {summary}")
if check_summary.get("decision") != "mgxs_input_contract_passed":
    raise SystemExit(f"checked conversion failed: {check_summary}")
if sidecar_summary.get("decision") != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit(f"ADF sidecar failed: {sidecar_summary}")
if face_flux_check_summary.get("decision") != "openmc2donjon_face_flux_contract_passed":
    raise SystemExit(f"face-flux contract failed: {face_flux_check_summary}")
if adf_summary.get("decision") != "openmc2donjon_adf_augment_passed":
    raise SystemExit(f"ADF augment failed: {adf_summary}")
if sidecar_summary.get("mode") != "flux-ratio":
    raise SystemExit(f"ADF sidecar mode mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_kind") != "production" or sidecar_summary.get("adf_real") is not True:
    raise SystemExit(f"ADF sidecar provenance mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_surface_flux") != str(face_flux):
    raise SystemExit(f"ADF surface-flux source mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_surface_flux_dataset") != "openmc_surface_flux":
    raise SystemExit(f"ADF surface-flux dataset mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_homogeneous_face_flux") != str(face_flux):
    raise SystemExit(f"ADF homogeneous-flux source mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_homogeneous_face_flux_dataset") != "homogeneous_face_flux":
    raise SystemExit(f"ADF homogeneous-flux dataset mismatch: {sidecar_summary}")
if sidecar_summary.get("invalid_count") != 52 or sidecar_summary.get("invalid_filled_count") != 52:
    raise SystemExit(f"C5G7 ADF invalid-bin policy changed: {sidecar_summary}")
if sidecar_summary.get("clip_min") != 0.5 or sidecar_summary.get("clip_max") != 2.0:
    raise SystemExit(f"C5G7 ADF clip policy changed: {sidecar_summary}")
if face_flux_check_summary.get("schema") != "openmc2donjon.face-flux-contract.v1":
    raise SystemExit(f"face-flux contract schema mismatch: {face_flux_check_summary}")
if face_flux_check_summary.get("surface_flux") != str(face_flux):
    raise SystemExit(f"face-flux contract surface source mismatch: {face_flux_check_summary}")
if face_flux_check_summary.get("surface_flux_dataset") != "openmc_surface_flux":
    raise SystemExit(f"face-flux contract surface dataset mismatch: {face_flux_check_summary}")
if face_flux_check_summary.get("homogeneous_face_flux") != str(face_flux):
    raise SystemExit(f"face-flux contract homogeneous source mismatch: {face_flux_check_summary}")
if face_flux_check_summary.get("homogeneous_face_flux_dataset") != "homogeneous_face_flux":
    raise SystemExit(f"face-flux contract homogeneous dataset mismatch: {face_flux_check_summary}")
if (
    face_flux_check_summary.get("invalid_count") != 52
    or face_flux_check_summary.get("invalid_filled_count") != 52
):
    raise SystemExit(f"C5G7 face-flux invalid-bin policy changed: {face_flux_check_summary}")
if (
    face_flux_check_summary.get("clip_min") != 0.5
    or face_flux_check_summary.get("clip_max") != 2.0
):
    raise SystemExit(f"C5G7 face-flux clip policy changed: {face_flux_check_summary}")

labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required_labels = {
    "mgxs",
    "mcompo",
    "run-summary",
    "check-summary",
    "adf-source",
    "adf-summary",
    "surface-flux",
    "homogeneous-face-flux",
    "face-flux-check-summary",
    "adf-sidecar-summary",
    "recipe",
}
if set(labels) != required_labels:
    raise SystemExit(f"bundle labels changed: {sorted(labels)}")
if labels["surface-flux"]["source"] != str(face_flux):
    raise SystemExit(f"surface-flux manifest source mismatch: {labels['surface-flux']}")
if labels["homogeneous-face-flux"]["source"] != str(face_flux):
    raise SystemExit(
        f"homogeneous-face-flux manifest source mismatch: {labels['homogeneous-face-flux']}"
    )
if labels["adf-sidecar-summary"].get("summary_decision") != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit(f"ADF sidecar manifest summary mismatch: {labels}")
if labels["face-flux-check-summary"].get("summary_decision") != "openmc2donjon_face_flux_contract_passed":
    raise SystemExit(f"face-flux manifest summary mismatch: {labels}")

with h5py.File(accepted, "r") as ref, h5py.File(candidate, "r") as out:
    ref_payloads = _dataset_payloads(ref)
    out_payloads = _dataset_payloads(out)
    if set(ref_payloads) != set(out_payloads):
        missing = sorted(set(ref_payloads) - set(out_payloads))
        extra = sorted(set(out_payloads) - set(ref_payloads))
        raise SystemExit(f"non-ADF dataset set changed: missing={missing} extra={extra}")
    max_abs = 0.0
    for name, expected in ref_payloads.items():
        actual = out_payloads[name]
        if expected.shape != actual.shape:
            raise SystemExit(f"{name}: shape changed {actual.shape} != {expected.shape}")
        if np.issubdtype(expected.dtype, np.number):
            delta = float(np.max(np.abs(actual - expected))) if expected.size else 0.0
            max_abs = max(max_abs, delta)
            if delta != 0.0:
                raise SystemExit(f"{name}: non-ADF dataset differs max_abs={delta}")
        elif not np.array_equal(actual, expected):
            raise SystemExit(f"{name}: non-ADF dataset differs")

    ref_attrs = _root_attrs_without_adf(ref)
    out_attrs = _root_attrs_without_adf(out)
    if set(ref_attrs) != set(out_attrs):
        missing = sorted(set(ref_attrs) - set(out_attrs))
        extra = sorted(set(out_attrs) - set(ref_attrs))
        raise SystemExit(f"non-ADF root attrs changed: missing={missing} extra={extra}")
    for key, expected in ref_attrs.items():
        if not _attrs_equal(out_attrs[key], expected):
            raise SystemExit(f"non-ADF root attr differs: {key}")

    names = tuple(str(name) for name in ref["mixtures"])
    expected_adf = np.stack([_adf_matrix(ref["mixtures"][name], faces) for name in names])
    actual_adf = np.stack([_adf_matrix(out["mixtures"][name], faces) for name in names])
    if not np.array_equal(actual_adf, expected_adf):
        delta = float(np.max(np.abs(actual_adf - expected_adf)))
        raise SystemExit(f"from-OpenMC ADF payload differs from accepted baseline: max_abs={delta}")

blocks = lcm_ascii.read_lcm_ascii(mcompo)
names = [block.name for block in blocks if block.name]
if names[:1] != ["SIGNATURE"]:
    raise SystemExit(f"{mcompo}: invalid LCM ASCII output")

checks = {
    "format": summary.get("format") == "multicompo",
    "hdf5": Path(summary.get("hdf5", "")) == candidate,
    "output": Path(summary.get("output", "")) == mcompo,
    "hdf5_kept": summary.get("hdf5_kept") is True,
    "energy_groups": summary.get("energy_groups") == 7,
    "legendre_order": summary.get("legendre_order") == 1,
    "mixture_count": summary.get("mixture_count") == 9,
    "state_points": summary.get("state_points") == 1,
    "checked": summary.get("checked") is True,
    "check_passed": summary.get("check_passed") is True,
    "check_summary_json": Path(summary.get("check_summary_json", "")) == check_summary_path,
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit(f"from-OpenMC summary failed checks: {failed}; {summary}")

print(
    "C5G7 from-OpenMC flux-ratio ADF OK: "
    f"mixtures={len(expected_adf)} faces={len(faces)} groups={expected_adf.shape[-1]} "
    f"non_adf_max_abs={max_abs:g} adf_max_abs=0 mco_blocks={len(blocks)}"
)
PY

echo
echo "openmc2donjon C5G7 from-OpenMC flux-ratio ADF smoke: PASS"

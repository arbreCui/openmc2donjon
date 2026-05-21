#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
DATA_DIR="$REPO_ROOT/examples/donjon_openmc2donjon"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_adf_source_smoke}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

ACCEPTED_H5="$DATA_DIR/c5g7_assembly_p1_adf_production.h5"
FACE_FLUX_H5="$DATA_DIR/c5g7_homogeneous_face_flux_donjon.h5"
FACES="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"

STRIPPED_H5="$RUN_DIR/c5g7_no_adf.h5"
SIDECAR_H5="$RUN_DIR/c5g7_flux_ratio_adf_sidecar.h5"
SIDECAR_SUMMARY="$RUN_DIR/c5g7_flux_ratio_adf_sidecar.summary.json"
AUGMENTED_H5="$RUN_DIR/c5g7_with_rebuilt_adf.h5"
AUGMENT_SUMMARY="$RUN_DIR/c5g7_with_rebuilt_adf.summary.json"
CHECK_SUMMARY="$RUN_DIR/c5g7_with_rebuilt_adf.check.json"

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
}

require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$ACCEPTED_H5"
require_path "$FACE_FLUX_H5"
mkdir -p "$RUN_DIR"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon C5G7 ADF source reconstruction smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "accepted_h5: $ACCEPTED_H5"
echo "face_flux_h5: $FACE_FLUX_H5"

"$PYTHON_BIN" - "$ACCEPTED_H5" "$STRIPPED_H5" <<'PY'
from pathlib import Path
import shutil
import sys

import h5py

source = Path(sys.argv[1])
stripped = Path(sys.argv[2])
shutil.copyfile(source, stripped)
with h5py.File(stripped, "r+") as h5:
    for key in list(h5.attrs):
        if str(key).startswith("adf"):
            del h5.attrs[key]
    for group in h5["mixtures"].values():
        if "adf" in group:
            del group["adf"]
print(f"stripped production ADF payload: {stripped}")
PY

"$PYTHON_BIN" -m openmc2donjon.cli make-adf-sidecar "$ACCEPTED_H5" \
  -o "$SIDECAR_H5" \
  --mode flux-ratio \
  --surface-flux "$FACE_FLUX_H5::openmc_surface_flux" \
  --homogeneous-face-flux "$FACE_FLUX_H5::homogeneous_face_flux" \
  --faces "$FACES" \
  --invalid-fill 1.0 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --adf-kind production \
  --adf-real true \
  --adf-source-label "OpenMC mu-surface flux over DONJON mixed-dual current face-flux reconstruction" \
  --summary-json "$SIDECAR_SUMMARY" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli augment-adf "$STRIPPED_H5" \
  --adf-source "$SIDECAR_H5" \
  -o "$AUGMENTED_H5" \
  --faces "$FACES" \
  --summary-json "$AUGMENT_SUMMARY" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli check "$AUGMENTED_H5" \
  --require-adf \
  --expected-adf-faces "$FACES" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail "${OPENMC2DONJON_C5G7_SCATTER_ROW_BALANCE_FAIL:-1e-8}" \
  --summary-json "$CHECK_SUMMARY"

"$PYTHON_BIN" - "$ACCEPTED_H5" "$SIDECAR_H5" "$AUGMENTED_H5" "$SIDECAR_SUMMARY" "$AUGMENT_SUMMARY" "$CHECK_SUMMARY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np

accepted = Path(sys.argv[1])
sidecar = Path(sys.argv[2])
augmented = Path(sys.argv[3])
sidecar_summary = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
augment_summary = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))
check_summary = json.loads(Path(sys.argv[6]).read_text(encoding="utf-8"))
faces = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8").rstrip("\x00")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8").rstrip("\x00")
    return str(value)


def _adf_matrix(mixture, faces: tuple[str, ...]) -> np.ndarray:
    adf = mixture["adf"]
    if hasattr(adf, "keys"):
        return np.stack([adf[face][:] for face in faces])
    return np.asarray(adf[:], dtype=float)


def _adf_group(mixture, faces: tuple[str, ...]) -> np.ndarray:
    adf = mixture["adf"]
    if not hasattr(adf, "keys"):
        return np.asarray(adf[:], dtype=float)
    return np.stack([adf[face][:] for face in faces])


if sidecar_summary.get("decision") != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit(f"ADF sidecar did not pass: {sidecar_summary}")
if sidecar_summary.get("mode") != "flux-ratio":
    raise SystemExit(f"ADF sidecar mode mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_kind") != "production" or sidecar_summary.get("adf_real") is not True:
    raise SystemExit(f"ADF sidecar provenance mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_surface_flux_dataset") != "openmc_surface_flux":
    raise SystemExit(f"ADF sidecar did not use OpenMC surface flux: {sidecar_summary}")
if sidecar_summary.get("adf_homogeneous_face_flux_dataset") != "homogeneous_face_flux":
    raise SystemExit(f"ADF sidecar did not use homogeneous face flux: {sidecar_summary}")
if sidecar_summary.get("invalid_count") != 52 or sidecar_summary.get("invalid_filled_count") != 52:
    raise SystemExit(f"C5G7 ADF invalid-bin policy changed: {sidecar_summary}")
if sidecar_summary.get("clip_min") != 0.5 or sidecar_summary.get("clip_max") != 2.0:
    raise SystemExit(f"C5G7 ADF clip policy changed: {sidecar_summary}")

if augment_summary.get("decision") != "openmc2donjon_adf_augment_passed":
    raise SystemExit(f"ADF augment did not pass: {augment_summary}")
if check_summary.get("decision") != "mgxs_input_contract_passed":
    raise SystemExit(f"ADF augmented HDF5 preflight did not pass: {check_summary}")

with h5py.File(accepted, "r") as ref, h5py.File(sidecar, "r") as src, h5py.File(augmented, "r") as out:
    names = tuple(str(name) for name in ref["mixtures"])
    sidecar_names = tuple(_decode(value) for value in src["adf"].attrs["mixture_names"])
    sidecar_faces = tuple(_decode(value) for value in src["adf"].attrs["face_names"])
    if sidecar_names != names:
        raise SystemExit(f"sidecar mixture order changed: {sidecar_names} != {names}")
    if sidecar_faces != faces:
        raise SystemExit(f"sidecar face names changed: {sidecar_faces}")

    expected = np.stack([_adf_matrix(ref["mixtures"][name], faces) for name in names])
    rebuilt = np.asarray(src["adf"][:], dtype=float)
    if not np.array_equal(rebuilt, expected):
        max_abs = float(np.max(np.abs(rebuilt - expected)))
        raise SystemExit(f"rebuilt sidecar ADF differs from accepted payload: max_abs={max_abs}")

    augmented_values = np.stack([_adf_group(out["mixtures"][name], faces) for name in names])
    if not np.array_equal(augmented_values, expected):
        max_abs = float(np.max(np.abs(augmented_values - expected)))
        raise SystemExit(f"augmented HDF5 ADF differs from accepted payload: max_abs={max_abs}")

print(
    "C5G7 ADF source reconstruction OK: "
    f"mixtures={len(names)} faces={len(faces)} groups={expected.shape[-1]} "
    "max_abs=0"
)
PY

echo
echo "openmc2donjon C5G7 ADF source reconstruction smoke: PASS"

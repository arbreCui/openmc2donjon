#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
DATA_DIR="$REPO_ROOT/examples/donjon_openmc2donjon"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_donjon_face_flux_smoke}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

DONJON_ROOT="${OPENMC2DONJON_DONJON_ROOT:-/Users/wen/dragon-5.1}"
MGXS_SOURCE="${OPENMC2DONJON_C5G7_MGXS_SOURCE:-/Users/wen/openmc-workspace/c5g7_converter_test/mgxs_library_assembly_p1.h5}"
CURRENTS_H5="${OPENMC2DONJON_C5G7_CURRENTS:-$DONJON_ROOT/Donjon/data/openmc2donjon/c5g7_boundary_currents_mu_full.h5}"
FLUX_DUMP="${OPENMC2DONJON_C5G7_FLUX_DUMP:-$DONJON_ROOT/Donjon/Darwin_arm64/c5g7ap1_flux_dump.result}"
TRACK_DUMP="${OPENMC2DONJON_C5G7_TRACK_DUMP:-$DONJON_ROOT/Donjon/Darwin_arm64/c5g7ap1_track_dump.result}"

ACCEPTED_H5="$DATA_DIR/c5g7_assembly_p1_adf_production.h5"
ACCEPTED_FACE_FLUX_H5="$DATA_DIR/c5g7_homogeneous_face_flux_donjon.h5"
REGENERATED_FACE_FLUX_H5="$RUN_DIR/c5g7_homogeneous_face_flux_donjon.regenerated.h5"
FACE_FLUX_CHECK_SUMMARY="$RUN_DIR/c5g7_face_flux_check.summary.json"
SIDECAR_H5="$RUN_DIR/c5g7_donjon_face_flux_adf_sidecar.h5"
SIDECAR_SUMMARY="$RUN_DIR/c5g7_donjon_face_flux_adf_sidecar.summary.json"
FACES="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
}

optional_source_missing=0
for path in "$MGXS_SOURCE" "$CURRENTS_H5" "$FLUX_DUMP" "$TRACK_DUMP"; do
  if [[ ! -e "$path" ]]; then
    optional_source_missing=1
    echo "missing local source input: $path"
  fi
done
if [[ "$optional_source_missing" -eq 1 ]]; then
  echo "skipped; C5G7 DONJON face-flux regeneration needs local DONJON dumps"
  exit 0
fi

require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$ACCEPTED_H5"
require_path "$ACCEPTED_FACE_FLUX_H5"
mkdir -p "$RUN_DIR"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon C5G7 DONJON face-flux regeneration smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "mgxs_source: $MGXS_SOURCE"
echo "currents_h5: $CURRENTS_H5"
echo "flux_dump: $FLUX_DUMP"
echo "track_dump: $TRACK_DUMP"

"$PYTHON_BIN" "$REPO_ROOT/scripts/extract_c5g7_donjon_face_flux.py" \
  --mgxs "$MGXS_SOURCE" \
  --currents "$CURRENTS_H5" \
  --flux-dump "$FLUX_DUMP" \
  --track-dump "$TRACK_DUMP" \
  --output "$REGENERATED_FACE_FLUX_H5"

"$PYTHON_BIN" - "$ACCEPTED_FACE_FLUX_H5" "$REGENERATED_FACE_FLUX_H5" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

import h5py
import numpy as np

accepted = Path(sys.argv[1])
regenerated = Path(sys.argv[2])
path_attrs = {"mgxs", "currents", "flux_dump", "track_dump"}


def _dataset_payloads(path: Path) -> dict[str, np.ndarray]:
    payloads: dict[str, np.ndarray] = {}
    with h5py.File(path, "r") as h5:
        def visit(name: str, obj) -> None:
            if isinstance(obj, h5py.Dataset):
                payloads[name] = obj[()]

        h5.visititems(visit)
    return payloads


def _normalize_attr(value):
    if isinstance(value, np.generic):
        return value.item()
    return value


def _attr_equal(left, right) -> bool:
    left = _normalize_attr(left)
    right = _normalize_attr(right)
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return np.array_equal(left, right)
    return left == right


ref_payloads = _dataset_payloads(accepted)
new_payloads = _dataset_payloads(regenerated)
if set(ref_payloads) != set(new_payloads):
    raise SystemExit(
        "regenerated face-flux datasets changed: "
        f"missing={sorted(set(ref_payloads) - set(new_payloads))} "
        f"extra={sorted(set(new_payloads) - set(ref_payloads))}"
    )
for name, expected in ref_payloads.items():
    actual = new_payloads[name]
    if expected.shape != actual.shape:
        raise SystemExit(
            f"dataset {name!r} shape changed: {actual.shape} != {expected.shape}"
        )
    if not np.array_equal(actual, expected):
        if np.issubdtype(np.asarray(expected).dtype, np.number):
            max_abs = float(np.max(np.abs(actual - expected)))
            raise SystemExit(f"dataset {name!r} changed: max_abs={max_abs}")
        raise SystemExit(f"dataset {name!r} changed")

with h5py.File(accepted, "r") as ref, h5py.File(regenerated, "r") as new:
    ref_attrs = {key: ref.attrs[key] for key in ref.attrs if key not in path_attrs}
    new_attrs = {key: new.attrs[key] for key in new.attrs if key not in path_attrs}
    if set(ref_attrs) != set(new_attrs):
        raise SystemExit(
            "regenerated face-flux attributes changed: "
            f"missing={sorted(set(ref_attrs) - set(new_attrs))} "
            f"extra={sorted(set(new_attrs) - set(ref_attrs))}"
        )
    for key, expected in ref_attrs.items():
        actual = new_attrs[key]
        if not _attr_equal(actual, expected):
            raise SystemExit(
                f"attribute {key!r} changed: {actual!r} != {expected!r}"
            )

print(
    "C5G7 DONJON face-flux regeneration OK: "
    f"datasets={len(ref_payloads)} checked_attrs={len(ref_attrs)} max_abs=0"
)
PY

"$PYTHON_BIN" -m openmc2donjon.cli check-face-flux "$ACCEPTED_H5" \
  --surface-flux "$REGENERATED_FACE_FLUX_H5::openmc_surface_flux" \
  --homogeneous-face-flux "$REGENERATED_FACE_FLUX_H5::homogeneous_face_flux" \
  --faces "$FACES" \
  --invalid-fill 1.0 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --summary-json "$FACE_FLUX_CHECK_SUMMARY"

"$PYTHON_BIN" -m openmc2donjon.cli make-adf-sidecar "$ACCEPTED_H5" \
  -o "$SIDECAR_H5" \
  --mode flux-ratio \
  --surface-flux "$REGENERATED_FACE_FLUX_H5::openmc_surface_flux" \
  --homogeneous-face-flux "$REGENERATED_FACE_FLUX_H5::homogeneous_face_flux" \
  --faces "$FACES" \
  --invalid-fill 1.0 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --adf-kind production \
  --adf-real true \
  --adf-source-label "OpenMC mu-surface flux over DONJON mixed-dual current face-flux reconstruction" \
  --summary-json "$SIDECAR_SUMMARY" \
  --force

"$PYTHON_BIN" - "$ACCEPTED_H5" "$SIDECAR_H5" "$FACE_FLUX_CHECK_SUMMARY" "$SIDECAR_SUMMARY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np

accepted = Path(sys.argv[1])
sidecar = Path(sys.argv[2])
check_summary = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
sidecar_summary = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
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


if check_summary.get("decision") != "openmc2donjon_face_flux_contract_passed":
    raise SystemExit(f"face-flux contract did not pass: {check_summary}")
if check_summary.get("invalid_count") != 52 or check_summary.get("invalid_filled_count") != 52:
    raise SystemExit(f"C5G7 face-flux invalid-bin policy changed: {check_summary}")
if check_summary.get("clip_min") != 0.5 or check_summary.get("clip_max") != 2.0:
    raise SystemExit(f"C5G7 face-flux clip policy changed: {check_summary}")

if sidecar_summary.get("decision") != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit(f"ADF sidecar did not pass: {sidecar_summary}")
if sidecar_summary.get("mode") != "flux-ratio":
    raise SystemExit(f"ADF sidecar mode mismatch: {sidecar_summary}")
if sidecar_summary.get("adf_kind") != "production" or sidecar_summary.get("adf_real") is not True:
    raise SystemExit(f"ADF sidecar provenance mismatch: {sidecar_summary}")

with h5py.File(accepted, "r") as ref, h5py.File(sidecar, "r") as src:
    names = tuple(str(name) for name in ref["mixtures"])
    sidecar_names = tuple(_decode(value) for value in src["adf"].attrs["mixture_names"])
    sidecar_faces = tuple(_decode(value) for value in src["adf"].attrs["face_names"])
    if sidecar_names != names:
        raise SystemExit(f"sidecar mixture order changed: {sidecar_names} != {names}")
    if sidecar_faces != faces:
        raise SystemExit(f"sidecar face names changed: {sidecar_faces}")

    expected = np.stack([_adf_matrix(ref["mixtures"][name], faces) for name in names])
    actual = np.asarray(src["adf"][:], dtype=float)
    if not np.array_equal(actual, expected):
        max_abs = float(np.max(np.abs(actual - expected)))
        raise SystemExit(f"ADF rebuilt from regenerated DONJON face flux changed: max_abs={max_abs}")

print(
    "C5G7 DONJON face-flux ADF rebuild OK: "
    f"mixtures={len(names)} faces={len(faces)} groups={expected.shape[-1]} max_abs=0"
)
PY

echo
echo "openmc2donjon C5G7 DONJON face-flux regeneration smoke: PASS"

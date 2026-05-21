#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_sph_iteration_flux}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
C5G7_ACCEPTED_H5="${C5G7_ACCEPTED_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5}"
C5G7_DONJON_FLUX_H5="${C5G7_DONJON_FLUX_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_homogeneous_face_flux_donjon.h5}"
C5G7_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_C5G7_SCATTER_ROW_BALANCE_FAIL:-1e-8}"

NEXT_SPH_TABLE="$RUN_DIR/c5g7_next_sph_from_donjon_flux.csv"
SPH_SIDECAR="$RUN_DIR/c5g7_next_sph_from_donjon_flux.sidecar.h5"
AUGMENTED_H5="$RUN_DIR/c5g7_with_next_sph_from_donjon_flux.h5"
MACROLIB="$RUN_DIR/c5g7_next_sph_from_donjon_flux.macrolib.txt"
ITERATION_SUMMARY="$RUN_DIR/c5g7_sph_iteration_summary.json"
SPH_SIDECAR_SUMMARY="$RUN_DIR/c5g7_sph_sidecar_summary.json"
SPH_AUGMENT_SUMMARY="$RUN_DIR/c5g7_sph_augment_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon C5G7 SPH iteration from DONJON flux smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "mgxs: $C5G7_ACCEPTED_H5"
echo "flux: $C5G7_DONJON_FLUX_H5"

if [[ ! -e "$C5G7_ACCEPTED_H5" ]]; then
  echo "missing C5G7 accepted MGXS: $C5G7_ACCEPTED_H5" >&2
  exit 1
fi
if [[ ! -e "$C5G7_DONJON_FLUX_H5" ]]; then
  echo "missing C5G7 DONJON flux HDF5: $C5G7_DONJON_FLUX_H5" >&2
  exit 1
fi

echo
echo "== Build next SPH table from OpenMC/DONJON volume fluxes =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-update-table "$C5G7_ACCEPTED_H5" \
  -o "$NEXT_SPH_TABLE" \
  --reference-flux "$C5G7_DONJON_FLUX_H5::openmc_volume_flux" \
  --low-order-flux "$C5G7_DONJON_FLUX_H5::donjon_volume_flux" \
  --damping 0.5 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --source-label "C5G7 OpenMC/DONJON volume-flux SPH iteration smoke" \
  --summary-json "$ITERATION_SUMMARY" \
  --force

echo
echo "== Canonicalize next SPH table =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$C5G7_ACCEPTED_H5" \
  -o "$SPH_SIDECAR" \
  --mode table \
  --table "$NEXT_SPH_TABLE" \
  --sph-kind c5g7-donjon-flux-iteration-smoke \
  --sph-real false \
  --sph-applied false \
  --summary-json "$SPH_SIDECAR_SUMMARY" \
  --force

echo
echo "== Inject and convert next SPH =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$C5G7_ACCEPTED_H5" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED_H5" \
  --summary-json "$SPH_AUGMENT_SUMMARY" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$AUGMENTED_H5" -o "$MACROLIB" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-sph \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL"

echo
echo "== Validate C5G7 SPH iteration artifacts =="
"$PYTHON_BIN" - "$NEXT_SPH_TABLE" "$SPH_SIDECAR" "$AUGMENTED_H5" "$MACROLIB" "$ITERATION_SUMMARY" "$SPH_SIDECAR_SUMMARY" "$SPH_AUGMENT_SUMMARY" <<'PY'
import csv
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

(
    table_path,
    sidecar_path,
    augmented_path,
    macrolib_path,
    iteration_summary_path,
    sidecar_summary_path,
    augment_summary_path,
) = [Path(value) for value in sys.argv[1:]]

iteration_summary = json.loads(iteration_summary_path.read_text(encoding="utf-8"))
if iteration_summary["decision"] != "openmc2donjon_sph_iteration_table_passed":
    raise SystemExit(f"SPH iteration summary failed: {iteration_summary}")
if iteration_summary["reference_flux_dataset"] != "openmc_volume_flux":
    raise SystemExit("reference flux dataset mismatch")
if iteration_summary["low_order_flux_dataset"] != "donjon_volume_flux":
    raise SystemExit("low-order flux dataset mismatch")
if iteration_summary["mixture_count"] != 9 or iteration_summary["energy_groups"] != 7:
    raise SystemExit(f"unexpected C5G7 shape metadata: {iteration_summary}")
if iteration_summary["sph_minimum"] <= 1.0:
    raise SystemExit(f"unexpected non-amplifying SPH range: {iteration_summary}")

rows = list(csv.DictReader(table_path.open("r", encoding="utf-8", newline="")))
if len(rows) != 9 * 7:
    raise SystemExit(f"unexpected SPH table row count: {len(rows)}")

with h5py.File(sidecar_path, "r") as sidecar:
    sph = sidecar["sph"][:]
    names = list(iteration_summary["mixture_names"])
    if sidecar.attrs["sph_kind"] != "c5g7-donjon-flux-iteration-smoke":
        raise SystemExit("SPH sidecar kind mismatch")
    if sidecar.attrs["sph_real"]:
        raise SystemExit("SPH smoke sidecar must be marked sph_real=false")
    if sidecar.attrs.get("source_table") != str(table_path):
        raise SystemExit("SPH sidecar source_table mismatch")
    if sph.shape != (9, 7):
        raise SystemExit(f"unexpected SPH shape: {sph.shape}")
    if float(np.min(sph)) <= 1.0 or float(np.max(sph)) >= 2.0:
        raise SystemExit(f"unexpected SPH range: {float(np.min(sph))}..{float(np.max(sph))}")

with h5py.File(augmented_path, "r") as augmented:
    for mix_index, name in enumerate(names):
        np.testing.assert_allclose(augmented[f"mixtures/{name}/sph"][:], sph[mix_index])
    if augmented.attrs["sph_kind"] != "c5g7-donjon-flux-iteration-smoke":
        raise SystemExit("augmented HDF5 SPH kind mismatch")

macrolib = read_macrolib_ascii(macrolib_path)
np.testing.assert_allclose(macrolib.sph, sph)
for path, decision in {
    sidecar_summary_path: "openmc2donjon_sph_sidecar_passed",
    augment_summary_path: "openmc2donjon_sph_augment_passed",
}.items():
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["decision"] != decision:
        raise SystemExit(f"{path.name}: expected {decision}, got {payload['decision']}")

print(
    "C5G7 SPH iteration from DONJON flux OK: "
    f"mixtures={sph.shape[0]} groups={sph.shape[1]} "
    f"sph_range={float(np.min(sph)):.6g}..{float(np.max(sph)):.6g}"
)
PY

echo
echo "openmc2donjon C5G7 SPH iteration from DONJON flux smoke: PASS"

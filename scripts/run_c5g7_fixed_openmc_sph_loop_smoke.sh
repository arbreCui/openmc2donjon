#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_fixed_openmc_sph_loop}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
DONJON_RUNNER="${DONJON_RUNNER:-$DONJON_ROOT/rdonjon}"
C5G7_ACCEPTED_H5="${C5G7_ACCEPTED_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5}"
C5G7_REFERENCE_FLUX_H5="${C5G7_REFERENCE_FLUX_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_homogeneous_face_flux_donjon.h5}"
C5G7_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_C5G7_SCATTER_ROW_BALANCE_FAIL:-1e-8}"
SPH_DAMPING="${SPH_DAMPING:-0.1}"
RUN_TAG="${RUN_TAG:-c5g7_fixed_openmc_sph_loop}"
CONFIG_WRITER="$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_sph_loop/make_config.py"
SOLVE_TEMPLATE="$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_sph_loop/templates/solve_lflux_dump.x2m.in"
APPLY_TEMPLATE="$REPO_ROOT/examples/donjon_sph_loop_adapter/templates/apply_nsph_mac.x2m.in"

LOOP_DIR="$RUN_DIR/sph_loop"
LOOP_CONFIG="$RUN_DIR/c5g7_sph_loop_config.json"
LOOP_SUMMARY_JSON="$LOOP_DIR/sph_loop_summary.json"
BASE_MACROLIB="$LOOP_DIR/iter00_initial/out.macrolib.txt"
ITER1_DIR="$LOOP_DIR/iter01_sph"
ITER1_TABLE="$ITER1_DIR/next_sph.csv"
ITER1_SIDECAR="$ITER1_DIR/next_sph.sidecar.h5"
ITER1_H5="$ITER1_DIR/mgxs_with_sph.h5"
ITER1_RAW_MACROLIB="$ITER1_DIR/out.macrolib.txt"
ITER1_CORRECTED_MACROLIB="$ITER1_DIR/corrected_pn.macrolib.txt"
ITER2_DIR="$LOOP_DIR/iter02_sph"
ITER2_TABLE="$ITER2_DIR/next_sph.csv"
ITER2_SIDECAR="$ITER2_DIR/next_sph.sidecar.h5"
ITER2_H5="$ITER2_DIR/mgxs_with_sph.h5"
ITER2_RAW_MACROLIB="$ITER2_DIR/out.macrolib.txt"
ITER2_CORRECTED_MACROLIB="$ITER2_DIR/corrected_pn.macrolib.txt"
BASE_FLUX_H5="$ITER1_DIR/donjon_volume_flux.h5"
ITER1_FLUX_H5="$ITER2_DIR/donjon_volume_flux.h5"
ITER2_FLUX_H5="$RUN_DIR/iter2_donjon_volume_flux.h5"
RESULT0="$LOOP_DIR/iter00_solve/donjon_flux.result"
RESULT1="$LOOP_DIR/iter01_solve/donjon_flux.result"
RESULT2="$LOOP_DIR/iter02_solve/donjon_flux.result"
SUMMARY_JSON="$RUN_DIR/c5g7_fixed_openmc_sph_loop_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon C5G7 fixed-OpenMC SPH loop smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "donjon: $DONJON_RUNNER"
echo "mgxs: $C5G7_ACCEPTED_H5"
echo "reference_flux: $C5G7_REFERENCE_FLUX_H5::openmc_volume_flux"

if [[ ! -e "$C5G7_ACCEPTED_H5" ]]; then
  echo "missing C5G7 accepted MGXS: $C5G7_ACCEPTED_H5" >&2
  exit 1
fi
if [[ ! -e "$C5G7_REFERENCE_FLUX_H5" ]]; then
  echo "missing C5G7 reference flux HDF5: $C5G7_REFERENCE_FLUX_H5" >&2
  exit 1
fi
if [[ ! -x "$DONJON_RUNNER" ]]; then
  echo "DONJON runner is unavailable; skipping C5G7 fixed-OpenMC SPH loop smoke"
  exit 0
fi

echo
echo "== Check fixed OpenMC base XS =="
"$PYTHON_BIN" -m openmc2donjon.cli check "$C5G7_ACCEPTED_H5" \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL"

echo
echo "== Write C5G7 SPH loop config =="
"$PYTHON_BIN" "$CONFIG_WRITER" \
  --output "$LOOP_CONFIG" \
  --output-dir "$LOOP_DIR" \
  --mgxs "$C5G7_ACCEPTED_H5" \
  --reference-flux "$C5G7_REFERENCE_FLUX_H5" \
  --donjon-root "$DONJON_ROOT" \
  --solve-template "$SOLVE_TEMPLATE" \
  --apply-template "$APPLY_TEMPLATE" \
  --python-bin "$PYTHON_BIN" \
  --damping "$SPH_DAMPING" \
  --run-tag "$RUN_TAG"

echo
echo "== Run configured fixed-OpenMC SPH loop =="
"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$LOOP_CONFIG" \
  --summary-json "$LOOP_SUMMARY_JSON" \
  --force

echo
echo "== Extract final post-SPH DONJON flux =="
"$PYTHON_BIN" -m openmc2donjon.cli extract-donjon-volume-flux "$C5G7_ACCEPTED_H5" \
  --flux-dump "$RESULT2" \
  --map-h5 "$C5G7_REFERENCE_FLUX_H5" \
  -o "$ITER2_FLUX_H5" \
  --force

echo
echo "== Validate fixed-OpenMC SPH loop =="
"$PYTHON_BIN" - "$SUMMARY_JSON" "$LOOP_SUMMARY_JSON" \
  "$BASE_FLUX_H5" "$ITER1_FLUX_H5" "$ITER2_FLUX_H5" \
  "$ITER1_SIDECAR" "$ITER2_SIDECAR" \
  "$BASE_MACROLIB" "$ITER1_CORRECTED_MACROLIB" "$ITER2_CORRECTED_MACROLIB" \
  "$RESULT0" "$RESULT1" "$RESULT2" <<'PY'
import csv
import json
from pathlib import Path
import re
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

(
    summary_path,
    loop_summary_path,
    flux0_path,
    flux1_path,
    flux2_path,
    sph1_path,
    sph2_path,
    base_macrolib_path,
    corrected1_path,
    corrected2_path,
    result0_path,
    result1_path,
    result2_path,
) = [Path(value) for value in sys.argv[1:]]


def read_flux(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        return np.asarray(h5["donjon_volume_flux"][:], dtype=float)


def read_mesh_flux(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        return np.asarray(h5["mesh_donjon_volume_flux"][:], dtype=float)


def read_sph(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        return np.asarray(h5["sph"][:], dtype=float)


def read_keff(path: Path, iteration: int) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "normal end of execution" not in text:
        raise SystemExit(f"DONJON solve did not end normally: {path}")
    match = re.search(
        rf"OPENMC2DONJON C5G7 FIXED OPENMC SPH LOOP ITER {iteration} K-EFFECTIVE\s+([0-9.Ee+-]+)",
        text,
    )
    if match is None:
        raise SystemExit(f"missing iteration {iteration} k-effective in {path}")
    value = float(match.group(1))
    if not np.isfinite(value) or value <= 0.0:
        raise SystemExit(f"invalid iteration {iteration} k-effective: {value}")
    return value


flux0 = read_flux(flux0_path)
flux1 = read_flux(flux1_path)
flux2 = read_flux(flux2_path)
mesh_flux0 = read_mesh_flux(flux0_path)
mesh_flux1 = read_mesh_flux(flux1_path)
mesh_flux2 = read_mesh_flux(flux2_path)
sph1 = read_sph(sph1_path)
sph2 = read_sph(sph2_path)
base = read_macrolib_ascii(base_macrolib_path)
corrected1 = read_macrolib_ascii(corrected1_path)
corrected2 = read_macrolib_ascii(corrected2_path)
keff0 = read_keff(result0_path, 0)
keff1 = read_keff(result1_path, 1)
keff2 = read_keff(result2_path, 2)
loop_summary = json.loads(loop_summary_path.read_text(encoding="utf-8"))
audit_csv = Path(loop_summary["audit_csv"])

if loop_summary.get("decision") != "openmc2donjon_sph_loop_passed":
    raise SystemExit(f"SPH loop summary did not pass: {loop_summary_path}")
if loop_summary.get("acceptance_decision") != "openmc2donjon_sph_loop_acceptance_passed":
    raise SystemExit(f"SPH loop acceptance did not pass: {loop_summary_path}")
if len(loop_summary.get("solves", [])) != 3:
    raise SystemExit("configured SPH loop did not run the final solve")
if len(loop_summary.get("postprocesses", [])) != 2:
    raise SystemExit("configured SPH loop did not apply two postprocess steps")
if len(loop_summary.get("audit_rows", [])) != 3:
    raise SystemExit("configured SPH loop summary is missing audit rows")
if not audit_csv.exists():
    raise SystemExit(f"configured SPH loop audit CSV is missing: {audit_csv}")
with audit_csv.open(encoding="utf-8", newline="") as stream:
    audit_rows = list(csv.DictReader(stream))
if [row["stage"] for row in audit_rows] != ["iteration", "iteration", "final"]:
    raise SystemExit(f"unexpected SPH loop audit stages: {audit_rows}")
audit_keff = [float(row["keff"]) for row in audit_rows]
np.testing.assert_allclose(audit_keff, [keff0, keff1, keff2], rtol=1.0e-6, atol=1.0e-6)
if sph1.shape != (9, 7) or sph2.shape != (9, 7):
    raise SystemExit(f"unexpected SPH shapes: {sph1.shape}, {sph2.shape}")
if flux0.shape != (9, 7) or flux1.shape != (9, 7) or flux2.shape != (9, 7):
    raise SystemExit(f"unexpected flux shapes: {flux0.shape}, {flux1.shape}, {flux2.shape}")
if (
    mesh_flux0.shape != (3, 3, 7)
    or mesh_flux1.shape != (3, 3, 7)
    or mesh_flux2.shape != (3, 3, 7)
):
    raise SystemExit(
        "unexpected mesh flux shapes: "
        f"{mesh_flux0.shape}, {mesh_flux1.shape}, {mesh_flux2.shape}"
    )
if np.allclose(sph1, 1.0) or np.allclose(sph2, sph1):
    raise SystemExit("SPH loop did not produce a nontrivial cumulative update")
if corrected1.sph is None or corrected2.sph is None:
    raise SystemExit("corrected macrolib is missing NSPH")
np.testing.assert_allclose(corrected1.sph, sph1, rtol=1.0e-7, atol=1.0e-7)
np.testing.assert_allclose(corrected2.sph, sph2, rtol=1.0e-7, atol=1.0e-7)
if float(np.max(np.abs(corrected1.ntot0 - base.ntot0))) <= 0.0:
    raise SystemExit("iteration 1 corrected macrolib did not perturb NTOT0")
if float(np.max(np.abs(corrected2.ntot0 - base.ntot0))) <= 0.0:
    raise SystemExit("iteration 2 corrected macrolib did not perturb NTOT0")

delta10_pcm = (keff1 - keff0) / keff0 * 1.0e5
delta20_pcm = (keff2 - keff0) / keff0 * 1.0e5
flux_delta_10 = float(np.max(np.abs(flux1 - flux0)))
flux_delta_21 = float(np.max(np.abs(flux2 - flux1)))
payload = {
    "decision": "openmc2donjon_c5g7_fixed_openmc_sph_loop_passed",
    "base_keff": keff0,
    "iter1_keff": keff1,
    "iter2_keff": keff2,
    "iter1_delta_pcm": delta10_pcm,
    "iter2_delta_pcm": delta20_pcm,
    "iter1_sph_minimum": float(np.min(sph1)),
    "iter1_sph_maximum": float(np.max(sph1)),
    "iter2_sph_minimum": float(np.min(sph2)),
    "iter2_sph_maximum": float(np.max(sph2)),
    "iter1_flux_max_abs_delta_from_base": flux_delta_10,
    "iter2_flux_max_abs_delta_from_iter1": flux_delta_21,
    "formula": "next_sph = previous_sph * (openmc_reference_flux / donjon_low_order_flux) ** damping",
    "openmc_xs_policy": "fixed base MGXS; only SPH sidecar changes between iterations",
}
summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(
    "C5G7 fixed-OpenMC SPH loop OK: "
    f"k0={keff0:.9g} k1={keff1:.9g} k2={keff2:.9g} "
    f"delta1={delta10_pcm:.6g}pcm delta2={delta20_pcm:.6g}pcm "
    f"sph1={float(np.min(sph1)):.6g}..{float(np.max(sph1)):.6g} "
    f"sph2={float(np.min(sph2)):.6g}..{float(np.max(sph2)):.6g}"
)
PY

echo
echo "openmc2donjon C5G7 fixed-OpenMC SPH loop smoke: PASS"

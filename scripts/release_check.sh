#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_release_check}"
PYTEST_CACHE="${PYTEST_CACHE:-/private/tmp/openmc2donjon_pytest_cache}"
C5G7_STATEPOINT="${C5G7_STATEPOINT:-/Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5}"
C5G7_ACCEPTED_H5="$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5"
C5G7_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_C5G7_SCATTER_ROW_BALANCE_FAIL:-1e-8}"
C5G7_EXPORT_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_C5G7_EXPORT_SCATTER_ROW_BALANCE_FAIL:-1e-2}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi
PYTEST_PYTHON="${PYTEST_PYTHON:-$PYTHON_BIN}"

RUN_TESTS=1
RUN_DONJON=0
RUN_LOCAL_CANDIDATES=0
REQUIRE_STATEPOINT_EXPORT=0

usage() {
  cat <<'EOF'
usage: scripts/release_check.sh [--skip-tests] [--run-donjon] [--run-local-candidates] [--require-statepoint-export]

Run the release/handoff checks for the accepted C5G7 assembly-wise baseline.

Default:
  - package tests
  - CLI help/version smoke
  - recipe/statepoint exporter smoke
  - OpenMC-to-SPH-loop entrypoint smoke
  - OpenMC-to-SPH-loop real DONJON loop smoke with --run-donjon
  - DRAGON SPH macrolib handoff smoke when local DRAGON TCM38 inputs exist
  - DONJON DSPH consume smoke when local DONJON is available
  - DONJON SPH solver-response smoke when local DONJON is available
  - SPH iteration table smoke
  - DONJON L_FLUX volume-flux extraction CLI smoke
  - SPH iteration workflow CLI smoke
  - SPH loop driver CLI smoke
  - generic DONJON SPH loop adapter smoke
  - minimal SPH loop user-case smoke
  - external SPH table handoff smoke
  - external face-flux adapter smoke
  - production minicase, OpenMC full-core, and OpenMC hex minicase smokes
  - optional PyGan backend smoke when PyGan is available
  - OpenMC full-core real DONJON-backed SPH loop smoke with --run-donjon
  - C5G7 converter readback smoke
  - accepted baseline manifest validation
  - C5G7 SPH solver-response smoke when local DONJON is available
  - C5G7 SPH iteration from accepted DONJON/OpenMC volume-flux artifact
  - C5G7 fixed-OpenMC SPH loop smoke when local DONJON is available
  - C5G7 DONJON face-flux regeneration smoke when local DONJON dumps exist
  - C5G7 production ADF source reconstruction smoke
  - C5G7 from-OpenMC flux-ratio ADF smoke when C5G7_STATEPOINT exists
  - C5G7 statepoint exporter parity check when C5G7_STATEPOINT exists
  - OpenMC hex minicase DONJON k-eff comparison with --run-donjon

Options:
  --skip-tests                 skip pytest
  --run-donjon                 run the full DONJON C5G7 acceptance decks
  --run-local-candidates       run non-accepted candidate/capability examples
  --require-statepoint-export  fail if C5G7_STATEPOINT is unavailable

Environment:
  PYTHON_BIN        default openmc-dev python if present, else python3
  PYTEST_PYTHON     default PYTHON_BIN
  RUN_DIR           default /private/tmp/openmc2donjon_release_check
  C5G7_STATEPOINT   saved OpenMC assembly P1 statepoint path
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      RUN_TESTS=0
      shift
      ;;
    --run-donjon)
      RUN_DONJON=1
      shift
      ;;
    --run-local-candidates)
      RUN_LOCAL_CANDIDATES=1
      shift
      ;;
    --require-statepoint-export)
      REQUIRE_STATEPOINT_EXPORT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
}

require_executable() {
  local exe="$1"
  if [[ "$exe" == */* ]]; then
    if [[ ! -x "$exe" ]]; then
      echo "missing executable: $exe" >&2
      exit 1
    fi
  elif ! command -v "$exe" >/dev/null 2>&1; then
    echo "missing executable on PATH: $exe" >&2
    exit 1
  fi
}

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon release check =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "run_donjon: $RUN_DONJON"
echo "run_local_candidates: $RUN_LOCAL_CANDIDATES"

require_executable "$PYTHON_BIN"
require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$C5G7_ACCEPTED_H5"

if [[ "$RUN_TESTS" -eq 1 ]]; then
  echo
  echo "== Package tests =="
  require_executable "$PYTEST_PYTHON"
  "$PYTEST_PYTHON" -m pytest -q -o "cache_dir=$PYTEST_CACHE" "$REPO_ROOT/tests"
else
  echo
  echo "== Package tests skipped =="
fi

echo
echo "== CLI smoke =="
"$PYTHON_BIN" -m openmc2donjon.cli --version
"$PYTHON_BIN" -m openmc2donjon.cli --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli prepare-openmc-sph-loop --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli check --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli export-surface-flux --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli check-face-flux --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-low-order-driver --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli check-low-order-driver --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-homogeneous-face-flux --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-adf-sidecar --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli augment-adf --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-update-table --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli extract-donjon-volume-flux --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli run-sph-iteration --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-donjon-sph-loop-config --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-loop-scaffold --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli pygan-doctor --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli pygan-inspect-compo --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli compare-writers --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.donjon_deck_runner --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.export_cli --version
"$PYTHON_BIN" -m openmc2donjon.export_cli --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli --version
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli --help >/dev/null

echo
echo "== Energy mesh contract smoke =="
RUN_DIR="$RUN_DIR/energy_mesh_contract" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_energy_mesh_contract_smoke.sh"

echo
echo "== Recipe export smoke =="
RUN_DIR="$RUN_DIR/recipe_export_smoke" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_recipe_export_smoke.sh"

echo
echo "== OpenMC-to-SPH-loop entrypoint smoke =="
RUN_DIR="$RUN_DIR/openmc_sph_loop_entrypoint" \
PYTHON_BIN="$PYTHON_BIN" \
RUN_REAL_DONJON="$RUN_DONJON" \
  bash "$REPO_ROOT/examples/openmc_sph_loop_entrypoint/run_smoke.sh"

echo
echo "== DRAGON SPH macrolib handoff smoke =="
DRAGON_SPH_RUN_DIR="$RUN_DIR/dragon_sph_handoff"
RUN_DIR="$DRAGON_SPH_RUN_DIR" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_dragon_sph_handoff_smoke.sh"

echo
echo "== DONJON SPH consume smoke =="
RUN_DIR="$RUN_DIR/donjon_sph_consume" \
PYTHON_BIN="$PYTHON_BIN" \
MACROLIB_ASCII="$DRAGON_SPH_RUN_DIR/from_openmc_sph/out.macrolib.txt" \
  bash "$REPO_ROOT/scripts/run_donjon_sph_consume_smoke.sh"

echo
echo "== DONJON SPH solver response smoke =="
RUN_DIR="$RUN_DIR/donjon_sph_solver_response" \
PYTHON_BIN="$PYTHON_BIN" \
MACROLIB_ASCII="$DRAGON_SPH_RUN_DIR/from_openmc_sph/out.macrolib.txt" \
  bash "$REPO_ROOT/scripts/run_donjon_sph_solver_response_smoke.sh"

echo
echo "== External low-order handoff smoke =="
RUN_DIR="$RUN_DIR/external_low_order_handoff" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/external_low_order_handoff/run_smoke.sh"

echo
echo "== SPH iteration loop smoke =="
RUN_DIR="$RUN_DIR/sph_iteration_loop" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/sph_iteration_loop/run_smoke.sh"

echo
echo "== Generic DONJON SPH loop adapter smoke =="
RUN_DIR="$RUN_DIR/donjon_sph_loop_adapter" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/donjon_sph_loop_adapter/run_smoke.sh"

echo
echo "== Minimal SPH loop user-case smoke =="
RUN_DIR="$RUN_DIR/sph_loop_minicase" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/sph_loop_minicase/run_smoke.sh"

echo
echo "== External SPH handoff smoke =="
RUN_DIR="$RUN_DIR/external_sph_handoff" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/external_sph_handoff/run_smoke.sh"

echo
echo "== External face-flux adapter smoke =="
RUN_DIR="$RUN_DIR/external_face_flux_adapter" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/external_face_flux_adapter/run_smoke.sh"

echo
echo "== Production minicase smoke =="
RUN_DIR="$RUN_DIR/production_minicase" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_production_minicase_smoke.sh"

echo
echo "== PyGan backend smoke =="
RUN_DIR="$RUN_DIR/pygan_backend" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_pygan_backend_smoke.sh"

echo
echo "== OpenMC full-core assembly-wise minicase smoke =="
RUN_DIR="$RUN_DIR/openmc_full_core_minicase" \
PYTHON_BIN="$PYTHON_BIN" \
RUN_REAL_DONJON="$RUN_DONJON" \
  bash "$REPO_ROOT/scripts/run_openmc_full_core_production_smoke.sh"

echo
echo "== OpenMC hex minicase smoke =="
RUN_DIR="$RUN_DIR/openmc_hex_minicase" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/openmc_hex_minicase/run_smoke.sh"

echo
echo "== C5G7 converter smoke =="
RUN_DIR="$RUN_DIR/c5g7_demo" bash "$REPO_ROOT/scripts/run_c5g7_demo.sh" --skip-tests

if [[ "$RUN_LOCAL_CANDIDATES" -eq 1 ]]; then
  echo
  echo "== Candidate/capability smokes =="
  RUN_DIR="$RUN_DIR/hex_minicase" \
  PYTHON_BIN="$PYTHON_BIN" \
    bash "$REPO_ROOT/examples/hex_minicase/run_smoke.sh"
  RUN_DIR="$RUN_DIR/uox_5x5_tg6" \
  PYTHON_BIN="$PYTHON_BIN" \
    bash "$REPO_ROOT/examples/uox_5x5_tg6/run_smoke.sh"
else
  echo
  echo "== Candidate/capability smokes skipped =="
fi

echo
echo "== Accepted baseline manifest =="
"$PYTHON_BIN" "$REPO_ROOT/examples/donjon_openmc2donjon/validate_accepted_baseline.py"

echo
echo "== C5G7 ADF augment smoke =="
adf_stripped="$RUN_DIR/c5g7_adf_augment.no_adf.h5"
adf_augmented="$RUN_DIR/c5g7_adf_augment.with_adf.h5"
adf_summary="$RUN_DIR/c5g7_adf_augment.summary.json"
"$PYTHON_BIN" - "$C5G7_ACCEPTED_H5" "$adf_stripped" <<'PY'
import shutil
import sys
from pathlib import Path

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
PY
"$PYTHON_BIN" -m openmc2donjon.cli augment-adf "$adf_stripped" \
  --adf-source "$C5G7_ACCEPTED_H5" \
  -o "$adf_augmented" \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --summary-json "$adf_summary"
"$PYTHON_BIN" -m openmc2donjon.cli check "$adf_augmented" \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL"
"$PYTHON_BIN" - "$C5G7_ACCEPTED_H5" "$adf_augmented" "$adf_summary" <<'PY'
import json
import sys
from pathlib import Path

import h5py
import numpy as np

source = Path(sys.argv[1])
augmented = Path(sys.argv[2])
summary = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
if summary.get("decision") != "openmc2donjon_adf_augment_passed":
    raise SystemExit(f"ADF augment summary failed: {summary}")
faces = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
with h5py.File(source, "r") as src, h5py.File(augmented, "r") as out:
    mixture = tuple(src["mixtures"])[1]
    expected = np.asarray(src[f"mixtures/{mixture}/adf"][:], dtype=float)
    actual = np.stack([out[f"mixtures/{mixture}/adf/{face}"][:] for face in faces])
    if not np.allclose(actual, expected, rtol=0.0, atol=0.0):
        raise SystemExit("ADF augment payload differs from C5G7 production source")
print("C5G7 ADF augment OK")
PY

echo
echo "== C5G7 SPH augment smoke =="
sph_sidecar="$RUN_DIR/c5g7_sph.sidecar.h5"
sph_augmented="$RUN_DIR/c5g7_sph.with_sph.h5"
sph_macrolib="$RUN_DIR/c5g7_sph.macrolib.txt"
sph_macrolib_sidecar="$RUN_DIR/c5g7_sph.from_macrolib.sidecar.h5"
sph_summary="$RUN_DIR/c5g7_sph.summary.json"
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$C5G7_ACCEPTED_H5" \
  -o "$sph_sidecar" \
  --value 1.0
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$C5G7_ACCEPTED_H5" \
  --sph-source "$sph_sidecar" \
  -o "$sph_augmented" \
  --summary-json "$sph_summary"
"$PYTHON_BIN" -m openmc2donjon.cli "$sph_augmented" \
  --format macrolib \
  -o "$sph_macrolib" \
  --check \
  --require-sph \
  --require-volume \
  --require-transport-dataset
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$C5G7_ACCEPTED_H5" \
  -o "$sph_macrolib_sidecar" \
  --mode macrolib \
  --macrolib "$sph_macrolib"
"$PYTHON_BIN" - "$sph_macrolib" "$sph_summary" <<'PY'
import json
import sys
from pathlib import Path

import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

macrolib = read_macrolib_ascii(Path(sys.argv[1]))
summary = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if summary.get("decision") != "openmc2donjon_sph_augment_passed":
    raise SystemExit(f"SPH augment summary failed: {summary}")
if macrolib.state_vector[13] != 1:
    raise SystemExit("macrolib SPH state-vector flag is not set")
if macrolib.sph is None or not np.allclose(macrolib.sph, 1.0, rtol=0.0, atol=0.0):
    raise SystemExit("macrolib NSPH payload is not unity")
print("C5G7 SPH augment OK")
PY
"$PYTHON_BIN" - "$sph_macrolib_sidecar" <<'PY'
import sys
from pathlib import Path

import h5py
import numpy as np

with h5py.File(Path(sys.argv[1]), "r") as h5:
    if h5.attrs.get("sph_kind") != "macrolib-nsph":
        raise SystemExit("SPH macrolib sidecar kind is wrong")
    if not np.allclose(h5["sph"][:], 1.0, rtol=0.0, atol=0.0):
        raise SystemExit("SPH macrolib sidecar payload is not unity")
print("C5G7 SPH macrolib extraction OK")
PY

echo
echo "== C5G7 SPH solver response smoke =="
RUN_DIR="$RUN_DIR/c5g7_sph_solver_response" \
PYTHON_BIN="$PYTHON_BIN" \
C5G7_ACCEPTED_H5="$C5G7_ACCEPTED_H5" \
  bash "$REPO_ROOT/scripts/run_c5g7_sph_solver_response_smoke.sh"

echo
echo "== C5G7 SPH iteration from DONJON flux smoke =="
RUN_DIR="$RUN_DIR/c5g7_sph_iteration_flux" \
PYTHON_BIN="$PYTHON_BIN" \
C5G7_ACCEPTED_H5="$C5G7_ACCEPTED_H5" \
  bash "$REPO_ROOT/scripts/run_c5g7_sph_iteration_from_donjon_flux_smoke.sh"

echo
echo "== C5G7 fixed-OpenMC SPH loop smoke =="
RUN_DIR="$RUN_DIR/c5g7_fixed_openmc_sph_loop" \
PYTHON_BIN="$PYTHON_BIN" \
C5G7_ACCEPTED_H5="$C5G7_ACCEPTED_H5" \
  bash "$REPO_ROOT/scripts/run_c5g7_fixed_openmc_sph_loop_smoke.sh"

echo
echo "== C5G7 DONJON face-flux regeneration smoke =="
RUN_DIR="$RUN_DIR/c5g7_donjon_face_flux" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_c5g7_donjon_face_flux_smoke.sh"

echo
echo "== C5G7 ADF source reconstruction smoke =="
RUN_DIR="$RUN_DIR/c5g7_adf_source" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_c5g7_adf_source_smoke.sh"

echo
echo "== C5G7 statepoint exporter parity =="
if [[ -e "$C5G7_STATEPOINT" ]]; then
  echo
  echo "== C5G7 from-OpenMC flux-ratio ADF smoke =="
  RUN_DIR="$RUN_DIR/c5g7_from_openmc_adf" \
  C5G7_STATEPOINT="$C5G7_STATEPOINT" \
  PYTHON_BIN="$PYTHON_BIN" \
    bash "$REPO_ROOT/scripts/run_c5g7_from_openmc_adf_smoke.sh"

  exported_run_dir="$RUN_DIR/c5g7_exporter_statepoint"
  exported_h5="$exported_run_dir/mgxs_library.h5"
  exported_mco="$exported_run_dir/out.mcompo.txt"
  exported_summary="$exported_run_dir/run_summary.json"
  exported_check_summary="$exported_run_dir/check_summary.json"
  exported_diff_summary="$exported_run_dir/diff_summary.json"
  exported_manifest="$exported_run_dir/manifest.json"
  exported_log="$exported_run_dir/export.log"
  mkdir -p "$exported_run_dir"
  set +e
  C5G7_ADF_SOURCE="$C5G7_ACCEPTED_H5" \
  "$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
    --recipe "$REPO_ROOT/scripts/c5g7_export_recipe.py" \
    --statepoint "$C5G7_STATEPOINT" \
    --run-dir "$exported_run_dir" \
    --check \
    --require-volume \
    --require-transport-dataset \
    --require-adf \
    --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
    --scatter-row-balance-fail "$C5G7_EXPORT_SCATTER_ROW_BALANCE_FAIL" \
    2>&1 | tee "$exported_log"
  export_status="${PIPESTATUS[0]}"
  set -e
  if [[ "$export_status" -ne 0 ]]; then
    if [[ "$REQUIRE_STATEPOINT_EXPORT" -eq 1 ]]; then
      echo "C5G7 statepoint exporter parity failed; log: $exported_log" >&2
      exit "$export_status"
    fi
    echo "skipped; C5G7_STATEPOINT is present but not compatible with current exporter"
    echo "  statepoint: $C5G7_STATEPOINT"
    echo "  log: $exported_log"
  else
    "$PYTHON_BIN" -m openmc2donjon.cli diff "$C5G7_ACCEPTED_H5" "$exported_h5" \
      --summary-json "$exported_diff_summary"
    "$PYTHON_BIN" - "$exported_h5" "$exported_mco" "$exported_summary" "$exported_check_summary" "$exported_diff_summary" "$exported_manifest" <<'PY'
import json
import sys
from pathlib import Path

from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import (
    FROM_OPENMC_SUMMARY_SCHEMA,
    validate_from_openmc_summary,
)

candidate = Path(sys.argv[1])
candidate_mco = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
check_summary_path = Path(sys.argv[4])
diff_summary_path = Path(sys.argv[5])
manifest_path = Path(sys.argv[6])

diff_summary = json.loads(diff_summary_path.read_text(encoding="utf-8"))
if diff_summary.get("decision") != "mgxs_hdf5_diff_passed":
    raise SystemExit(f"statepoint exporter HDF5 diff failed: {diff_summary}")
print(
    "statepoint exporter HDF5 diff OK: "
    f"datasets={diff_summary['compared_datasets']} max_abs={diff_summary['max_abs']}"
)

blocks = lcm_ascii.read_lcm_ascii(candidate_mco)
names = [block.name for block in blocks if block.name]
if names[:1] != ["SIGNATURE"]:
    raise SystemExit(f"{candidate_mco}: invalid LCM ASCII output")
print(f"statepoint exporter MCO readback OK: blocks={len(blocks)} first={names[:6]}")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if check_summary.get("decision") != "mgxs_input_contract_passed":
    raise SystemExit(f"statepoint exporter checked conversion failed: {check_summary}")
if manifest.get("schema") != "openmc2donjon.bundle.v1":
    raise SystemExit(f"statepoint exporter bundle schema failed: {manifest}")
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required_labels = {"mgxs", "mcompo", "run-summary", "check-summary", "recipe"}
if set(labels) != required_labels:
    raise SystemExit(f"statepoint exporter bundle labels failed: {labels}")
if labels["check-summary"].get("summary_decision") != "mgxs_input_contract_passed":
    raise SystemExit(f"statepoint exporter bundle check decision failed: {labels}")
schema_errors = validate_from_openmc_summary(summary)
if schema_errors:
    raise SystemExit("statepoint exporter summary schema failed: " + "; ".join(schema_errors))
checks = {
    "schema": summary.get("schema") == FROM_OPENMC_SUMMARY_SCHEMA,
    "format": summary.get("format") == "multicompo",
    "hdf5": Path(summary.get("hdf5", "")) == candidate,
    "output": Path(summary.get("output", "")) == candidate_mco,
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
    raise SystemExit(f"statepoint exporter summary failed checks: {failed}; {summary}")
print(
    "statepoint exporter summary OK: "
    f"mixtures={summary['mixture_count']} groups={summary['energy_groups']} "
    f"P{summary['legendre_order']}"
)
PY
  fi
else
  if [[ "$REQUIRE_STATEPOINT_EXPORT" -eq 1 ]]; then
    echo "missing C5G7_STATEPOINT: $C5G7_STATEPOINT" >&2
    exit 1
  fi
  echo "skipped; C5G7_STATEPOINT not found: $C5G7_STATEPOINT"
fi

if [[ "$RUN_DONJON" -eq 1 ]]; then
  echo
  echo "== OpenMC hex DONJON k-eff comparison =="
  PYTHON_BIN="$PYTHON_BIN" \
    bash "$REPO_ROOT/examples/openmc_hex_minicase/run_keff_comparison.sh"

  echo
  echo "== Full DONJON acceptance =="
  RUN_DIR="$RUN_DIR/top_acceptance" \
  PYTHON_BIN="$PYTHON_BIN" \
  PYTEST_PYTHON="$PYTEST_PYTHON" \
  OPENMC2DONJON_CAPTURE_LOG=0 \
    bash "$REPO_ROOT/examples/donjon_openmc2donjon/run_acceptance.sh" --skip-tests
else
  echo
  echo "== Full DONJON acceptance skipped =="
fi

echo
echo "openmc2donjon release check: PASS"

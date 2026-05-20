#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_release_check}"
PYTEST_CACHE="${PYTEST_CACHE:-/private/tmp/openmc2donjon_pytest_cache}"
C5G7_STATEPOINT="${C5G7_STATEPOINT:-/Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5}"
C5G7_ACCEPTED_H5="$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5"

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
REQUIRE_STATEPOINT_EXPORT=0

usage() {
  cat <<'EOF'
usage: scripts/release_check.sh [--skip-tests] [--run-donjon] [--require-statepoint-export]

Run the release/handoff checks for the accepted C5G7 assembly-wise baseline.

Default:
  - package tests
  - CLI help/version smoke
  - recipe/statepoint exporter smoke
  - C5G7 converter readback smoke
  - accepted baseline manifest validation
  - C5G7 statepoint exporter parity check when C5G7_STATEPOINT exists

Options:
  --skip-tests                 skip pytest
  --run-donjon                 run the full DONJON C5G7 acceptance decks
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
"$PYTHON_BIN" -m openmc2donjon.cli check --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli export-surface-flux --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-low-order-driver --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli check-low-order-driver --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-homogeneous-face-flux --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-adf-sidecar --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli augment-adf --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.export_cli --version
"$PYTHON_BIN" -m openmc2donjon.export_cli --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli --version
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli --help >/dev/null

echo
echo "== Recipe export smoke =="
RUN_DIR="$RUN_DIR/recipe_export_smoke" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_recipe_export_smoke.sh"

echo
echo "== Production minicase smoke =="
RUN_DIR="$RUN_DIR/production_minicase" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_production_minicase_smoke.sh"

echo
echo "== C5G7 converter smoke =="
RUN_DIR="$RUN_DIR/c5g7_demo" bash "$REPO_ROOT/scripts/run_c5g7_demo.sh" --skip-tests

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
  --require-transport-dataset
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
echo "== C5G7 statepoint exporter parity =="
if [[ -e "$C5G7_STATEPOINT" ]]; then
  exported_run_dir="$RUN_DIR/c5g7_exporter_statepoint"
  exported_h5="$exported_run_dir/mgxs_library.h5"
  exported_mco="$exported_run_dir/out.mcompo.txt"
  exported_summary="$exported_run_dir/run_summary.json"
  exported_check_summary="$exported_run_dir/check_summary.json"
  exported_diff_summary="$exported_run_dir/diff_summary.json"
  exported_manifest="$exported_run_dir/manifest.json"
  C5G7_ADF_SOURCE="$C5G7_ACCEPTED_H5" \
  "$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
    --recipe "$REPO_ROOT/scripts/c5g7_export_recipe.py" \
    --statepoint "$C5G7_STATEPOINT" \
    --run-dir "$exported_run_dir" \
    --check \
    --require-volume \
    --require-transport-dataset \
    --require-adf \
    --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX
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
else
  if [[ "$REQUIRE_STATEPOINT_EXPORT" -eq 1 ]]; then
    echo "missing C5G7_STATEPOINT: $C5G7_STATEPOINT" >&2
    exit 1
  fi
  echo "skipped; C5G7_STATEPOINT not found: $C5G7_STATEPOINT"
fi

if [[ "$RUN_DONJON" -eq 1 ]]; then
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

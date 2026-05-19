#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_recipe_export_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

RECIPE="$REPO_ROOT/examples/recipe_export_smoke/minimal_recipe.py"
STATEPOINT="$RUN_DIR/statepoint.fake.h5"
MGXS="$RUN_DIR/minimal_recipe_mgxs.h5"
MCO="$RUN_DIR/minimal_recipe.mcompo.txt"
MAC="$RUN_DIR/minimal_recipe.macrolib.txt"
INSPECT_SUMMARY="$RUN_DIR/minimal_recipe_inspect_summary.json"
ONE_STEP_H5="$RUN_DIR/one_step_mgxs.h5"
ONE_STEP_MCO="$RUN_DIR/one_step.mcompo.txt"
ONE_STEP_SUMMARY="$RUN_DIR/one_step_summary.json"
ONE_STEP_CHECK_SUMMARY="$RUN_DIR/one_step_check_summary.json"
ONE_STEP_DRY_H5="$RUN_DIR/one_step_dry_run_$$.h5"
ONE_STEP_DRY_MCO="$RUN_DIR/one_step_dry_run_$$.mcompo.txt"
ONE_STEP_DRY_SUMMARY="$RUN_DIR/one_step_dry_run_$$.summary.json"
ONE_STEP_DRY_CHECK_SUMMARY="$RUN_DIR/one_step_dry_run_$$.check_summary.json"

echo "== openmc2donjon recipe export smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

printf 'recipe smoke statepoint marker\n' > "$STATEPOINT"

echo
echo "== Recipe dry-run =="
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$RECIPE" \
  --no-load-statepoint \
  --dry-run

echo
echo "== Recipe export =="
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$RECIPE" \
  --statepoint "$STATEPOINT" \
  -o "$MGXS"

echo
echo "== HDF5 inspect =="
"$PYTHON_BIN" -m openmc2donjon.cli inspect "$MGXS" \
  --limit 5 \
  --summary-json "$INSPECT_SUMMARY"
"$PYTHON_BIN" - "$INSPECT_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload["schema"] != "openmc2donjon.mgxs-inspect.v1":
    raise SystemExit("unexpected inspect summary schema")
summary = payload["inputs"][0]
if summary["mixture_count"] != 2 or summary["calculation_count"] != 2:
    raise SystemExit(f"unexpected inspect summary counts: {summary}")
PY

echo
echo "== HDF5 preflight =="
"$PYTHON_BIN" -m openmc2donjon.cli check \
  "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --format multicompo \
  --output "$MCO" \
  --check

echo
echo "== Converter readback =="
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" -o "$MCO" \
  --check \
  --require-volume \
  --require-transport-dataset
"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$MGXS" -o "$MAC" \
  --check \
  --require-volume \
  --require-transport-dataset

echo
echo "== One-step dry-run =="
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --dry-run \
  --keep-hdf5 "$ONE_STEP_DRY_H5" \
  -o "$ONE_STEP_DRY_MCO" \
  --summary-json "$ONE_STEP_DRY_SUMMARY" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --check-summary-json "$ONE_STEP_DRY_CHECK_SUMMARY"
for path in "$ONE_STEP_DRY_H5" "$ONE_STEP_DRY_MCO" "$ONE_STEP_DRY_SUMMARY" "$ONE_STEP_DRY_CHECK_SUMMARY"; do
  if [[ -e "$path" ]]; then
    echo "dry-run unexpectedly wrote $path" >&2
    exit 1
  fi
done

echo
echo "== One-step from OpenMC recipe =="
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --statepoint "$STATEPOINT" \
  --keep-hdf5 "$ONE_STEP_H5" \
  -o "$ONE_STEP_MCO" \
  --summary-json "$ONE_STEP_SUMMARY" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --check-summary-json "$ONE_STEP_CHECK_SUMMARY"

"$PYTHON_BIN" - "$MGXS" "$MCO" "$MAC" "$STATEPOINT" "$ONE_STEP_H5" "$ONE_STEP_MCO" "$ONE_STEP_SUMMARY" "$ONE_STEP_CHECK_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary

mgxs = Path(sys.argv[1])
mco = Path(sys.argv[2])
mac = Path(sys.argv[3])
statepoint = str(Path(sys.argv[4]))
one_step_h5 = Path(sys.argv[5])
one_step_mco = Path(sys.argv[6])
summary = Path(sys.argv[7])
check_summary = Path(sys.argv[8])

for path in (mgxs, one_step_h5):
    with h5py.File(path, "r") as h5:
        names = sorted(h5["mixtures"])
        if names != ["FUEL_A", "MOD_A"]:
            raise SystemExit(f"unexpected mixtures: {names}")
        if h5.attrs["domain_mode"] != "recipe_smoke":
            raise SystemExit("missing recipe_smoke domain_mode")
        if h5.attrs["statepoint_marker"] != statepoint:
            raise SystemExit("recipe did not receive the statepoint path")

for path in (mco, mac, one_step_mco):
    blocks = lcm_ascii.read_lcm_ascii(path)
    names = [block.name for block in blocks if block.name]
    if names[:1] != ["SIGNATURE"]:
        raise SystemExit(f"{path}: invalid LCM ASCII output")
    print(f"readback {path.name}: blocks={len(blocks)} first={names[:6]}")

payload = json.loads(summary.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(payload)
if summary_errors:
    raise SystemExit("invalid summary schema: " + "; ".join(summary_errors))
check_payload = json.loads(check_summary.read_text(encoding="utf-8"))
if check_payload["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("one-step checked conversion preflight did not pass")
if payload["checked"] is not True or payload["check_passed"] is not True:
    raise SystemExit("one-step summary did not record checked preflight success")
if payload["check_summary_json"] != str(check_summary):
    raise SystemExit("one-step summary check_summary_json path mismatch")
if payload["mixture_names"] != ["FUEL_A", "MOD_A"]:
    raise SystemExit("unexpected summary mixture names")
if payload["hdf5"] != str(one_step_h5) or payload["output"] != str(one_step_mco):
    raise SystemExit("summary paths do not match one-step outputs")
print(f"summary {summary.name}: schema={payload['schema']} mixtures={payload['mixture_count']}")
PY

echo
echo "openmc2donjon recipe export smoke: PASS"

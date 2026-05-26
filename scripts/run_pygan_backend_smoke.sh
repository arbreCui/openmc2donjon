#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_pygan_backend_smoke}"
INPUT_H5="${INPUT_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon PyGan backend smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "input_h5: $INPUT_H5"

if [[ ! -f "$INPUT_H5" ]]; then
  echo "PyGan backend smoke skipped: input HDF5 unavailable: $INPUT_H5"
  exit 0
fi

doctor_json="$RUN_DIR/pygan_doctor.json"
echo
echo "== PyGan doctor =="
set +e
"$PYTHON_BIN" -m openmc2donjon.cli pygan-doctor --summary-json "$doctor_json"
doctor_status=$?
set -e
if [[ "$doctor_status" -ne 0 ]]; then
  echo "PyGan backend smoke skipped: PyGan backend unavailable"
  echo "doctor_summary: $doctor_json"
  exit 0
fi

multicompo_dir="$RUN_DIR/multicompo_compare"
macrolib_dir="$RUN_DIR/macrolib_compare"
multicompo_json="$RUN_DIR/multicompo_writer_compare.json"
macrolib_json="$RUN_DIR/macrolib_writer_compare.json"
inspection_json="$RUN_DIR/pygan_multicompo_inspect.json"

echo
echo "== Compare writer backends: L_MULTICOMPO =="
"$PYTHON_BIN" -m openmc2donjon.cli compare-writers "$INPUT_H5" \
  --format multicompo \
  --summary-json "$multicompo_json" \
  --keep-dir "$multicompo_dir"

echo
echo "== Compare writer backends: L_MACROLIB =="
"$PYTHON_BIN" -m openmc2donjon.cli compare-writers "$INPUT_H5" \
  --format macrolib \
  --summary-json "$macrolib_json" \
  --keep-dir "$macrolib_dir"

echo
echo "== Inspect PyGan MULTICOMPO output =="
"$PYTHON_BIN" -m openmc2donjon.cli pygan-inspect-compo \
  "$multicompo_dir/pygan.mcompo.txt" \
  --summary-json "$inspection_json"

"$PYTHON_BIN" - "$multicompo_json" "$macrolib_json" "$inspection_json" <<'PY'
import json
import sys
from pathlib import Path

comparison_paths = [Path(sys.argv[1]), Path(sys.argv[2])]
inspection_path = Path(sys.argv[3])

for path in comparison_paths:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "openmc2donjon.writer-comparison.v1":
        raise SystemExit(f"{path}: unexpected schema {payload.get('schema')!r}")
    if payload.get("ok") is not True:
        raise SystemExit(f"{path}: writer comparison did not pass: {payload}")
    if payload.get("issue_count") != 0:
        raise SystemExit(f"{path}: writer comparison reported issues: {payload['issues']}")
    if int(payload.get("compared_payloads", 0)) <= 0:
        raise SystemExit(f"{path}: no payloads were compared")

inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
if inspection.get("schema") != "openmc2donjon.pygan-compo-inspect.v1":
    raise SystemExit(f"{inspection_path}: unexpected schema {inspection.get('schema')!r}")
if inspection.get("signature") != "L_MULTICOMPO":
    raise SystemExit(f"{inspection_path}: expected L_MULTICOMPO signature, got {inspection.get('signature')!r}")
if int(inspection.get("mixture_count") or 0) <= 0:
    raise SystemExit(f"{inspection_path}: no mixtures found in PyGan output")

print("PyGan writer comparison summaries OK")
PY

echo
echo "openmc2donjon PyGan backend smoke: PASS"
echo "artifacts: $RUN_DIR"

#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_pygan_backend_smoke}"
INPUT_H5="${INPUT_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
DONJON_RUNNER="${DONJON_RUNNER:-$DONJON_ROOT/rdonjon}"
DONJON_RESULT_DIR="${DONJON_RESULT_DIR:-$DONJON_ROOT/Darwin_arm64}"

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
echo "donjon: $DONJON_RUNNER"

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

if [[ -x "$DONJON_RUNNER" ]]; then
  echo
  echo "== DONJON ingest of PyGan ASCII outputs =="
  short_tag="o2d_pg_$$"
  case_id="${RUN_TAG:-pygan_donjon_ingest_$short_tag}"
  data_case_dir="$DONJON_ROOT/data/openmc2donjon/case_runs/pygan_donjon_ingest_smoke"
  deck_rel="openmc2donjon/case_runs/pygan_donjon_ingest_smoke/${case_id}.x2m"
  deck_path="$DONJON_ROOT/data/$deck_rel"
  result_path="$DONJON_RESULT_DIR/${case_id}.result"
  short_mcompo="/tmp/${short_tag}.mco"
  short_macrolib="/tmp/${short_tag}.mac"

  mkdir -p "$data_case_dir"
  cp "$multicompo_dir/pygan.mcompo.txt" "$short_mcompo"
  cp "$macrolib_dir/pygan.macrolib.txt" "$short_macrolib"

  "$PYTHON_BIN" - "$deck_path" "$short_mcompo" "$short_macrolib" <<'PY'
from pathlib import Path
import sys

deck = Path(sys.argv[1])
mcompo = Path(sys.argv[2])
macrolib = Path(sys.argv[3])
deck.write_text(
    f"""* Read PyGan-exported ASCII LCM payloads in DONJON.
MODULE END: ABORT: ;
LINKED_LIST CPO MACRO ;
SEQ_ASCII CPO_ASC :: FILE '{mcompo}' ;
SEQ_ASCII MACRO_ASC :: FILE '{macrolib}' ;
CPO := CPO_ASC ;
MACRO := MACRO_ASC ;
ECHO 'OPENMC2DONJON PYGAN DONJON INGEST OK' ;
END: ;
""",
    encoding="utf-8",
)
PY

  (
    cd "$DONJON_ROOT"
    "$DONJON_RUNNER" -q "$deck_rel"
  )

  "$PYTHON_BIN" - "$result_path" <<'PY'
from pathlib import Path
import sys

result = Path(sys.argv[1])
if not result.exists():
    raise SystemExit(f"DONJON ingest listing is missing: {result}")
text = result.read_text(encoding="utf-8", errors="replace")
if "normal end of execution" not in text:
    raise SystemExit(f"DONJON ingest did not end normally: {result}")
if "OPENMC2DONJON PYGAN DONJON INGEST OK" not in text:
    raise SystemExit(f"DONJON ingest marker is missing: {result}")
print(f"DONJON read PyGan MULTICOMPO and MACROLIB ASCII outputs: {result}")
PY
else
  echo
  echo "DONJON runner unavailable; skipping PyGan -> DONJON ingest smoke"
fi

echo
echo "openmc2donjon PyGan backend smoke: PASS"
echo "artifacts: $RUN_DIR"

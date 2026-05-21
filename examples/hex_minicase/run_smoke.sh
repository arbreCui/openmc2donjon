#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_hex_minicase}"
SCATTER_ROW_BALANCE_WARN="${OPENMC2DONJON_SCATTER_ROW_BALANCE_WARN:-5e-2}"
SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_SCATTER_ROW_BALANCE_FAIL:-}"
SCATTER_ROW_BALANCE_ARGS=(--scatter-row-balance-warn "$SCATTER_ROW_BALANCE_WARN")
if [[ -n "$SCATTER_ROW_BALANCE_FAIL" ]]; then
  SCATTER_ROW_BALANCE_ARGS+=(--scatter-row-balance-fail "$SCATTER_ROW_BALANCE_FAIL")
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

MGXS_H5="$RUN_DIR/hex_minicase.h5"
SUMMARY_JSON="$RUN_DIR/hex_minicase_summary.json"
CHECK_JSON="$RUN_DIR/hex_minicase_check.json"
MCOMPO_TXT="$RUN_DIR/out.mcompo.txt"
MACROLIB_TXT="$RUN_DIR/out.macrolib.txt"
ADF_FACES="FD_E,FD_NE,FD_NW,FD_W,FD_SW,FD_SE"

echo "== openmc2donjon hex minicase smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

mkdir -p "$RUN_DIR"

echo
echo "== Build hex MGXS handoff =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" "$REPO_ROOT/examples/hex_minicase/make_hex_mgxs.py" \
  -o "$MGXS_H5" \
  --summary-json "$SUMMARY_JSON" \
  --force

echo
echo "== Preflight =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS_H5" \
  --summary-json "$CHECK_JSON" \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces "$ADF_FACES" \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== Convert =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" -m openmc2donjon.cli "$MGXS_H5" \
  -o "$MCOMPO_TXT" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces "$ADF_FACES" \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" -m openmc2donjon.cli "$MGXS_H5" \
  --format macrolib \
  -o "$MACROLIB_TXT" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces "$ADF_FACES" \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== Readback =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" - "$SUMMARY_JSON" "$CHECK_JSON" "$MCOMPO_TXT" "$MACROLIB_TXT" <<'PY'
import json
from pathlib import Path
import sys

from openmc2donjon import lcm_ascii
from openmc2donjon.macrolib import read_macrolib_ascii

summary_path = Path(sys.argv[1])
check_path = Path(sys.argv[2])
mcompo_path = Path(sys.argv[3])
macrolib_path = Path(sys.argv[4])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
check = json.loads(check_path.read_text(encoding="utf-8"))
if summary["mixture_count"] != 7:
    raise SystemExit("expected seven hex-domain mixtures")
if summary["energy_groups"] != 3:
    raise SystemExit("expected three energy groups")
if summary["legendre_order"] != 1:
    raise SystemExit("expected P1 scattering")
expected_faces = ["FD_E", "FD_NE", "FD_NW", "FD_W", "FD_SW", "FD_SE"]
if summary["adf_faces"] != expected_faces:
    raise SystemExit(f"unexpected summary ADF faces: {summary['adf_faces']}")
if check["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("hex minicase preflight did not pass")
report = check["inputs"][0]
if report["adf_faces"] != expected_faces:
    raise SystemExit(f"unexpected preflight ADF faces: {report['adf_faces']}")

mcompo_blocks = lcm_ascii.read_lcm_ascii(mcompo_path)
macrolib = read_macrolib_ascii(macrolib_path)
if macrolib.ngroups != 3 or macrolib.nmixtures != 7:
    raise SystemExit("unexpected MACROLIB dimensions")
if tuple(macrolib.adf) != tuple(expected_faces):
    raise SystemExit(f"unexpected MACROLIB ADF faces: {tuple(macrolib.adf)}")
print(
    "hex minicase readback OK: "
    f"mixtures={summary['mixture_count']} groups={summary['energy_groups']} "
    f"P{summary['legendre_order']} mcompo_blocks={len(mcompo_blocks)} "
    f"macrolib_adf_faces={','.join(macrolib.adf)}"
)
PY

echo
echo "openmc2donjon hex minicase smoke: PASS"

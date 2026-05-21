#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
DRAGON_ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
SOURCE_H5="${SOURCE_H5:-$DRAGON_ROOT/Dragon/data/UOX_5x5_TG6_sym8_multiDom_proc/UOX_5x5_TG6_sym8_multiDom.h5}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_uox_5x5_tg6}"
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

MGXS_H5="$RUN_DIR/uox_5x5_tg6_subdomain.h5"
SUMMARY_JSON="$RUN_DIR/uox_5x5_tg6_summary.json"
CHECK_JSON="$RUN_DIR/uox_5x5_tg6_check.json"
MCOMPO_TXT="$RUN_DIR/out.mcompo.txt"
MACROLIB_TXT="$RUN_DIR/out.macrolib.txt"

echo "== openmc2donjon UOX 5x5 TG6 candidate smoke =="
echo "repo: $REPO_ROOT"
echo "source: $SOURCE_H5"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

mkdir -p "$RUN_DIR"

echo
echo "== Adapt APEX HDF5 to openmc2donjon contract =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" "$REPO_ROOT/examples/uox_5x5_tg6/apex_to_mgxs.py" \
  --input "$SOURCE_H5" \
  -o "$MGXS_H5" \
  --domain-mode subdomain \
  --summary-json "$SUMMARY_JSON" \
  --force

echo
echo "== Preflight =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS_H5" \
  --summary-json "$CHECK_JSON" \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== Convert =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" -m openmc2donjon.cli "$MGXS_H5" \
  -o "$MCOMPO_TXT" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" -m openmc2donjon.cli "$MGXS_H5" \
  --format macrolib \
  -o "$MACROLIB_TXT" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== Readback =="
PYTHONPATH="$PACKAGE_SRC" "$PYTHON_BIN" - "$SUMMARY_JSON" "$MCOMPO_TXT" "$MACROLIB_TXT" <<'PY'
import json
from pathlib import Path
import sys

from openmc2donjon.lcm_ascii import read_lcm_ascii

summary_path = Path(sys.argv[1])
mcompo_path = Path(sys.argv[2])
macrolib_path = Path(sys.argv[3])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
mcompo_blocks = read_lcm_ascii(mcompo_path)
macrolib_blocks = read_lcm_ascii(macrolib_path)
if summary["mixture_count"] != 6:
    raise SystemExit("expected six subdomain mixtures")
if summary["energy_groups"] != 8:
    raise SystemExit("expected eight energy groups")
if summary["legendre_order"] != 1:
    raise SystemExit("expected P1 scattering")
print(
    "UOX 5x5 TG6 candidate readback OK: "
    f"mixtures={summary['mixture_count']} groups={summary['energy_groups']} "
    f"P{summary['legendre_order']} mcompo_blocks={len(mcompo_blocks)} "
    f"macrolib_blocks={len(macrolib_blocks)}"
)
PY

echo
echo "openmc2donjon UOX 5x5 TG6 candidate smoke: PASS"

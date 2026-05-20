#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_production_minicase_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"
OPENMC_EXEC="${OPENMC_EXEC:-}"
OPENMC_THREADS="${OPENMC_THREADS:-2}"
MINICASE_PARTICLES="${MINICASE_PARTICLES:-200}"
MINICASE_BATCHES="${MINICASE_BATCHES:-12}"
MINICASE_INACTIVE="${MINICASE_INACTIVE:-4}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

if [[ -z "$OPENMC_EXEC" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/openmc ]]; then
    OPENMC_EXEC=/Users/wen/miniforge3/envs/openmc-dev/bin/openmc
  elif command -v openmc >/dev/null 2>&1; then
    OPENMC_EXEC="$(command -v openmc)"
  fi
fi

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

EXAMPLE_DIR="$REPO_ROOT/examples/production_minicase"
CASE_DIR="$RUN_DIR/openmc_case"
CONVERT_RUN_DIR="$RUN_DIR/openmc2donjon_run"
STATEPOINT="$CASE_DIR/statepoint.${MINICASE_BATCHES}.h5"
MGXS="$CONVERT_RUN_DIR/mgxs_library.h5"
MCO="$CONVERT_RUN_DIR/out.mcompo.txt"
SUMMARY="$CONVERT_RUN_DIR/run_summary.json"
CHECK_SUMMARY="$CONVERT_RUN_DIR/check_summary.json"
MANIFEST="$CONVERT_RUN_DIR/manifest.json"

echo "== openmc2donjon production minicase smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "openmc: ${OPENMC_EXEC:-not found}"

if [[ -z "$OPENMC_EXEC" ]]; then
  echo "production minicase skipped: OpenMC executable not found"
  exit 0
fi

if ! "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import sys

try:
    import openmc
except Exception as exc:
    print(f"OpenMC Python import failed: {exc}", file=sys.stderr)
    raise SystemExit(1)

cross_sections = openmc.config.get("cross_sections")
if not cross_sections or not Path(cross_sections).exists():
    print(f"OpenMC cross_sections not available: {cross_sections}", file=sys.stderr)
    raise SystemExit(1)
print(f"OpenMC cross_sections: {cross_sections}")
PY
then
  echo "production minicase skipped: OpenMC Python runtime is not configured"
  exit 0
fi

echo
echo "== Build OpenMC XML =="
"$PYTHON_BIN" "$EXAMPLE_DIR/build_model.py" \
  --case-dir "$CASE_DIR" \
  --particles "$MINICASE_PARTICLES" \
  --batches "$MINICASE_BATCHES" \
  --inactive "$MINICASE_INACTIVE"

echo
echo "== Run OpenMC =="
(
  cd "$CASE_DIR"
  "$OPENMC_EXEC" -s "$OPENMC_THREADS"
)
if [[ ! -e "$STATEPOINT" ]]; then
  echo "missing statepoint: $STATEPOINT" >&2
  exit 1
fi

echo
echo "== Export and convert =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$CONVERT_RUN_DIR" \
  --check \
  --require-volume \
  --require-transport-dataset

"$PYTHON_BIN" - "$MGXS" "$MCO" "$SUMMARY" "$CHECK_SUMMARY" "$MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary

mgxs = Path(sys.argv[1])
mco = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
check_summary_path = Path(sys.argv[4])
manifest_path = Path(sys.argv[5])

with h5py.File(mgxs, "r") as h5:
    if h5.attrs["case"] != "production_minicase":
        raise SystemExit("missing production_minicase root attr")
    if h5.attrs["domain_mode"] != "assembly":
        raise SystemExit("unexpected domain_mode")
    if int(h5.attrs["energy_groups"]) != 2:
        raise SystemExit("unexpected group count")
    if int(h5.attrs["legendre_order"]) != 1:
        raise SystemExit("unexpected Legendre order")
    names = sorted(h5["mixtures"])
    if names != ["ASM_FUEL_LEFT", "ASM_MOD_RIGHT"]:
        raise SystemExit(f"unexpected mixture names: {names}")
    for name in names:
        if "transport_total" not in h5[f"mixtures/{name}"]:
            raise SystemExit(f"{name}: missing transport_total")
        volume = float(h5[f"mixtures/{name}"].attrs["volume"])
        if volume <= 0.0:
            raise SystemExit(f"{name}: non-positive volume")

blocks = lcm_ascii.read_lcm_ascii(mco)
block_names = [block.name for block in blocks if block.name]
if block_names[:1] != ["SIGNATURE"] or "MIXTURES" not in block_names:
    raise SystemExit("invalid MULTICOMPO output")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(summary)
if summary_errors:
    raise SystemExit("invalid from-OpenMC summary: " + "; ".join(summary_errors))
if summary["mixture_names"] != ["ASM_FUEL_LEFT", "ASM_MOD_RIGHT"]:
    raise SystemExit("summary mixture names mismatch")
if summary["energy_groups"] != 2 or summary["legendre_order"] != 1:
    raise SystemExit("summary group/order mismatch")
if summary["checked"] is not True or summary["check_passed"] is not True:
    raise SystemExit("summary did not record checked conversion")

check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
if check_summary["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("production minicase preflight did not pass")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required = {"mgxs", "mcompo", "run-summary", "check-summary", "recipe"}
if set(labels) != required:
    raise SystemExit(f"unexpected manifest labels: {sorted(labels)}")
if labels["check-summary"].get("summary_decision") != "mgxs_input_contract_passed":
    raise SystemExit("manifest did not record preflight decision")

print(
    "production minicase readback OK: "
    f"blocks={len(blocks)} mixtures={summary['mixture_count']} "
    f"groups={summary['energy_groups']} P{summary['legendre_order']}"
)
PY

echo
echo "openmc2donjon production minicase smoke: PASS"

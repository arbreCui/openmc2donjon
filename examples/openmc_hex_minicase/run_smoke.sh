#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_openmc_hex_minicase}"
PYTHON_BIN="${PYTHON_BIN:-}"
OPENMC_EXEC="${OPENMC_EXEC:-}"
OPENMC_THREADS="${OPENMC_THREADS:-2}"
HEX_MINICASE_PARTICLES="${HEX_MINICASE_PARTICLES:-300}"
HEX_MINICASE_BATCHES="${HEX_MINICASE_BATCHES:-10}"
HEX_MINICASE_INACTIVE="${HEX_MINICASE_INACTIVE:-4}"
UNCERTAINTY_PRODUCTION_FAIL="${OPENMC2DONJON_HEX_UNCERTAINTY_PRODUCTION_FAIL:-10.0}"
SCATTER_ROW_BALANCE_WARN="${OPENMC2DONJON_SCATTER_ROW_BALANCE_WARN:-5e-2}"
SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_SCATTER_ROW_BALANCE_FAIL:-}"
SCATTER_ROW_BALANCE_ARGS=(--scatter-row-balance-warn "$SCATTER_ROW_BALANCE_WARN")
if [[ -n "$SCATTER_ROW_BALANCE_FAIL" ]]; then
  SCATTER_ROW_BALANCE_ARGS+=(--scatter-row-balance-fail "$SCATTER_ROW_BALANCE_FAIL")
fi

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

EXAMPLE_DIR="$REPO_ROOT/examples/openmc_hex_minicase"
CASE_DIR="$RUN_DIR/openmc_case"
DRY_RUN_DIR="$RUN_DIR/openmc2donjon_dry_run"
CONVERT_RUN_DIR="$RUN_DIR/openmc2donjon_run"
STATEPOINT="$CASE_DIR/statepoint.${HEX_MINICASE_BATCHES}.h5"
MGXS="$CONVERT_RUN_DIR/mgxs_library.h5"
MCO="$CONVERT_RUN_DIR/out.mcompo.txt"
MACROLIB="$RUN_DIR/out.macrolib.txt"
SUMMARY="$CONVERT_RUN_DIR/run_summary.json"
CHECK_SUMMARY="$CONVERT_RUN_DIR/check_summary.json"
MANIFEST="$CONVERT_RUN_DIR/manifest.json"

echo "== openmc2donjon OpenMC hex minicase smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "openmc: ${OPENMC_EXEC:-not found}"

if [[ -z "$OPENMC_EXEC" ]]; then
  echo "OpenMC hex minicase skipped: OpenMC executable not found"
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
  echo "OpenMC hex minicase skipped: OpenMC Python runtime is not configured"
  exit 0
fi

echo
echo "== Build OpenMC XML =="
"$PYTHON_BIN" "$EXAMPLE_DIR/build_model.py" \
  --case-dir "$CASE_DIR" \
  --particles "$HEX_MINICASE_PARTICLES" \
  --batches "$HEX_MINICASE_BATCHES" \
  --inactive "$HEX_MINICASE_INACTIVE"

echo
echo "== Strict production dry-run =="
OPENMC2DONJON_HEX_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --no-load-statepoint \
  --dry-run \
  --strict-dry-run \
  --run-dir "$DRY_RUN_DIR" \
  --production \
  --expected-energy-group-structure OPENMC2DONJON-HEX-MINICASE-2G \
  --uncertainty-production-fail "$UNCERTAINTY_PRODUCTION_FAIL" \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

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
OPENMC2DONJON_HEX_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$CONVERT_RUN_DIR" \
  --force-run-dir \
  --production \
  --expected-energy-group-structure OPENMC2DONJON-HEX-MINICASE-2G \
  --uncertainty-production-fail "$UNCERTAINTY_PRODUCTION_FAIL" \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== MACROLIB convert =="
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" \
  --format macrolib \
  -o "$MACROLIB" \
  --production \
  --expected-energy-group-structure OPENMC2DONJON-HEX-MINICASE-2G \
  --uncertainty-production-fail "$UNCERTAINTY_PRODUCTION_FAIL" \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== Readback =="
"$PYTHON_BIN" - "$MGXS" "$MCO" "$MACROLIB" "$SUMMARY" "$CHECK_SUMMARY" "$MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary
from openmc2donjon.macrolib import read_macrolib_ascii

mgxs = Path(sys.argv[1])
mco = Path(sys.argv[2])
macrolib_path = Path(sys.argv[3])
summary_path = Path(sys.argv[4])
check_summary_path = Path(sys.argv[5])
manifest_path = Path(sys.argv[6])
expected_names = ["HEX_C", "HEX_E", "HEX_NE", "HEX_NW", "HEX_W", "HEX_SW", "HEX_SE"]

with h5py.File(mgxs, "r") as h5:
    if h5.attrs["case"] != "openmc_hex_minicase":
        raise SystemExit("missing openmc_hex_minicase root attr")
    if h5.attrs["domain_mode"] != "hex_cell":
        raise SystemExit("unexpected domain_mode")
    if h5.attrs["geometry_kind"] != "hexagonal":
        raise SystemExit("unexpected geometry_kind")
    if int(h5.attrs["energy_groups"]) != 2:
        raise SystemExit("unexpected group count")
    if int(h5.attrs["legendre_order"]) != 1:
        raise SystemExit("unexpected Legendre order")
    names = sorted(h5["mixtures"])
    if names != sorted(expected_names):
        raise SystemExit(f"unexpected mixture names: {names}")
    fissionable_count = 0
    non_fissionable_count = 0
    for name in expected_names:
        mixture = h5[f"mixtures/{name}"]
        if "transport_total" not in mixture:
            raise SystemExit(f"{name}: missing transport_total")
        if bool(mixture.attrs["fissionable"]):
            fissionable_count += 1
            if "kappa_fission" not in mixture:
                raise SystemExit(f"{name}: missing fissionable kappa_fission")
            if not np.any(mixture["kappa_fission"][:] > 0.0):
                raise SystemExit(f"{name}: fissionable kappa_fission has no positive bins")
        else:
            non_fissionable_count += 1
            if "kappa_fission" in mixture and not np.allclose(
                mixture["kappa_fission"][:],
                0.0,
            ):
                raise SystemExit(f"{name}: non-fissionable kappa_fission is not zero")
        if float(mixture.attrs["volume"]) <= 0.0:
            raise SystemExit(f"{name}: non-positive volume")
        if mixture["scatter_matrix"].shape != (2, 2, 2):
            raise SystemExit(f"{name}: unexpected scatter shape {mixture['scatter_matrix'].shape}")
        if mixture.attrs["source_domain_type"] != "cell":
            raise SystemExit(f"{name}: source domain is not cell")
        if float(mixture.attrs["hex_pitch_cm"]) <= 0.0:
            raise SystemExit(f"{name}: non-positive hex pitch metadata")
    if fissionable_count != 6 or non_fissionable_count != 1:
        raise SystemExit(
            "unexpected hex fissionable split: "
            f"{fissionable_count} fissionable, {non_fissionable_count} non-fissionable"
        )

mcompo_blocks = lcm_ascii.read_lcm_ascii(mco)
macrolib = read_macrolib_ascii(macrolib_path)
macrolib_blocks = lcm_ascii.read_lcm_ascii(macrolib_path)
if macrolib.ngroups != 2 or macrolib.nmixtures != 7:
    raise SystemExit("unexpected MACROLIB dimensions")
if "H-FACTOR" not in [block.name for block in mcompo_blocks if block.name]:
    raise SystemExit("MULTICOMPO output is missing H-FACTOR")
if macrolib.h_factor is None:
    raise SystemExit("MACROLIB output is missing H-FACTOR")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(summary)
if summary_errors:
    raise SystemExit("invalid from-OpenMC summary: " + "; ".join(summary_errors))
if summary["mixture_names"] != sorted(expected_names):
    raise SystemExit("summary mixture names mismatch")
if summary["energy_groups"] != 2 or summary["legendre_order"] != 1:
    raise SystemExit("summary group/order mismatch")
if summary["checked"] is not True or summary["check_passed"] is not True:
    raise SystemExit("summary did not record checked conversion")

check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
if check_summary["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("OpenMC hex minicase preflight did not pass")
input_summary = check_summary["inputs"][0]
if input_summary["mixtures"] != 7:
    raise SystemExit("OpenMC hex minicase preflight did not see seven hex domains")
if input_summary["volume_attributes"] != 7:
    raise SystemExit("OpenMC hex minicase preflight did not see all explicit volumes")
if input_summary["transport_total_datasets"] != 7:
    raise SystemExit("OpenMC hex minicase preflight did not see all transport_total datasets")
if input_summary["h_factor_datasets"] != 7:
    raise SystemExit(
        "OpenMC hex minicase preflight did not see one H-FACTOR dataset per domain"
    )

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required = {"mgxs", "mcompo", "run-summary", "check-summary", "recipe"}
if set(labels) != required:
    raise SystemExit(f"unexpected manifest labels: {sorted(labels)}")
if labels["check-summary"].get("summary_decision") != "mgxs_input_contract_passed":
    raise SystemExit("manifest did not record preflight decision")

print(
    "OpenMC hex minicase readback OK: "
    f"mixtures={summary['mixture_count']} groups={summary['energy_groups']} "
    f"P{summary['legendre_order']} mcompo_blocks={len(mcompo_blocks)} "
    f"macrolib_blocks={len(macrolib_blocks)}"
)
PY

echo
echo "openmc2donjon OpenMC hex minicase smoke: PASS"

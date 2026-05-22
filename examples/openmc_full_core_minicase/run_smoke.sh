#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_openmc_full_core_minicase}"
PYTHON_BIN="${PYTHON_BIN:-}"
OPENMC_EXEC="${OPENMC_EXEC:-}"
OPENMC_THREADS="${OPENMC_THREADS:-2}"
FULL_CORE_PARTICLES="${FULL_CORE_PARTICLES:-3000}"
FULL_CORE_BATCHES="${FULL_CORE_BATCHES:-14}"
FULL_CORE_INACTIVE="${FULL_CORE_INACTIVE:-4}"
UNCERTAINTY_PRODUCTION_FAIL="${OPENMC2DONJON_FULL_CORE_UNCERTAINTY_PRODUCTION_FAIL:-5.0}"

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

EXAMPLE_DIR="$REPO_ROOT/examples/openmc_full_core_minicase"
CASE_DIR="$RUN_DIR/openmc_case"
DRY_RUN_DIR="$RUN_DIR/openmc2donjon_dry_run"
CONVERT_RUN_DIR="$RUN_DIR/openmc2donjon_run"
STATEPOINT="$CASE_DIR/statepoint.${FULL_CORE_BATCHES}.h5"
MGXS="$CONVERT_RUN_DIR/mgxs_library.h5"
MCO="$CONVERT_RUN_DIR/out.mcompo.txt"
MACROLIB="$RUN_DIR/out.macrolib.txt"
SUMMARY="$CONVERT_RUN_DIR/run_summary.json"
CHECK_SUMMARY="$CONVERT_RUN_DIR/check_summary.json"
MANIFEST="$CONVERT_RUN_DIR/manifest.json"
SPH_FIXTURE_DIR="$RUN_DIR/full_core_sph_fixture"
SPH_CONFIG="$SPH_FIXTURE_DIR/loop_config.json"
SPH_SUMMARY="$SPH_FIXTURE_DIR/sph_loop_summary.json"
SPH_BUNDLE="$SPH_FIXTURE_DIR/bundle"
ENERGY_STRUCTURE="OPENMC2DONJON-FULL-CORE-MINICASE-2G"

echo "== openmc2donjon OpenMC full-core assembly-wise minicase smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "openmc: ${OPENMC_EXEC:-not found}"

if [[ -z "$OPENMC_EXEC" ]]; then
  echo "OpenMC full-core minicase skipped: OpenMC executable not found"
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
  echo "OpenMC full-core minicase skipped: OpenMC Python runtime is not configured"
  exit 0
fi

echo
echo "== Build OpenMC XML =="
"$PYTHON_BIN" "$EXAMPLE_DIR/build_model.py" \
  --case-dir "$CASE_DIR" \
  --particles "$FULL_CORE_PARTICLES" \
  --batches "$FULL_CORE_BATCHES" \
  --inactive "$FULL_CORE_INACTIVE"

echo
echo "== Strict production dry-run =="
OPENMC2DONJON_FULL_CORE_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --no-load-statepoint \
  --dry-run \
  --strict-dry-run \
  --run-dir "$DRY_RUN_DIR" \
  --production \
  --expected-energy-group-structure "$ENERGY_STRUCTURE" \
  --uncertainty-production-fail "$UNCERTAINTY_PRODUCTION_FAIL"

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
OPENMC2DONJON_FULL_CORE_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$CONVERT_RUN_DIR" \
  --force-run-dir \
  --production \
  --expected-energy-group-structure "$ENERGY_STRUCTURE" \
  --uncertainty-production-fail "$UNCERTAINTY_PRODUCTION_FAIL"

echo
echo "== MACROLIB convert =="
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" \
  --format macrolib \
  -o "$MACROLIB" \
  --production \
  --expected-energy-group-structure "$ENERGY_STRUCTURE" \
  --uncertainty-production-fail "$UNCERTAINTY_PRODUCTION_FAIL"

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
expected_names = [
    f"ASM_Y{y_index:02d}_X{x_index:02d}"
    for y_index in range(1, 4)
    for x_index in range(1, 4)
]

with h5py.File(mgxs, "r") as h5:
    if h5.attrs["case"] != "openmc_full_core_minicase":
        raise SystemExit("missing openmc_full_core_minicase root attr")
    if h5.attrs["domain_mode"] != "full_core_assembly":
        raise SystemExit("unexpected domain_mode")
    if tuple(h5.attrs["core_shape"]) != (3, 3):
        raise SystemExit("unexpected core_shape")
    if int(h5.attrs["axial_layers"]) != 1:
        raise SystemExit("unexpected axial layer count")
    if int(h5.attrs["energy_groups"]) != 2:
        raise SystemExit("unexpected group count")
    if int(h5.attrs["legendre_order"]) != 1:
        raise SystemExit("unexpected Legendre order")
    names = sorted(h5["mixtures"])
    if names != expected_names:
        raise SystemExit(f"unexpected mixture names: {names}")
    if "openmc_volume_flux" not in h5:
        raise SystemExit("full-core MGXS is missing openmc_volume_flux")
    openmc_volume_flux = h5["openmc_volume_flux"][:]
    if openmc_volume_flux.shape != (9, 2):
        raise SystemExit(f"unexpected OpenMC volume-flux shape: {openmc_volume_flux.shape}")
    if not np.all(np.isfinite(openmc_volume_flux)) or np.any(openmc_volume_flux <= 0.0):
        raise SystemExit("OpenMC volume flux is not positive finite")
    for name in expected_names:
        mixture = h5[f"mixtures/{name}"]
        if "transport_total" not in mixture:
            raise SystemExit(f"{name}: missing transport_total")
        if "kappa_fission" not in mixture:
            raise SystemExit(f"{name}: missing kappa_fission")
        if not np.any(mixture["kappa_fission"][:] > 0.0):
            raise SystemExit(f"{name}: kappa_fission has no positive bins")
        if float(mixture.attrs["volume"]) <= 0.0:
            raise SystemExit(f"{name}: non-positive volume")
        if mixture["scatter_matrix"].shape != (2, 2, 2):
            raise SystemExit(f"{name}: unexpected scatter shape {mixture['scatter_matrix'].shape}")
        for attr in ("assembly_x", "assembly_y", "axial_layer", "assembly_material_tag"):
            if attr not in mixture.attrs:
                raise SystemExit(f"{name}: missing spatial attr {attr}")

mcompo_blocks = lcm_ascii.read_lcm_ascii(mco)
macrolib = read_macrolib_ascii(macrolib_path)
if macrolib.ngroups != 2 or macrolib.nmixtures != 9:
    raise SystemExit("unexpected MACROLIB dimensions")
if "H-FACTOR" not in [block.name for block in mcompo_blocks if block.name]:
    raise SystemExit("MULTICOMPO output is missing H-FACTOR")
if macrolib.h_factor is None:
    raise SystemExit("MACROLIB output is missing H-FACTOR")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(summary)
if summary_errors:
    raise SystemExit("invalid from-OpenMC summary: " + "; ".join(summary_errors))
if summary["mixture_names"] != expected_names:
    raise SystemExit("summary mixture names mismatch")
if summary["energy_groups"] != 2 or summary["legendre_order"] != 1:
    raise SystemExit("summary group/order mismatch")
if summary["checked"] is not True or summary["check_passed"] is not True:
    raise SystemExit("summary did not record checked conversion")

check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
input_summary = check_summary["inputs"][0]
if check_summary["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("OpenMC full-core minicase preflight did not pass")
if input_summary["mixtures"] != 9:
    raise SystemExit("preflight did not see nine assembly domains")
if input_summary["h_factor_datasets"] != 9:
    raise SystemExit("preflight did not see all H-FACTOR/kappa_fission datasets")
if input_summary["transport_total_datasets"] != 9:
    raise SystemExit("preflight did not see all transport_total datasets")
if input_summary["volume_attributes"] != 9:
    raise SystemExit("preflight did not see all explicit volumes")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
for label in ("mgxs", "mcompo", "run-summary", "check-summary"):
    if label not in labels:
        raise SystemExit(f"bundle manifest missing {label}")

print(
    "full-core assembly-wise readback OK: "
    f"mixtures={len(expected_names)} groups=2 mco_blocks={len(mcompo_blocks)}"
)
PY

echo
echo "== Full-core SPH loop handoff =="
"$PYTHON_BIN" "$EXAMPLE_DIR/make_sph_loop_fixture.py" \
  --mgxs "$MGXS" \
  --output-dir "$SPH_FIXTURE_DIR" \
  --config "$SPH_CONFIG" \
  --driver "$EXAMPLE_DIR/fake_full_core_low_order_solver.py" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$SPH_CONFIG" \
  --summary-json "$SPH_SUMMARY" \
  --bundle-dir "$SPH_BUNDLE" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli validate-bundle "$SPH_BUNDLE/manifest.json"

"$PYTHON_BIN" - "$SPH_FIXTURE_DIR" "$SPH_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii


fixture_dir = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
expected_names = [
    f"ASM_Y{y_index:02d}_X{x_index:02d}"
    for y_index in range(1, 4)
    for x_index in range(1, 4)
]

summary = json.loads(summary_path.read_text(encoding="utf-8"))
if summary["decision"] != "openmc2donjon_sph_loop_passed":
    raise SystemExit("SPH loop did not pass")
if summary["completed_iterations"] != 2:
    raise SystemExit("SPH loop did not complete two iterations")
if summary["final_solve"] is None:
    raise SystemExit("SPH loop did not run final solve")
if not summary["converged"]:
    raise SystemExit("SPH loop did not converge")
if not summary["acceptance_passed"]:
    raise SystemExit("SPH loop acceptance failed")
preflight = summary["flux_map_preflight"]
if preflight["map_kind"] != "map_h5:/scalar_flux_ids":
    raise SystemExit("SPH loop did not use the fixture flux map")
if preflight["mixture_names"] != expected_names:
    raise SystemExit("SPH loop mixture names mismatch")
if preflight["scalar_flux_ids"] != list(range(1, 10)):
    raise SystemExit("SPH loop scalar flux IDs are not one per assembly")
if preflight["reference_flux_shape"] != [9, 2]:
    raise SystemExit("SPH loop reference flux shape mismatch")
quality = summary["quality"]
if quality["final_flux_ratio_max_residual"] > 1.0e-8:
    raise SystemExit("SPH final flux residual exceeds ASCII round-trip tolerance")

final_sph = Path(summary["final_sph_sidecar"])
with h5py.File(final_sph, "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], np.full((9, 2), 2.0))
    assert h5.attrs["sph_kind"] == "full-core-assembly-sph-loop-iter2"

expected_path = fixture_dir / "expected_sph.h5"
with h5py.File(expected_path, "r") as h5:
    np.testing.assert_allclose(h5["expected_sph"][:], np.full((9, 2), 2.0))

macrolib = read_macrolib_ascii(Path(summary["final_ascii"]))
if macrolib.ngroups != 2 or macrolib.nmixtures != 9:
    raise SystemExit("SPH MACROLIB dimensions changed")
if macrolib.sph is None:
    raise SystemExit("SPH MACROLIB is missing SPH data")
np.testing.assert_allclose(macrolib.sph, np.full((9, 2), 2.0))

print("full-core SPH loop readback OK: mixtures=9 groups=2 final_sph=2")
PY

echo
echo "OpenMC full-core assembly-wise minicase smoke passed"

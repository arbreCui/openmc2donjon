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
SCATTER_ROW_BALANCE_WARN="${OPENMC2DONJON_SCATTER_ROW_BALANCE_WARN:-5e-2}"
SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_SCATTER_ROW_BALANCE_FAIL:-}"
SCATTER_ROW_BALANCE_ARGS=(--scatter-row-balance-warn "$SCATTER_ROW_BALANCE_WARN")
if [[ -n "$SCATTER_ROW_BALANCE_FAIL" ]]; then
  SCATTER_ROW_BALANCE_ARGS+=(--scatter-row-balance-fail "$SCATTER_ROW_BALANCE_FAIL")
fi
UNCERTAINTY_WARN="${OPENMC2DONJON_UNCERTAINTY_WARN:-5e-2}"
UNCERTAINTY_FAIL="${OPENMC2DONJON_UNCERTAINTY_FAIL:-}"
UNCERTAINTY_PRODUCTION_FAIL="${OPENMC2DONJON_UNCERTAINTY_PRODUCTION_FAIL:-1.0}"
UNCERTAINTY_ARGS=(--uncertainty-warn "$UNCERTAINTY_WARN")
if [[ -n "$UNCERTAINTY_FAIL" ]]; then
  UNCERTAINTY_ARGS+=(--uncertainty-fail "$UNCERTAINTY_FAIL")
fi
if [[ -n "$UNCERTAINTY_PRODUCTION_FAIL" ]]; then
  UNCERTAINTY_ARGS+=(--uncertainty-production-fail "$UNCERTAINTY_PRODUCTION_FAIL")
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

EXAMPLE_DIR="$REPO_ROOT/examples/production_minicase"
CASE_DIR="$RUN_DIR/openmc_case"
DRY_RUN_DIR="$RUN_DIR/openmc2donjon_dry_run"
CONVERT_RUN_DIR="$RUN_DIR/openmc2donjon_run"
RECIPE_TALLIES="$RUN_DIR/tallies_from_recipe.xml"
STATEPOINT="$CASE_DIR/statepoint.${MINICASE_BATCHES}.h5"
MGXS="$CONVERT_RUN_DIR/mgxs_library.h5"
MCO="$CONVERT_RUN_DIR/out.mcompo.txt"
SUMMARY="$CONVERT_RUN_DIR/run_summary.json"
CHECK_SUMMARY="$CONVERT_RUN_DIR/check_summary.json"
MANIFEST="$CONVERT_RUN_DIR/manifest.json"
STRICT_UNCERTAINTY_CHECK_SUMMARY="$RUN_DIR/strict_uncertainty_check_summary.json"
SPH_HANDOFF_RUN_DIR="$RUN_DIR/openmc2donjon_sph_loop_handoff"
SPH_HANDOFF_MGXS="$SPH_HANDOFF_RUN_DIR/mgxs_library.h5"
SPH_HANDOFF_SUMMARY="$SPH_HANDOFF_RUN_DIR/openmc_sph_loop_handoff_summary.json"
SPH_SCAFFOLD_DIR="$SPH_HANDOFF_RUN_DIR/sph_loop_inputs"
SPH_SOLVE_TEMPLATE="$REPO_ROOT/examples/sph_loop_minicase/templates/solve_lflux_dump.x2m.in"
SPH_LOOP_CONFIG="$SPH_SCAFFOLD_DIR/loop_config.json"
SPH_LOOP_DIR="$SPH_SCAFFOLD_DIR/sph_loop"
SPH_LOOP_SUMMARY="$SPH_LOOP_DIR/loop_summary.json"
LOW_ORDER_RAW="$RUN_DIR/low_order_driver_raw.h5"
ADF_RUN_DIR="$RUN_DIR/openmc2donjon_adf_run"
SURFACE_FLUX="$ADF_RUN_DIR/openmc_surface_flux.h5"
SURFACE_FLUX_SUMMARY="$ADF_RUN_DIR/surface_flux_summary.json"
LOW_ORDER_DRIVER="$ADF_RUN_DIR/low_order_driver.h5"
LOW_ORDER_DRIVER_SUMMARY="$ADF_RUN_DIR/low_order_driver_summary.json"
LOW_ORDER_DRIVER_CHECK_SUMMARY="$ADF_RUN_DIR/low_order_driver_check_summary.json"
HOMOGENEOUS_FACE_FLUX="$ADF_RUN_DIR/homogeneous_face_flux.h5"
HOMOGENEOUS_FACE_FLUX_SUMMARY="$ADF_RUN_DIR/homogeneous_face_flux_summary.json"
FACE_FLUX_CHECK_SUMMARY="$ADF_RUN_DIR/face_flux_check_summary.json"
ADF_SIDECAR="$ADF_RUN_DIR/adf_sidecar.h5"
ADF_SIDECAR_SUMMARY="$ADF_RUN_DIR/adf_sidecar_summary.json"
ADF_H5="$ADF_RUN_DIR/mgxs_library.h5"
ADF_MCO="$ADF_RUN_DIR/out.mcompo.txt"
ADF_RUN_SUMMARY="$ADF_RUN_DIR/run_summary.json"
ADF_CHECK_SUMMARY="$ADF_RUN_DIR/check_summary.json"
ADF_INJECT_SUMMARY="$ADF_RUN_DIR/adf_summary.json"
ADF_MANIFEST="$ADF_RUN_DIR/manifest.json"
EXTERNAL_ADF_RUN_DIR="$RUN_DIR/openmc2donjon_external_adf_run"
EXTERNAL_ADF_H5="$EXTERNAL_ADF_RUN_DIR/mgxs_library.h5"
EXTERNAL_ADF_MCO="$EXTERNAL_ADF_RUN_DIR/out.mcompo.txt"
EXTERNAL_ADF_RUN_SUMMARY="$EXTERNAL_ADF_RUN_DIR/run_summary.json"
EXTERNAL_ADF_CHECK_SUMMARY="$EXTERNAL_ADF_RUN_DIR/check_summary.json"
EXTERNAL_ADF_INJECT_SUMMARY="$EXTERNAL_ADF_RUN_DIR/adf_summary.json"
EXTERNAL_ADF_SIDECAR="$EXTERNAL_ADF_RUN_DIR/adf_sidecar.h5"
EXTERNAL_ADF_SIDECAR_SUMMARY="$EXTERNAL_ADF_RUN_DIR/adf_sidecar_summary.json"
EXTERNAL_FACE_FLUX_CHECK_SUMMARY="$EXTERNAL_ADF_RUN_DIR/face_flux_check_summary.json"
EXTERNAL_ADF_MANIFEST="$EXTERNAL_ADF_RUN_DIR/manifest.json"
ADF_FACES="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"
SURFACE_FLUX_MU_EDGES="0.0,0.25,0.5,0.75,1.0"

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
echo "== Write OpenMC tallies from recipe CLI =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --write-tallies "$RECIPE_TALLIES" \
  --no-overwrite
"$PYTHON_BIN" - "$RECIPE_TALLIES" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

tallies_path = Path(sys.argv[1])
root = ET.parse(tallies_path).getroot()
names = [element.attrib.get("name", "") for element in root.findall("tally")]
if "openmc2donjon_surface_current_mu" not in names:
    raise SystemExit("recipe-written tallies.xml is missing the surface-current tally")
if "openmc2donjon_volume_flux" not in names:
    raise SystemExit("recipe-written tallies.xml is missing the volume-flux tally")
if len(names) < 2:
    raise SystemExit(f"recipe-written tallies.xml has too few tallies: {len(names)}")
print(
    "recipe-written tallies OK: "
    f"tallies={len(names)} volume_flux=openmc2donjon_volume_flux "
    "surface_current=openmc2donjon_surface_current_mu"
)
PY

echo
echo "== Strict production dry-run =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --no-load-statepoint \
  --dry-run \
  --strict-dry-run \
  --run-dir "$DRY_RUN_DIR" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}" \
  "${UNCERTAINTY_ARGS[@]}"

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
  --force-run-dir \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}" \
  "${UNCERTAINTY_ARGS[@]}"

"$PYTHON_BIN" - "$MGXS" "$MCO" "$SUMMARY" "$CHECK_SUMMARY" "$MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
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
    if "openmc_volume_flux" not in h5:
        raise SystemExit("production minicase MGXS is missing openmc_volume_flux")
    openmc_volume_flux = h5["openmc_volume_flux"][:]
    if openmc_volume_flux.shape != (2, 2):
        raise SystemExit(f"unexpected OpenMC volume-flux shape: {openmc_volume_flux.shape}")
    if not np.all(np.isfinite(openmc_volume_flux)) or np.any(openmc_volume_flux <= 0.0):
        raise SystemExit("OpenMC volume flux is not positive finite")
    for name in names:
        group = h5[f"mixtures/{name}"]
        if "transport_total" not in group:
            raise SystemExit(f"{name}: missing transport_total")
        volume = float(group.attrs["volume"])
        if volume <= 0.0:
            raise SystemExit(f"{name}: non-positive volume")
        for mean_name in (
            "total",
            "absorption",
            "scatter_matrix",
            "transport_total",
        ):
            std_name = f"{mean_name}_std_dev"
            if std_name not in group:
                raise SystemExit(f"{name}: missing real OpenMC {std_name}")
            mean = group[mean_name][:]
            std_dev = group[std_name][:]
            if std_dev.shape != mean.shape:
                raise SystemExit(
                    f"{name}: {std_name} shape {std_dev.shape} != {mean_name} {mean.shape}"
                )
            if not np.all(np.isfinite(std_dev)) or np.any(std_dev < 0.0):
                raise SystemExit(f"{name}: invalid {std_name}")
            if not np.any(std_dev > 0.0):
                raise SystemExit(f"{name}: {std_name} has no positive bins")

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
uncertainty = check_summary["inputs"][0]["uncertainty"]
if uncertainty["datasets"] <= 0:
    raise SystemExit("production minicase preflight did not see any *_std_dev datasets")
if uncertainty["missing_datasets"] >= uncertainty["expected_datasets"]:
    raise SystemExit("production minicase preflight treated all uncertainty datasets as missing")
if uncertainty["max_rel"] is None or uncertainty["max_rel"] <= 0.0:
    raise SystemExit("production minicase preflight did not compute positive relative uncertainty")
if uncertainty["production_max_rel"] is None or uncertainty["production_max_rel"] <= 0.0:
    raise SystemExit("production minicase preflight did not compute positive production uncertainty")

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
    f"groups={summary['energy_groups']} P{summary['legendre_order']} "
    f"uncertainty_max_rel={uncertainty['max_rel']:.6g} "
    f"production_max_rel={uncertainty['production_max_rel']:.6g}"
)
PY

echo
echo "== Assert strict uncertainty preflight can fail =="
if "$PYTHON_BIN" -m openmc2donjon.cli check \
  "$MGXS" \
  --uncertainty-production-fail 0.0 \
  --summary-json "$STRICT_UNCERTAINTY_CHECK_SUMMARY"; then
  echo "strict uncertainty check unexpectedly passed" >&2
  exit 1
fi
"$PYTHON_BIN" - "$STRICT_UNCERTAINTY_CHECK_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if summary["decision"] != "mgxs_input_contract_failed":
    raise SystemExit("strict uncertainty check did not record a failed decision")
input_summary = summary["inputs"][0]
uncertainty = input_summary["uncertainty"]
if uncertainty["datasets"] <= 0:
    raise SystemExit("strict uncertainty check did not see *_std_dev datasets")
if uncertainty["max_rel"] is None or uncertainty["max_rel"] <= 0.0:
    raise SystemExit("strict uncertainty check did not compute positive max_rel")
if uncertainty["production_max_rel"] is None or uncertainty["production_max_rel"] <= 0.0:
    raise SystemExit("strict uncertainty check did not compute positive production max_rel")
if not any("exceeds production fail threshold" in issue for issue in input_summary["issues"]):
    raise SystemExit("strict uncertainty check did not fail on the production threshold")
print(
    "strict uncertainty preflight failed as expected: "
    f"production_max_rel={uncertainty['production_max_rel']:.6g}"
)
PY

echo
echo "== Prepare OpenMC SPH loop handoff =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.cli prepare-openmc-sph-loop \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$SPH_HANDOFF_RUN_DIR" \
  --solve-template "$SPH_SOLVE_TEMPLATE" \
  --scalar-flux-map ASM_FUEL_LEFT=2,ASM_MOD_RIGHT=4 \
  --case-id-prefix production_minicase_sph_loop \
  --stage-prefix odj_production_minicase_sph_loop \
  --case-dir openmc2donjon/case_runs/production_minicase_sph_loop \
  --sph-kind production-minicase-openmc-sph-loop \
  --source-label "Production minicase OpenMC SPH loop handoff" \
  --acceptance-min-completed-iterations 2 \
  --acceptance-require-final-solve \
  --acceptance-max-final-to-initial-flux-residual-ratio 0.5 \
  --acceptance-max-final-clipped-fraction 1.0 \
  --acceptance-max-final-clipped-count 4 \
  --acceptance-sph-minimum-floor 0.5 \
  --acceptance-sph-maximum-ceiling 3.0 \
  --fail-on-acceptance-violation \
  --force \
  "${SCATTER_ROW_BALANCE_ARGS[@]}" \
  "${UNCERTAINTY_ARGS[@]}"

"$PYTHON_BIN" - "$SPH_HANDOFF_MGXS" "$SPH_SCAFFOLD_DIR" "$SPH_HANDOFF_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np

mgxs = Path(sys.argv[1])
scaffold = Path(sys.argv[2])
summary = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))

with h5py.File(mgxs, "r") as h5:
    if "openmc_volume_flux" not in h5:
        raise SystemExit("SPH handoff MGXS is missing openmc_volume_flux")
    flux = h5["openmc_volume_flux"][:]
    if flux.shape != (2, 2):
        raise SystemExit(f"unexpected SPH handoff OpenMC flux shape: {flux.shape}")
    if not np.all(np.isfinite(flux)) or np.any(flux <= 0.0):
        raise SystemExit("SPH handoff OpenMC flux is not positive finite")

with h5py.File(scaffold / "reference_flux.h5", "r") as h5:
    np.testing.assert_allclose(h5["openmc_volume_flux"][:], flux)

with h5py.File(scaffold / "flux_map.h5", "r") as h5:
    np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [2, 4])

config = json.loads((scaffold / "loop_config.json").read_text(encoding="utf-8"))
if config["input_h5"] != str(mgxs):
    raise SystemExit("SPH loop config input_h5 mismatch")
if summary["decision"] != "openmc2donjon_openmc_sph_loop_handoff_passed":
    raise SystemExit("SPH handoff summary did not pass")

print(f"production minicase SPH loop handoff OK: {scaffold}")
PY

echo
echo "== Run OpenMC SPH loop handoff through DONJON =="
"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$SPH_LOOP_CONFIG" \
  --summary-json "$SPH_LOOP_SUMMARY" \
  --force

"$PYTHON_BIN" - "$SPH_LOOP_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if summary["decision"] != "openmc2donjon_sph_loop_passed":
    raise SystemExit("SPH loop summary did not pass")
if not summary["acceptance_enabled"] or not summary["acceptance_passed"]:
    raise SystemExit("SPH loop production acceptance did not pass")
if summary["completed_iterations"] != 2:
    raise SystemExit(f"unexpected completed iterations: {summary['completed_iterations']}")
if len(summary["solves"]) != 3:
    raise SystemExit(f"expected two iteration solves plus final solve: {len(summary['solves'])}")
if len(summary["postprocesses"]) != 2:
    raise SystemExit(f"expected two NSPH apply postprocesses: {len(summary['postprocesses'])}")
if any(solve["returncode"] != 0 for solve in summary["solves"]):
    raise SystemExit("at least one DONJON solve failed")
if any(step["returncode"] != 0 for step in summary["postprocesses"]):
    raise SystemExit("at least one DONJON NSPH apply step failed")

checks = {
    item["name"]: item
    for item in summary["acceptance"]["checks"]
}
ratio = checks["max_final_to_initial_flux_residual_ratio"]["actual"]
if ratio is None or ratio > 0.5:
    raise SystemExit(f"SPH loop did not reduce flux residual enough: {ratio}")
clipped_fraction = checks["max_final_clipped_fraction"]["actual"]
if clipped_fraction is None or clipped_fraction > 1.0:
    raise SystemExit(f"unexpected SPH clipped fraction: {clipped_fraction}")
convergence = summary["convergence"]
if len(convergence) != 2:
    raise SystemExit(f"expected two convergence rows: {len(convergence)}")
if convergence[-1]["flux_ratio_max_residual"] >= convergence[0]["flux_ratio_max_residual"]:
    raise SystemExit("SPH loop flux residual did not improve")

for key in ("final_ascii", "final_sph_sidecar", "audit_csv", "audit_text"):
    path = Path(summary[key])
    if not path.exists():
        raise SystemExit(f"missing SPH loop artifact {key}: {path}")

with h5py.File(summary["final_sph_sidecar"], "r") as h5:
    sph = h5["sph"][:]
    if sph.shape != (2, 2):
        raise SystemExit(f"unexpected final SPH shape: {sph.shape}")
    if not np.all(np.isfinite(sph)) or np.any(sph <= 0.0):
        raise SystemExit("final SPH sidecar contains non-positive or non-finite values")

print(
    "production minicase DONJON SPH loop OK: "
    f"iterations={summary['completed_iterations']} final_ascii={summary['final_ascii']}"
)
PY

echo
echo "== Build raw low-order driver fixture =="
"$PYTHON_BIN" - "$MGXS" "$LOW_ORDER_RAW" "$ADF_FACES" <<'PY'
from pathlib import Path
import sys

import h5py
import numpy as np

mgxs_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
faces = tuple(part.strip() for part in sys.argv[3].split(",") if part.strip())

with h5py.File(mgxs_path, "r") as h5:
    mixture_names = tuple(str(name) for name in h5["mixtures"])
    ngroups = int(h5.attrs["energy_groups"])

volume_flux = np.zeros((len(mixture_names), ngroups), dtype=float)
net_current = np.zeros((len(mixture_names), len(faces), ngroups), dtype=float)
for mix_index in range(len(mixture_names)):
    volume_flux[mix_index] = 1.0 + 0.25 * mix_index + 0.10 * np.arange(ngroups)
    for face_index in range(len(faces)):
        net_current[mix_index, face_index] = (
            ((-1.0) ** face_index) * 0.01 * (mix_index + 1) * (np.arange(ngroups) + 1)
        )

with h5py.File(output_path, "w") as h5:
    h5.attrs["schema"] = "openmc2donjon.low-order-driver-raw.v1"
    volume = h5.create_dataset("volume_flux", data=volume_flux)
    current = h5.create_dataset("net_current_density", data=net_current)
    names = np.asarray(mixture_names, dtype="S")
    volume.attrs["mixture_names"] = names
    current.attrs["mixture_names"] = names

print(f"wrote low-order driver raw fixture: {output_path}")
PY

echo
echo "== Export and convert with integrated flux-ratio ADF workflow =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$ADF_RUN_DIR" \
  --force-run-dir \
  --build-flux-ratio-adf \
  --export-surface-flux \
  --surface-flux-tally-name openmc2donjon_surface_current_mu \
  --surface-flux-mesh-shape 1,2 \
  --surface-flux-mu-edges "$SURFACE_FLUX_MU_EDGES" \
  --surface-flux-face-area 4.0 \
  --low-order-raw-driver "$LOW_ORDER_RAW" \
  --low-order-source-label "production minicase external low-order driver fixture" \
  --adf-faces "$ADF_FACES" \
  --adf-face-widths 4.0 \
  --adf-invalid-fill 1.0 \
  --adf-kind flux-ratio-minicase \
  --adf-real false \
  --extra-artifact "low-order-raw=$LOW_ORDER_RAW" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}" \
  "${UNCERTAINTY_ARGS[@]}"

"$PYTHON_BIN" - "$SURFACE_FLUX" "$SURFACE_FLUX_SUMMARY" "$LOW_ORDER_DRIVER" "$LOW_ORDER_DRIVER_SUMMARY" "$LOW_ORDER_DRIVER_CHECK_SUMMARY" "$HOMOGENEOUS_FACE_FLUX" "$HOMOGENEOUS_FACE_FLUX_SUMMARY" "$FACE_FLUX_CHECK_SUMMARY" "$ADF_SIDECAR" "$ADF_SIDECAR_SUMMARY" "$ADF_H5" "$ADF_MCO" "$ADF_RUN_SUMMARY" "$ADF_CHECK_SUMMARY" "$ADF_INJECT_SUMMARY" "$ADF_MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary

surface_flux = Path(sys.argv[1])
surface_flux_summary_path = Path(sys.argv[2])
low_order_driver = Path(sys.argv[3])
low_order_driver_summary_path = Path(sys.argv[4])
low_order_driver_check_summary_path = Path(sys.argv[5])
homogeneous_face_flux = Path(sys.argv[6])
homogeneous_face_flux_summary_path = Path(sys.argv[7])
face_flux_check_summary_path = Path(sys.argv[8])
sidecar = Path(sys.argv[9])
sidecar_summary_path = Path(sys.argv[10])
mgxs = Path(sys.argv[11])
mco = Path(sys.argv[12])
summary_path = Path(sys.argv[13])
check_summary_path = Path(sys.argv[14])
adf_summary_path = Path(sys.argv[15])
manifest_path = Path(sys.argv[16])
faces = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")

surface_flux_summary = json.loads(surface_flux_summary_path.read_text(encoding="utf-8"))
if surface_flux_summary["decision"] != "openmc2donjon_surface_flux_export_passed":
    raise SystemExit("surface-flux summary did not pass")
if surface_flux_summary["schema"] != "openmc2donjon.surface-flux.v1":
    raise SystemExit("surface-flux summary schema mismatch")
if surface_flux_summary["mesh_shape"] != [1, 2]:
    raise SystemExit("surface-flux mesh shape mismatch")
if tuple(surface_flux_summary["face_names"]) != faces:
    raise SystemExit("surface-flux face names mismatch")

with h5py.File(surface_flux, "r") as h5:
    if h5.attrs["schema"] != "openmc2donjon.surface-flux.v1":
        raise SystemExit("surface-flux HDF5 schema mismatch")
    values = h5["surface_flux/mean"][:]
    if values.shape != (1, 2, 2, 4):
        raise SystemExit(f"unexpected surface-flux shape: {values.shape}")

low_order_driver_summary = json.loads(low_order_driver_summary_path.read_text(encoding="utf-8"))
if low_order_driver_summary["decision"] != "openmc2donjon_low_order_driver_passed":
    raise SystemExit("low-order driver summary did not pass")
if low_order_driver_summary["schema"] != "openmc2donjon.low-order-driver.v1":
    raise SystemExit("low-order driver summary schema mismatch")
if tuple(low_order_driver_summary["face_names"]) != faces:
    raise SystemExit("low-order driver summary face names mismatch")
if low_order_driver_summary["adapter_mode"] != "raw-driver-bundle":
    raise SystemExit("low-order driver did not use raw-driver adapter")

low_order_driver_check_summary = json.loads(
    low_order_driver_check_summary_path.read_text(encoding="utf-8")
)
if low_order_driver_check_summary["decision"] != "openmc2donjon_low_order_driver_contract_passed":
    raise SystemExit("low-order driver contract summary did not pass")
if low_order_driver_check_summary["schema"] != "openmc2donjon.low-order-driver-contract.v1":
    raise SystemExit("low-order driver contract summary schema mismatch")
if tuple(low_order_driver_check_summary["face_names"]) != faces:
    raise SystemExit("low-order driver contract summary face names mismatch")
if low_order_driver_check_summary["homogeneous_face_flux_min"] <= 0.0:
    raise SystemExit("low-order driver contract did not verify positive homogeneous face flux")

with h5py.File(low_order_driver, "r") as h5:
    if h5.attrs["schema"] != "openmc2donjon.low-order-driver.v1":
        raise SystemExit("low-order driver HDF5 schema mismatch")
    volume_flux = h5["volume_flux"][:]
    net_current = h5["net_current_density"][:]
    if volume_flux.shape != (2, 2):
        raise SystemExit(f"unexpected low-order volume-flux shape: {volume_flux.shape}")
    if net_current.shape != (2, 4, 2):
        raise SystemExit(f"unexpected low-order net-current shape: {net_current.shape}")
    if not np.all(np.isfinite(volume_flux)) or np.any(volume_flux <= 0.0):
        raise SystemExit("low-order volume flux is not positive finite")
    if not np.all(np.isfinite(net_current)):
        raise SystemExit("low-order net current is not finite")

homogeneous_face_flux_summary = json.loads(
    homogeneous_face_flux_summary_path.read_text(encoding="utf-8")
)
if homogeneous_face_flux_summary["decision"] != "openmc2donjon_homogeneous_face_flux_passed":
    raise SystemExit("homogeneous face-flux summary did not pass")
if homogeneous_face_flux_summary["schema"] != "openmc2donjon.homogeneous-face-flux.v1":
    raise SystemExit("homogeneous face-flux summary schema mismatch")
if tuple(homogeneous_face_flux_summary["face_names"]) != faces:
    raise SystemExit("homogeneous face-flux summary face names mismatch")

with h5py.File(homogeneous_face_flux, "r") as h5:
    if h5.attrs["schema"] != "openmc2donjon.homogeneous-face-flux.v1":
        raise SystemExit("homogeneous face-flux HDF5 schema mismatch")
    values = h5["homogeneous_face_flux"][:]
    if values.shape != (2, 4, 2):
        raise SystemExit(f"unexpected homogeneous face-flux shape: {values.shape}")
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise SystemExit("homogeneous face flux is not positive finite")

face_flux_check_summary = json.loads(
    face_flux_check_summary_path.read_text(encoding="utf-8")
)
if face_flux_check_summary["decision"] != "openmc2donjon_face_flux_contract_passed":
    raise SystemExit("face-flux contract summary did not pass")
if face_flux_check_summary["schema"] != "openmc2donjon.face-flux-contract.v1":
    raise SystemExit("face-flux contract summary schema mismatch")
if tuple(face_flux_check_summary["face_names"]) != faces:
    raise SystemExit("face-flux contract summary face names mismatch")
if face_flux_check_summary["surface_flux_dataset"] != "surface_flux/mean":
    raise SystemExit("face-flux contract surface dataset mismatch")
if face_flux_check_summary["homogeneous_face_flux_dataset"] != "homogeneous_face_flux":
    raise SystemExit("face-flux contract homogeneous dataset mismatch")

sidecar_summary = json.loads(sidecar_summary_path.read_text(encoding="utf-8"))
if sidecar_summary["decision"] != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit("ADF sidecar summary did not pass")
if sidecar_summary["schema"] != "openmc2donjon.adf-sidecar.v1":
    raise SystemExit("ADF sidecar summary schema mismatch")
if sidecar_summary["mode"] != "flux-ratio":
    raise SystemExit("ADF sidecar mode mismatch")
if sidecar_summary["adf_kind"] != "flux-ratio-minicase":
    raise SystemExit("ADF sidecar kind mismatch")
if sidecar_summary["adf_real"] is not False:
    raise SystemExit("ADF sidecar summary should be marked adf_real=false")
if tuple(sidecar_summary["face_names"]) != faces:
    raise SystemExit("ADF sidecar summary face names mismatch")

with h5py.File(sidecar, "r") as h5:
    if h5.attrs["adf_kind"] != "flux-ratio-minicase" or h5.attrs["adf_real"] != "false":
        raise SystemExit("ADF sidecar provenance mismatch")
    values = h5["adf"][:]
    if values.shape != (2, 4, 2):
        raise SystemExit(f"unexpected ADF sidecar shape: {values.shape}")
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise SystemExit("ADF sidecar contains non-positive or non-finite values")

with h5py.File(mgxs, "r") as h5:
    if h5.attrs["adf_kind"] != "flux-ratio-minicase" or h5.attrs["adf_real"] != "false":
        raise SystemExit("injected HDF5 ADF provenance mismatch")
    names = sorted(h5["mixtures"])
    if names != ["ASM_FUEL_LEFT", "ASM_MOD_RIGHT"]:
        raise SystemExit(f"unexpected ADF mixture names: {names}")
    for name in names:
        for face in faces:
            values = h5[f"mixtures/{name}/adf/{face}"][:]
            if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
                raise SystemExit(f"{name}/{face}: invalid injected ADF values")

blocks = lcm_ascii.read_lcm_ascii(mco)
block_names = [block.name for block in blocks if block.name]
for required_name in ("MACROLIB", "ADF", "HADF", *faces):
    if required_name not in block_names:
        raise SystemExit(f"ADF MULTICOMPO readback missing {required_name}")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(summary)
if summary_errors:
    raise SystemExit("invalid ADF from-OpenMC summary: " + "; ".join(summary_errors))
if summary["checked"] is not True or summary["check_passed"] is not True:
    raise SystemExit("ADF conversion summary did not record checked conversion")

check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
if check_summary["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("ADF production minicase preflight did not pass")

adf_summary = json.loads(adf_summary_path.read_text(encoding="utf-8"))
if adf_summary["schema"] != "openmc2donjon.adf-augment.v1":
    raise SystemExit("ADF injection summary schema mismatch")
if adf_summary["decision"] != "openmc2donjon_adf_augment_passed":
    raise SystemExit("ADF injection summary did not pass")
if tuple(adf_summary["face_names"]) != faces:
    raise SystemExit("ADF injection summary face names mismatch")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required = {
    "mgxs",
    "mcompo",
    "run-summary",
    "check-summary",
    "adf-source",
    "adf-summary",
    "adf-sidecar-summary",
    "recipe",
    "surface-flux",
    "surface-flux-summary",
    "low-order-raw",
    "low-order-driver",
    "low-order-driver-summary",
    "low-order-driver-check-summary",
    "homogeneous-face-flux",
    "homogeneous-face-flux-summary",
    "face-flux-check-summary",
}
if set(labels) != required:
    raise SystemExit(f"unexpected ADF manifest labels: {sorted(labels)}")
if labels["adf-summary"].get("summary_schema") != "openmc2donjon.adf-augment.v1":
    raise SystemExit("ADF manifest did not record augment summary schema")
if labels["adf-summary"].get("summary_decision") != "openmc2donjon_adf_augment_passed":
    raise SystemExit("ADF manifest did not record augment decision")
expected_summary_decisions = {
    "surface-flux-summary": "openmc2donjon_surface_flux_export_passed",
    "low-order-driver-summary": "openmc2donjon_low_order_driver_passed",
    "low-order-driver-check-summary": "openmc2donjon_low_order_driver_contract_passed",
    "homogeneous-face-flux-summary": "openmc2donjon_homogeneous_face_flux_passed",
    "face-flux-check-summary": "openmc2donjon_face_flux_contract_passed",
    "adf-sidecar-summary": "openmc2donjon_adf_sidecar_passed",
}
for label, decision in expected_summary_decisions.items():
    if labels[label].get("summary_decision") != decision:
        raise SystemExit(f"manifest did not record {label} decision")

print(
    "production minicase ADF readback OK: "
    f"blocks={len(blocks)} faces={','.join(faces)} labels={sorted(labels)}"
)
PY

echo
echo "== Export and convert with external flux-ratio ADF inputs =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$EXTERNAL_ADF_RUN_DIR" \
  --force-run-dir \
  --build-flux-ratio-adf \
  --adf-surface-flux "$SURFACE_FLUX::surface_flux/mean" \
  --homogeneous-face-flux "$HOMOGENEOUS_FACE_FLUX::homogeneous_face_flux" \
  --adf-faces "$ADF_FACES" \
  --adf-invalid-fill 1.0 \
  --adf-kind flux-ratio-minicase-external \
  --adf-real false \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}" \
  "${UNCERTAINTY_ARGS[@]}"

"$PYTHON_BIN" - "$ADF_H5" "$ADF_SIDECAR" "$EXTERNAL_ADF_H5" "$EXTERNAL_ADF_SIDECAR" "$EXTERNAL_ADF_MCO" "$EXTERNAL_ADF_RUN_SUMMARY" "$EXTERNAL_ADF_CHECK_SUMMARY" "$EXTERNAL_ADF_INJECT_SUMMARY" "$EXTERNAL_ADF_SIDECAR_SUMMARY" "$EXTERNAL_FACE_FLUX_CHECK_SUMMARY" "$EXTERNAL_ADF_MANIFEST" "$SURFACE_FLUX" "$HOMOGENEOUS_FACE_FLUX" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary

reference_h5 = Path(sys.argv[1])
reference_sidecar = Path(sys.argv[2])
candidate_h5 = Path(sys.argv[3])
candidate_sidecar = Path(sys.argv[4])
candidate_mco = Path(sys.argv[5])
summary_path = Path(sys.argv[6])
check_summary_path = Path(sys.argv[7])
adf_summary_path = Path(sys.argv[8])
sidecar_summary_path = Path(sys.argv[9])
face_flux_check_summary_path = Path(sys.argv[10])
manifest_path = Path(sys.argv[11])
surface_flux = Path(sys.argv[12])
homogeneous_face_flux = Path(sys.argv[13])
faces = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")

with h5py.File(reference_sidecar, "r") as ref, h5py.File(candidate_sidecar, "r") as out:
    expected = ref["adf"][:]
    actual = out["adf"][:]
    if not np.array_equal(actual, expected):
        max_abs = float(np.max(np.abs(actual - expected)))
        raise SystemExit(f"external ADF sidecar differs from reconstructed path: max_abs={max_abs}")
    if out.attrs["adf_kind"] != "flux-ratio-minicase-external":
        raise SystemExit("external ADF sidecar kind mismatch")
    if out.attrs["adf_real"] != "false":
        raise SystemExit("external ADF sidecar should be marked adf_real=false")

with h5py.File(reference_h5, "r") as ref, h5py.File(candidate_h5, "r") as out:
    for name in sorted(ref["mixtures"]):
        for face in faces:
            expected = ref[f"mixtures/{name}/adf/{face}"][:]
            actual = out[f"mixtures/{name}/adf/{face}"][:]
            if not np.array_equal(actual, expected):
                max_abs = float(np.max(np.abs(actual - expected)))
                raise SystemExit(f"{name}/{face}: external injected ADF differs max_abs={max_abs}")
    if out.attrs["adf_kind"] != "flux-ratio-minicase-external":
        raise SystemExit("external injected HDF5 ADF kind mismatch")
    if out.attrs["adf_real"] != "false":
        raise SystemExit("external injected HDF5 ADF real flag mismatch")

blocks = lcm_ascii.read_lcm_ascii(candidate_mco)
block_names = [block.name for block in blocks if block.name]
for required_name in ("MACROLIB", "ADF", "HADF", *faces):
    if required_name not in block_names:
        raise SystemExit(f"external ADF MULTICOMPO readback missing {required_name}")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(summary)
if summary_errors:
    raise SystemExit("invalid external ADF from-OpenMC summary: " + "; ".join(summary_errors))
if summary["checked"] is not True or summary["check_passed"] is not True:
    raise SystemExit("external ADF conversion summary did not record checked conversion")

check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
if check_summary["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("external ADF production minicase preflight did not pass")

adf_summary = json.loads(adf_summary_path.read_text(encoding="utf-8"))
if adf_summary["decision"] != "openmc2donjon_adf_augment_passed":
    raise SystemExit("external ADF injection summary did not pass")

sidecar_summary = json.loads(sidecar_summary_path.read_text(encoding="utf-8"))
if sidecar_summary["decision"] != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit("external ADF sidecar summary did not pass")
if sidecar_summary["adf_kind"] != "flux-ratio-minicase-external":
    raise SystemExit("external ADF sidecar summary kind mismatch")
if sidecar_summary["adf_surface_flux"] != str(surface_flux):
    raise SystemExit("external ADF sidecar surface-flux source mismatch")
if sidecar_summary["adf_surface_flux_dataset"] != "surface_flux/mean":
    raise SystemExit("external ADF sidecar surface-flux dataset mismatch")
if sidecar_summary["adf_homogeneous_face_flux"] != str(homogeneous_face_flux):
    raise SystemExit("external ADF sidecar homogeneous-flux source mismatch")
if sidecar_summary["adf_homogeneous_face_flux_dataset"] != "homogeneous_face_flux":
    raise SystemExit("external ADF sidecar homogeneous-flux dataset mismatch")

face_flux_check_summary = json.loads(
    face_flux_check_summary_path.read_text(encoding="utf-8")
)
if face_flux_check_summary["decision"] != "openmc2donjon_face_flux_contract_passed":
    raise SystemExit("external face-flux contract summary did not pass")
if face_flux_check_summary["schema"] != "openmc2donjon.face-flux-contract.v1":
    raise SystemExit("external face-flux contract summary schema mismatch")
if face_flux_check_summary["surface_flux"] != str(surface_flux):
    raise SystemExit("external face-flux contract surface source mismatch")
if face_flux_check_summary["surface_flux_dataset"] != "surface_flux/mean":
    raise SystemExit("external face-flux contract surface dataset mismatch")
if face_flux_check_summary["homogeneous_face_flux"] != str(homogeneous_face_flux):
    raise SystemExit("external face-flux contract homogeneous source mismatch")
if face_flux_check_summary["homogeneous_face_flux_dataset"] != "homogeneous_face_flux":
    raise SystemExit("external face-flux contract homogeneous dataset mismatch")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required = {
    "mgxs",
    "mcompo",
    "run-summary",
    "check-summary",
    "adf-source",
    "adf-summary",
    "adf-sidecar-summary",
    "face-flux-check-summary",
    "surface-flux",
    "homogeneous-face-flux",
    "recipe",
}
if set(labels) != required:
    raise SystemExit(f"unexpected external ADF manifest labels: {sorted(labels)}")
for forbidden in (
    "low-order-raw",
    "low-order-driver",
    "low-order-driver-summary",
    "low-order-driver-check-summary",
    "homogeneous-face-flux-summary",
):
    if forbidden in labels:
        raise SystemExit(f"external ADF manifest unexpectedly includes {forbidden}")
if labels["surface-flux"]["source"] != str(surface_flux):
    raise SystemExit("external ADF manifest surface-flux source mismatch")
if labels["homogeneous-face-flux"]["source"] != str(homogeneous_face_flux):
    raise SystemExit("external ADF manifest homogeneous-face-flux source mismatch")
if labels["adf-sidecar-summary"].get("summary_decision") != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit("external ADF manifest did not record sidecar decision")
if labels["face-flux-check-summary"].get("summary_decision") != "openmc2donjon_face_flux_contract_passed":
    raise SystemExit("external ADF manifest did not record face-flux contract decision")

print(
    "production minicase external ADF readback OK: "
    f"blocks={len(blocks)} faces={','.join(faces)} labels={sorted(labels)}"
)
PY

echo
echo "openmc2donjon production minicase smoke: PASS"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_openmc_sph_loop_entrypoint}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

CASE_DIR="$RUN_DIR/case"
STATEPOINT="$CASE_DIR/statepoint.fake.h5"
HANDOFF_RUN_DIR="$CASE_DIR/openmc_sph_loop_handoff"
MGXS="$HANDOFF_RUN_DIR/mgxs_library.h5"
SCAFFOLD_DIR="$HANDOFF_RUN_DIR/sph_loop_inputs"
HANDOFF_SUMMARY="$HANDOFF_RUN_DIR/openmc_sph_loop_handoff_summary.json"
SCAFFOLD_SUMMARY="$SCAFFOLD_DIR/scaffold_summary.json"
RUN_SCRIPT="$SCAFFOLD_DIR/run_sph_loop.sh"
BUNDLE_DIR="$HANDOFF_RUN_DIR/bundle"
SOLVE_TEMPLATE="$REPO_ROOT/examples/sph_loop_minicase/templates/solve_lflux_dump.x2m.in"
EXPECTED_REFERENCE_FLUX='[[617.96762, 156.844407], [47.4604219, 4.87293612]]'
EXPECTED_REFERENCE_FLUX_STD_DEV='[[0.61796762, 0.156844407], [0.0474604219, 0.00487293612]]'

echo "== openmc2donjon OpenMC SPH loop entrypoint smoke =="
mkdir -p "$CASE_DIR"
printf "fake statepoint for openmc sph loop entrypoint\n" > "$STATEPOINT"

"$PYTHON_BIN" -m openmc2donjon.cli prepare-openmc-sph-loop \
  --recipe "$SCRIPT_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$HANDOFF_RUN_DIR" \
  --solve-template "$SOLVE_TEMPLATE" \
  --format macrolib \
  --production \
  --require-std-dev-coverage \
  --scatter-row-balance-fail 1e-12 \
  --acceptance-require-mgxs-std-dev-coverage \
  --acceptance-require-reference-flux-std-dev \
  --acceptance-max-reference-flux-std-dev-rel 0.01 \
  --scalar-flux-map FUEL_A=2,MOD_A=4 \
  --case-id-prefix openmc_sph_loop_entrypoint \
  --stage-prefix odj_openmc_sph_loop_entrypoint \
  --case-dir openmc2donjon/case_runs/openmc_sph_loop_entrypoint \
  --sph-kind openmc-sph-loop-entrypoint \
  --source-label "OpenMC SPH loop entrypoint smoke" \
  --summary-json "$HANDOFF_SUMMARY" \
  --scaffold-summary-json "$SCAFFOLD_SUMMARY" \
  --bundle-dir "$BUNDLE_DIR" \
  --force

"$PYTHON_BIN" - "$MGXS" "$SCAFFOLD_DIR" "$SCAFFOLD_SUMMARY" "$HANDOFF_SUMMARY" "$RUN_SCRIPT" "$BUNDLE_DIR" "$EXPECTED_REFERENCE_FLUX" "$EXPECTED_REFERENCE_FLUX_STD_DEV" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import h5py
import numpy as np

from openmc2donjon.sph_loop_plan import build_sph_loop_plan


mgxs = Path(sys.argv[1])
scaffold = Path(sys.argv[2])
scaffold_summary = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
handoff_summary = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
run_script = Path(sys.argv[5])
bundle_dir = Path(sys.argv[6])
expected_reference_flux = np.asarray(json.loads(sys.argv[7]), dtype=float)
expected_reference_flux_std_dev = np.asarray(json.loads(sys.argv[8]), dtype=float)

with h5py.File(mgxs, "r") as h5:
    assert "openmc_volume_flux" in h5
    np.testing.assert_allclose(h5["openmc_volume_flux"][:], expected_reference_flux)
    np.testing.assert_allclose(
        h5["openmc_volume_flux_std_dev"][:],
        expected_reference_flux_std_dev,
    )
    assert h5["openmc_volume_flux"].attrs["group_order"] == "mgxs_donjon"
    assert h5["openmc_volume_flux_std_dev"].attrs["std_dev_of"] == "openmc_volume_flux"
    assert h5["openmc_volume_flux_std_dev"].attrs["group_order"] == "mgxs_donjon"
    assert "total_std_dev" in h5["mixtures/FUEL_A"]
    assert "scatter_matrix_std_dev" in h5["mixtures/FUEL_A"]
    assert "transport_total_std_dev" in h5["mixtures/MOD_A"]
    assert "fission_std_dev" not in h5["mixtures/MOD_A"]
    np.testing.assert_allclose(h5["mixtures/FUEL_A/kappa_fission"][:], [3.2e-12, 3.1e-12])

with h5py.File(scaffold / "reference_flux.h5", "r") as h5:
    np.testing.assert_allclose(h5["openmc_volume_flux"][:], expected_reference_flux)
    np.testing.assert_allclose(
        h5["openmc_volume_flux_std_dev"][:],
        expected_reference_flux_std_dev,
    )
    assert h5["openmc_volume_flux"].attrs["group_order"] == "mgxs_donjon"
    assert h5["openmc_volume_flux_std_dev"].attrs["std_dev_of"] == "openmc_volume_flux"

with h5py.File(scaffold / "flux_map.h5", "r") as h5:
    np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [2, 4])

config = json.loads((scaffold / "loop_config.json").read_text(encoding="utf-8"))
assert config["input_h5"] == str(mgxs)
assert config["map_h5"] == str(scaffold / "flux_map.h5")
assert config["run_script"] == str(run_script)
assert config["reference_flux"] == f"{scaffold / 'reference_flux.h5'}::openmc_volume_flux"
assert config["flux_normalization"] == "auto"
assert config["acceptance"]["preset"] == "production"
assert config["acceptance"]["require_mgxs_std_dev_coverage"] is True
assert config["acceptance"]["require_reference_flux_std_dev"] is True
assert config["acceptance"]["max_reference_flux_std_dev_rel"] == 0.01
assert "openmc2donjon.donjon_deck_runner" in config["solver"]["command"]
plan = build_sph_loop_plan(scaffold / "loop_config.json")
assert plan.normalized_acceptance["require_artifact_metadata_alignment"] is True
assert plan.normalized_acceptance["require_final_solve"] is True
assert scaffold_summary["decision"] == "openmc2donjon_sph_loop_scaffold_passed"
assert scaffold_summary["run_script"] == str(run_script)
assert scaffold_summary["run_command"][-2:] == ["--config", str(scaffold / "loop_config.json")]
assert handoff_summary["decision"] == "openmc2donjon_openmc_sph_loop_handoff_passed"
assert Path(handoff_summary["ascii_output"]).name == "out.macrolib.txt"
assert handoff_summary["run_script"] == str(run_script)
assert handoff_summary["bundle_manifest"] == str(bundle_dir / "manifest.json")
assert run_script.exists()
assert "run-sph-loop" in run_script.read_text(encoding="utf-8")
manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
for label in {
    "openmc-sph-loop-config",
    "openmc-sph-loop-flux-map",
    "openmc-sph-loop-reference-flux",
    "openmc-sph-loop-run-script",
    "openmc-sph-loop-summary",
    "openmc-sph-loop-solve-template",
}:
    assert label in labels, label
assert labels["openmc-sph-loop-config"]["bundled_path"] == "loop_config.json"
assert labels["openmc-sph-loop-run-script"]["bundled_path"] == "run_sph_loop.sh"
bundle_config = json.loads((bundle_dir / "loop_config.json").read_text(encoding="utf-8"))
assert bundle_config["input_h5"] == "mgxs_library.h5"
assert bundle_config["map_h5"] == "flux_map.h5"
assert bundle_config["reference_flux"] == "reference_flux.h5::openmc_volume_flux"
assert bundle_config["run_script"] == "run_sph_loop.sh"
assert bundle_config["flux_normalization"] == "auto"
assert bundle_config["acceptance"]["preset"] == "production"
assert bundle_config["acceptance"]["require_mgxs_std_dev_coverage"] is True
assert bundle_config["acceptance"]["require_reference_flux_std_dev"] is True
assert bundle_config["acceptance"]["max_reference_flux_std_dev_rel"] == 0.01
relocated = bundle_dir.parent / "relocated_bundle"
if relocated.exists():
    shutil.rmtree(relocated)
shutil.copytree(bundle_dir, relocated)
plan = build_sph_loop_plan(relocated / "loop_config.json")
assert plan.input_h5 == relocated / "mgxs_library.h5"
assert plan.map_h5 == relocated / "flux_map.h5"
assert plan.reference_flux == f"{relocated / 'reference_flux.h5'}::openmc_volume_flux"
assert plan.loop_dir == relocated / "sph_loop"
assert plan.run_script == relocated / "run_sph_loop.sh"
print(f"OpenMC SPH loop entrypoint OK: {scaffold}")
PY

if [[ "${RUN_REAL_DONJON:-0}" == "1" ]]; then
  REAL_SUMMARY="$HANDOFF_RUN_DIR/real_sph_loop_summary.json"
  REAL_BUNDLE_DIR="$HANDOFF_RUN_DIR/real_sph_loop_bundle"
  echo "== OpenMC SPH loop entrypoint real DONJON loop =="
  "$RUN_SCRIPT" \
    --summary-json "$REAL_SUMMARY" \
    --bundle-dir "$REAL_BUNDLE_DIR" \
    --force
  "$PYTHON_BIN" -m openmc2donjon.cli validate-bundle "$REAL_BUNDLE_DIR/manifest.json"

  "$PYTHON_BIN" - "$REAL_SUMMARY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np


summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert summary["decision"] == "openmc2donjon_sph_loop_passed"
assert summary["acceptance_passed"] is True
assert summary["completed_iterations"] == 2
assert summary["final_solve"]["iteration"] == 2
checks = {item["name"]: item for item in summary["acceptance"]["checks"]}
assert checks["require_artifact_metadata_alignment"]["passed"] is True
assert checks["require_mgxs_std_dev_coverage"]["passed"] is True
assert checks["require_reference_flux_std_dev"]["passed"] is True
assert checks["max_reference_flux_std_dev_rel"]["passed"] is True
assert checks["max_final_clipped_count"]["passed"] is True
metadata = summary["artifact_metadata"]
assert metadata["reference_flux"]["group_order"] == "mgxs_donjon"
assert metadata["reference_flux"]["std_dev_dataset"] == "openmc_volume_flux_std_dev"
assert abs(metadata["reference_flux"]["std_dev_max_rel"] - 0.001) < 1.0e-15
for workflow in metadata["workflows"]:
    assert workflow["donjon_volume_flux"]["group_order"] == "mgxs_donjon"
    assert workflow["sph_sidecar"]["group_order"] == "mgxs_donjon"
with h5py.File(summary["final_sph_sidecar"], "r") as h5:
    sph = h5["sph"][:]
    assert h5.attrs["sph_kind"] == "openmc-sph-loop-entrypoint-iter2"
np.testing.assert_allclose(sph, np.ones_like(sph), rtol=1.0e-3, atol=1.0e-3)
print(f"OpenMC SPH loop entrypoint real DONJON loop OK: {sys.argv[1]}")
PY
fi

echo "openmc2donjon OpenMC SPH loop entrypoint smoke: PASS"

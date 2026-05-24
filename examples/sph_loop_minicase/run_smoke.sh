#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_sph_loop_minicase}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

CASE_DIR="$RUN_DIR/case"
MGXS="$CASE_DIR/inputs/mgxs_library.h5"
CONFIG="$CASE_DIR/loop_config.json"
REAL_CONFIG="$CASE_DIR/real_loop_config.json"
EXPECTED="$CASE_DIR/expected_sph.h5"
SUMMARY="$CASE_DIR/sph_loop/sph_loop_summary.json"
BUNDLE_DIR="$CASE_DIR/sph_loop/bundle"
SOLVE_TEMPLATE="$SCRIPT_DIR/templates/solve_lflux_dump.x2m.in"

echo "== openmc2donjon minimal SPH loop minicase =="

"$PYTHON_BIN" "$SCRIPT_DIR/make_inputs.py" \
  --output-dir "$CASE_DIR" \
  --config "$CONFIG" \
  --driver "$SCRIPT_DIR/fake_low_order_solver.py" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --require-std-dev-coverage \
  --scatter-row-balance-fail 1e-12

"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$CONFIG" \
  --summary-json "$SUMMARY" \
  --bundle-dir "$BUNDLE_DIR" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli validate-bundle "$BUNDLE_DIR/manifest.json"

"$PYTHON_BIN" "$SCRIPT_DIR/make_real_config.py" \
  --output "$REAL_CONFIG" \
  --output-dir "$CASE_DIR/sph_loop_real" \
  --mgxs "$MGXS" \
  --reference-flux "$CASE_DIR/inputs/reference_flux.h5" \
  --flux-map "$CASE_DIR/inputs/flux_map.h5" \
  --solve-template "$SOLVE_TEMPLATE" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" - "$REAL_CONFIG" "$SOLVE_TEMPLATE" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys


config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
solve_template = Path(sys.argv[2])
solver = config["solver"]["command"]
postprocess = config["postprocess"]["command"]
assert config["schema"] == "openmc2donjon.sph-loop-config.v1"
assert config["sph_kind"] == "sph-loop-minicase-donjon"
assert config["acceptance"]["require_mgxs_std_dev_coverage"] is True
assert config["acceptance"]["require_reference_flux_std_dev"] is True
assert config["acceptance"]["max_reference_flux_std_dev_rel"] == 1.0e-2
assert "-m" in solver
assert "openmc2donjon.donjon_deck_runner" in solver
assert "openmc2donjon.donjon_deck_runner" in postprocess
assert str(solve_template) in solver
assert any(part.startswith("/tmp/odj_sph_loop_minicase") for part in solver)
assert "{ascii_input}" in solver
assert "{result}" in solver
assert "{workflow_ascii}" in postprocess
assert "{output}" in postprocess
print(f"SPH loop minicase DONJON config OK: {Path(sys.argv[1])}")
PY

DRY_ROOT="$CASE_DIR/donjon_root_dry"
DRY_STAGE="$CASE_DIR/donjon_runner_dry/stage"
DRY_SOLVE_CASE="sph_loop_minicase_solve_dry"
DRY_APPLY_CASE="sph_loop_minicase_apply_dry"
DRY_SOLVE_DECK="$DRY_ROOT/data/openmc2donjon/case_runs/sph_loop_minicase/$DRY_SOLVE_CASE.x2m"
DRY_APPLY_DECK="$DRY_ROOT/data/openmc2donjon/case_runs/sph_loop_minicase/$DRY_APPLY_CASE.x2m"

"$PYTHON_BIN" -m openmc2donjon.donjon_deck_runner solve \
  --dry-run \
  --donjon-root "$DRY_ROOT" \
  --deck-template "$SOLVE_TEMPLATE" \
  --macrolib "$CASE_DIR/sph_loop/iter00_initial/out.macrolib.txt" \
  --result "$CASE_DIR/donjon_runner_dry/solve.result" \
  --iteration 0 \
  --case-id "$DRY_SOLVE_CASE" \
  --case-dir "openmc2donjon/case_runs/sph_loop_minicase" \
  --work-dir "$DRY_STAGE/solve"

"$PYTHON_BIN" -m openmc2donjon.donjon_deck_runner apply \
  --dry-run \
  --donjon-root "$DRY_ROOT" \
  --deck-template "$PACKAGE_SRC/openmc2donjon/templates/apply_nsph_mac.x2m.in" \
  --macrolib "$CASE_DIR/sph_loop/iter02_sph/corrected.macrolib.txt" \
  --output "$CASE_DIR/donjon_runner_dry/corrected.macrolib.txt" \
  --iteration 2 \
  --case-id "$DRY_APPLY_CASE" \
  --case-dir "openmc2donjon/case_runs/sph_loop_minicase" \
  --work-dir "$DRY_STAGE/apply"

"$PYTHON_BIN" - "$DRY_SOLVE_DECK" "$DRY_APPLY_DECK" "$DRY_STAGE" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys


solve_deck = Path(sys.argv[1])
apply_deck = Path(sys.argv[2])
stage = Path(sys.argv[3])
assert solve_deck.exists()
assert apply_deck.exists()
assert (stage / "solve/input.macrolib.txt").exists()
assert (stage / "apply/input.macrolib.txt").exists()
solve_text = solve_deck.read_text(encoding="utf-8")
apply_text = apply_deck.read_text(encoding="utf-8")
assert "TRIVAA:" in solve_text
assert "FLUD:" in solve_text
assert "UTL: FLUX :: IMPR STATE-VECTOR * DUMP ;" in solve_text
assert "DSPH:" in apply_text
assert "MAC:" in apply_text
print(f"SPH loop minicase DONJON runner dry-run OK: {solve_deck}")
PY

"$PYTHON_BIN" - "$SUMMARY" "$EXPECTED" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii


summary_path = Path(sys.argv[1])
expected_path = Path(sys.argv[2])
summary = json.loads(summary_path.read_text(encoding="utf-8"))

assert summary["decision"] == "openmc2donjon_sph_loop_passed"
assert summary["acceptance_passed"] is True
assert summary["converged"] is True
assert summary["completed_iterations"] == 2
assert len(summary["solves"]) == 3
assert len(summary["workflows"]) == 2
assert len(summary["postprocesses"]) == 2
assert summary["final_solve"]["iteration"] == 2
assert summary["final_ascii"].endswith("corrected.macrolib.txt")

checks = {item["name"]: item for item in summary["acceptance"]["checks"]}
assert checks["require_artifact_metadata_alignment"]["passed"] is True
assert checks["require_mgxs_std_dev_coverage"]["passed"] is True
assert checks["require_reference_flux_std_dev"]["passed"] is True
assert checks["max_reference_flux_std_dev_rel"]["passed"] is True
assert abs(checks["max_reference_flux_std_dev_rel"]["actual"] - 1.0e-3) < 1.0e-15
assert summary["flux_map_preflight"]["mgxs_std_dev_datasets"] == 12
assert summary["flux_map_preflight"]["mgxs_std_dev_expected_datasets"] == 12
metadata = summary["artifact_metadata"]
assert metadata["reference_flux"]["group_order"] == "mgxs_donjon"
assert metadata["reference_flux"]["mixture_names"] == ["FUEL_ASM", "REFL_ASM"]
assert metadata["reference_flux"]["std_dev_dataset"] == "openmc_volume_flux_std_dev"
assert abs(metadata["reference_flux"]["std_dev_max_rel"] - 1.0e-3) < 1.0e-15
for workflow in metadata["workflows"]:
    assert workflow["donjon_volume_flux"]["group_order"] == "mgxs_donjon"
    assert workflow["donjon_volume_flux"]["mixture_names"] == ["FUEL_ASM", "REFL_ASM"]
    assert workflow["sph_sidecar"]["group_order"] == "mgxs_donjon"
    assert workflow["sph_sidecar"]["mixture_names"] == ["FUEL_ASM", "REFL_ASM"]
assert metadata["final_sph_sidecar"]["group_order"] == "mgxs_donjon"

with h5py.File(expected_path, "r") as h5:
    expected_sph = h5["expected_sph"][:]

with h5py.File(summary["final_sph_sidecar"], "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected_sph)
    assert h5.attrs["sph_kind"] == "sph-loop-minicase-iter2"

macrolib = read_macrolib_ascii(summary["final_ascii"])
np.testing.assert_allclose(macrolib.sph, expected_sph)

print(
    "SPH loop minicase OK: "
    f"final_sph={float(expected_sph[0, 0]):.8g} "
    f"summary={summary_path}"
)
PY

echo "openmc2donjon minimal SPH loop minicase: PASS"

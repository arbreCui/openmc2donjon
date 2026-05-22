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
SOLVE_TEMPLATE="$REPO_ROOT/examples/sph_loop_minicase/templates/solve_lflux_dump.x2m.in"

echo "== openmc2donjon OpenMC SPH loop entrypoint smoke =="
mkdir -p "$CASE_DIR"
printf "fake statepoint for openmc sph loop entrypoint\n" > "$STATEPOINT"

"$PYTHON_BIN" -m openmc2donjon.cli prepare-openmc-sph-loop \
  --recipe "$SCRIPT_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$HANDOFF_RUN_DIR" \
  --solve-template "$SOLVE_TEMPLATE" \
  --format macrolib \
  --scatter-row-balance-fail 1e-12 \
  --scalar-flux-map FUEL_A=2,MOD_A=4 \
  --case-id-prefix openmc_sph_loop_entrypoint \
  --stage-prefix odj_openmc_sph_loop_entrypoint \
  --case-dir openmc2donjon/case_runs/openmc_sph_loop_entrypoint \
  --sph-kind openmc-sph-loop-entrypoint \
  --source-label "OpenMC SPH loop entrypoint smoke" \
  --summary-json "$HANDOFF_SUMMARY" \
  --scaffold-summary-json "$SCAFFOLD_SUMMARY" \
  --force

"$PYTHON_BIN" - "$MGXS" "$SCAFFOLD_DIR" "$SCAFFOLD_SUMMARY" "$HANDOFF_SUMMARY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np


mgxs = Path(sys.argv[1])
scaffold = Path(sys.argv[2])
scaffold_summary = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
handoff_summary = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))

with h5py.File(mgxs, "r") as h5:
    assert "openmc_volume_flux" in h5
    np.testing.assert_allclose(h5["openmc_volume_flux"][:], [[80.0, 800.0], [120.0, 600.0]])

with h5py.File(scaffold / "reference_flux.h5", "r") as h5:
    np.testing.assert_allclose(h5["openmc_volume_flux"][:], [[80.0, 800.0], [120.0, 600.0]])

with h5py.File(scaffold / "flux_map.h5", "r") as h5:
    np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [2, 4])

config = json.loads((scaffold / "loop_config.json").read_text(encoding="utf-8"))
assert config["input_h5"] == str(mgxs)
assert config["map_h5"] == str(scaffold / "flux_map.h5")
assert config["reference_flux"] == f"{scaffold / 'reference_flux.h5'}::openmc_volume_flux"
assert "openmc2donjon.donjon_deck_runner" in config["solver"]["command"]
assert scaffold_summary["decision"] == "openmc2donjon_sph_loop_scaffold_passed"
assert handoff_summary["decision"] == "openmc2donjon_openmc_sph_loop_handoff_passed"
assert Path(handoff_summary["ascii_output"]).name == "out.macrolib.txt"
print(f"OpenMC SPH loop entrypoint OK: {scaffold}")
PY

echo "openmc2donjon OpenMC SPH loop entrypoint smoke: PASS"

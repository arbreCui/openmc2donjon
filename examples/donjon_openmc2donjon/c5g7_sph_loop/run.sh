#!/usr/bin/env bash
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$EXAMPLE_DIR/../../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_sph_loop_example}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
C5G7_ACCEPTED_H5="${C5G7_ACCEPTED_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5}"
C5G7_REFERENCE_FLUX_H5="${C5G7_REFERENCE_FLUX_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_homogeneous_face_flux_donjon.h5}"
SPH_DAMPING="${SPH_DAMPING:-0.1}"
RUN_TAG="${RUN_TAG:-c5g7_fixed_openmc_sph_loop_example}"

CONFIG="$RUN_DIR/c5g7_sph_loop_config.json"
LOOP_DIR="$RUN_DIR/sph_loop"
SUMMARY="$LOOP_DIR/sph_loop_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -x "$DONJON_ROOT/rdonjon" ]]; then
  echo "missing DONJON runner: $DONJON_ROOT/rdonjon" >&2
  exit 1
fi

"$PYTHON_BIN" "$EXAMPLE_DIR/make_config.py" \
  --output "$CONFIG" \
  --output-dir "$LOOP_DIR" \
  --mgxs "$C5G7_ACCEPTED_H5" \
  --reference-flux "$C5G7_REFERENCE_FLUX_H5" \
  --donjon-root "$DONJON_ROOT" \
  --python-bin "$PYTHON_BIN" \
  --damping "$SPH_DAMPING" \
  --run-tag "$RUN_TAG"

"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$CONFIG" \
  --summary-json "$SUMMARY" \
  --force

"$PYTHON_BIN" - "$SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(
    "C5G7 SPH loop example OK: "
    f"solves={len(summary['solves'])} "
    f"postprocesses={len(summary['postprocesses'])} "
    f"final_ascii={summary['final_ascii']}"
)
PY

#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_openmc_full_core_production_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"
RUN_REAL_DONJON="${RUN_REAL_DONJON:-0}"

echo "== openmc2donjon OpenMC full-core production smoke gate =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "run_real_donjon: $RUN_REAL_DONJON"

RUN_DIR="$RUN_DIR" \
PYTHON_BIN="$PYTHON_BIN" \
RUN_REAL_DONJON="$RUN_REAL_DONJON" \
  bash "$REPO_ROOT/examples/openmc_full_core_minicase/run_smoke.sh"

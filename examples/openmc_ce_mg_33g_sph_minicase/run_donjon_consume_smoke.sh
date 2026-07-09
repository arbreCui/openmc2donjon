#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ROOT="${RUN_ROOT:-/private/tmp/openmc2donjon_ce_mg_sph_production_fixed_20260709}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc_ce_mg_33g_sph_donjon_consume_smoke}"
RUN_TAG="${RUN_TAG:-openmc_ce_mg_33g_sph_macrolib_donjon_smoke}"
MACROLIB_ASCII="${MACROLIB_ASCII:-$RUN_ROOT/handoff/out_with_openmc_sph.macrolib.txt}"

if [[ ! -f "$MACROLIB_ASCII" ]]; then
  echo "OpenMC CE/MG SPH MACROLIB not found:"
  echo "  $MACROLIB_ASCII"
  echo
  echo "Run the minicase workflow first, for example:"
  echo "  RUN_ROOT=$RUN_ROOT bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh"
  exit 1
fi

echo "== OpenMC CE/MG SPH -> DONJON NSPH consumption smoke =="
echo "run_root: $RUN_ROOT"
echo "macrolib: $MACROLIB_ASCII"
echo "run_dir:  $RUN_DIR"
echo "run_tag:  $RUN_TAG"
echo

RUN_DIR="$RUN_DIR" \
RUN_TAG="$RUN_TAG" \
MACROLIB_ASCII="$MACROLIB_ASCII" \
  bash "$REPO_ROOT/scripts/run_donjon_sph_consume_smoke.sh"

echo
echo "DONJON result listing:"
echo "  /Users/wen/dragon-5.1/Donjon/Darwin_arm64/${RUN_TAG}.result"

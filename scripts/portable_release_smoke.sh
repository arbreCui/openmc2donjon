#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_portable_release_smoke}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_TESTS=0

usage() {
  cat <<'EOF'
usage: scripts/portable_release_smoke.sh [--with-tests]

Run the portable release smoke suite.

This gate is intentionally fixture-backed and CI-friendly:
  - no local OpenMC executable or cross-section library required;
  - no local DRAGON/DONJON checkout required;
  - no PyGan installation required.

It proves the converter-facing handoff mechanics are healthy. It is not a
substitute for the local physics release gate (`scripts/release_check.sh`),
which can also run OpenMC/DONJON/PyGan-dependent checks.

Options:
  --with-tests  run the Python unit tests before the portable smokes

Environment:
  OPENMC2DONJON_SRC  default src
  PYTHON_BIN         default python3
  RUN_DIR            default /private/tmp/openmc2donjon_portable_release_smoke
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-tests)
      RUN_TESTS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_executable() {
  local exe="$1"
  if [[ "$exe" == */* ]]; then
    if [[ ! -x "$exe" ]]; then
      echo "missing executable: $exe" >&2
      exit 1
    fi
  elif ! command -v "$exe" >/dev/null 2>&1; then
    echo "missing executable on PATH: $exe" >&2
    exit 1
  fi
}

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon portable release smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

require_executable "$PYTHON_BIN"

if [[ "$RUN_TESTS" -eq 1 ]]; then
  echo
  echo "== Python unit tests =="
  "$PYTHON_BIN" -m unittest discover -s "$REPO_ROOT/tests"
fi

echo
echo "== CLI entrypoint smoke =="
"$PYTHON_BIN" -m openmc2donjon.cli --version
"$PYTHON_BIN" -m openmc2donjon.cli --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli check --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph --help >/dev/null
"$PYTHON_BIN" -m openmc2donjon.export_cli --version
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli --version

echo
echo "== Energy mesh contract smoke =="
RUN_DIR="$RUN_DIR/energy_mesh_contract" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_energy_mesh_contract_smoke.sh"

echo
echo "== Recipe export smoke =="
RUN_DIR="$RUN_DIR/recipe_export_smoke" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_recipe_export_smoke.sh"

echo
echo "== OpenMC CE/MG SPH sidecar smoke =="
RUN_DIR="$RUN_DIR/openmc_sph_sidecar_minicase" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/openmc_sph_sidecar_minicase/run_smoke.sh"

echo
echo "== External SPH handoff smoke =="
RUN_DIR="$RUN_DIR/external_sph_handoff" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/external_sph_handoff/run_smoke.sh"

echo
echo "== External face-flux adapter smoke =="
RUN_DIR="$RUN_DIR/external_face_flux_adapter" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/examples/external_face_flux_adapter/run_smoke.sh"

echo
echo "== C5G7 converter fixture smoke =="
RUN_DIR="$RUN_DIR/c5g7_demo" \
PYTHON_BIN="$PYTHON_BIN" \
  bash "$REPO_ROOT/scripts/run_c5g7_demo.sh" --skip-tests

echo
echo "openmc2donjon portable release smoke: PASS"

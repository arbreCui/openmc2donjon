#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE_DIR="$REPO_ROOT/examples/irena30_zrefl_hex"
DRAGON_ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
DONJON_DIR="$DRAGON_ROOT/Donjon"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
IRENA30_DIR="${IRENA30_DIR:-/Users/wen/openmc-workspace/irena}"
IRENA30_MACROLIB="${IRENA30_MACROLIB:-$IRENA30_DIR/build/macrolib.h5}"
RUN_BASE="${RUN_BASE:-$DONJON_DIR/data/openmc2donjon/irena30_zrefl_keff_runs}"
# DONJON SEQ_ASCII paths are limited to 72 characters; keep the staged
# multicompo on a short absolute path.
SHORT_BASE="${SHORT_BASE:-/private/tmp/o2d_irena30}"
PYTHON_BIN="${PYTHON_BIN:-}"
OPENMC_EXEC="${OPENMC_EXEC:-}"
OPENMC_THREADS="${OPENMC_THREADS:-8}"
IRENA_PARTICLES="${IRENA_PARTICLES:-50000}"
IRENA_BATCHES="${IRENA_BATCHES:-130}"
IRENA_INACTIVE="${IRENA_INACTIVE:-30}"
IRENA_SEED="${IRENA_SEED:-47}"
MAX_DELTA_PCM="${OPENMC2DONJON_IRENA_MAX_DELTA_PCM:-300}"

usage() {
  cat <<'EOF'
usage: run_zrefl_keff.sh

Run the IRENA-30 91-hex 2D ARI ZREFL case in OpenMC multi-group mode with
per-position MGXS tallies, export the statepoint to L_MULTICOMPO, consume it
through DONJON NCR: + SNT: SN8 transport (primary) and TRIVAC MCFD diffusion
(diagnostic), and compare k-effective against the paired OpenMC run.

Environment overrides:
  IRENA30_DIR                       default /Users/wen/openmc-workspace/irena
  IRENA30_MACROLIB                  default $IRENA30_DIR/build/macrolib.h5
  OPENMC2DONJON_ROOT                default /Users/wen/dragon-5.1
  RUN_BASE                          default $DONJON_DIR/data/openmc2donjon/irena30_zrefl_keff_runs
  IRENA_PARTICLES/BATCHES/INACTIVE  default 50000/130/30
  IRENA_SEED                        default 47 (change for robustness runs)
  OPENMC_THREADS                    default 8
  OPENMC2DONJON_IRENA_MAX_DELTA_PCM default 300 (applies to the SN8 result)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

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
  else
    OPENMC_EXEC="$(command -v openmc || true)"
  fi
fi

require_path() {
  if [[ ! -e "$1" ]]; then
    echo "missing required path: $1" >&2
    exit 1
  fi
}

require_path "$PYTHON_BIN"
require_path "$IRENA30_DIR/geometry_91hex.py"
require_path "$IRENA30_MACROLIB"
require_path "$DONJON_DIR/rdonjon"
if [[ -z "$OPENMC_EXEC" ]]; then
  echo "OpenMC executable not found" >&2
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$RUN_BASE/$stamp"
CASE_DIR="$RUN_DIR/openmc_case"
CONVERT_DIR="$RUN_DIR/openmc2donjon_run"
DECK_DIR="$RUN_DIR/donjon"
SHORT_DIR="$SHORT_BASE/$stamp"
mkdir -p "$CASE_DIR" "$CONVERT_DIR" "$DECK_DIR" "$SHORT_DIR"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"
export IRENA30_DIR IRENA30_MACROLIB

echo "== IRENA-30 ZREFL hex k-eff comparison =="
echo "run_dir: $RUN_DIR"
echo "particles/batches/inactive/seed: $IRENA_PARTICLES/$IRENA_BATCHES/$IRENA_INACTIVE/$IRENA_SEED"

echo
echo "== Build OpenMC XML =="
"$PYTHON_BIN" "$EXAMPLE_DIR/irena_model.py" \
  --case-dir "$CASE_DIR" \
  --particles "$IRENA_PARTICLES" \
  --batches "$IRENA_BATCHES" \
  --inactive "$IRENA_INACTIVE" \
  --seed "$IRENA_SEED"

echo
echo "== Run OpenMC (multi-group) =="
( cd "$CASE_DIR" && "$OPENMC_EXEC" -s "$OPENMC_THREADS" )
STATEPOINT="$CASE_DIR/statepoint.${IRENA_BATCHES}.h5"
require_path "$STATEPOINT"

echo
echo "== Export statepoint (HDF5 only; conversion happens after the fill) =="
MGXS="$CONVERT_DIR/mgxs_library.h5"
OPENMC2DONJON_IRENA_ZREFL_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  -o "$MGXS"
require_path "$MGXS"

echo
echo "== Fill zero-flux thermal groups from the MG macrolib =="
"$PYTHON_BIN" -m openmc2donjon.cli fill-zero-flux "$MGXS" \
  --macrolib "$IRENA30_MACROLIB" \
  --in-place

echo
echo "== Checked conversion to L_MULTICOMPO =="
MCO="$CONVERT_DIR/irena_zrefl.mcompo.txt"
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" -o "$MCO" --overwrite --check
SHORT_MCO="$SHORT_DIR/out.mcompo.txt"
cp "$MCO" "$SHORT_MCO"

echo
echo "== Write DONJON decks =="
EDI_ASC="$SHORT_DIR/edi.txt"
"$PYTHON_BIN" "$EXAMPLE_DIR/write_donjon_decks.py" \
  --mco "$SHORT_MCO" \
  --edi "$EDI_ASC" \
  --deck-dir "$DECK_DIR" \
  --stamp "$stamp"

run_donjon_deck() {
  local deck="$1"
  local stem
  stem="$(basename "$deck" .x2m)"
  local result="$DONJON_DIR/Darwin_arm64/$stem.result"
  rm -f "$result"
  echo
  echo "== Run DONJON: $stem =="
  ( cd "$DONJON_DIR" && ./rdonjon -q "${deck#"$DONJON_DIR/data/"}" )
  require_path "$result"
  if ! grep -aqi "normal end of execution" "$result"; then
    echo "DONJON listing did not reach normal end: $result" >&2
    exit 1
  fi
}

SN8_DECK="$DECK_DIR/irena30_zrefl_sn8_${stamp}.x2m"
MCFD_DECK="$DECK_DIR/irena30_zrefl_mcfd_${stamp}.x2m"
run_donjon_deck "$SN8_DECK"
run_donjon_deck "$MCFD_DECK"

echo
echo "== Compare k-effective =="
"$PYTHON_BIN" "$EXAMPLE_DIR/compare_keff.py" \
  --statepoint "$STATEPOINT" \
  --sn8-result "$DONJON_DIR/Darwin_arm64/$(basename "$SN8_DECK" .x2m).result" \
  --mcfd-result "$DONJON_DIR/Darwin_arm64/$(basename "$MCFD_DECK" .x2m).result" \
  --multicompo "$MCO" \
  --max-delta-pcm "$MAX_DELTA_PCM" \
  --summary "$RUN_DIR/keff_comparison.json"

echo
echo "== Compare per-position fission rates (power shape) =="
"$PYTHON_BIN" "$EXAMPLE_DIR/extract_openmc_fission.py" \
  --case-dir "$CASE_DIR" \
  --statepoint "$STATEPOINT" \
  --output "$RUN_DIR/openmc_fission_rates.json"
"$PYTHON_BIN" "$EXAMPLE_DIR/compare_power.py" \
  --openmc-fission "$RUN_DIR/openmc_fission_rates.json" \
  --edi "$EDI_ASC" \
  --max-rel "${OPENMC2DONJON_IRENA_POWER_MAX_REL:-0.02}" \
  --max-rms "${OPENMC2DONJON_IRENA_POWER_MAX_RMS:-0.01}" \
  --summary "$RUN_DIR/power_comparison.json"

echo
echo "IRENA-30 ZREFL hex k-eff + power-shape comparison: PASS"

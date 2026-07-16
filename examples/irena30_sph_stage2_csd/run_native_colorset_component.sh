#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE_DIR="$REPO_ROOT/examples/irena30_sph_stage2_csd"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OPENMC_EXEC="${OPENMC_EXEC:-openmc}"
DONJON_DIR="${DONJON_DIR:-}"
if [[ -z "$DONJON_DIR" && -n "${OPENMC2DONJON_ROOT:-}" ]]; then
  DONJON_DIR="$OPENMC2DONJON_ROOT/Donjon"
fi
: "${DONJON_DIR:?Set DONJON_DIR or OPENMC2DONJON_ROOT for the external DONJON checkout}"
[[ -x "$DONJON_DIR/rdonjon" ]] || {
  echo "missing DONJON runner: $DONJON_DIR/rdonjon" >&2
  exit 2
}
DONJON_PLATFORM="${DONJON_PLATFORM:-$(uname -sm | tr ' ' '_')}"
DONJON_RESULT_DIR="${DONJON_RESULT_DIR:-$DONJON_DIR/$DONJON_PLATFORM}"
CASE="${1:-${IRENA_SPH2_CASE:-pnl_ext}}"

SIGNATURE_MODE=0
if [[ -n "${IRENA_SPH2_CENTER_KIND:-}" || -n "${IRENA_SPH2_NEIGHBOR_KINDS:-}" ]]; then
  [[ -n "${IRENA_SPH2_CENTER_KIND:-}" && -n "${IRENA_SPH2_NEIGHBOR_KINDS:-}" ]] || {
    echo "center and six-neighbor declarations must be provided together" >&2
    exit 2
  }
  SIGNATURE_MODE=1
  TARGET="$(printf '%s' "$IRENA_SPH2_CENTER_KIND" | tr '[:lower:]' '[:upper:]')"
  NEIGHBOR_DECLARATION="$(
    printf '%s' "$IRENA_SPH2_NEIGHBOR_KINDS" | tr '[:lower:]' '[:upper:]'
  )"
  IFS=',' read -r -a NEIGHBOR_KINDS <<<"$NEIGHBOR_DECLARATION"
  [[ "${#NEIGHBOR_KINDS[@]}" -eq 6 ]] || {
    echo "IRENA_SPH2_NEIGHBOR_KINDS must contain six entries" >&2
    exit 2
  }
  MIX_MAP="1"
  NEXT_MIX=2
  for kind in "${NEIGHBOR_KINDS[@]}"; do
    if [[ "$kind" == "OUT" ]]; then
      MIX_MAP+=",0"
    else
      MIX_MAP+=",$NEXT_MIX"
      NEXT_MIX=$((NEXT_MIX + 1))
    fi
  done
  NEIGHBOR="$NEIGHBOR_DECLARATION"
else
  case "$CASE" in
    int_ext) TARGET="INT"; NEIGHBOR="EXT" ;;
    ext_int) TARGET="EXT"; NEIGHBOR="INT" ;;
    csd_int) TARGET="CSD"; NEIGHBOR="INT" ;;
    dsdf_int) TARGET="DSDF"; NEIGHBOR="INT" ;;
    pnl_ext) TARGET="PNL"; NEIGHBOR="EXT" ;;
    *) echo "unsupported IRENA colorset or undeclared signature: $CASE" >&2; exit 2 ;;
  esac
  NEIGHBOR_KINDS=("$NEIGHBOR" "$NEIGHBOR" "$NEIGHBOR" "$NEIGHBOR" "$NEIGHBOR" "$NEIGHBOR")
  MIX_MAP="1,2,3,4,5,6,7"
fi

RUN_ROOT="${RUN_ROOT:-$REPO_ROOT/.openmc2donjon-runs/irena_${CASE}_anl24c20_native_physical}"
BATCHES="${BATCHES:-60}"
INACTIVE="${INACTIVE:-20}"
PARTICLES="${PARTICLES:-40000}"
OPENMC_THREADS="${OPENMC_THREADS:-8}"
REUSE_CE="${REUSE_CE:-0}"
MAX_OUTSIDE_FRACTION="${MAX_OUTSIDE_FRACTION:-0.005}"
NODE_SIDE_CM="${IRENA_SPH2_NODE_SIDE_CM:-10.1036}"
SCATTER_MOMENTS="${IRENA_SPH2_SCATTER_MOMENTS:-2}"
SN_ACCELERATION="${IRENA_SPH2_SN_ACCELERATION:-livolant}"
SN_INNER_ITERATIONS="${IRENA_SPH2_SN_INNER_ITERATIONS:-1000}"
SN_INNER_EPSILON="${IRENA_SPH2_SN_INNER_EPSILON:-1.0E-8}"

CE_DIR="$RUN_ROOT/ce_case"
HANDOFF="$RUN_ROOT/handoff"
STATEPOINT="$CE_DIR/statepoint.$BATCHES.h5"
RAW_H5="$HANDOFF/mgxs_library.h5"
COMPONENT_H5="$HANDOFF/mgxs_components.h5"
REFERENCE="$HANDOFF/reference_24g_p3.macrolib.txt"
SPH_MACROLIB="$HANDOFF/native_sph_24g_p3.macrolib.txt"
VERIFY_MACROLIB="$HANDOFF/donjon_verify_24g_p3.macrolib.txt"
RESULT="$HANDOFF/native_sph_donjon.result"
SUMMARY="$HANDOFF/physics_summary.json"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT/src:$EXAMPLE_DIR${PYTHONPATH:+:$PYTHONPATH}"
export IRENA_SPH2_CASE="$CASE"
export IRENA_SPH2_ENERGY_MESH_ID="anl_24c_20mev"
export IRENA_SPH2_NODE_SIDE_CM="$NODE_SIDE_CM"

mkdir -p "$HANDOFF"
echo "== IRENA $CASE: OpenMC fine -> Converter -> DRAGON native SPH =="
echo "target=$TARGET neighbors=$NEIGHBOR run=$RUN_ROOT"
echo "declared downstream node side=$NODE_SIDE_CM cm (catch-all sodium included)"
echo "DRAGON scattering moments=$SCATTER_MOMENTS (IRENA accepted baseline uses P0+P1)"
echo "forbidden: ADF, empirical multiplier, clipping, frozen group, flux floor, zero-bin fill"

if [[ "$REUSE_CE" != "1" ]]; then
  : "${IRENA_CE_COMPARE_DIR:?Set IRENA_CE_COMPARE_DIR to the external IRENA ce_compare input directory}"
  : "${OPENMC_CROSS_SECTIONS:?Set OPENMC_CROSS_SECTIONS to the OpenMC cross_sections.xml file}"
  export IRENA_CE_COMPARE_DIR OPENMC_CROSS_SECTIONS
  "$PYTHON_BIN" "$EXAMPLE_DIR/build_ce_case.py" \
    --case-dir "$CE_DIR" --batches "$BATCHES" --inactive "$INACTIVE" \
    --particles "$PARTICLES"
  (cd "$CE_DIR" && "$OPENMC_EXEC" -s "$OPENMC_THREADS")

  "$PYTHON_BIN" "$EXAMPLE_DIR/evaluate_energy_coverage.py" "$STATEPOINT" \
    --max-outside-fraction "$MAX_OUTSIDE_FRACTION" \
    --summary-json "$HANDOFF/energy_coverage_summary.json"

  OPENMC2DONJON_IRENA_SPH2_DIR="$CE_DIR" \
  "$PYTHON_BIN" -m openmc2donjon.export_cli \
    --recipe "$EXAMPLE_DIR/export_recipe.py" --statepoint "$STATEPOINT" -o "$RAW_H5"
else
  for required in "$STATEPOINT" "$RAW_H5" "$HANDOFF/energy_coverage_summary.json"; do
    [[ -f "$required" ]] || { echo "REUSE_CE=1 missing $required" >&2; exit 4; }
  done
fi

if [[ "$SIGNATURE_MODE" == "1" ]]; then
  # Preserve every active local position.  Native SPH is solved on the exact
  # declared signature; no directional neighbor is averaged into another.
  cp "$RAW_H5" "$COMPONENT_H5"
else
  GROUP_ARGS=(--group "$TARGET=${TARGET}_C")
  NEIGHBOR_MEMBERS=""
  for index in 1 2 3 4 5 6; do
    [[ -n "$NEIGHBOR_MEMBERS" ]] && NEIGHBOR_MEMBERS+=","
    NEIGHBOR_MEMBERS+="${NEIGHBOR}_N${index}"
  done
  GROUP_ARGS+=(--group "$NEIGHBOR=$NEIGHBOR_MEMBERS")
  "$PYTHON_BIN" -m openmc2donjon.mixture_collapse "$RAW_H5" \
    -o "$COMPONENT_H5" "${GROUP_ARGS[@]}" \
    --summary-json "$HANDOFF/component_collapse_summary.json" --force
fi

"$PYTHON_BIN" -m openmc2donjon.cli "$COMPONENT_H5" \
  --format macrolib --max-scatter-order 3 -o "$REFERENCE" \
  --production --summary-json "$HANDOFF/converter_summary.json" --overwrite

SHORT_DIR="${TMPDIR:-/tmp}/o2d_${CASE}_native"
mkdir -p "$SHORT_DIR"
SHORT_REF="$SHORT_DIR/reference.macrolib.txt"
SHORT_SPH="$SHORT_DIR/native_sph.macrolib.txt"
SHORT_VERIFY="$SHORT_DIR/verify.macrolib.txt"
cp "$REFERENCE" "$SHORT_REF"

DECK_DIR="$DONJON_DIR/data/openmc2donjon/irena_native_components"
mkdir -p "$DECK_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DECK="$DECK_DIR/irena_${CASE}_native_sph_${STAMP}.x2m"
"$PYTHON_BIN" "$EXAMPLE_DIR/write_native_sph_deck.py" \
  --case "$CASE" --reference "$SHORT_REF" --sph-output "$SHORT_SPH" \
  --verify-output "$SHORT_VERIFY" --output "$DECK" --side "$NODE_SIDE_CM" \
  --scatter-moments "$SCATTER_MOMENTS" --mix-map "$MIX_MAP" \
  --sn-acceleration "$SN_ACCELERATION" \
  --sn-inner-iterations "$SN_INNER_ITERATIONS" \
  --sn-inner-epsilon "$SN_INNER_EPSILON"

STEM="$(basename "$DECK" .x2m)"
DONJON_RESULT="$DONJON_RESULT_DIR/$STEM.result"
rm -f "$DONJON_RESULT" "$SHORT_SPH" "$SHORT_VERIFY"
(cd "$DONJON_DIR" && ./rdonjon -q "${DECK#"$DONJON_DIR/data/"}")
grep -aqi "normal end of execution" "$DONJON_RESULT" || {
  echo "DONJON native-SPH run did not reach normal end: $DONJON_RESULT" >&2
  exit 5
}
cp "$SHORT_SPH" "$SPH_MACROLIB"
cp "$SHORT_VERIFY" "$VERIFY_MACROLIB"
cp "$DONJON_RESULT" "$RESULT"

"$PYTHON_BIN" -m openmc2donjon.cli validate-native-sph "$COMPONENT_H5" \
  --reference-macrolib "$REFERENCE" --sph-macrolib "$SPH_MACROLIB" \
  --verify-macrolib "$VERIFY_MACROLIB" --result-listing "$RESULT" \
  --energy-coverage "$HANDOFF/energy_coverage_summary.json" \
  --converter-receipt "$HANDOFF/converter_summary.json" \
  --summary-json "$SUMMARY"

echo "native-SPH component result: $SUMMARY"

#!/usr/bin/env bash
set -euo pipefail

if [[ "${IRENA_ALLOW_LEGACY_COMPONENT_DIAGNOSTIC:-0}" != "1" ]]; then
  echo "This is the archived five-component diagnostic, not the current IRENA full-core SPH route." >&2
  echo "Use the 91-position/21-D3-orbit workflow documented in ORBIT_CE_REFERENCE.md." >&2
  echo "Set IRENA_ALLOW_LEGACY_COMPONENT_DIAGNOSTIC=1 only to reproduce the archive." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE_DIR="$REPO_ROOT/examples/irena30_native_fullcore"
POWER_TOOL_DIR="$REPO_ROOT/examples/irena30_zrefl_hex"
PROJECT_ROOT="${PROJECT_ROOT:-$REPO_ROOT/.openmc2donjon-runs/irena_fullcore_node_project}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DONJON_DIR="${DONJON_DIR:-}"
if [[ -z "$DONJON_DIR" && -n "${OPENMC2DONJON_ROOT:-}" ]]; then
  DONJON_DIR="$OPENMC2DONJON_ROOT/Donjon"
fi
REFERENCE_STATEPOINT="${REFERENCE_STATEPOINT:-}"
REFERENCE_POWER="${REFERENCE_POWER:-}"

: "${DONJON_DIR:?Set DONJON_DIR or OPENMC2DONJON_ROOT for the external DONJON checkout}"
: "${REFERENCE_STATEPOINT:?Set REFERENCE_STATEPOINT to the external OpenMC statepoint}"
: "${REFERENCE_POWER:?Set REFERENCE_POWER to the external OpenMC fission-rate JSON}"
[[ -x "$DONJON_DIR/rdonjon" ]] || {
  echo "missing DONJON runner: $DONJON_DIR/rdonjon" >&2
  exit 2
}
for reference in "$REFERENCE_STATEPOINT" "$REFERENCE_POWER"; do
  [[ -f "$reference" ]] || {
    echo "missing external reference input: $reference" >&2
    exit 2
  }
done

DONJON_PLATFORM="${DONJON_PLATFORM:-$(uname -sm | tr ' ' '_')}"
DONJON_RESULT_DIR="${DONJON_RESULT_DIR:-$DONJON_DIR/$DONJON_PLATFORM}"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT/src:$EXAMPLE_DIR${PYTHONPATH:+:$PYTHONPATH}"

CORE_DIR="$PROJECT_ROOT/core"
COMPONENT_LIBRARY="$CORE_DIR/accepted_components_24g_p3.macrolib.txt"
COMPONENT_SUMMARY="$CORE_DIR/accepted_components_summary.json"
POSITION_LIBRARY="$CORE_DIR/irena30_positions_24g_p3.macrolib.txt"
POSITION_SUMMARY="$CORE_DIR/irena30_positions_summary.json"
mkdir -p "$CORE_DIR"

for case in int_ext ext_int csd_int dsdf_int pnl_ext; do
  for file in mgxs_components.h5 native_sph_24g_p3.macrolib.txt physics_summary.json; do
    path="$PROJECT_ROOT/colorsets/$case/handoff/$file"
    [[ -f "$path" ]] || { echo "missing accepted component artifact: $path" >&2; exit 2; }
  done
done

echo "== Assemble five legacy local component records (diagnostic only) =="
"$PYTHON_BIN" -m openmc2donjon.cli assemble-component-library \
  --component "INT=$PROJECT_ROOT/colorsets/int_ext/handoff/native_sph_24g_p3.macrolib.txt::INT" \
  --physics-summary "INT=$PROJECT_ROOT/colorsets/int_ext/handoff/physics_summary.json" \
  --component "EXT=$PROJECT_ROOT/colorsets/ext_int/handoff/native_sph_24g_p3.macrolib.txt::EXT" \
  --physics-summary "EXT=$PROJECT_ROOT/colorsets/ext_int/handoff/physics_summary.json" \
  --component "CSD=$PROJECT_ROOT/colorsets/csd_int/handoff/native_sph_24g_p3.macrolib.txt::CSD" \
  --physics-summary "CSD=$PROJECT_ROOT/colorsets/csd_int/handoff/physics_summary.json" \
  --component "DSDF=$PROJECT_ROOT/colorsets/dsdf_int/handoff/native_sph_24g_p3.macrolib.txt::DSDF" \
  --physics-summary "DSDF=$PROJECT_ROOT/colorsets/dsdf_int/handoff/physics_summary.json" \
  --component "PNL=$PROJECT_ROOT/colorsets/pnl_ext/handoff/native_sph_24g_p3.macrolib.txt::PNL" \
  --physics-summary "PNL=$PROJECT_ROOT/colorsets/pnl_ext/handoff/physics_summary.json" \
  -o "$COMPONENT_LIBRARY" --summary-json "$COMPONENT_SUMMARY" --force

echo "== Expand legacy component records onto the declared IRENA map =="
"$PYTHON_BIN" "$EXAMPLE_DIR/build_position_library.py" "$COMPONENT_LIBRARY" \
  --library-summary "$COMPONENT_SUMMARY" -o "$POSITION_LIBRARY" \
  --summary-json "$POSITION_SUMMARY" --force

SHORT_DIR="${TMPDIR:-/tmp}/o2d_irena_fc"
mkdir -p "$SHORT_DIR"
SHORT_MACRO="$SHORT_DIR/macro.txt"
SN_EDI="$SHORT_DIR/sn.edi"
SPN_EDI="$SHORT_DIR/spn.edi"
cp "$POSITION_LIBRARY" "$SHORT_MACRO"
rm -f "$SN_EDI" "$SPN_EDI"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DECK_DIR="$DONJON_DIR/data/openmc2donjon/irena_component_fullcore/$STAMP"
"$PYTHON_BIN" "$EXAMPLE_DIR/write_donjon_decks.py" \
  --macrolib "$SHORT_MACRO" --sn-edi "$SN_EDI" --spn-edi "$SPN_EDI" \
  --deck-dir "$DECK_DIR" --stamp "$STAMP"

run_deck() {
  local solver="$1"
  local deck="$DECK_DIR/irena30_component_fullcore_${solver}_${STAMP}.x2m"
  local stem
  stem="$(basename "$deck" .x2m)"
  local result="$DONJON_RESULT_DIR/$stem.result"
  rm -f "$result"
  (cd "$DONJON_DIR" && ./rdonjon -q "${deck#"$DONJON_DIR/data/"}")
  grep -aqi "normal end of execution" "$result" || {
    echo "DONJON $solver did not reach normal end: $result" >&2
    exit 3
  }
  cp "$deck" "$CORE_DIR/irena30_component_fullcore_${solver}.x2m"
  cp "$result" "$CORE_DIR/irena30_component_fullcore_${solver}.result"
}

echo "== Run independent DONJON SN full core =="
run_deck sn
cp "$SN_EDI" "$CORE_DIR/irena30_component_fullcore_sn.edi.txt"
echo "== Run independent DONJON SPN full core =="
run_deck spn
cp "$SPN_EDI" "$CORE_DIR/irena30_component_fullcore_spn.edi.txt"

echo "== Compare k-effective and leakage to OpenMC CE =="
"$PYTHON_BIN" "$EXAMPLE_DIR/compare_fullcore.py" \
  --statepoint "$REFERENCE_STATEPOINT" \
  --sn-result "$CORE_DIR/irena30_component_fullcore_sn.result" \
  --spn-result "$CORE_DIR/irena30_component_fullcore_spn.result" \
  --sn-edi "$CORE_DIR/irena30_component_fullcore_sn.edi.txt" \
  --spn-edi "$CORE_DIR/irena30_component_fullcore_spn.edi.txt" \
  --summary "$CORE_DIR/keff_leakage_comparison.json"

echo "== Compare normalized 52-position fuel power shapes =="
for solver in sn spn; do
  "$PYTHON_BIN" "$POWER_TOOL_DIR/compare_power.py" \
    --openmc-fission "$REFERENCE_POWER" \
    --edi "$CORE_DIR/irena30_component_fullcore_${solver}.edi.txt" \
    --max-rel "${POWER_MAX_REL:-0.02}" --max-rms "${POWER_MAX_RMS:-0.01}" \
    --summary "$CORE_DIR/power_${solver}_comparison.json"
done

echo "IRENA legacy five-component diagnostic gates completed; this is not full-core SPH acceptance"

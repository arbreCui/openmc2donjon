#!/usr/bin/env bash
set -euo pipefail

if [[ "${OPENMC2DONJON_ALLOW_WITHDRAWN_COLORSET_DIAGNOSTIC:-0}" != "1" ]]; then
  echo "This OpenMC-MG colorset closure is a withdrawn diagnostic, not an IRENA production or full-core acceptance route." >&2
  echo "Use the 91-position/21-D3-orbit native-SPH workflow for the current IRENA candidate." >&2
  echo "Set OPENMC2DONJON_ALLOW_WITHDRAWN_COLORSET_DIAGNOSTIC=1 only to reproduce the archived diagnostic." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE_DIR="$REPO_ROOT/examples/irena30_sph_stage2_csd"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OPENMC_EXEC="${OPENMC_EXEC:-openmc}"
OPENMC_THREADS="${OPENMC_THREADS:-8}"
RUN_ROOT="${RUN_ROOT:-$REPO_ROOT/.openmc2donjon-runs/irena_pnl_ext_anl23c_tied_physical}"

# Frozen physics charter. Only histories and thread count may be increased.
export IRENA_SPH2_CASE="pnl_ext"
export IRENA_SPH2_ENERGY_MESH_ID="anl_23c"
ENERGY_OUTSIDE_MAX="0.005"
SPH_DAMPING="0.5"
SPH_MAX_UPDATE_RESIDUAL="0.02"
MAX_FLUX_REL_STD="0.10"
SPH_ITERATIONS="8"
TIE_MIXTURES="EXT_N1,EXT_N2,EXT_N3,EXT_N4,EXT_N5,EXT_N6"
BATCHES="${BATCHES:-60}"
INACTIVE="${INACTIVE:-20}"
PARTICLES="${PARTICLES:-40000}"
MG_BATCHES="${MG_BATCHES:-60}"
MG_INACTIVE="${MG_INACTIVE:-20}"
MG_PARTICLES="${MG_PARTICLES:-40000}"
REUSE_CE="${REUSE_CE:-0}"

CE_CASE_DIR="$RUN_ROOT/ce_case"
OUT_DIR="$RUN_ROOT/handoff"
RECIPE="$EXAMPLE_DIR/export_recipe.py"
CE_SP="$CE_CASE_DIR/statepoint.$BATCHES.h5"
MGXS_H5="$OUT_DIR/mgxs_library.h5"
CE_FLUX="$OUT_DIR/openmc_ce_flux.h5"
FINAL_SPH="$OUT_DIR/openmc_sph_sidecar.h5"
CORRECTED_H5="$OUT_DIR/mgxs_sph_applied.h5"
CONVERTER_OUTPUT="$OUT_DIR/out_sph_applied.macrolib.txt"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT/src:$EXAMPLE_DIR${PYTHONPATH:+:$PYTHONPATH}"
if [[ "$REUSE_CE" != "1" ]]; then
  : "${IRENA_CE_COMPARE_DIR:?Set IRENA_CE_COMPARE_DIR to the external IRENA ce_compare input directory}"
  : "${OPENMC_CROSS_SECTIONS:?Set OPENMC_CROSS_SECTIONS to the OpenMC cross_sections.xml file}"
  export IRENA_CE_COMPARE_DIR OPENMC_CROSS_SECTIONS
fi

run_openmc_case() {
  (cd "$1" && "$OPENMC_EXEC" -s "$OPENMC_THREADS")
}

mkdir -p "$OUT_DIR"
cp "$EXAMPLE_DIR/PHYSICAL_CLOSURE_CHARTER.md" "$RUN_ROOT/PHYSICAL_CLOSURE_CHARTER.md"

echo "== WITHDRAWN OpenMC-MG colorset diagnostic: pnl_ext / ANL-23C =="
echo "run root: $RUN_ROOT"
echo "scope: local seven-assembly diagnostic only; never IRENA full-core acceptance"
echo "forbidden: fill, blacken, floor, freeze, clip, identity, ADF, empirical factor"
echo "physical symmetry class: $TIE_MIXTURES"

if [[ "$REUSE_CE" == "1" ]]; then
  for REQUIRED in "$CE_SP" "$OUT_DIR/energy_coverage_summary.json" "$MGXS_H5" "$CE_FLUX"; do
    if [[ ! -f "$REQUIRED" ]]; then
      echo "REUSE_CE=1 requires existing evidence: $REQUIRED" >&2
      exit 4
    fi
  done
  echo "== Reuse the archived CE reference; restart diagnostic MG statistics =="
else
  echo "== Build and run continuous-energy fine model =="
  "$PYTHON_BIN" "$EXAMPLE_DIR/build_ce_case.py" \
    --case-dir "$CE_CASE_DIR" \
    --batches "$BATCHES" \
    --inactive "$INACTIVE" \
    --particles "$PARTICLES"
  run_openmc_case "$CE_CASE_DIR"

  echo "== Qualify the declared ANL-23C energy domain =="
  "$PYTHON_BIN" "$EXAMPLE_DIR/evaluate_energy_coverage.py" "$CE_SP" \
    --max-outside-fraction "$ENERGY_OUTSIDE_MAX" \
    --summary-json "$OUT_DIR/energy_coverage_summary.json"

  echo "== Export unmodified CE-derived converter handoff and CE flux =="
  OPENMC2DONJON_IRENA_SPH2_DIR="$CE_CASE_DIR" \
  "$PYTHON_BIN" -m openmc2donjon.export_cli \
    --recipe "$RECIPE" \
    --statepoint "$CE_SP" \
    -o "$MGXS_H5"
  "$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$CE_SP" \
    --mgxs "$MGXS_H5" \
    --tally-name irena30_sph_stage2_volume_flux \
    --dataset-name openmc_volume_flux \
    -o "$CE_FLUX" \
    --force
fi

PREVIOUS_SPH=""
CONVERGED="0"
BASELINE_MG_SP=""
for ((ITER=1; ITER<=SPH_ITERATIONS; ITER++)); do
  L="$(printf "%02d" "$ITER")"
  MG_CASE_DIR="$RUN_ROOT/mg_case_iter$L"
  MG_SP="$MG_CASE_DIR/statepoint.$MG_BATCHES.h5"
  MG_FLUX="$OUT_DIR/openmc_mg_flux_iter$L.h5"
  SIDECAR="$OUT_DIR/openmc_sph_sidecar_iter$L.h5"
  TABLE="$OUT_DIR/openmc_sph_iter$L.csv"
  SUMMARY="$OUT_DIR/openmc_sph_summary_iter$L.json"

  PREPARE_ARGS=(
    --ce-case-dir "$CE_CASE_DIR"
    --ce-statepoint "$CE_SP"
    --mg-case-dir "$MG_CASE_DIR"
    --batches "$MG_BATCHES"
    --inactive "$MG_INACTIVE"
    --particles "$MG_PARTICLES"
    --seed $((31 + ITER))
    --zero-xs-policy reject
    --summary-json "$OUT_DIR/mg_macro_summary_iter$L.json"
  )
  if [[ -n "$PREVIOUS_SPH" ]]; then
    PREPARE_ARGS+=(
      --sph-source "$PREVIOUS_SPH"
      --sph-apply-summary-json "$OUT_DIR/sph_apply_summary_iter$L.json"
    )
  fi
  "$PYTHON_BIN" "$EXAMPLE_DIR/prepare_mg_case.py" "${PREPARE_ARGS[@]}"
  run_openmc_case "$MG_CASE_DIR"
  if [[ "$ITER" == "1" ]]; then
    BASELINE_MG_SP="$MG_SP"
  fi

  "$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$MG_SP" \
    --mgxs "$MGXS_H5" \
    --tally-name irena30_sph_stage2_volume_flux \
    --dataset-name openmc_mg_flux \
    -o "$MG_FLUX" \
    --force

  SPH_ARGS=(
    "$MGXS_H5"
    -o "$SIDECAR"
    --reference-flux "$CE_FLUX::openmc_volume_flux"
    --mg-flux "$MG_FLUX::openmc_mg_flux"
    --table-output "$TABLE"
    --damping "$SPH_DAMPING"
    --flux-normalization power
    --sph-target rate
    --zero-flux-policy reject
    --tie-mixtures "$TIE_MIXTURES"
    --require-reference-flux-std-dev
    --max-reference-flux-std-dev-rel "$MAX_FLUX_REL_STD"
    --require-mg-flux-std-dev
    --max-mg-flux-std-dev-rel "$MAX_FLUX_REL_STD"
    --source-label "irena-pnl-ext-anl27-rate-sph"
    --summary-json "$SUMMARY"
    --force
  )
  if [[ -n "$PREVIOUS_SPH" ]]; then
    SPH_ARGS+=(--previous-sph "$PREVIOUS_SPH")
  fi
  "$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar "${SPH_ARGS[@]}"

  set +e
  "$PYTHON_BIN" "$EXAMPLE_DIR/evaluate_physical_iteration.py" "$SUMMARY" \
    --max-update-residual "$SPH_MAX_UPDATE_RESIDUAL" \
    --require-tie-mixtures "$TIE_MIXTURES"
  STATUS=$?
  set -e
  PREVIOUS_SPH="$SIDECAR"
  if [[ "$STATUS" == "0" ]]; then
    CONVERGED="1"
    break
  fi
  if [[ "$STATUS" != "10" ]]; then
    exit "$STATUS"
  fi
done

if [[ "$CONVERGED" != "1" ]]; then
  echo "strict SPH did not converge within $SPH_ITERATIONS iterations" >&2
  exit 3
fi
cp "$PREVIOUS_SPH" "$FINAL_SPH"

echo "== Diagnostic MG rerun of the candidate factor set =="
VALIDATION_DIR="$RUN_ROOT/mg_case_validation"
VALIDATION_SP="$VALIDATION_DIR/statepoint.$MG_BATCHES.h5"
VALIDATION_FLUX="$OUT_DIR/openmc_mg_flux_validation.h5"
VALIDATION_NEXT="$OUT_DIR/openmc_sph_validation_candidate.h5"
VALIDATION_SUMMARY="$OUT_DIR/openmc_sph_validation_summary.json"
"$PYTHON_BIN" "$EXAMPLE_DIR/prepare_mg_case.py" \
  --ce-case-dir "$CE_CASE_DIR" \
  --ce-statepoint "$CE_SP" \
  --mg-case-dir "$VALIDATION_DIR" \
  --batches "$MG_BATCHES" \
  --inactive "$MG_INACTIVE" \
  --particles "$MG_PARTICLES" \
  --seed 97 \
  --sph-source "$FINAL_SPH" \
  --sph-apply-summary-json "$OUT_DIR/sph_apply_summary_validation.json" \
  --zero-xs-policy reject \
  --summary-json "$OUT_DIR/mg_macro_summary_validation.json"
run_openmc_case "$VALIDATION_DIR"
"$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$VALIDATION_SP" \
  --mgxs "$MGXS_H5" \
  --tally-name irena30_sph_stage2_volume_flux \
  --dataset-name openmc_mg_flux \
  -o "$VALIDATION_FLUX" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar "$MGXS_H5" \
  -o "$VALIDATION_NEXT" \
  --reference-flux "$CE_FLUX::openmc_volume_flux" \
  --mg-flux "$VALIDATION_FLUX::openmc_mg_flux" \
  --previous-sph "$FINAL_SPH" \
  --table-output "$OUT_DIR/openmc_sph_validation.csv" \
  --damping "$SPH_DAMPING" \
  --flux-normalization power \
  --sph-target rate \
  --zero-flux-policy reject \
  --tie-mixtures "$TIE_MIXTURES" \
  --require-reference-flux-std-dev \
  --max-reference-flux-std-dev-rel "$MAX_FLUX_REL_STD" \
  --require-mg-flux-std-dev \
  --max-mg-flux-std-dev-rel "$MAX_FLUX_REL_STD" \
  --source-label "irena-pnl-ext-anl27-rate-sph-validation" \
  --summary-json "$VALIDATION_SUMMARY" \
  --force
"$PYTHON_BIN" "$EXAMPLE_DIR/evaluate_physical_iteration.py" "$VALIDATION_SUMMARY" \
  --max-update-residual "$SPH_MAX_UPDATE_RESIDUAL" \
  --require-tie-mixtures "$TIE_MIXTURES"

echo "== Write a diagnostic SPH-applied artifact (not a formal production handoff) =="
"$PYTHON_BIN" -m openmc2donjon.cli apply-sph "$MGXS_H5" \
  --sph-source "$FINAL_SPH" \
  -o "$CORRECTED_H5" \
  --summary-json "$OUT_DIR/sph_apply_converter_summary.json" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli "$CORRECTED_H5" \
  --format macrolib \
  -o "$CONVERTER_OUTPUT" \
  --summary-json "$OUT_DIR/converter_summary.json" \
  --overwrite

"$PYTHON_BIN" "$EXAMPLE_DIR/summarize_physical_closure.py" \
  --ce-statepoint "$CE_SP" \
  --uncorrected-mg-statepoint "$BASELINE_MG_SP" \
  --corrected-mg-statepoint "$VALIDATION_SP" \
  --energy-coverage "$OUT_DIR/energy_coverage_summary.json" \
  --validation-iteration "$VALIDATION_SUMMARY" \
  --corrected-h5 "$CORRECTED_H5" \
  --converter-output "$CONVERTER_OUTPUT" \
  --output "$OUT_DIR/physics_summary.json"

echo "withdrawn diagnostic summary: $OUT_DIR/physics_summary.json"

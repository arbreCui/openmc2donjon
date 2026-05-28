#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OPENMC_EXEC="${OPENMC_EXEC:-openmc}"
OPENMC_LIB_DIR="${OPENMC_LIB_DIR:-}"
RUN_ROOT="${RUN_ROOT:-/private/tmp/openmc2donjon_ce_mg_33g_sph_minicase}"
CE_CASE_DIR="$RUN_ROOT/ce_case"
MG_CASE_DIR="$RUN_ROOT/mg_case"
OUT_DIR="$RUN_ROOT/handoff"
RECIPE="$REPO_ROOT/examples/openmc_ce_mg_33g_sph_minicase/export_recipe.py"
CE_SP="$CE_CASE_DIR/statepoint.${BATCHES:-20}.h5"
MGXS_H5="$OUT_DIR/mgxs_library.h5"
CE_FLUX="$OUT_DIR/openmc_ce_flux.h5"
MG_FLUX="$OUT_DIR/openmc_mg_flux.h5"
SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar.h5"
SPH_TABLE="$OUT_DIR/openmc_sph.csv"
AUGMENTED="$OUT_DIR/mgxs_with_openmc_sph.h5"
MG_MACRO_SCATTER_FORMAT="${MG_MACRO_SCATTER_FORMAT:-histogram}"
MG_MACRO_HISTOGRAM_BINS="${MG_MACRO_HISTOGRAM_BINS:-16}"
MG_MACRO_LEGENDRE_ORDER="${MG_MACRO_LEGENDRE_ORDER:-3}"
SPH_ITERATIONS="${SPH_ITERATIONS:-1}"
SPH_DAMPING="${SPH_DAMPING:-1.0}"
SPH_CLIP_MIN="${SPH_CLIP_MIN:-}"
SPH_CLIP_MAX="${SPH_CLIP_MAX:-}"

run_openmc_case() {
  local case_dir="$1"
  if [[ -n "$OPENMC_LIB_DIR" ]]; then
    (
      cd "$case_dir"
      env \
        DYLD_LIBRARY_PATH="$OPENMC_LIB_DIR${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" \
        LD_LIBRARY_PATH="$OPENMC_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$OPENMC_EXEC"
    )
  else
    (cd "$case_dir" && "$OPENMC_EXEC")
  fi
}

copy_if_different() {
  local src="$1"
  local dst="$2"
  if [[ "$src" != "$dst" ]]; then
    cp "$src" "$dst"
  fi
}

if (( SPH_ITERATIONS < 1 )); then
  echo "SPH_ITERATIONS must be >= 1" >&2
  exit 2
fi

echo "== OpenMC CE/MG SPH colorset minicase (ECCO-33 example) =="
echo "run root: $RUN_ROOT"
echo "SPH iterations: $SPH_ITERATIONS"
echo "SPH damping: $SPH_DAMPING"
if [[ -n "$SPH_CLIP_MIN" || -n "$SPH_CLIP_MAX" ]]; then
  echo "SPH clipping: min=${SPH_CLIP_MIN:-none} max=${SPH_CLIP_MAX:-none}"
fi
if [[ "$MG_MACRO_SCATTER_FORMAT" == "histogram" ]]; then
  echo "OpenMC MG macro scatter treatment: H$MG_MACRO_HISTOGRAM_BINS"
else
  echo "OpenMC MG macro scatter treatment: P$MG_MACRO_LEGENDRE_ORDER"
fi
if [[ -n "$OPENMC_LIB_DIR" ]]; then
  echo "OpenMC library dir: $OPENMC_LIB_DIR"
fi
mkdir -p "$OUT_DIR"

echo
echo "== Build continuous-energy OpenMC input =="
"$PYTHON_BIN" "$REPO_ROOT/examples/openmc_ce_mg_33g_sph_minicase/build_ce_case.py" \
  --case-dir "$CE_CASE_DIR" \
  --batches "${BATCHES:-20}" \
  --inactive "${INACTIVE:-5}" \
  --particles "${PARTICLES:-1000}" \
  --mg-macro-scatter-format "$MG_MACRO_SCATTER_FORMAT" \
  --mg-macro-histogram-bins "$MG_MACRO_HISTOGRAM_BINS" \
  --mg-macro-legendre-order "$MG_MACRO_LEGENDRE_ORDER"

echo
echo "== Run OpenMC CE reference =="
run_openmc_case "$CE_CASE_DIR"

echo
echo "== Export converter MGXS HDF5 from CE statepoint =="
OPENMC2DONJON_COLORSET_DIR="$CE_CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --statepoint "$CE_SP" \
  --keep-hdf5 "$MGXS_H5" \
  --output "$OUT_DIR/out.mcompo.txt" \
  --format multicompo \
  --check \
  --require-volume \
  --require-transport-dataset \
  --force-run-dir \
  --run-dir "$OUT_DIR/from_openmc_run"

echo
echo "== Export CE reference region/group flux map =="
"$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$CE_SP" \
  --mgxs "$MGXS_H5" \
  --tally-name openmc_ce_mg_sph_volume_flux \
  --dataset-name openmc_volume_flux \
  -o "$CE_FLUX" \
  --force

echo
echo "== Iterate OpenMC MG macro calculation and OpenMC-side SPH factors =="
PREVIOUS_SPH=""
FINAL_MG_CASE_DIR=""
FINAL_MG_FLUX=""
FINAL_SPH_SIDECAR=""
FINAL_SPH_TABLE=""
FINAL_SPH_SUMMARY=""
FINAL_MG_MACRO_SUMMARY=""
for ((ITER=1; ITER<=SPH_ITERATIONS; ITER++)); do
  ITER_LABEL="$(printf "%02d" "$ITER")"
  if (( SPH_ITERATIONS == 1 )); then
    ITER_MG_CASE_DIR="$MG_CASE_DIR"
    ITER_MG_FLUX="$MG_FLUX"
    ITER_SPH_SIDECAR="$SPH_SIDECAR"
    ITER_SPH_TABLE="$SPH_TABLE"
    ITER_SPH_SUMMARY="$OUT_DIR/openmc_sph_summary.json"
    ITER_MG_MACRO_SUMMARY="$OUT_DIR/mg_macro_summary.json"
    ITER_APPLY_SUMMARY="$OUT_DIR/sph_apply_summary.json"
  else
    ITER_MG_CASE_DIR="$RUN_ROOT/mg_case_iter${ITER_LABEL}"
    ITER_MG_FLUX="$OUT_DIR/openmc_mg_flux_iter${ITER_LABEL}.h5"
    ITER_SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar_iter${ITER_LABEL}.h5"
    ITER_SPH_TABLE="$OUT_DIR/openmc_sph_iter${ITER_LABEL}.csv"
    ITER_SPH_SUMMARY="$OUT_DIR/openmc_sph_summary_iter${ITER_LABEL}.json"
    ITER_MG_MACRO_SUMMARY="$OUT_DIR/mg_macro_summary_iter${ITER_LABEL}.json"
    ITER_APPLY_SUMMARY="$OUT_DIR/sph_apply_summary_iter${ITER_LABEL}.json"
  fi
  ITER_MG_SP="$ITER_MG_CASE_DIR/statepoint.${MG_BATCHES:-20}.h5"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: prepare OpenMC MG macro input =="
  PREPARE_ARGS=(
    --ce-case-dir "$CE_CASE_DIR"
    --ce-statepoint "$CE_SP"
    --mg-case-dir "$ITER_MG_CASE_DIR"
    --batches "${MG_BATCHES:-20}"
    --inactive "${MG_INACTIVE:-5}"
    --particles "${MG_PARTICLES:-1000}"
    --scatter-format "$MG_MACRO_SCATTER_FORMAT"
    --histogram-bins "$MG_MACRO_HISTOGRAM_BINS"
    --legendre-order "$MG_MACRO_LEGENDRE_ORDER"
    --summary-json "$ITER_MG_MACRO_SUMMARY"
  )
  if [[ -n "$PREVIOUS_SPH" ]]; then
    PREPARE_ARGS+=(
      --sph-source "$PREVIOUS_SPH"
      --sph-apply-summary-json "$ITER_APPLY_SUMMARY"
    )
  fi
  "$PYTHON_BIN" "$REPO_ROOT/examples/openmc_ce_mg_33g_sph_minicase/prepare_mg_case.py" "${PREPARE_ARGS[@]}"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: run OpenMC MG macro calculation =="
  run_openmc_case "$ITER_MG_CASE_DIR"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: export MG region/group flux =="
  "$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$ITER_MG_SP" \
    --mgxs "$MGXS_H5" \
    --tally-name openmc_ce_mg_sph_volume_flux \
    --dataset-name openmc_mg_flux \
    -o "$ITER_MG_FLUX" \
    --force

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: compute OpenMC-side SPH =="
  SPH_ARGS=(
    "$MGXS_H5"
    -o "$ITER_SPH_SIDECAR"
    --reference-flux "$CE_FLUX::openmc_volume_flux"
    --mg-flux "$ITER_MG_FLUX::openmc_mg_flux"
    --table-output "$ITER_SPH_TABLE"
    --damping "$SPH_DAMPING"
    --flux-normalization auto
    --require-reference-flux-std-dev
    --max-reference-flux-std-dev-rel "${MAX_CE_FLUX_REL_STD:-0.20}"
    --require-mg-flux-std-dev
    --max-mg-flux-std-dev-rel "${MAX_MG_FLUX_REL_STD:-0.20}"
    --summary-json "$ITER_SPH_SUMMARY"
    --force
  )
  if [[ -n "$PREVIOUS_SPH" ]]; then
    SPH_ARGS+=(--previous-sph "$PREVIOUS_SPH")
  fi
  if [[ -n "$SPH_CLIP_MIN" ]]; then
    SPH_ARGS+=(--clip-min "$SPH_CLIP_MIN")
  fi
  if [[ -n "$SPH_CLIP_MAX" ]]; then
    SPH_ARGS+=(--clip-max "$SPH_CLIP_MAX")
  fi
  "$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar "${SPH_ARGS[@]}"

  PREVIOUS_SPH="$ITER_SPH_SIDECAR"
  FINAL_MG_CASE_DIR="$ITER_MG_CASE_DIR"
  FINAL_MG_FLUX="$ITER_MG_FLUX"
  FINAL_SPH_SIDECAR="$ITER_SPH_SIDECAR"
  FINAL_SPH_TABLE="$ITER_SPH_TABLE"
  FINAL_SPH_SUMMARY="$ITER_SPH_SUMMARY"
  FINAL_MG_MACRO_SUMMARY="$ITER_MG_MACRO_SUMMARY"
done

copy_if_different "$FINAL_MG_FLUX" "$MG_FLUX"
copy_if_different "$FINAL_SPH_SIDECAR" "$SPH_SIDECAR"
copy_if_different "$FINAL_SPH_TABLE" "$SPH_TABLE"
copy_if_different "$FINAL_SPH_SUMMARY" "$OUT_DIR/openmc_sph_summary.json"
copy_if_different "$FINAL_MG_MACRO_SUMMARY" "$OUT_DIR/mg_macro_summary.json"

"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS_H5" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED" \
  --summary-json "$OUT_DIR/sph_augment_summary.json" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED" \
  -o "$OUT_DIR/out_with_openmc_sph.mcompo.txt" \
  --check \
  --require-sph

"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED" \
  --format macrolib \
  -o "$OUT_DIR/out_with_openmc_sph.macrolib.txt" \
  --check \
  --require-sph

echo
echo "== Summarize OpenMC-side SPH physics handoff =="
"$PYTHON_BIN" "$REPO_ROOT/examples/openmc_ce_mg_33g_sph_minicase/summarize_outputs.py" \
  --handoff-dir "$OUT_DIR"

echo
echo "OpenMC CE/MG SPH colorset minicase complete:"
echo "  MGXS: $MGXS_H5"
echo "  CE flux: $CE_FLUX::openmc_volume_flux"
echo "  MG flux: $MG_FLUX::openmc_mg_flux"
echo "  final MG case: $FINAL_MG_CASE_DIR"
echo "  MG macro scatter summary: $OUT_DIR/mg_macro_summary.json"
echo "  SPH sidecar: $SPH_SIDECAR"
echo "  MULTICOMPO ASCII: $OUT_DIR/out_with_openmc_sph.mcompo.txt"
echo "  MACROLIB ASCII: $OUT_DIR/out_with_openmc_sph.macrolib.txt"
echo "  physics summary: $OUT_DIR/physics_summary.md"

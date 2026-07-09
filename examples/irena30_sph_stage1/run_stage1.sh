#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE_DIR="$REPO_ROOT/examples/irena30_sph_stage1"
PYTHON_BIN="${PYTHON_BIN:-/Users/wen/miniforge3/envs/openmc-dev/bin/python}"
OPENMC_EXEC="${OPENMC_EXEC:-/Users/wen/miniforge3/envs/openmc-dev/bin/openmc}"
OPENMC_THREADS="${OPENMC_THREADS:-8}"
RUN_ROOT="${RUN_ROOT:-/private/tmp/openmc2donjon_irena_sph_stage1}"
CE_CASE_DIR="$RUN_ROOT/ce_case"
OUT_DIR="$RUN_ROOT/handoff"
RECIPE="$EXAMPLE_DIR/export_recipe.py"
BATCHES="${BATCHES:-60}"
INACTIVE="${INACTIVE:-20}"
PARTICLES="${PARTICLES:-20000}"
MG_BATCHES="${MG_BATCHES:-60}"
MG_INACTIVE="${MG_INACTIVE:-20}"
MG_PARTICLES="${MG_PARTICLES:-20000}"
SPH_ITERATIONS="${SPH_ITERATIONS:-4}"
SPH_DAMPING="${SPH_DAMPING:-1.0}"
SPH_FLUX_FLOOR_REL="${SPH_FLUX_FLOOR_REL:-1e-3}"
SPH_CLIP_MIN="${SPH_CLIP_MIN:-0.5}"
SPH_CLIP_MAX="${SPH_CLIP_MAX:-2.0}"
# Optional comma-separated DRAGON-order group list, e.g. "31" for the
# established CSD practice of switching group-31 SPH off entirely.
SPH_FREEZE_GROUPS="${SPH_FREEZE_GROUPS:-}"
MAX_CE_FLUX_REL_STD="${MAX_CE_FLUX_REL_STD:-0.20}"
MAX_MG_FLUX_REL_STD="${MAX_MG_FLUX_REL_STD:-0.20}"
CE_SP="$CE_CASE_DIR/statepoint.$BATCHES.h5"
MGXS_H5="$OUT_DIR/mgxs_library.h5"
CE_FLUX="$OUT_DIR/openmc_ce_flux.h5"
MG_FLUX="$OUT_DIR/openmc_mg_flux.h5"
SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar.h5"
AUGMENTED="$OUT_DIR/mgxs_with_openmc_sph.h5"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT/src:$EXAMPLE_DIR${PYTHONPATH:+:$PYTHONPATH}"
export OPENMC_CROSS_SECTIONS="${OPENMC_CROSS_SECTIONS:-/Users/wen/openmc-workspace/data/endfb-viii.1-hdf5/cross_sections.xml}"

run_openmc_case() {
  (cd "$1" && "$OPENMC_EXEC" -s "$OPENMC_THREADS")
}

echo "== IRENA SPH Stage 1: fissile assembly CE fine vs MG coarse =="
echo "run root: $RUN_ROOT"
echo "CE: $PARTICLES x $BATCHES ($INACTIVE inactive); MG: $MG_PARTICLES x $MG_BATCHES"
echo "SPH iterations: $SPH_ITERATIONS  damping: $SPH_DAMPING  floor: $SPH_FLUX_FLOOR_REL  clip: [$SPH_CLIP_MIN, $SPH_CLIP_MAX]"
mkdir -p "$OUT_DIR"

echo
echo "== Build continuous-energy OpenMC input =="
"$PYTHON_BIN" "$EXAMPLE_DIR/build_ce_case.py" \
  --case-dir "$CE_CASE_DIR" \
  --batches "$BATCHES" \
  --inactive "$INACTIVE" \
  --particles "$PARTICLES"

echo
echo "== Run OpenMC CE reference =="
run_openmc_case "$CE_CASE_DIR"

echo
echo "== Export converter MGXS HDF5 from CE statepoint =="
OPENMC2DONJON_IRENA_SPH_DIR="$CE_CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$RECIPE" \
  --statepoint "$CE_SP" \
  -o "$MGXS_H5"

echo
echo "== Fill zero-flux thermal groups of the handoff from the MG macrolib =="
IRENA30_MACROLIB="${IRENA30_MACROLIB:-/Users/wen/openmc-workspace/irena/build/macrolib.h5}"
"$PYTHON_BIN" -m openmc2donjon.cli fill-zero-flux "$MGXS_H5" \
  --macrolib "$IRENA30_MACROLIB" \
  --in-place

echo
echo "== Export CE reference region/group flux =="
"$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$CE_SP" \
  --mgxs "$MGXS_H5" \
  --tally-name irena30_sph_stage1_volume_flux \
  --dataset-name openmc_volume_flux \
  -o "$CE_FLUX" \
  --allow-zero-flux \
  --force

echo
echo "== Iterate OpenMC MG macro calculation and OpenMC-side SPH factors =="
PREVIOUS_SPH=""
for ((ITER=1; ITER<=SPH_ITERATIONS; ITER++)); do
  L="$(printf "%02d" "$ITER")"
  ITER_MG_CASE_DIR="$RUN_ROOT/mg_case_iter$L"
  ITER_MG_FLUX="$OUT_DIR/openmc_mg_flux_iter$L.h5"
  ITER_SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar_iter$L.h5"
  ITER_SPH_TABLE="$OUT_DIR/openmc_sph_iter$L.csv"
  ITER_SPH_SUMMARY="$OUT_DIR/openmc_sph_summary_iter$L.json"
  ITER_MG_SP="$ITER_MG_CASE_DIR/statepoint.$MG_BATCHES.h5"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: prepare MG coarse case =="
  PREPARE_ARGS=(
    --ce-case-dir "$CE_CASE_DIR"
    --ce-statepoint "$CE_SP"
    --mg-case-dir "$ITER_MG_CASE_DIR"
    --batches "$MG_BATCHES"
    --inactive "$MG_INACTIVE"
    --particles "$MG_PARTICLES"
    --seed $((31 + ITER))
    --summary-json "$OUT_DIR/mg_macro_summary_iter$L.json"
  )
  if [[ -n "$PREVIOUS_SPH" ]]; then
    PREPARE_ARGS+=(
      --sph-source "$PREVIOUS_SPH"
      --sph-apply-summary-json "$OUT_DIR/sph_apply_summary_iter$L.json"
    )
  fi
  "$PYTHON_BIN" "$EXAMPLE_DIR/prepare_mg_case.py" "${PREPARE_ARGS[@]}"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: run MG coarse case =="
  run_openmc_case "$ITER_MG_CASE_DIR"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: export MG region/group flux =="
  "$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$ITER_MG_SP" \
    --mgxs "$MGXS_H5" \
    --tally-name irena30_sph_stage1_volume_flux \
    --dataset-name openmc_mg_flux \
    -o "$ITER_MG_FLUX" \
    --allow-zero-flux \
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
    --zero-flux-policy identity
    --flux-floor-rel "$SPH_FLUX_FLOOR_REL"
    --clip-min "$SPH_CLIP_MIN"
    --clip-max "$SPH_CLIP_MAX"
    --require-reference-flux-std-dev
    --max-reference-flux-std-dev-rel "$MAX_CE_FLUX_REL_STD"
    --require-mg-flux-std-dev
    --max-mg-flux-std-dev-rel "$MAX_MG_FLUX_REL_STD"
    --summary-json "$ITER_SPH_SUMMARY"
    --force
  )
  if [[ -n "$SPH_FREEZE_GROUPS" ]]; then
    SPH_ARGS+=(--freeze-groups "$SPH_FREEZE_GROUPS")
  fi
  if [[ -n "$PREVIOUS_SPH" ]]; then
    SPH_ARGS+=(--previous-sph "$PREVIOUS_SPH")
  fi
  "$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar "${SPH_ARGS[@]}"
  PREVIOUS_SPH="$ITER_SPH_SIDECAR"
done

cp "$PREVIOUS_SPH" "$SPH_SIDECAR"

echo
echo "== Augment MGXS with final SPH and write DONJON ASCII =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS_H5" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED" \
  --summary-json "$OUT_DIR/sph_augment_summary.json" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED" \
  --format macrolib \
  -o "$OUT_DIR/out_with_openmc_sph.macrolib.txt" \
  --require-sph

echo
echo "IRENA SPH Stage 1 complete:"
echo "  handoff: $OUT_DIR"

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
MG_SP="$MG_CASE_DIR/statepoint.${MG_BATCHES:-20}.h5"
MGXS_H5="$OUT_DIR/mgxs_library.h5"
CE_FLUX="$OUT_DIR/openmc_ce_flux.h5"
MG_FLUX="$OUT_DIR/openmc_mg_flux.h5"
SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar.h5"
SPH_TABLE="$OUT_DIR/openmc_sph.csv"
AUGMENTED="$OUT_DIR/mgxs_with_openmc_sph.h5"

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

echo "== OpenMC CE/MG 33g SPH colorset minicase =="
echo "run root: $RUN_ROOT"
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
  --particles "${PARTICLES:-1000}"

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
echo "== Prepare OpenMC MG 33g macro input from the CE MGXS library =="
"$PYTHON_BIN" "$REPO_ROOT/examples/openmc_ce_mg_33g_sph_minicase/prepare_mg_case.py" \
  --ce-case-dir "$CE_CASE_DIR" \
  --ce-statepoint "$CE_SP" \
  --mg-case-dir "$MG_CASE_DIR" \
  --batches "${MG_BATCHES:-20}" \
  --inactive "${MG_INACTIVE:-5}" \
  --particles "${MG_PARTICLES:-1000}"

echo
echo "== Run OpenMC MG macro calculation =="
run_openmc_case "$MG_CASE_DIR"

echo
echo "== Export CE and MG region/group flux maps =="
"$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$CE_SP" \
  --mgxs "$MGXS_H5" \
  --tally-name openmc_ce_mg_sph_volume_flux \
  --dataset-name openmc_volume_flux \
  -o "$CE_FLUX" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$MG_SP" \
  --mgxs "$MGXS_H5" \
  --tally-name openmc_ce_mg_sph_volume_flux \
  --dataset-name openmc_mg_flux \
  -o "$MG_FLUX" \
  --force

echo
echo "== Compute OpenMC-side SPH, inject it, and convert =="
"$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar "$MGXS_H5" \
  -o "$SPH_SIDECAR" \
  --reference-flux "$CE_FLUX::openmc_volume_flux" \
  --mg-flux "$MG_FLUX::openmc_mg_flux" \
  --table-output "$SPH_TABLE" \
  --flux-normalization auto \
  --require-reference-flux-std-dev \
  --max-reference-flux-std-dev-rel "${MAX_CE_FLUX_REL_STD:-0.20}" \
  --require-mg-flux-std-dev \
  --max-mg-flux-std-dev-rel "${MAX_MG_FLUX_REL_STD:-0.20}" \
  --summary-json "$OUT_DIR/openmc_sph_summary.json" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS_H5" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED" \
  --summary-json "$OUT_DIR/sph_augment_summary.json" \
  --force

"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED" \
  -o "$OUT_DIR/out_with_openmc_sph.mcompo.txt" \
  --check \
  --require-sph

echo
echo "== Summarize OpenMC-side SPH physics handoff =="
"$PYTHON_BIN" "$REPO_ROOT/examples/openmc_ce_mg_33g_sph_minicase/summarize_outputs.py" \
  --handoff-dir "$OUT_DIR"

echo
echo "OpenMC CE/MG 33g SPH colorset minicase complete:"
echo "  MGXS: $MGXS_H5"
echo "  CE flux: $CE_FLUX::openmc_volume_flux"
echo "  MG flux: $MG_FLUX::openmc_mg_flux"
echo "  SPH sidecar: $SPH_SIDECAR"
echo "  DONJON ASCII: $OUT_DIR/out_with_openmc_sph.mcompo.txt"
echo "  physics summary: $OUT_DIR/physics_summary.md"

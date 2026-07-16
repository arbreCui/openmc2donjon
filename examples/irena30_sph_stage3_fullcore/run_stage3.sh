#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_REJECTED_FULLCORE_SPH:-0}" != "1" ]]; then
  echo "This archived OpenMC-MG-side full-core SPH research line has no accepted result." >&2
  echo "Use the 91-position/21-D3-orbit Converter -> native DRAGON SPH route for the current IRENA candidate." >&2
  echo "Set ALLOW_REJECTED_FULLCORE_SPH=1 only to continue the rejected research calculation." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE_DIR="$REPO_ROOT/examples/irena30_sph_stage3_fullcore"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OPENMC_EXEC="${OPENMC_EXEC:-openmc}"
OPENMC_THREADS="${OPENMC_THREADS:-8}"
RUN_ROOT="${RUN_ROOT:-${TMPDIR:-/tmp}/o2d_irena30_stage3}"
CE_CASE_DIR="$RUN_ROOT/ce_case"
OUT_DIR="$RUN_ROOT/handoff"
RECIPE="$EXAMPLE_DIR/export_recipe.py"

# Historical high-statistics CE diagnostic setting.
IRENA_PARTICLES="${IRENA_PARTICLES:-50000}"
IRENA_BATCHES="${IRENA_BATCHES:-130}"
IRENA_INACTIVE="${IRENA_INACTIVE:-30}"
IRENA_SEED="${IRENA_SEED:-47}"
# Assembly-homogenized MG full-core runs (cheap per history; use more particles).
MG_PARTICLES="${MG_PARTICLES:-200000}"
MG_BATCHES="${MG_BATCHES:-130}"
MG_INACTIVE="${MG_INACTIVE:-30}"
# Only the CE/MG rate-preserving SPH fixed-point iteration is permitted.
# Eigenvalue matching and post-hoc global multipliers are deliberately absent.
SPH_STRATEGY="${SPH_STRATEGY:-rate-preserving}"
if [[ "$SPH_STRATEGY" != "rate-preserving" ]]; then
  echo "SPH_STRATEGY must be rate-preserving; empirical global scaling is forbidden" >&2
  exit 2
fi
SPH_ITERATIONS="${SPH_ITERATIONS:-4}"
SPH_DAMPING="${SPH_DAMPING:-0.5}"
MAX_SPH_UPDATE_RESIDUAL="${MAX_SPH_UPDATE_RESIDUAL:-0.02}"
if [[ -z "$MAX_SPH_UPDATE_RESIDUAL" ]]; then
  echo "MAX_SPH_UPDATE_RESIDUAL is mandatory for the diagnostic convergence gate" >&2
  exit 2
fi
FINAL_SPH_KIND="openmc-ce-mg-rate-120deg-tied"
# Resume an interrupted/convergence-extension run at this 1-based iteration.
# Iterations before START must already have their statepoints and sidecars in
# RUN_ROOT.  Set START=ITERATIONS+1 to reuse every completed iteration and run
# only the final-factor evaluation plus handoff/closure stages.  The CE export
# is refreshed, but completed MG solves are not rerun.
SPH_START_ITER="${SPH_START_ITER:-1}"
SPH_TARGET="${SPH_TARGET:-rate}"
if [[ "$SPH_TARGET" != "rate" ]]; then
  echo "SPH_TARGET must be rate in this archived diagnostic workflow" >&2
  exit 2
fi
SPH_FREEZE_GROUPS="${SPH_FREEZE_GROUPS:-}"
# Tie factors over the exact three-member 120-degree rotation orbits.  The
# earlier 91-independent experiment fitted position-wise Monte Carlo noise.
SPH_TIE_120="${SPH_TIE_120:-1}"
SPH_FLUX_FLOOR_REL="${SPH_FLUX_FLOOR_REL:-}"
# Fill criterion for micro-flux noise bins whose rate/flux XS explodes
# (single-score bins carry rel std sqrt(2); measured spike: 52.9 b fuel
# total vs 1.86 b library-wide sane maximum -> SN8 diverges to NaN).
FILL_MAX_TOTAL_REL_STD="${FILL_MAX_TOTAL_REL_STD:-0.5}"
# A noisy analog scatter row can be unphysical even when the track-length
# total is precise.  Rows more than 1% above total are replaced as a complete
# group from the same material macrolib; exact/macrolib rows only differ at
# floating-point roundoff, while the failed Stage 3 run reached +44%.
FILL_MAX_SCATTER_ROW_OVERSHOOT_REL="${FILL_MAX_SCATTER_ROW_OVERSHOOT_REL:-0.01}"
SPH_CLIP_MIN="${SPH_CLIP_MIN:-}"
SPH_CLIP_MAX="${SPH_CLIP_MAX:-}"
if [[ -n "$SPH_FREEZE_GROUPS" || -n "$SPH_FLUX_FLOOR_REL" || -n "$SPH_CLIP_MIN" || -n "$SPH_CLIP_MAX" ]]; then
  echo "this diagnostic reproduction forbids frozen groups, flux floors, and clipping" >&2
  exit 2
fi
MAX_CE_FLUX_REL_STD="${MAX_CE_FLUX_REL_STD:-0.20}"
MAX_MG_FLUX_REL_STD="${MAX_MG_FLUX_REL_STD:-0.20}"
# Each loop statepoint consumes the previous iteration's SPH sidecar.  Run one
# additional MG solve with the final sidecar so the reported corrected-MG k and
# corrected DONJON handoff use exactly the same factor table.
EVALUATE_FINAL_SPH="${EVALUATE_FINAL_SPH:-1}"
# DONJON closure leg (SN8, uncorrected + corrected multicompo). Set
# RUN_DONJON=0 for OpenMC-only runs (e.g. smoke tests).
RUN_DONJON="${RUN_DONJON:-1}"
MCO_CHECK="${MCO_CHECK:-1}"
DONJON_DIR="${DONJON_DIR:-}"
if [[ -z "$DONJON_DIR" && -n "${OPENMC2DONJON_ROOT:-}" ]]; then
  DONJON_DIR="$OPENMC2DONJON_ROOT/Donjon"
fi
# This DONJON build needs SEQ_ASCII paths <=64 characters in practice; stage
# the multicompo and EDI dumps on a short absolute path.
SHORT_BASE="${SHORT_BASE:-${TMPDIR:-/tmp}/o2d_s3}"

CE_SP="$CE_CASE_DIR/statepoint.$IRENA_BATCHES.h5"
MGXS_H5="$OUT_DIR/mgxs_library.h5"
CE_FLUX="$OUT_DIR/openmc_ce_flux.h5"
SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar.h5"
AUGMENTED="$OUT_DIR/mgxs_with_openmc_sph.h5"
CORRECTED_H5="$OUT_DIR/mgxs_sph_corrected.h5"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT/src:$EXAMPLE_DIR${PYTHONPATH:+:$PYTHONPATH}"
IRENA30_MACROLIB="${IRENA30_MACROLIB:-}"
: "${IRENA30_MACROLIB:?Set IRENA30_MACROLIB to the external IRENA material MACROLIB}"
[[ -f "$IRENA30_MACROLIB" ]] || {
  echo "missing IRENA material MACROLIB: $IRENA30_MACROLIB" >&2
  exit 2
}

REUSE_CE="${REUSE_CE:-0}"
if [[ "$REUSE_CE" != "1" || ! -f "$CE_SP" ]]; then
  : "${IRENA_CE_COMPARE_DIR:?Set IRENA_CE_COMPARE_DIR to the external IRENA ce_compare input directory}"
  : "${IRENA30_DIR:?Set IRENA30_DIR to the external IRENA workspace containing geometry_91hex.py}"
  : "${OPENMC_CROSS_SECTIONS:?Set OPENMC_CROSS_SECTIONS to the OpenMC cross_sections.xml file}"
  export IRENA_CE_COMPARE_DIR IRENA30_DIR OPENMC_CROSS_SECTIONS
elif [[ -n "${OPENMC_CROSS_SECTIONS:-}" ]]; then
  export OPENMC_CROSS_SECTIONS
fi

run_openmc_case() {
  (cd "$1" && "$OPENMC_EXEC" -s "$OPENMC_THREADS")
}

echo "== IRENA SPH Stage 3: fine full core vs assembly-homogenized full core =="
echo "run root: $RUN_ROOT"
echo "CE: $IRENA_PARTICLES x $IRENA_BATCHES ($IRENA_INACTIVE inactive, seed $IRENA_SEED); MG: $MG_PARTICLES x $MG_BATCHES"
echo "SPH strategy: $SPH_STRATEGY"
echo "SPH iterations: $SPH_ITERATIONS  damping: $SPH_DAMPING  target: $SPH_TARGET"
echo "SPH start iteration: $SPH_START_ITER"
echo "120-degree SPH tying: $SPH_TIE_120  empirical global scale: forbidden"
echo "frozen groups / flux floor / clipping: forbidden  final-factor MG evaluation: $EVALUATE_FINAL_SPH  DONJON leg: $RUN_DONJON"
mkdir -p "$OUT_DIR"

echo
# REUSE_CE=1 skips the CE build+run when the statepoint already exists,
# so an iteration-stage failure does not force repaying the CE leg.
if [ "$REUSE_CE" = "1" ] && [ -f "$CE_SP" ]; then
  echo "== Reusing existing CE truth statepoint: $CE_SP =="
else
  echo "== Build continuous-energy full-core OpenMC input =="
  "$PYTHON_BIN" "$EXAMPLE_DIR/ce_core_model.py" \
    --case-dir "$CE_CASE_DIR" \
    --batches "$IRENA_BATCHES" \
    --inactive "$IRENA_INACTIVE" \
    --particles "$IRENA_PARTICLES" \
    --seed "$IRENA_SEED"

  echo
  echo "== Run OpenMC CE truth =="
  run_openmc_case "$CE_CASE_DIR"
fi

echo
echo "== Export converter MGXS HDF5 from CE statepoint (91 positions) =="
OPENMC2DONJON_IRENA_SPH3_DIR="$CE_CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$RECIPE" \
  --statepoint "$CE_SP" \
  -o "$MGXS_H5"

echo
echo "== Fill zero-flux thermal groups of the handoff from the MG macrolib =="
"$PYTHON_BIN" -m openmc2donjon.cli fill-zero-flux "$MGXS_H5" \
  --macrolib "$IRENA30_MACROLIB" \
  --max-total-rel-std-dev "$FILL_MAX_TOTAL_REL_STD" \
  --max-scatter-row-overshoot-rel "$FILL_MAX_SCATTER_ROW_OVERSHOOT_REL" \
  --in-place

echo
echo "== Export CE reference region/group flux =="
"$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$CE_SP" \
  --mgxs "$MGXS_H5" \
  --tally-name irena30_sph_stage3_volume_flux \
  --dataset-name openmc_volume_flux \
  -o "$CE_FLUX" \
  --allow-zero-flux \
  --force

echo
echo "== Iterate OpenMC MG macro calculation and OpenMC-side SPH factors =="
if (( SPH_START_ITER < 1 || SPH_START_ITER > SPH_ITERATIONS + 1 )); then
  echo "SPH_START_ITER must satisfy 1 <= start <= SPH_ITERATIONS + 1" >&2
  exit 2
fi
PREVIOUS_SPH=""
MG_UNCORR_SP="$RUN_ROOT/mg_case_iter01/statepoint.$MG_BATCHES.h5"
MG_LAST_SP=""
if (( SPH_START_ITER > 1 )); then
  PREV_L="$(printf "%02d" $((SPH_START_ITER - 1)))"
  PREVIOUS_SPH="$OUT_DIR/openmc_sph_sidecar_iter$PREV_L.h5"
  if [[ ! -f "$PREVIOUS_SPH" || ! -f "$MG_UNCORR_SP" ]]; then
    echo "cannot resume: missing $PREVIOUS_SPH or $MG_UNCORR_SP" >&2
    exit 2
  fi
  echo "resuming from SPH sidecar: $PREVIOUS_SPH"
  MG_LAST_SP="$RUN_ROOT/mg_case_iter$PREV_L/statepoint.$MG_BATCHES.h5"
fi

for ((ITER=SPH_START_ITER; ITER<=SPH_ITERATIONS; ITER++)); do
  L="$(printf "%02d" "$ITER")"
  ITER_MG_CASE_DIR="$RUN_ROOT/mg_case_iter$L"
  ITER_MG_FLUX="$OUT_DIR/openmc_mg_flux_iter$L.h5"
  ITER_SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar_iter$L.h5"
  ITER_SPH_TABLE="$OUT_DIR/openmc_sph_iter$L.csv"
  ITER_SPH_SUMMARY="$OUT_DIR/openmc_sph_summary_iter$L.json"
  ITER_RAW_SPH_SIDECAR="$OUT_DIR/openmc_sph_sidecar_raw_iter$L.h5"
  ITER_RAW_SPH_TABLE="$OUT_DIR/openmc_sph_raw_iter$L.csv"
  ITER_MG_SP="$ITER_MG_CASE_DIR/statepoint.$MG_BATCHES.h5"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: prepare homogenized MG full core =="
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
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: run homogenized MG full core =="
  run_openmc_case "$ITER_MG_CASE_DIR"
  if [[ "$ITER" -eq 1 ]]; then
    MG_UNCORR_SP="$ITER_MG_SP"
  fi
  MG_LAST_SP="$ITER_MG_SP"

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: export MG region/group flux =="
  "$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$ITER_MG_SP" \
    --mgxs "$MGXS_H5" \
    --tally-name irena30_sph_stage3_volume_flux \
    --dataset-name openmc_mg_flux \
    -o "$ITER_MG_FLUX" \
    --allow-zero-flux \
    --force

  echo
  echo "== SPH iteration $ITER/$SPH_ITERATIONS: compute OpenMC-side SPH =="
  SPH_OUTPUT="$ITER_SPH_SIDECAR"
  SPH_TABLE_OUTPUT="$ITER_SPH_TABLE"
  if [[ "$SPH_TIE_120" == "1" ]]; then
    SPH_OUTPUT="$ITER_RAW_SPH_SIDECAR"
    SPH_TABLE_OUTPUT="$ITER_RAW_SPH_TABLE"
  fi
  SPH_ARGS=(
    "$MGXS_H5"
    -o "$SPH_OUTPUT"
    --reference-flux "$CE_FLUX::openmc_volume_flux"
    --mg-flux "$ITER_MG_FLUX::openmc_mg_flux"
    --table-output "$SPH_TABLE_OUTPUT"
    --damping "$SPH_DAMPING"
    --flux-normalization auto
    --sph-target "$SPH_TARGET"
    --zero-flux-policy reject
    --require-reference-flux-std-dev
    --max-reference-flux-std-dev-rel "$MAX_CE_FLUX_REL_STD"
    --require-mg-flux-std-dev
    --max-mg-flux-std-dev-rel "$MAX_MG_FLUX_REL_STD"
    --summary-json "$ITER_SPH_SUMMARY"
    --force
  )
  if [[ -n "$PREVIOUS_SPH" ]]; then
    SPH_ARGS+=(--previous-sph "$PREVIOUS_SPH")
  fi
  "$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar "${SPH_ARGS[@]}"
  if [[ "$SPH_TIE_120" == "1" ]]; then
    echo
    echo "== SPH iteration $ITER/$SPH_ITERATIONS: tie 120-degree symmetry orbits =="
    "$PYTHON_BIN" "$EXAMPLE_DIR/regularize_sph_table.py" "$ITER_RAW_SPH_TABLE" \
      -o "$ITER_SPH_TABLE" \
      --summary-json "$OUT_DIR/sph_symmetry_summary_iter$L.json" \
      --force
    "$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$MGXS_H5" \
      --mode table \
      --table "$ITER_SPH_TABLE" \
      --sph-kind openmc-ce-mg-rate-120deg-tied \
      --sph-real true \
      -o "$ITER_SPH_SIDECAR" \
      --summary-json "$OUT_DIR/sph_tied_sidecar_summary_iter$L.json" \
      --force
  fi
  PREVIOUS_SPH="$ITER_SPH_SIDECAR"
done

if [[ "$SPH_TIE_120" == "1" ]]; then
  FINAL_L="$(printf "%02d" "$SPH_ITERATIONS")"
  FINAL_LOCAL_TABLE="$OUT_DIR/openmc_sph_iter$FINAL_L.csv"
  FINAL_COMBINED_TABLE="$OUT_DIR/openmc_sph_final_combined.csv"
  "$PYTHON_BIN" "$EXAMPLE_DIR/regularize_sph_table.py" "$FINAL_LOCAL_TABLE" \
    -o "$FINAL_COMBINED_TABLE" \
    --summary-json "$OUT_DIR/sph_final_combined_summary.json" \
    --force
  "$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$MGXS_H5" \
    --mode table \
    --table "$FINAL_COMBINED_TABLE" \
    --sph-kind "$FINAL_SPH_KIND" \
    --sph-real true \
    -o "$SPH_SIDECAR" \
    --summary-json "$OUT_DIR/sph_final_sidecar_summary.json" \
    --force
else
  cp "$PREVIOUS_SPH" "$SPH_SIDECAR"
fi

if [[ "$EVALUATE_FINAL_SPH" == "1" ]]; then
  FINAL_MG_CASE_DIR="$RUN_ROOT/mg_case_sph_final"
  FINAL_MG_SP="$FINAL_MG_CASE_DIR/statepoint.$MG_BATCHES.h5"
  FINAL_MG_FLUX="$OUT_DIR/openmc_mg_flux_final.h5"
  echo
  echo "== Evaluate final SPH in the assembly-homogenized MG full core =="
  "$PYTHON_BIN" "$EXAMPLE_DIR/prepare_mg_case.py" \
    --ce-case-dir "$CE_CASE_DIR" \
    --ce-statepoint "$CE_SP" \
    --mg-case-dir "$FINAL_MG_CASE_DIR" \
    --batches "$MG_BATCHES" \
    --inactive "$MG_INACTIVE" \
    --particles "$MG_PARTICLES" \
    --seed $((32 + SPH_ITERATIONS)) \
    --sph-source "$SPH_SIDECAR" \
    --sph-apply-summary-json "$OUT_DIR/sph_apply_summary_final.json" \
    --summary-json "$OUT_DIR/mg_macro_summary_final.json"
  run_openmc_case "$FINAL_MG_CASE_DIR"
  MG_LAST_SP="$FINAL_MG_SP"
  "$PYTHON_BIN" -m openmc2donjon.cli export-volume-flux "$FINAL_MG_SP" \
    --mgxs "$MGXS_H5" \
    --tally-name irena30_sph_stage3_volume_flux \
    --dataset-name openmc_mg_flux \
    -o "$FINAL_MG_FLUX" \
    --allow-zero-flux \
    --force
  "$PYTHON_BIN" "$EXAMPLE_DIR/compare_power_shape.py" \
    --mgxs "$MGXS_H5" \
    --reference-flux "$CE_FLUX::openmc_volume_flux" \
    --uncorrected-flux "$OUT_DIR/openmc_mg_flux_iter01.h5::openmc_mg_flux" \
    --corrected-flux "$FINAL_MG_FLUX::openmc_mg_flux" \
    --corrected-sph "$SPH_SIDECAR" \
    --summary "$RUN_ROOT/stage3_power_shape.json"
elif [[ -z "$MG_LAST_SP" ]]; then
  echo "EVALUATE_FINAL_SPH=0 leaves no corrected MG statepoint" >&2
  exit 2
else
  echo
  echo "WARNING: EVALUATE_FINAL_SPH=0 reports a statepoint that consumed the"
  echo "previous SPH sidecar; use only for smoke/debug runs."
fi

echo
echo "== Augment MGXS with final SPH (NSPH-record artifact) =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS_H5" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED" \
  --summary-json "$OUT_DIR/sph_augment_summary.json" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED" \
  --format macrolib \
  -o "$OUT_DIR/out_with_openmc_sph.macrolib.txt" \
  --overwrite \
  --require-sph

echo
echo "== Apply final SPH to the handoff XS (corrected library) =="
"$PYTHON_BIN" -m openmc2donjon.cli apply-sph "$MGXS_H5" \
  --input-format converter \
  --sph-source "$SPH_SIDECAR" \
  -o "$CORRECTED_H5" \
  --summary-json "$OUT_DIR/sph_apply_corrected_summary.json" \
  --force

echo
echo "== Convert uncorrected + corrected multicompo =="
CHECK_ARGS=()
if [[ "$MCO_CHECK" == "1" ]]; then
  CHECK_ARGS+=(--check)
fi
MCO_UNCORR="$OUT_DIR/irena30_stage3_uncorr.mcompo.txt"
MCO_CORR="$OUT_DIR/irena30_stage3_sphcorr.mcompo.txt"
# ${arr[@]+...} keeps macOS bash 3.2 happy with empty arrays under set -u.
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS_H5" -o "$MCO_UNCORR" --overwrite \
  ${CHECK_ARGS[@]+"${CHECK_ARGS[@]}"}
"$PYTHON_BIN" -m openmc2donjon.cli "$CORRECTED_H5" -o "$MCO_CORR" --overwrite \
  ${CHECK_ARGS[@]+"${CHECK_ARGS[@]}"}

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
SHORT_DIR="$SHORT_BASE/$stamp"
mkdir -p "$SHORT_DIR"
cp "$MCO_UNCORR" "$SHORT_DIR/unc.mcompo.txt"
cp "$MCO_CORR" "$SHORT_DIR/cor.mcompo.txt"
echo "staged multicompos (short paths for DONJON SEQ_ASCII, <=64 chars):"
echo "  $SHORT_DIR/unc.mcompo.txt"
echo "  $SHORT_DIR/cor.mcompo.txt"

COMPARE_ARGS=(
  --ce-statepoint "$CE_SP"
  --mg-uncorrected-statepoint "$MG_UNCORR_SP"
  --mg-corrected-statepoint "$MG_LAST_SP"
  --sph-strategy "$SPH_STRATEGY"
  --summary "$RUN_ROOT/stage3_closure.json"
)
if [[ -f "$RUN_ROOT/stage3_power_shape.json" ]]; then
  COMPARE_ARGS+=(--power-summary "$RUN_ROOT/stage3_power_shape.json")
fi
if [[ -n "$MAX_SPH_UPDATE_RESIDUAL" ]]; then
  COMPARE_ARGS+=(
    --sph-summary "$OUT_DIR/openmc_sph_summary_iter$(printf "%02d" "$SPH_ITERATIONS").json"
    --max-sph-update-residual "$MAX_SPH_UPDATE_RESIDUAL"
  )
fi

if [[ "$RUN_DONJON" == "1" ]]; then
  : "${DONJON_DIR:?Set DONJON_DIR or OPENMC2DONJON_ROOT for the external DONJON checkout}"
  if [[ ! -x "$DONJON_DIR/rdonjon" ]]; then
    echo "missing DONJON runner: $DONJON_DIR/rdonjon" >&2
    exit 1
  fi
  DONJON_PLATFORM="${DONJON_PLATFORM:-$(uname -sm | tr ' ' '_')}"
  DONJON_RESULT_DIR="${DONJON_RESULT_DIR:-$DONJON_DIR/$DONJON_PLATFORM}"
  DECK_DIR="$DONJON_DIR/data/openmc2donjon/irena30_stage3_runs/$stamp"
  mkdir -p "$DECK_DIR"

  run_donjon_deck() {
    local deck="$1"
    local stem
    stem="$(basename "$deck" .x2m)"
    local result="$DONJON_RESULT_DIR/$stem.result"
    rm -f "$result"
    echo
    echo "== Run DONJON: $stem =="
    ( cd "$DONJON_DIR" && ./rdonjon -q "${deck#"$DONJON_DIR/data/"}" )
    if [[ ! -e "$result" ]]; then
      echo "missing DONJON listing: $result" >&2
      exit 1
    fi
    if ! grep -aqi "normal end of execution" "$result"; then
      echo "DONJON listing did not reach normal end: $result" >&2
      exit 1
    fi
  }

  for TAG in uncorr sphcorr; do
    if [[ "$TAG" == "uncorr" ]]; then
      MCO_SHORT="$SHORT_DIR/unc.mcompo.txt"
    else
      MCO_SHORT="$SHORT_DIR/cor.mcompo.txt"
    fi
    "$PYTHON_BIN" "$EXAMPLE_DIR/write_donjon_decks.py" \
      --mco "$MCO_SHORT" \
      --edi "$SHORT_DIR/edi_$TAG.txt" \
      --deck-dir "$DECK_DIR" \
      --stamp "$stamp" \
      --tag "$TAG"
    run_donjon_deck "$DECK_DIR/irena30_stage3_sn8_${TAG}_${stamp}.x2m"
  done
  COMPARE_ARGS+=(
    --sn8-uncorrected-result "$DONJON_RESULT_DIR/irena30_stage3_sn8_uncorr_${stamp}.result"
    --sn8-corrected-result "$DONJON_RESULT_DIR/irena30_stage3_sn8_sphcorr_${stamp}.result"
  )
else
  echo
  echo "DONJON leg skipped (RUN_DONJON=0). To plug it in later, write SN8 decks"
  echo "with write_donjon_decks.py against the staged multicompos above and run"
  echo "them from the configured DONJON_DIR with ./rdonjon (see RUN_DONJON=1 branch)."
fi

echo
echo "== Withdrawn diagnostic closure report =="
"$PYTHON_BIN" "$EXAMPLE_DIR/compare_keff.py" "${COMPARE_ARGS[@]}"

echo
echo "IRENA SPH Stage 3 (full core) workflow finished:"
echo "  handoff: $OUT_DIR"
echo "  permanently withdrawn diagnostic decision: $RUN_ROOT/stage3_closure.json"

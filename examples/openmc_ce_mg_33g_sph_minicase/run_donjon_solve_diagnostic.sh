#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ROOT="${RUN_ROOT:-/private/tmp/openmc2donjon_ce_mg_sph_production_fixed_20260709}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc_ce_mg_33g_sph_donjon_solve_diagnostic}"
RUN_TAG="${RUN_TAG:-openmc_ce_mg_33g_sph_colorset}"
PYTHON_BIN="${PYTHON_BIN:-}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
DONJON_RUNNER="${DONJON_RUNNER:-$DONJON_ROOT/rdonjon}"
MACROLIB_ASCII="${MACROLIB_ASCII:-$RUN_ROOT/handoff/out_with_openmc_sph.macrolib.txt}"
UNCORRECTED_MACROLIB_ASCII="${UNCORRECTED_MACROLIB_ASCII:-$RUN_ROOT/handoff/out_uncorrected.macrolib.txt}"
MGXS_H5="${MGXS_H5:-$RUN_ROOT/handoff/mgxs_library.h5}"
SPH_SIDECAR="${SPH_SIDECAR:-$RUN_ROOT/handoff/openmc_sph_sidecar.h5}"
REFERENCE_FLUX="${REFERENCE_FLUX:-$RUN_ROOT/handoff/openmc_ce_flux.h5}"
REFERENCE_DATASET="${REFERENCE_DATASET:-openmc_volume_flux}"
MG_FLUX="${MG_FLUX:-$RUN_ROOT/handoff/openmc_mg_flux.h5}"
MG_DATASET="${MG_DATASET:-openmc_mg_flux}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

if [[ ! -f "$MACROLIB_ASCII" ]]; then
  echo "OpenMC CE/MG SPH MACROLIB not found:"
  echo "  $MACROLIB_ASCII"
  echo
  echo "Run the minicase workflow first, for example:"
  echo "  RUN_ROOT=$RUN_ROOT bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh"
  exit 1
fi

if [[ ! -f "$REFERENCE_FLUX" || ! -f "$MG_FLUX" ]]; then
  echo "OpenMC CE/MG flux files are required for the solve diagnostic:"
  echo "  reference: $REFERENCE_FLUX"
  echo "  mg:        $MG_FLUX"
  exit 1
fi

if [[ ! -f "$MGXS_H5" || ! -f "$SPH_SIDECAR" ]]; then
  echo "MGXS handoff and SPH sidecar are required to build the corrected solve operator:"
  echo "  mgxs:    $MGXS_H5"
  echo "  sidecar: $SPH_SIDECAR"
  exit 1
fi

if [[ ! -x "$DONJON_RUNNER" ]]; then
  echo "DONJON runner is unavailable; skipping DONJON solve diagnostic"
  exit 0
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

DATA_CASE_DIR="$DONJON_ROOT/data/openmc2donjon/case_runs/openmc_ce_mg_sph_colorset"
mkdir -p "$RUN_DIR" "$DATA_CASE_DIR"

SUMMARY_JSON="$RUN_DIR/donjon_solve_summary.json"
SUMMARY_MD="$RUN_DIR/donjon_solve_summary.md"
SCRIPT_PID="$$"

echo "== OpenMC CE/MG SPH -> DONJON solve diagnostic =="
echo "run_root:      $RUN_ROOT"
echo "corrected:     $MACROLIB_ASCII"
if [[ -f "$UNCORRECTED_MACROLIB_ASCII" ]]; then
  echo "uncorrected:   $UNCORRECTED_MACROLIB_ASCII"
else
  echo "uncorrected:   not available; running corrected-only diagnostic"
fi
echo "reference:     $REFERENCE_FLUX::$REFERENCE_DATASET"
echo "mg flux:       $MG_FLUX::$MG_DATASET"
echo "run_dir:       $RUN_DIR"
echo "donjon:        $DONJON_RUNNER"
echo

make_deck() {
  local label="$1"
  local mode="$2"
  local track_options="$3"
  local macrolib="$4"
  local deck_path="$5"
  local flux_path="$6"
  "$PYTHON_BIN" - "$label" "$mode" "$track_options" "$macrolib" "$deck_path" "$flux_path" <<'PY'
from pathlib import Path
import sys

import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii


label, mode, track_options, macrolib, deck, flux = sys.argv[1:]
macro = read_macrolib_ascii(macrolib)


def _mesh_edges(volumes: np.ndarray) -> list[float]:
    base = float(np.min(volumes[volumes > 0.0]))
    widths = volumes / base
    edges = [0.0]
    for width in widths:
        edges.append(edges[-1] + float(width))
    return edges


def _has_five_region_colorset_volumes(volumes: np.ndarray) -> bool:
    if volumes.shape != (5,) or np.any(volumes <= 0.0):
        return False
    relative = volumes / float(np.min(volumes))
    return bool(np.allclose(relative, np.array([2.0, 1.0, 1.0, 1.0, 1.0])))


def _geometry_card() -> tuple[str, str]:
    nmixtures = macro.nmixtures
    if nmixtures == 3:
        return (
            """CAR2D 3 1
  EDIT 0
  X- REFL X+ REFL
  Y- REFL Y+ REFL
  MIX
  1 2 3
  MESHX
  0.00000000 2.00000000 4.00000000 6.00000000
  MESHY
  0.00000000 4.00000000""",
            "3-region reflective CAR2D slab matching CS_FUEL/CS_MOD/CS_ABS widths",
        )
    if nmixtures == 5 and _has_five_region_colorset_volumes(np.asarray(macro.volume, dtype=float)):
        return (
            """CAR2D 3 2
  EDIT 0
  X- REFL X+ REFL
  Y- REFL Y+ REFL
  MIX
  1 2 4
  1 3 5
  MESHX
  0.00000000 2.00000000 4.00000000 6.00000000
  MESHY
  0.00000000 2.00000000 4.00000000""",
            "5-region CAR2D 3x2 colorset",
        )
    edges = _mesh_edges(np.asarray(macro.volume, dtype=float))
    meshx = " ".join(f"{edge:.8f}" for edge in edges)
    mix = " ".join(str(index) for index in range(1, nmixtures + 1))
    return (
        f"""CAR2D {nmixtures} 1
  EDIT 0
  X- REFL X+ REFL
  Y- REFL Y+ REFL
  MIX
  {mix}
  MESHX
  {meshx}
  MESHY
  0.00000000 4.00000000""",
        f"{nmixtures}-region volume-ratio-preserving reflective CAR2D slab",
    )


geometry_card, geometry_note = _geometry_card()
deck_path = Path(deck)
flux_path = Path(flux)
echo_label = label.upper().replace("-", "_")
echo_mode = mode.upper().replace("-", "_")
# The SPH-corrected case reads a macrolib whose XS were already divided by
# NSPH package-side (apply-sph), so both cases use the same plain deck.
deck_path.write_text(
    f"""* OpenMC CE/MG SPH colorset DONJON {label} {mode} solve diagnostic.
MODULE GEO: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;
LINKED_LIST MACRO SOLVE_MACRO GEOM TRACK SYS FLUX ;
REAL keff ;
SEQ_ASCII MACRO_ASC :: FILE '{macrolib}' ;
SEQ_ASCII FLUX_ASC :: FILE '{flux_path}' ;

MACRO := MACRO_ASC ;
SOLVE_MACRO := MACRO ;
GEOM := GEO: :: {geometry_card}
;
TRACK := TRIVAT: GEOM ::
  TITLE 'OpenMC2DONJON OpenMC-side SPH colorset {label} {mode} diagnostic'
  EDIT 1 MAXR 64
  {track_options} ;
SYS := TRIVAA: SOLVE_MACRO TRACK :: EDIT 0 ;
FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;
ECHO 'OPENMC2DONJON OPENMC SPH COLORSET {echo_label} {echo_mode} K-EFFECTIVE' keff ;
ECHO 'OPENMC2DONJON OPENMC SPH COLORSET GEOMETRY {geometry_note}' ;
FLUX_ASC := FLUX ;
END: ;
""",
    encoding="utf-8",
)
PY
}

run_mode() {
  local label="$1"
  local mode="$2"
  local track_options="$3"
  local macrolib="$4"
  local safe_label="${label//-/_}"
  local deck_rel="openmc2donjon/case_runs/openmc_ce_mg_sph_colorset/${RUN_TAG}_${safe_label}_${mode}.x2m"
  local deck_path="$DONJON_ROOT/data/$deck_rel"
  local flux_path
  flux_path="$(tmp_flux_path "$label" "$mode")"
  local result_path="$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_${safe_label}_${mode}.result"

  rm -f "$flux_path" "$result_path"
  make_deck "$label" "$mode" "$track_options" "$macrolib" "$deck_path" "$flux_path"

  echo "== DONJON $label $mode solve =="
  (
    cd "$DONJON_ROOT"
    ./rdonjon -q "$deck_rel"
  )
  if [[ ! -f "$result_path" ]]; then
    echo "missing DONJON result: $result_path" >&2
    exit 1
  fi
  if ! grep -qi "normal end of execution" "$result_path"; then
    echo "DONJON listing did not reach normal end: $result_path" >&2
    exit 1
  fi
  grep -E "OPENMC2DONJON|normal end" "$result_path" | tail -n 5 || true
}

tmp_flux_path() {
  local label="$1"
  local mode="$2"
  local safe_label="${label//-/_}"
  echo "/tmp/o2d_${safe_label}_${mode}_${SCRIPT_PID}_flux.txt"
}

CASE_ARGS=()
if [[ -f "$UNCORRECTED_MACROLIB_ASCII" ]]; then
  SHORT_UNCORRECTED="/tmp/o2d_uncorrected_${SCRIPT_PID}.macrolib.txt"
  cp "$UNCORRECTED_MACROLIB_ASCII" "$SHORT_UNCORRECTED"
  run_mode uncorrected diffusion "DUAL 1 1" "$SHORT_UNCORRECTED"
  run_mode uncorrected spn3 "DUAL 1 1 SPN 3 SCAT 2" "$SHORT_UNCORRECTED"
  CASE_ARGS+=(
    uncorrected
    "$UNCORRECTED_MACROLIB_ASCII"
    "$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_uncorrected_diffusion.result"
    "$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_uncorrected_spn3.result"
    "$(tmp_flux_path uncorrected diffusion)"
    "$(tmp_flux_path uncorrected spn3)"
  )
fi

# Build the SPH-corrected solve operator with the package divisor convention
# (XS_corrected = XS / NSPH), the same application used by apply-sph and the
# OpenMC MG rerun loop.  DONJON's native DSPH:/MAC: path applies NSPH
# multiplicatively (measured by the consume smoke), which would invert the
# openmc2donjon correction, so the corrected operator is prepared
# package-side and DONJON solves it directly.
APPLIED_H5="/tmp/o2d_sph_applied_${SCRIPT_PID}.h5"
SHORT_CORRECTED="/tmp/o2d_sph_corrected_${SCRIPT_PID}.macrolib.txt"
"$PYTHON_BIN" -m openmc2donjon.cli apply-sph "$MGXS_H5" \
  --sph-source "$SPH_SIDECAR" \
  -o "$APPLIED_H5" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli "$APPLIED_H5" \
  --format macrolib \
  -o "$SHORT_CORRECTED" \
  --check
run_mode sph_corrected diffusion "DUAL 1 1" "$SHORT_CORRECTED"
run_mode sph_corrected spn3 "DUAL 1 1 SPN 3 SCAT 2" "$SHORT_CORRECTED"
CASE_ARGS+=(
  sph_corrected
  "$MACROLIB_ASCII"
  "$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_sph_corrected_diffusion.result"
  "$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_sph_corrected_spn3.result"
  "$(tmp_flux_path sph_corrected diffusion)"
  "$(tmp_flux_path sph_corrected spn3)"
)

"$PYTHON_BIN" - \
  "$RUN_TAG" \
  "$RUN_DIR" \
  "$SUMMARY_JSON" \
  "$SUMMARY_MD" \
  "$REFERENCE_FLUX" \
  "$REFERENCE_DATASET" \
  "$MG_FLUX" \
  "$MG_DATASET" \
  "${CASE_ARGS[@]}" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

import h5py
import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon.macrolib import read_macrolib_ascii


(
    run_tag,
    run_dir_raw,
    summary_json_raw,
    summary_md_raw,
    reference_flux_raw,
    reference_dataset,
    mg_flux_raw,
    mg_dataset,
    *case_args,
) = sys.argv[1:]

if len(case_args) % 6 != 0:
    raise SystemExit("internal error: case arguments must be groups of six")

run_dir = Path(run_dir_raw)
summary_json = Path(summary_json_raw)
summary_md = Path(summary_md_raw)
reference_flux = Path(reference_flux_raw)
mg_flux = Path(mg_flux_raw)


def _read_hdf5_flux(path: Path, dataset: str) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        values = np.asarray(h5[dataset][:], dtype=float)
    if values.ndim != 2:
        raise SystemExit(f"{path}::{dataset} must be rank-2 [mixture, group]")
    return values


def _read_donjon_flux(
    path: Path,
    *,
    nmixtures: int,
    ngroups: int,
    cell_mixture_map: tuple[int, ...],
    cell_weights: tuple[float, ...],
) -> np.ndarray:
    blocks = lcm_ascii.read_lcm_ascii(path)
    rows = [
        block.data
        for block in blocks
        if block.level == 2 and block.type_code == 2 and block.name is None and block.trailing
    ]
    if len(rows) != ngroups:
        raise SystemExit(f"{path}: expected {ngroups} FLUX records, got {len(rows)}")
    values = np.asarray(rows, dtype=float)
    if len(cell_mixture_map) != len(cell_weights):
        raise SystemExit("internal error: cell_mixture_map and cell_weights length mismatch")
    if values.shape[1] < len(cell_mixture_map):
        raise SystemExit(
            f"{path}: flux unknown count {values.shape[1]} < mapped cells {len(cell_mixture_map)}"
        )
    cell_flux = values[:, : len(cell_mixture_map)].T
    mixture_flux = np.zeros((nmixtures, ngroups), dtype=float)
    mixture_weight = np.zeros(nmixtures, dtype=float)
    for cell_index, (mixture, weight) in enumerate(zip(cell_mixture_map, cell_weights, strict=True)):
        if mixture < 1 or mixture > nmixtures:
            raise SystemExit(f"invalid geometry mixture index {mixture} for {nmixtures} mixtures")
        if weight <= 0.0:
            raise SystemExit(f"invalid geometry cell weight {weight}")
        mixture_flux[mixture - 1, :] += weight * cell_flux[cell_index, :]
        mixture_weight[mixture - 1] += weight
    if np.any(mixture_weight <= 0.0):
        raise SystemExit(f"{path}: geometry map does not cover every mixture")
    return mixture_flux / mixture_weight[:, None]


def _keff(path: Path, label: str, mode: str) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "normal end of execution" not in text:
        raise SystemExit(f"DONJON did not end normally: {path}")
    echo_label = label.upper().replace("-", "_")
    echo_mode = mode.upper().replace("-", "_")
    pattern = rf"OPENMC2DONJON OPENMC SPH COLORSET {echo_label} {echo_mode} K-EFFECTIVE\s+([0-9.Ee+-]+)"
    match = re.search(pattern, text)
    if match is None:
        raise SystemExit(f"missing {label} {mode} k-effective echo in {path}")
    value = float(match.group(1))
    if not np.isfinite(value) or value <= 0.0:
        raise SystemExit(f"invalid {label} {mode} k-effective: {value}")
    return value


def _metrics(donjon_flux: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    positive = (donjon_flux > 0.0) & (reference > 0.0)
    if not np.any(positive):
        raise SystemExit("no positive overlapping bins for DONJON/reference flux")
    scale = float(
        np.sum(donjon_flux[positive] * reference[positive])
        / np.sum(donjon_flux[positive] * donjon_flux[positive])
    )
    scaled = scale * donjon_flux
    rel = np.abs(scaled[positive] / reference[positive] - 1.0)

    donjon_shape = donjon_flux / np.sum(donjon_flux, axis=0, keepdims=True)
    ref_shape = reference / np.sum(reference, axis=0, keepdims=True)
    shape_mask = (donjon_shape > 0.0) & (ref_shape > 0.0)
    shape_rel = np.abs(donjon_shape[shape_mask] / ref_shape[shape_mask] - 1.0)
    return {
        "global_scale_to_reference": scale,
        "scaled_flux_max_relative_residual": float(np.max(rel)),
        "scaled_flux_mean_relative_residual": float(np.mean(rel)),
        "flux_shape_max_relative_residual": float(np.max(shape_rel)),
        "flux_shape_mean_relative_residual": float(np.mean(shape_rel)),
    }


def _reaction_rate_metrics(
    donjon_flux: np.ndarray,
    reference: np.ndarray,
    sigma_tallied: np.ndarray,
    nsph: np.ndarray,
    *,
    mask_fraction: float = 0.01,
) -> dict[str, float]:
    """Compare DONJON vs reference region/group reaction rates.

    SPH is a reaction-rate-preservation method, and its correction here is
    mostly spectral (group-wise), so a per-group-normalized flux-shape residual
    cancels it almost exactly.  This metric instead folds the cross sections
    DONJON actually applied (``sigma_tallied / NSPH``) into a reaction rate and
    compares it to the reference reaction rate (``sigma_tallied * reference``)
    under a single GLOBAL normalization, so the spectral SPH effect is visible.
    Bins below ``mask_fraction`` of the per-group peak are dropped so that
    near-zero tails do not dominate the relative residual.
    """

    rr_donjon = (sigma_tallied / nsph) * donjon_flux
    rr_ref = sigma_tallied * reference
    finite = np.isfinite(rr_donjon) & np.isfinite(rr_ref) & (rr_donjon > 0.0) & (rr_ref > 0.0)
    peak = np.maximum(
        np.max(rr_donjon, axis=0, keepdims=True),
        np.max(rr_ref, axis=0, keepdims=True),
    )
    mask = finite & (rr_donjon >= mask_fraction * peak) & (rr_ref >= mask_fraction * peak)
    if not np.any(mask):
        raise SystemExit("no overlapping reaction-rate bins above the mask threshold")
    scale = float(np.sum(rr_donjon[mask] * rr_ref[mask]) / np.sum(rr_donjon[mask] * rr_donjon[mask]))
    rel = np.abs(scale * rr_donjon[mask] / rr_ref[mask] - 1.0)
    return {
        "reaction_rate_global_scale_to_reference": scale,
        "reaction_rate_mean_relative_residual": float(np.mean(rel)),
        "reaction_rate_max_relative_residual": float(np.max(rel)),
        "reaction_rate_mask_fraction": mask_fraction,
        "reaction_rate_valid_bins": int(np.sum(mask)),
    }


def _has_five_region_colorset_volumes(volumes: np.ndarray) -> bool:
    if volumes.shape != (5,) or np.any(volumes <= 0.0):
        return False
    relative = volumes / float(np.min(volumes))
    return bool(np.allclose(relative, np.array([2.0, 1.0, 1.0, 1.0, 1.0])))


def _geometry_metadata(macrolib: Path) -> dict[str, Any]:
    macro = read_macrolib_ascii(macrolib)
    if macro.nmixtures == 3:
        return {
            "description": "3-region reflective CAR2D slab matching CS_FUEL/CS_MOD/CS_ABS widths",
            "cell_mixture_map": (1, 2, 3),
            "cell_weights": (1.0, 1.0, 1.0),
        }
    volumes = np.asarray(macro.volume, dtype=float)
    if macro.nmixtures == 5 and _has_five_region_colorset_volumes(volumes):
        return {
            "description": (
                "5-region reflective CAR2D 3x2 colorset matching OpenMC five_region_2d layout"
            ),
            "cell_mixture_map": (1, 2, 4, 1, 3, 5),
            "cell_weights": (1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        }
    return {
        "description": f"{macro.nmixtures}-region volume-ratio-preserving reflective CAR2D slab",
        "cell_mixture_map": tuple(range(1, macro.nmixtures + 1)),
        "cell_weights": tuple(1.0 for _ in range(macro.nmixtures)),
    }


reference = _read_hdf5_flux(reference_flux, reference_dataset)
mg = _read_hdf5_flux(mg_flux, mg_dataset)
nmixtures, ngroups = reference.shape
if mg.shape != reference.shape:
    raise SystemExit(f"MG flux shape {mg.shape} != reference flux shape {reference.shape}")

cases: dict[str, Any] = {}
for offset in range(0, len(case_args), 6):
    label = case_args[offset]
    macrolib = Path(case_args[offset + 1])
    diffusion_result = Path(case_args[offset + 2])
    spn3_result = Path(case_args[offset + 3])
    diffusion_flux = Path(case_args[offset + 4])
    spn3_flux = Path(case_args[offset + 5])
    geometry = _geometry_metadata(macrolib)
    macro_xs = read_macrolib_ascii(macrolib)
    sigma_tallied = np.asarray(macro_xs.ntot0, dtype=float)
    nsph = (
        np.ones_like(sigma_tallied)
        if macro_xs.sph is None
        else np.asarray(macro_xs.sph, dtype=float)
    )
    modes = {}
    for mode, result, flux_path in (
        ("diffusion", diffusion_result, diffusion_flux),
        ("spn3", spn3_result, spn3_flux),
    ):
        donjon = _read_donjon_flux(
            flux_path,
            nmixtures=nmixtures,
            ngroups=ngroups,
            cell_mixture_map=geometry["cell_mixture_map"],
            cell_weights=geometry["cell_weights"],
        )
        modes[mode] = {
            "k_effective": _keff(result, label, mode),
            "result_path": str(result),
            "flux_ascii_path": str(flux_path),
            "vs_openmc_ce": _metrics(donjon, reference),
            "vs_openmc_mg": _metrics(donjon, mg),
            "reaction_rate_vs_openmc_ce": _reaction_rate_metrics(
                donjon, reference, sigma_tallied, nsph
            ),
            "reaction_rate_vs_openmc_mg": _reaction_rate_metrics(
                donjon, mg, sigma_tallied, nsph
            ),
        }
    cases[label] = {
        "macrolib_ascii": str(macrolib),
        "geometry": geometry["description"],
        "cell_mixture_map": list(geometry["cell_mixture_map"]),
        "modes": modes,
    }

improvement = {}
if "uncorrected" in cases and "sph_corrected" in cases:
    for mode in ("diffusion", "spn3"):
        before_metrics = cases["uncorrected"]["modes"][mode]["vs_openmc_ce"]
        after_metrics = cases["sph_corrected"]["modes"][mode]["vs_openmc_ce"]
        before_mean = before_metrics["flux_shape_mean_relative_residual"]
        after_mean = after_metrics["flux_shape_mean_relative_residual"]
        before_max = before_metrics["flux_shape_max_relative_residual"]
        after_max = after_metrics["flux_shape_max_relative_residual"]
        rr_before = cases["uncorrected"]["modes"][mode]["reaction_rate_vs_openmc_ce"][
            "reaction_rate_mean_relative_residual"
        ]
        rr_after = cases["sph_corrected"]["modes"][mode]["reaction_rate_vs_openmc_ce"][
            "reaction_rate_mean_relative_residual"
        ]
        improvement[mode] = {
            "ce_shape_mean_before": before_mean,
            "ce_shape_mean_after": after_mean,
            "ce_shape_mean_delta": before_mean - after_mean,
            "ce_shape_mean_ratio": after_mean / before_mean if before_mean else None,
            "ce_shape_max_before": before_max,
            "ce_shape_max_after": after_max,
            "ce_shape_max_delta": before_max - after_max,
            "ce_shape_max_ratio": after_max / before_max if before_max else None,
            "reaction_rate_mean_before": rr_before,
            "reaction_rate_mean_after": rr_after,
            "reaction_rate_mean_delta": rr_before - rr_after,
            "reaction_rate_mean_ratio": rr_after / rr_before if rr_before else None,
        }

payload = {
    "schema": "openmc2donjon.openmc-ce-mg-sph-donjon-solve-diagnostic.v2",
    "decision": "donjon_solve_diagnostic_recorded",
    "run_tag": run_tag,
    "run_dir": str(run_dir),
    "reference_flux": str(reference_flux),
    "reference_flux_dataset": reference_dataset,
    "mg_flux": str(mg_flux),
    "mg_flux_dataset": mg_dataset,
    "mixtures": nmixtures,
    "energy_groups": ngroups,
    "note": (
        "This is a DONJON low-order solve diagnostic, not a k-effective "
        "benchmark or an acceptance gate. Flux comparisons remove arbitrary "
        "eigenvector normalization. When an uncorrected MACROLIB is available, "
        "the same DONJON geometry and solver settings are used for both cases."
        " For multi-cell diagnostic geometries, DONJON flux unknowns are "
        "area-weighted back to the OpenMC output-mixture ordering before comparison."
        " The SPH-corrected case solves cross sections divided by NSPH "
        "(the openmc2donjon divisor convention shared with apply-sph); "
        "DONJON's DSPH:/MAC: modules apply NSPH multiplicatively and are "
        "exercised by the consume smoke, not by this solve."
    ),
    "cases": cases,
    "improvement": improvement,
}
if "sph_corrected" in cases:
    payload["modes"] = cases["sph_corrected"]["modes"]
    payload["macrolib_ascii"] = cases["sph_corrected"]["macrolib_ascii"]
    payload["geometry"] = cases["sph_corrected"]["geometry"]
summary_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

lines = [
    "# DONJON Solve Diagnostic",
    "",
    "This diagnostic runs DONJON low-order solves with the OpenMC-side SPH",
    "MACROLIB handoff.  It is not a benchmark acceptance test.",
    "",
    f"- reference flux: `{reference_flux}::{reference_dataset}`",
    f"- mixtures: {nmixtures}",
    f"- groups: {ngroups}",
    "- flux comparison: DONJON cell unknowns are area-weighted back to output mixtures",
    "",
    "| Case | Mode | k-effective | CE shape mean residual | CE shape max residual |",
    "| --- | --- | ---: | ---: | ---: |",
]
for label, case in cases.items():
    for mode in ("diffusion", "spn3"):
        row = case["modes"][mode]
        metrics = row["vs_openmc_ce"]
        lines.append(
            f"| {label} | {mode} | {row['k_effective']:.9g} | "
            f"{metrics['flux_shape_mean_relative_residual']:.6g} | "
            f"{metrics['flux_shape_max_relative_residual']:.6g} |"
        )
if improvement:
    lines.extend(
        [
            "",
            "## SPH-Corrected vs Uncorrected",
            "",
            "| Mode | mean before | mean after | mean delta | max before | max after | max delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for mode, row in improvement.items():
        lines.append(
            f"| {mode} | {row['ce_shape_mean_before']:.6g} | "
            f"{row['ce_shape_mean_after']:.6g} | "
            f"{row['ce_shape_mean_delta']:.6g} | "
            f"{row['ce_shape_max_before']:.6g} | "
            f"{row['ce_shape_max_after']:.6g} | "
            f"{row['ce_shape_max_delta']:.6g} |"
        )
    lines.extend(
        [
            "",
            "## Reaction-Rate vs CE (global-normalized, near-zero bins masked)",
            "",
            "SPH preserves reaction rates, not per-group flux shape, and its correction",
            "here is mostly spectral; this global-normalized reaction-rate residual is the",
            "SPH-relevant metric. A negative delta means SPH made the residual worse.",
            "",
            "| Mode | RR mean before | RR mean after | RR mean delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for mode, row in improvement.items():
        lines.append(
            f"| {mode} | {row['reaction_rate_mean_before']:.6g} | "
            f"{row['reaction_rate_mean_after']:.6g} | "
            f"{row['reaction_rate_mean_delta']:.6g} |"
        )
lines.extend(
    [
        "",
        "The residual is reported so the low-order solve can be reviewed; it is",
        "not forced to pass a tight threshold in this minicase.",
        "",
    ]
)
summary_md.write_text("\n".join(lines), encoding="utf-8")

print(f"wrote DONJON solve diagnostic JSON: {summary_json}")
print(f"wrote DONJON solve diagnostic Markdown: {summary_md}")
for label, case in cases.items():
    for mode in ("diffusion", "spn3"):
        row = case["modes"][mode]
        metrics = row["vs_openmc_ce"]
        rr_metrics = row["reaction_rate_vs_openmc_ce"]
        print(
            "DONJON solve diagnostic: "
            f"{label} {mode} k={row['k_effective']:.9g} "
            f"ce_shape_mean={metrics['flux_shape_mean_relative_residual']:.6g} "
            f"ce_shape_max={metrics['flux_shape_max_relative_residual']:.6g} "
            f"rr_mean={rr_metrics['reaction_rate_mean_relative_residual']:.6g}"
        )
PY

echo
echo "openmc2donjon DONJON solve diagnostic: PASS"
echo "summary_json: $SUMMARY_JSON"

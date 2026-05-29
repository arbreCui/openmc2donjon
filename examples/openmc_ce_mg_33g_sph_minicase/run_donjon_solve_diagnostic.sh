#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ROOT="${RUN_ROOT:-/private/tmp/openmc2donjon_ce_mg_sph_production_candidate2}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc_ce_mg_33g_sph_donjon_solve_diagnostic}"
RUN_TAG="${RUN_TAG:-openmc_ce_mg_33g_sph_colorset}"
PYTHON_BIN="${PYTHON_BIN:-}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
DONJON_RUNNER="${DONJON_RUNNER:-$DONJON_ROOT/rdonjon}"
MACROLIB_ASCII="${MACROLIB_ASCII:-$RUN_ROOT/handoff/out_with_openmc_sph.macrolib.txt}"
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

if [[ ! -x "$DONJON_RUNNER" ]]; then
  echo "DONJON runner is unavailable; skipping DONJON solve diagnostic"
  exit 0
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

DATA_CASE_DIR="$DONJON_ROOT/data/openmc2donjon/case_runs/openmc_ce_mg_sph_colorset"
mkdir -p "$RUN_DIR" "$DATA_CASE_DIR"

SHORT_MACROLIB="/tmp/${RUN_TAG}.macrolib.txt"
cp "$MACROLIB_ASCII" "$SHORT_MACROLIB"

SUMMARY_JSON="$RUN_DIR/donjon_solve_summary.json"
SUMMARY_MD="$RUN_DIR/donjon_solve_summary.md"

echo "== OpenMC CE/MG SPH -> DONJON solve diagnostic =="
echo "run_root:   $RUN_ROOT"
echo "macrolib:   $MACROLIB_ASCII"
echo "reference:  $REFERENCE_FLUX::$REFERENCE_DATASET"
echo "mg flux:    $MG_FLUX::$MG_DATASET"
echo "run_dir:    $RUN_DIR"
echo "donjon:     $DONJON_RUNNER"
echo

make_deck() {
  local mode="$1"
  local track_options="$2"
  local deck_path="$3"
  local flux_path="$4"
  "$PYTHON_BIN" - "$mode" "$track_options" "$SHORT_MACROLIB" "$deck_path" "$flux_path" <<'PY'
from pathlib import Path
import sys

mode, track_options, macrolib, deck, flux = sys.argv[1:]
deck_path = Path(deck)
flux_path = Path(flux)
deck_path.write_text(
    f"""* OpenMC CE/MG SPH colorset 3-region DONJON {mode} solve diagnostic.
MODULE GEO: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;
LINKED_LIST MACRO GEOM TRACK SYS FLUX ;
REAL keff ;
SEQ_ASCII MACRO_ASC :: FILE '{macrolib}' ;
SEQ_ASCII FLUX_ASC :: FILE '{flux_path}' ;

MACRO := MACRO_ASC ;
GEOM := GEO: :: CAR2D 3 1
  EDIT 0
  X- REFL X+ REFL
  Y- REFL Y+ REFL
  MIX
  1 2 3
  MESHX
  0.00000000 2.00000000 4.00000000 6.00000000
  MESHY
  0.00000000 4.00000000
;

TRACK := TRIVAT: GEOM ::
  TITLE 'OpenMC2DONJON OpenMC-side SPH colorset {mode} diagnostic'
  EDIT 1 MAXR 64
  {track_options} ;
SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;
FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;
ECHO 'OPENMC2DONJON OPENMC SPH COLORSET {mode.upper()} K-EFFECTIVE' keff ;
FLUX_ASC := FLUX ;
END: ;
""",
    encoding="utf-8",
)
PY
}

run_mode() {
  local mode="$1"
  local track_options="$2"
  local deck_rel="openmc2donjon/case_runs/openmc_ce_mg_sph_colorset/${RUN_TAG}_${mode}.x2m"
  local deck_path="$DONJON_ROOT/data/$deck_rel"
  local flux_path="/tmp/${RUN_TAG}_${mode}_flux.txt"
  local result_path="$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_${mode}.result"

  rm -f "$flux_path" "$result_path"
  make_deck "$mode" "$track_options" "$deck_path" "$flux_path"

  echo "== DONJON $mode solve =="
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
  grep -E "OPENMC2DONJON|normal end" "$result_path" | tail -n 4 || true
}

run_mode diffusion "DUAL 1 1"
run_mode spn3 "DUAL 1 1 SPN 3 SCAT 2"

"$PYTHON_BIN" - \
  "$RUN_TAG" \
  "$RUN_DIR" \
  "$SUMMARY_JSON" \
  "$SUMMARY_MD" \
  "$REFERENCE_FLUX" \
  "$REFERENCE_DATASET" \
  "$MG_FLUX" \
  "$MG_DATASET" \
  "$MACROLIB_ASCII" \
  "$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_diffusion.result" \
  "$DONJON_ROOT/Darwin_arm64/${RUN_TAG}_spn3.result" \
  "/tmp/${RUN_TAG}_diffusion_flux.txt" \
  "/tmp/${RUN_TAG}_spn3_flux.txt" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

import h5py
import numpy as np

from openmc2donjon import lcm_ascii


(
    run_tag,
    run_dir_raw,
    summary_json_raw,
    summary_md_raw,
    reference_flux_raw,
    reference_dataset,
    mg_flux_raw,
    mg_dataset,
    macrolib_raw,
    diffusion_result_raw,
    spn3_result_raw,
    diffusion_flux_raw,
    spn3_flux_raw,
) = sys.argv[1:]

run_dir = Path(run_dir_raw)
summary_json = Path(summary_json_raw)
summary_md = Path(summary_md_raw)
reference_flux = Path(reference_flux_raw)
mg_flux = Path(mg_flux_raw)
macrolib = Path(macrolib_raw)


def _read_hdf5_flux(path: Path, dataset: str) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        values = np.asarray(h5[dataset][:], dtype=float)
    if values.ndim != 2:
        raise SystemExit(f"{path}::{dataset} must be rank-2 [mixture, group]")
    return values


def _read_donjon_flux(path: Path, *, nmixtures: int, ngroups: int) -> np.ndarray:
    blocks = lcm_ascii.read_lcm_ascii(path)
    rows = [
        block.data
        for block in blocks
        if block.level == 2 and block.type_code == 2 and block.name is None and block.trailing
    ]
    if len(rows) != ngroups:
        raise SystemExit(f"{path}: expected {ngroups} FLUX records, got {len(rows)}")
    values = np.asarray(rows, dtype=float)
    if values.shape[1] < nmixtures:
        raise SystemExit(f"{path}: flux unknown count {values.shape[1]} < mixtures {nmixtures}")
    return values[:, :nmixtures].T


def _keff(path: Path, mode: str) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "normal end of execution" not in text:
        raise SystemExit(f"DONJON did not end normally: {path}")
    pattern = rf"OPENMC2DONJON OPENMC SPH COLORSET {mode.upper()} K-EFFECTIVE\s+([0-9.Ee+-]+)"
    match = re.search(pattern, text)
    if match is None:
        raise SystemExit(f"missing {mode} k-effective echo in {path}")
    value = float(match.group(1))
    if not np.isfinite(value) or value <= 0.0:
        raise SystemExit(f"invalid {mode} k-effective: {value}")
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


reference = _read_hdf5_flux(reference_flux, reference_dataset)
mg = _read_hdf5_flux(mg_flux, mg_dataset)
nmixtures, ngroups = reference.shape
if mg.shape != reference.shape:
    raise SystemExit(f"MG flux shape {mg.shape} != reference flux shape {reference.shape}")

summaries: dict[str, Any] = {}
for mode, result_raw, flux_raw in (
    ("diffusion", diffusion_result_raw, diffusion_flux_raw),
    ("spn3", spn3_result_raw, spn3_flux_raw),
):
    result = Path(result_raw)
    flux_path = Path(flux_raw)
    donjon = _read_donjon_flux(flux_path, nmixtures=nmixtures, ngroups=ngroups)
    summaries[mode] = {
        "k_effective": _keff(result, mode),
        "result_path": str(result),
        "flux_ascii_path": str(flux_path),
        "vs_openmc_ce": _metrics(donjon, reference),
        "vs_openmc_mg": _metrics(donjon, mg),
    }

payload = {
    "schema": "openmc2donjon.openmc-ce-mg-sph-donjon-solve-diagnostic.v1",
    "decision": "donjon_solve_diagnostic_recorded",
    "run_tag": run_tag,
    "run_dir": str(run_dir),
    "macrolib_ascii": str(macrolib),
    "reference_flux": str(reference_flux),
    "reference_flux_dataset": reference_dataset,
    "mg_flux": str(mg_flux),
    "mg_flux_dataset": mg_dataset,
    "mixtures": nmixtures,
    "energy_groups": ngroups,
    "geometry": "3-region reflective CAR2D slab matching CS_FUEL/CS_MOD/CS_ABS widths",
    "note": (
        "This is a DONJON low-order solve diagnostic, not a k-effective "
        "benchmark or an acceptance gate. Flux comparisons use the first "
        "three KEYFLX unknowns and remove arbitrary eigenvector normalization."
    ),
    "modes": summaries,
}
summary_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

lines = [
    "# DONJON Solve Diagnostic",
    "",
    "This diagnostic proves that DONJON can run a low-order solve with the",
    "OpenMC-side SPH MACROLIB.  It is not a benchmark acceptance test.",
    "",
    f"- MACROLIB: `{macrolib}`",
    f"- reference flux: `{reference_flux}::{reference_dataset}`",
    f"- mixtures: {nmixtures}",
    f"- groups: {ngroups}",
    "",
    "| Mode | k-effective | CE shape mean residual | CE shape max residual |",
    "| --- | ---: | ---: | ---: |",
]
for mode in ("diffusion", "spn3"):
    row = summaries[mode]
    metrics = row["vs_openmc_ce"]
    lines.append(
        f"| {mode} | {row['k_effective']:.9g} | "
        f"{metrics['flux_shape_mean_relative_residual']:.6g} | "
        f"{metrics['flux_shape_max_relative_residual']:.6g} |"
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
for mode in ("diffusion", "spn3"):
    row = summaries[mode]
    metrics = row["vs_openmc_ce"]
    print(
        "DONJON solve diagnostic: "
        f"{mode} k={row['k_effective']:.9g} "
        f"ce_shape_mean={metrics['flux_shape_mean_relative_residual']:.6g} "
        f"ce_shape_max={metrics['flux_shape_max_relative_residual']:.6g}"
    )
PY

echo
echo "openmc2donjon DONJON solve diagnostic: PASS"
echo "summary_json: $SUMMARY_JSON"

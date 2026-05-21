#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_sph_iteration_flux}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
DONJON_RUNNER="${DONJON_RUNNER:-$DONJON_ROOT/rdonjon}"
C5G7_ACCEPTED_H5="${C5G7_ACCEPTED_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5}"
C5G7_DONJON_FLUX_H5="${C5G7_DONJON_FLUX_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_homogeneous_face_flux_donjon.h5}"
C5G7_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_C5G7_SCATTER_ROW_BALANCE_FAIL:-1e-8}"

NEXT_SPH_TABLE="$RUN_DIR/c5g7_next_sph_from_donjon_flux.csv"
SPH_SIDECAR="$RUN_DIR/c5g7_next_sph_from_donjon_flux.sidecar.h5"
AUGMENTED_H5="$RUN_DIR/c5g7_with_next_sph_from_donjon_flux.h5"
BASE_MACROLIB="$RUN_DIR/c5g7_base.macrolib.txt"
MACROLIB="$RUN_DIR/c5g7_next_sph_from_donjon_flux.macrolib.txt"
ITERATION_SUMMARY="$RUN_DIR/c5g7_sph_iteration_summary.json"
SPH_SIDECAR_SUMMARY="$RUN_DIR/c5g7_sph_sidecar_summary.json"
SPH_AUGMENT_SUMMARY="$RUN_DIR/c5g7_sph_augment_summary.json"
RESPONSE_SUMMARY="$RUN_DIR/c5g7_sph_iteration_solver_response_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon C5G7 SPH iteration from DONJON flux smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "donjon: $DONJON_RUNNER"
echo "mgxs: $C5G7_ACCEPTED_H5"
echo "flux: $C5G7_DONJON_FLUX_H5"

if [[ ! -e "$C5G7_ACCEPTED_H5" ]]; then
  echo "missing C5G7 accepted MGXS: $C5G7_ACCEPTED_H5" >&2
  exit 1
fi
if [[ ! -e "$C5G7_DONJON_FLUX_H5" ]]; then
  echo "missing C5G7 DONJON flux HDF5: $C5G7_DONJON_FLUX_H5" >&2
  exit 1
fi

echo
echo "== Build next SPH table from OpenMC/DONJON volume fluxes =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-update-table "$C5G7_ACCEPTED_H5" \
  -o "$NEXT_SPH_TABLE" \
  --reference-flux "$C5G7_DONJON_FLUX_H5::openmc_volume_flux" \
  --low-order-flux "$C5G7_DONJON_FLUX_H5::donjon_volume_flux" \
  --damping 0.5 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --source-label "C5G7 OpenMC/DONJON volume-flux SPH iteration smoke" \
  --summary-json "$ITERATION_SUMMARY" \
  --force

echo
echo "== Canonicalize next SPH table =="
"$PYTHON_BIN" -m openmc2donjon.cli make-sph-sidecar "$C5G7_ACCEPTED_H5" \
  -o "$SPH_SIDECAR" \
  --mode table \
  --table "$NEXT_SPH_TABLE" \
  --sph-kind c5g7-donjon-flux-iteration-smoke \
  --sph-real false \
  --sph-applied false \
  --summary-json "$SPH_SIDECAR_SUMMARY" \
  --force

echo
echo "== Inject and convert next SPH =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$C5G7_ACCEPTED_H5" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED_H5" \
  --summary-json "$SPH_AUGMENT_SUMMARY" \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$C5G7_ACCEPTED_H5" -o "$BASE_MACROLIB" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL"
"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$AUGMENTED_H5" -o "$MACROLIB" \
  --check \
  --require-volume \
  --require-transport-dataset \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --require-sph \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL"

echo
echo "== Validate C5G7 SPH iteration artifacts =="
"$PYTHON_BIN" - "$NEXT_SPH_TABLE" "$SPH_SIDECAR" "$AUGMENTED_H5" "$MACROLIB" "$ITERATION_SUMMARY" "$SPH_SIDECAR_SUMMARY" "$SPH_AUGMENT_SUMMARY" <<'PY'
import csv
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

(
    table_path,
    sidecar_path,
    augmented_path,
    macrolib_path,
    iteration_summary_path,
    sidecar_summary_path,
    augment_summary_path,
) = [Path(value) for value in sys.argv[1:]]

iteration_summary = json.loads(iteration_summary_path.read_text(encoding="utf-8"))
if iteration_summary["decision"] != "openmc2donjon_sph_iteration_table_passed":
    raise SystemExit(f"SPH iteration summary failed: {iteration_summary}")
if iteration_summary["reference_flux_dataset"] != "openmc_volume_flux":
    raise SystemExit("reference flux dataset mismatch")
if iteration_summary["low_order_flux_dataset"] != "donjon_volume_flux":
    raise SystemExit("low-order flux dataset mismatch")
if iteration_summary["mixture_count"] != 9 or iteration_summary["energy_groups"] != 7:
    raise SystemExit(f"unexpected C5G7 shape metadata: {iteration_summary}")
if iteration_summary["sph_minimum"] <= 1.0:
    raise SystemExit(f"unexpected non-amplifying SPH range: {iteration_summary}")

rows = list(csv.DictReader(table_path.open("r", encoding="utf-8", newline="")))
if len(rows) != 9 * 7:
    raise SystemExit(f"unexpected SPH table row count: {len(rows)}")

with h5py.File(sidecar_path, "r") as sidecar:
    sph = sidecar["sph"][:]
    names = list(iteration_summary["mixture_names"])
    if sidecar.attrs["sph_kind"] != "c5g7-donjon-flux-iteration-smoke":
        raise SystemExit("SPH sidecar kind mismatch")
    if sidecar.attrs["sph_real"]:
        raise SystemExit("SPH smoke sidecar must be marked sph_real=false")
    if sidecar.attrs.get("source_table") != str(table_path):
        raise SystemExit("SPH sidecar source_table mismatch")
    if sph.shape != (9, 7):
        raise SystemExit(f"unexpected SPH shape: {sph.shape}")
    if float(np.min(sph)) <= 1.0 or float(np.max(sph)) >= 2.0:
        raise SystemExit(f"unexpected SPH range: {float(np.min(sph))}..{float(np.max(sph))}")

with h5py.File(augmented_path, "r") as augmented:
    for mix_index, name in enumerate(names):
        np.testing.assert_allclose(augmented[f"mixtures/{name}/sph"][:], sph[mix_index])
    if augmented.attrs["sph_kind"] != "c5g7-donjon-flux-iteration-smoke":
        raise SystemExit("augmented HDF5 SPH kind mismatch")

macrolib = read_macrolib_ascii(macrolib_path)
np.testing.assert_allclose(macrolib.sph, sph)
for path, decision in {
    sidecar_summary_path: "openmc2donjon_sph_sidecar_passed",
    augment_summary_path: "openmc2donjon_sph_augment_passed",
}.items():
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["decision"] != decision:
        raise SystemExit(f"{path.name}: expected {decision}, got {payload['decision']}")

print(
    "C5G7 SPH iteration from DONJON flux OK: "
    f"mixtures={sph.shape[0]} groups={sph.shape[1]} "
    f"sph_range={float(np.min(sph)):.6g}..{float(np.max(sph)):.6g}"
)
PY

echo
echo "== DONJON C5G7 SPH iteration solver response =="
if [[ ! -x "$DONJON_RUNNER" ]]; then
  echo "DONJON runner is unavailable; skipping C5G7 SPH iteration solver response"
else
  CASE_ID="${RUN_TAG:-c5g7_sph_iteration_flux_response_smoke}"
  DATA_CASE_DIR="$DONJON_ROOT/data/openmc2donjon/case_runs/c5g7_sph_iteration_flux_response"
  APPLY_DECK_REL="openmc2donjon/case_runs/c5g7_sph_iteration_flux_response/${CASE_ID}_apply.x2m"
  APPLY_DECK_PATH="$DONJON_ROOT/data/$APPLY_DECK_REL"
  SOLVE_DECK_REL="openmc2donjon/case_runs/c5g7_sph_iteration_flux_response/${CASE_ID}_solve.x2m"
  SOLVE_DECK_PATH="$DONJON_ROOT/data/$SOLVE_DECK_REL"
  RESULT_PATH="$DONJON_ROOT/Darwin_arm64/${CASE_ID}_solve.result"
  SHORT_BASE="/tmp/${CASE_ID}.base.macrolib.txt"
  SHORT_SPH="/tmp/${CASE_ID}.with_sph.macrolib.txt"
  CORRECTED_PN="/tmp/${CASE_ID}.sph_pn.macrolib.txt"
  CORRECTED_SN="/tmp/${CASE_ID}.sph_sn.macrolib.txt"

  mkdir -p "$DATA_CASE_DIR"
  cp "$BASE_MACROLIB" "$SHORT_BASE"
  cp "$MACROLIB" "$SHORT_SPH"
  rm -f "$CORRECTED_PN" "$CORRECTED_SN"

  "$PYTHON_BIN" - "$APPLY_DECK_PATH" "$SHORT_SPH" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import sys

deck = Path(sys.argv[1])
sph_macrolib = Path(sys.argv[2])
corrected_pn = Path(sys.argv[3])
corrected_sn = Path(sys.argv[4])
deck.write_text(
    f"""* C5G7 assembly-wise flux-derived SPH update through DONJON DSPH/MAC.
MODULE DSPH: MAC: END: ABORT: ;
LINKED_LIST SPHSRC DMACROPN OPTIMPN DMACROSN OPTIMSN MACROPN MACROSN ;
SEQ_ASCII SPH_ASC :: FILE '{sph_macrolib}' ;
SEQ_ASCII PN_ASC :: FILE '{corrected_pn}' ;
SEQ_ASCII SN_ASC :: FILE '{corrected_sn}' ;

SPHSRC := SPH_ASC ;
DMACROPN OPTIMPN := DSPH: SPHSRC :: EDIT 1 SPH PN ;
MACROPN := SPHSRC ;
MACROPN := MAC: MACROPN OPTIMPN ;
PN_ASC := MACROPN ;
DMACROSN OPTIMSN := DSPH: SPHSRC :: EDIT 1 SPH SN ;
MACROSN := SPHSRC ;
MACROSN := MAC: MACROSN OPTIMSN ;
SN_ASC := MACROSN ;
END: ;
""",
    encoding="utf-8",
)
PY

  "$PYTHON_BIN" - "$SOLVE_DECK_PATH" "$SHORT_BASE" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import sys

deck = Path(sys.argv[1])
base_macrolib = Path(sys.argv[2])
corrected_pn = Path(sys.argv[3])
corrected_sn = Path(sys.argv[4])
deck.write_text(
    f"""* C5G7 assembly-wise solver response to one flux-derived SPH update.
MODULE GEO: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;
LINKED_LIST BASE MACROPN MACROSN GEOM TRACK SYSB FLUXB SYSPN FLUXPN SYSSN FLUXSN ;
REAL keff_base keff_pn keff_sn ;
SEQ_ASCII BASE_ASC :: FILE '{base_macrolib}' ;
SEQ_ASCII PN_ASC :: FILE '{corrected_pn}' ;
SEQ_ASCII SN_ASC :: FILE '{corrected_sn}' ;

BASE := BASE_ASC ;
MACROPN := PN_ASC ;
MACROSN := SN_ASC ;

GEOM := GEO: :: CAR2D 3 3
  EDIT 0
  X- REFL X+ VOID
  Y- REFL Y+ VOID
  MIX
  1 2 3
  4 5 6
  7 8 9
  MESHX
  0.00000000 21.42000000 42.84000000 64.26000000
  MESHY
  0.00000000 21.42000000 42.84000000 64.26000000
;

TRACK := TRIVAT: GEOM ::
  TITLE 'C5G7 OpenMC assembly-wise flux-derived SPH solver response' EDIT 1 MAXR 109
  DUAL 1 1 ;

SYSB := TRIVAA: BASE TRACK :: EDIT 0 ;
FLUXB := FLUD: SYSB TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXB :: GETVAL 'K-EFFECTIVE ' 1 >>keff_base<< ;
ECHO 'OPENMC2DONJON C5G7 SPH ITERATION BASE K-EFFECTIVE' keff_base ;
SYSPN := TRIVAA: MACROPN TRACK :: EDIT 0 ;
FLUXPN := FLUD: SYSPN TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXPN :: GETVAL 'K-EFFECTIVE ' 1 >>keff_pn<< ;
ECHO 'OPENMC2DONJON C5G7 SPH ITERATION PN K-EFFECTIVE' keff_pn ;
SYSSN := TRIVAA: MACROSN TRACK :: EDIT 0 ;
FLUXSN := FLUD: SYSSN TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXSN :: GETVAL 'K-EFFECTIVE ' 1 >>keff_sn<< ;
ECHO 'OPENMC2DONJON C5G7 SPH ITERATION SN K-EFFECTIVE' keff_sn ;
END: ;
""",
    encoding="utf-8",
)
PY

  (
    cd "$DONJON_ROOT"
    ./rdonjon -q "$APPLY_DECK_REL"
  )
  (
    cd "$DONJON_ROOT"
    ./rdonjon -q "$SOLVE_DECK_REL"
  )

  "$PYTHON_BIN" - "$RESULT_PATH" "$BASE_MACROLIB" "$MACROLIB" "$CORRECTED_PN" "$CORRECTED_SN" "$RESPONSE_SUMMARY" <<'PY'
import json
from pathlib import Path
import re
import sys

import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

(
    result_path,
    base_path,
    sph_path,
    corrected_pn_path,
    corrected_sn_path,
    summary_path,
) = [Path(value) for value in sys.argv[1:]]

text = result_path.read_text(encoding="utf-8", errors="replace")
if "normal end of execution" not in text:
    raise SystemExit(f"DONJON listing did not end normally: {result_path}")

keff = {}
for label in ("BASE", "PN", "SN"):
    pattern = rf"OPENMC2DONJON C5G7 SPH ITERATION {label} K-EFFECTIVE\s+([0-9.Ee+-]+)"
    match = re.search(pattern, text)
    if match is None:
        raise SystemExit(f"missing C5G7 SPH iteration {label} echo in {result_path}")
    keff[label.lower()] = float(match.group(1))
for label, value in keff.items():
    if not np.isfinite(value) or value <= 0.0:
        raise SystemExit(f"invalid C5G7 {label} k-effective: {value}")

base = read_macrolib_ascii(base_path)
sph_source = read_macrolib_ascii(sph_path)
corrected_pn = read_macrolib_ascii(corrected_pn_path)
corrected_sn = read_macrolib_ascii(corrected_sn_path)
if sph_source.sph is None:
    raise SystemExit("SPH source macrolib is missing NSPH")
if corrected_pn.state_vector[13] != 1 or corrected_sn.state_vector[13] != 1:
    raise SystemExit("corrected macrolib SPH state-vector flag is not set")
if corrected_pn.sph is None or corrected_sn.sph is None:
    raise SystemExit("corrected macrolib is missing NSPH")

np.testing.assert_allclose(corrected_pn.sph, sph_source.sph, rtol=1.0e-7, atol=1.0e-7)
np.testing.assert_allclose(corrected_sn.sph, sph_source.sph, rtol=1.0e-7, atol=1.0e-7)
if np.allclose(sph_source.sph, 1.0):
    raise SystemExit("C5G7 SPH source is unexpectedly unity")

pn_ntot_delta = float(np.max(np.abs(corrected_pn.ntot0 - base.ntot0)))
sn_ntot_delta = float(np.max(np.abs(corrected_sn.ntot0 - base.ntot0)))
if pn_ntot_delta <= 0.0:
    raise SystemExit("PN-corrected C5G7 macrolib did not perturb NTOT0")

delta_pn_pcm = (keff["pn"] - keff["base"]) / keff["base"] * 1.0e5
delta_sn_pcm = (keff["sn"] - keff["base"]) / keff["base"] * 1.0e5
if abs(delta_pn_pcm) < 1.0 and abs(delta_sn_pcm) < 1.0:
    raise SystemExit(
        "C5G7 flux-derived SPH correction produced no meaningful solver response: "
        f"PN={delta_pn_pcm:.6g} pcm SN={delta_sn_pcm:.6g} pcm"
    )

payload = {
    "decision": "openmc2donjon_c5g7_sph_iteration_solver_response_passed",
    "base_keff": keff["base"],
    "pn_keff": keff["pn"],
    "sn_keff": keff["sn"],
    "delta_pn_pcm": delta_pn_pcm,
    "delta_sn_pcm": delta_sn_pcm,
    "sph_minimum": float(np.min(sph_source.sph)),
    "sph_maximum": float(np.max(sph_source.sph)),
    "pn_ntot0_max_delta": pn_ntot_delta,
    "sn_ntot0_max_delta": sn_ntot_delta,
    "result": str(result_path),
}
summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(
    "C5G7 flux-derived SPH solver response: "
    f"base={keff['base']:.9g} pn={keff['pn']:.9g} sn={keff['sn']:.9g} "
    f"delta_pn_pcm={delta_pn_pcm:.6g} delta_sn_pcm={delta_sn_pcm:.6g} "
    f"sph_range={float(np.min(sph_source.sph)):.6g}..{float(np.max(sph_source.sph)):.6g} "
    f"pn_ntot0_max_delta={pn_ntot_delta:.6g} sn_ntot0_max_delta={sn_ntot_delta:.6g}"
)
PY
fi

echo
echo "openmc2donjon C5G7 SPH iteration from DONJON flux smoke: PASS"

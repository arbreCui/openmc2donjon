#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_sph_solver_response_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
DONJON_RUNNER="${DONJON_RUNNER:-$DONJON_ROOT/rdonjon}"
MGXS="${C5G7_ACCEPTED_H5:-$REPO_ROOT/examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5}"
C5G7_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_C5G7_SCATTER_ROW_BALANCE_FAIL:-1e-8}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon C5G7 SPH solver response smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "donjon: $DONJON_RUNNER"
echo "mgxs: $MGXS"

if [[ ! -f "$MGXS" ]]; then
  echo "C5G7 accepted HDF5 is unavailable; skipping C5G7 SPH solver response smoke"
  exit 0
fi
if [[ ! -x "$DONJON_RUNNER" ]]; then
  echo "DONJON runner is unavailable; skipping C5G7 SPH solver response smoke"
  exit 0
fi

SPH_SIDECAR="$RUN_DIR/c5g7_nonunity_sph_sidecar.h5"
SPH_AUGMENTED="$RUN_DIR/c5g7_with_nonunity_sph.h5"
BASE_MACROLIB="$RUN_DIR/c5g7_base.macrolib.txt"
SPH_MACROLIB="$RUN_DIR/c5g7_with_nonunity_sph.macrolib.txt"
CHECK_JSON="$RUN_DIR/c5g7_sph_check_summary.json"

echo
echo "== Build non-unity SPH sidecar =="
"$PYTHON_BIN" - "$MGXS" "$SPH_SIDECAR" <<'PY'
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon import __version__

source = Path(sys.argv[1])
sidecar = Path(sys.argv[2])
with h5py.File(source, "r") as h5:
    mixture_names = tuple(str(name) for name in h5["mixtures"].keys())
    ngroups = int(h5.attrs["energy_groups"])

values = np.ones((len(mixture_names), ngroups), dtype=float)
for mixture_index in range(len(mixture_names)):
    for group_index in range(ngroups):
        # Deterministic, bounded perturbation: large enough to move k-eff,
        # small enough to stay in a physically plausible smoke-test range.
        values[mixture_index, group_index] += (
            0.010 * ((mixture_index % 3) - 1)
            + 0.003 * ((group_index % 4) - 1.5)
        )

if np.allclose(values, 1.0):
    raise SystemExit("constructed SPH sidecar is unexpectedly unity")
if float(np.min(values)) <= 0.0:
    raise SystemExit("constructed SPH sidecar contains non-positive values")

sidecar.parent.mkdir(parents=True, exist_ok=True)
with h5py.File(sidecar, "w") as h5:
    h5.attrs["schema"] = "openmc2donjon.sph-sidecar.v1"
    h5.attrs["package_version"] = __version__
    h5.attrs["sph_kind"] = "c5g7-nonunity-smoke"
    h5.attrs["sph_real"] = False
    h5.attrs["sph_applied"] = False
    h5.attrs["source_mgxs"] = str(source)
    dataset = h5.create_dataset("sph", data=values)
    dataset.attrs.create(
        "mixture_names",
        np.asarray(mixture_names, dtype=h5py.string_dtype("utf-8")),
    )

print(
    "C5G7 non-unity SPH sidecar: "
    f"mixtures={len(mixture_names)} groups={ngroups} "
    f"range={float(np.min(values)):.6g}..{float(np.max(values)):.6g}"
)
PY

echo
echo "== Convert base and SPH macrolibs =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS" \
  --sph-source "$SPH_SIDECAR" \
  -o "$SPH_AUGMENTED" \
  --sph-kind c5g7-nonunity-smoke \
  --sph-real false \
  --sph-applied false \
  --force
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" \
  --format macrolib \
  -o "$BASE_MACROLIB" \
  --check \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL"
"$PYTHON_BIN" -m openmc2donjon.cli "$SPH_AUGMENTED" \
  --format macrolib \
  -o "$SPH_MACROLIB" \
  --check \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --require-volume \
  --require-transport-dataset \
  --require-sph \
  --scatter-row-balance-fail "$C5G7_SCATTER_ROW_BALANCE_FAIL" \
  --check-summary-json "$CHECK_JSON"

CASE_ID="${RUN_TAG:-c5g7_sph_solver_response_smoke}"
DATA_CASE_DIR="$DONJON_ROOT/data/openmc2donjon/case_runs/c5g7_sph_solver_response"
APPLY_DECK_REL="openmc2donjon/case_runs/c5g7_sph_solver_response/${CASE_ID}_apply.x2m"
APPLY_DECK_PATH="$DONJON_ROOT/data/$APPLY_DECK_REL"
SOLVE_DECK_REL="openmc2donjon/case_runs/c5g7_sph_solver_response/${CASE_ID}_solve.x2m"
SOLVE_DECK_PATH="$DONJON_ROOT/data/$SOLVE_DECK_REL"
RESULT_PATH="$DONJON_ROOT/Darwin_arm64/${CASE_ID}_solve.result"
SHORT_BASE="/tmp/${CASE_ID}.base.macrolib.txt"
SHORT_SPH="/tmp/${CASE_ID}.with_sph.macrolib.txt"
CORRECTED_PN="/tmp/${CASE_ID}.sph_pn.macrolib.txt"
CORRECTED_SN="/tmp/${CASE_ID}.sph_sn.macrolib.txt"

mkdir -p "$DATA_CASE_DIR"
cp "$BASE_MACROLIB" "$SHORT_BASE"
cp "$SPH_MACROLIB" "$SHORT_SPH"
rm -f "$CORRECTED_PN" "$CORRECTED_SN"

"$PYTHON_BIN" - "$APPLY_DECK_PATH" "$SHORT_SPH" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import sys

deck = Path(sys.argv[1])
sph_macrolib = Path(sys.argv[2])
corrected_pn = Path(sys.argv[3])
corrected_sn = Path(sys.argv[4])
deck.write_text(
    f"""* C5G7 assembly-wise root L_MACROLIB SPH update through DONJON DSPH/MAC.
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
    f"""* C5G7 assembly-wise root L_MACROLIB SPH solver response after DSPH/MAC update.
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
  TITLE 'C5G7 OpenMC assembly-wise SPH solver response smoke' EDIT 1 MAXR 109
  DUAL 1 1 ;

SYSB := TRIVAA: BASE TRACK :: EDIT 0 ;
FLUXB := FLUD: SYSB TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXB :: GETVAL 'K-EFFECTIVE ' 1 >>keff_base<< ;
ECHO 'OPENMC2DONJON C5G7 SPH SOLVER BASE K-EFFECTIVE' keff_base ;
SYSPN := TRIVAA: MACROPN TRACK :: EDIT 0 ;
FLUXPN := FLUD: SYSPN TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXPN :: GETVAL 'K-EFFECTIVE ' 1 >>keff_pn<< ;
ECHO 'OPENMC2DONJON C5G7 SPH SOLVER PN K-EFFECTIVE' keff_pn ;
SYSSN := TRIVAA: MACROSN TRACK :: EDIT 0 ;
FLUXSN := FLUD: SYSSN TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXSN :: GETVAL 'K-EFFECTIVE ' 1 >>keff_sn<< ;
ECHO 'OPENMC2DONJON C5G7 SPH SOLVER SN K-EFFECTIVE' keff_sn ;
END: ;
""",
    encoding="utf-8",
)
PY

echo
echo "== DONJON C5G7 SPH update =="
(
  cd "$DONJON_ROOT"
  ./rdonjon -q "$APPLY_DECK_REL"
)

echo
echo "== DONJON C5G7 SPH solver response =="
(
  cd "$DONJON_ROOT"
  ./rdonjon -q "$SOLVE_DECK_REL"
)

"$PYTHON_BIN" - "$RESULT_PATH" "$BASE_MACROLIB" "$SPH_MACROLIB" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import re
import sys

import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

result = Path(sys.argv[1])
base_path = Path(sys.argv[2])
sph_path = Path(sys.argv[3])
corrected_pn_path = Path(sys.argv[4])
corrected_sn_path = Path(sys.argv[5])

text = result.read_text(encoding="utf-8", errors="replace")
if "normal end of execution" not in text:
    raise SystemExit(f"DONJON listing did not end normally: {result}")

keff = {}
for label in ("BASE", "PN", "SN"):
    pattern = rf"OPENMC2DONJON C5G7 SPH SOLVER {label} K-EFFECTIVE\s+([0-9.Ee+-]+)"
    match = re.search(pattern, text)
    if match is None:
        raise SystemExit(f"missing C5G7 SPH solver {label} echo in {result}")
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
np.testing.assert_allclose(corrected_sn.ntot0, base.ntot0, rtol=1.0e-6, atol=1.0e-7)

delta_pn_pcm = (keff["pn"] - keff["base"]) / keff["base"] * 1.0e5
delta_sn_pcm = (keff["sn"] - keff["base"]) / keff["base"] * 1.0e5
if abs(delta_pn_pcm) < 1.0:
    raise SystemExit(
        "C5G7 PN SPH correction produced no meaningful solver response: "
        f"delta={delta_pn_pcm:.6g} pcm"
    )

print(
    "C5G7 SPH solver response: "
    f"base={keff['base']:.9g} pn={keff['pn']:.9g} sn={keff['sn']:.9g} "
    f"delta_pn_pcm={delta_pn_pcm:.6g} delta_sn_pcm={delta_sn_pcm:.6g} "
    f"sph_range={float(np.min(sph_source.sph)):.6g}..{float(np.max(sph_source.sph)):.6g} "
    f"pn_ntot0_max_delta={pn_ntot_delta:.6g} sn_ntot0_max_delta={sn_ntot_delta:.6g}"
)
PY

echo
echo "openmc2donjon C5G7 SPH solver response smoke: PASS"

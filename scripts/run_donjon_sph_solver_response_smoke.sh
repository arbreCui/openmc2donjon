#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_donjon_sph_solver_response_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"
DONJON_RUNNER="${DONJON_RUNNER:-$DONJON_ROOT/rdonjon}"
MACROLIB_ASCII="${MACROLIB_ASCII:-}"

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

echo "== openmc2donjon DONJON SPH solver response smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "donjon: $DONJON_RUNNER"

if [[ ! -x "$DONJON_RUNNER" ]]; then
  echo "DONJON runner is unavailable; skipping DONJON SPH solver response smoke"
  exit 0
fi

if [[ -z "$MACROLIB_ASCII" || ! -f "$MACROLIB_ASCII" ]]; then
  SOURCE_RUN_DIR="$RUN_DIR/dragon_sph_handoff_source"
  echo "SPH macrolib source unavailable; building one with DRAGON handoff smoke"
  RUN_DIR="$SOURCE_RUN_DIR" PYTHON_BIN="$PYTHON_BIN" \
    bash "$REPO_ROOT/scripts/run_dragon_sph_handoff_smoke.sh"
  MACROLIB_ASCII="$SOURCE_RUN_DIR/from_openmc_sph/out.macrolib.txt"
fi

if [[ ! -f "$MACROLIB_ASCII" ]]; then
  echo "SPH macrolib source is unavailable after setup; skipping DONJON SPH solver response smoke"
  exit 0
fi

CASE_ID="${RUN_TAG:-donjon_sph_solver_response_smoke}"
DATA_CASE_DIR="$DONJON_ROOT/data/openmc2donjon/case_runs/donjon_sph_solver_response"
DECK_REL="openmc2donjon/case_runs/donjon_sph_solver_response/${CASE_ID}.x2m"
DECK_PATH="$DONJON_ROOT/data/$DECK_REL"
RESULT_PATH="$DONJON_ROOT/Darwin_arm64/${CASE_ID}.result"
BASE_MACROLIB="/tmp/${CASE_ID}.base.macrolib.txt"
CORRECTED_PN="/tmp/${CASE_ID}.sph_pn.macrolib.txt"
CORRECTED_SN="/tmp/${CASE_ID}.sph_sn.macrolib.txt"

mkdir -p "$DATA_CASE_DIR"
cp "$MACROLIB_ASCII" "$BASE_MACROLIB"
rm -f "$CORRECTED_PN" "$CORRECTED_SN"

"$PYTHON_BIN" - "$DECK_PATH" "$BASE_MACROLIB" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import sys

deck = Path(sys.argv[1])
base_macrolib = Path(sys.argv[2])
corrected_pn = Path(sys.argv[3])
corrected_sn = Path(sys.argv[4])
deck.write_text(
    f"""* DONJON low-order solver response after DSPH/MAC update of an L_MACROLIB NSPH payload.
MODULE DSPH: MAC: GEO: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;
LINKED_LIST MACRO DMACROPN OPTIMPN DMACROSN OPTIMSN MACROPN MACROSN GEOM TRACK SYSB FLUXB SYSPN FLUXPN SYSSN FLUXSN ;
REAL keff_base keff_pn keff_sn ;
SEQ_ASCII MACRO_ASC :: FILE '{base_macrolib}' ;
SEQ_ASCII PN_ASC :: FILE '{corrected_pn}' ;
SEQ_ASCII SN_ASC :: FILE '{corrected_sn}' ;

MACRO := MACRO_ASC ;
DMACROPN OPTIMPN := DSPH: MACRO :: EDIT 1 SPH PN ;
MACROPN := MACRO ;
MACROPN := MAC: MACROPN OPTIMPN ;
PN_ASC := MACROPN ;
DMACROSN OPTIMSN := DSPH: MACRO :: EDIT 1 SPH SN ;
MACROSN := MACRO ;
MACROSN := MAC: MACROSN OPTIMSN ;
SN_ASC := MACROSN ;

REAL side1 := 1.0 ;
REAL side2 := side1 1.0 + ;
REAL side3 := side2 1.0 + ;
REAL y1 := 1.0 ;
REAL y2 := y1 1.0 + ;
GEOM := GEO: :: CAR2D 3 2
  X- REFL X+ REFL
  Y- REFL Y+ REFL
  MESHX 0.0 <<side1>> <<side2>> <<side3>>
  MESHY 0.0 <<y1>> <<y2>>
  MIX 1 2 3
      4 5 6
;

TRACK := TRIVAT: GEOM ::
  TITLE 'OpenMC2DONJON SPH solver response smoke'
  EDIT 0 MAXR 100 DUAL 1 1 ;

SYSB := TRIVAA: MACRO TRACK :: EDIT 0 ;
FLUXB := FLUD: SYSB TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXB :: GETVAL 'K-EFFECTIVE ' 1 >>keff_base<< ;
ECHO 'OPENMC2DONJON DONJON SPH SOLVER BASE K-EFFECTIVE' keff_base ;
SYSPN := TRIVAA: MACROPN TRACK :: EDIT 0 ;
FLUXPN := FLUD: SYSPN TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXPN :: GETVAL 'K-EFFECTIVE ' 1 >>keff_pn<< ;
ECHO 'OPENMC2DONJON DONJON SPH SOLVER PN K-EFFECTIVE' keff_pn ;
SYSSN := TRIVAA: MACROSN TRACK :: EDIT 0 ;
FLUXSN := FLUD: SYSSN TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUXSN :: GETVAL 'K-EFFECTIVE ' 1 >>keff_sn<< ;
ECHO 'OPENMC2DONJON DONJON SPH SOLVER SN K-EFFECTIVE' keff_sn ;
END: ;
""",
    encoding="utf-8",
)
PY

(
  cd "$DONJON_ROOT"
  ./rdonjon -q "$DECK_REL"
)

"$PYTHON_BIN" - "$RESULT_PATH" "$MACROLIB_ASCII" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import re
import sys

import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii

result = Path(sys.argv[1])
source_macrolib = Path(sys.argv[2])
corrected_pn_path = Path(sys.argv[3])
corrected_sn_path = Path(sys.argv[4])

text = result.read_text(encoding="utf-8", errors="replace")
if "normal end of execution" not in text:
    raise SystemExit(f"DONJON listing did not end normally: {result}")

keff = {}
for label in ("BASE", "PN", "SN"):
    pattern = rf"OPENMC2DONJON DONJON SPH SOLVER {label} K-EFFECTIVE\s+([0-9.Ee+-]+)"
    match = re.search(pattern, text)
    if match is None:
        raise SystemExit(f"missing DONJON SPH solver {label} echo in {result}")
    keff[label.lower()] = float(match.group(1))

for key, value in keff.items():
    if not np.isfinite(value) or value <= 0.0:
        raise SystemExit(f"invalid {key} k-effective: {value}")

base = read_macrolib_ascii(source_macrolib)
corrected_pn = read_macrolib_ascii(corrected_pn_path)
corrected_sn = read_macrolib_ascii(corrected_sn_path)
if corrected_pn.state_vector[13] != 1:
    raise SystemExit("PN-corrected macrolib SPH state-vector flag is not set")
if corrected_sn.state_vector[13] != 1:
    raise SystemExit("SN-corrected macrolib SPH state-vector flag is not set")

mix3_base = float(base.ntot0[2, 0])
mix3_pn = float(corrected_pn.ntot0[2, 0])
mix3_sn = float(corrected_sn.ntot0[2, 0])
if np.isclose(mix3_pn, mix3_base, rtol=1.0e-8, atol=1.0e-10):
    raise SystemExit("PN-corrected macrolib did not perturb mix 3 total XS")
np.testing.assert_allclose(mix3_sn, mix3_base, rtol=1.0e-6, atol=1.0e-7)

delta_pn_pcm = (keff["pn"] - keff["base"]) / keff["base"] * 1.0e5
delta_sn_pcm = (keff["sn"] - keff["base"]) / keff["base"] * 1.0e5
if abs(delta_pn_pcm) < 1.0:
    raise SystemExit(
        "PN-corrected macrolib produced no meaningful solver response: "
        f"delta={delta_pn_pcm:.6g} pcm"
    )

print(
    "DONJON SPH solver response: "
    f"base={keff['base']:.9g} pn={keff['pn']:.9g} sn={keff['sn']:.9g} "
    f"delta_pn_pcm={delta_pn_pcm:.6g} delta_sn_pcm={delta_sn_pcm:.6g}"
)
PY

echo
echo "openmc2donjon DONJON SPH solver response smoke: PASS"

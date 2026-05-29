#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_donjon_sph_consume_smoke}"
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

echo "== openmc2donjon DONJON precomputed NSPH consume smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "donjon: $DONJON_RUNNER"

if [[ ! -x "$DONJON_RUNNER" ]]; then
  echo "DONJON runner is unavailable; skipping DONJON precomputed NSPH consume smoke"
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
  echo "SPH macrolib source is unavailable after setup; skipping DONJON precomputed NSPH consume smoke"
  exit 0
fi

CASE_ID="${RUN_TAG:-donjon_sph_consume_smoke}"
DATA_CASE_DIR="$DONJON_ROOT/data/openmc2donjon/case_runs/donjon_sph_consume_smoke"
DECK_REL="openmc2donjon/case_runs/donjon_sph_consume_smoke/${CASE_ID}.x2m"
DECK_PATH="$DONJON_ROOT/data/$DECK_REL"
RESULT_PATH="$DONJON_ROOT/Darwin_arm64/${CASE_ID}.result"
SHORT_MACROLIB="/tmp/${CASE_ID}.macrolib.txt"
CORRECTED_PN="/tmp/${CASE_ID}.sph_pn.macrolib.txt"
CORRECTED_SN="/tmp/${CASE_ID}.sph_sn.macrolib.txt"

mkdir -p "$DATA_CASE_DIR"
cp "$MACROLIB_ASCII" "$SHORT_MACROLIB"
rm -f "$CORRECTED_PN" "$CORRECTED_SN"

"$PYTHON_BIN" - "$DECK_PATH" "$SHORT_MACROLIB" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import sys

import numpy as np

from openmc2donjon.macrolib import extract_sph_from_macrolib_ascii

deck = Path(sys.argv[1])
macrolib = Path(sys.argv[2])
corrected_pn = Path(sys.argv[3])
corrected_sn = Path(sys.argv[4])
expected = extract_sph_from_macrolib_ascii(macrolib)
if expected.shape[0] < 1 or expected.shape[1] < 1:
    raise SystemExit(f"expected at least one mixture and one group, got {expected.shape}")
target_index = int(np.argmax(np.abs(expected[:, 0] - 1.0))) + 1
target = float(expected[target_index - 1, 0])
if np.isclose(target, 1.0):
    raise SystemExit("selected NSPH value is unity; smoke needs a non-unity SPH factor")
deck.write_text(
    f"""* DONJON DSPH consumption and MAC update of an L_MACROLIB NSPH payload.
MODULE DSPH: MAC: GREP: END: ABORT: ;
LINKED_LIST MACRO DMACROPN OPTIMPN DMACROSN OPTIMSN CORRPN CORRSN ;
DOUBLE sph3pn sph3sn ;
SEQ_ASCII MACRO_ASC :: FILE '{macrolib}' ;
SEQ_ASCII CORRPN_ASC :: FILE '{corrected_pn}' ;
SEQ_ASCII CORRSN_ASC :: FILE '{corrected_sn}' ;

MACRO := MACRO_ASC ;
DMACROPN OPTIMPN := DSPH: MACRO :: EDIT 1 SPH PN ;
GREP: OPTIMPN :: GETVAL 'VAR-VALUE' {target_index} NVAL 1 >>sph3pn<< ;
ECHO 'OPENMC2DONJON DONJON DSPH PN NSPH VAR-VALUE {target_index}' sph3pn ;
CORRPN := MACRO ;
CORRPN := MAC: CORRPN OPTIMPN ;
CORRPN_ASC := CORRPN ;
DMACROSN OPTIMSN := DSPH: MACRO :: EDIT 1 SPH SN ;
GREP: OPTIMSN :: GETVAL 'VAR-VALUE' {target_index} NVAL 1 >>sph3sn<< ;
ECHO 'OPENMC2DONJON DONJON DSPH SN NSPH VAR-VALUE {target_index}' sph3sn ;
CORRSN := MACRO ;
CORRSN := MAC: CORRSN OPTIMSN ;
CORRSN_ASC := CORRSN ;
END: ;
""",
    encoding="utf-8",
)
PY

(
  cd "$DONJON_ROOT"
  ./rdonjon -q "$DECK_REL"
)

"$PYTHON_BIN" - "$MACROLIB_ASCII" "$RESULT_PATH" "$CORRECTED_PN" "$CORRECTED_SN" <<'PY'
from pathlib import Path
import re
import sys

import numpy as np

from openmc2donjon.macrolib import extract_sph_from_macrolib_ascii, read_macrolib_ascii

macrolib = Path(sys.argv[1])
result = Path(sys.argv[2])
corrected_pn_path = Path(sys.argv[3])
corrected_sn_path = Path(sys.argv[4])
expected = extract_sph_from_macrolib_ascii(macrolib)
if expected.shape[0] < 1 or expected.shape[1] < 1:
    raise SystemExit(f"expected at least one mixture and one group, got {expected.shape}")
target_index = int(np.argmax(np.abs(expected[:, 0] - 1.0))) + 1
target = float(expected[target_index - 1, 0])
if np.isclose(target, 1.0):
    raise SystemExit("selected NSPH value is unity; smoke needs a non-unity SPH factor")

text = result.read_text(encoding="utf-8", errors="replace")
if "normal end of execution" not in text:
    raise SystemExit(f"DONJON listing did not end normally: {result}")
if "IDELTA       3" not in text or "IDELTA       4" not in text:
    raise SystemExit("DONJON DSPH did not report both PN and SN SPH consume modes")

values = {}
for label in ("PN", "SN"):
    pattern = (
        rf"OPENMC2DONJON DONJON DSPH {label} NSPH VAR-VALUE "
        rf"{target_index}\s+([0-9.Ee+-]+)"
    )
    match = re.search(pattern, text)
    if match is None:
        raise SystemExit(f"missing DONJON DSPH {label} echo in {result}")
    values[label] = float(match.group(1))
    np.testing.assert_allclose(values[label], target, rtol=1.0e-7, atol=1.0e-7)

base = read_macrolib_ascii(macrolib)
corrected_pn = read_macrolib_ascii(corrected_pn_path)
corrected_sn = read_macrolib_ascii(corrected_sn_path)
if corrected_pn.state_vector[13] != 1:
    raise SystemExit("PN-corrected macrolib SPH state-vector flag is not set")
if corrected_sn.state_vector[13] != 1:
    raise SystemExit("SN-corrected macrolib SPH state-vector flag is not set")
if corrected_pn.sph is None or corrected_sn.sph is None:
    raise SystemExit("corrected macrolib is missing GROUP/*/NSPH payload")
np.testing.assert_allclose(
    corrected_pn.sph[target_index - 1, 0],
    target,
    rtol=1.0e-7,
    atol=1.0e-7,
)
np.testing.assert_allclose(
    corrected_sn.sph[target_index - 1, 0],
    target,
    rtol=1.0e-7,
    atol=1.0e-7,
)

base_ntot0 = float(base.ntot0[target_index - 1, 0])
pn_ntot0 = float(corrected_pn.ntot0[target_index - 1, 0])
sn_ntot0 = float(corrected_sn.ntot0[target_index - 1, 0])
np.testing.assert_allclose(pn_ntot0, base_ntot0 * target, rtol=1.0e-6, atol=1.0e-7)
np.testing.assert_allclose(sn_ntot0, base_ntot0, rtol=1.0e-6, atol=1.0e-7)

print(
    "DONJON DSPH consumed NSPH: "
    f"target_mix={target_index} expected_g1={target:.9g} "
    f"pn={values['PN']:.9g} sn={values['SN']:.9g}"
)
print(
    "DONJON MAC applied SPH: "
    f"pn_ntot0_ratio={pn_ntot0 / base_ntot0:.9g} "
    f"sn_ntot0_ratio={sn_ntot0 / base_ntot0:.9g}"
)
PY

echo
echo "openmc2donjon DONJON precomputed NSPH consume smoke: PASS"

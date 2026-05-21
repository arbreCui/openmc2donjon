#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE_DIR="$REPO_ROOT/examples/openmc_hex_minicase"
DRAGON_ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
DONJON_DIR="$DRAGON_ROOT/Donjon"
DATA_DIR="${OPENMC2DONJON_DATA_DIR:-$DONJON_DIR/data/openmc2donjon}"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
OUTPUT_BASE="${OUTPUT_BASE:-/private/tmp}"
RUN_BASE="${RUN_BASE:-$DATA_DIR/openmc_hex_minicase_keff_runs}"
PYTHON_BIN="${PYTHON_BIN:-}"
OPENMC_THREADS="${OPENMC_THREADS:-4}"
HEX_MINICASE_PARTICLES="${HEX_MINICASE_PARTICLES:-10000}"
HEX_MINICASE_BATCHES="${HEX_MINICASE_BATCHES:-80}"
HEX_MINICASE_INACTIVE="${HEX_MINICASE_INACTIVE:-20}"
MAX_DELTA_PCM="${OPENMC2DONJON_HEX_MAX_DELTA_PCM:-300}"

usage() {
  cat <<'EOF'
usage: run_keff_comparison.sh

Run the OpenMC hex minicase, export its MGXS statepoint to L_MULTICOMPO,
consume that file through DONJON NCR + TRIVAC diffusion, and compare k-eff.

Environment overrides:
  OPENMC2DONJON_ROOT              default /Users/wen/dragon-5.1
  OPENMC2DONJON_DATA_DIR          default $OPENMC2DONJON_ROOT/Donjon/data/openmc2donjon
  OPENMC2DONJON_SRC               default repo src/
  RUN_BASE                        default $OPENMC2DONJON_DATA_DIR/openmc_hex_minicase_keff_runs
  OUTPUT_BASE                     default /private/tmp
  HEX_MINICASE_PARTICLES          default 10000
  HEX_MINICASE_BATCHES            default 80
  HEX_MINICASE_INACTIVE           default 20
  OPENMC_THREADS                  default 4
  OPENMC2DONJON_HEX_MAX_DELTA_PCM default 300
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
}

result_for_deck() {
  local deck="$1"
  local stem
  stem="$(basename "$deck" .x2m)"
  printf '%s/Darwin_arm64/%s.result' "$DONJON_DIR" "$stem"
}

data_relative_deck() {
  local deck="$1"
  if [[ "$deck" == "$DONJON_DIR/data/"* ]]; then
    printf '%s' "${deck#"$DONJON_DIR/data/"}"
  else
    printf '%s' "$deck"
  fi
}

run_donjon_deck() {
  local deck="$1"
  local deck_arg result
  deck_arg="$(data_relative_deck "$deck")"
  result="$(result_for_deck "$deck")"
  rm -f "$result"

  echo
  echo "== Run DONJON NCR diffusion =="
  echo "./rdonjon -q $deck_arg"
  (
    cd "$DONJON_DIR"
    ./rdonjon -q "$deck_arg"
  )

  require_path "$result"
  if ! grep -qi "normal end of execution" "$result"; then
    echo "DONJON listing did not reach normal end: $result" >&2
    exit 1
  fi
  grep -E "OPENMC2DONJON OPENMC HEX MINICASE|K-EFFECTIVE|normal end" "$result" | tail -n 12 || true
}

write_deck() {
  local deck="$1"
  local mco_path="$2"
  cat > "$deck" <<EOF
*----
*  OpenMC hex minicase: converted L_MULTICOMPO -> NCR -> TRIVAC diffusion keff.
*  Capability sanity check only; this is not an accepted hex benchmark.
*----
MODULE GEO: NCR: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;
LINKED_LIST CPO MACRO GEOM TRACK SYS FLUX ;
REAL keff ;
SEQ_ASCII CPO_ASC :: FILE '$mco_path' ;

CPO := CPO_ASC ;
MACRO := NCR: CPO :: EDIT 1 MACRO NMIX 7
  COMPO CPO CPO
  MIX 1 USE ENDMIX (* HEX_C  *)
  MIX 2 USE ENDMIX (* HEX_E  *)
  MIX 3 USE ENDMIX (* HEX_NE *)
  MIX 4 USE ENDMIX (* HEX_NW *)
  MIX 5 USE ENDMIX (* HEX_SE *)
  MIX 6 USE ENDMIX (* HEX_SW *)
  MIX 7 USE ENDMIX (* HEX_W  *)
;

GEOM := GEO: :: HEX 7
  EDIT 1
  HBC COMPLETE REFL
  SIDE 0.808290376865476
  MIX 1 2 3 4 7 6 5
  SPLITL 1
;

TRACK := TRIVAT: GEOM ::
  TITLE 'OpenMC hex minicase NCR diffusion'
  EDIT 1 MAXR 21 DUAL 1 1 ;
SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;
FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;
ECHO 'OPENMC2DONJON OPENMC HEX MINICASE NCR DIFFUSION K-EFFECTIVE' keff ;
END: ;
EOF
}

compare_keff() {
  local statepoint="$1"
  local result="$2"
  local summary="$3"
  local mco="$4"
  local deck="$5"
  "$PYTHON_BIN" - "$statepoint" "$result" "$summary" "$mco" "$deck" "$MAX_DELTA_PCM" <<'PY'
import json
import re
import sys
from pathlib import Path

import openmc

statepoint = Path(sys.argv[1])
result = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
mco_path = Path(sys.argv[4])
deck_path = Path(sys.argv[5])
max_delta_pcm = float(sys.argv[6])

sp = openmc.StatePoint(statepoint)
openmc_keff = float(sp.keff.nominal_value)
openmc_std = float(sp.keff.std_dev)

text = result.read_text(encoding="utf-8", errors="replace")
matches = re.findall(
    r"OPENMC2DONJON OPENMC HEX MINICASE NCR DIFFUSION K-EFFECTIVE\s+([0-9.+\-Ee]+)",
    text,
)
if not matches:
    matches = re.findall(r"K-EFFECTIVE\s+([0-9.+\-Ee]+)", text)
if not matches:
    raise SystemExit(f"no DONJON k-effective found in {result}")
donjon_keff = float(matches[-1])

delta_k = donjon_keff - openmc_keff
delta_pcm = delta_k / openmc_keff * 1.0e5
openmc_std_pcm = openmc_std / openmc_keff * 1.0e5
passed = abs(delta_pcm) <= max_delta_pcm

summary = {
    "schema": "openmc2donjon.openmc-hex-keff-comparison.v1",
    "decision": "openmc_hex_keff_comparison_passed" if passed else "openmc_hex_keff_comparison_failed",
    "openmc_keff": openmc_keff,
    "openmc_std": openmc_std,
    "openmc_std_pcm": openmc_std_pcm,
    "donjon_diffusion_keff": donjon_keff,
    "delta_k": delta_k,
    "delta_pcm": delta_pcm,
    "max_delta_pcm": max_delta_pcm,
    "statepoint": str(statepoint),
    "multicompo": str(mco_path),
    "donjon_deck": str(deck_path),
    "donjon_result": str(result),
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print("OpenMC hex minicase k-eff comparison")
print(f"  OpenMC: {openmc_keff:.10f} +/- {openmc_std:.10f} ({openmc_std_pcm:.1f} pcm)")
print(f"  DONJON: {donjon_keff:.10f}")
print(f"  delta: {delta_pcm:+.1f} pcm")
print(f"  summary: {summary_path}")
if not passed:
    raise SystemExit(
        f"hex minicase k-eff comparison failed: |{delta_pcm:.1f}| pcm > {max_delta_pcm:.1f} pcm"
    )
print("  decision: openmc_hex_keff_comparison_passed")
PY
}

require_path "$PYTHON_BIN"
require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$DONJON_DIR/rdonjon"

case "$RUN_BASE" in
  "$DONJON_DIR/data/"*) ;;
  *)
    echo "RUN_BASE must be under $DONJON_DIR/data because rdonjon consumes data-relative input decks." >&2
    exit 2
    ;;
esac

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$RUN_BASE/$stamp"
OUTPUT_DIR="$OUTPUT_BASE/o2d_hex_keff_$stamp"
DECK_DIR="$RUN_DIR/donjon"
mkdir -p "$RUN_DIR" "$OUTPUT_DIR" "$DECK_DIR"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== OpenMC hex minicase k-eff comparison =="
echo "repo: $REPO_ROOT"
echo "dragon_root: $DRAGON_ROOT"
echo "run_dir: $RUN_DIR"
echo "output_dir: $OUTPUT_DIR"
echo "particles/batches/inactive: $HEX_MINICASE_PARTICLES/$HEX_MINICASE_BATCHES/$HEX_MINICASE_INACTIVE"
echo "max_delta_pcm: $MAX_DELTA_PCM"

echo
echo "== Run OpenMC hex smoke/export =="
RUN_DIR="$RUN_DIR" \
PYTHON_BIN="$PYTHON_BIN" \
OPENMC_THREADS="$OPENMC_THREADS" \
HEX_MINICASE_PARTICLES="$HEX_MINICASE_PARTICLES" \
HEX_MINICASE_BATCHES="$HEX_MINICASE_BATCHES" \
HEX_MINICASE_INACTIVE="$HEX_MINICASE_INACTIVE" \
OPENMC2DONJON_SCATTER_ROW_BALANCE_WARN="${OPENMC2DONJON_SCATTER_ROW_BALANCE_WARN:-2e-2}" \
OPENMC2DONJON_SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_SCATTER_ROW_BALANCE_FAIL:-5e-2}" \
  bash "$EXAMPLE_DIR/run_smoke.sh"

STATEPOINT="$RUN_DIR/openmc_case/statepoint.${HEX_MINICASE_BATCHES}.h5"
MCO="$RUN_DIR/openmc2donjon_run/out.mcompo.txt"
SHORT_MCO="$OUTPUT_DIR/out.mcompo.txt"
DECK="$DECK_DIR/openmc_hex_minicase_ncr_diffusion_keff_${stamp}.x2m"
SUMMARY="$RUN_DIR/keff_comparison.json"

require_path "$STATEPOINT"
require_path "$MCO"
cp "$MCO" "$SHORT_MCO"
write_deck "$DECK" "$SHORT_MCO"

run_donjon_deck "$DECK"
RESULT="$(result_for_deck "$DECK")"
compare_keff "$STATEPOINT" "$RESULT" "$SUMMARY" "$MCO" "$DECK"

echo
echo "OpenMC hex minicase k-eff comparison: PASS"

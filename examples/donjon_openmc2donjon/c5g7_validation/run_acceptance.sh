#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
DONJON_DIR="$ROOT/Donjon"
DATA_DIR="$DONJON_DIR/data/openmc2donjon"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-/Users/wen/openmc-workspace/openmc2donjon/src}"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.14}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_c5g7_acceptance}"

RUN_DONJON=1
RUN_CONVERTER=1
ORIGINAL_ARGS=("$@")
ORIGINAL_COMMAND="$0${*:+ $*}"

usage() {
  cat <<'EOF'
usage: run_acceptance.sh [--skip-donjon] [--skip-converter]

Runs the locked C5G7 acceptance checks without overwriting the accepted
production MULTICOMPO. Converter smoke outputs are written under RUN_DIR
(default: /private/tmp/openmc2donjon_c5g7_acceptance).

Environment overrides:
  OPENMC2DONJON_ROOT   default /Users/wen/dragon-5.1
  OPENMC2DONJON_SRC    default /Users/wen/openmc-workspace/openmc2donjon/src
  OPENMC2DONJON_ARCHIVE_DIR
                       default $OPENMC2DONJON_ROOT/Donjon/data/openmc2donjon/release_archive
  OPENMC2DONJON_CAPTURE_LOG
                       default 1; set to 0 to disable timestamped log capture
  PYTHON_BIN           default /opt/homebrew/bin/python3.14
  RUN_DIR              default /private/tmp/openmc2donjon_c5g7_acceptance
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-donjon)
      RUN_DONJON=0
      shift
      ;;
    --skip-converter)
      RUN_CONVERTER=0
      shift
      ;;
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

LOG_STEM="c5g7_acceptance"
ARCHIVE_DIR="${OPENMC2DONJON_ARCHIVE_DIR:-$DATA_DIR/release_archive}"
if [[ "${OPENMC2DONJON_CAPTURE_LOG:-1}" -eq 1 && -z "${OPENMC2DONJON_LOG_ACTIVE:-}" ]]; then
  mkdir -p "$ARCHIVE_DIR"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log_path="$ARCHIVE_DIR/${LOG_STEM}_${stamp}.log"
  summary_path="$ARCHIVE_DIR/${LOG_STEM}_${stamp}.summary.txt"
  echo "acceptance log: $log_path"
  set +e
  if [[ "${#ORIGINAL_ARGS[@]}" -gt 0 ]]; then
    OPENMC2DONJON_LOG_ACTIVE=1 bash "$0" "${ORIGINAL_ARGS[@]}" 2>&1 | tee "$log_path"
  else
    OPENMC2DONJON_LOG_ACTIVE=1 bash "$0" 2>&1 | tee "$log_path"
  fi
  status="${PIPESTATUS[0]}"
  set -e
  {
    echo "name=$LOG_STEM"
    echo "timestamp_utc=$stamp"
    echo "status=$status"
    echo "log=$log_path"
    echo "command=$ORIGINAL_COMMAND"
    echo "run_converter=$RUN_CONVERTER"
    echo "run_donjon=$RUN_DONJON"
    echo
    echo "key_lines:"
    grep -E "PASS|OpenMC reference|DONJON diffusion|DONJON SPN3|ADF active|NODF|failed|FAIL|ERROR" "$log_path" || true
  } > "$summary_path"
  echo "acceptance summary: $summary_path"
  exit "$status"
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

MGXS="$DATA_DIR/c5g7_assembly_p1_adf_production.h5"
TMP_MCO="$RUN_DIR/c5g7_acceptance_smoke.mco"
TMP_MACROLIB="$RUN_DIR/c5g7_acceptance_smoke.macrolib.txt"

echo "== C5G7 OpenMC-to-DONJON acceptance =="
echo "root: $ROOT"
echo "run_dir: $RUN_DIR"
mkdir -p "$RUN_DIR"

for required in "$PYTHON_BIN" "$MGXS" "$PACKAGE_SRC/openmc2donjon/cli.py"; do
  if [[ ! -e "$required" ]]; then
    echo "missing required path: $required" >&2
    exit 1
  fi
done

if [[ "$RUN_CONVERTER" -eq 1 ]]; then
  echo
  echo "== Converter CLI smoke =="
  "$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" -o "$TMP_MCO"
  "$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$MGXS" -o "$TMP_MACROLIB"
  "$PYTHON_BIN" - "$TMP_MCO" "$TMP_MACROLIB" <<'PY'
from pathlib import Path
import sys
from openmc2donjon import lcm_ascii as lcm

for raw in sys.argv[1:]:
    path = Path(raw)
    blocks = lcm.read_lcm_ascii(path)
    names = [block.name for block in blocks if block.name]
    print(f"{path.name}: blocks={len(blocks)} first_names={names[:8]}")
    if not names or names[0] != "SIGNATURE":
        raise SystemExit(f"{path}: missing SIGNATURE block")
PY
else
  echo
  echo "== Converter CLI smoke skipped =="
fi

if [[ "$RUN_DONJON" -eq 1 ]]; then
  echo
  echo "== DONJON locked decks =="
  decks=(
    "openmc2donjon/c5g7_adf_production_carrythrough.x2m"
    "openmc2donjon/c5g7_validation/c5g7pa_diffusion_keff.x2m"
    "openmc2donjon/c5g7_validation/c5g7pa_spn3_keff.x2m"
    "openmc2donjon/c5g7_validation/c5g7pa_spn3_scat1_keff.x2m"
    "openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_adf_effect.x2m"
  )
  cd "$DONJON_DIR"
  for deck in "${decks[@]}"; do
    echo "./rdonjon -q $deck"
    ./rdonjon -q "$deck"
  done
else
  echo
  echo "== DONJON locked decks skipped =="
fi

echo
echo "== Summary =="
cd "$ROOT"
"$PYTHON_BIN" "$DATA_DIR/c5g7_validation/summarize_c5g7_validation.py"

echo
echo "C5G7 acceptance: PASS"

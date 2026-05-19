#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
DONJON_DIR="$ROOT/Donjon"
DATA_DIR="$DONJON_DIR/data/openmc2donjon"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-/Users/wen/openmc-workspace/openmc2donjon/src}"
ARCHIVE_DIR="${OPENMC2DONJON_ARCHIVE_DIR:-$DATA_DIR/release_archive}"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.14}"
RUN_BASE="${RUN_BASE:-$DATA_DIR/fresh_pipeline_runs}"
OUTPUT_BASE="${OUTPUT_BASE:-/private/tmp}"
ORIGINAL_ARGS=("$@")
ORIGINAL_COMMAND="$0${*:+ $*}"

usage() {
  cat <<'EOF'
usage: run_production_pipeline_smoke.sh

Regenerate the accepted C5G7 handoff outputs from HDF5 using the
openmc2donjon CLI, then run DONJON against the fresh temporary outputs.
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

if [[ "${OPENMC2DONJON_CAPTURE_LOG:-1}" -eq 1 && -z "${OPENMC2DONJON_LOG_ACTIVE:-}" ]]; then
  mkdir -p "$ARCHIVE_DIR"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log_path="$ARCHIVE_DIR/production_pipeline_smoke_${stamp}.log"
  summary_path="$ARCHIVE_DIR/production_pipeline_smoke_${stamp}.summary.txt"
  echo "production pipeline smoke log: $log_path"
  set +e
  if [[ "${#ORIGINAL_ARGS[@]}" -gt 0 ]]; then
    OPENMC2DONJON_LOG_ACTIVE=1 bash "$0" "${ORIGINAL_ARGS[@]}" 2>&1 | tee "$log_path"
  else
    OPENMC2DONJON_LOG_ACTIVE=1 bash "$0" 2>&1 | tee "$log_path"
  fi
  status="${PIPESTATUS[0]}"
  set -e
  {
    echo "name=production_pipeline_smoke"
    echo "timestamp_utc=$stamp"
    echo "status=$status"
    echo "log=$log_path"
    echo "command=$ORIGINAL_COMMAND"
    echo
    echo "key_lines:"
    grep -E "PASS|production_pipeline_fresh_outputs_passed|fresh output|readback|K-EFFECTIVE|ANM KEFF|normal end|failed|FAIL|ERROR" "$log_path" || true
  } > "$summary_path"
  echo "production pipeline smoke summary: $summary_path"
  exit "$status"
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$RUN_BASE/$stamp"
OUTPUT_DIR="$OUTPUT_BASE/o2dpps_$stamp"
DECK_DIR="$RUN_DIR/decks"
case "$RUN_DIR" in
  "$DONJON_DIR/data/"*) ;;
  *)
    echo "RUN_BASE must be under $DONJON_DIR/data because rdonjon consumes data-relative input decks." >&2
    exit 2
    ;;
esac
mkdir -p "$DECK_DIR" "$OUTPUT_DIR"

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

convert_multicompo() {
  local input="$1"
  local output="$2"
  echo "fresh output: $output"
  "$PYTHON_BIN" -m openmc2donjon.cli "$input" -o "$output"
}

make_fresh_deck() {
  local source_deck="$1"
  local old_path="$2"
  local new_path="$3"
  local output_deck="$4"
  sed "s|$old_path|$new_path|g" "$source_deck" > "$output_deck"
  echo "fresh deck: $output_deck"
}

run_deck() {
  local label="$1"
  local deck="$2"
  local deck_arg="$deck"
  local result
  result="$(result_for_deck "$deck")"
  if [[ "$deck" == "$DONJON_DIR/data/"* ]]; then
    deck_arg="${deck#"$DONJON_DIR/data/"}"
  fi
  rm -f "$result"

  echo
  echo "== $label =="
  echo "./rdonjon -q $deck_arg"
  cd "$DONJON_DIR"
  ./rdonjon -q "$deck_arg"
  cd "$ROOT"

  require_path "$result"
  if ! grep -qi "normal end of execution" "$result"; then
    echo "DONJON listing did not reach normal end: $result" >&2
    exit 1
  fi
  echo "result: $result"
  grep -E "OPENMC2DONJON|K-EFFECTIVE|ANM KEFF|normal end" "$result" | tail -n 12 || true
  echo "PASS $label"
}

check_keff() {
  local label="$1"
  local result="$2"
  local expected="$3"
  local tolerance="$4"
  "$PYTHON_BIN" - "$label" "$result" "$expected" "$tolerance" <<'PY'
import re
import sys
from pathlib import Path

label, result, expected, tolerance = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
text = result.read_text(encoding="utf-8", errors="replace")
matches = re.findall(r"EFFECTIVE MULTIPLICATION FACTOR\s*=\s*([0-9.+\-Ee]+)", text)
if not matches:
    matches = re.findall(r"K-EFFECTIVE\s+([0-9.+\-Ee]+)", text)
if not matches:
    raise SystemExit(f"{label}: no k-effective found in {result}")
observed = float(matches[-1])
delta = abs(observed - expected)
if delta > tolerance:
    raise SystemExit(
        f"{label}: observed={observed:.12g} expected={expected:.12g} "
        f"tolerance={tolerance:.3g}"
    )
print(f"PASS {label}: observed={observed:.12g} expected={expected:.12g}")
PY
}

check_nssf_pair() {
  local result="$1"
  "$PYTHON_BIN" - "$result" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace")
matches = [float(value) for value in re.findall(r"NSSFL4:\s+ANM KEFF=\s*([0-9.+\-Ee]+)", text)]
if len(matches) < 2:
    raise SystemExit(f"expected two NSSFL4 ANM KEFF lines in {path}")
expected = (1.18533289, 1.20179343)
for label, observed, want in zip(("ADF", "NODF"), matches[:2], expected):
    if abs(observed - want) > 5.0e-8:
        raise SystemExit(f"C5G7 2G NSSF {label}: observed={observed:.8f} expected={want:.8f}")
print(f"PASS C5G7 2G NSSF ADF/NODF: ADF={matches[0]:.8f} NODF={matches[1]:.8f}")
PY
}

readback_outputs() {
  "$PYTHON_BIN" - "$@" <<'PY'
import sys
from pathlib import Path
from openmc2donjon import lcm_ascii

for raw in sys.argv[1:]:
    path = Path(raw)
    blocks = lcm_ascii.read_lcm_ascii(path)
    if not blocks:
        raise SystemExit(f"{path}: no LCM ASCII blocks read")
    names = [block.name for block in blocks if block.name]
    print(f"readback {path.name}: blocks={len(blocks)} first={names[0] if names else '<none>'}")
PY
}

echo "== OpenMC-to-DONJON production pipeline fresh-output smoke =="
echo "root: $ROOT"
echo "data: $DATA_DIR"
echo "package_src: $PACKAGE_SRC"
echo "run_dir: $RUN_DIR"
echo "output_dir: $OUTPUT_DIR"

require_path "$PYTHON_BIN"
require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$DONJON_DIR/rdonjon"
require_path "$DATA_DIR/c5g7_assembly_p1_adf_production.h5"
require_path "$DATA_DIR/c5g7_validation/c5g7pa_2g_nssf_smoke.h5"

C5G7_MCO="$OUTPUT_DIR/c5g7pa_fresh.mco"
C5G7_2G_MCO="$OUTPUT_DIR/c5g7p2_fresh.mco"

convert_multicompo "$DATA_DIR/c5g7_assembly_p1_adf_production.h5" "$C5G7_MCO"
convert_multicompo "$DATA_DIR/c5g7_validation/c5g7pa_2g_nssf_smoke.h5" "$C5G7_2G_MCO"
readback_outputs "$C5G7_MCO" "$C5G7_2G_MCO"

ARCHIVE_OUTPUT_DIR="$RUN_DIR/outputs"
mkdir -p "$ARCHIVE_OUTPUT_DIR"
cp "$C5G7_MCO" "$ARCHIVE_OUTPUT_DIR/"
cp "$C5G7_2G_MCO" "$ARCHIVE_OUTPUT_DIR/"
echo "archived fresh outputs: $ARCHIVE_OUTPUT_DIR"

C5G7_DIFF_DECK="$DECK_DIR/c5g7pa_fresh_diffusion_keff.x2m"
C5G7_CARRY_DECK="$DECK_DIR/c5g7pa_fresh_adf_carrythrough.x2m"
C5G7_NSSF_DECK="$DECK_DIR/c5g7p2_fresh_nssf_adf_effect.x2m"

make_fresh_deck \
  "$DATA_DIR/c5g7_validation/c5g7pa_diffusion_keff.x2m" \
  "$DATA_DIR/c5g7pa.mco" \
  "$C5G7_MCO" \
  "$C5G7_DIFF_DECK"
make_fresh_deck \
  "$DATA_DIR/c5g7_adf_production_carrythrough.x2m" \
  "$DATA_DIR/c5g7pa.mco" \
  "$C5G7_MCO" \
  "$C5G7_CARRY_DECK"
make_fresh_deck \
  "$DATA_DIR/c5g7_validation/c5g7pa_2g_nssf_adf_effect.x2m" \
  "$DATA_DIR/c5g7p2.mco" \
  "$C5G7_2G_MCO" \
  "$C5G7_NSSF_DECK"

run_deck "C5G7 fresh MULTICOMPO carry-through" "$C5G7_CARRY_DECK"
run_deck "C5G7 fresh diffusion keff" "$C5G7_DIFF_DECK"
check_keff "C5G7 fresh diffusion keff" "$(result_for_deck "$C5G7_DIFF_DECK")" 1.1896194220 5.0e-8

run_deck "C5G7 fresh 2G NSSF ADF-vs-NODF" "$C5G7_NSSF_DECK"
check_nssf_pair "$(result_for_deck "$C5G7_NSSF_DECK")"

echo
echo "Production pipeline smoke decision"
echo "  production_pipeline_fresh_outputs_passed"
echo
echo "OpenMC-to-DONJON production pipeline smoke: PASS"

#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
DONJON_DIR="$ROOT/Donjon"
DATA_DIR="$DONJON_DIR/data/openmc2donjon"
ARCHIVE_DIR="${OPENMC2DONJON_ARCHIVE_DIR:-$DATA_DIR/release_archive}"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.14}"
ORIGINAL_ARGS=("$@")
ORIGINAL_COMMAND="$0${*:+ $*}"

usage() {
  cat <<'EOF'
usage: run_handoff_smoke.sh

Run the DONJON consumer smoke against the accepted C5G7 handoff artifacts.
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
  log_path="$ARCHIVE_DIR/handoff_donjon_smoke_${stamp}.log"
  summary_path="$ARCHIVE_DIR/handoff_donjon_smoke_${stamp}.summary.txt"
  echo "handoff smoke log: $log_path"
  set +e
  if [[ "${#ORIGINAL_ARGS[@]}" -gt 0 ]]; then
    OPENMC2DONJON_LOG_ACTIVE=1 bash "$0" "${ORIGINAL_ARGS[@]}" 2>&1 | tee "$log_path"
  else
    OPENMC2DONJON_LOG_ACTIVE=1 bash "$0" 2>&1 | tee "$log_path"
  fi
  status="${PIPESTATUS[0]}"
  set -e
  {
    echo "name=handoff_donjon_smoke"
    echo "timestamp_utc=$stamp"
    echo "status=$status"
    echo "log=$log_path"
    echo "command=$ORIGINAL_COMMAND"
    echo
    echo "key_lines:"
    grep -E "PASS|handoff_case_passed|summary:|normal end|OPENMC2DONJON|K-EFFECTIVE|ANM KEFF|failed|FAIL|ERROR" "$log_path" || true
  } > "$summary_path"
  echo "handoff smoke summary: $summary_path"
  exit "$status"
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

run_deck() {
  local label="$1"
  local deck="$2"
  local result
  result="$(result_for_deck "$deck")"
  rm -f "$result"

  echo
  echo "== $label =="
  echo "./rdonjon -q $deck"
  cd "$DONJON_DIR"
  ./rdonjon -q "$deck"
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

run_manifest_case() {
  local label="$1"
  local manifest="$2"
  local run_dir="$3"
  local expected_keff="$4"
  local log_file="$5"

  echo
  echo "== $label =="
  "$PYTHON_BIN" "$DATA_DIR/run_handoff_case.py" \
    "$DATA_DIR/case_manifests/$manifest" \
    --run-dir "$run_dir" \
    --run-donjon \
    > "$log_file"
  grep -q "handoff_case_passed" "$log_file"
  grep -q "PASS  k-effective $expected_keff" "$log_file"
  grep -E "PASS  k-effective|handoff_case_passed|summary:" "$log_file"
  echo "PASS $label"
}

echo "== OpenMC-to-DONJON handoff consumer smoke =="
echo "root: $ROOT"
echo "data: $DATA_DIR"

require_path "$DONJON_DIR/rdonjon"
require_path "$PYTHON_BIN"
require_path "$DATA_DIR/run_handoff_case.py"
require_path "$DATA_DIR/case_manifests/c5g7_production_diffusion.json"
require_path "$DATA_DIR/c5g7pa.mco"
require_path "$DATA_DIR/c5g7p2.mco"
require_path "$DATA_DIR/c5g7_adf_production_carrythrough.x2m"
require_path "$DATA_DIR/c5g7_validation/c5g7pa_2g_nssf_adf_effect.x2m"

mkdir -p "$DATA_DIR/case_runs/delivery_c5g7"

run_manifest_case \
  "C5G7 manifest handoff case DONJON" \
  "c5g7_production_diffusion.json" \
  "$DATA_DIR/case_runs/delivery_c5g7" \
  "1.189619422" \
  "$DATA_DIR/case_runs/delivery_c5g7/handoff_smoke_stdout.txt"

run_deck \
  "C5G7 MULTICOMPO carry-through" \
  "openmc2donjon/c5g7_adf_production_carrythrough.x2m"

run_deck \
  "C5G7 NSSF ADF-vs-NODF smoke" \
  "openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_adf_effect.x2m"

echo
echo "OpenMC-to-DONJON handoff consumer smoke: PASS"

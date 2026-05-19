#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPENMC2DONJON_ROOT:-/Users/wen/dragon-5.1}"
DATA_DIR="$ROOT/Donjon/data/openmc2donjon"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-/Users/wen/openmc-workspace/openmc2donjon/src}"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.14}"
PYTEST_PYTHON="${PYTEST_PYTHON:-/Users/wen/miniforge3/envs/openmc-dev/bin/python}"
PYTEST_CACHE="${PYTEST_CACHE:-/private/tmp/openmc2donjon_pytest_cache}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_acceptance}"
ARCHIVE_DIR="${OPENMC2DONJON_ARCHIVE_DIR:-$DATA_DIR/release_archive}"

RUN_TESTS=1
C5G7_DONJON=1
ORIGINAL_ARGS=("$@")
ORIGINAL_COMMAND="$0${*:+ $*}"

usage() {
  cat <<'EOF'
usage: run_acceptance.sh [--quick] [--skip-tests]

Top-level OpenMC-to-DONJON acceptance entry.

Default:
  - converter package CLI smoke
  - converter package pytest smoke
  - C5G7 assembly-wise validation, including DONJON decks

Options:
  --quick       skip package tests and C5G7 DONJON deck reruns
  --skip-tests  skip converter package pytest smoke
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)
      RUN_TESTS=0
      C5G7_DONJON=0
      shift
      ;;
    --skip-tests)
      RUN_TESTS=0
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

if [[ "${OPENMC2DONJON_CAPTURE_LOG:-1}" -eq 1 && -z "${OPENMC2DONJON_LOG_ACTIVE:-}" ]]; then
  mkdir -p "$ARCHIVE_DIR"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log_path="$ARCHIVE_DIR/top_level_acceptance_${stamp}.log"
  summary_path="$ARCHIVE_DIR/top_level_acceptance_${stamp}.summary.txt"
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
    echo "name=top_level_acceptance"
    echo "timestamp_utc=$stamp"
    echo "status=$status"
    echo "log=$log_path"
    echo "command=$ORIGINAL_COMMAND"
    echo "run_tests=$RUN_TESTS"
    echo "c5g7_donjon=$C5G7_DONJON"
    echo
    echo "key_lines:"
    grep -E "PASS|[0-9]+ passed|openmc2donjon [0-9]|C5G7|DONJON keff|diffusion k=|SPN3|OpenMC reference|failed|FAIL|ERROR" "$log_path" || true
  } > "$summary_path"
  echo "acceptance summary: $summary_path"
  exit "$status"
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
}

echo "== OpenMC-to-DONJON top-level acceptance =="
echo "root: $ROOT"
echo "run_dir: $RUN_DIR"
echo "c5g7_donjon: $C5G7_DONJON"

mkdir -p "$RUN_DIR"
require_path "$PYTHON_BIN"
require_path "$PACKAGE_SRC/openmc2donjon/cli.py"
require_path "$DATA_DIR/c5g7_validation/run_acceptance.sh"

echo
echo "== Converter package smoke =="
"$PYTHON_BIN" -m openmc2donjon.cli --version > "$RUN_DIR/openmc2donjon_cli_version.txt"
echo "CLI version OK: $RUN_DIR/openmc2donjon_cli_version.txt"
"$PYTHON_BIN" -m openmc2donjon.cli --help > "$RUN_DIR/openmc2donjon_cli_help.txt"
echo "CLI help OK: $RUN_DIR/openmc2donjon_cli_help.txt"

if [[ "$RUN_TESTS" -eq 1 ]]; then
  require_path "$PYTEST_PYTHON"
  "$PYTEST_PYTHON" -m pytest -q \
    -o "cache_dir=$PYTEST_CACHE" \
    /Users/wen/openmc-workspace/openmc2donjon/tests
else
  echo "pytest smoke skipped"
fi

echo
echo "== C5G7 acceptance =="
c5g7_args=()
if [[ "$C5G7_DONJON" -eq 0 ]]; then
  c5g7_args+=(--skip-donjon)
fi
if [[ "${#c5g7_args[@]}" -gt 0 ]]; then
  OPENMC2DONJON_CAPTURE_LOG=0 RUN_DIR="$RUN_DIR/c5g7" \
    bash "$DATA_DIR/c5g7_validation/run_acceptance.sh" "${c5g7_args[@]}"
else
  OPENMC2DONJON_CAPTURE_LOG=0 RUN_DIR="$RUN_DIR/c5g7" \
    bash "$DATA_DIR/c5g7_validation/run_acceptance.sh"
fi

echo
echo "OpenMC-to-DONJON top-level acceptance: PASS"

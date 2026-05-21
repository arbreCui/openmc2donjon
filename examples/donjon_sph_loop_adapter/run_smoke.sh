#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_donjon_sph_loop_adapter}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DONJON_ROOT="${DONJON_ROOT:-/Users/wen/dragon-5.1/Donjon}"

export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

INPUT_DIR="$RUN_DIR/inputs"
MGXS="$INPUT_DIR/mgxs_library.h5"
REFERENCE_FLUX="$INPUT_DIR/reference_flux.h5"
FLUX_MAP="$INPUT_DIR/flux_map.h5"
EXPECTED="$INPUT_DIR/reference_expected.h5"
CONFIG="$RUN_DIR/donjon_sph_loop_config.json"
REAL_CONFIG="$RUN_DIR/donjon_sph_loop_real_config.json"
CLI_REAL_CONFIG="$RUN_DIR/donjon_sph_loop_cli_real_config.json"
LOOP_DIR="$RUN_DIR/sph_loop"
SUMMARY="$LOOP_DIR/sph_loop_summary.json"
TEMPLATE_DIR="$SCRIPT_DIR/templates"

echo "== openmc2donjon DONJON SPH loop adapter smoke =="

"$PYTHON_BIN" "$SCRIPT_DIR/make_inputs.py" \
  --output-dir "$INPUT_DIR"

"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail 1e-12

"$PYTHON_BIN" "$SCRIPT_DIR/make_config.py" \
  --output "$CONFIG" \
  --output-dir "$LOOP_DIR" \
  --mgxs "$MGXS" \
  --reference-flux "$REFERENCE_FLUX" \
  --flux-map "$FLUX_MAP" \
  --driver "$SCRIPT_DIR/fake_donjon_driver.py" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" "$SCRIPT_DIR/make_real_config.py" \
  --output "$REAL_CONFIG" \
  --output-dir "$LOOP_DIR" \
  --mgxs "$MGXS" \
  --reference-flux "$REFERENCE_FLUX" \
  --flux-map "$FLUX_MAP" \
  --driver "$SCRIPT_DIR/donjon_deck_runner.py" \
  --solve-template "$TEMPLATE_DIR/solve_lflux_dump.x2m.in" \
  --apply-template "$TEMPLATE_DIR/apply_nsph_mac.x2m.in" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" -m openmc2donjon.cli make-donjon-sph-loop-config \
  --output "$CLI_REAL_CONFIG" \
  --output-dir "$LOOP_DIR" \
  --mgxs "$MGXS" \
  --reference-flux "$REFERENCE_FLUX" \
  --flux-map "$FLUX_MAP" \
  --solve-template "$TEMPLATE_DIR/solve_lflux_dump.x2m.in" \
  --donjon-root "$DONJON_ROOT" \
  --python-bin "$PYTHON_BIN"

"$PYTHON_BIN" - "$REAL_CONFIG" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys


config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert config["schema"] == "openmc2donjon.sph-loop-config.v1"
assert "donjon_deck_runner.py" in " ".join(config["solver"]["command"])
assert "solve_lflux_dump.x2m.in" in " ".join(config["solver"]["command"])
assert "apply_nsph_mac.x2m.in" in " ".join(config["postprocess"]["command"])
assert any(part.startswith("/tmp/") for part in config["solver"]["command"])
assert any(part.startswith("/tmp/") for part in config["postprocess"]["command"])
PY

"$PYTHON_BIN" - "$CLI_REAL_CONFIG" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys


config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
solver = config["solver"]["command"]
postprocess = config["postprocess"]["command"]
assert config["schema"] == "openmc2donjon.sph-loop-config.v1"
assert "-m" in solver
assert "openmc2donjon.donjon_deck_runner" in solver
assert "openmc2donjon.donjon_deck_runner" in postprocess
assert "solve_lflux_dump.x2m.in" in " ".join(solver)
assert "apply_nsph_mac.x2m.in" in " ".join(postprocess)
print(f"DONJON SPH loop package config OK: {Path(sys.argv[1])}")
PY

"$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop \
  --config "$CONFIG" \
  --summary-json "$SUMMARY" \
  --force

"$PYTHON_BIN" - "$SUMMARY" "$EXPECTED" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii


summary_path = Path(sys.argv[1])
expected_path = Path(sys.argv[2])
summary = json.loads(summary_path.read_text(encoding="utf-8"))

assert summary["decision"] == "openmc2donjon_sph_loop_passed"
assert summary["iterations"] == 2
assert summary["output_format"] == "macrolib"
assert len(summary["solves"]) == 3
assert len(summary["workflows"]) == 2
assert len(summary["postprocesses"]) == 2
assert summary["final_solve"]["iteration"] == 2
assert summary["final_ascii"].endswith("corrected.macrolib.txt")

with h5py.File(expected_path, "r") as h5:
    expected_sph = h5["expected_sph"][:]
    expected_ids = h5["scalar_flux_ids"][:]

with h5py.File(summary["final_sph_sidecar"], "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected_sph)
    assert h5.attrs["sph_kind"] == "donjon-sph-loop-adapter-smoke-iter2"

macrolib = read_macrolib_ascii(summary["final_ascii"])
np.testing.assert_allclose(macrolib.sph, expected_sph)

first_workflow = summary["workflows"][0]
with h5py.File(first_workflow["donjon_volume_flux_h5"], "r") as h5:
    np.testing.assert_array_equal(h5["scalar_flux_ids"][:], expected_ids)
    np.testing.assert_allclose(h5["donjon_volume_flux"][:], expected_sph * 0.0 + [[40.0, 400.0], [60.0, 300.0]])

print(
    "DONJON SPH loop adapter OK: "
    f"final_sph={float(expected_sph[0, 0]):.8g} "
    f"summary={summary_path}"
)
PY

DRY_ROOT="$RUN_DIR/donjon_root_dry"
DRY_STAGE="$RUN_DIR/donjon_deck_runner_dry/stage"
DRY_OUTPUT="$RUN_DIR/donjon_deck_runner_dry/corrected.macrolib.txt"
DRY_CASE_ID="openmc2donjon_adapter_apply_dry"
DRY_DECK="$DRY_ROOT/data/openmc2donjon/case_runs/donjon_sph_loop_adapter/$DRY_CASE_ID.x2m"
"$PYTHON_BIN" "$SCRIPT_DIR/donjon_deck_runner.py" apply \
  --dry-run \
  --donjon-root "$DRY_ROOT" \
  --deck-template "$TEMPLATE_DIR/apply_nsph_mac.x2m.in" \
  --macrolib "$LOOP_DIR/iter02_sph/corrected.macrolib.txt" \
  --output "$DRY_OUTPUT" \
  --iteration 2 \
  --case-id "$DRY_CASE_ID" \
  --work-dir "$DRY_STAGE"

"$PYTHON_BIN" - "$DRY_DECK" "$DRY_STAGE/input.macrolib.txt" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys


deck = Path(sys.argv[1])
staged_macrolib = Path(sys.argv[2])
assert deck.exists()
assert staged_macrolib.exists()
text = deck.read_text(encoding="utf-8")
assert "DSPH:" in text
assert "MAC:" in text
assert str(staged_macrolib) in text
assert "corrected.macrolib.txt" in text
print(f"DONJON real deck runner dry-run OK: deck={deck}")
PY

if [[ -x "$DONJON_ROOT/rdonjon" ]]; then
  REAL_SOLVE_RESULT="$RUN_DIR/real_donjon_solve.result"
  REAL_FLUX_H5="$RUN_DIR/real_donjon_volume_flux.h5"
  REAL_FLUX_SUMMARY="$RUN_DIR/real_donjon_volume_flux.summary.json"
  REAL_SOLVE_CASE_ID="odj_real_solve"
  "$PYTHON_BIN" "$SCRIPT_DIR/donjon_deck_runner.py" solve \
    --donjon-root "$DONJON_ROOT" \
    --deck-template "$TEMPLATE_DIR/solve_lflux_dump.x2m.in" \
    --macrolib "$LOOP_DIR/iter00_initial/out.macrolib.txt" \
    --result "$REAL_SOLVE_RESULT" \
    --iteration 0 \
    --case-id "$REAL_SOLVE_CASE_ID" \
    --work-dir "/tmp/${REAL_SOLVE_CASE_ID}"

  "$PYTHON_BIN" -m openmc2donjon.cli extract-donjon-volume-flux "$MGXS" \
    --flux-dump "$REAL_SOLVE_RESULT" \
    --scalar-flux-map ASM_LEFT=1,ASM_RIGHT=2 \
    --output "$REAL_FLUX_H5" \
    --summary-json "$REAL_FLUX_SUMMARY" \
    --force

  "$PYTHON_BIN" - "$REAL_SOLVE_RESULT" "$REAL_FLUX_H5" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

import h5py
import numpy as np


listing = Path(sys.argv[1])
flux_h5 = Path(sys.argv[2])
text = listing.read_text(errors="replace")
assert "OPENMC2DONJON DONJON SPH LOOP ADAPTER K-EFFECTIVE" in text
assert "FLUX" in text
with h5py.File(flux_h5, "r") as h5:
    values = h5["donjon_volume_flux"][:]
    np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [1, 2])
    assert values.shape == (2, 2)
    assert np.all(np.isfinite(values))
    assert np.all(values > 0.0)
print(f"DONJON real solve L_FLUX smoke OK: flux={flux_h5}")
PY
else
  echo "DONJON runner unavailable; skipping real L_FLUX solve smoke"
fi

echo "openmc2donjon DONJON SPH loop adapter smoke: PASS"

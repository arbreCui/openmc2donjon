#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_dragon_sph_handoff_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"
DRAGON_ROOT="${DRAGON_ROOT:-/Users/wen/dragon-5.1/Dragon}"
DRAGON_BIN="${DRAGON_BIN:-$DRAGON_ROOT/bin/Darwin_arm64/Dragon}"
TCM38_SOURCE="${TCM38_SOURCE:-$DRAGON_ROOT/data/tmacro_proc/TCM38.c2m}"
ASSERTS_SOURCE="$DRAGON_ROOT/data/assertS.c2m"

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

DRAGON_INPUT="$RUN_DIR/TCM38_sph_export.x2m"
DRAGON_LOG="$RUN_DIR/dragon_sph.log"
DRAGON_MACROLIB="$RUN_DIR/dragon_sph_macrolib.txt"
RECIPE="$RUN_DIR/dragon_sph_recipe.py"
ONE_STEP_RUN_DIR="$RUN_DIR/from_openmc_sph"
ONE_STEP_H5="$ONE_STEP_RUN_DIR/mgxs_library.h5"
ONE_STEP_MACROLIB="$ONE_STEP_RUN_DIR/out.macrolib.txt"
ONE_STEP_MANIFEST="$ONE_STEP_RUN_DIR/manifest.json"

echo "== openmc2donjon DRAGON SPH handoff smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "dragon: $DRAGON_BIN"

if [[ ! -x "$DRAGON_BIN" || ! -f "$TCM38_SOURCE" || ! -f "$ASSERTS_SOURCE" ]]; then
  echo "DRAGON TCM38 inputs are unavailable; skipping DRAGON SPH handoff smoke"
  exit 0
fi

"$PYTHON_BIN" - "$TCM38_SOURCE" "$DRAGON_INPUT" "$DRAGON_MACROLIB" "$RECIPE" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
dragon_input = Path(sys.argv[2])
dragon_macrolib = Path(sys.argv[3])
recipe = Path(sys.argv[4])

text = source.read_text(encoding="utf-8")
text = text.replace(
    "LINKED_LIST ASSMBH TRACK MACRO FLUX SYS EDIT ASSMB2 TRACK2 MACRO2 ;",
    "LINKED_LIST ASSMBH TRACK MACRO FLUX SYS EDIT ASSMB2 TRACK2 MACRO2 MACROSPH ;\n"
    f"SEQ_ASCII SPHMAC :: FILE './{dragon_macrolib.name}' ;",
)
text = text.replace(
    "MACRO2 := EDIT :: STEP UP 'REF-CASE0001' STEP UP MACROLIB\n"
    "                  STEP UP GROUP STEP AT 1 ;",
    "MACROSPH := EDIT :: STEP UP 'REF-CASE0001' STEP UP MACROLIB ;\n"
    "SPHMAC := MACROSPH ;\n"
    "MACRO2 := MACROSPH :: STEP UP GROUP STEP AT 1 ;",
)
dragon_input.write_text(text, encoding="utf-8")

recipe.write_text(
    '''"""Minimal recipe matching the six-mixture, one-group DRAGON TCM38 SPH macrolib."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Domain:
    name: str
    id: int
    volume: float
    fissionable: bool


class EnergyGroups:
    group_edges = np.array([1.0e-5, 1.0e7], dtype=float)


class MGXS:
    def __init__(self, values) -> None:
        self.values = np.asarray(values, dtype=float)

    def get_xs(self, **_kwargs):
        return self.values


class TinyLibrary:
    def __init__(self) -> None:
        self.energy_groups = EnergyGroups()
        self.domains = [
            Domain(f"DRAGON_MIX_{index}", index, 1.0, index in (3, 6))
            for index in range(1, 7)
        ]
        self.data = {}
        for domain in self.domains:
            total = 0.20 + 0.03 * domain.id
            absorption = 0.02 + 0.005 * domain.id
            scatter = total - absorption
            self.data[(domain.id, "total")] = [total]
            self.data[(domain.id, "absorption")] = [absorption]
            self.data[(domain.id, "scatter matrix")] = [[scatter]]
            self.data[(domain.id, "transport")] = [total]
            self.data[(domain.id, "fission")] = [0.01 if domain.fissionable else 0.0]
            self.data[(domain.id, "nu-fission")] = [0.03 if domain.fissionable else 0.0]
            self.data[(domain.id, "chi")] = [1.0 if domain.fissionable else 0.0]

    def get_mgxs(self, domain, mgxs_type):
        return MGXS(self.data[(domain.id, mgxs_type)])


def build_library():
    return TinyLibrary()


def domain_names():
    return {index: f"DRAGON_MIX_{index}" for index in range(1, 7)}


def root_attrs(library):
    return {
        "case": "dragon_tcm38_sph_handoff",
        "domain_mode": "dragon-sph-smoke",
        "domain_type": "synthetic",
    }
''',
    encoding="utf-8",
)
PY

cp "$ASSERTS_SOURCE" "$RUN_DIR/assertS.c2m"
(
  cd "$RUN_DIR"
  "$DRAGON_BIN" < "$DRAGON_INPUT" > "$DRAGON_LOG"
)

if ! grep -q "normal end of execution" "$DRAGON_LOG"; then
  echo "DRAGON SPH run did not end normally; see $DRAGON_LOG" >&2
  exit 1
fi
if [[ ! -s "$DRAGON_MACROLIB" ]]; then
  echo "DRAGON SPH macrolib was not written: $DRAGON_MACROLIB" >&2
  exit 1
fi

"$PYTHON_BIN" - "$DRAGON_MACROLIB" <<'PY'
from pathlib import Path
import sys

import numpy as np

from openmc2donjon.macrolib import extract_sph_from_macrolib_ascii

macrolib = Path(sys.argv[1])
sph = extract_sph_from_macrolib_ascii(macrolib)
if sph.shape != (6, 1):
    raise SystemExit(f"unexpected DRAGON NSPH shape: {sph.shape}")
np.testing.assert_allclose(sph[2, 0], 9.58183825e-01, rtol=2.0e-4, atol=2.0e-4)
print(
    "DRAGON SPH macrolib readback: "
    f"shape={sph.shape} min={float(np.min(sph)):.6g} max={float(np.max(sph)):.6g}"
)
PY

"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --no-load-statepoint \
  --run-dir "$ONE_STEP_RUN_DIR" \
  --force-run-dir \
  --format macrolib \
  --sph-macrolib "$DRAGON_MACROLIB" \
  --check \
  --require-volume \
  --require-transport-dataset

"$PYTHON_BIN" - "$DRAGON_MACROLIB" "$ONE_STEP_H5" "$ONE_STEP_MACROLIB" "$ONE_STEP_MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.macrolib import extract_sph_from_macrolib_ascii, read_macrolib_ascii

dragon_macrolib = Path(sys.argv[1])
h5_path = Path(sys.argv[2])
out_macrolib = Path(sys.argv[3])
manifest_path = Path(sys.argv[4])

expected = extract_sph_from_macrolib_ascii(dragon_macrolib)
with h5py.File(h5_path, "r") as h5:
    actual = np.stack(
        [h5[f"mixtures/DRAGON_MIX_{index}/sph"][:] for index in range(1, 7)]
    )
np.testing.assert_allclose(actual, expected)

macrolib = read_macrolib_ascii(out_macrolib)
np.testing.assert_allclose(macrolib.sph, expected)

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required = {
    "mgxs",
    "macrolib",
    "run-summary",
    "check-summary",
    "sph-source",
    "sph-summary",
    "sph-macrolib",
    "sph-sidecar-summary",
    "recipe",
}
missing = sorted(required - set(labels))
if missing:
    raise SystemExit(f"missing SPH handoff manifest labels: {missing}")
if labels["sph-sidecar-summary"].get("summary_decision") != "openmc2donjon_sph_sidecar_passed":
    raise SystemExit("SPH sidecar summary decision was not recorded")
if labels["sph-summary"].get("summary_decision") != "openmc2donjon_sph_augment_passed":
    raise SystemExit("SPH augment summary decision was not recorded")
print(
    "DRAGON SPH handoff OK: "
    f"mixtures={expected.shape[0]} groups={expected.shape[1]} "
    f"labels={sorted(labels)}"
)
PY

echo
echo "openmc2donjon DRAGON SPH handoff smoke: PASS"

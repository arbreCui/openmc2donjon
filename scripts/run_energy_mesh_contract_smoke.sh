#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_energy_mesh_contract_smoke}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN=python3
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$RUN_DIR"

KNOWN_H5="$RUN_DIR/casmo7_known_mesh.h5"
UNKNOWN_H5="$RUN_DIR/unknown_mesh.h5"
KNOWN_SUMMARY="$RUN_DIR/known_mesh.summary.json"
UNKNOWN_WARN_SUMMARY="$RUN_DIR/unknown_mesh_warn.summary.json"
UNKNOWN_FAIL_SUMMARY="$RUN_DIR/unknown_mesh_fail.summary.json"
UNKNOWN_FAIL_LOG="$RUN_DIR/unknown_mesh_fail.log"

"$PYTHON_BIN" - "$KNOWN_H5" "$UNKNOWN_H5" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.energy_groups import load_energy_mesh


def write_handoff(path: Path, bounds: np.ndarray) -> None:
    groups = int(bounds.size - 1)
    total = np.linspace(0.2, 0.8, groups)
    absorption = np.linspace(0.02, 0.08, groups)
    scatter = np.zeros((1, groups, groups), dtype=float)
    scatter[0, np.arange(groups), np.arange(groups)] = total - absorption
    fission = np.linspace(0.01, 0.02, groups)
    chi = np.zeros(groups, dtype=float)
    chi[0] = 1.0

    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = groups
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=bounds)
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = "moment,from,to"
        fuel.attrs["volume"] = 1.0
        fuel.create_dataset("total", data=total)
        fuel.create_dataset("absorption", data=absorption)
        fuel.create_dataset("fission", data=fission)
        fuel.create_dataset("nu_fission", data=2.5 * fission)
        fuel.create_dataset("chi", data=chi)
        fuel.create_dataset("transport_total", data=total)
        fuel.create_dataset("scatter_matrix", data=scatter)


known = Path(sys.argv[1])
unknown = Path(sys.argv[2])
write_handoff(known, load_energy_mesh("casmo_7").boundaries_descending[::-1])
write_handoff(unknown, np.array([1.0e-5, 1.0, 1.0e7], dtype=float))
PY

"$PYTHON_BIN" -m openmc2donjon.cli check \
  "$KNOWN_H5" \
  --warn-unknown-energy-mesh \
  --summary-json "$KNOWN_SUMMARY" \
  >/dev/null

"$PYTHON_BIN" - "$KNOWN_SUMMARY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
record = payload["inputs"][0]
assert record["ok"] is True
assert record["energy_mesh_id"] == "casmo_7"
assert record["energy_mesh_name"] == "CASMO-7"
assert not any("known energy mesh" in item for item in record["warnings"])
PY

"$PYTHON_BIN" -m openmc2donjon.cli check \
  "$UNKNOWN_H5" \
  --warn-unknown-energy-mesh \
  --summary-json "$UNKNOWN_WARN_SUMMARY" \
  >/dev/null

"$PYTHON_BIN" - "$UNKNOWN_WARN_SUMMARY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
record = payload["inputs"][0]
assert record["ok"] is True
assert record["energy_mesh_id"] is None
assert any(
    "did not match a bundled known energy mesh" in item
    for item in record["warnings"]
)
PY

if "$PYTHON_BIN" -m openmc2donjon.cli check \
  "$UNKNOWN_H5" \
  --require-known-energy-mesh \
  --summary-json "$UNKNOWN_FAIL_SUMMARY" \
  >"$UNKNOWN_FAIL_LOG" 2>&1; then
  echo "expected --require-known-energy-mesh to reject the unknown mesh" >&2
  exit 1
fi

"$PYTHON_BIN" - "$UNKNOWN_FAIL_SUMMARY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
record = payload["inputs"][0]
assert record["ok"] is False
assert record["energy_mesh_id"] is None
assert any(
    "does not match a bundled known energy mesh" in item
    for item in record["issues"]
)
PY

echo "openmc2donjon energy mesh contract smoke: PASS"

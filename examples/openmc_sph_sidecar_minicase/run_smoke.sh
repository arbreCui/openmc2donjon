#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

INPUT_DIR="$RUN_DIR/inputs"
MGXS="$INPUT_DIR/mgxs_library.h5"
CE_FLUX="$INPUT_DIR/openmc_ce_flux.h5"
MG_FLUX="$INPUT_DIR/openmc_mg_flux.h5"
REFERENCE="$INPUT_DIR/reference_expected.h5"
SPH_SIDECAR="$RUN_DIR/openmc_sph_sidecar.h5"
SPH_TABLE="$RUN_DIR/openmc_sph.csv"
AUGMENTED_H5="$RUN_DIR/mgxs_with_openmc_sph.h5"
MCOMPO="$RUN_DIR/out.mcompo.txt"
MACROLIB="$RUN_DIR/out.macrolib.txt"
CHECK_SUMMARY="$RUN_DIR/check_summary.json"
OPENMC_SPH_SUMMARY="$RUN_DIR/openmc_sph_summary.json"
SPH_AUGMENT_SUMMARY="$RUN_DIR/sph_augment_summary.json"

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

echo "== openmc2donjon OpenMC CE/MG SPH sidecar minicase =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

echo
echo "== Build deterministic OpenMC CE/MG inputs =="
"$PYTHON_BIN" "$REPO_ROOT/examples/openmc_sph_sidecar_minicase/make_inputs.py" \
  --output-dir "$INPUT_DIR"

echo
echo "== MGXS input contract =="
"$PYTHON_BIN" -m openmc2donjon.cli check "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --scatter-row-balance-fail 1e-12 \
  --summary-json "$CHECK_SUMMARY"

echo
echo "== Compute OpenMC-side SPH sidecar =="
"$PYTHON_BIN" -m openmc2donjon.cli make-openmc-sph-sidecar "$MGXS" \
  -o "$SPH_SIDECAR" \
  --reference-flux "$CE_FLUX::openmc_volume_flux" \
  --mg-flux "$MG_FLUX::openmc_mg_flux" \
  --table-output "$SPH_TABLE" \
  --damping 0.5 \
  --require-reference-flux-std-dev \
  --max-reference-flux-std-dev-rel 0.02 \
  --require-mg-flux-std-dev \
  --max-mg-flux-std-dev-rel 0.02 \
  --source-label openmc-ce-mg-minicase \
  --summary-json "$OPENMC_SPH_SUMMARY" \
  --force

echo
echo "== Inject OpenMC-side SPH sidecar =="
"$PYTHON_BIN" -m openmc2donjon.cli augment-sph "$MGXS" \
  --sph-source "$SPH_SIDECAR" \
  -o "$AUGMENTED_H5" \
  --summary-json "$SPH_AUGMENT_SUMMARY" \
  --force

echo
echo "== Convert corrected handoff =="
"$PYTHON_BIN" -m openmc2donjon.cli "$AUGMENTED_H5" -o "$MCOMPO" \
  --check \
  --overwrite \
  --require-volume \
  --require-transport-dataset \
  --require-sph \
  --scatter-row-balance-fail 1e-12

"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$AUGMENTED_H5" -o "$MACROLIB" \
  --check \
  --overwrite \
  --require-volume \
  --require-transport-dataset \
  --require-sph \
  --scatter-row-balance-fail 1e-12

echo
echo "== Validate generated OpenMC-side SPH payloads =="
"$PYTHON_BIN" - "$REFERENCE" "$SPH_SIDECAR" "$SPH_TABLE" "$AUGMENTED_H5" "$MCOMPO" "$MACROLIB" "$CHECK_SUMMARY" "$OPENMC_SPH_SUMMARY" "$SPH_AUGMENT_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon.macrolib import read_macrolib_ascii

(
    reference_path,
    sidecar_path,
    table_path,
    augmented_path,
    mcompo_path,
    macrolib_path,
    check_summary_path,
    openmc_sph_summary_path,
    augment_summary_path,
) = [Path(value) for value in sys.argv[1:]]

with h5py.File(reference_path, "r") as ref:
    expected = ref["sph"][:]

with h5py.File(sidecar_path, "r") as h5:
    np.testing.assert_allclose(h5["sph"][:], expected, rtol=1.0e-11)
    if h5.attrs["sph_kind"] != "openmc-ce-mg":
        raise SystemExit("SPH sidecar kind mismatch")
    if not bool(h5.attrs["sph_real"]):
        raise SystemExit("SPH sidecar should be marked real")
    if bool(h5.attrs["sph_applied"]):
        raise SystemExit("SPH sidecar should be marked unapplied")
    if h5.attrs["source_table"] != str(table_path):
        raise SystemExit("SPH sidecar did not record CSV table provenance")

rows = table_path.read_text(encoding="utf-8").strip().splitlines()
if rows[0] != "mixture,group,sph":
    raise SystemExit("unexpected SPH table header")
if len(rows) != expected.size + 1:
    raise SystemExit("unexpected SPH table row count")

with h5py.File(augmented_path, "r") as h5:
    for mix_index, name in enumerate(("FUEL_A", "MOD_B")):
        np.testing.assert_allclose(
            h5[f"mixtures/{name}/sph"][:],
            expected[mix_index],
            rtol=1.0e-11,
        )

macrolib = read_macrolib_ascii(macrolib_path)
np.testing.assert_allclose(macrolib.sph, expected, rtol=1.0e-8)
if macrolib.state_vector[13] != 1:
    raise SystemExit("macrolib SPH state-vector flag is not set")

expected_decisions = {
    check_summary_path: "mgxs_input_contract_passed",
    openmc_sph_summary_path: "openmc2donjon_openmc_sph_sidecar_passed",
    augment_summary_path: "openmc2donjon_sph_augment_passed",
}
for path, decision in expected_decisions.items():
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["decision"] != decision:
        raise SystemExit(f"{path.name}: expected {decision}, got {payload['decision']}")

summary = json.loads(openmc_sph_summary_path.read_text(encoding="utf-8"))
if summary["reference_flux_dataset"] != "openmc_volume_flux":
    raise SystemExit("summary did not record CE flux dataset")
if summary["mg_flux_dataset"] != "openmc_mg_flux":
    raise SystemExit("summary did not record MG flux dataset")
if summary["reference_flux_std_dev_dataset"] != "openmc_volume_flux_std_dev":
    raise SystemExit("summary did not record CE flux std_dev dataset")
if summary["mg_flux_std_dev_dataset"] != "openmc_mg_flux_std_dev":
    raise SystemExit("summary did not record MG flux std_dev dataset")
if summary["reference_flux_max_relative_std_dev"] > 0.02:
    raise SystemExit("CE flux uncertainty gate was not applied")
if summary["mg_flux_max_relative_std_dev"] > 0.02:
    raise SystemExit("MG flux uncertainty gate was not applied")
if summary["source_label"] != "openmc-ce-mg-minicase":
    raise SystemExit("summary did not record source label")

for path in (mcompo_path, macrolib_path):
    blocks = lcm_ascii.read_lcm_ascii(path)
    names = [block.name for block in blocks if block.name]
    if names[:1] != ["SIGNATURE"]:
        raise SystemExit(f"{path}: invalid LCM ASCII output")
    if "NSPH" not in names:
        raise SystemExit(f"{path}: missing NSPH payload")
    print(f"readback {path.name}: blocks={len(blocks)}")

print(
    "OpenMC CE/MG SPH sidecar minicase OK: "
    f"mixtures={expected.shape[0]} groups={expected.shape[1]} "
    f"sph_range={float(np.min(expected)):.6g}..{float(np.max(expected)):.6g}"
)
PY

echo
echo "openmc2donjon OpenMC CE/MG SPH sidecar minicase: PASS"

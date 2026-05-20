#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_production_minicase_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"
OPENMC_EXEC="${OPENMC_EXEC:-}"
OPENMC_THREADS="${OPENMC_THREADS:-2}"
MINICASE_PARTICLES="${MINICASE_PARTICLES:-200}"
MINICASE_BATCHES="${MINICASE_BATCHES:-12}"
MINICASE_INACTIVE="${MINICASE_INACTIVE:-4}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/python ]]; then
    PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

if [[ -z "$OPENMC_EXEC" ]]; then
  if [[ -x /Users/wen/miniforge3/envs/openmc-dev/bin/openmc ]]; then
    OPENMC_EXEC=/Users/wen/miniforge3/envs/openmc-dev/bin/openmc
  elif command -v openmc >/dev/null 2>&1; then
    OPENMC_EXEC="$(command -v openmc)"
  fi
fi

mkdir -p "$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PACKAGE_SRC${PYTHONPATH:+:$PYTHONPATH}"

EXAMPLE_DIR="$REPO_ROOT/examples/production_minicase"
CASE_DIR="$RUN_DIR/openmc_case"
CONVERT_RUN_DIR="$RUN_DIR/openmc2donjon_run"
STATEPOINT="$CASE_DIR/statepoint.${MINICASE_BATCHES}.h5"
MGXS="$CONVERT_RUN_DIR/mgxs_library.h5"
MCO="$CONVERT_RUN_DIR/out.mcompo.txt"
SUMMARY="$CONVERT_RUN_DIR/run_summary.json"
CHECK_SUMMARY="$CONVERT_RUN_DIR/check_summary.json"
MANIFEST="$CONVERT_RUN_DIR/manifest.json"
SURFACE_FLUX="$RUN_DIR/openmc_surface_flux.h5"
SURFACE_FLUX_SUMMARY="$RUN_DIR/openmc_surface_flux_summary.json"
ADF_SIDECAR="$RUN_DIR/adf_sidecar.h5"
ADF_SIDECAR_SUMMARY="$RUN_DIR/adf_sidecar_summary.json"
ADF_RUN_DIR="$RUN_DIR/openmc2donjon_adf_run"
ADF_H5="$ADF_RUN_DIR/mgxs_library.h5"
ADF_MCO="$ADF_RUN_DIR/out.mcompo.txt"
ADF_RUN_SUMMARY="$ADF_RUN_DIR/run_summary.json"
ADF_CHECK_SUMMARY="$ADF_RUN_DIR/check_summary.json"
ADF_INJECT_SUMMARY="$ADF_RUN_DIR/adf_summary.json"
ADF_MANIFEST="$ADF_RUN_DIR/manifest.json"
ADF_FACES="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"
SURFACE_FLUX_MU_EDGES="0.0,0.25,0.5,0.75,1.0"

echo "== openmc2donjon production minicase smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"
echo "openmc: ${OPENMC_EXEC:-not found}"

if [[ -z "$OPENMC_EXEC" ]]; then
  echo "production minicase skipped: OpenMC executable not found"
  exit 0
fi

if ! "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import sys

try:
    import openmc
except Exception as exc:
    print(f"OpenMC Python import failed: {exc}", file=sys.stderr)
    raise SystemExit(1)

cross_sections = openmc.config.get("cross_sections")
if not cross_sections or not Path(cross_sections).exists():
    print(f"OpenMC cross_sections not available: {cross_sections}", file=sys.stderr)
    raise SystemExit(1)
print(f"OpenMC cross_sections: {cross_sections}")
PY
then
  echo "production minicase skipped: OpenMC Python runtime is not configured"
  exit 0
fi

echo
echo "== Build OpenMC XML =="
"$PYTHON_BIN" "$EXAMPLE_DIR/build_model.py" \
  --case-dir "$CASE_DIR" \
  --particles "$MINICASE_PARTICLES" \
  --batches "$MINICASE_BATCHES" \
  --inactive "$MINICASE_INACTIVE"

echo
echo "== Run OpenMC =="
(
  cd "$CASE_DIR"
  "$OPENMC_EXEC" -s "$OPENMC_THREADS"
)
if [[ ! -e "$STATEPOINT" ]]; then
  echo "missing statepoint: $STATEPOINT" >&2
  exit 1
fi

echo
echo "== Export and convert =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$CONVERT_RUN_DIR" \
  --check \
  --require-volume \
  --require-transport-dataset

"$PYTHON_BIN" - "$MGXS" "$MCO" "$SUMMARY" "$CHECK_SUMMARY" "$MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary

mgxs = Path(sys.argv[1])
mco = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
check_summary_path = Path(sys.argv[4])
manifest_path = Path(sys.argv[5])

with h5py.File(mgxs, "r") as h5:
    if h5.attrs["case"] != "production_minicase":
        raise SystemExit("missing production_minicase root attr")
    if h5.attrs["domain_mode"] != "assembly":
        raise SystemExit("unexpected domain_mode")
    if int(h5.attrs["energy_groups"]) != 2:
        raise SystemExit("unexpected group count")
    if int(h5.attrs["legendre_order"]) != 1:
        raise SystemExit("unexpected Legendre order")
    names = sorted(h5["mixtures"])
    if names != ["ASM_FUEL_LEFT", "ASM_MOD_RIGHT"]:
        raise SystemExit(f"unexpected mixture names: {names}")
    for name in names:
        if "transport_total" not in h5[f"mixtures/{name}"]:
            raise SystemExit(f"{name}: missing transport_total")
        volume = float(h5[f"mixtures/{name}"].attrs["volume"])
        if volume <= 0.0:
            raise SystemExit(f"{name}: non-positive volume")

blocks = lcm_ascii.read_lcm_ascii(mco)
block_names = [block.name for block in blocks if block.name]
if block_names[:1] != ["SIGNATURE"] or "MIXTURES" not in block_names:
    raise SystemExit("invalid MULTICOMPO output")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(summary)
if summary_errors:
    raise SystemExit("invalid from-OpenMC summary: " + "; ".join(summary_errors))
if summary["mixture_names"] != ["ASM_FUEL_LEFT", "ASM_MOD_RIGHT"]:
    raise SystemExit("summary mixture names mismatch")
if summary["energy_groups"] != 2 or summary["legendre_order"] != 1:
    raise SystemExit("summary group/order mismatch")
if summary["checked"] is not True or summary["check_passed"] is not True:
    raise SystemExit("summary did not record checked conversion")

check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
if check_summary["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("production minicase preflight did not pass")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required = {"mgxs", "mcompo", "run-summary", "check-summary", "recipe"}
if set(labels) != required:
    raise SystemExit(f"unexpected manifest labels: {sorted(labels)}")
if labels["check-summary"].get("summary_decision") != "mgxs_input_contract_passed":
    raise SystemExit("manifest did not record preflight decision")

print(
    "production minicase readback OK: "
    f"blocks={len(blocks)} mixtures={summary['mixture_count']} "
    f"groups={summary['energy_groups']} P{summary['legendre_order']}"
)
PY

echo
echo "== Export OpenMC surface flux =="
"$PYTHON_BIN" -m openmc2donjon.cli export-surface-flux "$STATEPOINT" \
  --mgxs "$MGXS" \
  -o "$SURFACE_FLUX" \
  --tally-name openmc2donjon_surface_current_mu \
  --mesh-shape 1,2 \
  --mu-edges "$SURFACE_FLUX_MU_EDGES" \
  --face-area 4.0 \
  --faces "$ADF_FACES" \
  --summary-json "$SURFACE_FLUX_SUMMARY"

echo
echo "== Build flux-ratio ADF sidecar =="
"$PYTHON_BIN" -m openmc2donjon.cli make-adf-sidecar "$MGXS" \
  -o "$ADF_SIDECAR" \
  --mode flux-ratio \
  --surface-flux "$SURFACE_FLUX" \
  --homogeneous-face-flux "$SURFACE_FLUX::surface_flux/mean" \
  --faces "$ADF_FACES" \
  --invalid-fill 1.0 \
  --adf-kind flux-ratio-smoke \
  --adf-real false \
  --adf-source-label "production minicase surface-flux self-ratio smoke" \
  --summary-json "$ADF_SIDECAR_SUMMARY"

echo
echo "== Export and convert with ADF sidecar =="
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$EXAMPLE_DIR/export_recipe.py" \
  --statepoint "$STATEPOINT" \
  --run-dir "$ADF_RUN_DIR" \
  --adf-source "$ADF_SIDECAR" \
  --adf-faces "$ADF_FACES" \
  --adf-kind flux-ratio-smoke \
  --adf-real false \
  --check \
  --require-adf \
  --require-volume \
  --require-transport-dataset

"$PYTHON_BIN" - "$SURFACE_FLUX" "$SURFACE_FLUX_SUMMARY" "$ADF_SIDECAR" "$ADF_SIDECAR_SUMMARY" "$ADF_H5" "$ADF_MCO" "$ADF_RUN_SUMMARY" "$ADF_CHECK_SUMMARY" "$ADF_INJECT_SUMMARY" "$ADF_MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary

surface_flux = Path(sys.argv[1])
surface_flux_summary_path = Path(sys.argv[2])
sidecar = Path(sys.argv[3])
sidecar_summary_path = Path(sys.argv[4])
mgxs = Path(sys.argv[5])
mco = Path(sys.argv[6])
summary_path = Path(sys.argv[7])
check_summary_path = Path(sys.argv[8])
adf_summary_path = Path(sys.argv[9])
manifest_path = Path(sys.argv[10])
faces = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")

surface_flux_summary = json.loads(surface_flux_summary_path.read_text(encoding="utf-8"))
if surface_flux_summary["decision"] != "openmc2donjon_surface_flux_export_passed":
    raise SystemExit("surface-flux summary did not pass")
if surface_flux_summary["schema"] != "openmc2donjon.surface-flux.v1":
    raise SystemExit("surface-flux summary schema mismatch")
if surface_flux_summary["mesh_shape"] != [1, 2]:
    raise SystemExit("surface-flux mesh shape mismatch")
if tuple(surface_flux_summary["face_names"]) != faces:
    raise SystemExit("surface-flux face names mismatch")

with h5py.File(surface_flux, "r") as h5:
    if h5.attrs["schema"] != "openmc2donjon.surface-flux.v1":
        raise SystemExit("surface-flux HDF5 schema mismatch")
    values = h5["surface_flux/mean"][:]
    if values.shape != (1, 2, 2, 4):
        raise SystemExit(f"unexpected surface-flux shape: {values.shape}")

sidecar_summary = json.loads(sidecar_summary_path.read_text(encoding="utf-8"))
if sidecar_summary["decision"] != "openmc2donjon_adf_sidecar_passed":
    raise SystemExit("ADF sidecar summary did not pass")
if sidecar_summary["schema"] != "openmc2donjon.adf-sidecar.v1":
    raise SystemExit("ADF sidecar summary schema mismatch")
if sidecar_summary["mode"] != "flux-ratio":
    raise SystemExit("ADF sidecar mode mismatch")
if sidecar_summary["adf_kind"] != "flux-ratio-smoke":
    raise SystemExit("ADF sidecar kind mismatch")
if sidecar_summary["adf_real"] is not False:
    raise SystemExit("ADF sidecar summary should be marked adf_real=false")
if tuple(sidecar_summary["face_names"]) != faces:
    raise SystemExit("ADF sidecar summary face names mismatch")

with h5py.File(sidecar, "r") as h5:
    if h5.attrs["adf_kind"] != "flux-ratio-smoke" or h5.attrs["adf_real"] != "false":
        raise SystemExit("ADF sidecar provenance mismatch")
    values = h5["adf"][:]
    if values.shape != (2, 4, 2):
        raise SystemExit(f"unexpected ADF sidecar shape: {values.shape}")
    np.testing.assert_allclose(values, 1.0)

with h5py.File(mgxs, "r") as h5:
    if h5.attrs["adf_kind"] != "flux-ratio-smoke" or h5.attrs["adf_real"] != "false":
        raise SystemExit("injected HDF5 ADF provenance mismatch")
    names = sorted(h5["mixtures"])
    if names != ["ASM_FUEL_LEFT", "ASM_MOD_RIGHT"]:
        raise SystemExit(f"unexpected ADF mixture names: {names}")
    for name in names:
        for face in faces:
            np.testing.assert_allclose(h5[f"mixtures/{name}/adf/{face}"][:], 1.0)

blocks = lcm_ascii.read_lcm_ascii(mco)
block_names = [block.name for block in blocks if block.name]
for required_name in ("MACROLIB", "ADF", "HADF", *faces):
    if required_name not in block_names:
        raise SystemExit(f"ADF MULTICOMPO readback missing {required_name}")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(summary)
if summary_errors:
    raise SystemExit("invalid ADF from-OpenMC summary: " + "; ".join(summary_errors))
if summary["checked"] is not True or summary["check_passed"] is not True:
    raise SystemExit("ADF conversion summary did not record checked conversion")

check_summary = json.loads(check_summary_path.read_text(encoding="utf-8"))
if check_summary["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("ADF production minicase preflight did not pass")

adf_summary = json.loads(adf_summary_path.read_text(encoding="utf-8"))
if adf_summary["schema"] != "openmc2donjon.adf-augment.v1":
    raise SystemExit("ADF injection summary schema mismatch")
if adf_summary["decision"] != "openmc2donjon_adf_augment_passed":
    raise SystemExit("ADF injection summary did not pass")
if tuple(adf_summary["face_names"]) != faces:
    raise SystemExit("ADF injection summary face names mismatch")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
required = {
    "mgxs",
    "mcompo",
    "run-summary",
    "check-summary",
    "adf-source",
    "adf-summary",
    "recipe",
}
if set(labels) != required:
    raise SystemExit(f"unexpected ADF manifest labels: {sorted(labels)}")
if labels["adf-summary"].get("summary_schema") != "openmc2donjon.adf-augment.v1":
    raise SystemExit("ADF manifest did not record augment summary schema")
if labels["adf-summary"].get("summary_decision") != "openmc2donjon_adf_augment_passed":
    raise SystemExit("ADF manifest did not record augment decision")

print(
    "production minicase ADF readback OK: "
    f"blocks={len(blocks)} faces={','.join(faces)} labels={sorted(labels)}"
)
PY

echo
echo "openmc2donjon production minicase smoke: PASS"

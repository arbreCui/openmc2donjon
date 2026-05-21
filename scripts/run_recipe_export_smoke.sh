#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_SRC="${OPENMC2DONJON_SRC:-$REPO_ROOT/src}"
RUN_DIR="${RUN_DIR:-/private/tmp/openmc2donjon_recipe_export_smoke}"
PYTHON_BIN="${PYTHON_BIN:-}"
SCATTER_ROW_BALANCE_WARN="${OPENMC2DONJON_SCATTER_ROW_BALANCE_WARN:-1e-12}"
SCATTER_ROW_BALANCE_FAIL="${OPENMC2DONJON_SCATTER_ROW_BALANCE_FAIL:-1e-10}"
SCATTER_ROW_BALANCE_ARGS=(
  --scatter-row-balance-warn "$SCATTER_ROW_BALANCE_WARN"
  --scatter-row-balance-fail "$SCATTER_ROW_BALANCE_FAIL"
)

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

RECIPE="$REPO_ROOT/examples/recipe_export_smoke/minimal_recipe.py"
STATEPOINT="$RUN_DIR/statepoint.fake.h5"
DOCTOR_SUMMARY="$RUN_DIR/doctor_summary.json"
MGXS="$RUN_DIR/minimal_recipe_mgxs.h5"
MCO="$RUN_DIR/minimal_recipe.mcompo.txt"
MAC="$RUN_DIR/minimal_recipe.macrolib.txt"
INSPECT_SUMMARY="$RUN_DIR/minimal_recipe_inspect_summary.json"
ONE_STEP_RUN_DIR="$RUN_DIR/one_step_run"
ONE_STEP_H5="$ONE_STEP_RUN_DIR/mgxs_library.h5"
ONE_STEP_MCO="$ONE_STEP_RUN_DIR/out.mcompo.txt"
ONE_STEP_SUMMARY="$ONE_STEP_RUN_DIR/run_summary.json"
ONE_STEP_CHECK_SUMMARY="$ONE_STEP_RUN_DIR/check_summary.json"
ONE_STEP_DIFF_SUMMARY="$ONE_STEP_RUN_DIR/diff_summary.json"
BUNDLE_MANIFEST="$ONE_STEP_RUN_DIR/manifest.json"
ONE_STEP_DRY_RUN_DIR="$RUN_DIR/one_step_dry_run_$$"
ADF_SIDECAR="$RUN_DIR/adf_sidecar.h5"
ADF_RUN_DIR="$RUN_DIR/one_step_adf_run"
ADF_H5="$ADF_RUN_DIR/mgxs_library.h5"
ADF_MCO="$ADF_RUN_DIR/out.mcompo.txt"
ADF_SUMMARY="$ADF_RUN_DIR/adf_summary.json"
ADF_CHECK_SUMMARY="$ADF_RUN_DIR/check_summary.json"
ADF_MANIFEST="$ADF_RUN_DIR/manifest.json"
SPH_SIDECAR="$RUN_DIR/sph_sidecar.h5"
SPH_RUN_DIR="$RUN_DIR/one_step_sph_run"
SPH_H5="$SPH_RUN_DIR/mgxs_library.h5"
SPH_MAC="$SPH_RUN_DIR/out.macrolib.txt"
SPH_SUMMARY="$SPH_RUN_DIR/sph_summary.json"
SPH_CHECK_SUMMARY="$SPH_RUN_DIR/check_summary.json"
SPH_MANIFEST="$SPH_RUN_DIR/manifest.json"

echo "== openmc2donjon recipe export smoke =="
echo "repo: $REPO_ROOT"
echo "run_dir: $RUN_DIR"
echo "python: $PYTHON_BIN"

printf 'recipe smoke statepoint marker\n' > "$STATEPOINT"
"$PYTHON_BIN" - "$ADF_SIDECAR" "$SPH_SIDECAR" <<'PY'
from pathlib import Path
import sys

import h5py
import numpy as np

adf_path = Path(sys.argv[1])
sph_path = Path(sys.argv[2])
values = np.array(
    [
        [[1.01, 1.02], [0.99, 0.98]],
        [[1.03, 1.04], [0.97, 0.96]],
    ]
)
with h5py.File(adf_path, "w") as h5:
    h5.attrs["adf_kind"] = "production"
    h5.attrs["adf_real"] = "true"
    dataset = h5.create_dataset("adf", data=values)
    dataset.attrs["mixture_names"] = np.asarray(["FUEL_A", "MOD_A"], dtype="S")
    dataset.attrs["face_names"] = np.asarray(["FD_XMIN", "FD_XMAX"], dtype="S")

sph_values = np.array([[1.10, 0.90], [0.95, 1.05]], dtype=float)
with h5py.File(sph_path, "w") as h5:
    h5.attrs["schema"] = "openmc2donjon.sph-sidecar.v1"
    h5.attrs["sph_kind"] = "production-sph"
    h5.attrs["sph_real"] = True
    h5.attrs["sph_applied"] = False
    dataset = h5.create_dataset("sph", data=sph_values)
    dataset.attrs["mixture_names"] = np.asarray(["FUEL_A", "MOD_A"], dtype="S")
PY

echo
echo "== Doctor =="
"$PYTHON_BIN" -m openmc2donjon.cli doctor \
  --recipe "$RECIPE" \
  --summary-json "$DOCTOR_SUMMARY"
"$PYTHON_BIN" - "$DOCTOR_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload["schema"] != "openmc2donjon.doctor.v1":
    raise SystemExit("unexpected doctor summary schema")
if payload["decision"] != "openmc2donjon_doctor_passed":
    raise SystemExit(f"doctor did not pass: {payload}")
PY

echo
echo "== Recipe dry-run =="
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$RECIPE" \
  --no-load-statepoint \
  --dry-run

echo
echo "== Recipe export =="
"$PYTHON_BIN" -m openmc2donjon.export_cli \
  --recipe "$RECIPE" \
  --statepoint "$STATEPOINT" \
  -o "$MGXS"

echo
echo "== HDF5 inspect =="
"$PYTHON_BIN" -m openmc2donjon.cli inspect "$MGXS" \
  --limit 5 \
  --summary-json "$INSPECT_SUMMARY"
"$PYTHON_BIN" - "$INSPECT_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload["schema"] != "openmc2donjon.mgxs-inspect.v1":
    raise SystemExit("unexpected inspect summary schema")
summary = payload["inputs"][0]
if summary["mixture_count"] != 2 or summary["calculation_count"] != 2:
    raise SystemExit(f"unexpected inspect summary counts: {summary}")
PY

echo
echo "== HDF5 preflight =="
"$PYTHON_BIN" -m openmc2donjon.cli check \
  "$MGXS" \
  --require-volume \
  --require-transport-dataset \
  --format multicompo \
  --output "$MCO" \
  --check \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== Converter readback =="
"$PYTHON_BIN" -m openmc2donjon.cli "$MGXS" -o "$MCO" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"
"$PYTHON_BIN" -m openmc2donjon.cli --format macrolib "$MGXS" -o "$MAC" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== One-step dry-run =="
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --dry-run \
  --run-dir "$ONE_STEP_DRY_RUN_DIR" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"
if [[ -e "$ONE_STEP_DRY_RUN_DIR" ]]; then
  echo "dry-run unexpectedly wrote $ONE_STEP_DRY_RUN_DIR" >&2
  exit 1
fi

echo
echo "== One-step managed run directory =="
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --statepoint "$STATEPOINT" \
  --run-dir "$ONE_STEP_RUN_DIR" \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

echo
echo "== HDF5 diff =="
"$PYTHON_BIN" -m openmc2donjon.cli diff "$MGXS" "$ONE_STEP_H5" \
  --summary-json "$ONE_STEP_DIFF_SUMMARY"

echo
echo "== Managed run-dir manifest =="
"$PYTHON_BIN" - "$BUNDLE_MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

manifest_path = Path(sys.argv[1])
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
if payload["schema"] != "openmc2donjon.bundle.v1":
    raise SystemExit("unexpected bundle manifest schema")
labels = {artifact["label"]: artifact for artifact in payload["artifacts"]}
required = {
    "mgxs",
    "mcompo",
    "run-summary",
    "check-summary",
    "recipe",
}
missing = sorted(required - set(labels))
if missing:
    raise SystemExit(f"bundle manifest missing labels: {missing}")
for label, artifact in labels.items():
    if len(artifact["sha256"]) != 64:
        raise SystemExit(f"{label}: invalid sha256")
    if not Path(artifact["path"]).exists():
        raise SystemExit(f"{label}: bundled path is missing")
if labels["check-summary"].get("summary_decision") != "mgxs_input_contract_passed":
    raise SystemExit("bundle did not record check decision")
print(f"bundle {manifest_path.parent.name}: artifacts={payload['artifact_count']}")
PY

"$PYTHON_BIN" - "$MGXS" "$MCO" "$MAC" "$STATEPOINT" "$ONE_STEP_H5" "$ONE_STEP_MCO" "$ONE_STEP_SUMMARY" "$ONE_STEP_CHECK_SUMMARY" "$ONE_STEP_DIFF_SUMMARY" <<'PY'
import json
from pathlib import Path
import sys

import h5py
from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_summary import validate_from_openmc_summary

mgxs = Path(sys.argv[1])
mco = Path(sys.argv[2])
mac = Path(sys.argv[3])
statepoint = str(Path(sys.argv[4]))
one_step_h5 = Path(sys.argv[5])
one_step_mco = Path(sys.argv[6])
summary = Path(sys.argv[7])
check_summary = Path(sys.argv[8])
diff_summary = Path(sys.argv[9])

for path in (mgxs, one_step_h5):
    with h5py.File(path, "r") as h5:
        names = sorted(h5["mixtures"])
        if names != ["FUEL_A", "MOD_A"]:
            raise SystemExit(f"unexpected mixtures: {names}")
        if h5.attrs["domain_mode"] != "recipe_smoke":
            raise SystemExit("missing recipe_smoke domain_mode")
        if h5.attrs["statepoint_marker"] != statepoint:
            raise SystemExit("recipe did not receive the statepoint path")

for path in (mco, mac, one_step_mco):
    blocks = lcm_ascii.read_lcm_ascii(path)
    names = [block.name for block in blocks if block.name]
    if names[:1] != ["SIGNATURE"]:
        raise SystemExit(f"{path}: invalid LCM ASCII output")
    print(f"readback {path.name}: blocks={len(blocks)} first={names[:6]}")

payload = json.loads(summary.read_text(encoding="utf-8"))
summary_errors = validate_from_openmc_summary(payload)
if summary_errors:
    raise SystemExit("invalid summary schema: " + "; ".join(summary_errors))
check_payload = json.loads(check_summary.read_text(encoding="utf-8"))
if check_payload["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("one-step checked conversion preflight did not pass")
diff_payload = json.loads(diff_summary.read_text(encoding="utf-8"))
if diff_payload["decision"] != "mgxs_hdf5_diff_passed":
    raise SystemExit("one-step HDF5 diff did not pass")
if payload["checked"] is not True or payload["check_passed"] is not True:
    raise SystemExit("one-step summary did not record checked preflight success")
if payload["check_summary_json"] != str(check_summary):
    raise SystemExit("one-step summary check_summary_json path mismatch")
if payload["mixture_names"] != ["FUEL_A", "MOD_A"]:
    raise SystemExit("unexpected summary mixture names")
if payload["hdf5"] != str(one_step_h5) or payload["output"] != str(one_step_mco):
    raise SystemExit("summary paths do not match one-step outputs")
print(f"summary {summary.name}: schema={payload['schema']} mixtures={payload['mixture_count']}")
PY

echo
echo "== One-step with ADF sidecar =="
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --statepoint "$STATEPOINT" \
  --run-dir "$ADF_RUN_DIR" \
  --adf-source "$ADF_SIDECAR" \
  --adf-faces FD_XMIN,FD_XMAX \
  --check \
  --require-adf \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

"$PYTHON_BIN" - "$ADF_H5" "$ADF_MCO" "$ADF_SUMMARY" "$ADF_CHECK_SUMMARY" "$ADF_MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
from openmc2donjon import lcm_ascii

h5_path = Path(sys.argv[1])
mco_path = Path(sys.argv[2])
adf_summary = Path(sys.argv[3])
check_summary = Path(sys.argv[4])
manifest_path = Path(sys.argv[5])

with h5py.File(h5_path, "r") as h5:
    np.testing.assert_allclose(h5["mixtures/FUEL_A/adf/FD_XMIN"][:], [1.01, 1.02])
    np.testing.assert_allclose(h5["mixtures/MOD_A/adf/FD_XMAX"][:], [0.97, 0.96])

blocks = lcm_ascii.read_lcm_ascii(mco_path)
names = [block.name for block in blocks if block.name]
for required_name in ("MACROLIB", "ADF", "HADF", "FD_XMIN", "FD_XMAX"):
    if required_name not in names:
        raise SystemExit(f"{mco_path}: missing {required_name} block")

adf_payload = json.loads(adf_summary.read_text(encoding="utf-8"))
if adf_payload["decision"] != "openmc2donjon_adf_augment_passed":
    raise SystemExit("ADF injection summary did not pass")
if adf_payload["face_names"] != ["FD_XMIN", "FD_XMAX"]:
    raise SystemExit("ADF injection summary face names mismatch")

check_payload = json.loads(check_summary.read_text(encoding="utf-8"))
if check_payload["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("ADF one-step preflight did not pass")

manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}
required_labels = {
    "mgxs",
    "mcompo",
    "run-summary",
    "check-summary",
    "adf-source",
    "adf-summary",
    "recipe",
}
missing = sorted(required_labels - set(labels))
if missing:
    raise SystemExit(f"ADF bundle manifest missing labels: {missing}")
if labels["adf-summary"].get("summary_schema") != "openmc2donjon.adf-augment.v1":
    raise SystemExit("ADF bundle did not record augment summary schema")
if labels["adf-summary"].get("summary_decision") != "openmc2donjon_adf_augment_passed":
    raise SystemExit("ADF bundle did not record augment decision")
print(f"ADF one-step readback: blocks={len(blocks)} labels={sorted(labels)}")
PY

echo
echo "== One-step with SPH sidecar =="
"$PYTHON_BIN" -m openmc2donjon.from_openmc_cli \
  --recipe "$RECIPE" \
  --statepoint "$STATEPOINT" \
  --run-dir "$SPH_RUN_DIR" \
  --format macrolib \
  --sph-source "$SPH_SIDECAR" \
  --sph-kind production-sph \
  --sph-real true \
  --sph-applied false \
  --check \
  --require-volume \
  --require-transport-dataset \
  "${SCATTER_ROW_BALANCE_ARGS[@]}"

"$PYTHON_BIN" - "$SPH_H5" "$SPH_MAC" "$SPH_SUMMARY" "$SPH_CHECK_SUMMARY" "$SPH_MANIFEST" <<'PY'
import json
from pathlib import Path
import sys

import h5py
import numpy as np
from openmc2donjon.macrolib import read_macrolib_ascii

h5_path = Path(sys.argv[1])
macrolib_path = Path(sys.argv[2])
sph_summary = Path(sys.argv[3])
check_summary = Path(sys.argv[4])
manifest_path = Path(sys.argv[5])

with h5py.File(h5_path, "r") as h5:
    np.testing.assert_allclose(h5["mixtures/FUEL_A/sph"][:], [1.10, 0.90])
    np.testing.assert_allclose(h5["mixtures/MOD_A/sph"][:], [0.95, 1.05])
    if h5.attrs["sph_kind"] != "production-sph":
        raise SystemExit("SPH provenance kind was not preserved")

macrolib = read_macrolib_ascii(macrolib_path)
np.testing.assert_allclose(macrolib.sph, [[1.10, 0.90], [0.95, 1.05]])

sph_payload = json.loads(sph_summary.read_text(encoding="utf-8"))
if sph_payload["decision"] != "openmc2donjon_sph_augment_passed":
    raise SystemExit("SPH injection summary did not pass")

check_payload = json.loads(check_summary.read_text(encoding="utf-8"))
if check_payload["decision"] != "mgxs_input_contract_passed":
    raise SystemExit("SPH one-step preflight did not pass")

manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}
required_labels = {
    "mgxs",
    "macrolib",
    "run-summary",
    "check-summary",
    "sph-source",
    "sph-summary",
    "recipe",
}
missing = sorted(required_labels - set(labels))
if missing:
    raise SystemExit(f"SPH bundle manifest missing labels: {missing}")
if labels["sph-summary"].get("summary_schema") != "openmc2donjon.sph-augment.v1":
    raise SystemExit("SPH bundle did not record augment summary schema")
if labels["sph-summary"].get("summary_decision") != "openmc2donjon_sph_augment_passed":
    raise SystemExit("SPH bundle did not record augment decision")
print(f"SPH one-step readback: NSPH={macrolib.sph.shape} labels={sorted(labels)}")
PY

echo
echo "openmc2donjon recipe export smoke: PASS"

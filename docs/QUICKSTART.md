# Quickstart

This page is the shortest path from a fresh checkout to a working
OpenMC-to-DONJON conversion.

## Install

From the repository root:

```sh
python -m pip install -e .
```

Or run directly from source:

```sh
export PYTHONPATH=src
```

## Check The User Entry Point

Check the local Python/package environment:

```sh
openmc2donjon doctor
```

Run the tiny recipe/statepoint smoke:

```sh
bash scripts/run_recipe_export_smoke.sh
```

This checks:

- environment doctor;
- recipe dry-run metadata preflight;
- one-step dry-run conversion-plan preflight;
- recipe/statepoint export to the HDF5 handoff contract;
- HDF5 inventory inspect;
- HDF5 preflight;
- HDF5 baseline diff;
- managed run directory and bundle manifest;
- `L_MULTICOMPO` write/readback;
- root `L_MACROLIB` write/readback;
- one-command `openmc2donjon-from-openmc` conversion.

On a machine with OpenMC and continuous-energy data configured, run the minimal
production-style case:

```sh
bash scripts/run_production_minicase_smoke.sh
```

## One-Step OpenMC To DONJON

For a real OpenMC case, write a small recipe that builds the case's
`openmc.mgxs.Library`. You can start from
[`examples/openmc_recipe_template/`](../examples/openmc_recipe_template/) or inspect
[`examples/production_minicase/`](../examples/production_minicase/). Then run:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --dry-run \
  --run-dir runs/case1 \
  --check
```

The dry-run output includes a production checklist for MGXS coverage,
transport/STRD readiness, domain-to-mixture mapping, volumes, and `domain_mode`.

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --run-dir runs/case1 \
  --check
```

The run directory contains the HDF5 handoff, DONJON ASCII output, summary JSON,
check summary when `--check` is enabled, and `manifest.json`. Existing managed
files are refused unless `--force-run-dir` is set. Add side artifacts to the
same manifest with repeatable `--extra-artifact LABEL=PATH` options:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --run-dir runs/case1 \
  --extra-artifact surface-flux=openmc_surface_flux.h5 \
  --extra-artifact low-order-driver=low_order_driver.h5 \
  --extra-artifact homogeneous-face-flux=homogeneous_face_flux.h5 \
  --check
```

To keep explicit paths instead of using a managed run directory:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --keep-hdf5 mgxs_library.h5 \
  -o out.mcompo.txt \
  --summary-json run_summary.json
```

To add extra files to an existing handoff manifest:

```sh
openmc2donjon bundle \
  --output-dir runs/case1 \
  --mgxs runs/case1/mgxs_library.h5 \
  --mcompo runs/case1/out.mcompo.txt \
  --run-summary runs/case1/run_summary.json \
  --extra notes=notes.txt \
  --force
```

For root `L_MACROLIB` output:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --format macrolib \
  -o out.macrolib.txt \
  --summary-json run_summary.json
```

## Two-Step Workflow

If you want to inspect or archive the HDF5 before conversion:

```sh
openmc2donjon-export \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  -o mgxs_library.h5

openmc2donjon inspect mgxs_library.h5
openmc2donjon mgxs_library.h5 -o out.mcompo.txt --check
```

To confirm a regenerated handoff matches a baseline:

```sh
openmc2donjon diff accepted_mgxs.h5 mgxs_library.h5
```

To inject computed ADF/DF values before conversion:

```sh
openmc2donjon make-adf-sidecar mgxs_library.h5 \
  -o adf_sidecar.h5 \
  --mode unity

openmc2donjon augment-adf mgxs_library.h5 \
  --adf-source adf_sidecar.h5 \
  -o mgxs_with_adf.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX
```

`make-adf-sidecar --mode unity` writes identity ADF values marked
`adf_real=false`; use it to verify plumbing before replacing the sidecar with
case-specific physics ADF/DF values.

For a physics sidecar, provide heterogeneous and homogeneous face-flux HDF5
datasets:

```sh
openmc2donjon export-surface-flux statepoint.120.h5 \
  --mgxs mgxs_library.h5 \
  -o openmc_surface_flux.h5 \
  --tally-name openmc2donjon_surface_current_mu \
  --mesh-shape 1,2 \
  --mu-edges 0.0,0.25,0.5,0.75,1.0 \
  --face-area 4.0

openmc2donjon make-low-order-driver mgxs_library.h5 \
  -o low_order_driver.h5 \
  --volume-flux raw_low_order_driver.h5 \
  --net-current raw_low_order_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX

openmc2donjon make-homogeneous-face-flux mgxs_library.h5 \
  -o homogeneous_face_flux.h5 \
  --volume-flux low_order_driver.h5 \
  --net-current low_order_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --face-widths 4.0

openmc2donjon make-adf-sidecar mgxs_library.h5 \
  -o adf_sidecar.h5 \
  --mode flux-ratio \
  --surface-flux openmc_surface_flux.h5 \
  --homogeneous-face-flux homogeneous_face_flux.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX
```

Or inject the sidecar during the one-step OpenMC export:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --run-dir runs/case1 \
  --adf-source adf_sidecar.h5 \
  --adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --check --require-adf
```

Run preflight on the HDF5:

```sh
openmc2donjon check mgxs_library.h5
```

## C5G7 Accepted Check

Run the portable converter-side acceptance check:

```sh
bash scripts/release_check.sh --skip-tests
```

On a machine with the local DRAGON/DONJON checkout and staged data, run the full
DONJON-side check:

```sh
bash scripts/release_check.sh --run-donjon
```

## Next Documents

- [OpenMC export workflow](OPENMC_EXPORT_WORKFLOW.md)
- [HDF5 input contract](HDF5_INPUT_CONTRACT.md)
- [From-OpenMC summary JSON](FROM_OPENMC_SUMMARY_SCHEMA.md)
- [Validation summary](VALIDATION.md)

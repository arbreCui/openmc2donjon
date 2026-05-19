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
- `L_MULTICOMPO` write/readback;
- root `L_MACROLIB` write/readback;
- one-command `openmc2donjon-from-openmc` conversion.

## One-Step OpenMC To DONJON

For a real OpenMC case, write a small recipe that builds the case's
`openmc.mgxs.Library`. You can start from
[`examples/openmc_recipe_template/`](../examples/openmc_recipe_template/). Then run:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --dry-run \
  -o out.mcompo.txt \
  --check
```

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  -o out.mcompo.txt \
  --check
```

To keep the intermediate HDF5 handoff for audit/debugging:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --keep-hdf5 mgxs_library.h5 \
  -o out.mcompo.txt \
  --summary-json run_summary.json
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

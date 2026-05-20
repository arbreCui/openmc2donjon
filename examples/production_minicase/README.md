# Production Minicase

This is a tiny continuous-energy OpenMC case that exercises the production
workflow without relying on the locked C5G7 snapshot.

It has two homogenized cell domains:

```text
ASM_FUEL_LEFT  -> DONJON mixture 1
ASM_MOD_RIGHT  -> DONJON mixture 2
```

The physics is intentionally small and noisy; it is a workflow example, not an
accepted benchmark.  Its purpose is to prove that a user can build an OpenMC
case, run MGXS tallies, and feed the resulting statepoint directly to
`openmc2donjon-from-openmc`.

## Run

```sh
CASE_DIR=/tmp/openmc2donjon_minicase/case
RUN_DIR=/tmp/openmc2donjon_minicase/output

python examples/production_minicase/build_model.py \
  --case-dir "$CASE_DIR" \
  --particles 200 \
  --batches 12 \
  --inactive 4

openmc -s 2 "$CASE_DIR"

OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
openmc2donjon-from-openmc \
  --recipe examples/production_minicase/export_recipe.py \
  --statepoint "$CASE_DIR/statepoint.12.h5" \
  --run-dir "$RUN_DIR" \
  --check \
  --require-volume \
  --require-transport-dataset
```

The managed run directory contains:

```text
mgxs_library.h5
out.mcompo.txt
run_summary.json
check_summary.json
manifest.json
export_recipe.py
```

To exercise the ADF/DF path, provide the low-order driver volume flux and
outward net current density in an HDF5 fixture, then let the one-step workflow
export the OpenMC surface-flux tally, canonicalize and check the low-order
handoff, reconstruct homogeneous face flux, build the flux-ratio sidecar, and
inject it before conversion:

```sh
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
openmc2donjon-from-openmc \
  --recipe examples/production_minicase/export_recipe.py \
  --statepoint "$CASE_DIR/statepoint.12.h5" \
  --run-dir /tmp/openmc2donjon_minicase/output_adf \
  --build-flux-ratio-adf \
  --export-surface-flux \
  --surface-flux-tally-name openmc2donjon_surface_current_mu \
  --surface-flux-mesh-shape 1,2 \
  --surface-flux-mu-edges 0.0,0.25,0.5,0.75,1.0 \
  --surface-flux-face-area 4.0 \
  --low-order-volume-flux /tmp/openmc2donjon_minicase/raw_low_order_driver.h5 \
  --low-order-net-current /tmp/openmc2donjon_minicase/raw_low_order_driver.h5 \
  --low-order-net-current-sign-convention auto \
  --adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --adf-face-widths 4.0 \
  --adf-invalid-fill 1.0 \
  --adf-kind flux-ratio-minicase \
  --adf-real false \
  --require-volume \
  --require-transport-dataset
```

The minicase low-order driver is a tiny fixture marked through the final
sidecar as `adf_real=false`; it is an interface and workflow check, not a
production physics ADF estimate.

For the repository smoke test, run:

```sh
bash scripts/run_production_minicase_smoke.sh
```

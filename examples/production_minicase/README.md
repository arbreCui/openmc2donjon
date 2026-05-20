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

To exercise the ADF/DF path, export the OpenMC surface-flux tally, canonicalize
a low-order driver handoff, reconstruct the homogeneous face flux, build a
flux-ratio sidecar, and rerun the one-step workflow with sidecar injection:

```sh
openmc2donjon export-surface-flux "$CASE_DIR/statepoint.12.h5" \
  --mgxs "$RUN_DIR/mgxs_library.h5" \
  -o /tmp/openmc2donjon_minicase/openmc_surface_flux.h5 \
  --tally-name openmc2donjon_surface_current_mu \
  --mesh-shape 1,2 \
  --mu-edges 0.0,0.25,0.5,0.75,1.0 \
  --face-area 4.0

openmc2donjon make-low-order-driver "$RUN_DIR/mgxs_library.h5" \
  -o /tmp/openmc2donjon_minicase/low_order_driver.h5 \
  --volume-flux /tmp/openmc2donjon_minicase/raw_low_order_driver.h5 \
  --net-current /tmp/openmc2donjon_minicase/raw_low_order_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX

openmc2donjon check-low-order-driver \
  "$RUN_DIR/mgxs_library.h5" /tmp/openmc2donjon_minicase/low_order_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --face-widths 4.0

openmc2donjon make-homogeneous-face-flux "$RUN_DIR/mgxs_library.h5" \
  -o /tmp/openmc2donjon_minicase/homogeneous_face_flux.h5 \
  --volume-flux /tmp/openmc2donjon_minicase/low_order_driver.h5 \
  --net-current /tmp/openmc2donjon_minicase/low_order_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --face-widths 4.0

openmc2donjon make-adf-sidecar "$RUN_DIR/mgxs_library.h5" \
  -o /tmp/openmc2donjon_minicase/adf_sidecar.h5 \
  --mode flux-ratio \
  --surface-flux /tmp/openmc2donjon_minicase/openmc_surface_flux.h5 \
  --homogeneous-face-flux /tmp/openmc2donjon_minicase/homogeneous_face_flux.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --invalid-fill 1.0 \
  --adf-kind flux-ratio-minicase \
  --adf-real false

OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
openmc2donjon-from-openmc \
  --recipe examples/production_minicase/export_recipe.py \
  --statepoint "$CASE_DIR/statepoint.12.h5" \
  --run-dir /tmp/openmc2donjon_minicase/output_adf \
  --adf-source /tmp/openmc2donjon_minicase/adf_sidecar.h5 \
  --adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --extra-artifact surface-flux=/tmp/openmc2donjon_minicase/openmc_surface_flux.h5 \
  --extra-artifact low-order-driver=/tmp/openmc2donjon_minicase/low_order_driver.h5 \
  --extra-artifact homogeneous-face-flux=/tmp/openmc2donjon_minicase/homogeneous_face_flux.h5 \
  --check \
  --require-adf \
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

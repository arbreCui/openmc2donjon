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

OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
openmc2donjon-from-openmc \
  --recipe examples/production_minicase/export_recipe.py \
  --no-load-statepoint \
  --dry-run \
  --strict-dry-run \
  --run-dir "$RUN_DIR" \
  --check \
  --require-volume \
  --require-h-factor \
  --expected-energy-group-structure OPENMC2DONJON-PRODUCTION-MINICASE-2G \
  --require-transport-dataset

openmc -s 2 "$CASE_DIR"

OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
openmc2donjon-from-openmc \
  --recipe examples/production_minicase/export_recipe.py \
  --statepoint "$CASE_DIR/statepoint.12.h5" \
  --run-dir "$RUN_DIR" \
  --force-run-dir \
  --check \
  --require-volume \
  --require-h-factor \
  --expected-energy-group-structure OPENMC2DONJON-PRODUCTION-MINICASE-2G \
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

The recipe also writes `openmc_volume_flux` from a real OpenMC cell/energy flux
tally.  That lets the same statepoint prepare a fixed-OpenMC SPH loop handoff:

```sh
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
openmc2donjon prepare-openmc-sph-loop \
  --recipe examples/production_minicase/export_recipe.py \
  --statepoint "$CASE_DIR/statepoint.12.h5" \
  --run-dir /tmp/openmc2donjon_minicase/sph_loop_handoff \
  --solve-template examples/sph_loop_minicase/templates/solve_lflux_dump.x2m.in \
  --scalar-flux-map ASM_FUEL_LEFT=2,ASM_MOD_RIGHT=4 \
  --force

openmc2donjon run-sph-loop \
  --config /tmp/openmc2donjon_minicase/sph_loop_handoff/sph_loop_inputs/loop_config.json \
  --force
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
  --force-run-dir \
  --build-flux-ratio-adf \
  --export-surface-flux \
  --surface-flux-tally-name openmc2donjon_surface_current_mu \
  --surface-flux-mesh-shape 1,2 \
  --surface-flux-mu-edges 0.0,0.25,0.5,0.75,1.0 \
  --surface-flux-face-area 4.0 \
  --low-order-raw-driver /tmp/openmc2donjon_minicase/raw_low_order_driver.h5 \
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

If an external low-order or nodal solve has already produced the homogeneous
face-flux denominator, the one-step workflow can consume those files directly
and skip the low-order reconstruction artifacts:

```sh
OPENMC2DONJON_MINICASE_DIR="$CASE_DIR" \
openmc2donjon-from-openmc \
  --recipe examples/production_minicase/export_recipe.py \
  --statepoint "$CASE_DIR/statepoint.12.h5" \
  --run-dir /tmp/openmc2donjon_minicase/output_external_adf \
  --force-run-dir \
  --build-flux-ratio-adf \
  --adf-surface-flux /tmp/openmc2donjon_minicase/openmc_surface_flux.h5::surface_flux/mean \
  --homogeneous-face-flux /tmp/openmc2donjon_minicase/homogeneous_face_flux.h5::homogeneous_face_flux \
  --adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --adf-invalid-fill 1.0 \
  --adf-kind flux-ratio-minicase-external \
  --adf-real false \
  --require-volume \
  --require-transport-dataset
```

For the repository smoke test, run:

```sh
bash scripts/run_production_minicase_smoke.sh
```

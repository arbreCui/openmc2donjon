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

For the repository smoke test, run:

```sh
bash scripts/run_production_minicase_smoke.sh
```

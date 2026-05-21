# DONJON SPH Loop Adapter

This example is a small template for connecting `openmc2donjon run-sph-loop`
to a DONJON low-order solve.  The default smoke is intentionally synthetic:
`fake_donjon_driver.py` writes a deterministic `L_FLUX` dump so the adapter
contract can be tested without a local DONJON deck.

Run it with:

```sh
bash examples/donjon_sph_loop_adapter/run_smoke.sh
```

The generated config demonstrates the production contract:

- `solver.command` consumes `{ascii_input}` and writes `{result}`.
- `map_h5` maps OpenMC/DONJON mixtures to one-based DONJON scalar flux IDs.
- `postprocess.command` can replace `{workflow_ascii}` with a DONJON-corrected
  handoff at `{output}` after each SPH update.
- placeholders available to commands include `{iteration}`, `{iteration1}`,
  `{loop_dir}`, `{solve_dir}`, `{workflow_dir}`, `{input_h5}`,
  `{ascii_input}`, `{result}`, `{previous_sph}`, `{workflow_ascii}`,
  `{sph_sidecar}`, `{augmented_h5}`, and `{output}`.

For a real case, keep `make_config.py` as the pattern and replace the fake
driver command with the DONJON card runner that dumps scalar volume fluxes.

## Real DONJON Runner

For production wiring, start from `make_real_config.py` instead.  It writes a
`run-sph-loop` config that calls `donjon_deck_runner.py` for both phases:

```sh
python examples/donjon_sph_loop_adapter/make_real_config.py \
  --output loop.json \
  --output-dir runs/sph_loop \
  --mgxs mgxs_library.h5 \
  --reference-flux reference_flux.h5 \
  --flux-map flux_map.h5 \
  --donjon-root /path/to/dragon-5.1/Donjon
```

The runner stages the current ASCII macrolib under a short `/tmp` path, renders
an `.x2m` deck under
`$DONJON_ROOT/data/openmc2donjon/case_runs/donjon_sph_loop_adapter/`, runs
`rdonjon -q`, then copies the DONJON listing or corrected macrolib back to the
path requested by `run-sph-loop`.

Templates:

- `templates/solve_lflux_dump.x2m.in` is a minimal runnable 1x2 Cartesian
  solve-side template.  Replace the geometry/tracking/solve body with the real
  DONJON model and keep
  `UTL: FLUX :: IMPR STATE-VECTOR * DUMP ;`.
- `templates/apply_nsph_mac.x2m.in` is a generic `DSPH`/`MAC` postprocess deck
  for applying `NSPH` factors written by the loop.

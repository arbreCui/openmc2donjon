# DONJON SPH Loop Adapter

This example is a small template for connecting `openmc2donjon run-sph-loop`
to a DONJON low-order solve.  It is intentionally synthetic: the included
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

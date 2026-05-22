# Minimal SPH Loop User Case

This example is a small, runnable template for the production SPH workflow:

1. start from an OpenMC-style homogeneous MGXS HDF5 file,
2. export the current macrolib to the low-order solver,
3. read back low-order volume flux,
4. compute SPH factors against the OpenMC reference flux,
5. write the next corrected macrolib.

Run it from the repository root:

```bash
RUN_DIR=/private/tmp/openmc2donjon_sph_loop_minicase \
  bash examples/sph_loop_minicase/run_smoke.sh
```

The script writes a clean case directory under `$RUN_DIR/case`:

- `inputs/mgxs_library.h5`: two-mixture, two-group MGXS input.
- `inputs/reference_flux.h5`: OpenMC volume flux used as the fixed reference.
- `inputs/flux_map.h5`: mapping from mixture to low-order scalar flux unknown.
- `loop_config.json`: concrete `run-sph-loop` config.
- `sph_loop/`: iteration outputs, final macrolib, summary, audit files, bundle.

`fake_low_order_solver.py` is only the replaceable interface stub. In a real case,
replace `solver.command` with the DONJON solve card/runner that consumes
`{ascii_input}` and writes `{result}`, and replace `postprocess.command` with the
DONJON card/runner that applies `{sph_sidecar}` to `{workflow_ascii}` and writes
`{output}`.

The checked-in `loop_config.json` shows the shape of the user config. The smoke
script generates an equivalent concrete config with paths resolved for the run
directory.

For a DONJON-backed handoff, generate the real-runner config:

```bash
python examples/sph_loop_minicase/make_real_config.py \
  --output /private/tmp/openmc2donjon_sph_loop_minicase/case/real_loop_config.json \
  --output-dir /private/tmp/openmc2donjon_sph_loop_minicase/case/sph_loop_real \
  --mgxs /private/tmp/openmc2donjon_sph_loop_minicase/case/inputs/mgxs_library.h5 \
  --reference-flux /private/tmp/openmc2donjon_sph_loop_minicase/case/inputs/reference_flux.h5 \
  --flux-map /private/tmp/openmc2donjon_sph_loop_minicase/case/inputs/flux_map.h5
```

That config calls `python -m openmc2donjon.donjon_deck_runner`. The included
`templates/solve_lflux_dump.x2m.in` is intentionally tiny; in a production case,
replace its geometry and flux-solve body with the DONJON model that matches the
OpenMC homogenization domains.

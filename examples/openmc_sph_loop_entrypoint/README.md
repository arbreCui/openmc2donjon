# OpenMC To SPH Loop Entrypoint

This example shows the shortest production-style handoff from an OpenMC
recipe/statepoint export into the fixed-OpenMC SPH loop inputs.

```bash
RUN_DIR=/private/tmp/openmc2donjon_openmc_sph_loop_entrypoint \
  bash examples/openmc_sph_loop_entrypoint/run_smoke.sh
```

The smoke writes:

- `openmc_sph_loop_handoff/mgxs_library.h5`: MGXS HDF5 from the recipe.
- `openmc_sph_loop_handoff/out.macrolib.txt`: first DONJON macrolib handoff.
- `openmc_sph_loop_handoff/sph_loop_inputs/reference_flux.h5`: canonical OpenMC volume flux.
- `openmc_sph_loop_handoff/sph_loop_inputs/flux_map.h5`: DONJON scalar flux unknown map.
- `openmc_sph_loop_handoff/sph_loop_inputs/loop_config.json`: config for `openmc2donjon run-sph-loop`.

For a real case, the recipe should build the OpenMC `mgxs.Library`, load the
statepoint, and either write `openmc_volume_flux` in `postprocess_hdf5` or pass
an external OpenMC volume-flux CSV/HDF5 to `prepare-openmc-sph-loop`.

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

The recipe deliberately exports both uncertainty paths used by the production
SPH audit: MGXS `*_std_dev` datasets and
`/openmc_volume_flux_std_dev`. The smoke enables the matching strict gates with
`--require-std-dev-coverage`,
`--acceptance-require-mgxs-std-dev-coverage`, and
`--acceptance-require-reference-flux-std-dev`.

For a real case, the recipe should build the OpenMC `mgxs.Library`, load the
statepoint, and either write `openmc_volume_flux` in `postprocess_hdf5` or pass
an external OpenMC volume-flux CSV/HDF5 to `prepare-openmc-sph-loop`. When the
case policy requires uncertainty auditing, export the corresponding std-dev
datasets and turn on the same strict gates used by this smoke.

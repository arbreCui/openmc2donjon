# C5G7 SPH Loop Example

This is the reusable C5G7 fixed-OpenMC SPH loop entrypoint.

It writes a `run-sph-loop` JSON config, calls the packaged
`openmc2donjon.donjon_deck_runner` with a C5G7 solve template, applies DONJON
`DSPH:/MAC:` postprocessing, and leaves the final corrected MACROLIB in the
configured run directory.

```bash
PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python \
DONJON_ROOT=/Users/wen/dragon-5.1/Donjon \
RUN_DIR=/private/tmp/openmc2donjon_c5g7_sph_loop_example \
bash examples/donjon_openmc2donjon/c5g7_sph_loop/run.sh
```

The generated config is the important artifact.  A production run can also
write a manifest-backed bundle containing the fixed OpenMC HDF5, final ASCII
handoff, SPH sidecar, summary JSON, and audit files:

```bash
openmc2donjon run-sph-loop \
  --config "$RUN_DIR/c5g7_sph_loop_config.json" \
  --bundle-dir "$RUN_DIR/sph_loop/bundle" \
  --force
```

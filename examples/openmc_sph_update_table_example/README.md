# OpenMC-Side SPH Update-Table Example

This deterministic example exercises the `make-sph-update-table` path:

```text
OpenMC CE reference flux
OpenMC MG macro flux
previous SPH table
  -> make-sph-update-table
  -> make-sph-sidecar
  -> augment-sph
  -> convert to L_MACROLIB
```

It represents the new project direction where SPH factors are computed on
the OpenMC side from a fixed high-fidelity CE reference and an OpenMC MG
macro solve using the same geometry. The converter then carries those SPH
factors into the HDF5 handoff and writes the DRAGON/DONJON ASCII library.

This is not a DONJON feedback loop. DONJON is not run by this example, and
no DONJON flux is fed back into the SPH update.

Run it from the repository root:

```sh
examples/openmc_sph_update_table_example/run_smoke.sh
```

The default run directory is
`/private/tmp/openmc2donjon_openmc_sph_update_table_example`; set `RUN_DIR`
to override it.

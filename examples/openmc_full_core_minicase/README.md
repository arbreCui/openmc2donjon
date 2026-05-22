# OpenMC Full-Core Assembly-Wise Minicase

This example is the minimal version of the intended production workflow:
OpenMC builds one 3D core, tallies one MGXS domain per assembly position, and
`openmc2donjon` exports those domains without merging positions that share a
material.

The 3 by 3 core maps directly to DONJON mixtures:

```text
ASM_Y01_X01  ASM_Y01_X02  ASM_Y01_X03
ASM_Y02_X01  ASM_Y02_X02  ASM_Y02_X03
ASM_Y03_X01  ASM_Y03_X02  ASM_Y03_X03
```

Each `ASM_Y##_X##` is an OpenMC cell domain in the full-core geometry. The
recipe attaches `assembly_x`, `assembly_y`, and `axial_layer` attributes to the
HDF5 mixture so the spatial map can be reconstructed downstream.

Run the smoke test:

```bash
bash examples/openmc_full_core_minicase/run_smoke.sh
```

The smoke uses `openmc2donjon-from-openmc --production` so the exported HDF5 is
checked for explicit volumes, `transport_total`, fissionable H-factor data,
scatter row balance, and production-critical uncertainty metadata before the
ASCII file is accepted.

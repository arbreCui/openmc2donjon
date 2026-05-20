# OpenMC Hex Minicase

This is a minimal real OpenMC entry-point example for hexagonal geometry. It
builds and runs a tiny seven-position hex lattice, then exports the OpenMC
statepoint through the normal `openmc2donjon-from-openmc` workflow.

The exported domains are OpenMC cell domains:

```text
HEX_C
HEX_E
HEX_NE
HEX_NW
HEX_W
HEX_SW
HEX_SE
```

Each cell domain becomes one DONJON mixture. The smoke checks 2 energy groups,
P1 scattering, positive volumes, explicit `transport_total`, checked
`L_MULTICOMPO`, and checked `L_MACROLIB` readback.

This example is a production-workflow capability smoke, not an accepted physics
benchmark. It deliberately does not claim a reference hex `k-eff`.

## Run

```sh
bash examples/openmc_hex_minicase/run_smoke.sh
```

The smoke writes all generated files under `/private/tmp` by default.

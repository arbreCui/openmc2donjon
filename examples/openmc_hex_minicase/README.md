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

Each cell domain becomes one DONJON mixture through explicit `DomainExportSpec`
mapping with positive volumes. The smoke checks strict recipe dry-run, 2 energy
groups, P1 scattering, explicit `transport_total`, checked `L_MULTICOMPO`, and
checked `L_MACROLIB` readback.

This example is a production-workflow capability smoke, not an accepted physics
benchmark. It deliberately does not claim a reference hex `k-eff`.

## Run

```sh
bash examples/openmc_hex_minicase/run_smoke.sh
```

The smoke writes all generated files under `/private/tmp` by default.

## DONJON k-eff Comparison

On a machine with the local DRAGON/DONJON checkout available, run:

```sh
bash examples/openmc_hex_minicase/run_keff_comparison.sh
```

This performs the same OpenMC export, writes the generated case under
`Donjon/data/openmc2donjon/openmc_hex_minicase_keff_runs/<timestamp>`, consumes
the fresh `out.mcompo.txt` through `NCR:` and TRIVAC diffusion, and writes
`keff_comparison.json`. The default comparison settings are intentionally
higher-statistics than `run_smoke.sh`; override `HEX_MINICASE_PARTICLES`,
`HEX_MINICASE_BATCHES`, `HEX_MINICASE_INACTIVE`, or
`OPENMC2DONJON_HEX_MAX_DELTA_PCM` for faster local checks.

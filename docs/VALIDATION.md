# Validation Summary

## Accepted Line

The accepted validation line is C5G7 assembly-wise homogenization:

```text
OpenMC C5G7 MGXS/ADF HDF5
  -> openmc2donjon L_MULTICOMPO
  -> DONJON assembly-wise diffusion/SPN smokes
```

The mapping is one spatial MGXS domain to one DONJON mixture. The accepted C5G7
case uses nine assembly-wise mixtures.

## Reference Results

| Case | k-effective | Note |
| --- | ---: | --- |
| OpenMC reference | `1.18798` | upstream Monte Carlo reference |
| DONJON diffusion | `1.1896194220` | about `+164 pcm` vs OpenMC |
| DONJON SPN3 | `1.1912802458` | about `+330 pcm` vs OpenMC |
| DONJON SPN3 with first-order scattering retained | `1.1912822723` | sensitivity smoke |
| DONJON 2-group ADF smoke | `1.18533289` | ADF active |
| DONJON 2-group NODF smoke | `1.20179343` | ADF disabled comparison |

The accepted source HDF5 snapshot is:

```text
examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5
```

## OpenMC Exporter Integration

The OpenMC-side exporter has been checked against the existing C5G7
assembly-wise P1 statepoint. The local upstream driver now rebuilds the
OpenMC `mgxs.Library`, loads the saved statepoint, and writes the HDF5 contract
through `export_openmc_mgxs_library`.

Smoke result:

```text
mixtures = 9
groups = 7
scatter_matrix shape = (2, 7, 7)
transport_total present = true
max_abs_diff vs previous custom HDF5 dump = 0.0
```

Local reproduction command:

```sh
PYTHONPATH=src python scripts/export_c5g7_statepoint.py \
  --statepoint /Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5 \
  --adf-source examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5 \
  -o /private/tmp/openmc2donjon_c5g7_exporter_assembly_p1.h5
```

The accepted production HDF5 snapshot has been regenerated through this exporter
path, with the existing production ADF payload copied forward. The top-level
acceptance run remains green.

## Reproduce Converter-Side Smoke

```sh
bash scripts/run_c5g7_demo.sh
```

This runs package tests, converts the accepted C5G7 HDF5 to fresh
`L_MULTICOMPO` and `L_MACROLIB` outputs under `/private/tmp`, and reads both
files back through the LCM ASCII parser.

## Reproduce DONJON-Side Smoke

On a machine with a local DRAGON/DONJON checkout and the accepted data staged
under `Donjon/data/openmc2donjon`:

```sh
OPENMC2DONJON_ROOT=/path/to/dragon-5.1 \
OPENMC2DONJON_DATA_DIR=/path/to/dragon-5.1/Donjon/data/openmc2donjon \
  bash scripts/run_c5g7_demo.sh --run-donjon
```

The DONJON smoke runs:

- manifest-driven C5G7 conversion and diffusion k-effective check;
- MULTICOMPO carry-through through `NCR:`;
- 2-group NSSF ADF-vs-NODF comparison.

## Experimental BURN-Axis Smoke

The experimental multi-state serializer has a separate DONJON consumer smoke:

```sh
bash examples/donjon_openmc2donjon/run_burnup_axis_smoke.sh
```

It generates a tiny two-state HDF5 fixture, converts it to `L_MULTICOMPO`, runs
`NCR:` at `BURN=0` and `BURN=10`, and checks that the recovered `NTOT0` values
come from different calculations. This verifies the `PARKEY=BURN` + `TREE` +
`CALCULATIONS` selection path, but it is not an accepted physics benchmark.

## Hex Status

Hex support is implemented as converter/modeling capability, but this repository
does not currently include an accepted hex benchmark. A hex validation line
should only be promoted when the benchmark has complete material/profile/control
inputs and a defensible reference solution.

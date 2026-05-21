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

## Validation Contract

Accepted physics validation cases must be OpenMC-sourced:

```text
OpenMC heterogeneous/reference calculation
  -> OpenMC homogenized MGXS + transport correction + ADF/DF
  -> openmc2donjon
  -> DONJON k-effective
```

The DONJON comparison checks whether DONJON can consume OpenMC-derived
homogenized data and reproduce the OpenMC reference at the intended
homogenization level. It does not claim to reproduce another code's native
equivalence treatment, such as DRAGON/APEX `SPH` factors or `LEAK B2`
processing, unless those corrections are explicitly supplied as OpenMC-side
handoff data.

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

The C5G7 recipe is a compatibility recipe for this accepted baseline: it
explicitly selects OpenMC's `consistent nu-scatter matrix` MGXS because that is
the tally definition present in the locked statepoint. New production recipes
should use ordinary `scatter matrix` unless a non-default scattering definition
is intentional.

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
PYTHONPATH=src \
C5G7_ADF_SOURCE=examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5 \
  python -m openmc2donjon.export_cli \
  --recipe scripts/c5g7_export_recipe.py \
  --statepoint /Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5 \
  -o /private/tmp/openmc2donjon_c5g7_exporter_assembly_p1.h5
```

The accepted production HDF5 snapshot has been regenerated through this exporter
path, with the existing production ADF payload copied forward. The top-level
acceptance run remains green.

## ADF Denominator Regeneration

The accepted C5G7 production ADF denominator is not only a static HDF5 fixture.
When the local DONJON dump files are available,
`scripts/run_c5g7_donjon_face_flux_smoke.sh` regenerates
`c5g7_homogeneous_face_flux_donjon.h5` from the real DONJON `L_FLUX` and
`L_TRACK` ASCII dumps, checks exact dataset parity with the accepted artifact,
runs the face-flux contract preflight, and rebuilds the accepted ADF payload
from the regenerated denominator.

Local reproduction command:

```sh
bash scripts/run_c5g7_donjon_face_flux_smoke.sh
```

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

It generates a tiny two-state HDF5 fixture, runs the input-contract preflight,
converts it to `L_MULTICOMPO`, runs `NCR:` at `BURN=0` and `BURN=10`, and checks
that the recovered `NTOT0` values come from different calculations. This verifies
the `PARKEY=BURN` + `TREE` + `CALCULATIONS` selection path, but it is not an
accepted physics benchmark.

## Candidate Examples

`examples/hex_minicase` builds a synthetic OpenMC-style hex-domain MGXS HDF5
handoff, then runs checked `L_MULTICOMPO` and `L_MACROLIB` conversion/readback.
It exercises seven hex cell domains, P1 scattering, explicit `transport_total`,
and six-face ADF data.

```sh
bash examples/hex_minicase/run_smoke.sh
```

This is a converter capability smoke, not an accepted physics benchmark.

`examples/openmc_hex_minicase` builds and runs a tiny continuous-energy OpenMC
hex lattice, exports the statepoint through `openmc2donjon-from-openmc`, and
then runs checked `L_MULTICOMPO` and `L_MACROLIB` conversion/readback. It
exercises the real production recipe/statepoint entry point with seven OpenMC
hex cell domains, 2 groups, P1 scattering, explicit `transport_total`, and
positive volumes.

```sh
bash examples/openmc_hex_minicase/run_smoke.sh
```

This is an OpenMC workflow capability smoke, not an accepted physics benchmark.
It is part of the default `scripts/release_check.sh` gate so both Cartesian and
hexagonal OpenMC recipe/statepoint workflows are exercised before handoff.

`examples/uox_5x5_tg6` adapts a local DRAGON/APEX UOX 5x5 TG6 HDF5 file into
the openmc2donjon MGXS input contract, then runs checked `L_MULTICOMPO` and
`L_MACROLIB` conversion/readback. It is useful because it exercises a second
non-C5G7, multi-domain, 8-group, P1-scatter source path.

```sh
bash examples/uox_5x5_tg6/run_smoke.sh
```

This example is a candidate coverage case, not an accepted physics benchmark.
The source is an APEX/APOLLO2-A HDF5 file rather than an OpenMC statepoint, and
the adapter is intentionally kept in the example directory.

Its DRAGON/DONJON reference cards use APEX/DRAGON equivalence processing
(`SPH` plus `LEAK B2`). Those corrections are not recoverable from a plain
OpenMC-style MGXS handoff, so this example must not be promoted to an accepted
k-effective benchmark unless a matching OpenMC-sourced reference and correction
handoff are added.

Additional local candidate examples can be included in the release check on
machines with the local source files:

```sh
bash scripts/release_check.sh --run-local-candidates
```

## Hex Status

Hex support is implemented as converter/modeling capability and covered by both
the synthetic `examples/hex_minicase` smoke and the real OpenMC
`examples/openmc_hex_minicase` recipe/statepoint smoke. This repository does not
currently include an accepted hex benchmark. A hex validation line should only
be promoted when the benchmark has complete material/profile/control inputs and
a defensible reference solution.

# UOX 5x5 TG6 Candidate

This directory stages a small non-C5G7 candidate example from the local
DRAGON-5 distribution:

```text
/Users/wen/dragon-5.1/Dragon/data/UOX_5x5_TG6_sym8_multiDom.x2m
/Users/wen/dragon-5.1/Donjon/data/UOX_5x5_TG6_sym8_multiDom_rt2.x2m
/Users/wen/dragon-5.1/Dragon/data/UOX_5x5_TG6_sym8_multiDom_proc/UOX_5x5_TG6_sym8_multiDom.h5
```

The source HDF5 is an APEX/APOLLO2-A output, not an OpenMC MGXS file. The
adapter in this directory is therefore an example-side bridge into the
`openmc2donjon` HDF5 input contract; it is not part of the accepted OpenMC
validation line.

This example checks converter coverage and DONJON consumption. It is not a
physics k-effective benchmark for this project, because the local DRAGON/DONJON
reference cards rely on APEX/DRAGON `SPH` plus `LEAK B2` equivalence processing.
Those corrections are not recoverable from a plain OpenMC-style homogenized
MGXS handoff.

## Source Facts

- Geometry in the DRAGON card: 3 by 3 Cartesian eighth-assembly map with six
  merged domains.
- Group structure: 8 neutron groups.
- Legendre order: P1 scattering in the source macro XS.
- Transport correction: the source `DIFF` array is treated as a diffusion
  coefficient `D`; the adapter writes `STRD = 1 / (3D)` and retains `D` as
  provenance.
- Source calculations: four branch points, all at burnup 0.
- Reference DRAGON card target: `K-INFINITY = 1.320080`.
- Reference DONJON/TRIVAC card target: `K-EFFECTIVE = 0.9982139`.

The current local DRAGON/DONJON executables fail while opening the APEX HDF5
with `INVALID IPARAM (8)`, so this example is kept as a converter smoke and
candidate dossier rather than a locked physics benchmark.

The `0.9982139` target should not be used to judge the converter output unless a
matching OpenMC-sourced leakage/equivalence correction handoff is provided.

## Smoke

```sh
bash examples/uox_5x5_tg6/run_smoke.sh
```

The smoke:

1. reads the local APEX HDF5;
2. writes an `openmc2donjon` MGXS-contract HDF5 for the six subdomains;
3. runs the input-contract preflight;
4. converts to fresh `out.mcompo.txt` and `out.macrolib.txt`;
5. reads both LCM ASCII files back.

The output directory defaults to `/private/tmp/openmc2donjon_uox_5x5_tg6`.

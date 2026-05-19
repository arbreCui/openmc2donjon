# C5G7 NSSF ADF-Effect Smoke

This is a solver-side smoke test for the accepted real ADF payload. It is not
the production C5G7 7-group keff target.

## Why 2 Groups

The production 7-group assembly-wise C5G7 macrolib is stable in the regular
`NCR -> TRIVAT/TRIVAA -> FLUD` path, but the DONJON `NSSF/ANM` path aborts
during local nodal-relation construction:

- failing routine: `NSSLR2`
- failing condition: complex local ANM eigenmodes
- independent of ADF: the `NODF` run aborts at the same point
- affected assembly-wise mixtures: `ASM_Y01_X01`, `ASM_Y02_X02`

The original 7 material-domain C5G7 data has real ANM local eigenmodes. The
failure is therefore a limitation of this particular 7-group assembly-wise
homogenized data with the current `NSSF/ANM` implementation, not a converter
format failure and not an ADF payload failure.

To test the ADF-active solver path anyway, the production 7-group assembly-wise
MGXS was flux-weighted to 2 groups using the OpenMC assembly volume flux:

- source MGXS: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_assembly_p1_adf_production.h5`
- flux weights: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_boundary_currents_mu_full.h5`
- coarse groups: `[0:4]`, `[4:7]`
- derivative HDF5: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_smoke.h5`
- archive MCO: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_smoke.mco`
- runtime MCO mirror: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7p2.mco`

The runtime mirror uses a short filename because CLE-2000 sequential ASCII
file names are truncated in practice when the absolute path is too long.

The derivative HDF5 is explicitly tagged as
`condensation=flux_weighted_for_nssf_anm_smoke`.

## Diagnostics

The 2-group derivative preserves coarse row balance to roundoff:

- worst `|total - absorption - scatter_out|`: `2.22e-15`
- worst reconstructed local ANM eigenmode imaginary part: `0.0`

## DONJON Run

Deck:

```sh
cd /Users/wen/dragon-5.1/Donjon
./rdonjon -q openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_adf_effect.x2m
```

Result file:

`/Users/wen/dragon-5.1/Donjon/Darwin_arm64/c5g7pa_2g_nssf_adf_effect.result`

The `NCR` output reports `IDF=3`, so the macrolib carries ADF information.

## Result

| Case | Solver | k-effective |
| --- | --- | ---: |
| ADF active | `NSSF/ANM` | `1.18533289` |
| ADF disabled | `NSSF/ANM NODF` | `1.20179343` |

Difference:

- `k_ADF - k_NODF = -0.01646054`
- delta-k units: about `-1646 pcm`

This proves that DONJON's ADF-aware `NSSF` path consumes the converter-written
real ADF payload and changes the nodal solution. The production C5G7 benchmark
target remains the 7-group assembly-wise keff comparison in the stable
`TRIVAT/TRIVAA/FLUD` path.

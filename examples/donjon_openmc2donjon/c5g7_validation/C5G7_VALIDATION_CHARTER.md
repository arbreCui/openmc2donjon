# C5G7 Validation Charter

This folder now carries two intentionally separate validation tracks.

## Track A: Production 7-Group Keff

Purpose: validate the OpenMC-to-DONJON converter output as a production
assembly-wise C5G7 deterministic input.

- Input HDF5: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_assembly_p1_adf_production.h5`
- MULTICOMPO: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7pa.mco`
- Solver path: `NCR -> TRIVAT/TRIVAA -> FLUD`
- OpenMC reference: `k = 1.18798`
- DONJON diffusion: `k = 1.1896194220`, about `+164 pcm`
- DONJON SPN3: `k = 1.1912802458`, about `+330 pcm`
- Scope: stable keff benchmark and row-balance/ADF carry-through validation

Acceptance meaning:

The remaining few-hundred-pcm deterministic residual is tracked as method and
homogenization residual, not a converter-format failure. The 7-group production
path is locked unless the upstream OpenMC statistics, homogenization policy, or
DONJON transport/diffusion correction policy changes.

## Track B: Solver-Side ADF Consumption

Purpose: prove that DONJON can consume converter-written real ADF data inside
an ADF-aware solver route.

- Source HDF5: same production 7-group assembly-wise MGXS+ADF
- Derivative HDF5: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_smoke.h5`
- Archive MULTICOMPO: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_smoke.mco`
- Runtime MULTICOMPO mirror: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7p2.mco`
- Solver path: `NCR -> NSST -> NSSF/ANM`
- ADF active: `k = 1.18533289`
- ADF disabled with `NODF`: `k = 1.20179343`
- ADF effect: about `-1646 pcm`
- Scope: solver-side ADF activation smoke, not production 7-group physics

Acceptance meaning:

This track proves that `STATE-VECTOR(12)=3`, `ADF/HADF`, and face-wise `FD_*`
payloads are not merely carried through `NCR`; `NSSDRV` reads them and they
change the nodal solution. The 2-group derivative is explicitly tagged as an
`NSSF/ANM` smoke because the current DONJON 7-group assembly-wise ANM local
relation aborts in `NSSLR2` even with `NODF`.

## One-Command Summary

```sh
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /opt/homebrew/bin/python3.14 \
  /Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_validation/summarize_c5g7_validation.py
```

This command reports both Track A and Track B.

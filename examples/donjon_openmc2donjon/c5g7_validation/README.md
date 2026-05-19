# C5G7 Production Assembly-Wise Validation

This folder keeps the C5G7 validation decks that are meant to stay tidy and
reproducible.

Status: locked for the current assembly-wise production baseline. The remaining
keff differences are recorded as deterministic-equivalence residuals, not
converter-format failures.

The validation charter is in `C5G7_VALIDATION_CHARTER.md`. In short:

- Track A is the production 7-group keff line through `TRIVAT/TRIVAA/FLUD`.
- Track B is the 2-group `NSSF/ANM` smoke proving solver-side ADF consumption.

## Inputs

- Production MULTICOMPO: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7pa.mco`
- Production MGXS+ADF source: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_assembly_p1_adf_production.h5`
- OpenMC reference keff used here: `1.18798`

The production ADF definition is the accepted project definition:
OpenMC mu-binned surface flux divided by DONJON mixed-dual reconstructed
homogeneous face flux. The HDF5 records the explicit fill/clip policy for bins
where the raw denominator is not usable.

## Run

One-command acceptance rerun from `/Users/wen/dragon-5.1`:

```sh
bash Donjon/data/openmc2donjon/c5g7_validation/run_acceptance.sh
```

The script writes converter smoke outputs under
`/private/tmp/openmc2donjon_c5g7_acceptance`, reruns the locked DONJON decks,
and then calls `summarize_c5g7_validation.py`. Use `--skip-donjon` for a fast
converter/read-back plus summary check.

From `/Users/wen/dragon-5.1/Donjon`:

```sh
./rdonjon -q openmc2donjon/c5g7_validation/c5g7pa_diffusion_keff.x2m
./rdonjon -q openmc2donjon/c5g7_validation/c5g7pa_spn3_keff.x2m
./rdonjon -q openmc2donjon/c5g7_validation/c5g7pa_spn3_scat1_keff.x2m
./rdonjon -q openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_adf_effect.x2m
```

Then summarize from `/Users/wen/dragon-5.1`:

```sh
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /opt/homebrew/bin/python3.14 \
  Donjon/data/openmc2donjon/c5g7_validation/summarize_c5g7_validation.py
```

## Current Result

- `NCR` reads the production macrolib with `IDF=3`.
- ADF payload round-trip is numerically closed:
  max absolute difference from HDF5 source to NCR `L_MACROLIB` is about
  `6.5e-8`.
- MGXS row-balance audit is clean:
  `bad_group_entries=0`, `row_balance_bad_entries=0`,
  `max |total - absorption - scatter_out| = 2.7e-15`.
- DONJON diffusion keff: `1.1896194220`, about `+164 pcm` vs OpenMC `1.18798`.
- DONJON SPN3 keff: `1.1912802458`, about `+330 pcm` vs OpenMC `1.18798`.
- DONJON SPN3 with `SCAT 1`: `1.1912822723`, effectively identical to
  `SCAT 2`; the SPN3 offset is therefore not driven by the P1 scatter moment.

## NSSF Note

The 2D `NSSF` route is not the production C5G7 keff path right now. `NSSF`
only accepts 2D/3D in ANM mode, and the current 7-group assembly-wise C5G7
macrolib aborts in `NSSLR2` with complex local ANM eigenmodes during nodal
relation construction. The `NODF` run aborts at the same point, so this is not
caused by ADF values.

A separate 2-group flux-weighted derivative is kept as an ADF-active solver
smoke:

- generator: `condense_c5g7_2g_for_nssf.py`
- deck: `c5g7pa_2g_nssf_adf_effect.x2m`
- report: `NSSF_ADF_EFFECT_2G.md`
- result: ADF `k=1.18533289`, NODF `k=1.20179343`

So this validation separates the three responsibilities:

- stable DONJON keff: `NCR -> TRIVAT/TRIVAA -> FLUD`
- real ADF transport through DONJON data structures: `NCR -> L_MACROLIB -> EDI`
- real ADF consumption by DONJON nodal solver: 2-group `NSSF/ANM` smoke

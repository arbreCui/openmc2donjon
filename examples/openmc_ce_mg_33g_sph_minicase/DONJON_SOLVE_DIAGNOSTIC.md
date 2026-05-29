# DONJON Solve Diagnostic

This note explains the downstream DONJON solve diagnostic attached to the
OpenMC CE/MG SPH minicase.

It is deliberately a diagnostic, not a benchmark.  Its job is to prove that
the OpenMC-side SPH handoff can be consumed by DONJON in a real low-order solve
and to expose the resulting flux-shape comparison for review.

## Inputs

The diagnostic uses the high-statistics minicase run:

```text
/private/tmp/openmc2donjon_ce_mg_sph_production_candidate2
```

Required files:

```text
handoff/out_with_openmc_sph.macrolib.txt
handoff/openmc_ce_flux.h5
handoff/openmc_mg_flux.h5
```

Optional comparison file:

```text
handoff/out_uncorrected.macrolib.txt
```

When the uncorrected MACROLIB exists, the diagnostic runs the same DONJON
geometry and solver settings for both the uncorrected and SPH-corrected
handoffs.

The MACROLIB is the accepted SPH consumption route for this minicase because it
writes `GROUP/*/NSPH` directly.  DONJON reads those factors through `DSPH:` and
applies them through `MAC:`.

## Command

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_production_candidate2 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_donjon_solve_diagnostic.sh
```

By default the script writes:

```text
/private/tmp/openmc_ce_mg_33g_sph_donjon_solve_diagnostic/donjon_solve_summary.json
/private/tmp/openmc_ce_mg_33g_sph_donjon_solve_diagnostic/donjon_solve_summary.md
```

## What It Runs

The generated DONJON decks use a reflective `CAR2D` model inferred from the
MACROLIB mixture count.  For the original three-region case this reproduces the
hand-tuned slab:

```text
mixture 1: CS_FUEL
mixture 2: CS_MOD
mixture 3: CS_ABS
```

For larger variants, such as `five_region_2d`, the diagnostic builds a
volume-ratio-preserving one-dimensional `CAR2D` slab in mixture order.  That is
good enough to compare uncorrected and SPH-corrected DONJON responses with the
same low-order operator; it is still not a geometry benchmark.

Two low-order solves are run:

| Mode | DONJON path |
| --- | --- |
| diffusion | `TRIVAT` / `TRIVAA` / `FLUD` |
| SPN3 | `TRIVAT` / `TRIVAA` / `FLUD`, with `SPN 3 SCAT 2` |

The script exports the DONJON flux object and compares the first `N` flux
unknowns, where `N` is the number of OpenMC output mixtures, against the OpenMC
CE and OpenMC MG volume fluxes.  Because a low-order eigenvector has arbitrary
normalization, each flux shape is compared after removing a scalar
normalization factor.

## Current Result

The current high-statistics run gives:

| Mode | k-effective | CE shape mean residual | CE shape max residual |
| --- | ---: | ---: | ---: |
| diffusion | 0.8899511 | 0.0755294 | 0.761238 |
| SPN3 | 0.9084644 | 0.0515226 | 0.767714 |

Interpretation:

- DONJON successfully reads the exported MACROLIB, consumes `NSPH`, and runs a
  low-order solve.
- SPN3 gives a better mean flux-shape diagnostic than diffusion for this
  minicase.
- The maximum residual remains large because this tiny reflective three-region
  slab is a stress test for the handoff, not a tuned benchmark geometry.

## What This Proves

- The produced ASCII MACROLIB is a usable DONJON input.
- The OpenMC-side `NSPH` payload survives the converter and is consumed by
  DONJON.
- A real DONJON low-order operator can run from the corrected handoff.
- Flux-shape diagnostics can be exported and compared against OpenMC reference
  data.

## What This Does Not Prove

- It is not a C5G7-style k-effective benchmark.
- It does not validate a full-core diffusion/SPN model.
- It does not prove that the three-region slab is a good deterministic model.
- It does not replace the OpenMC CE/MG SPH reaction-rate diagnostic.

The diagnostic is best read as a downstream integration check.  The next
physics validation step is a larger colorset where the uncorrected and
SPH-corrected DONJON solves can be compared against the same OpenMC CE
reference.

# OpenMC CE/MG SPH Production Evidence

This note is the short, presentation-ready evidence package for the
OpenMC-side SPH minicase.  The bundled web fixture
`src/openmc2donjon/web/fixtures/openmc_sph_physics_summary.json` mirrors the
two-region production probe summarized below.

## Claim

The minicase demonstrates that openmc2donjon can carry an OpenMC-side SPH
handoff into DONJON ASCII:

```text
OpenMC CE reference
  + OpenMC MG macro solve on the same geometry and output regions
  -> OpenMC-side SPH(region, group)
  -> MGXS HDF5 augmented with SPH metadata
  -> L_MACROLIB ASCII with GROUP/*/NSPH for DONJON consumption
```

This is not a DONJON feedback loop.  DONJON is the downstream deterministic
consumer of the corrected handoff.

## Update Direction Fix (2026-07)

The SPH iteration update direction was fixed in July 2026: the update
formula previously multiplied by `mg_flux / ce_flux` while every apply path
divides cross sections by the factor, so the iterated loop was structurally
divergent and even a single "correction" moved the coarse model away from
the CE reference.  The fixed update is
`next_sph = previous_sph * (ce_flux / normalized_mg_flux) ** damping`,
whose fixed point makes the corrected OpenMC MG flux equal the CE
reference.  All evidence recorded before the fix (including the previous
one-shot production tables, the iterative "negative result", and the
damping-sweep conclusions) documented factors with the inverted sign and
has been invalidated; every number in this note comes from post-fix reruns
with `SPH_ITERATIONS=3`.

## Equivalence Target Choice

The workflow default is `--sph-target flux`: its fixed point drives the
corrected coarse-model flux to the CE reference, which is exactly what the
DONJON solve diagnostic in this example measures (flux-shape agreement
against the CE flux map), so the flux target is the appropriate showcase
default here.  It does not preserve reaction rates or k: in coupled
geometries the corrected model's k drifts with the size of the central
homogenization defect.  Coupled-geometry k-preservation needs
`--sph-target rate`, the classic Hebert/DRAGON rate-preserving update; see
`examples/irena30_sph_stage2_csd/README.md` for the measured flux-vs-rate
comparison on the IRENA colorsets.

## Minicase

The geometry is a small three-region colorset:

| Region | Output mixture |
| --- | --- |
| `CS_FUEL` | 1 |
| `CS_MOD` | 2 |
| `CS_ABS` | 3 |

The concrete run uses ECCO-33 groups, but the workflow is not limited to 33
groups.  The same group boundaries must be used consistently by the CE-tallied
MGXS handoff, the OpenMC MG macro solve, and the CE/MG flux exports.

Scatter treatment is intentionally split:

| Role | Treatment |
| --- | --- |
| Converter-facing handoff | P3 Legendre MGXS tallied from the CE run |
| OpenMC MG macro solve for SPH | H16 histogram angular representation |
| DONJON handoff | P3 MGXS plus scalar `SPH(region, group)` factors |

The H16 histogram data is not written to DONJON as scatter data.  It is used
inside OpenMC MG to obtain the macro flux used in the SPH update.

## Two-Region SPH Production Probe

The minimal Alain/Siggi-style colorset is now wired through the same route.
It has two output regions, so the OpenMC-side equivalence produces two
`SPH(region, group)` factors per energy group:

```sh
OPENMC2DONJON_COLORSET_VARIANT=two_region \
RUN_ROOT=/private/tmp/openmc2donjon_two_region_production_20260709 \
BATCHES=80 INACTIVE=10 PARTICLES=20000 \
MG_BATCHES=80 MG_INACTIVE=10 MG_PARTICLES=20000 \
MAX_CE_FLUX_REL_STD=0.06 \
MAX_MG_FLUX_REL_STD=0.06 \
SPH_ITERATIONS=3 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

This run reaches the same production-quality flux uncertainty threshold used
for the rest of the minicase evidence:

| Quantity | Result |
| --- | ---: |
| Summary decision | `openmc_ce_mg_sph_production_quality` |
| Mixtures | 2 (`CS_FUEL`, `CS_MOD`) |
| Energy groups | 33 |
| CE flux max relative std dev | 0.0396835 |
| MG flux max relative std dev | 0.0389937 |
| SPH minimum | 0.872018 |
| SPH maximum | 1.11109 |
| Max `abs(SPH - 1)` | 0.127982 |
| Clipped SPH bins | 0 |
| Current OpenMC MG reaction-rate residual | 0.146766 |
| Frozen-flux rate residual after the new SPH update | 0.214907 |
| MACROLIB `NSPH` block count | 33 |

The frozen-flux rate row no longer closes to zero: with the fixed
flux-target update the corrected coarse flux, not the frozen-flux reaction
rate, is driven to the CE reference (rate closure is the `--sph-target
rate` fixed point).

The same DONJON `DSPH:` / `MAC:` consume smoke now auto-selects a non-unity
target mixture, so it works for two-, three-, and five-region handoffs:

```text
DONJON DSPH consumed NSPH: target_mix=1 expected_g1=1.11109312 pn=1.11109316 sn=1.11109316
DONJON MAC applied SPH: pn_ntot0_ratio=1.11109318 sn_ntot0_ratio=1.00000003
```

## Production Run

Command used on the development machine:

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_production_fixed_20260709 \
BATCHES=80 INACTIVE=20 PARTICLES=20000 \
MG_BATCHES=100 MG_INACTIVE=20 MG_PARTICLES=30000 \
MAX_CE_FLUX_REL_STD=0.05 \
MAX_MG_FLUX_REL_STD=0.05 \
SPH_ITERATIONS=3 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

OpenMC executable used locally:

```text
/Users/wen/miniforge3/envs/openmc-dev/bin/openmc
```

The Python environment imported OpenMC from the local development environment
used by the project.  The workflow does not require a special OpenMC hex fork;
this minicase is a simple colorset slab.

## Results

| Quantity | Result |
| --- | ---: |
| Summary decision | `openmc_ce_mg_sph_production_quality` |
| CE flux max relative std dev | 0.0428184 |
| MG flux max relative std dev | 0.0269931 |
| Production flux uncertainty threshold | 0.05 |
| SPH minimum | 0.965754 |
| SPH maximum | 1.08736 |
| Max `abs(SPH - 1)` | 0.0873624 |
| Clipped SPH bins | 0 |
| Iteration-1 raw update range | 0.978399 .. 1.07354 |
| Iteration-2 raw update range | 0.972024 .. 1.02500 |
| Iteration-3 raw update range | 0.965686 .. 1.04599 |
| MACROLIB `NSPH` block count | 33 |
| DONJON consume smoke | passed |
| DONJON diffusion solve diagnostic (uncorrected -> corrected) | k = 0.8889332 -> 0.8942402 |
| DONJON SPN3 solve diagnostic (uncorrected -> corrected) | k = 0.9072928 -> 0.9124593 |
| OpenMC CE reference k | 0.9948 +/- 0.0008 |

Interpretation:

- The uncorrected OpenMC MG macro solve differs from the CE reference flux
  by up to about 7% (iteration-1 raw update range); after the first fixed
  update the remaining per-iteration updates sit at the Monte Carlo noise
  floor of the flux ratios (a few percent at these statistics).
- The SPH-corrected DONJON solves move k toward the OpenMC CE reference for
  both diffusion (+530 pcm) and SPN3 (+517 pcm); the low-order model defect
  of this tiny reflective slab still dominates the absolute k gap.
- The result is production-quality for this minicase because both CE and MG
  flux uncertainty gates are below 5%, the SPH factors are finite/positive, no
  clipping was needed, and the ASCII handoff carries `GROUP/*/NSPH`.

## Five-Region 2D Production Run

The larger five-region two-dimensional colorset has also reached the
production-quality flux uncertainty gate:

```sh
OPENMC2DONJON_COLORSET_VARIANT=five_region_2d \
RUN_ROOT=/private/tmp/openmc2donjon_five_region_2d_production_20260709 \
BATCHES=80 INACTIVE=20 PARTICLES=30000 \
MG_BATCHES=80 MG_INACTIVE=20 MG_PARTICLES=30000 \
MAX_CE_FLUX_REL_STD=0.05 \
MAX_MG_FLUX_REL_STD=0.05 \
SPH_ITERATIONS=3 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

| Quantity | Result |
| --- | ---: |
| Summary decision | `openmc_ce_mg_sph_production_quality` |
| CE flux max relative std dev | 0.0406169 |
| MG flux max relative std dev | 0.0447442 |
| Production flux uncertainty threshold | 0.05 |
| SPH minimum | 0.927331 |
| SPH maximum | 1.13000 |
| Max `abs(SPH - 1)` | 0.130003 |
| Clipped SPH bins | 0 |
| Iteration-1 raw update range | 0.974296 .. 1.08019 |
| Iteration-2 raw update range | 0.962990 .. 1.05918 |
| Iteration-3 raw update range | 0.919061 .. 1.02317 |
| OpenMC CE reference k | 1.3741 +/- 0.0005 |

A matching 2D DONJON diagnostic solved both the uncorrected handoff and the
SPH-corrected operator (cross sections divided by `NSPH`, the openmc2donjon
divisor convention):

```sh
RUN_ROOT=/private/tmp/openmc2donjon_five_region_2d_production_20260709 \
RUN_DIR=/private/tmp/openmc2donjon_five_region_2d_production_20260709_donjon_2d \
RUN_TAG=openmc_ce_mg_sph_five_region_production_2d \
bash examples/openmc_ce_mg_33g_sph_minicase/run_donjon_solve_diagnostic.sh
```

| Case | Mode | k-effective | CE shape mean residual | CE shape max residual | CE rate mean residual |
| --- | --- | ---: | ---: | ---: | ---: |
| uncorrected | diffusion | 1.295644 | 0.232018 | 0.908086 | 0.297742 |
| SPH-corrected | diffusion | 1.302132 | 0.230841 | 0.906976 | 0.287371 |
| uncorrected | SPN3 | 1.298612 | 0.225032 | 0.910189 | 0.429037 |
| SPH-corrected | SPN3 | 1.304875 | 0.224348 | 0.908928 | 0.419784 |

Interpretation:

- The five-region case is a stronger converter/SPH handoff check than the
  three-region slab because it uses repeated cells, five output regions, and a
  matching 2D DONJON colorset diagnostic.
- With the fixed update direction, the SPH-corrected DONJON solve moves every
  recorded diagnostic toward the OpenMC CE reference: k (+649 pcm diffusion,
  +626 pcm SPN3, against a CE reference of 1.3741), the CE flux-shape mean and
  max residuals, and the global-normalized CE reaction-rate residual.
- The residuals remain large because this small colorset is a stress test for
  the handoff.  This is production-quality handoff evidence, not a final
  deterministic benchmark.

## Iterative SPH Review

All three production runs above use `SPH_ITERATIONS=3` with undamped updates
(`SPH_DAMPING=1.0`).  With the fixed update direction the loop is a
contraction: the first iteration removes the systematic CE/MG defect (raw
updates up to about 7-13% from unity), and the second and third iterations
operate at the Monte Carlo noise floor of the CE/MG flux ratios (raw updates
within the few-percent statistical band, no runaway).  The pre-fix
three-iteration "negative result" recorded here previously — geometric
overshoot at damping 1.0 and damping-sensitivity at 0.5 — was measured with
the inverted update and is invalidated; that behavior was the structural
divergence of the old loop, not a property of OpenMC MG reruns.  A fresh
damping sweep with the fixed loop has not been recorded yet;
`summarize_damping_sweep.py` remains the tool for it.

## Produced Artifacts

The high-statistics run produced:

```text
handoff/mgxs_library.h5
handoff/openmc_ce_flux.h5
handoff/openmc_mg_flux.h5
handoff/openmc_sph.csv
handoff/openmc_sph_sidecar.h5
handoff/mgxs_with_openmc_sph.h5
handoff/out_with_openmc_sph.mcompo.txt
handoff/out_with_openmc_sph.macrolib.txt
handoff/physics_summary.json
handoff/physics_summary.md
```

For DONJON SPH consumption, use the MACROLIB handoff:

```text
handoff/out_with_openmc_sph.macrolib.txt
```

It writes SPH factors as `GROUP/*/NSPH`, matching the downstream DONJON
`DSPH:`/`MAC:` consumption route.  The MULTICOMPO file is still useful as a
mapped/archival library, but MACROLIB is the accepted route for this SPH
minicase.

The DONJON consume smoke was run on this MACROLIB and confirmed that `DSPH:`
reads the precomputed `NSPH` factors and that `MAC:` applies the PN correction:

```text
DONJON DSPH consumed NSPH: target_mix=2 expected_g1=1.08736236 pn=1.08736241 sn=1.08736241
DONJON MAC applied SPH: pn_ntot0_ratio=1.08736241 sn_ntot0_ratio=1.00000003
```

The listing was written to:

```text
/Users/wen/dragon-5.1/Donjon/Darwin_arm64/openmc_ce_mg_33g_sph_macrolib_donjon_smoke.result
```

Convention note: the smoke shows that DONJON's `DSPH:`/`MAC:` modules apply
`NSPH` multiplicatively to the PN data (`pn_ntot0_ratio` equals the NSPH
value).  The openmc2donjon `NSPH` payload is a divisor (`XS_corrected =
XS / NSPH`, the same convention used by `apply-sph` and the OpenMC MG rerun
loop), so the consume smoke is a data-plumbing check, and the solve
diagnostic below builds the corrected operator package-side with `apply-sph`
before handing it to DONJON.

A separate DONJON solve diagnostic was also run with the same handoff on a
3-region reflective `CAR2D` slab matching the colorset ordering.  It uses
`TRIVAT/TRIVAA/FLUD`, exports the DONJON flux object, and compares the first
three `KEYFLX` unknowns against the OpenMC CE and OpenMC MG volume fluxes after
removing arbitrary eigenvector normalization:

```text
DONJON solve diagnostic: uncorrected diffusion k=0.8889332 ce_shape_mean=0.0768475 ce_shape_max=0.762128 rr_mean=0.378818
DONJON solve diagnostic: uncorrected spn3 k=0.9072928 ce_shape_mean=0.0504169 ce_shape_max=0.768526 rr_mean=0.495103
DONJON solve diagnostic: sph_corrected diffusion k=0.8942402 ce_shape_mean=0.0760514 ce_shape_max=0.750895 rr_mean=0.357176
DONJON solve diagnostic: sph_corrected spn3 k=0.9124593 ce_shape_mean=0.05111 ce_shape_max=0.757663 rr_mean=0.476871
```

Against the OpenMC CE reference k of 0.9948 +/- 0.0008, the corrected
operator moves k, the CE flux-shape max residual, and the CE reaction-rate
residual toward the reference for both modes; the SPN3 shape mean is flat
within its small margin (0.0504 -> 0.0511).  This tiny slab remains a
stress test for the low-order model itself.

This diagnostic is deliberately reported as review evidence, not as a
k-effective benchmark or a hard acceptance gate.  The detailed interpretation
is in `DONJON_SOLVE_DIAGNOSTIC.md`.

## What This Proves

- OpenMC CE can provide converter-facing Pn MGXS and reference volume fluxes.
- OpenMC MG can provide the macro flux on the same geometry/output regions.
- openmc2donjon can build OpenMC-side SPH factors from those fluxes.
- openmc2donjon can augment the MGXS HDF5 and carry NSPH into ASCII LCM.
- DONJON can consume the exported MACROLIB `GROUP/*/NSPH` payload through
  `DSPH:`/`MAC:` in the checked smoke route.
- DONJON can run diffusion/SPN3 low-order solves with the exported MACROLIB;
  the resulting flux-shape residuals are recorded for review.
- The web demo fixture now reflects production-quality statistics, not only a
  smoke-test run.

## What This Does Not Prove

- It is not a full-core benchmark.
- It is not a DONJON k-effective validation.
- It is not a proof that one universal damping value is optimal.
- It does not require or validate PyGan; PyGan remains optional.

The next physics validation step is a larger, benchmark-like colorset or core
case where the uncorrected and SPH-corrected DONJON low-order results are both
compared against the OpenMC reference after consuming the generated MACROLIB.
`NEXT_PHYSICS_VALIDATION.md` defines the proposed target shape and acceptance
criteria.

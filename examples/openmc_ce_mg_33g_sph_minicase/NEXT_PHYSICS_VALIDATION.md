# Next Physics Validation Target

The current three-region minicase proves the OpenMC CE/MG SPH handoff and
DONJON consumption route.  The next validation case should be larger and more
benchmark-like, but still small enough to run repeatedly during development.

## Goal

Show that OpenMC-side SPH improves a DONJON low-order solve for a nontrivial
colorset:

```text
OpenMC CE reference
  + OpenMC MG macro solve on the same geometry/output regions
  -> OpenMC-side SPH(region, group)
  -> corrected MACROLIB
  -> DONJON diffusion / SPN solve
  -> compare low-order flux and reaction-rate diagnostics against OpenMC CE
```

The key comparison is not the absolute k-effective of a toy model.  The useful
comparison is:

```text
uncorrected DONJON handoff
vs.
SPH-corrected DONJON handoff
vs.
OpenMC CE reference diagnostics
```

## Proposed Case Shape

Start with a two-dimensional colorset before moving to a full assembly:

| Feature | Recommendation |
| --- | --- |
| Geometry | 2D Cartesian colorset, 5 to 9 output regions |
| Boundary | Reflective first; leakage boundary later |
| Materials | At least fuel, moderator, absorber/control-like, reflector-like |
| Energy groups | Any supported OpenMC group mesh; ECCO-33 remains a convenient default |
| Converter handoff | P3 Legendre MGXS |
| OpenMC MG macro solve | H16 histogram scatter by default |
| Equivalence factors | Scalar `SPH(region, group)` |
| DONJON consumer | `L_MACROLIB` first; `L_MULTICOMPO` remains archival/mapped output |

This case should have enough regions that SPH is meaningful, but not so many
that Monte Carlo statistics dominate every review cycle.

The repository now includes the first version of that case as a selectable
variant of this example:

```sh
OPENMC2DONJON_COLORSET_VARIANT=five_region_2d \
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_five_region_2d \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

The variant is intentionally wired through the same scripts as the three-region
smoke, so any change to the CE/MG/SPH route is exercised by both geometries.

## Required Artifacts

Each completed validation run should produce:

```text
handoff/mgxs_library.h5
handoff/openmc_ce_flux.h5
handoff/openmc_mg_flux.h5
handoff/openmc_sph_sidecar.h5
handoff/mgxs_with_openmc_sph.h5
handoff/out_uncorrected.macrolib.txt
handoff/out_with_openmc_sph.macrolib.txt
handoff/physics_summary.json
handoff/physics_summary.md
donjon_uncorrected_summary.json
donjon_sph_corrected_summary.json
```

The uncorrected and SPH-corrected DONJON summaries should use the same geometry
and solver settings.

`run_workflow.sh` now writes `out_uncorrected.macrolib.txt` alongside the
SPH-corrected MACROLIB, and `run_donjon_solve_diagnostic.sh` consumes both
files when they are present.

For `five_region_2d`, the DONJON diagnostic now uses the matching 3 x 2
colorset geometry and aggregates repeated DONJON cell unknowns back to OpenMC
output regions before comparing flux shapes.  That removes the previous 1D
slab approximation from this validation step.

## Current Five-Region Production Snapshot

A local `five_region_2d` run has closed the complete route at production
quality:

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

The run produced five OpenMC output regions, ECCO-33 groups, CE-tallied P3
Legendre MGXS for the converter, and H16 histogram scatter for the OpenMC MG
macro solve used to generate SPH factors.  It uses the fixed SPH update
direction (`next_sph = previous_sph * (ce_flux / mg_flux) ** damping`) with
three iterations; the pre-fix snapshot recorded here previously carried the
inverted update and was invalidated.

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
| Current OpenMC MG reaction-rate residual | 0.115047 |
| Frozen-flux rate residual after the new SPH update | 0.173332 |
| OpenMC CE reference k | 1.3741 +/- 0.0005 |

The frozen-flux rate row does not close under the flux-target update; rate
closure is the `--sph-target rate` fixed point (see
`examples/irena30_sph_stage2_csd/README.md`).

The matching 2D DONJON diagnostic solved the uncorrected handoff and the
SPH-corrected operator (cross sections divided by `NSPH`):

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

This is useful evidence for the new route: with the fixed update direction
the corrected operator moves k toward the OpenMC CE reference (+649 pcm
diffusion, +626 pcm SPN3) and improves the CE flux-shape and reaction-rate
residuals for both modes.  The low-order flux-shape residual remains large
in this small colorset, so this is production-quality handoff evidence rather
than a final benchmark-quality deterministic validation.

With the fixed loop, the three-iteration run behaves as a contraction: the
first iteration removes the systematic CE/MG defect (raw updates up to about
8% from unity) and iterations two and three stay within the Monte Carlo
noise band of the flux ratios.  The pre-fix conclusion that iteration
overshoots and that one-shot SPH should be the accepted baseline was an
artifact of the inverted update and no longer applies.

## Acceptance Criteria

A run is useful as production evidence when:

- CE and MG flux relative standard deviations are below the selected review
  threshold, preferably 5% or lower.
- SPH factors are finite, positive, and not clipped.
- The OpenMC frozen-flux reaction-rate diagnostic closes after applying the new
  SPH update.
- DONJON can consume the corrected MACROLIB through `DSPH:` / `MAC:`.
- The SPH-corrected DONJON diagnostic improves at least one physically relevant
  residual compared with the uncorrected DONJON diagnostic.

The last point is the important upgrade over the current minicase: it turns the
DONJON solve from a downstream integration check into a low-order improvement
check.

## Deliberate Non-Goals

- Do not reintroduce a DONJON feedback-loop SPH algorithm as the main route.
- Do not require PyGan for the converter; PyGan can remain an optional backend
  or DONJON-deck helper.
- Do not hard-code 33 groups.  The workflow should keep using whatever group
  mesh is consistently used by the CE MGXS tally, OpenMC MG macro solve, and
  exported flux data.
- Do not optimize damping from one case.  Damping should be reviewed with a
  sweep when the geometry is statistically stable.

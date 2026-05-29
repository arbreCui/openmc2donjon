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

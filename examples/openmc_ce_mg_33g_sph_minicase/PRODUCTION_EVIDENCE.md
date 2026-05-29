# OpenMC CE/MG SPH Production Evidence

This note is the short, presentation-ready evidence package for the
OpenMC-side SPH minicase.  It summarizes the high-statistics run whose
machine-readable summary is mirrored in the web fixture
`src/openmc2donjon/web/fixtures/openmc_sph_physics_summary.json`.

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

## Production Run

Command used on the development machine:

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_production_candidate2 \
BATCHES=80 INACTIVE=20 PARTICLES=20000 \
MG_BATCHES=100 MG_INACTIVE=20 MG_PARTICLES=30000 \
MAX_CE_FLUX_REL_STD=0.05 \
MAX_MG_FLUX_REL_STD=0.05 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

OpenMC executable used locally:

```text
/Users/wen/openmc-workspace/src-v0.15.3/build/bin/openmc
```

The Python environment imported OpenMC from the local development environment
used by the project.  The workflow does not require a special OpenMC hex fork;
this minicase is a simple colorset slab.

## Results

| Quantity | Result |
| --- | ---: |
| Summary decision | `openmc_ce_mg_sph_production_quality` |
| CE flux max relative std dev | 0.041976 |
| MG flux max relative std dev | 0.032363 |
| Production flux uncertainty threshold | 0.05 |
| SPH minimum | 0.963441 |
| SPH maximum | 1.059468 |
| Max `abs(SPH - 1)` | 0.059468 |
| Clipped SPH bins | 0 |
| Current OpenMC MG reaction-rate residual | 0.059468 |
| Frozen-flux residual after applying the new SPH update | 4.65e-12 |
| MACROLIB `NSPH` block count | 33 |
| DONJON consume smoke | passed |

Interpretation:

- The pre-SPH OpenMC MG macro solve differs from the CE reference by about 6%
  in the worst reaction-rate bin.
- The generated SPH update removes that difference in the frozen-flux
  diagnostic because the factors are computed from the same CE/MG flux ratio.
- The result is production-quality for this minicase because both CE and MG
  flux uncertainty gates are below 5%, the SPH factors are finite/positive, no
  clipping was needed, and the ASCII handoff carries `GROUP/*/NSPH`.

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
DONJON DSPH consumed NSPH: expected_mix3_g1=1.05946788 pn=1.05946791 sn=1.05946791
DONJON MAC applied SPH: pn_ntot0_ratio=1.05946786 sn_ntot0_ratio=0.999999982
```

The listing was written to:

```text
/Users/wen/dragon-5.1/Donjon/Darwin_arm64/openmc_ce_mg_33g_sph_macrolib_donjon_smoke.result
```

## What This Proves

- OpenMC CE can provide converter-facing Pn MGXS and reference volume fluxes.
- OpenMC MG can provide the macro flux on the same geometry/output regions.
- openmc2donjon can build OpenMC-side SPH factors from those fluxes.
- openmc2donjon can augment the MGXS HDF5 and carry NSPH into ASCII LCM.
- DONJON can consume the exported MACROLIB `GROUP/*/NSPH` payload through
  `DSPH:`/`MAC:` in the checked smoke route.
- The web demo fixture now reflects production-quality statistics, not only a
  smoke-test run.

## What This Does Not Prove

- It is not a full-core benchmark.
- It is not a DONJON k-effective validation.
- It is not a proof that one universal damping value is optimal.
- It does not require or validate PyGan; PyGan remains optional.

The next physics validation step is a larger, benchmark-like colorset or core
case where the DONJON low-order result is compared against the OpenMC reference
after consuming the generated MACROLIB.

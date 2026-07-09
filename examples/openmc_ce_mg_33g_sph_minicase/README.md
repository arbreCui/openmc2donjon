# OpenMC CE/MG SPH Colorset Minicase

This example is the new physics route for SPH equivalence:

```text
OpenMC continuous-energy reference
  + OpenMC multi-group macro calculation
    using the selected energy mesh and the same geometry/output regions
  -> OpenMC-side SPH factors
  -> corrected MGXS HDF5 / SPH sidecar
  -> openmc2donjon L_MACROLIB ASCII for DONJON SPH consumption
```

It deliberately does **not** use a DONJON feedback loop.  DONJON is only the
downstream consumer of the corrected handoff.

## Geometry

The default model is a tiny three-region slab colorset with reflective outer
boundaries:

```text
CS_FUEL  -> DONJON mixture 1 / SPH region 1
CS_MOD   -> DONJON mixture 2 / SPH region 2
CS_ABS   -> DONJON mixture 3 / SPH region 3
```

This remains the default because it runs quickly and is useful as a
development smoke.  A minimal two-region colorset is also available for the
Alain/Siggi case where two output regions require two `SPH(region, group)`
factors per energy group:

```sh
OPENMC2DONJON_COLORSET_VARIANT=two_region \
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_two_region \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

```text
CS_FUEL -> fuel-like output region
CS_MOD  -> moderator-like output region
```

A larger five-region two-dimensional variant is available for the next physics
validation step:

```sh
OPENMC2DONJON_COLORSET_VARIANT=five_region_2d \
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_five_region_2d \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

The five-region variant uses the same CE/MG/SPH route, but exports five
OpenMC cell domains instead of three:

```text
CS_FUEL_L -> fuel-like output region
CS_MOD    -> moderator-like output region
CS_FUEL_U -> second fuel-like output region
CS_ABS    -> absorber/control-like output region
CS_REF    -> reflector-like output region
```

Use `two_region` to demonstrate the minimum multi-region SPH semantics.  Use
the three-region variant for fast interface checks.  Use `five_region_2d` when
reviewing whether the OpenMC-side SPH route improves a larger low-order
colorset diagnostic.

This concrete minicase uses the ECCO-33 energy mesh, but the workflow is not
limited to 33 groups: any valid OpenMC MG group structure can be used as long
as the CE-tallied MGXS handoff, OpenMC MG macro solve, CE flux export, and MG
flux export all share the same group boundaries and output-region ordering.

The converter-facing handoff uses Legendre order 3 so DONJON receives ordinary
P1/P2/P3 scatter moments.  The OpenMC MG macro calculation used to derive SPH
factors uses histogram angular representation by default (`H16`):

```text
CE statepoint tallies:
  P3 Legendre scatter -> converter MGXS HDF5
  H16 histogram scatter -> OpenMC MG macro solve
```

The H16 data is not written to DONJON as scatter data.  It is only used inside
OpenMC's MG run to obtain a higher-fidelity MG flux.  The final DONJON handoff
is:

```text
CE-tallied P3 MGXS + OpenMC-side SPH(region, group)
```

The SPH factors produced by this example are still scalar factors per region
and energy group:

```text
SPH(region, group)
```

## Run

Set `PYTHON_BIN` to the Python environment that can import both OpenMC and
openmc2donjon.  Set `OPENMC_EXEC` if `openmc` is not on `PATH`.

```sh
PYTHON_BIN=/Users/wen/miniforge3/envs/openmc-dev/bin/python \
OPENMC_EXEC=/Users/wen/openmc-workspace/src-v0.15.3/build/bin/openmc \
OPENMC_LIB_DIR=/Users/wen/openmc-workspace/src-v0.15.3/build/lib \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

Optional knobs:

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_33g_sph_minicase
PARTICLES=1000 BATCHES=20 INACTIVE=5
MG_PARTICLES=1000 MG_BATCHES=20 MG_INACTIVE=5
MG_MACRO_SCATTER_FORMAT=histogram
MG_MACRO_HISTOGRAM_BINS=16
SPH_ITERATIONS=1
SPH_DAMPING=1.0
SPH_CLIP_MIN=
SPH_CLIP_MAX=
MAX_CE_FLUX_REL_STD=0.20
MAX_MG_FLUX_REL_STD=0.20
OPENMC_LIB_DIR=/path/to/openmc/build/lib
OPENMC2DONJON_COLORSET_VARIANT=three_region   # or two_region / five_region_2d
```

`OPENMC_LIB_DIR` is optional, but useful on macOS when the OpenMC executable
would otherwise pick up a stale `libopenmc.dylib` from another Python or conda
environment.

`SPH_DAMPING` controls the multiplicative SPH update (fixed direction: the
converged flux-target factor is the CE/MG flux ratio, so a low-order flux
that is too high produces a factor below unity and the corrected cross
sections increase):

```text
next_sph = previous_sph * (ce_flux / normalized_mg_flux) ** SPH_DAMPING
```

The default `1.0` is the undamped update.  For noisy or low-flux colorset
bins, use a smaller value such as `0.5` and optionally set `SPH_CLIP_MIN` /
`SPH_CLIP_MAX` to keep exploratory runs from being dominated by a single
statistically weak group.

The default particle counts are intentionally small so the workflow can be
tested quickly.  They are not production statistics.  If any MG region
has zero sampled flux, the flux export/SPH gate should fail; increase
`PARTICLES`/`BATCHES` rather than accepting a zero-flux SPH ratio.

## Output

The run directory contains:

```text
ce_case/                         continuous-energy OpenMC XML + statepoint
mg_case/                         OpenMC MG XML + mgxs.h5 + statepoint
handoff/mgxs_library.h5          converter-facing MGXS handoff from CE run
handoff/openmc_ce_flux.h5        CE reference flux, shape (region, group)
handoff/openmc_mg_flux.h5        OpenMC MG macro flux, same shape/order
handoff/openmc_mg_flux_iterNN.h5 per-iteration MG flux if SPH_ITERATIONS > 1
handoff/mg_macro_summary.json    OpenMC MG macro scatter treatment (Hn/Pn)
handoff/openmc_sph.csv           auditable SPH table
handoff/openmc_sph_sidecar.h5    HDF5 SPH sidecar
handoff/openmc_sph_sidecar_iterNN.h5  per-iteration SPH factors if SPH_ITERATIONS > 1
handoff/mgxs_with_openmc_sph.h5  MGXS handoff after SPH augmentation
handoff/out_with_openmc_sph.mcompo.txt  mapped XS handoff / archival route
handoff/out_uncorrected.macrolib.txt  uncorrected DONJON MACROLIB baseline
handoff/out_with_openmc_sph.macrolib.txt accepted DONJON SPH consumption route
handoff/physics_summary.json     machine-readable CE/MG/SPH audit summary
handoff/physics_summary.md       human-readable CE/MG/SPH audit summary
```

The SPH command gates both CE and MG flux uncertainty:

```sh
--require-reference-flux-std-dev
--max-reference-flux-std-dev-rel ...
--require-mg-flux-std-dev
--max-mg-flux-std-dev-rel ...
```

That keeps noisy OpenMC flux ratios from being silently promoted into
production SPH factors.

The physics summary records the CE/MG flux uncertainty, SPH factor range by
mixture, and a reaction-rate preservation diagnostic.  The diagnostic compares
`CE-tallied MGXS * CE volume flux` against the OpenMC MG rate before/after the
new SPH update using the openmc2donjon `XS / NSPH` divisor convention (the
same application used by `apply-sph`; DONJON's native `MAC:` module applies
`NSPH` multiplicatively, see `PRODUCTION_EVIDENCE.md`).  With the default
flux-target update the after-update rate rows do not close to zero; rate
closure is the `--sph-target rate` fixed point.  It is
meant for review and demos; it is not a substitute for a benchmark-quality
validation.

The summary also separates structural success from statistical quality:

- `openmc_ce_mg_sph_production_quality` means the HDF5/ASCII SPH handoff is
  complete and both CE/MG flux relative standard deviations are at or below
  5%.
- `openmc_ce_mg_sph_demonstration_quality` means the route is suitable for a
  quick demo, but flux statistics are above the production threshold.
- `openmc_ce_mg_sph_statistical_review_required` means the route closed, but
  the flux ratios are too noisy to present as production SPH evidence.

For example, an 8-batch / 2000-particle smoke on the development machine
closed the full route and wrote P3 handoff data plus H16 MG-macro evidence, but
the summary correctly marked it `statistical_review_required` because the
largest CE/MG flux relative standard deviation was about 0.65.

A 24-batch / 4000-particle run with 6 inactive batches on both CE and MG
sides reached `openmc_ce_mg_sph_demonstration_quality` on the development
machine:

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_demo_quality_20260709 \
BATCHES=24 INACTIVE=6 PARTICLES=4000 \
MG_BATCHES=24 MG_INACTIVE=6 MG_PARTICLES=4000 \
MAX_CE_FLUX_REL_STD=0.30 \
MAX_MG_FLUX_REL_STD=0.30 \
SPH_ITERATIONS=3 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

That run gave CE/MG flux relative standard deviations of 0.231 / 0.184 and an
SPH range of 0.640 .. 1.326 (at these statistics the iterated factors are
dominated by the flux-ratio noise, not by a systematic defect).  It is
suitable as a live demonstration of the OpenMC-side SPH route, but it remains
above the 5% production-quality threshold.

A local production-quality run reached the 5% CE/MG flux uncertainty target
with higher MG statistics (all recorded production evidence uses the fixed
update direction and `SPH_ITERATIONS=3`; the pre-fix records were
invalidated):

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_production_fixed_20260709 \
BATCHES=80 INACTIVE=20 PARTICLES=20000 \
MG_BATCHES=100 MG_INACTIVE=20 MG_PARTICLES=30000 \
MAX_CE_FLUX_REL_STD=0.05 \
MAX_MG_FLUX_REL_STD=0.05 \
SPH_ITERATIONS=3 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh
```

That run gave CE/MG flux relative standard deviations of 0.04282 / 0.02699
and an SPH range of 0.96575 .. 1.08736 with no clipped bins.  The summary
decision was `openmc_ce_mg_sph_production_quality`.  The flux-target update
does not close the frozen-flux reaction-rate diagnostic (that closure is the
`--sph-target rate` fixed point); the recorded rate residuals are reviewed in
`PRODUCTION_EVIDENCE.md`.

The larger `five_region_2d` variant has also closed the complete route at
production quality:

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

That five-region run gave CE/MG flux relative standard deviations of
0.04062 / 0.04474, an SPH range of 0.92733 .. 1.13000, and no clipped SPH
bins.  The summary decision was `openmc_ce_mg_sph_production_quality`.  A
matching 2D DONJON diagnostic solved the uncorrected handoff and the
SPH-corrected operator and moved k, the CE flux-shape residuals, and the CE
reaction-rate residual toward the OpenMC CE reference for both diffusion and
SPN3.  The detailed table is in `NEXT_PHYSICS_VALIDATION.md`.

With the fixed update direction, `SPH_ITERATIONS=3` is the evidence default
for this example: the first iteration removes the systematic CE/MG defect
and later iterations sit at the Monte Carlo noise floor of the flux ratios.
The previously recorded conclusion that iterating OpenMC MG overshoots and
that one-shot SPH is the accepted path was measured with the inverted
pre-fix update and no longer applies.

To close the downstream handoff, run the DONJON consumption smoke on the
produced MACROLIB:

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_production_fixed_20260709 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_donjon_consume_smoke.sh
```

This is not a k-effective benchmark.  It verifies that DONJON can read the
exported `L_MACROLIB` ASCII, consume `GROUP/*/NSPH` through `DSPH:`, and apply
the PN correction through `MAC:`.  The smoke also checks the SN convention used
by DONJON: `DSPH:` consumes the same `NSPH` values, while `MAC:` leaves
`NTOT0` unchanged for the SN path in this convention.

For a slightly stronger downstream diagnostic, run a DONJON low-order solve
with the same MACROLIB:

```sh
RUN_ROOT=/private/tmp/openmc2donjon_ce_mg_sph_production_fixed_20260709 \
bash examples/openmc_ce_mg_33g_sph_minicase/run_donjon_solve_diagnostic.sh
```

This writes `donjon_solve_summary.json` and `donjon_solve_summary.md` under
`RUN_DIR` (default:
`/private/tmp/openmc_ce_mg_33g_sph_donjon_solve_diagnostic`).  It runs both a
diffusion and an SPN3 `TRIVAT/TRIVAA/FLUD` solve, exports the DONJON flux
object, and compares the DONJON flux unknowns against the OpenMC CE and OpenMC
MG volume fluxes after removing arbitrary eigenvector normalization.  For the
`five_region_2d` variant, the script uses a matching 3 x 2 `CAR2D` colorset and
area-weights the repeated left-fuel cells back to the single OpenMC output
region before comparison.  If
`handoff/out_uncorrected.macrolib.txt` is present, the script runs the same
geometry and solver settings for both the uncorrected and SPH-corrected
cases.  The SPH-corrected operator is prepared package-side with `apply-sph`
(`XS_corrected = XS / NSPH`); DONJON's native `DSPH:`/`MAC:` application is
multiplicative and is exercised by the consume smoke instead.  This is still
a diagnostic, not a benchmark acceptance
gate: the residual is reported for review rather than forced to pass a tight
threshold.

For the exact interpretation of the diffusion/SPN3 diagnostic, see
`DONJON_SOLVE_DIAGNOSTIC.md`.  For the proposed larger validation target, see
`NEXT_PHYSICS_VALIDATION.md`.

For a shorter presentation-ready summary of that high-statistics run, see
`PRODUCTION_EVIDENCE.md`.

## Damping sweep review

To compare several completed damping runs, use `summarize_damping_sweep.py`.
It reads existing `physics_summary.json` files and does not rerun OpenMC:

```sh
python examples/openmc_ce_mg_33g_sph_minicase/summarize_damping_sweep.py \
  --case damping_1p0=/path/to/run_damping_1p0 \
  --case damping_0p7=/path/to/run_damping_0p7 \
  --case damping_0p5=/path/to/run_damping_0p5 \
  --output-json /tmp/openmc_sph_damping_sweep.json \
  --output-md /tmp/openmc_sph_damping_sweep.md
```

The sweep table compares the current-solve reaction-rate residual, the
after-update frozen-flux residual, SPH range, update range, and flux
statistical uncertainty.  Use it to justify a damping recommendation instead
of selecting `SPH_DAMPING` from the SPH factor range alone.

A pre-fix 60-batch / 10000-particle sweep recorded here previously was
measured with the inverted update direction and its damping recommendations
are invalidated: it was characterizing the divergence rate of a structurally
unstable loop.  With the fixed update the undamped loop is already a
contraction, and damping mainly trades convergence speed against the Monte
Carlo noise accumulated by extra iterations.  A fresh sweep with the fixed
loop has not been recorded yet; use `summarize_damping_sweep.py` when one is
needed.

## Manual Steps

The shell script expands to these core commands:

```sh
python examples/openmc_ce_mg_33g_sph_minicase/build_ce_case.py \
  --case-dir ce_case \
  --mg-macro-scatter-format histogram \
  --mg-macro-histogram-bins 16
(cd ce_case && openmc)

OPENMC2DONJON_COLORSET_DIR=ce_case \
openmc2donjon-from-openmc \
  --recipe examples/openmc_ce_mg_33g_sph_minicase/export_recipe.py \
  --statepoint ce_case/statepoint.20.h5 \
  --keep-hdf5 handoff/mgxs_library.h5 \
  --output handoff/out.mcompo.txt \
  --format multicompo \
  --check

python examples/openmc_ce_mg_33g_sph_minicase/prepare_mg_case.py \
  --ce-case-dir ce_case \
  --ce-statepoint ce_case/statepoint.20.h5 \
  --mg-case-dir mg_case \
  --scatter-format histogram \
  --histogram-bins 16 \
  --summary-json handoff/mg_macro_summary.json
(cd mg_case && openmc)

openmc2donjon export-volume-flux ce_case/statepoint.20.h5 \
  --mgxs handoff/mgxs_library.h5 \
  --tally-name openmc_ce_mg_sph_volume_flux \
  --dataset-name openmc_volume_flux \
  -o handoff/openmc_ce_flux.h5

openmc2donjon export-volume-flux mg_case/statepoint.20.h5 \
  --mgxs handoff/mgxs_library.h5 \
  --tally-name openmc_ce_mg_sph_volume_flux \
  --dataset-name openmc_mg_flux \
  -o handoff/openmc_mg_flux.h5

openmc2donjon make-openmc-sph-sidecar handoff/mgxs_library.h5 \
  -o handoff/openmc_sph_sidecar.h5 \
  --reference-flux handoff/openmc_ce_flux.h5::openmc_volume_flux \
  --mg-flux handoff/openmc_mg_flux.h5::openmc_mg_flux \
  --table-output handoff/openmc_sph.csv \
  --flux-normalization auto

# Optional next OpenMC MG iteration: apply the current SPH factors to an
# OpenMC-native mgxs.h5 copy, rerun OpenMC MG with that corrected XS, export
# the new MG flux, and rebuild the sidecar.
openmc2donjon apply-sph mg_case/mgxs_unapplied.h5 \
  --input-format openmc-mgxs \
  --sph-source handoff/openmc_sph_sidecar.h5 \
  -o mg_case/mgxs.h5

# The bundled run_workflow.sh performs that native-MGXS application
# automatically when SPH_ITERATIONS is greater than 1.

# Final DONJON handoff path: attach the final sidecar and convert.
openmc2donjon augment-sph handoff/mgxs_library.h5 \
  --sph-source handoff/openmc_sph_sidecar.h5 \
  -o handoff/mgxs_with_openmc_sph.h5

openmc2donjon handoff/mgxs_with_openmc_sph.h5 \
  -o handoff/out_with_openmc_sph.mcompo.txt \
  --check \
  --require-sph

openmc2donjon handoff/mgxs_with_openmc_sph.h5 \
  --format macrolib \
  -o handoff/out_with_openmc_sph.macrolib.txt \
  --check \
  --require-sph

openmc2donjon handoff/mgxs_library.h5 \
  --format macrolib \
  -o handoff/out_uncorrected.macrolib.txt \
  --check

python examples/openmc_ce_mg_33g_sph_minicase/summarize_outputs.py \
  --handoff-dir handoff
```

## What This Proves

- CE and MG calculations share geometry, output regions, and energy groups.
- The OpenMC MG macro solve can use Hn histogram scatter while the DONJON
  handoff remains Pn/Legendre.
- SPH factors are generated on the OpenMC side from CE/MG flux comparison.
- The converter carries those factors as `NSPH` into DONJON ASCII.
- The accepted DONJON downstream route is `L_MACROLIB`, where `NSPH` is written
  as `GROUP/*/NSPH` and can be consumed by DONJON `DSPH:`/`MAC:`.
- DONJON-side SPH iteration is not part of this route.

## What It Does Not Prove

- This is not a benchmark-quality k-effective validation.
- The default statistics are too low for production SPH.
- `L_MULTICOMPO + NCR:` currently extracts the macroscopic XS but does not
  promote OpenMC-side `NSPH` into non-unity `GROUP/*/NSPH`; use `L_MACROLIB`
  for the SPH consumption smoke.
- Angular-bin-dependent SPH factors, such as `SPH(region, group, H-bin)`, are
  not implemented here; only scalar region-by-group SPH is generated.

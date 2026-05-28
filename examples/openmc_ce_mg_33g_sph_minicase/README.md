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

The model is a tiny three-region slab colorset with reflective outer
boundaries:

```text
CS_FUEL  -> DONJON mixture 1 / SPH region 1
CS_MOD   -> DONJON mixture 2 / SPH region 2
CS_ABS   -> DONJON mixture 3 / SPH region 3
```

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
MAX_CE_FLUX_REL_STD=0.20
MAX_MG_FLUX_REL_STD=0.20
OPENMC_LIB_DIR=/path/to/openmc/build/lib
```

`OPENMC_LIB_DIR` is optional, but useful on macOS when the OpenMC executable
would otherwise pick up a stale `libopenmc.dylib` from another Python or conda
environment.

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
handoff/mg_macro_summary.json    OpenMC MG macro scatter treatment (Hn/Pn)
handoff/openmc_sph.csv           auditable SPH table
handoff/openmc_sph_sidecar.h5    HDF5 SPH sidecar
handoff/mgxs_with_openmc_sph.h5  MGXS handoff after SPH augmentation
handoff/out_with_openmc_sph.mcompo.txt  mapped XS handoff / archival route
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

The physics summary records the CE/MG flux uncertainty and SPH factor range by
mixture.  It is meant for review and demos; it is not a substitute for a
benchmark-quality validation.

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

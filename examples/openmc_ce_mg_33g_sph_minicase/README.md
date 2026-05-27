# OpenMC CE/MG 33g SPH Colorset Minicase

This example is the new physics route for SPH equivalence:

```text
OpenMC continuous-energy reference
  + OpenMC multi-group 33g macro calculation
  using the same geometry and output regions
  -> OpenMC-side SPH factors
  -> corrected MGXS HDF5 / SPH sidecar
  -> openmc2donjon L_MULTICOMPO or L_MACROLIB ASCII
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

The energy mesh is ECCO-33.  The OpenMC MGXS library uses Legendre order 3 so
the route is ready for P1/P2/P3 scatter moments.  The SPH factors produced by
this example are still scalar factors per region and energy group:

```text
SPH(region, group)
```

Angular/Hn-dependent SPH is a later extension.

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
MAX_CE_FLUX_REL_STD=0.20
MAX_MG_FLUX_REL_STD=0.20
OPENMC_LIB_DIR=/path/to/openmc/build/lib
```

`OPENMC_LIB_DIR` is optional, but useful on macOS when the OpenMC executable
would otherwise pick up a stale `libopenmc.dylib` from another Python or conda
environment.

The default particle counts are intentionally small so the workflow can be
tested quickly.  They are not production statistics.  If any 33-group region
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
handoff/openmc_sph.csv           auditable SPH table
handoff/openmc_sph_sidecar.h5    HDF5 SPH sidecar
handoff/mgxs_with_openmc_sph.h5  MGXS handoff after SPH augmentation
handoff/out_with_openmc_sph.mcompo.txt
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
mixture, and confirms that the final ASCII handoff contains `NSPH` equivalence
factors.  It is meant for review and demos; it is not a substitute for a
benchmark-quality validation.

## Manual Steps

The shell script expands to these core commands:

```sh
python examples/openmc_ce_mg_33g_sph_minicase/build_ce_case.py --case-dir ce_case
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
  --mg-case-dir mg_case
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

python examples/openmc_ce_mg_33g_sph_minicase/summarize_outputs.py \
  --handoff-dir handoff
```

## What This Proves

- CE and MG calculations share geometry, output regions, and energy groups.
- SPH factors are generated on the OpenMC side from CE/MG flux comparison.
- The converter carries those factors as `NSPH` into DONJON ASCII.
- DONJON-side SPH iteration is not part of this route.

## What It Does Not Prove

- This is not a benchmark-quality k-effective validation.
- The default statistics are too low for production SPH.
- Hn/angular SPH factors are not implemented here; only scalar
  region-by-group SPH is generated.

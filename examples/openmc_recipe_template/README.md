# OpenMC Recipe Template

This directory is a starting point for a real OpenMC MGXS statepoint export.
Copy it into an OpenMC case directory, edit `export_recipe.py`, then run
`openmc2donjon-from-openmc`.

## Copy And Edit

```sh
cp -R examples/openmc_recipe_template /path/to/my_case/openmc2donjon_recipe
cd /path/to/my_case/openmc2donjon_recipe
```

Edit these values in `export_recipe.py`:

| Setting | Meaning |
| --- | --- |
| `MATERIALS_XML` / `GEOMETRY_XML` / `SETTINGS_XML` / `TALLIES_XML` | OpenMC model and transport input files whose content hashes identify the fine calculation. |
| `EXTRA_MODEL_SOURCES` | Imported Python, CAD/mesh, or other files needed to reconstruct the model. |
| `RUN_THREADS` / `RUN_MPI_RANKS` | Optional launcher topology copied from the actual OpenMC run receipt; never inferred from the export shell. |
| `input_closure_complete` | Keep `True` only after `provenance_files()` lists every imported Python, CAD/DAGMC, mesh, external-source, weight-window, and other model-defining file. Otherwise set it `False`; replay will remain honestly incomplete. |
| `ENERGY_BOUNDS_EV` | Ascending energy boundaries in eV. |
| `DOMAIN_TYPE` | OpenMC MGXS domain type, usually `cell` or `material`. |
| `DOMAIN_ID_WHITELIST` | Optional subset of OpenMC domain ids to export. |
| `DOMAIN_MODE` | Metadata label such as `assembly`, `cell`, or `pin`. |
| `DOMAIN_VOLUME_BY_ID_CM3` / `DEFAULT_DOMAIN_VOLUME_CM3` | Explicit homogenized domain volumes used by strict production checks and DONJON mixture volumes. |
| `LEGENDRE_ORDER` | Highest scattering Legendre order to tally/export. |
| `MGXS_TYPES` | Required MGXS set for DONJON output. |

`MGXS_TYPES` should include ordinary OpenMC `"scatter matrix"` for DONJON
scattering. The exporter does not silently substitute `"nu-scatter matrix"` or
`"consistent nu-scatter matrix"`; those require an explicit
`--scatter-mgxs-type` override or a recipe `scatter_mgxs_type()` hook.

The key mapping is:

```text
one exported OpenMC MGXS domain or subdomain -> one DONJON mixture
```

For assembly-wise production use, make each exported OpenMC domain represent one
assembly or one assembly subdomain before tallying MGXS.

## Prepare OpenMC Tallies

Check the local environment and recipe import path:

```sh
openmc2donjon doctor --recipe export_recipe.py
```

Dry-run the recipe before generating tallies:

```sh
openmc2donjon-export --recipe export_recipe.py --no-load-statepoint --dry-run
openmc2donjon-export --recipe export_recipe.py --no-load-statepoint --dry-run --strict-dry-run
```

Check that the reported mixture count and names match the intended spatial
homogenization map. Use `--strict-dry-run` as the production gate once the
recipe declares ordinary `"scatter matrix"`, P1, transport, stable domain
mapping, `domain_mode`, and explicit volumes.

Dry-run the full one-step conversion plan before writing artifacts:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --dry-run \
  --run-dir runs/case1 \
  --check \
  --strict-dry-run
```

Use the same recipe to add MGXS tallies before running OpenMC:

```sh
openmc2donjon-export --recipe export_recipe.py --write-tallies tallies.xml
```

Then run OpenMC normally to produce a statepoint containing those MGXS tallies.

## Export And Convert

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --run-dir runs/case1 \
  --check
```

The managed run directory contains `mgxs_library.h5`, `out.mcompo.txt`,
`run_summary.json`, `openmc_provenance.json`, optional `check_summary.json`,
the recipe and small declared model sources, and `manifest.json`. The
statepoint and nuclear-data libraries are content-hash bound but are not copied
by default because they may be very large. Native DRAGON SPH consumes the
frozen MGXS reference; it does not rerun OpenMC. The embedded handoff digest
also binds the final energy grid, mixtures, XS, fluxes, and correction datasets,
so modifying the HDF5 after export is detected.

For direct root `L_MACROLIB` output:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --format macrolib \
  -o out.macrolib.txt \
  --summary-json run_summary.json
```

## Check The HDF5 Handoff

```sh
openmc2donjon inspect mgxs_library.h5
openmc2donjon check mgxs_library.h5
openmc2donjon check mgxs_library.h5 --scatter-row-balance-warn 1e-3 --scatter-row-balance-fail 1e-2
```

If you keep an accepted handoff, compare regenerated output with:

```sh
openmc2donjon diff accepted_mgxs.h5 mgxs_library.h5
```

Keep `mgxs_library.h5`, `out.mcompo.txt`, and `run_summary.json` together when
sharing a conversion run.

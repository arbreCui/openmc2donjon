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
| `MATERIALS_XML` / `GEOMETRY_XML` | OpenMC model files. |
| `ENERGY_BOUNDS_EV` | Ascending energy boundaries in eV. |
| `DOMAIN_TYPE` | OpenMC MGXS domain type, usually `cell` or `material`. |
| `DOMAIN_ID_WHITELIST` | Optional subset of OpenMC domain ids to export. |
| `DOMAIN_MODE` | Metadata label such as `assembly`, `cell`, or `pin`. |
| `LEGENDRE_ORDER` | Highest scattering Legendre order to tally/export. |
| `MGXS_TYPES` | Required MGXS set for DONJON output. |

The key mapping is:

```text
one exported OpenMC MGXS domain or subdomain -> one DONJON mixture
```

For assembly-wise production use, make each exported OpenMC domain represent one
assembly or one assembly subdomain before tallying MGXS.

## Prepare OpenMC Tallies

Dry-run the recipe before generating tallies:

```sh
openmc2donjon-export --recipe export_recipe.py --no-load-statepoint --dry-run
```

Check that the reported mixture count and names match the intended spatial
homogenization map.

Dry-run the full one-step conversion plan before writing artifacts:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --dry-run \
  --keep-hdf5 mgxs_library.h5 \
  -o out.mcompo.txt \
  --check
```

Use the same recipe to add MGXS tallies before running OpenMC:

```sh
PYTHONPATH=/path/to/openmc2donjon/src:. python - <<'PY'
import openmc

from export_recipe import build_library

library = build_library()
tallies = openmc.Tallies()
if hasattr(library, "add_to_tallies"):
    library.add_to_tallies(tallies)
else:
    library.add_to_tallies_file(tallies)
tallies.export_to_xml()
PY
```

Then run OpenMC normally to produce a statepoint containing those MGXS tallies.

## Export And Convert

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --keep-hdf5 mgxs_library.h5 \
  -o out.mcompo.txt \
  --summary-json run_summary.json \
  --check
```

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
openmc2donjon check mgxs_library.h5
```

Keep `mgxs_library.h5`, `out.mcompo.txt`, and `run_summary.json` together when
sharing a conversion run.

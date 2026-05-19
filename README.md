# openmc2donjon

Convert OpenMC MGXS HDF5 data into DRAGON/DONJON LCM ASCII.

The package writes:

- `L_MULTICOMPO` for homogenized assembly-wise or domain-wise data.
- root `L_MACROLIB` for direct DONJON consumption in large one-state cases.

Data flow:

```text
OpenMC MGXS domains
  -> HDF5 input contract
  -> openmc2donjon
  -> L_MULTICOMPO or L_MACROLIB
  -> DONJON mixture map
```

Current validation status:

- C5G7 assembly-wise is the accepted validation line.
- Hex-domain support exists as converter/modeling capability.
- Experimental `BURN`-axis multi-state serialization exists, but is not part of
  the accepted physics validation yet.
- A suitable accepted hex benchmark is still future work.

## For Reviewers

Start here:

- [HDF5 input contract](docs/HDF5_INPUT_CONTRACT.md)
- [Handoff note](docs/HANDOFF_NOTE.md)
- [Validation summary](docs/VALIDATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

Fast smoke:

```sh
bash scripts/run_c5g7_demo.sh
```

Release/handoff check:

```sh
bash scripts/release_check.sh
```

Full local acceptance with DONJON decks:

```sh
bash scripts/release_check.sh --run-donjon
```

## Spatial Domain Mapping

The production mapping is spatial, not material-collapsed:

- one OpenMC MGXS domain produces one homogenized cross-section set;
- one homogenized cross-section set is written as one DONJON mixture;
- the DONJON geometry places that mixture back at the same spatial position.

For assembly-wise work, this means each assembly or component position has its
own OpenMC-derived cross sections. Two components with the same material type
are still kept as separate mixtures if they occupy different positions, because
their spectra, leakage, and neighbor effects can differ.

For 3D work, the same rule applies to the chosen spatial partition. For example,
`assembly position + axial layer` becomes one OpenMC MGXS domain and therefore
one DONJON mixture. If an assembly is split into ten axial layers, it produces
ten cross-section sets.

## Install

From a source checkout:

```sh
python -m pip install -e .
```

Run without installing:

```sh
PYTHONPATH=src python -m openmc2donjon.cli mgxs_library.h5 -o out.mcompo.txt
```

After installation:

```sh
openmc2donjon mgxs_library.h5 -o out.mcompo.txt
openmc2donjon --format macrolib mgxs_library.h5 -o out.macrolib.txt
```

## OpenMC MGXS Export

If you already have an OpenMC `mgxs.Library` object in Python, export the
converter-facing HDF5 directly:

```python
from openmc2donjon import DomainExportSpec, export_openmc_mgxs_library

export_openmc_mgxs_library(library, "mgxs_library.h5")
```

The exporter keeps the spatial domain map intact: each OpenMC MGXS domain is
written as one `/mixtures/<domain_name>` group. Stable names can be supplied
with domain objects, ids, or names:

```python
export_openmc_mgxs_library(
    library,
    "mgxs_library.h5",
    domain_names={101: "ASM_Y01_X01"},
)
```

For OpenMC mesh or cell subdomains, pass explicit specs. Each spec becomes one
HDF5 mixture and therefore one DONJON mixture:

```python
export_openmc_mgxs_library(
    library,
    "mgxs_library.h5",
    domain_specs=[
        DomainExportSpec(
            domain=mesh,
            name="ASM_Y01_X01",
            xs_kwargs={"subdomains": [(1, 1, 1)]},
            volume=assembly_volume,
        ),
    ],
)
```

For a pickled library object, the helper CLI is:

```sh
openmc2donjon-export library.pkl -o mgxs_library.h5
```

## C5G7 Demo

Run the portable converter-side C5G7 demo from the repository snapshot:

```sh
bash scripts/run_c5g7_demo.sh
```

This runs package tests, converts the accepted C5G7 HDF5 to fresh
`L_MULTICOMPO` and `L_MACROLIB` outputs under `/private/tmp`, and reads both
outputs back through the LCM ASCII parser.

To include the DONJON consumer smoke, run from a machine with a DRAGON/DONJON
checkout and set the DONJON root:

```sh
OPENMC2DONJON_ROOT=/path/to/dragon-5.1 \
OPENMC2DONJON_DATA_DIR=/path/to/dragon-5.1/Donjon/data/openmc2donjon \
  bash scripts/run_c5g7_demo.sh --run-donjon
```

To regenerate a C5G7 HDF5 handoff from an existing OpenMC statepoint through
the package exporter:

```sh
PYTHONPATH=src python scripts/export_c5g7_statepoint.py \
  --statepoint /Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5 \
  --adf-source examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5 \
  -o /private/tmp/openmc2donjon_c5g7_exporter_assembly_p1.h5
```

## Validation Workspace

This repository includes a DONJON-side handoff snapshot under
`examples/donjon_openmc2donjon/`. The snapshot is intentionally scoped to the
accepted C5G7 line and the current project status documents.

Useful entry points:

- `examples/donjon_openmc2donjon/PROJECT_STATUS.md`
- `examples/donjon_openmc2donjon/ACCEPTED_BASELINE.md`
- `examples/donjon_openmc2donjon/run_acceptance.sh`
- `examples/donjon_openmc2donjon/run_handoff_smoke.sh`

The HDF5 handoff schema is documented in
`docs/HDF5_INPUT_CONTRACT.md`.

## Current Scope

- One state point by default.
- Experimental `BURN`-axis multi-state HDF5 input can be serialized to
  `L_MULTICOMPO`, but the accepted validation line remains one-state C5G7.
- One DONJON mixture per OpenMC MGXS domain, preserving the spatial domain map.
- OpenMC group order is preserved; `ENERGY` is written as reversed energy
  bounds for DRAGON/DONJON.
- Scattering is written as DRAGON `NJJS/IJJS/SCAT` triplets with contiguous
  incoming-group spans and descending incoming-group order.
- Multiple Legendre moments are supported.
- `STRD` is read from `transport_total` when available, or derived from P1
  scattering when possible.
- Optional `OVERV`, `H-FACTOR`, ADF/HADF, single-mixture filtering, and
  single-point `BURN` helper metadata are supported.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=src \
  python -m pytest -q -o cache_dir=/private/tmp/openmc2donjon_pytest_cache tests
```

## Repository Layout

- `src/openmc2donjon/` - converter package.
- `tests/` - unit tests for LCM ASCII, scatter, MULTICOMPO, MACROLIB, and CLI.
- `scripts/` - local validation and C5G7 helper scripts.
- `examples/donjon_openmc2donjon/` - DONJON-side C5G7 handoff snapshot.

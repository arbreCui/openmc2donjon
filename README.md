# openmc2donjon

Convert OpenMC MGXS HDF5 data into DRAGON/DONJON LCM ASCII.

The package writes:

- `L_MULTICOMPO` for homogenized assembly-wise or domain-wise data.
- root `L_MACROLIB` for direct DONJON consumption in large one-state cases.

Current validation status:

- C5G7 assembly-wise is the accepted validation line.
- Hex-domain support exists as converter/modeling capability.
- A suitable accepted hex benchmark is still future work.

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

## Validation Workspace

This repository includes a DONJON-side handoff snapshot under
`examples/donjon_openmc2donjon/`. The snapshot is intentionally scoped to the
accepted C5G7 line and the current project status documents.

Useful entry points:

- `examples/donjon_openmc2donjon/PROJECT_STATUS.md`
- `examples/donjon_openmc2donjon/ACCEPTED_BASELINE.md`
- `examples/donjon_openmc2donjon/run_acceptance.sh`
- `examples/donjon_openmc2donjon/run_handoff_smoke.sh`

## Current Scope

- One calculation per mixture by default.
- One DONJON mixture per OpenMC MGXS domain.
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

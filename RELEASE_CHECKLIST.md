# openmc2donjon Release Checklist

This checklist covers the current `0.1.0` internal handoff state.

## Package Scope

- [x] `L_MULTICOMPO` ASCII writer for one-state OpenMC MGXS libraries.
- [x] Root `L_MACROLIB` ASCII writer for direct DONJON solves.
- [x] Duck-typed OpenMC `mgxs.Library` exporter for the documented HDF5 input
  contract, including explicit mesh/cell subdomain export specs.
- [x] DRAGON/DONJON scatter triplet conversion with contiguous descending
  incoming-group spans.
- [x] Multiple Legendre moments from `[moment, G_in, G_out]` or OpenMC-style
  `[G_in, G_out, moment]` input.
- [x] Transport correction fields through `transport_total` or P1-derived
  `STRD`.
- [x] Optional `H-FACTOR`, `OVERV`, ADF/HADF, single-mixture filtering, and
  single-point `BURN` axis helpers.

## Required Smoke Commands

Run unit tests:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=src \
  python -m pytest -q -o cache_dir=/private/tmp/openmc2donjon_pytest_cache tests
```

Run CLI help and version:

```sh
PYTHONPATH=src python -m openmc2donjon.cli --help
PYTHONPATH=src python -m openmc2donjon.cli --version
PYTHONPATH=src python -m openmc2donjon.export_cli --help
PYTHONPATH=src python -m openmc2donjon.export_cli --version
```

Run the portable C5G7 demo:

```sh
bash scripts/run_c5g7_demo.sh
```

Optionally regenerate the C5G7 HDF5 handoff from a saved OpenMC statepoint:

```sh
PYTHONPATH=src python scripts/export_c5g7_statepoint.py \
  --statepoint /Users/wen/openmc-workspace/c5g7_converter_test/runs/assembly_p1/statepoint.120.h5 \
  --adf-source examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5 \
  -o /private/tmp/openmc2donjon_c5g7_exporter_assembly_p1.h5
```

Run the DONJON-side C5G7 acceptance from a full local DRAGON/DONJON checkout:

```sh
bash examples/donjon_openmc2donjon/run_acceptance.sh
```

## Validation Records

- [x] C5G7 accepted validation:
  `examples/donjon_openmc2donjon/c5g7_validation/C5G7_VALIDATION_CHARTER.md`
- [x] Reviewer validation summary:
  `docs/VALIDATION.md`
- [x] Architecture summary:
  `docs/ARCHITECTURE.md`
- [x] Roadmap:
  `docs/ROADMAP.md`
- [x] Accepted artifact manifest:
  `examples/donjon_openmc2donjon/ACCEPTED_ARTIFACTS.md`
- [x] Accepted baseline manifest:
  `examples/donjon_openmc2donjon/accepted_baseline_manifest.json`
- [x] HDF5 input contract:
  `docs/HDF5_INPUT_CONTRACT.md`

## Known Limits

- [ ] Multiple state points are not implemented.
- [ ] Hex support is implemented as capability work, but no accepted hex
  benchmark is included yet.
- [ ] Full-core production use should keep validating against the local
  DONJON-side handoff workspace before promotion.

## Release Decision

The package is ready for internal handoff when the package tests pass and the
C5G7 DONJON-side acceptance remains green.

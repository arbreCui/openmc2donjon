# openmc2donjon

[![CI](https://github.com/arbreCui/openmc2donjon/actions/workflows/ci.yml/badge.svg)](https://github.com/arbreCui/openmc2donjon/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Build production handoffs from OpenMC multi-group cross sections to
DRAGON/DONJON deterministic workflows.

The project bridges a high-fidelity OpenMC reference and a low-order
DRAGON/DONJON solve at the assembly / domain level:

```text
OpenMC (high-fidelity reference, full geometry)
  -> assembly- / domain-wise homogenization (MGXS HDF5 handoff)
  -> equivalence stage
  -> L_MULTICOMPO or L_MACROLIB ASCII
  -> DONJON low-order solve (diffusion / SPN)
```

## Equivalence Methods

All three methods are implemented and exercised by the production smokes.

| Method | What it does | Entry point |
| --- | --- | --- |
| Direct | No equivalence factors; accept the homogenization bias. | Convert without equivalence flags. |
| One-shot equivalence | Inject ADF/DF and/or SPH factors from a sidecar before conversion. Examples include flux-ratio ADF built from OpenMC surface flux plus a low-order driver, or an SPH table from a previous run. | `make-adf-sidecar` + `augment-adf`, `make-sph-sidecar` + `augment-sph`, or `openmc2donjon-from-openmc --build-flux-ratio-adf` / `--sph-source` / `--sph-macrolib`. |
| Iterative SPH | Fix the OpenMC reference, then iterate: DONJON solve -> extract low-order flux -> recompute SPH -> reconvert, until convergence. | `openmc2donjon run-sph-loop --config loop.json` |

## Export And Convert Modes

Both invocation styles ship:

- two-step: `openmc2donjon-export` writes `mgxs_library.h5`, then
  `openmc2donjon` converts it to ASCII. This is useful when the HDF5 is shared,
  archived, or post-processed between stages.
- one-step: `openmc2donjon-from-openmc` exports, checks, converts, and bundles
  a managed run directory in a single command.

Either invocation style composes with any of the equivalence methods above.

## Output Formats

- `L_MULTICOMPO` as `.mcompo.txt` for mapped domain-wise libraries.
- `L_MACROLIB` as `.macrolib.txt` for direct one-state macrolib handoffs.

Accepted validation: C5G7 assembly-wise OpenMC -> DONJON handoff with
documented k-effective comparisons; see [Validation Status](#validation-status).

## Quick Start

Install from a source checkout:

```sh
python -m pip install -e .
```

Check an MGXS handoff before conversion:

```sh
openmc2donjon check mgxs_library.h5 --production
```

Convert to MULTICOMPO:

```sh
openmc2donjon mgxs_library.h5 -o out.mcompo.txt --check
```

Convert to MACROLIB:

```sh
openmc2donjon mgxs_library.h5 --format macrolib -o out.macrolib.txt --check
```

Run a tiny recipe/export smoke without OpenMC data:

```sh
bash scripts/run_recipe_export_smoke.sh
```

For the full walkthrough, see [docs/QUICKSTART.md](docs/QUICKSTART.md).

## OpenMC Entry Points

Most real cases should use a small Python recipe that builds the case-specific
OpenMC `mgxs.Library` and assigns stable spatial domain names.

Export only the converter-facing HDF5:

```sh
openmc2donjon-export \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  -o mgxs_library.h5
```

Export and convert in one managed run directory:

```sh
openmc2donjon-from-openmc \
  --recipe export_recipe.py \
  --statepoint statepoint.120.h5 \
  --run-dir runs/case1 \
  --check
```

Inspect a recipe before writing files:

```sh
openmc2donjon-export --recipe export_recipe.py --no-load-statepoint --dry-run
openmc2donjon-from-openmc --recipe export_recipe.py --dry-run --run-dir runs/case1 --check
```

Useful references:

- [OpenMC export workflow](docs/OPENMC_EXPORT_WORKFLOW.md)
- [HDF5 input contract](docs/HDF5_INPUT_CONTRACT.md)
- [Recipe template](examples/openmc_recipe_template/)
- [Production minicase](examples/production_minicase/)
- [Full-core minicase](examples/openmc_full_core_minicase/)
- [Hex minicase](examples/openmc_hex_minicase/)

## Spatial Domain Rule

The converter preserves the OpenMC spatial partition:

- one OpenMC MGXS domain becomes one HDF5 mixture;
- one HDF5 mixture becomes one DONJON mixture;
- the DONJON geometry places that mixture back at the matching spatial position.

This is intentionally not material-collapsed. Two domains with the same
material may still receive different homogenized cross sections because their
spectra, leakage, and neighbor effects differ.

For a 3D assembly-wise workflow, a typical domain might be
`assembly position + axial layer`. If a core has 193 assemblies and 20 axial
layers, the handoff contains 3860 spatial mixtures.

## Production Checks

`openmc2donjon check --production` enables the project production baseline:

- explicit positive volumes;
- explicit `transport_total`;
- group-wise H-FACTOR/kappa-fission for fissionable calculations;
- stable declared mixture order and source-domain provenance;
- energy-bound consistency and known mesh audit metadata;
- scatter row-balance, chi normalization, ADF face consistency, and
  transport/P1 consistency gates;
- statistical-uncertainty visibility when `*_std_dev` datasets are present.

Details:

- [Production preset](docs/PRODUCTION_PRESET.md)
- [Production thresholds](docs/PRODUCTION_THRESHOLDS.md)
- [HDF5 input contract](docs/HDF5_INPUT_CONTRACT.md)

## SPH And ADF/DF

The package can carry equivalence data into DONJON handoffs:

- ADF/HADF discontinuity factors, including flux-ratio ADF sidecars.
- SPH/NSPH factors for workflows where the downstream method prefers SPH.

The converter records these factors and provenance in the HDF5/MACROLIB/MULTICOMPO
handoff; it does not invent physics corrections on its own. Case-specific ADF
or SPH factors should come from the chosen OpenMC/low-order/DONJON workflow.

Entry points:

```sh
openmc2donjon make-adf-sidecar mgxs_library.h5 -o adf_sidecar.h5 --mode unity
openmc2donjon augment-adf mgxs_library.h5 --adf-source adf_sidecar.h5 -o mgxs_with_adf.h5

openmc2donjon make-sph-sidecar mgxs_library.h5 -o sph_sidecar.h5 --value 1.0
openmc2donjon augment-sph mgxs_library.h5 --sph-source sph_sidecar.h5 -o mgxs_with_sph.h5
openmc2donjon run-sph-loop --config loop.json
```

Docs and examples:

- [External face-flux contract](docs/EXTERNAL_FACE_FLUX_CONTRACT.md)
- [DONJON SPH loop adapter](examples/donjon_sph_loop_adapter/)
- [External low-order handoff](examples/external_low_order_handoff/)

## Validation Status

Current accepted validation line:

- C5G7 assembly-wise OpenMC-to-DONJON handoff with DONJON k-effective checks.
- Converter round trips for `L_MULTICOMPO` and `L_MACROLIB`.
- Production smokes for recipe export, full-core domain mapping, hex geometry
  capability, ADF carry-through, and SPH handoff mechanics.

Run portable checks:

```sh
bash scripts/run_recipe_export_smoke.sh
bash scripts/run_c5g7_demo.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests
```

Run the full local release gate, including optional DONJON-dependent smokes
when the local DRAGON/DONJON checkout is available:

```sh
bash scripts/release_check.sh
bash scripts/release_check.sh --run-donjon
```

More detail:

- [Validation summary](docs/VALIDATION.md)
- [Current handoff snapshot](docs/HANDOFF_SNAPSHOT.md)
- [Release notes](RELEASE_NOTES.md)
- [C5G7 DONJON snapshot](examples/donjon_openmc2donjon/)

## Output Contract

The CLI keeps stdout as a result stream and stderr as diagnostics:

- reports, generated paths, and "wrote/exported/injected" confirmations use
  stdout;
- diagnostic errors, warnings, progress, and debug detail use the package
  logger on stderr;
- `-v`, `-vv`, `-q`, and `--log-level` control diagnostic verbosity.

This is enforced by `tests/test_print_audit.py` so accidental status
`print()` calls do not leak into business logic.

## Development

Install developer tools:

```sh
python -m pip install -e ".[dev]"
```

Run the local gates:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests
ruff check .
mypy --no-incremental \
  src/openmc2donjon/constants.py \
  src/openmc2donjon/scatter.py \
  src/openmc2donjon/energy_groups.py \
  src/openmc2donjon/mgxs_physics_checks.py
```

CI runs the same unit-test matrix on Python 3.10, 3.11, and 3.12, plus Ruff
and the whitelisted strict mypy gate.

## Roadmap

Near-term work:

- localhost web UI for preflight, conversion, report viewing, and energy-mesh
  inspection;
- tighter integration with the existing nucdata energy-group resources;
- broader mypy coverage for small pure helper modules;
- optional citation/DOI metadata for research workflows.

Larger physics work remains separate from the format converter core:

- uncertainty propagation from OpenMC tally `std_dev` data;
- richer standard energy-mesh ID checks;
- additional production examples and benchmark comparisons.

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Repository Layout

- `src/openmc2donjon/` - Python package and CLI implementation.
- `docs/` - workflow, contract, production, and validation notes.
- `examples/` - small runnable handoff examples and DONJON adapters.
- `scripts/` - local smoke, validation, and release-check helpers.
- `tests/` - unit tests and contract/audit gates.

## License

MIT. See [LICENSE](LICENSE).

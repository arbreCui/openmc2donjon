# openmc2donjon

[![CI](https://github.com/arbreCui/openmc2donjon/actions/workflows/ci.yml/badge.svg)](https://github.com/arbreCui/openmc2donjon/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Build production handoffs from OpenMC multi-group cross sections and
OpenMC-side equivalence factors to DRAGON/DONJON deterministic workflows.

The production route keeps the physics equivalence on the OpenMC side, then
uses this package as the delivery bridge into DRAGON/DONJON:

```text
OpenMC CE reference
  + OpenMC MG using the selected group structure and the same geometry
    (typically with Hn angular histogram scattering)
  -> OpenMC-side SPH factors and/or ADF/DF sidecars
  -> corrected MGXS HDF5 handoff
  -> openmc2donjon converter
  -> DONJON L_MULTICOMPO or L_MACROLIB consumption
```

For OpenMC-side SPH consumed by DONJON `DSPH:`/`MAC:`, use the
`L_MACROLIB` route: the converter writes SPH as `GROUP/*/NSPH`, which DONJON
reads directly. `L_MULTICOMPO` remains the mapped-library route for
domain-wise handoffs extracted through `NCR:`.

In the OpenMC CE/MG SPH route, the CE run can tally two scattering
representations at once:

```text
OpenMC CE run
  P3 Legendre MGXS   -> converter-facing HDF5 -> DONJON scatter blocks
  H16 histogram MGXS -> OpenMC MG macro solve on the selected mesh -> MG-H16 flux

OpenMC CE flux vs OpenMC MG-H16 flux -> SPH(region, group)
```

Thus Hn is used to improve the OpenMC MG macro calculation that generates SPH
factors. It is not converted to DONJON scatter; DONJON receives the directly
tallied Pn/Legendre MGXS plus explicit SPH factors.

## Equivalence Methods

The converter does not compute the physics correction itself. It carries
explicit factors produced upstream, with OpenMC CE/MG equivalence as the
production SPH route.

| Method | What it does | Entry point |
| --- | --- | --- |
| Direct | No equivalence factors; accept the homogenization bias. | Convert without equivalence flags. |
| OpenMC-side SPH / ADF | Generate SPH factors from OpenMC CE reference vs an OpenMC MG macro calculation on the selected group structure with the same geometry, usually using OpenMC Hn histogram angular representation for the MG macro solve; or build ADF/DF sidecars from OpenMC face-flux evidence. | `make-openmc-sph-sidecar` + `augment-sph`, `make-adf-sidecar` + `augment-adf`, or `openmc2donjon-from-openmc --sph-source` / `--build-flux-ratio-adf`. |

## Export And Convert Modes

Both invocation styles ship:

- two-step: `openmc2donjon-export` writes `mgxs_library.h5`, then
  `openmc2donjon` converts it to ASCII. This is useful when the HDF5 is shared,
  archived, or post-processed between stages.
- one-step: `openmc2donjon-from-openmc` exports, checks, converts, and bundles
  a managed run directory in a single command.

Either invocation style composes with direct conversion or explicit OpenMC-side
equivalence factors.

## Output Formats

- `L_MULTICOMPO` as `.mcompo.txt` for mapped domain-wise libraries.
- `L_MACROLIB` as `.macrolib.txt` for direct one-state macrolib handoffs.

If the handoff carries OpenMC-side SPH factors and the next DONJON step should
consume them, prefer `.macrolib.txt`.

Accepted validation: C5G7 assembly-wise OpenMC -> DONJON handoff with
documented k-effective comparisons; see [Validation Status](#validation-status).

## PyGan Integration

The default converter backend is the pure Python ASCII LCM writer shipped in
this package. PyGan is treated as an optional DRAGON/DONJON integration layer
for validation, inspection, and an alternate writer backend.

Recommended PyGan demonstration path:

1. Check whether the optional backend is available:

```sh
openmc2donjon pygan-doctor
```

2. Write the same converter LCM tree through PyGan instead of the built-in
   ASCII writer:

```sh
openmc2donjon mgxs_library.h5 \
  --writer-backend pygan \
  --format multicompo \
  -o out.mcompo.txt
```

3. Compare the default writer and PyGan writer semantically:

```sh
openmc2donjon compare-writers mgxs_library.h5 \
  --format multicompo \
  --summary-json writer_compare.json
```

4. Run the optional local PyGan backend smoke:

```sh
bash scripts/run_pygan_backend_smoke.sh
```

The smoke skips cleanly when PyGan is not installed. When PyGan is available,
it compares both `L_MULTICOMPO` and `L_MACROLIB` writer outputs against the
default ASCII backend using the bundled C5G7 production fixture. If DONJON is
also available locally, the same smoke runs a read-only CLE-2000 ingest deck so
DONJON itself reads the PyGan-exported ASCII files, runs `NCR:` on the PyGan
`L_MULTICOMPO`, and checks the extracted macrolib against the PyGan direct
`L_MACROLIB`.

5. Inspect the root structure of a native DRAGON/DONJON COMPO through PyGan:

```sh
openmc2donjon pygan-inspect-compo FUEL30.COMPO --summary-json fuel30.pygan.json
```

If PyGan is not installed, conversion still works through the default ASCII
writer. Installing PyGan is useful when you want Python-side access to native
DRAGON/DONJON LCM objects, want PyGan to export the ASCII file, or want to run
CLE-2000 procedures as part of a local validation harness.

In the localhost Web UI, `/pygan` shows the PyGan doctor result, module import
paths, and a runnable ASCII-vs-PyGan writer comparison report. `/convert`
reports whether PyGan is importable from the running backend Python environment;
when a PyGan conversion succeeds, the result panel links directly to the
prefilled `/pygan` comparison workflow.

See [docs/PYGAN_BACKEND.md](docs/PYGAN_BACKEND.md) for install notes, command
examples, and the current scope of the optional backend.

## Quick Start

New users should start with the short path-oriented guide:

- [User README: HDF5 -> Convert -> Bundle -> DONJON](docs/CONVERTER_USER_README.md)

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
- statistical-uncertainty visibility when `*_std_dev` datasets are present,
  with optional hard coverage gates for production workflows.

Details:

- [Production preset](docs/PRODUCTION_PRESET.md)
- [Production thresholds](docs/PRODUCTION_THRESHOLDS.md)
- [HDF5 input contract](docs/HDF5_INPUT_CONTRACT.md)

## OpenMC-Side SPH And ADF/DF

The package can carry equivalence data into DONJON handoffs:

- ADF/HADF discontinuity factors, including flux-ratio ADF sidecars.
- SPH/NSPH factors generated from OpenMC-side CE/MG equivalence.

The converter records these factors and provenance in the HDF5/MACROLIB/MULTICOMPO
handoff; it does not invent physics corrections on its own. Case-specific ADF
or SPH factors should come from the chosen OpenMC CE reference and OpenMC MG
macro workflow. A single isolated assembly generally does not need SPH; a
colorset or full-core macro model needs one SPH factor per homogenized output
region and energy group.

For the current DONJON consumption smoke, OpenMC-side SPH is accepted through
`L_MACROLIB` because DONJON `DSPH:` reads `GROUP/*/NSPH`. `L_MULTICOMPO`
continues to carry mapped macroscopic data, but `NCR:` does not currently
promote these OpenMC-side SPH factors into non-unity macrolib `NSPH` values.

Entry points:

```sh
openmc2donjon make-adf-sidecar mgxs_library.h5 -o adf_sidecar.h5 --mode unity
openmc2donjon augment-adf mgxs_library.h5 --adf-source adf_sidecar.h5 -o mgxs_with_adf.h5

openmc2donjon make-openmc-sph-sidecar mgxs_library.h5 \
  -o sph_sidecar.h5 \
  --reference-flux openmc_ce_flux.h5::openmc_volume_flux \
  --mg-flux openmc_mg_flux.h5::openmc_volume_flux
openmc2donjon augment-sph mgxs_library.h5 --sph-source sph_sidecar.h5 -o mgxs_with_sph.h5
openmc2donjon mgxs_with_sph.h5 --format macrolib -o out.macrolib.txt --check --require-sph
```

Docs and examples:

- [External face-flux contract](docs/EXTERNAL_FACE_FLUX_CONTRACT.md)
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

CI runs the same unit-test matrix on Python 3.10, 3.11, and 3.12, plus Ruff,
the whitelisted strict mypy gate, and a frontend job that lints, type-checks,
and builds the `web/` Next.js project.

## Web UI (preview)

A localhost-only Next.js + FastAPI web UI lives in [`web/`](web/), wired to
the same Python package as the CLI. It includes a command workspace
(`Commands`), the OpenMC production planner (`OpenMC`), the direct converter
workflow (`Convert`), HDF5 inspection (`Inspect`), OpenMC-side ADF/SPH sidecar
builders (`Equivalence`), PyGan integration (`PyGan`), DONJON handoff guidance
(`DONJON`), and generic CLI command builders (`Builder`).

```sh
python -m pip install -e ".[web]"
openmc2donjon serve              # FastAPI on http://localhost:8000

# In another shell:
cd web
npm install
npm run dev                      # Next.js on http://localhost:3000
```

`openmc2donjon serve --mock` returns fixture data instead of calling the
real package APIs — useful for frontend-only development. See
[`web/README.md`](web/README.md) for full layout and conventions.

The Web UI is intentionally localhost-first. Direct conversion can be dry-run
or executed through `/convert`; equivalence and generic builders assemble
copyable CLI commands for OpenMC-side sidecar, bundle, and diagnostic support
commands.

## Roadmap

Near-term work:

- tighten the OpenMC CE/MG colorset minicase around corrected HDF5 ->
  MACROLIB NSPH -> DONJON `DSPH:`/`MAC:` handoff records;
- keep standard energy-mesh identification and uncertainty coverage visible in
  every production audit surface;
- broader mypy coverage for small pure helper modules.

Larger physics work remains separate from the format converter core:

- full downstream uncertainty propagation beyond exported OpenMC `std_dev`
  coverage and preflight gates;
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

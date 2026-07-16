# openmc2donjon

[![CI](https://github.com/arbreCui/openmc2donjon/actions/workflows/ci.yml/badge.svg)](https://github.com/arbreCui/openmc2donjon/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`openmc2donjon` is a general OpenMC-MGXS-to-DRAGON/DONJON Converter and
handoff workflow.
Converter is its mandatory core: every formal handoff validates one declared
MGXS HDF5, writes `L_MULTICOMPO` or `L_MACROLIB`, and records a hash-linked
receipt. The HDF5 may represent one assembly, one component with any number of
homogenization domains, an arbitrary colorset, or a full-core coarse model.

The product architecture is:

- **Converter:** required formal handoff boundary.
- **OpenMC MGXS:** optional input preparation when the HDF5 does not exist.
- **Physical SPH:** optional CE/MG equivalence when the model requires it.
- **Project:** optional coordination for repeated or multi-component jobs.
- **Inspect:** independent, read-only HDF5 structure and MGXS diagnostics.
- **DONJON:** downstream use and independent validation.
- **PyGan:** optional writer and semantic cross-validation backend inside
  Converter.

The stable path is:

```text
one declared MGXS HDF5
  -> Converter production validation
  -> L_MULTICOMPO or L_MACROLIB + receipt
  -> user- or project-defined DRAGON/DONJON consumer
```

When physical SPH is selected, the primary route sends the fine OpenMC
reference through Converter first, then solves native DRAGON `SPH:` on the
project-declared coarse geometry and verifies the corrected object in DONJON.
Native-SPH acceptance permits no ADF substitution, global multiplier,
empirical calibration, or k-effective fitting. The model may declare one
domain, many component domains, 91 independent positions, or exact symmetry
orbits pooled during fine transport.

```text
OpenMC fine reference
  -> Converter reference MACROLIB + receipt
  -> native DRAGON SPH on the declared coarse geometry
  -> corrected MACROLIB + DONJON verification
```

The OpenMC CE/MG `make-openmc-sph-sidecar` + `apply-sph` workflow remains an
optional alternate or cross-check when a project explicitly selects it. It is
not the mandatory production operator and cannot replace the declared
DRAGON/DONJON coarse solve for IRENA full-core acceptance.

Generic Converter inputs may carry explicitly supplied ADF/DF records for
separately declared workflows. Preserving those records is not permission to
use ADF in a native-SPH acceptance route, and Converter never invents or fits
an ADF or empirical correction.

## Export And Convert Modes

Both invocation styles ship:

- two-step: `openmc2donjon-export` writes `mgxs_library.h5`, then
  `openmc2donjon` converts it to ASCII. This is useful when the HDF5 is shared,
  archived, or post-processed between stages.
- one-step: `openmc2donjon-from-openmc` exports, checks, converts, and bundles
  a managed run directory in a single command.

Either invocation style produces the same Converter-facing HDF5. A direct
handoff can stop after Converter; a physical-equivalence project follows the
declared native-DRAGON route above. OpenMC-side factors remain an optional
alternate, not the primary product path.

## Output Formats

- `L_MULTICOMPO` as `.mcompo.txt` for mapped domain-wise libraries.
- `L_MACROLIB` as `.macrolib.txt` for direct one-state macrolib handoffs.

Accepted validation: C5G7 assembly-wise OpenMC -> DONJON handoff with
documented k-effective comparisons; see [Validation Status](#validation-status).

## PyGan Integration

The default converter backend is the pure Python ASCII LCM writer shipped in
this package. PyGan is treated as an optional DRAGON/DONJON integration layer
for validation, inspection, and an alternate writer backend.

These are deliberately separate statuses. The built-in ASCII writer is always
the normal OpenMC-to-DONJON handoff path. PyGan being unavailable only disables
PyGan-backed export and writer-comparison evidence; it does not block ordinary
`.mcompo.txt` or `.macrolib.txt` conversion.

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
  -o out.mcompo.txt \
  --production \
  --summary-json out.mcompo.txt.convert.json
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

5. Inspect the root structure of a DRAGON/DONJON LCM ASCII COMPO through
   PyGan:

```sh
openmc2donjon pygan-inspect-compo FUEL30.COMPO --summary-json fuel30.pygan.json
```

If PyGan is not installed, conversion still works through the default ASCII
writer. Installing PyGan is useful when you want Python-side access to native
DRAGON/DONJON LCM objects, want PyGan to export the ASCII file, or want to run
CLE-2000 procedures as part of a local validation harness.

In the localhost Web UI, `/pygan` shows the default ASCII writer and optional
PyGan writer as two separate cards, then reports the PyGan doctor result,
module import paths, and a runnable ASCII-vs-PyGan writer comparison report.
`/convert` reports whether PyGan is importable from the running backend Python
environment; when a PyGan conversion succeeds, the result panel links directly
to the prefilled `/pygan` comparison workflow.

See [docs/PYGAN_BACKEND.md](docs/PYGAN_BACKEND.md) for install notes, command
examples, and the current scope of the optional backend.

## Quick Start

New users should start with the short path-oriented guide:

- [User README: HDF5 -> Convert -> Bundle -> DONJON](docs/CONVERTER_USER_README.md)
- [Physics evidence audit and next accepted closure](docs/PHYSICS_EVIDENCE_AUDIT.md)

Clone and install from a fresh checkout:

```sh
git clone https://github.com/arbreCui/openmc2donjon.git
cd openmc2donjon
python -m pip install -e .
openmc2donjon --help
```

Check an MGXS handoff before conversion:

```sh
openmc2donjon check mgxs_library.h5 --production
```

Convert to MULTICOMPO:

```sh
openmc2donjon mgxs_library.h5 -o out.mcompo.txt --production \
  --summary-json out.mcompo.txt.convert.json
```

Convert to MACROLIB:

```sh
openmc2donjon mgxs_library.h5 --format macrolib \
  -o out.macrolib.txt --production \
  --summary-json out.macrolib.txt.convert.json
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
- [Fast-spectrum workflow](docs/FAST_SPECTRUM_WORKFLOW.md)
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

Recipe/statepoint exports also embed a content-hash-bound OpenMC provenance
record. It binds both a declared-complete fine-model input manifest and the
actual numerical HDF5 payload; the one-step v5 summary additionally binds the
final HDF5 and ASCII bytes. This makes the fine reference auditable without
making native DRAGON SPH rerun OpenMC or depend on the original local model
paths.

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
- for OpenMC-source handoffs, an intact recipe/statepoint reference binding;
- energy-bound consistency and known mesh audit metadata;
- scatter row-balance, chi normalization, ADF face consistency, and
  transport/P1 consistency gates;
- statistical-uncertainty visibility when `*_std_dev` datasets are present,
  with optional hard coverage gates for production workflows.

Details:

- [Production preset](docs/PRODUCTION_PRESET.md)
- [Production thresholds](docs/PRODUCTION_THRESHOLDS.md)
- [HDF5 input contract](docs/HDF5_INPUT_CONTRACT.md)

## Physical SPH

Physical SPH is optional. Use it only when the homogenized model needs an
explicit equivalence closure. The primary physical route is OpenMC fine
reference -> Converter reference MACROLIB -> native DRAGON SPH -> DONJON
verification. A standalone assembly is a valid SPH model when its declared
fine and coarse problems match; geometry alone neither accepts nor rejects it.

The general contract accepts any positive number of declared domains. It
requires a matched fine reference and coarse model, rate preservation,
convergence, zero numerical exemptions, and hash-linked artifacts. Converter
checks the formal boundary and provenance; it never invents or fits a factor.

The commands below implement the optional OpenMC CE/MG alternate route. They
do not replace native DRAGON SPH when the project declares that coarse solver.

Entry points:

```sh
openmc2donjon make-openmc-sph-sidecar mgxs_library.h5 \
  -o sph_sidecar.h5 \
  --reference-flux openmc_ce_flux.h5::openmc_volume_flux \
  --mg-flux openmc_mg_flux.h5::openmc_mg_flux

# Optional OpenMC-side SPH iteration:
# write corrected OpenMC-native MGXS (XS / NSPH), rerun OpenMC MG with it,
# then recompute the SPH sidecar from the new MG flux.
openmc2donjon apply-sph mg_case/mgxs_unapplied.h5 \
  --input-format openmc-mgxs \
  --sph-source sph_sidecar.h5 \
  -o mg_case/mgxs.h5

# Final Converter handoff path (MULTICOMPO or MACROLIB is chosen downstream):
openmc2donjon apply-sph mgxs_library.h5 \
  --sph-source sph_sidecar.h5 \
  -o mgxs_sph_applied.h5
openmc2donjon mgxs_sph_applied.h5 --format multicompo \
  -o out.mcompo.txt --production --require-physical-sph
```

Docs and examples:

- [External face-flux contract](docs/EXTERNAL_FACE_FLUX_CONTRACT.md)
- [External low-order handoff](examples/external_low_order_handoff/)

## Validation Status

Current validation line:

- C5G7 assembly-wise OpenMC-to-DONJON handoff with DONJON k-effective checks.
- The accepted IRENA-30 ZREFL 91-hex OpenMC-MG -> Converter -> DONJON
  SN8/SCAT2 baseline agrees with its paired OpenMC-MG reference in k-effective
  and fission-source shape. It validates downstream hex mapping and solver
  mechanics; it is not CE-fine/native-SPH/full-core physics acceptance.
- Converter round trips for `L_MULTICOMPO` and `L_MACROLIB`.
- Mechanics smokes for recipe export, full-core domain mapping, hex geometry
  capability, and SPH handoff mechanics.

There is currently no accepted IRENA continuous-energy fine -> SPH ->
full-core result. Earlier local PNL/EXT and INT/EXT summaries are withdrawn as
physics passes: their listings contain unconverged final transport solves, and
their local boundary/volume contract does not establish the full-core leakage
environment. The current candidate uses all 91 fine assemblies with either 91
independent domains or 21 exact global D3 orbit domains, then requires joint
k-effective, leakage, power-shape, statistical, and numerical-convergence
gates. No ADF or empirical/global eigenvalue factor is permitted.

Run portable checks:

```sh
bash scripts/portable_release_smoke.sh
bash scripts/run_recipe_export_smoke.sh
bash scripts/run_c5g7_demo.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests
```

GitHub CI and `scripts/portable_release_smoke.sh` are software/fixture gates:
they do not require OpenMC, DRAGON/DONJON, or PyGan and do not claim a physics
benchmark by themselves. Run the full local release gate, including optional
DONJON-dependent smokes when the local DRAGON/DONJON checkout is available:

```sh
bash scripts/release_check.sh
bash scripts/release_check.sh --run-donjon
```

More detail:

- [Validation summary](docs/VALIDATION.md)
- [Release gates](docs/RELEASE_GATES.md)
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
(`Commands`), OpenMC MGXS preparation (`OpenMC`), the core Converter workflow
(`Converter`), HDF5 inspection (`Inspect`), physical SPH tools (`SPH`), optional
project coordination (`Projects`), PyGan integration (`PyGan`), DONJON guidance
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

Live mode is localhost-first. If you bind the backend to a non-loopback host,
constrain filesystem access with `--workspace-root /path/to/openmc-runs`;
otherwise the server refuses to start unless `--unsafe-remote` is explicitly
requested.

The Web UI is intentionally localhost-first. Converter production validation,
exact-deck native DRAGON SPH execution and evidence validation, optional
OpenMC-side SPH sidecar/application, project creation/status, read-only HDF5
inspection, PyGan writer comparison, and DONJON diagnostics can run locally;
advanced builders retain copyable CLI commands for lower-level support
operations.

## Roadmap

Near-term work:

- produce one hash-linked IRENA 91-position/21-D3-orbit result through
  Converter -> native DRAGON SPH -> DONJON and every full-core acceptance gate;
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

# Release Notes

## Unreleased

- Added a concise quickstart for the installed CLI and recipe/statepoint
  workflows.
- Reorganized the README first screen around install, smoke, and one-step
  conversion commands.
- Added `--summary-json` to `openmc2donjon-from-openmc` for conversion
  provenance manifests.
- Documented the `openmc2donjon.from-openmc-summary.v2` JSON schema for
  automation and handoff checks.
- Added shared summary schema validation for unittest and smoke-script checks.
- Added an editable OpenMC recipe template for user production cases.
- Added `openmc2donjon-export --dry-run` for recipe/domain preflight checks.
- Added `openmc2donjon check` as the packaged MGXS HDF5 input-contract
  preflight entry point.
- Added `openmc2donjon ... --check` to run input-contract preflight before
  writing DONJON ASCII.
- Added checked conversion support to `openmc2donjon-from-openmc` so the
  recipe/statepoint one-step path can fail before writing DONJON ASCII.
- Bumped the from-OpenMC summary schema to v2 with checked preflight provenance.
- Added `openmc2donjon-from-openmc --dry-run` for one-step conversion-plan
  checks that do not write HDF5, summary JSON, or DONJON ASCII files.
- Added a recipe production checklist to dry-run/doctor output covering MGXS
  coverage, transport readiness, domain mapping, volumes, and `domain_mode`.
- Added `openmc2donjon inspect` for read-only MGXS HDF5 inventory reports with
  optional JSON output.
- Added `openmc2donjon diff` for exact or tolerance-based MGXS HDF5 baseline
  comparisons.
- Added `openmc2donjon doctor` for local runtime, dependency, entrypoint, and
  optional recipe dry-run diagnostics.
- Added `openmc2donjon bundle` to collect production handoff artifacts into a
  manifest-backed directory.
- Added `openmc2donjon-from-openmc --run-dir` for standard production run
  directories with managed outputs and a bundle manifest.
- Added `openmc2donjon augment-adf` for injecting computed ADF/DF sidecars into
  MGXS HDF5 handoffs before DONJON conversion.
- Added `openmc2donjon make-adf-sidecar` for generating an identity
  `adf_real=false` sidecar that exercises the ADF/DF injection workflow.
- Extended `make-adf-sidecar` with a `flux-ratio` mode that writes physical
  sidecars from heterogeneous and homogeneous face-flux HDF5 datasets.
- Added `openmc2donjon export-surface-flux` for exporting OpenMC
  `MeshSurfaceFilter`/`MuSurfaceFilter` current tallies to the flux-ratio
  surface-flux HDF5 layout.
- Added `openmc2donjon make-homogeneous-face-flux` for reconstructing the
  homogeneous denominator from volume flux, outward net current, and
  `transport_total`.
- Added `openmc2donjon-from-openmc --adf-source` so the one-step OpenMC export
  path can inject ADF before checked DONJON conversion.
- Added `examples/production_minicase` plus a smoke script for a fresh
  continuous-energy OpenMC MGXS case that does not rely on the C5G7 snapshot.
- Extended the production minicase smoke to run the OpenMC statepoint ->
  surface flux -> flux-ratio ADF sidecar -> checked MULTICOMPO path.
- Extended release check so the C5G7 statepoint parity path exercises
  `openmc2donjon-from-openmc`, reads back the generated MCO, and validates the
  summary manifest.

## v0.1.2-openmc-workflow - 2026-05-19

- Added a production-facing `openmc2donjon-export --recipe ... --statepoint ...`
  workflow for exporting real OpenMC MGXS statepoints to the HDF5 handoff
  contract.
- Added a documented OpenMC export recipe interface and a C5G7 recipe smoke
  wired into `scripts/release_check.sh`.
- Added a tiny recipe export smoke that exercises the user entry point without
  requiring C5G7 setup or real OpenMC output.
- Added `openmc2donjon-from-openmc`, a one-command recipe/statepoint export plus
  DONJON ASCII conversion entry point.
- Verified the installed console scripts from a fresh GitHub checkout in a
  temporary virtual environment.

## v0.1.1-c5g7-handoff - 2026-05-19

This is the current internal handoff release for `openmc2donjon`.

### Accepted Validation Line

- C5G7 assembly-wise homogenization is the accepted physics validation line.
- The production path is:

```text
OpenMC MGXS/ADF HDF5
  -> openmc2donjon L_MULTICOMPO / L_MACROLIB
  -> DONJON assembly-wise diffusion/SPN smokes
```

- Spatial mapping remains one OpenMC MGXS domain or subdomain to one DONJON
  mixture.
- Locked reference results are documented in `docs/VALIDATION.md`.

### Changes Since v0.1.0-c5g7-accepted

- Added a reviewer handoff note for the accepted C5G7 line.
- Added experimental one-dimensional `BURN` multi-state serialization.
- Added a tiny DONJON `NCR:` smoke that proves `PARKEY=BURN`, `TREE`, and
  `CALCULATIONS` select the expected state.
- Extended HDF5 preflight to validate `BURN`-axis multi-state inputs.
- Rejected unsupported multi-axis branch-library inputs instead of silently
  ignoring extra `/state_points/*` axes.
- Documented supported HDF5 schema variants in the README and input contract.

### Supported Scope

- Production: one-state MGXS HDF5 to `L_MULTICOMPO` or root `L_MACROLIB`.
- Experimental: one-dimensional `BURN` multi-state HDF5 serialization.
- Capability only: hex spatial-domain conversion/modeling.
- Not supported: general multi-axis branch libraries such as boron,
  temperature, coolant-density, or control-state grids.

### Required Checks

```sh
bash scripts/release_check.sh
bash examples/donjon_openmc2donjon/run_burnup_axis_smoke.sh
```

Full local acceptance with DONJON decks:

```sh
bash scripts/release_check.sh --run-donjon
```

## v0.1.0-c5g7-accepted - 2026-05-19

Initial accepted C5G7 assembly-wise handoff tag.

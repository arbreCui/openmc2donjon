# Release Notes

## Unreleased

- Added `examples/irena30_zrefl_hex`, the accepted hex benchmark: IRENA-30
  91-hex 2D ARI ZREFL in OpenMC multi-group mode with per-position MGXS
  tallies, exported to a 91-mixture `L_MULTICOMPO` and consumed through
  DONJON `NCR:` + `SNT:` SN8 transport (primary) and TRIVAC MCFD diffusion
  (diagnostic). Both acceptance gates passed in one `run_zrefl_keff.sh`
  invocation against the paired OpenMC reference: SN8 k-eff delta -9 pcm
  (21 pcm Monte Carlo sigma) and per-assembly fission-source shape within
  1.27 % worst / 0.47 % RMS over the 52 fuel positions (via `EDI: MERG MIX
  COND` and `NUSIGF * FLUX-INTG`). The baseline manifest's hex line is now
  `accepted` and its summaries are validated by
  `validate_accepted_baseline.py`. Encodes two multi-group-mode workflow
  gotchas: MG statepoints return mgxs arrays in ascending-energy order
  (the recipe requests `order_groups="decreasing"`), and zero-flux thermal
  groups need macrolib substitution before the input contract accepts the
  export.
- Refreshed the accepted C5G7 artifact
  (`examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5`)
  additively so the exporter-parity smokes pass again after the
  uncertainty-preservation feature: current exporters also write
  `mixture_names`, per-dataset `*_std_dev`, per-mixture `source_domain_*`
  attributes, and the `domain_type` / `energy_bounds_sha256` /
  `energy_group_structure` root attributes. All previously present datasets
  and attributes are byte-identical to the locked baseline.
- Added SPH sidecar/augmentation support: `make-sph-sidecar`,
  `augment-sph`, `check --require-sph`, HDF5 `sph/NSPH` carry-through, and
  DONJON `L_MACROLIB` `GROUP/*/NSPH` read/write with `STATE-VECTOR(14)` set.
- Extended `make-sph-sidecar` with `--mode macrolib` to extract DONJON/DRAGON
  `GROUP/*/NSPH` factors from an `L_MACROLIB` ASCII dump into the canonical
  SPH sidecar schema.
- Added `docs/EXTERNAL_FACE_FLUX_CONTRACT.md` and
  `examples/external_face_flux_adapter`, a runnable template for adapting
  external nodal/SPN/diffusion homogeneous face fluxes into the canonical
  `homogeneous_face_flux` HDF5 denominator used by flux-ratio ADF generation.
- Added `scripts/run_c5g7_donjon_face_flux_smoke.sh`, which regenerates the
  accepted C5G7 homogeneous face-flux denominator from real DONJON
  `L_FLUX`/`L_TRACK` dumps, checks exact HDF5 payload parity with the accepted
  artifact, and rebuilds the production ADF sidecar from that regenerated
  source.
- Added `examples/external_low_order_handoff`, a deterministic production-facing
  example for external low-order/nodal driver handoffs with case-specific HDF5
  paths, mixture/face reordering, positive-inward current conversion,
  homogeneous face-flux reconstruction, face-flux contract checking, and ADF
  injection/readback.
- Added `openmc2donjon check-face-flux` and wired it into
  `from-openmc --build-flux-ratio-adf`; managed ADF runs now write and bundle
  `face_flux_check_summary.json` before sidecar generation.
- Extended the production minicase smoke with a non-C5G7 external
  face-flux workflow: `from-openmc --build-flux-ratio-adf` now consumes
  existing surface and homogeneous face-flux HDF5 files directly, skips
  low-order reconstruction, and checks exact ADF parity with the reconstructed
  minicase path.
- Added `openmc2donjon-from-openmc --homogeneous-face-flux` so one-step
  flux-ratio ADF production runs can consume an existing homogeneous face-flux
  denominator directly instead of rebuilding it from low-order driver inputs.
- Added a C5G7 from-OpenMC flux-ratio ADF release smoke that exports the saved
  statepoint, consumes accepted OpenMC surface flux and DONJON homogeneous face
  flux through `--build-flux-ratio-adf`, and checks exact accepted ADF payload
  parity.
- Allowed `openmc2donjon-from-openmc --adf-surface-flux` to accept
  `FILE::DATASET` references and bundle the underlying HDF5 file.
- Added a C5G7 production ADF source reconstruction smoke that rebuilds the
  accepted ADF sidecar from OpenMC surface flux over DONJON homogeneous face
  flux and checks exact payload equality.
- Allowed flux-ratio ADF generation to handle nonpositive homogeneous
  denominator bins through the explicit `--invalid-fill` policy.
- Restored C5G7 statepoint exporter parity by making the C5G7 recipe's
  `consistent nu-scatter matrix` baseline compatibility choice explicit and
  recording the same scatter provenance on the accepted HDF5 snapshot.
- Added a current handoff snapshot for reviewers, covering capabilities,
  accepted C5G7 validation, release gates, known boundaries, and next physical
  work.
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
- Hardened the OpenMC recipe template with explicit `DomainExportSpec`
  mapping, volume hooks, production metadata, and strict-dry-run guidance.
- Added `openmc2donjon-export --dry-run` for recipe/domain preflight checks.
- Added `--strict-dry-run` to recipe dry-run entry points so production
  checklist warnings/failures can return non-zero in automation.
- Added `openmc2donjon check` as the packaged MGXS HDF5 input-contract
  preflight entry point.
- Added optional scatter row-balance thresholds to input-contract preflight,
  reporting the worst `total - absorption - sum(P0 scatter)` residual in text
  and JSON summaries.
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
- Added `openmc2donjon-from-openmc --extra-artifact LABEL=PATH` so side
  products can be copied into the managed run-directory manifest.
- Added `openmc2donjon augment-adf` for injecting computed ADF/DF sidecars into
  MGXS HDF5 handoffs before DONJON conversion.
- Added `openmc2donjon make-adf-sidecar` for generating an identity
  `adf_real=false` sidecar that exercises the ADF/DF injection workflow.
- Extended `make-adf-sidecar` with a `flux-ratio` mode that writes physical
  sidecars from heterogeneous and homogeneous face-flux HDF5 datasets.
- Added `openmc2donjon export-surface-flux` for exporting OpenMC
  `MeshSurfaceFilter`/`MuSurfaceFilter` current tallies to the flux-ratio
  surface-flux HDF5 layout.
- Added `openmc2donjon make-low-order-driver` for canonicalizing external
  low-order volume flux and outward net-current handoffs.
- Extended low-order driver canonicalization to honor declared raw
  `face_names`, reordering net-current faces into the requested canonical
  order.
- Extended low-order driver canonicalization to convert raw `positive inward`
  net-current sign conventions to the project canonical `positive outward`
  convention, with conversion provenance in summaries.
- Added raw low-order driver bundle adapters via `--raw-driver` and
  `--low-order-raw-driver`, with adapter provenance recorded in HDF5 and JSON
  summaries.
- Added `openmc2donjon check-low-order-driver` for strict low-order handoff
  preflight, including current sign convention and optional face-width
  homogeneous-flux positivity checks.
- Added `openmc2donjon-from-openmc --build-flux-ratio-adf` to build, check,
  inject, and bundle the surface-flux/low-order/homogeneous-flux/ADF side
  artifacts inside a managed production run directory.
- Added `openmc2donjon make-homogeneous-face-flux` for reconstructing the
  homogeneous denominator from volume flux, outward net current, and
  `transport_total`.
- Added `openmc2donjon-from-openmc --adf-source` so the one-step OpenMC export
  path can inject ADF before checked DONJON conversion.
- Report missing MGXS tallies in recipe/statepoint exports as actionable CLI
  errors instead of raw OpenMC `LookupError` tracebacks.
- Added `examples/production_minicase` plus a smoke script for a fresh
  continuous-energy OpenMC MGXS case that does not rely on the C5G7 snapshot.
- Hardened the production minicase recipe with explicit `DomainExportSpec`
  mapping, production metadata, a strict dry-run gate, and repeatable managed
  run-directory overwrites for smoke automation.
- Extended the production minicase smoke to run the OpenMC statepoint ->
  surface flux -> low-order driver handoff -> homogeneous face flux ->
  flux-ratio ADF sidecar -> checked MULTICOMPO path.
- Added `examples/hex_minicase`, a synthetic hex-domain capability smoke with
  seven cell-domain mixtures, P1 scattering, explicit `transport_total`, and
  six-face ADF readback through `L_MULTICOMPO` and `L_MACROLIB`.
- Added `examples/openmc_hex_minicase`, a real continuous-energy OpenMC hex
  lattice recipe/statepoint smoke with seven hex cell-domain mixtures and
  checked `L_MULTICOMPO`/`L_MACROLIB` readback.
- Hardened the OpenMC hex minicase recipe with explicit `DomainExportSpec`
  mapping, production metadata, strict dry-run gating, and repeatable managed
  run-directory overwrites.
- Promoted the real OpenMC hex minicase smoke into the default release check so
  Cartesian and hexagonal OpenMC recipe/statepoint workflows are gated together.
- Added `examples/uox_5x5_tg6`, a candidate non-C5G7 adapter/smoke for a local
  DRAGON/APEX UOX 5x5 TG6 HDF5 source, producing checked `L_MULTICOMPO` and
  `L_MACROLIB` outputs.
- Added `scripts/release_check.sh --run-local-candidates` to include local
  non-accepted candidate examples without changing the default accepted
  validation line.
- Extended release check so the C5G7 statepoint parity path exercises
  `openmc2donjon-from-openmc`, reads back the generated MCO, and validates the
  summary manifest.
- Wired row-balance preflight checks into production, hex, UOX, recipe, C5G7
  demo, and C5G7 acceptance smoke scripts.
- Balanced the recipe and synthetic hex smoke MGXS fixtures so deterministic
  examples can use strict row-balance failure thresholds instead of expected
  warnings.

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

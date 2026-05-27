# Scripts Inventory

This directory contains local smoke gates and case-specific rebuild helpers.
Keep package features in `src/openmc2donjon`; scripts are for validation,
accepted-baseline maintenance, or developer diagnostics.

## Release Gates

These are stable entry points used directly by the release check.

- `release_check.sh` - top-level release gate; runs package tests, portable
  smokes, accepted-baseline checks, and optional DONJON/local candidates.
- `run_energy_mesh_contract_smoke.sh` - CLI-level MGXS `/energy_bounds`
  known-mesh audit smoke; verifies a bundled mesh is identified and an unknown
  mesh can be promoted to hard failure.
- `run_recipe_export_smoke.sh` - portable recipe-to-HDF5-to-ASCII smoke.
- `run_production_minicase_smoke.sh` - small real OpenMC production-export
  workflow smoke.
- `run_pygan_backend_smoke.sh` - optional PyGan backend writer-comparison and
  DONJON read-only ingest smoke; skips cleanly when PyGan is not installed.
- `run_openmc_full_core_production_smoke.sh` - full-core assembly-wise
  OpenMC production handoff smoke.
- `../examples/openmc_sph_sidecar_minicase/run_smoke.sh` - portable OpenMC
  CE/MG SPH sidecar handoff smoke; verifies `make-openmc-sph-sidecar`,
  `augment-sph`, and both ASCII writer formats without a DONJON feedback loop.
- `run_dragon_sph_handoff_smoke.sh` - DRAGON NSPH extraction and handoff smoke.
- `run_donjon_sph_consume_smoke.sh` - DONJON consumes `NSPH` from generated
  macrolib output.
- `run_donjon_sph_solver_response_smoke.sh` - DONJON solver responds to SPH
  perturbations.
- `../examples/sph_loop_minicase/run_smoke.sh` - legacy fixed-OpenMC SPH loop
  candidate; useful for reference-flux `std_dev` acceptance diagnostics but no
  longer part of the default release gate.

## C5G7 Accepted-Baseline Gates

These are stable but case-specific. They exercise the locked C5G7
assembly-wise validation artifacts.

- `run_c5g7_demo.sh` - C5G7 converter/readback demo and optional DONJON run.
- `run_c5g7_adf_source_smoke.sh` - rebuilds production ADF from the accepted
  face-flux source and verifies carry-through.
- `run_c5g7_donjon_face_flux_smoke.sh` - regenerates DONJON homogeneous
  face-flux data for C5G7.
- `run_c5g7_from_openmc_adf_smoke.sh` - exercises statepoint export plus
  flux-ratio ADF injection.
- `run_c5g7_sph_solver_response_smoke.sh` - verifies DONJON k-eff changes when
  a C5G7 SPH table is consumed.
- `run_c5g7_sph_iteration_from_donjon_flux_smoke.sh` - builds one SPH update
  from OpenMC reference flux and DONJON flux.
- `run_c5g7_fixed_openmc_sph_loop_smoke.sh` - fixed-OpenMC SPH loop smoke with
  DONJON low-order feedback.

## C5G7 Recipes And Deck Generators

These generate or reproduce case-specific inputs. They are useful, but should
not become generic package APIs.

- `c5g7_export_recipe.py` - recipe for the generic OpenMC statepoint exporter.
- `export_c5g7_statepoint.py` - legacy C5G7-specific exporter retained for
  comparison with the generic recipe path.
- `generate_c5g7_assembly_keff_input.py` - writes the assembly-wise DONJON
  k-eff input.
- `generate_c5g7_keff_input.py` - writes the older fine Cartesian sampled
  DONJON k-eff smoke input.
- `generate_c5g7_dragon_moc.py` - writes the local DRAGON MOC deck.

## Rebuild Helpers

These rebuild accepted or candidate C5G7 data products. They usually depend on
local OpenMC/DONJON/DRAGON artifacts.

- `extract_c5g7_donjon_face_flux.py` - extracts homogeneous face flux from
  DONJON `L_FLUX`/`L_TRACK` ASCII dumps.
- `c5g7_boundary_currents.py` - runs OpenMC assembly-face current tallies.
- `build_c5g7_adf_candidate.py` - builds diagnostic ADF candidates from
  OpenMC face tallies.
- `estimate_c5g7_df_from_currents.py` - estimates diagnostic surface/volume
  flux ratios from current tallies.
- `unfold_c5g7_boundary_currents.py` - unfolds diagonal-wedge boundary currents
  to assembly-wise cells.

## Diagnostics

These are local validation probes. They can be useful when changing the
converter, but they are not release entry points unless called from a smoke.

- `validate_adf_carrythrough.py` - checks generated ADF blocks against HDF5.
- `validate_c5g7_assembly_target.py` - summarizes the locked C5G7 target.
- `validate_c5g7_dragon_moc_edi.py` - validates DRAGON exact-pin C5G7 EDI
  assembly homogenization output.
- `validate_ncr_macrolib.py` - validates DONJON NCR macrolib output against
  OpenMC MGXS HDF5.
- `stress_lcm_ascii_parser.py` - opt-in large-file parser stress gate for
  external DRAGON/DONJON ASCII samples.

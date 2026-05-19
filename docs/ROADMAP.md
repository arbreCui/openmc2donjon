# Roadmap

## Current Baseline

- C5G7 assembly-wise validation is accepted.
- HDF5 input contract is documented.
- OpenMC `mgxs.Library` exporter is available for the documented HDF5 contract.
- Portable C5G7 converter demo is available.
- Optional DONJON handoff smoke is available for machines with a local
  DRAGON/DONJON checkout.
- Hex support exists as capability work, but no accepted hex benchmark is
  included yet.

## Near-Term Work

1. Keep C5G7 reproducibility boring.
   - Keep `scripts/run_c5g7_demo.sh` green.
   - Keep `examples/donjon_openmc2donjon/run_handoff_smoke.sh` green.
   - Avoid adding new benchmark claims without a reproducible source path.

2. Harden the OpenMC exporter path with real cases.
   - Validate the exporter against the accepted C5G7 OpenMC workflow.
   - Keep the spatial domain naming stable enough to map back to DONJON
     mixtures.

3. Reduce example size where possible.
   - Keep the accepted snapshot for C5G7.
   - Add smaller synthetic fixtures for unit-level examples when helpful.

4. Select a proper hex benchmark.
   - Require complete geometry, material/profile/control inputs.
   - Require a defensible reference solution.
   - Promote only after field-level and k-effective checks are reproducible.

## Later Work

- Multi-state and branch-parameter support.
- More complete discontinuity-factor workflows.
- Additional validation cases beyond C5G7.
- Packaging polish for external installation and CI.

## Non-Goals For The Current Release

- Reconstructing missing benchmark material definitions from partial local
  artifacts.
- Treating exploratory hex results as accepted validation.
- Replacing OpenMC homogenization; OpenMC remains the source of spatially
  homogenized MGXS data.

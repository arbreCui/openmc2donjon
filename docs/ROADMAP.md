# Roadmap

## Current Baseline

- C5G7 assembly-wise validation is accepted.
- HDF5 input contract is documented.
- OpenMC `mgxs.Library` exporter is available for the documented HDF5 contract,
  including explicit mesh/cell subdomain exports.
- Recipe-based OpenMC statepoint export is available as the production-facing
  user entry point.
- A tiny recipe export smoke is available so the entry point can be tested
  without C5G7-specific setup.
- Portable C5G7 converter demo is available.
- Optional DONJON handoff smoke is available for machines with a local
  DRAGON/DONJON checkout.
- Experimental one-parameter `BURN` multi-state serialization is available and
  has a tiny DONJON `NCR:` consumer smoke.
- Hex support exists as capability work, but no accepted hex benchmark is
  included yet.

## Near-Term Work

1. Keep C5G7 reproducibility boring.
   - Keep `scripts/run_c5g7_demo.sh` green.
   - Keep `examples/donjon_openmc2donjon/run_handoff_smoke.sh` green.
   - Avoid adding new benchmark claims without a reproducible source path.

2. Harden the OpenMC exporter path with real cases.
   - Prefer recipe/statepoint exports over hand-maintained HDF5 snapshots.
   - Keep the tiny recipe export smoke green as the first user-entry check.
   - Keep the exporter-to-C5G7 statepoint smoke reproducible.
   - Keep the spatial domain naming stable enough to map back to DONJON
     mixtures.

3. Reduce example size where possible.
   - Keep the accepted snapshot for C5G7.
   - Add smaller synthetic fixtures for unit-level examples when helpful.

4. Keep the experimental `BURN`-axis consumer smoke green.
   - Keep it separate from the accepted C5G7 physics baseline.
   - Promote only after it is backed by a real depletion or branch case.

5. Select a proper hex benchmark.
   - Require complete geometry, material/profile/control inputs.
   - Require a defensible reference solution.
   - Promote only after field-level and k-effective checks are reproducible.

## Later Work

- Additional branch-parameter axes beyond the experimental `BURN` path.
  - This requires extending preflight, HDF5 schema, `PARKEY/PARTYP/PARFMT`,
    per-mixture `TREE`, and DONJON consumer smoke together.
- More complete discontinuity-factor workflows.
- Additional validation cases beyond C5G7.
- Packaging polish for external installation and CI.

## Non-Goals For The Current Release

- Reconstructing missing benchmark material definitions from partial local
  artifacts.
- Treating exploratory hex results as accepted validation.
- Treating the experimental multi-state serializer smoke as an accepted physics
  benchmark.
- Replacing OpenMC homogenization; OpenMC remains the source of spatially
  homogenized MGXS data.

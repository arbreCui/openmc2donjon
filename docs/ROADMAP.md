# Roadmap

## Current Baseline

- C5G7 assembly-wise validation is accepted.
- HDF5 input contract is documented.
- OpenMC `mgxs.Library` exporter is available for the documented HDF5 contract,
  including explicit mesh/cell subdomain exports.
- Recipe-based OpenMC statepoint export is available as the production-facing
  user entry point.
- One-step recipe/statepoint export plus DONJON ASCII conversion is available
  for users who do not need to manage the intermediate HDF5 explicitly.
- A tiny recipe export smoke is available so the entry point can be tested
  without C5G7-specific setup.
- Portable C5G7 converter demo is available.
- Optional DONJON handoff smoke is available for machines with a local
  DRAGON/DONJON checkout.
- Experimental one-parameter `BURN` multi-state serialization is available and
  has a tiny DONJON `NCR:` consumer smoke.
- Hex support is validated by an accepted benchmark:
  `examples/irena30_zrefl_hex` (IRENA-30 91-hex 2D ARI ZREFL, paired
  OpenMC-MG reference; DONJON SN8 k-eff within Monte Carlo statistics and
  per-assembly fission-source shape within 1.3 % worst / 0.5 % RMS).
  The synthetic and real OpenMC hex workflow smokes remain as capability
  checks.

## Near-Term Work

1. Keep C5G7 reproducibility boring.
   - Keep `scripts/run_c5g7_demo.sh` green.
   - Keep `examples/donjon_openmc2donjon/run_handoff_smoke.sh` green.
   - Avoid adding new benchmark claims without a reproducible source path.

2. Harden the OpenMC exporter path with real cases.
   - Prefer recipe/statepoint exports over hand-maintained HDF5 snapshots.
   - Keep the tiny recipe export smoke green as the first user-entry check.
   - Keep the exporter-to-C5G7 statepoint smoke reproducible.
   - Keep candidate non-C5G7 adapters, such as `examples/uox_5x5_tg6`, separate
     from accepted validation claims until their reference path is reproducible.
   - Keep the spatial domain naming stable enough to map back to DONJON
     mixtures.

3. Reduce example size where possible.
   - Keep the accepted snapshot for C5G7.
   - Keep `examples/hex_minicase` as a small capability smoke for hex-domain
     mapping and six-face ADF payloads.
   - Keep `examples/openmc_hex_minicase` as the small real OpenMC hex workflow
     smoke.
   - Add smaller synthetic fixtures for unit-level examples when helpful.

4. Keep the experimental `BURN`-axis consumer smoke green.
   - Keep it separate from the accepted C5G7 physics baseline.
   - Promote only after it is backed by a real depletion or branch case.

5. Keep the accepted hex benchmark reproducible.
   - `examples/irena30_zrefl_hex` (IRENA-30 91-hex 2D ARI ZREFL) is the
     accepted line: both gates — SN8 k-eff vs the paired OpenMC run and the
     per-assembly fission-source shape — passed in one
     `run_zrefl_keff.sh` invocation; summaries are locked under
     `irena30_zrefl_accepted/` and checked by the baseline manifest
     validation.
   - It depends on local IRENA workspace data and a local DONJON, so it
     stays an optional local check rather than a default gate step.
   - Natural extensions: the 3D fineZ rod-depth points (d00..d90) as a
     multi-state `ROD-DEPTH` multicompo, and a different-seed robustness
     run.

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

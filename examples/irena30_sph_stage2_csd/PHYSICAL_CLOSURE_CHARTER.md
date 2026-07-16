# IRENA PNL/EXT Native SPH Candidate V4 — Withdrawn

This charter preserves a historical local candidate completed on 2026-07-15.
It is withdrawn as a physics pass: the listing reaches the program's normal
end after reporting final transport nonconvergence, a condition the original
validator did not reject. It is not an IRENA full-core acceptance.

## Declared model

- Fine reference: real continuous-energy OpenMC `pnl_ext` explicit
  seven-assembly colorset, with the pin-resolved PNL center and six EXT
  neighbors.
- Homogenized components: the center becomes `PNL`; the six symmetry-equivalent
  neighbors collapse together to `EXT`. The coarse model therefore has two
  mixtures. This mapping belongs to this model; Converter does not assume two,
  five, seven, or 91 domains for other users.
- Energy model: `anl_24c_20mev`, formed by extending ANL-23C with the missing
  10--20 MeV group. Full-energy OpenMC absorption, fission, kappa-fission, and
  nu-fission tallies show zero reaction-rate fraction outside the retained
  energy range.
- Converter data: 24 groups, P3 scattering, exact volume-integrated flux, and
  reaction-rate-preserving component collapse.
- Coarse geometry: seven hexagons with side 9.9950212 cm and white outer
  boundary, mapped as one PNL center plus six EXT neighbors.
- Coarse solver: DRAGON native `SPH:` with TRIVAT SPN3 and SCAT1. `SN` or `SPN`
  is the general product choice; SPN3 is the declared solver for this run.

## Physical route

```text
OpenMC CE fine reference
  -> component MGXS with exact integrated flux and reference uncertainty
  -> Converter reference L_MACROLIB
  -> native DRAGON SPH on the declared coarse geometry
  -> corrected NSPH L_MACROLIB
  -> DONJON SPN verification
```

OpenMC MG mode is not required by this route. It may be retained as an
independent diagnostic, but it cannot replace the DRAGON/DONJON coarse solve.

## Frozen acceptance gates

- DRAGON must reach a normal end and native SPH RMS convergence at the declared
  `1e-6` criterion.
- Every one-speed inner solve and the final transport/eigenvalue solve must
  independently have auditable convergence evidence; a normal end is not
  sufficient.
- The Converter reference rate-balance eigenvalue and final DONJON eigenvalue
  must each lie within 2 OpenMC standard deviations of the fine reference.
- The energy-coverage check must pass.
- Zero-bin fills, identity substitution, flux floors, frozen groups, clipping,
  ADF, empirical factors, global eigenvalue multipliers, and post-hoc
  calibration are forbidden.
- Factor damping or iteration count may control numerical convergence only;
  neither may be tuned to a target eigenvalue.

## Recorded result and withdrawal

- OpenMC: `k_eff = 1.11231121 +/- 0.00058879`.
- Converter reaction-rate balance: `1.11227626`, delta `-3.49 pcm`
  (`-0.059 sigma`).
- Native SPH: 70 iterations; final RMS factor update `9.45e-7`.
- DONJON SPN: `k_eff = 1.11159539`, delta `-71.58 pcm`
  (`-1.216 sigma`).
- Global net-loss residual: `0.0612%`; physical flux RMS residual: `0.656%`.
- Historical decision: `native_sph_physics_passed` (invalidated by the stricter
  final-solver audit).

The current `openmc2donjon validate-native-sph` contract hard-fails the raw
nonconvergence marker and requires a provable one-speed solver path. This
record is negative evidence only; it accepts neither the PNL/EXT colorset nor
the five-component library or 91-position full core.

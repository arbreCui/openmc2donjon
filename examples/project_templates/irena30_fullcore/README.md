# IRENA-30 strict full-core candidate

This project template deliberately starts on **HOLD**. It is not an accepted
IRENA result and it does not reuse the withdrawn five-material/colorset core
mapping.

The manifest declares the expected native-SPH deck at
`fullcore/irena30_orbit_fullcore_native_sph.x2m` with `fullcore/` as its
working directory. The template does not ship that generated deck or any
solver result. Those missing files are intentional: opening this template may
prefill and attempt to load the declared path, but it remains on HOLD until a
real run and the independent machine validator supply matching live evidence.

The fine reference always contains all 91 physical positions. The coarse
domain contract may use either:

- 91 independent position domains; or
- 21 exact D3 symmetry orbits pooled while OpenMC transport tallies are being
  accumulated.

Cross sections must not be averaged between positions after transport. Final
acceptance requires the hash-linked Converter reference, native DRAGON SPH and
final transport convergence, finite-domain leakage balance, and the 91-position
power comparison. The project ledger cannot close this gate by itself: the
manifest binds acceptance to the file-backed `fullcore_validation.json` through
the `irena30-orbit-fullcore-v1` machine-validator contract, which rechecks all
declared input hashes against the live project files.

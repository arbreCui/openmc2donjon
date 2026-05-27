# Production Preset

The production preset turns converter preflight checks into a handoff contract
for real OpenMC-to-DONJON work. It is meant for files that will be consumed as
physics inputs, not for early format debugging.

## MGXS Input Preflight

`openmc2donjon check --production` enables these requirements:

| Check | Level | Purpose |
| --- | --- | --- |
| Declared mixture order | hard fail | Prevent DONJON mixture-index drift. |
| Domain provenance metadata | hard fail | Make each mixture traceable to its OpenMC source domain. |
| Positive volumes | hard fail | Avoid silently using default volume `1.0`. |
| Explicit `transport_total` | hard fail | Make the diffusion/SPN transport correction explicit. |
| Fissionable H-FACTOR | hard fail | Keep power normalization data visible. |
| Local energy bounds consistency | hard fail | Prevent state or mixture group-structure drift. |
| Known energy mesh | warning by default; optional hard fail | Identify standard group structures and flag custom/unknown bounds in the audit trail. |
| Scatter row balance | hard fail | Catch wrong scatter orientation or inconsistent reactions. |
| CHI normalization | hard fail | Ensure fission spectra are usable probability vectors. |
| ADF face consistency | hard fail when ADF exists | Prevent mixed face naming across calculations. |
| Transport/P1 consistency | hard fail when both are present | Catch inconsistent explicit and derived transport data. |
| NU ratio | warning | Flag suspicious `nu_fission / fission` values without rejecting valid fuel variations. |
| MGXS statistical uncertainty coverage | warning by default; optional hard fail | Keep OpenMC MGXS tally noise visible in the audit trail. |

## OpenMC-Side SPH Evidence

Production SPH is expected to be generated upstream from an OpenMC CE
reference and an OpenMC MG macro calculation using the same geometry. The
converter accepts the resulting SPH/NSPH factors as explicit sidecar data and
checks that the corrected HDF5 handoff is self-consistent before writing
DONJON-facing ASCII.

For SPH handoffs, production review should record:

- the OpenMC CE reference case and the OpenMC MG macro case, with its selected
  group structure, used to derive the factors;
- the homogenized output regions/media, because SPH is one factor per output
  region and energy group;
- the angular treatment used in the MG macro calculation, such as Legendre
  `P1/P2/P3` or OpenMC histogram angular representation `Hn`;
- whether the SPH factors were applied to cross sections upstream or carried as
  explicit `NSPH` data in the handoff;
- the same MGXS preflight checks listed above.

A single isolated assembly generally does not need SPH. Colorsets and
full-core macro models do, because the downstream deterministic problem has
multiple homogenized output regions/media.

Statistical uncertainty coverage has an opt-in shape, with two separate
inputs:

- MGXS `*_std_dev` datasets describe uncertainty on the exported cross-section
  means. Production preflight reports missing coverage as audit information by
  default; use `--require-std-dev-coverage` or
  `acceptance.require_mgxs_std_dev_coverage = true` when the workflow policy
  requires OpenMC tally uncertainty to be present for every eligible MGXS field.
- The OpenMC CE reference flux used for SPH may carry a sibling
  `openmc_volume_flux_std_dev` (or `<reference_dataset>_std_dev`) dataset. Use
  workflow-specific checks when the SPH derivation must prove reference-flux
  uncertainty coverage, and use a relative uncertainty ceiling when the case
  policy needs one.

## What This Preset Does Not Prove

Passing the production preset means the handoff is internally consistent and
auditable. It does not prove that the OpenMC model is a validated benchmark,
that the homogenization choice is physically optimal, or that the DONJON
solver method is bias-free. Those remain case-level validation tasks.

For the numerical defaults, see
[Production Thresholds](PRODUCTION_THRESHOLDS.md).

# Production Thresholds

This page records the default numerical gates used by the production
preflight and OpenMC-side SPH handoff paths. The defaults are intentionally
conservative: they catch common handoff mistakes without pretending that
Monte Carlo tallies are exact.

## Hard Gates

| Gate | Default | Meaning |
| --- | ---: | --- |
| Scatter row balance | `5.0e-2` relative | Max residual of `total - absorption - sum(P0 scatter out)` divided by `total`. |
| CHI normalization | `1.0e-6` absolute | Max `abs(sum(chi) - 1)` for fissionable calculations. |
| Transport/P1 consistency | `5.0e-2` relative | Max residual between explicit `transport_total` and `total - sum(P1 scatter out)`. |
| Local energy bounds | exact shape + `rtol=1.0e-10` | Any local mixture/state `energy_bounds` must match root `/energy_bounds`. |
| MGXS uncertainty coverage | off by default; exact coverage when required | If `--require-std-dev-coverage` or the workflow promotes coverage to a hard gate, every eligible mean MGXS dataset must have a matching `*_std_dev` dataset. |
| CE/MG flux uncertainty coverage | off by default; exact coverage when required | If the OpenMC-side SPH workflow promotes coverage to a hard gate, the CE reference flux and/or OpenMC MG macro flux dataset must have a matching `<dataset>_std_dev` dataset. |
| CE/MG flux uncertainty ceiling | off by default; caller-defined relative limit | If the case policy sets a ceiling, max `std_dev / |mean|` for the OpenMC CE reference flux and/or OpenMC MG macro flux must not exceed that value. |

Scatter row balance and transport/P1 use `5.0e-2` because these checks are
meant to catch wrong axes, transposed scatter matrices, and mismatched
transport definitions, not to reject ordinary low-statistics Monte Carlo
noise. A bad axis convention usually produces errors far above this level.

CHI uses `1.0e-6` because a fission spectrum is a normalized probability
vector. Non-finite values and negative entries are always errors for
fissionable calculations.

Energy bounds consistency uses a much tighter tolerance because the values
are group-edge metadata, not tally estimates. A state-specific edge mismatch
means the cross sections are not on the same group structure.

## OpenMC-Side SPH Factors

There is no default SPH convergence tolerance in the converter because the
production SPH iteration now belongs upstream to OpenMC CE/MG equivalence. The
converter expects an explicit table or sidecar of final factors:

- one SPH factor per homogenized output region and energy group;
- positive finite values;
- mixture/order metadata matching the MGXS HDF5 handoff;
- provenance identifying the OpenMC CE reference and OpenMC MG macro case.

Strict iterative tolerances such as `1.0e-12` may appear in archived legacy
fixtures because they record a specific test run. They are not a recommended
production default for the converter.

## Warning Gates

| Gate | Default | Meaning |
| --- | ---: | --- |
| NU ratio | `[2.0, 3.5]` | Warn if `nu_fission / fission` falls outside this interval for fissionable bins with `fission > 1.0e-30`. |
| Unknown energy mesh | production warning by default | Warn when `/energy_bounds` does not match a bundled known mesh in production preflight/SPH audit, unless the caller explicitly requires a known mesh. |
| Missing uncertainty datasets | warning by default | Warn when `*_std_dev` datasets are absent or incomplete, unless the caller promotes coverage to a hard gate. |

NU ratio is warning-only because valid values depend on isotope mix, burnup,
and spectrum. The range is still useful for catching swapped datasets or
accidental unit/normalization errors.

Uncertainty coverage is not required by the production preset because older
fixtures and external HDF5 files may not carry OpenMC tally standard
deviations. Production workflows that rely on Monte Carlo statistics should
turn it into hard gates explicitly:

- `--require-std-dev-coverage` for MGXS preflight;
- workflow-specific hard gates for OpenMC-side SPH MGXS coverage;
- `--require-reference-flux-std-dev` / `--max-reference-flux-std-dev-rel`
  for the OpenMC CE reference flux used by `make-openmc-sph-sidecar`;
- `--require-mg-flux-std-dev` / `--max-mg-flux-std-dev-rel` for the
  OpenMC MG macro flux used by `make-openmc-sph-sidecar`;
- a relative uncertainty ceiling when the reference flux also needs one.

## Override Policy

Command-line preflight options and workflow-specific OpenMC-side SPH checks can
tighten or relax these defaults. Production runs should record the effective
thresholds in the JSON summary or audit payload so that downstream reviewers
know what was accepted.

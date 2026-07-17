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
| Fission-source support | exact | `fission` and `nu_fission` must be positive in the same energy groups. |
| Transport/P1 consistency | `5.0e-2` relative | Max residual between explicit `transport_total` and the flux-weighted incoming-to-outgoing P1 identity. Requires a positive, mixture-bound `/openmc_volume_flux`; otherwise the diagnostic is reported as skipped. |
| Local energy bounds | exact shape + `rtol=1.0e-10` | Any local mixture/state `energy_bounds` must match root `/energy_bounds`. |
| MGXS uncertainty coverage | exact in production | Every eligible mean MGXS dataset must have a matching `*_std_dev` dataset. Engineering checks may leave this optional. |
| Production-critical MGXS uncertainty | `1.0e-1` relative policy ceiling | Gate available one-dimensional MGXS vectors and P0 scatter. This is an auditable statistical-quality policy, not a correction factor or universal physical constant. |
| CE/MG flux uncertainty coverage | off by default; exact coverage when required | If the OpenMC-side SPH workflow promotes coverage to a hard gate, the CE reference flux and/or OpenMC MG macro flux dataset must have a matching `<dataset>_std_dev` dataset. |
| CE/MG flux uncertainty ceiling | off by default; caller-defined relative limit | If the case policy sets a ceiling, max `std_dev / |mean|` for the OpenMC CE reference flux and/or OpenMC MG macro flux must not exceed that value. |

Scatter row balance and transport/P1 use `5.0e-2` because these checks are
meant to catch wrong axes, transposed scatter matrices, and mismatched
transport definitions, not to reject ordinary low-statistics Monte Carlo
noise. The P1 check uses
`sum_g_in(flux[g_in] * P1[g_in -> g_out]) / flux[g_out]`; a bare P1 row sum is
not OpenMC's `TransportXS` definition. A bad axis convention usually produces
errors far above this level.

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

## Diagnostics and Warning Gates

| Gate | Default | Meaning |
| --- | ---: | --- |
| Effective neutron yield | no built-in range | Record observed `nu_fission / fission` extrema wherever both vectors are positive. Their positive group support must match; any magnitude range must be explicitly supplied by a model-specific workflow. |
| All-data MGXS uncertainty | warn at `5.0e-2`; no default hard gate | Report the maximum relative sigma across every available dataset, including signed P1+ moments. `--uncertainty-fail` adds a declared all-data hard criterion. |
| Unknown energy mesh | production warning by default | Warn when `/energy_bounds` does not match a bundled known mesh in production preflight/SPH audit, unless the caller explicitly requires a known mesh. |
| Missing uncertainty datasets | hard fail in production; warning/optional in engineering | Production requires complete matching `*_std_dev` coverage; engineering checks retain configurable coverage policy. |

`nu_fission / fission` is the group-wise effective neutron yield. Its valid
magnitude depends on isotope mix, burnup, and incident energy, so a universal
range would be an empirical assumption. Converter instead hard-fails unequal
positive support between the two reaction vectors and records finite positive
ratios as diagnostics. A workflow may add a declared, reference-specific range
when that range is part of its documented physics model.

Older fixtures and external HDF5 files may not carry OpenMC tally standard
deviations. Such files remain usable for engineering inspection, but the
Converter production preset requires complete MGXS `*_std_dev` coverage.

The production-critical mask is structural: all one-dimensional MGXS fields
and P0 scatter are included. P1 and higher Legendre moments remain in coverage,
the all-data maximum, warnings, and top findings, but they are not subjected to
the default hard relative-sigma gate. Signed high-order coefficients can cross
zero, making a universal relative-error ceiling physically meaningless. If the
scatter moment axis cannot be established unambiguously, validation fails
closed by treating the entire scatter dataset as production-critical.

OpenMC-side SPH workflows may additionally require:

- `--require-reference-flux-std-dev` / `--max-reference-flux-std-dev-rel`
  for the OpenMC CE reference flux used by `make-openmc-sph-sidecar`;
- `--require-mg-flux-std-dev` / `--max-mg-flux-std-dev-rel` for the
  OpenMC MG macro flux used by `make-openmc-sph-sidecar`;
- a relative uncertainty ceiling when the reference flux also needs one.

## Override Policy

Command-line preflight options and workflow-specific OpenMC-side SPH checks can
tighten the canonical production-critical limits or declare an additional
all-data uncertainty criterion. Production runs record the effective thresholds
in the JSON summary or audit payload so downstream reviewers know what was
accepted.

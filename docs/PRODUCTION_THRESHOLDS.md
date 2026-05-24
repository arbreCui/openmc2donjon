# Production Thresholds

This page records the default numerical gates used by the production
preflight and SPH-loop acceptance paths. The defaults are intentionally
conservative: they catch common handoff mistakes without pretending that
Monte Carlo tallies are exact.

## Hard Gates

| Gate | Default | Meaning |
| --- | ---: | --- |
| Scatter row balance | `5.0e-2` relative | Max residual of `total - absorption - sum(P0 scatter out)` divided by `total`. |
| CHI normalization | `1.0e-6` absolute | Max `abs(sum(chi) - 1)` for fissionable calculations. |
| Transport/P1 consistency | `5.0e-2` relative | Max residual between explicit `transport_total` and `total - sum(P1 scatter out)`. |
| Local energy bounds | exact shape + `rtol=1.0e-10` | Any local mixture/state `energy_bounds` must match root `/energy_bounds`. |
| MGXS uncertainty coverage | off by default; exact coverage when required | If `--require-std-dev-coverage` or `acceptance.require_mgxs_std_dev_coverage` is set, every eligible mean MGXS dataset must have a matching `*_std_dev` dataset. |
| Reference-flux uncertainty coverage | off by default; exact coverage when required | If `acceptance.require_reference_flux_std_dev` is set, the OpenMC reference flux used by the SPH loop must have a matching `<dataset>_std_dev` dataset. |
| Reference-flux uncertainty ceiling | off by default; caller-defined relative limit | If `acceptance.max_reference_flux_std_dev_rel` is set, max `std_dev / |mean|` for the OpenMC reference flux must not exceed that value. |

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

## SPH Loop Convergence Targets

There is no default SPH convergence tolerance. A loop only enables numerical
early stopping when the config provides one or both of:

| Target | Default | Meaning |
| --- | ---: | --- |
| `convergence.flux_ratio_tolerance` | disabled | Stop once `max |low-order flux / OpenMC reference flux - 1|` is at or below this target. |
| `convergence.sph_change_tolerance` | disabled | Stop once `max |NSPH(new) / NSPH(old) - 1|` is at or below this target. |
| `convergence.fail_on_nonconvergence` | `false` | If `true`, a loop that hits the iteration limit before satisfying enabled targets fails the CLI command after writing its summary/audit artifacts. |

Strict values such as `1.0e-12` may appear in archived fixtures because they
record a specific test run. They are not a recommended production default.
Choose tolerances from the low-order method, tally uncertainty, and the
intended handoff use case.

The production acceptance preset does not automatically turn these numerical
targets into acceptance failures. Use `convergence.fail_on_nonconvergence =
true` to make nonconvergence fail the CLI command, or set
`acceptance.require_converged = true` / residual acceptance limits when the
summary itself must fail on nonconvergence.

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
- `acceptance.require_mgxs_std_dev_coverage = true` for SPH-loop MGXS
  coverage;
- `acceptance.require_reference_flux_std_dev = true` for the SPH OpenMC
  reference flux;
- `acceptance.max_reference_flux_std_dev_rel = <limit>` when the reference flux
  also needs a relative uncertainty ceiling.

## Override Policy

Command-line preflight options and SPH acceptance config keys can tighten or
relax these defaults. Production runs should record the effective thresholds
in the JSON summary or audit payload so that downstream reviewers know what
was accepted.

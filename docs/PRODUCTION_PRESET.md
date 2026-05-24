# Production Preset

The production preset turns the converter preflight and SPH-loop acceptance
checks into a handoff contract for real OpenMC-to-DONJON work. It is meant for
files that will be consumed as physics inputs, not for early format debugging.

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
| Scatter row balance | hard fail | Catch wrong scatter orientation or inconsistent reactions. |
| CHI normalization | hard fail | Ensure fission spectra are usable probability vectors. |
| ADF face consistency | hard fail when ADF exists | Prevent mixed face naming across calculations. |
| Transport/P1 consistency | hard fail when both are present | Catch inconsistent explicit and derived transport data. |
| NU ratio | warning | Flag suspicious `nu_fission / fission` values without rejecting valid fuel variations. |
| Statistical uncertainty coverage | warning or production fail if configured | Keep OpenMC tally noise visible in the audit trail. |

## SPH Loop Acceptance

The SPH-loop production preset adds the same MGXS physics gates to the
fixed-OpenMC SPH workflow. The loop still iterates only SPH/NSPH factors; the
base OpenMC cross sections remain fixed.

Production acceptance requires:

- artifact metadata alignment between reference flux, DONJON volume flux, and
  SPH sidecars;
- final solve completion;
- explicit MGXS volumes and fissionable H-FACTOR data;
- root energy bounds plus local mixture/state energy-bounds consistency;
- scatter row-balance, CHI, ADF-face, and transport/P1 consistency;
- final-to-initial flux residual ratio no worse than `1.0`;
- final clipped SPH fraction/count within configured limits;
- convergence checks only when explicitly requested in `acceptance`
  (`require_converged`, `max_sph_rel_change`, or
  `max_flux_ratio_residual`).

## SPH Convergence Versus Acceptance

SPH-loop convergence targets and production acceptance gates answer different
questions:

- `convergence.flux_ratio_tolerance` and
  `convergence.sph_change_tolerance` are numerical stopping targets for the
  iterative loop.
- `acceptance` checks decide whether the recorded handoff is usable as a
  production artifact.
- `convergence.fail_on_nonconvergence` controls whether a run that reaches the
  iteration limit without satisfying the convergence target should fail the CLI
  command.

Convergence targets are opt-in. If no `convergence.*_tolerance` values are set,
the loop runs the requested iteration count and reports `convergence_enabled =
false`. When targets are enabled, `fail_on_nonconvergence = false` means the
summary can still be written and accepted by production gates even if the
numeric stopping target was not reached; set it to `true` when nonconvergence
should make the CLI command fail.

The production preset deliberately does not copy convergence targets into
acceptance gates. If a case policy wants both a production handoff audit and a
hard convergence acceptance check, set the convergence policy explicitly, for
example:

```json
{
  "convergence": {
    "flux_ratio_tolerance": 1.0e-4,
    "sph_change_tolerance": 1.0e-4,
    "fail_on_nonconvergence": true
  },
  "acceptance": {
    "preset": "production",
    "require_converged": true
  }
}
```

A summary can therefore show `acceptance.passed = true` while `converged =
false`. In that case the handoff passed the configured production gates, but
the SPH iteration did not reach its numerical convergence target before the
configured stop condition.

## What This Preset Does Not Prove

Passing the production preset means the handoff is internally consistent and
auditable. It does not prove that the OpenMC model is a validated benchmark,
that the homogenization choice is physically optimal, or that the DONJON
solver method is bias-free. Those remain case-level validation tasks.

For the numerical defaults, see
[Production Thresholds](PRODUCTION_THRESHOLDS.md).

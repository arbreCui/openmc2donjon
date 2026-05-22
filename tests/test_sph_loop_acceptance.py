from __future__ import annotations

from types import SimpleNamespace
import unittest

from openmc2donjon.sph_loop_acceptance import (
    ACCEPTANCE_FAIL_DECISION,
    ACCEPTANCE_PASS_DECISION,
    build_acceptance_report,
)


class SphLoopAcceptanceTests(unittest.TestCase):
    def test_builds_acceptance_metrics_from_audit_and_convergence(self) -> None:
        report = build_acceptance_report(
            {
                "min_completed_iterations": 2,
                "require_final_solve": True,
                "require_converged": True,
                "max_sph_rel_change": 0.2,
                "max_flux_ratio_residual": 0.3,
                "sph_minimum_floor": 0.9,
                "sph_maximum_ceiling": 1.2,
                "max_keff_step_pcm": 250.0,
                "max_final_keff_delta_pcm": 60.0,
                "fail_on_violation": True,
            },
            audit_rows=(
                _row("iteration", keff=1.0, sph_minimum=0.95, sph_maximum=1.1),
                _row("iteration", keff=1.002, sph_minimum=0.96, sph_maximum=1.05),
                _row("final", keff=1.0025),
            ),
            convergence=(
                SimpleNamespace(
                    sph_max_abs_change=0.02,
                    sph_max_rel_change=0.1,
                    flux_ratio_max_residual=0.2,
                ),
            ),
            completed_iterations=2,
            converged=True,
            final_solve=object(),
        )

        self.assertTrue(report.enabled)
        self.assertTrue(report.passed)
        self.assertTrue(report.fail_on_violation)
        self.assertEqual(report.decision, ACCEPTANCE_PASS_DECISION)
        actual = {check.name: check.actual for check in report.checks}
        self.assertAlmostEqual(float(actual["max_keff_step_pcm"]), 200.0)
        self.assertAlmostEqual(
            float(actual["max_final_keff_delta_pcm"]),
            abs(1.0025 - 1.002) / 1.002 * 1.0e5,
        )

    def test_missing_convergence_metric_fails_threshold_check(self) -> None:
        report = build_acceptance_report(
            {"max_sph_rel_change": 0.01},
            audit_rows=(),
            convergence=(),
            completed_iterations=0,
            converged=False,
            final_solve=None,
        )

        self.assertTrue(report.enabled)
        self.assertFalse(report.passed)
        self.assertEqual(report.decision, ACCEPTANCE_FAIL_DECISION)
        self.assertEqual(report.checks[0].actual, None)
        self.assertIn("metric unavailable", report.checks[0].message)

    def test_empty_acceptance_config_is_disabled_and_passes(self) -> None:
        report = build_acceptance_report(
            {},
            audit_rows=(),
            convergence=(),
            completed_iterations=0,
            converged=False,
            final_solve=None,
        )

        self.assertFalse(report.enabled)
        self.assertTrue(report.passed)
        self.assertEqual(report.decision, ACCEPTANCE_PASS_DECISION)
        self.assertEqual(report.checks, ())


def _row(
    stage: str,
    *,
    keff: float | None = None,
    sph_minimum: float | None = None,
    sph_maximum: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        stage=stage,
        keff=keff,
        sph_minimum=sph_minimum,
        sph_maximum=sph_maximum,
    )


if __name__ == "__main__":
    unittest.main()

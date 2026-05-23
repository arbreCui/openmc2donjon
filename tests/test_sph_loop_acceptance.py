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
                    clipped_count=0,
                    clipped_fraction=0.0,
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

    def test_builds_flux_improvement_and_clipping_acceptance_metrics(self) -> None:
        report = build_acceptance_report(
            {
                "max_final_to_initial_flux_residual_ratio": 0.5,
                "max_final_clipped_fraction": 0.25,
                "max_final_clipped_count": 1,
            },
            audit_rows=(),
            convergence=(
                SimpleNamespace(
                    sph_max_abs_change=1.0,
                    sph_max_rel_change=1.0,
                    flux_ratio_max_residual=10.0,
                    clipped_count=2,
                    clipped_fraction=0.5,
                ),
                SimpleNamespace(
                    sph_max_abs_change=0.1,
                    sph_max_rel_change=0.1,
                    flux_ratio_max_residual=2.0,
                    clipped_count=1,
                    clipped_fraction=0.25,
                ),
            ),
            completed_iterations=2,
            converged=False,
            final_solve=None,
        )

        self.assertTrue(report.passed)
        actual = {check.name: check.actual for check in report.checks}
        self.assertAlmostEqual(
            float(actual["max_final_to_initial_flux_residual_ratio"]),
            0.2,
        )
        self.assertEqual(actual["max_final_clipped_count"], 1)
        self.assertEqual(actual["max_final_clipped_fraction"], 0.25)

    def test_builds_artifact_metadata_alignment_gate(self) -> None:
        report = build_acceptance_report(
            {"require_artifact_metadata_alignment": True},
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            artifact_metadata=SimpleNamespace(
                reference_flux=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                ),
                workflows=(
                    SimpleNamespace(
                        iteration=1,
                        donjon_volume_flux=_metadata(
                            "mgxs_donjon",
                            ("fuel", "moderator"),
                        ),
                        sph_sidecar=_metadata(
                            "mgxs_donjon",
                            ("fuel", "moderator"),
                        ),
                    ),
                ),
                final_sph_sidecar=_metadata("mgxs_donjon", ("fuel", "moderator")),
            ),
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.checks[0].name, "require_artifact_metadata_alignment")

    def test_artifact_metadata_alignment_gate_reports_mismatch(self) -> None:
        report = build_acceptance_report(
            {"require_artifact_metadata_alignment": True},
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            artifact_metadata=SimpleNamespace(
                reference_flux=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                ),
                workflows=(
                    SimpleNamespace(
                        iteration=1,
                        donjon_volume_flux=_metadata(
                            "ascending_energy",
                            ("fuel", "moderator"),
                        ),
                        sph_sidecar=_metadata(
                            "mgxs_donjon",
                            ("moderator", "fuel"),
                        ),
                    ),
                ),
                final_sph_sidecar=None,
            ),
        )

        self.assertFalse(report.passed)
        check = report.checks[0]
        self.assertFalse(check.actual)
        self.assertIn("donjon_volume_flux group_order", check.message)
        self.assertIn("sph_sidecar mixture_names", check.message)

    def test_builds_production_audit_gate(self) -> None:
        report = build_acceptance_report(
            {"require_production_audit": True},
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(),
            artifact_metadata=SimpleNamespace(
                reference_flux=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                    energy_groups=2,
                ),
                workflows=(
                    SimpleNamespace(
                        iteration=1,
                        donjon_volume_flux=_metadata(
                            "mgxs_donjon",
                            ("fuel", "moderator"),
                            energy_groups=2,
                        ),
                        sph_sidecar=_metadata(
                            "mgxs_donjon",
                            ("fuel", "moderator"),
                            energy_groups=2,
                        ),
                    ),
                ),
                final_sph_sidecar=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                    energy_groups=2,
                ),
            ),
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.checks[0].name, "require_production_audit")

    def test_mgxs_explicit_volume_acceptance_gate(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_explicit_volumes": True,
                "max_mgxs_default_volume_count": 0,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(volume_defaulted=0),
        )

        self.assertTrue(report.passed)
        actual = {check.name: check.actual for check in report.checks}
        self.assertTrue(actual["require_mgxs_explicit_volumes"])
        self.assertEqual(actual["max_mgxs_default_volume_count"], 0)

    def test_mgxs_explicit_volume_gate_fails_on_defaulted_volume(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_explicit_volumes": True,
                "max_mgxs_default_volume_count": 0,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(volume_defaulted=1),
        )

        self.assertFalse(report.passed)
        checks = {check.name: check for check in report.checks}
        self.assertFalse(checks["require_mgxs_explicit_volumes"].passed)
        self.assertFalse(checks["max_mgxs_default_volume_count"].passed)

    def test_production_audit_gate_reports_mismatch(self) -> None:
        report = build_acceptance_report(
            {"require_production_audit": True},
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(),
            artifact_metadata=SimpleNamespace(
                reference_flux=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                    energy_groups=2,
                ),
                workflows=(
                    SimpleNamespace(
                        iteration=1,
                        donjon_volume_flux=_metadata(
                            "mgxs_donjon",
                            ("fuel", "moderator"),
                            energy_groups=3,
                        ),
                        sph_sidecar=_metadata(
                            "ascending_energy",
                            ("fuel", "moderator"),
                            energy_groups=2,
                        ),
                    ),
                ),
                final_sph_sidecar=None,
            ),
        )

        self.assertFalse(report.passed)
        check = report.checks[0]
        self.assertFalse(check.actual)
        self.assertIn("donjon_volume_flux energy_groups", check.message)
        self.assertIn("sph_sidecar group_order", check.message)

    def test_reference_flux_uncertainty_acceptance_gate(self) -> None:
        artifact_metadata = SimpleNamespace(
            reference_flux=_metadata(
                "mgxs_donjon",
                ("fuel", "moderator"),
                std_dev_dataset="openmc_volume_flux_std_dev",
                std_dev_max_rel=0.012,
            ),
            workflows=(),
            final_sph_sidecar=None,
        )

        report = build_acceptance_report(
            {
                "require_reference_flux_std_dev": True,
                "max_reference_flux_std_dev_rel": 0.02,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            artifact_metadata=artifact_metadata,
        )

        self.assertTrue(report.passed)
        actual = {check.name: check.actual for check in report.checks}
        self.assertTrue(actual["require_reference_flux_std_dev"])
        self.assertAlmostEqual(
            float(actual["max_reference_flux_std_dev_rel"]),
            0.012,
        )

    def test_reference_flux_uncertainty_gate_fails_when_missing_or_too_large(self) -> None:
        report = build_acceptance_report(
            {
                "require_reference_flux_std_dev": True,
                "max_reference_flux_std_dev_rel": 0.02,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            artifact_metadata=SimpleNamespace(
                reference_flux=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                    std_dev_max_rel=0.05,
                ),
                workflows=(),
                final_sph_sidecar=None,
            ),
        )

        self.assertFalse(report.passed)
        checks = {check.name: check for check in report.checks}
        self.assertFalse(checks["require_reference_flux_std_dev"].passed)
        self.assertFalse(checks["max_reference_flux_std_dev_rel"].passed)

    def test_reference_flux_uncertainty_presence_gate_can_be_disabled(self) -> None:
        report = build_acceptance_report(
            {"require_reference_flux_std_dev": False},
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            artifact_metadata=SimpleNamespace(
                reference_flux=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                    std_dev_dataset="openmc_volume_flux_std_dev",
                ),
                workflows=(),
                final_sph_sidecar=None,
            ),
        )

        self.assertFalse(report.enabled)
        self.assertEqual(report.checks, ())

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


def _metadata(
    group_order: str,
    mixture_names: tuple[str, ...],
    *,
    energy_groups: int = 2,
    std_dev_dataset: str | None = None,
    std_dev_max_rel: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        source="test.h5::dataset",
        group_order=group_order,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        std_dev_dataset=std_dev_dataset,
        std_dev_max_rel=std_dev_max_rel,
    )


def _preflight(*, volume_defaulted: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        passed=True,
        map_kind="scalar_flux_map",
        mixture_names=("fuel", "moderator"),
        energy_groups=2,
        mgxs_declared_mixture_order=True,
        mgxs_source_domain_indices=(1, 2),
        mgxs_source_domain_order_errors=(),
        mgxs_volume_defaulted=volume_defaulted,
        mgxs_volume_nonpositive=0,
        scalar_flux_ids=(2, 4),
        minimum_required_flux_unknown_count=4,
        mixture_flux_map=(("fuel", 2), ("moderator", 4)),
    )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from types import SimpleNamespace
import unittest

from openmc2donjon.sph_loop_acceptance import (
    ACCEPTANCE_FAIL_DECISION,
    ACCEPTANCE_PASS_DECISION,
    build_acceptance_report,
)
from openmc2donjon.sph_loop_production_audit import build_production_audit_payload


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

    def test_production_audit_payload_includes_nu_ratio_warning_count(self) -> None:
        payload = build_production_audit_payload(
            flux_map_preflight=_preflight(nu_ratio_warning_count=1),
            artifact_metadata=SimpleNamespace(
                reference_flux=_metadata(
                    "mgxs_donjon",
                    ("fuel", "moderator"),
                    energy_groups=2,
                ),
                workflows=(),
                final_sph_sidecar=None,
            ),
            solve_count=0,
            postprocess_count=0,
        )

        self.assertEqual(
            payload["flux_map"]["mgxs_nu_ratio_warning_count"],
            1,
        )

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

    def test_mgxs_h_factor_acceptance_gate(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_h_factor": True,
                "max_mgxs_missing_h_factor_count": 0,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(h_factor_missing=0),
        )

        self.assertTrue(report.passed)
        actual = {check.name: check.actual for check in report.checks}
        self.assertTrue(actual["require_mgxs_h_factor"])
        self.assertEqual(actual["max_mgxs_missing_h_factor_count"], 0)

    def test_mgxs_h_factor_gate_fails_on_missing_or_invalid_data(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_h_factor": True,
                "max_mgxs_missing_h_factor_count": 0,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(
                h_factor_missing=1,
                h_factor_invalid=1,
            ),
        )

        self.assertFalse(report.passed)
        checks = {check.name: check for check in report.checks}
        self.assertFalse(checks["require_mgxs_h_factor"].passed)
        self.assertFalse(checks["max_mgxs_missing_h_factor_count"].passed)

    def test_mgxs_energy_bounds_acceptance_gate(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_energy_bounds": True,
                "require_known_mesh": True,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(energy_mesh_id="casmo_2"),
        )

        self.assertTrue(report.passed)
        actual = {check.name: check.actual for check in report.checks}
        self.assertTrue(actual["require_mgxs_energy_bounds"])
        self.assertTrue(actual["require_known_mesh"])

    def test_mgxs_energy_bounds_gate_fails_on_missing_or_unknown_mesh(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_energy_bounds": True,
                "require_known_mesh": True,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(
                energy_bounds_present=False,
                energy_mesh_id=None,
            ),
        )

        self.assertFalse(report.passed)
        checks = {check.name: check for check in report.checks}
        self.assertFalse(checks["require_mgxs_energy_bounds"].passed)
        self.assertFalse(checks["require_known_mesh"].passed)

    def test_mgxs_physics_acceptance_gates(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_energy_bounds_consistency": True,
                "max_mgxs_scatter_row_balance_rel": 5.0e-2,
                "max_mgxs_chi_sum_error": 1.0e-6,
                "require_mgxs_adf_face_consistency": True,
                "max_mgxs_transport_p1_rel": 5.0e-2,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(
                energy_bounds_consistency_errors=0,
                scatter_row_balance_rel=1.0e-3,
                chi_sum_error=5.0e-8,
                adf_face_errors=0,
                transport_p1_rel=2.0e-3,
            ),
        )

        self.assertTrue(report.passed)
        actual = {check.name: check.actual for check in report.checks}
        self.assertTrue(actual["require_mgxs_energy_bounds_consistency"])
        self.assertAlmostEqual(
            float(actual["max_mgxs_scatter_row_balance_rel"]),
            1.0e-3,
        )
        self.assertAlmostEqual(float(actual["max_mgxs_chi_sum_error"]), 5.0e-8)
        self.assertTrue(actual["require_mgxs_adf_face_consistency"])
        self.assertAlmostEqual(float(actual["max_mgxs_transport_p1_rel"]), 2.0e-3)

    def test_mgxs_physics_acceptance_gates_fail_on_contract_errors(self) -> None:
        report = build_acceptance_report(
            {
                "require_mgxs_energy_bounds_consistency": True,
                "max_mgxs_scatter_row_balance_rel": 5.0e-2,
                "max_mgxs_chi_sum_error": 1.0e-6,
                "require_mgxs_adf_face_consistency": True,
                "max_mgxs_transport_p1_rel": 5.0e-2,
            },
            audit_rows=(),
            convergence=(),
            completed_iterations=1,
            converged=False,
            final_solve=None,
            flux_map_preflight=_preflight(
                energy_bounds_consistency_errors=1,
                scatter_row_balance_rel=6.0e-2,
                chi_sum_error=2.0e-6,
                chi_errors=1,
                adf_face_errors=1,
                transport_p1_rel=7.0e-2,
                transport_p1_errors=1,
            ),
        )

        self.assertFalse(report.passed)
        checks = {check.name: check for check in report.checks}
        self.assertFalse(checks["require_mgxs_energy_bounds_consistency"].passed)
        self.assertFalse(checks["max_mgxs_scatter_row_balance_rel"].passed)
        self.assertFalse(checks["max_mgxs_chi_sum_error"].passed)
        self.assertFalse(checks["require_mgxs_adf_face_consistency"].passed)
        self.assertFalse(checks["max_mgxs_transport_p1_rel"].passed)

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


def _preflight(
    *,
    volume_defaulted: int = 0,
    h_factor_missing: int = 0,
    h_factor_invalid: int = 0,
    energy_bounds_present: bool = True,
    energy_bounds_error_count: int = 0,
    energy_bounds_consistency_errors: int = 0,
    energy_mesh_id: str | None = None,
    scatter_row_balance_rel: float | None = None,
    chi_sum_error: float | None = None,
    chi_errors: int = 0,
    adf_face_errors: int = 0,
    transport_p1_rel: float | None = None,
    transport_p1_errors: int = 0,
    nu_ratio_warning_count: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        passed=True,
        map_kind="scalar_flux_map",
        mixture_names=("fuel", "moderator"),
        energy_groups=2,
        mgxs_energy_bounds_present=energy_bounds_present,
        mgxs_energy_bounds_error_count=energy_bounds_error_count,
        mgxs_energy_bounds_consistency_error_count=(
            energy_bounds_consistency_errors
        ),
        mgxs_energy_bounds_local_count=0,
        mgxs_energy_mesh_id=energy_mesh_id,
        mgxs_declared_mixture_order=True,
        mgxs_source_domain_indices=(1, 2),
        mgxs_source_domain_order_errors=(),
        mgxs_volume_defaulted=volume_defaulted,
        mgxs_volume_nonpositive=0,
        mgxs_h_factor_missing=h_factor_missing,
        mgxs_h_factor_invalid=h_factor_invalid,
        mgxs_scatter_row_balance_checked=(
            0 if scatter_row_balance_rel is None else 1
        ),
        mgxs_scatter_row_balance_max_rel=scatter_row_balance_rel,
        mgxs_scatter_row_balance_max_abs=None,
        mgxs_scatter_row_balance_worst=None,
        mgxs_chi_checked=0 if chi_sum_error is None else 1,
        mgxs_chi_sum_max_abs_error=chi_sum_error,
        mgxs_chi_sum_worst=None,
        mgxs_chi_error_count=chi_errors,
        mgxs_nu_ratio_checked_bins=0,
        mgxs_nu_ratio_min=None,
        mgxs_nu_ratio_max=None,
        mgxs_nu_ratio_worst=None,
        mgxs_nu_ratio_warning_count=nu_ratio_warning_count,
        mgxs_adf_calculations=0,
        mgxs_adf_faces=(),
        mgxs_adf_face_error_count=adf_face_errors,
        mgxs_transport_p1_checked=0 if transport_p1_rel is None else 1,
        mgxs_transport_p1_max_rel=transport_p1_rel,
        mgxs_transport_p1_max_abs=None,
        mgxs_transport_p1_worst=None,
        mgxs_transport_p1_error_count=transport_p1_errors,
        scalar_flux_ids=(2, 4),
        minimum_required_flux_unknown_count=4,
        mixture_flux_map=(("fuel", 2), ("moderator", 4)),
    )


if __name__ == "__main__":
    unittest.main()

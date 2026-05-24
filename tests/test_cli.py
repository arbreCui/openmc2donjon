from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import build_command_parser, build_parser, main as cli_main
from openmc2donjon.energy_groups import energy_bounds_sha256


class CliTests(unittest.TestCase):
    def test_version_option(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            build_parser().parse_args(["--version"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(stream.getvalue().strip(), "openmc2donjon 0.1.2")

    def test_sph_loop_help_separates_production_and_convergence_policy(self) -> None:
        help_text = _parser_help(["make-donjon-sph-loop-config", "--help"])
        normalized = " ".join(help_text.split())

        self.assertIn(
            "adds MGXS handoff/audit gates and a non-worsening "
            "final flux-residual gate",
            normalized,
        )
        self.assertIn(
            "physics' also turns configured convergence tolerances into "
            "acceptance gates",
            normalized,
        )
        self.assertIn("production preset does not imply this", normalized)
        self.assertIn("independent of the acceptance preset", normalized)

    def test_check_command_accepts_valid_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            write_valid_mgxs(path)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "check",
                        str(path),
                        "--require-volume",
                        "--require-openmc-volume-flux",
                    ]
                )

        self.assertEqual(rc, 0)
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())
        self.assertIn("openmc_volume_flux=present", stream.getvalue())

    def test_check_command_rejects_invalid_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(["check", str(path)])

        self.assertEqual(rc, 1)
        self.assertIn("mgxs_input_contract_failed", stream.getvalue())
        self.assertIn("/energy_bounds dataset is missing", stream.getvalue())

    def test_check_command_can_require_h_factor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            write_valid_mgxs(path)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(["check", str(path), "--require-h-factor"])

        self.assertEqual(rc, 1)
        self.assertIn("mgxs_input_contract_failed", stream.getvalue())
        self.assertIn("H-FACTOR/kappa_fission", stream.getvalue())

    def test_check_command_production_preset_requires_h_factor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            summary = Path(tmpdir) / "summary.json"
            write_valid_mgxs(path)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                missing_rc = cli_main(["check", str(path), "--production"])

            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel"].create_dataset(
                    "kappa_fission",
                    data=np.array([3.2e-12, 3.1e-12]),
                )
                h5["mixtures/fuel/total"][:] = np.array([0.29, 0.38])
                h5["mixtures/fuel/transport_total"][:] = np.array([0.29, 0.38])

            with contextlib.redirect_stdout(io.StringIO()):
                present_rc = cli_main(
                    [
                        "check",
                        str(path),
                        "--production",
                        "--summary-json",
                        str(summary),
                    ]
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertEqual(missing_rc, 1)
        self.assertIn("H-FACTOR/kappa_fission", stream.getvalue())
        self.assertEqual(present_rc, 0)
        self.assertEqual(
            payload["inputs"][0]["scatter_row_balance"]["fail_threshold"],
            5.0e-2,
        )
        self.assertEqual(
            payload["inputs"][0]["physics_checks"]["chi_sum_max_abs_error"],
            0.0,
        )
        self.assertEqual(
            payload["inputs"][0]["uncertainty"]["production_fail_threshold"],
            1.0,
        )
        self.assertTrue(payload["inputs"][0]["declared_mixture_order"])
        self.assertEqual(payload["inputs"][0]["source_domain_indices"], 1)
        self.assertEqual(payload["inputs"][0]["domain_mode"], "unit_test")
        self.assertEqual(payload["inputs"][0]["source_domain_metadata"], 1)
        self.assertTrue(payload["inputs"][0]["openmc_volume_flux"]["present"])

    def test_check_command_can_gate_energy_group_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            bounds_path = Path(tmpdir) / "bounds.txt"
            write_valid_mgxs(path)
            bounds = np.array([1.0e-5, 1.0, 1.0e7])
            np.savetxt(bounds_path, bounds)
            with h5py.File(path, "a") as h5:
                h5.attrs["energy_group_structure"] = "C5G7-2g-test"
                h5.attrs["energy_bounds_sha256"] = energy_bounds_sha256(bounds)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "check",
                        str(path),
                        "--expected-energy-group-structure",
                        "C5G7-2g-test",
                        "--expected-energy-bounds",
                        str(bounds_path),
                        "--expected-energy-bounds-sha256",
                        energy_bounds_sha256(bounds),
                    ]
                )

        self.assertEqual(rc, 0)
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())
        self.assertIn("energy_group_structure=C5G7-2g-test", stream.getvalue())

    def test_doctor_command_reports_environment_and_recipe(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / "doctor_summary.json"

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "doctor",
                        "--recipe",
                        str(recipe),
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            payload = json.loads(summary_path.read_text(encoding="utf-8"))

        output = stream.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("OpenMC-to-DONJON doctor", output)
        self.assertIn("OK   python:", output)
        self.assertIn("OK   numpy:", output)
        self.assertIn("OK   h5py:", output)
        self.assertIn("OK   recipe:", output)
        self.assertIn("WARN recipe-check: mgxs-required:", output)
        self.assertIn("mixtures=2 groups=2 P0", output)
        self.assertEqual(payload["schema"], "openmc2donjon.doctor.v1")
        self.assertEqual(payload["decision"], "openmc2donjon_doctor_passed")
        self.assertTrue(payload["ok"])
        self.assertTrue(
            any(
                check["name"] == "recipe-check"
                and str(check["detail"]).startswith("mgxs-required:")
                for check in payload["checks"]
            )
        )

    def test_inspect_command_reports_hdf5_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = tmp / "mgxs.h5"
            summary_path = tmp / "inspect_summary.json"
            write_valid_mgxs(path)
            with h5py.File(path, "a") as h5:
                fuel = h5["mixtures/fuel"]
                fuel.create_dataset("H-FACTOR", data=np.array([10.0, 20.0]))
                fuel.create_dataset("total_std_dev", data=np.array([0.001, 0.002]))
                adf = fuel.create_group("adf")
                adf.create_dataset("FD_XMIN", data=np.array([1.01, 0.99]))
                adf.create_dataset("FD_XMAX", data=np.array([1.02, 0.98]))

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "inspect",
                        str(path),
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            payload = json.loads(summary_path.read_text(encoding="utf-8"))

        output = stream.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("OpenMC-to-DONJON MGXS inspect", output)
        self.assertIn("mixtures=1 calculations=1 state_points=1", output)
        self.assertIn("transport_total=1/1", output)
        self.assertIn("h_factor=1/1", output)
        self.assertIn("std_dev=1/8", output)
        self.assertIn("adf=1/1 faces=FD_XMAX,FD_XMIN", output)
        self.assertIn("fuel states=1", output)
        self.assertEqual(payload["schema"], "openmc2donjon.mgxs-inspect.v1")
        self.assertEqual(payload["inputs"][0]["mixture_count"], 1)
        self.assertEqual(payload["inputs"][0]["std_dev_datasets"], 1)
        self.assertEqual(payload["inputs"][0]["std_dev_expected_datasets"], 8)
        self.assertEqual(payload["inputs"][0]["mixtures"][0]["name"], "fuel")
        self.assertEqual(payload["inputs"][0]["mixtures"][0]["std_dev_datasets"], 1)
        self.assertEqual(
            payload["inputs"][0]["mixtures"][0]["std_dev_expected_datasets"],
            8,
        )
        self.assertEqual(
            set(payload["inputs"][0]["mixtures"][0]["adf_faces"]),
            {"FD_XMIN", "FD_XMAX"},
        )

    def test_inspect_std_dev_coverage_counts_each_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = tmp / "states_mgxs.h5"
            summary_path = tmp / "inspect_summary.json"
            write_valid_mgxs(path)
            with h5py.File(path, "a") as h5:
                fuel = h5["mixtures/fuel"]
                states = fuel.create_group("states")
                first = states.create_group("00000001")
                second = states.create_group("00000002")
                for dataset in (
                    "total",
                    "absorption",
                    "fission",
                    "nu_fission",
                    "chi",
                    "transport_total",
                    "scatter_matrix",
                ):
                    fuel.copy(dataset, first)
                    fuel.copy(dataset, second)
                    del fuel[dataset]
                first.create_dataset("total_std_dev", data=np.array([0.001, 0.002]))

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "inspect",
                        str(path),
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            payload = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertIn("std_dev=1/14", stream.getvalue())
        self.assertEqual(payload["inputs"][0]["std_dev_datasets"], 1)
        self.assertEqual(payload["inputs"][0]["std_dev_expected_datasets"], 14)
        self.assertEqual(payload["inputs"][0]["mixtures"][0]["std_dev_datasets"], 1)
        self.assertEqual(
            payload["inputs"][0]["mixtures"][0]["std_dev_expected_datasets"],
            14,
        )

    def test_diff_command_accepts_identical_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reference = tmp / "reference.h5"
            candidate = tmp / "candidate.h5"
            summary_path = tmp / "diff_summary.json"
            write_valid_mgxs(reference)
            shutil.copyfile(reference, candidate)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "diff",
                        str(reference),
                        str(candidate),
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            payload = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertIn("mgxs_hdf5_diff_passed", stream.getvalue())
        self.assertEqual(payload["schema"], "openmc2donjon.mgxs-diff.v1")
        self.assertEqual(payload["decision"], "mgxs_hdf5_diff_passed")
        self.assertGreater(payload["compared_datasets"], 0)
        self.assertEqual(payload["max_abs"], 0.0)

    def test_diff_command_reports_numeric_difference_and_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reference = tmp / "reference.h5"
            candidate = tmp / "candidate.h5"
            write_valid_mgxs(reference)
            shutil.copyfile(reference, candidate)
            with h5py.File(candidate, "a") as h5:
                h5["mixtures/fuel/total"][0] = 0.501

            failed_stream = io.StringIO()
            with contextlib.redirect_stdout(failed_stream):
                failed_rc = cli_main(["diff", str(reference), str(candidate)])

            passed_stream = io.StringIO()
            with contextlib.redirect_stdout(passed_stream):
                passed_rc = cli_main(
                    ["diff", str(reference), str(candidate), "--atol", "0.01"]
                )

        self.assertEqual(failed_rc, 1)
        self.assertIn("mgxs_hdf5_diff_failed", failed_stream.getvalue())
        self.assertIn("/mixtures/fuel/total", failed_stream.getvalue())
        self.assertIn("numeric values differ", failed_stream.getvalue())
        self.assertEqual(passed_rc, 0)
        self.assertIn("mgxs_hdf5_diff_passed", passed_stream.getvalue())

    def test_bundle_command_copies_artifacts_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs_library.h5"
            mcompo = tmp / "out.mcompo.txt"
            summary = tmp / "run_summary.json"
            extra = tmp / "notes.txt"
            bundle_dir = tmp / "bundle"
            write_valid_mgxs(mgxs)
            mcompo.write_text("mcompo payload\n", encoding="utf-8")
            summary.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.from-openmc-summary.v2",
                        "decision": "example_passed",
                        "ok": True,
                        "acceptance_enabled": True,
                        "acceptance_passed": True,
                        "acceptance_decision": "example_acceptance_passed",
                    }
                ),
                encoding="utf-8",
            )
            extra.write_text("notes\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "bundle",
                        "--output-dir",
                        str(bundle_dir),
                        "--mgxs",
                        str(mgxs),
                        "--mcompo",
                        str(mcompo),
                        "--run-summary",
                        str(summary),
                        "--extra",
                        f"notes={extra}",
                    ]
                )

            manifest = json.loads(
                (bundle_dir / "manifest.json").read_text(encoding="utf-8")
            )
            validation_summary = tmp / "bundle_validation.json"
            validation_stream = io.StringIO()
            with contextlib.redirect_stdout(validation_stream):
                validation_rc = cli_main(
                    [
                        "validate-bundle",
                        str(bundle_dir / "manifest.json"),
                        "--summary-json",
                        str(validation_summary),
                    ]
                )
            validation_payload = json.loads(validation_summary.read_text(encoding="utf-8"))
            bundled_paths_exist = [
                (bundle_dir / artifact["bundled_path"]).exists()
                for artifact in manifest["artifacts"]
            ]

        self.assertEqual(rc, 0)
        self.assertEqual(validation_rc, 0)
        self.assertIn("OpenMC-to-DONJON bundle", stream.getvalue())
        self.assertIn("openmc2donjon_bundle_validation_passed", validation_stream.getvalue())
        self.assertEqual(manifest["schema"], "openmc2donjon.bundle.v1")
        self.assertEqual(validation_payload["decision"], "openmc2donjon_bundle_validation_passed")
        self.assertTrue(validation_payload["ok"])
        self.assertEqual(manifest["artifact_count"], 4)
        labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
        self.assertEqual(set(labels), {"mgxs", "mcompo", "run-summary", "notes"})
        self.assertEqual(labels["mgxs"]["bundled_path"], "mgxs_library.h5")
        self.assertEqual(
            labels["run-summary"]["summary_schema"],
            "openmc2donjon.from-openmc-summary.v2",
        )
        self.assertEqual(labels["run-summary"]["summary_decision"], "example_passed")
        self.assertTrue(labels["run-summary"]["summary_ok"])
        self.assertTrue(labels["run-summary"]["acceptance_enabled"])
        self.assertTrue(labels["run-summary"]["acceptance_passed"])
        self.assertEqual(
            labels["run-summary"]["acceptance_decision"],
            "example_acceptance_passed",
        )
        for artifact in labels.values():
            self.assertEqual(len(artifact["sha256"]), 64)
        self.assertTrue(all(bundled_paths_exist))

    def test_bundle_command_can_manifest_sources_already_in_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary = tmp / "summary.json"
            summary.write_text(
                json.dumps({"schema": "example.v1", "decision": "passed"}),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "bundle",
                        "--output-dir",
                        str(tmp),
                        "--run-summary",
                        str(summary),
                    ]
                )

            manifest = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
        self.assertEqual(labels["run-summary"]["bundled_path"], "summary.json")
        self.assertEqual(labels["run-summary"]["summary_decision"], "passed")

    def test_validate_bundle_fails_on_failed_summary_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary = tmp / "run_summary.json"
            bundle_dir = tmp / "bundle"
            summary.write_text(
                json.dumps(
                    {
                        "schema": "example.summary.v1",
                        "decision": "example_failed",
                        "ok": False,
                        "acceptance_enabled": True,
                        "acceptance_passed": False,
                        "acceptance_decision": "example_acceptance_failed",
                    }
                ),
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                bundle_rc = cli_main(
                    [
                        "bundle",
                        "--output-dir",
                        str(bundle_dir),
                        "--run-summary",
                        str(summary),
                    ]
                )

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                validation_rc = cli_main(
                    ["validate-bundle", str(bundle_dir / "manifest.json")]
                )

        self.assertEqual(bundle_rc, 0)
        self.assertEqual(validation_rc, 1)
        self.assertIn("openmc2donjon_bundle_validation_failed", stream.getvalue())
        self.assertIn("summary payload reports ok=false", stream.getvalue())
        self.assertIn("example_acceptance_failed", stream.getvalue())

    def test_convert_check_writes_output_for_valid_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "mgxs.h5"
            output_path = tmp / "out.mcompo.txt"
            summary_path = tmp / "check_summary.json"
            write_valid_mgxs(input_path)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--check",
                        "--require-volume",
                        "--check-summary-json",
                        str(summary_path),
                    ]
                )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            output_exists = output_path.exists()

        self.assertEqual(rc, 0)
        self.assertTrue(output_exists)
        self.assertEqual(summary["decision"], "mgxs_input_contract_passed")
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())

    def test_convert_check_rejects_invalid_hdf5_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "bad.h5"
            output_path = tmp / "out.mcompo.txt"
            with h5py.File(input_path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main([str(input_path), "-o", str(output_path), "--check"])

        self.assertEqual(rc, 1)
        self.assertFalse(output_path.exists())
        self.assertIn("mgxs_input_contract_failed", stream.getvalue())

    def test_convert_check_can_fail_on_production_uncertainty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "mgxs.h5"
            output_path = tmp / "out.mcompo.txt"
            summary_path = tmp / "check_summary.json"
            write_valid_mgxs(input_path)
            with h5py.File(input_path, "a") as h5:
                h5["mixtures/fuel"].create_dataset(
                    "total_std_dev",
                    data=np.array([0.001, 0.14]),
                )

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--check",
                        "--uncertainty-production-fail",
                        "0.1",
                        "--check-summary-json",
                        str(summary_path),
                    ]
                )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 1)
        self.assertFalse(output_path.exists())
        self.assertEqual(summary["decision"], "mgxs_input_contract_failed")
        uncertainty = summary["inputs"][0]["uncertainty"]
        self.assertAlmostEqual(uncertainty["production_max_rel"], 0.2)
        self.assertIn("production fail threshold", stream.getvalue())


def _parser_help(argv: list[str]) -> str:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        try:
            build_command_parser().parse_args(argv)
        except SystemExit as exc:
            if exc.code != 0:
                raise AssertionError(f"help exited with {exc.code}") from exc
        else:
            raise AssertionError("help did not exit")
    return stream.getvalue()


def write_valid_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.attrs["domain_mode"] = "unit_test"
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = "moment,from,to"
        fuel.attrs["volume"] = 1.0
        fuel.attrs["source_domain_index"] = 1
        fuel.attrs["source_domain_id"] = 1
        fuel.attrs["source_domain_type"] = "cell"
        fuel.create_dataset("total", data=np.array([0.5, 0.7]))
        fuel.create_dataset("absorption", data=np.array([0.05, 0.08]))
        fuel.create_dataset("fission", data=np.array([0.01, 0.015]))
        fuel.create_dataset("nu_fission", data=np.array([0.025, 0.03]))
        fuel.create_dataset("chi", data=np.array([1.0, 0.0]))
        fuel.create_dataset("transport_total", data=np.array([0.45, 0.63]))
        fuel.create_dataset(
            "scatter_matrix",
            data=np.array([[[0.2, 0.04], [0.0, 0.3]]]),
        )
        flux = h5.create_dataset("openmc_volume_flux", data=np.array([[10.0, 20.0]]))
        flux.attrs["group_order"] = "mgxs_donjon"
        flux.attrs["mixture_names"] = np.asarray(["fuel"], dtype="S")
        flux.attrs["source_group_order"] = "unit_test"

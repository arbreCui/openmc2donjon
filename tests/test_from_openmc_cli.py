from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

import h5py
import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_cli import build_parser, main as from_openmc_main
from openmc2donjon.from_openmc_summary import (
    FROM_OPENMC_SUMMARY_SCHEMA,
    validate_from_openmc_summary,
)


def assert_from_openmc_summary(
    case: unittest.TestCase,
    payload: dict[str, object],
) -> None:
    case.assertEqual(validate_from_openmc_summary(payload), [])


class FromOpenMCCliTests(unittest.TestCase):
    def test_version_option(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            build_parser().parse_args(["--version"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(stream.getvalue().strip(), "openmc2donjon-from-openmc 0.1.2")

    def test_recipe_to_multicompo_with_kept_hdf5(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            hdf5 = tmp / "mgxs.h5"
            output = tmp / "out.mcompo.txt"
            summary = tmp / "summary.json"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--keep-hdf5",
                        str(hdf5),
                        "-o",
                        str(output),
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("preflight OK: mixtures=2", stream.getvalue())
            self.assertTrue(hdf5.exists())
            self.assertTrue(output.exists())
            self.assertTrue(summary.exists())

            with h5py.File(hdf5, "r") as h5:
                self.assertEqual(sorted(h5["mixtures"]), ["FUEL_A", "MOD_A"])
                self.assertEqual(h5.attrs["domain_mode"], "recipe_smoke")

            blocks = lcm_ascii.read_lcm_ascii(output)
            names = [block.name for block in blocks if block.name]
            self.assertEqual(names[0], "SIGNATURE")

            payload = json.loads(summary.read_text(encoding="utf-8"))
            assert_from_openmc_summary(self, payload)
            self.assertEqual(payload["schema"], FROM_OPENMC_SUMMARY_SCHEMA)
            self.assertEqual(payload["package_version"], "0.1.2")
            self.assertEqual(payload["recipe"], str(recipe.resolve()))
            self.assertEqual(payload["statepoint"], str(statepoint.resolve()))
            self.assertTrue(payload["loaded_statepoint"])
            self.assertEqual(payload["format"], "multicompo")
            self.assertEqual(payload["hdf5"], str(hdf5))
            self.assertTrue(payload["hdf5_kept"])
            self.assertEqual(payload["output"], str(output))
            self.assertEqual(payload["energy_groups"], 2)
            self.assertEqual(payload["legendre_order"], 0)
            self.assertEqual(payload["mixture_count"], 2)
            self.assertEqual(payload["mixture_names"], ["FUEL_A", "MOD_A"])
            self.assertEqual(payload["state_points"], 1)
            self.assertEqual(payload["burnup_axis"], {"present": False})
            self.assertIsNone(payload["selected_mixtures"])
            self.assertEqual(payload["root_name"], "CPO")
            self.assertIsNone(payload["single_point_burnup"])
            self.assertIsNone(payload["h_factor_default"])
            self.assertFalse(payload["checked"])
            self.assertIsNone(payload["check_passed"])
            self.assertIsNone(payload["check_summary_json"])

    def test_dry_run_reports_conversion_plan_without_writing_files(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            hdf5 = tmp / "mgxs.h5"
            output = tmp / "out.mcompo.txt"
            summary = tmp / "summary.json"
            check_summary = tmp / "check_summary.json"

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--dry-run",
                        "--keep-hdf5",
                        str(hdf5),
                        "-o",
                        str(output),
                        "--summary-json",
                        str(summary),
                        "--check",
                        "--require-volume",
                        "--require-transport-dataset",
                        "--check-summary-json",
                        str(check_summary),
                    ]
                )

            rendered = stream.getvalue()
            hdf5_exists = hdf5.exists()
            output_exists = output.exists()
            summary_exists = summary.exists()
            check_summary_exists = check_summary.exists()

        self.assertEqual(rc, 0)
        self.assertIn("recipe dry-run OK", rendered)
        self.assertIn("statepoint: none", rendered)
        self.assertIn("output: " + str(hdf5.resolve()) + " (not written)", rendered)
        self.assertIn("one-step conversion dry-run OK", rendered)
        self.assertIn("format: multicompo", rendered)
        self.assertIn("ascii_output: " + str(output) + " (not written)", rendered)
        self.assertIn("check: enabled after HDF5 export", rendered)
        self.assertIn("require_volume: yes", rendered)
        self.assertIn("require_transport_dataset: yes", rendered)
        self.assertFalse(hdf5_exists)
        self.assertFalse(output_exists)
        self.assertFalse(summary_exists)
        self.assertFalse(check_summary_exists)

    def test_strict_dry_run_returns_nonzero_for_recipe_warnings(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = from_openmc_main(
                [
                    "--recipe",
                    str(recipe),
                    "--dry-run",
                    "--strict-dry-run",
                ]
            )

        rendered = stream.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("one-step conversion dry-run OK", rendered)
        self.assertIn("recipe_dry_run_strict_failed", rendered)
        self.assertIn("WARN mgxs-required:", rendered)

    def test_missing_statepoint_tally_reports_actionable_error(self) -> None:
        recipe_text = """
class Library:
    def load_from_statepoint(self, statepoint):
        raise LookupError("Unable to get Tally")

def build_library():
    return Library()
"""

        class FakeStatePoint:
            def __init__(self, path):
                self.path = path

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            recipe = tmp / "recipe.py"
            statepoint = tmp / "statepoint.fake.h5"
            hdf5 = tmp / "mgxs.h5"
            output = tmp / "out.mcompo.txt"
            recipe.write_text(recipe_text, encoding="utf-8")
            statepoint.write_text("fake statepoint\n", encoding="utf-8")

            original_openmc = sys.modules.get("openmc")
            sys.modules["openmc"] = types.SimpleNamespace(StatePoint=FakeStatePoint)
            stderr = io.StringIO()
            try:
                with contextlib.redirect_stderr(stderr):
                    rc = from_openmc_main(
                        [
                            "--recipe",
                            str(recipe),
                            "--statepoint",
                            str(statepoint),
                            "--keep-hdf5",
                            str(hdf5),
                            "-o",
                            str(output),
                        ]
                    )
            finally:
                if original_openmc is None:
                    del sys.modules["openmc"]
                else:
                    sys.modules["openmc"] = original_openmc

        rendered = stderr.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("statepoint", rendered)
        self.assertIn("does not contain one or more MGXS tallies", rendered)
        self.assertIn("rerun OpenMC with the tallies generated by that recipe", rendered)
        self.assertIn("Unable to get Tally", rendered)
        self.assertNotIn("Traceback", rendered)

    def test_run_dir_writes_standard_artifacts_and_manifest(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            run_dir = tmp / "production_run"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                        "--check",
                        "--require-volume",
                        "--require-transport-dataset",
                    ]
                )

            hdf5 = run_dir / "mgxs_library.h5"
            output = run_dir / "out.mcompo.txt"
            summary = run_dir / "run_summary.json"
            check_summary = run_dir / "check_summary.json"
            manifest = run_dir / "manifest.json"
            bundle_validation = run_dir / "bundle_validation_summary.json"
            recipe_copy = run_dir / recipe.name
            conversion_payload = json.loads(summary.read_text(encoding="utf-8"))
            check_payload = json.loads(check_summary.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            validation_payload = json.loads(bundle_validation.read_text(encoding="utf-8"))
            standard_paths_exist = [
                path.exists()
                for path in (
                    hdf5,
                    output,
                    summary,
                    check_summary,
                    manifest,
                    bundle_validation,
                    recipe_copy,
                )
            ]

        self.assertEqual(rc, 0)
        self.assertIn("OpenMC-to-DONJON bundle", stream.getvalue())
        self.assertIn("openmc2donjon_bundle_validation_passed", stream.getvalue())
        self.assertTrue(all(standard_paths_exist))
        assert_from_openmc_summary(self, conversion_payload)
        self.assertEqual(conversion_payload["hdf5"], str(hdf5))
        self.assertTrue(conversion_payload["hdf5_kept"])
        self.assertEqual(conversion_payload["output"], str(output))
        self.assertTrue(conversion_payload["checked"])
        self.assertEqual(conversion_payload["check_summary_json"], str(check_summary))
        self.assertEqual(check_payload["decision"], "mgxs_input_contract_passed")
        self.assertEqual(manifest_payload["schema"], "openmc2donjon.bundle.v1")
        self.assertEqual(
            validation_payload["decision"],
            "openmc2donjon_bundle_validation_passed",
        )
        self.assertTrue(validation_payload["ok"])
        labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}
        self.assertEqual(set(labels), {"mgxs", "mcompo", "run-summary", "check-summary", "recipe"})
        self.assertEqual(labels["run-summary"]["summary_schema"], FROM_OPENMC_SUMMARY_SCHEMA)
        self.assertEqual(
            labels["check-summary"]["summary_decision"],
            "mgxs_input_contract_passed",
        )

    def test_run_dir_manifest_includes_extra_artifacts(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            surface_flux = tmp / "openmc_surface_flux.h5"
            driver_summary = tmp / "low_order_driver_summary.json"
            run_dir = tmp / "production_run"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            surface_flux.write_bytes(b"surface flux fixture\n")
            driver_summary.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.low-order-driver.v1",
                        "decision": "openmc2donjon_low_order_driver_passed",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                        "--extra-artifact",
                        f"surface-flux={surface_flux}",
                        "--extra-artifact",
                        f"low-order-driver-summary={driver_summary}",
                    ]
                )

            manifest = run_dir / "manifest.json"
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}

        self.assertEqual(rc, 0)
        self.assertIn("surface-flux", labels)
        self.assertIn("low-order-driver-summary", labels)
        self.assertEqual(labels["surface-flux"]["bundled_path"], "openmc_surface_flux.h5")
        self.assertEqual(
            labels["low-order-driver-summary"]["summary_schema"],
            "openmc2donjon.low-order-driver.v1",
        )
        self.assertEqual(
            labels["low-order-driver-summary"]["summary_decision"],
            "openmc2donjon_low_order_driver_passed",
        )

    def test_run_dir_injects_adf_sidecar_before_checked_conversion(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            adf_source = tmp / "adf_sidecar.h5"
            run_dir = tmp / "production_run"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            _write_adf_sidecar(adf_source)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                        "--adf-source",
                        str(adf_source),
                        "--adf-faces",
                        "FD_XMIN,FD_XMAX",
                        "--check",
                        "--require-adf",
                        "--require-volume",
                        "--require-transport-dataset",
                    ]
                )

            hdf5 = run_dir / "mgxs_library.h5"
            output = run_dir / "out.mcompo.txt"
            adf_summary = run_dir / "adf_summary.json"
            manifest = run_dir / "manifest.json"
            with h5py.File(hdf5, "r") as h5:
                fuel_xmin = h5["mixtures/FUEL_A/adf/FD_XMIN"][:]
                mod_xmax = h5["mixtures/MOD_A/adf/FD_XMAX"][:]
            adf_payload = json.loads(adf_summary.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            paths_exist = [hdf5.exists(), output.exists(), adf_summary.exists()]

        self.assertEqual(rc, 0)
        self.assertIn("injected ADF into HDF5", stream.getvalue())
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())
        self.assertTrue(all(paths_exist))
        np.testing.assert_allclose(fuel_xmin, [1.01, 1.02])
        np.testing.assert_allclose(mod_xmax, [0.97, 0.96])
        self.assertEqual(adf_payload["decision"], "openmc2donjon_adf_augment_passed")
        labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}
        self.assertIn("adf-source", labels)
        self.assertIn("adf-summary", labels)
        self.assertEqual(labels["adf-summary"]["summary_schema"], "openmc2donjon.adf-augment.v1")

    def test_run_dir_injects_sph_sidecar_before_checked_conversion(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            sph_source = tmp / "sph_sidecar.h5"
            run_dir = tmp / "production_run"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            _write_sph_sidecar(sph_source)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                        "--sph-source",
                        str(sph_source),
                        "--sph-kind",
                        "production-sph",
                        "--sph-real",
                        "true",
                        "--sph-applied",
                        "false",
                        "--check",
                        "--require-volume",
                        "--require-transport-dataset",
                    ]
                )

            hdf5 = run_dir / "mgxs_library.h5"
            output = run_dir / "out.mcompo.txt"
            sph_summary = run_dir / "sph_summary.json"
            check_summary = run_dir / "check_summary.json"
            manifest = run_dir / "manifest.json"
            with h5py.File(hdf5, "r") as h5:
                fuel_sph = h5["mixtures/FUEL_A/sph"][:]
                mod_sph = h5["mixtures/MOD_A/sph"][:]
                attrs = dict(h5.attrs)
            sph_payload = json.loads(sph_summary.read_text(encoding="utf-8"))
            check_payload = json.loads(check_summary.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}
            paths_exist = [hdf5.exists(), output.exists(), sph_summary.exists()]

        self.assertEqual(rc, 0)
        self.assertIn("injected SPH into HDF5", stream.getvalue())
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())
        self.assertTrue(all(paths_exist))
        np.testing.assert_allclose(fuel_sph, [1.10, 0.90])
        np.testing.assert_allclose(mod_sph, [0.95, 1.05])
        self.assertEqual(attrs["sph_kind"], "production-sph")
        self.assertTrue(bool(attrs["sph_real"]))
        self.assertFalse(bool(attrs["sph_applied"]))
        self.assertEqual(sph_payload["decision"], "openmc2donjon_sph_augment_passed")
        self.assertEqual(check_payload["decision"], "mgxs_input_contract_passed")
        self.assertIn("sph-source", labels)
        self.assertIn("sph-summary", labels)
        self.assertEqual(labels["sph-summary"]["summary_schema"], "openmc2donjon.sph-augment.v1")

    def test_run_dir_builds_sph_sidecar_from_macrolib(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            sph_source = tmp / "sph_sidecar.h5"
            donor_hdf5 = tmp / "donor_mgxs.h5"
            donor_macrolib = tmp / "donor.macrolib.txt"
            run_dir = tmp / "production_run"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            _write_sph_sidecar(sph_source)

            with contextlib.redirect_stdout(io.StringIO()):
                donor_rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--keep-hdf5",
                        str(donor_hdf5),
                        "--format",
                        "macrolib",
                        "-o",
                        str(donor_macrolib),
                        "--sph-source",
                        str(sph_source),
                    ]
                )

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                        "--sph-macrolib",
                        str(donor_macrolib),
                        "--check",
                        "--require-volume",
                        "--require-transport-dataset",
                    ]
                )

            hdf5 = run_dir / "mgxs_library.h5"
            sidecar = run_dir / "sph_sidecar.h5"
            sidecar_summary = run_dir / "sph_sidecar_summary.json"
            sph_summary = run_dir / "sph_summary.json"
            manifest = run_dir / "manifest.json"
            with h5py.File(hdf5, "r") as h5:
                fuel_sph = h5["mixtures/FUEL_A/sph"][:]
                attrs = dict(h5.attrs)
            sidecar_payload = json.loads(sidecar_summary.read_text(encoding="utf-8"))
            sph_payload = json.loads(sph_summary.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}
            sidecar_exists = sidecar.exists()

        self.assertEqual(donor_rc, 0)
        self.assertEqual(rc, 0)
        self.assertTrue(sidecar_exists)
        self.assertIn("openmc2donjon_sph_sidecar_passed", stream.getvalue())
        np.testing.assert_allclose(fuel_sph, [1.10, 0.90])
        self.assertEqual(attrs["sph_kind"], "macrolib-nsph")
        self.assertTrue(bool(attrs["sph_real"]))
        self.assertFalse(bool(attrs["sph_applied"]))
        self.assertEqual(sidecar_payload["decision"], "openmc2donjon_sph_sidecar_passed")
        self.assertEqual(sph_payload["decision"], "openmc2donjon_sph_augment_passed")
        required = {
            "sph-source",
            "sph-summary",
            "sph-macrolib",
            "sph-sidecar-summary",
        }
        self.assertTrue(required <= set(labels))
        self.assertEqual(
            labels["sph-sidecar-summary"]["summary_decision"],
            "openmc2donjon_sph_sidecar_passed",
        )

    def test_run_dir_builds_flux_ratio_adf_workflow(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            surface_flux = tmp / "surface_flux.h5"
            raw_driver = tmp / "raw_driver.h5"
            run_dir = tmp / "production_run"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            _write_surface_flux(surface_flux)
            _write_low_order_raw(raw_driver)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                        "--build-flux-ratio-adf",
                        "--adf-surface-flux",
                        str(surface_flux),
                        "--low-order-raw-driver",
                        str(raw_driver),
                        "--adf-faces",
                        "FD_XMIN,FD_XMAX",
                        "--adf-face-widths",
                        "4.0",
                        "--adf-kind",
                        "flux-ratio-test",
                        "--adf-real",
                        "false",
                        "--require-volume",
                        "--require-transport-dataset",
                    ]
                )

            hdf5 = run_dir / "mgxs_library.h5"
            sidecar = run_dir / "adf_sidecar.h5"
            sidecar_summary = run_dir / "adf_sidecar_summary.json"
            face_flux_check_summary = run_dir / "face_flux_check_summary.json"
            low_order_driver_summary = run_dir / "low_order_driver_summary.json"
            low_order_check = run_dir / "low_order_driver_check_summary.json"
            homogeneous = run_dir / "homogeneous_face_flux.h5"
            check_summary = run_dir / "check_summary.json"
            manifest = run_dir / "manifest.json"
            with h5py.File(hdf5, "r") as h5:
                fuel_xmin = h5["mixtures/FUEL_A/adf/FD_XMIN"][:]
                mod_xmax = h5["mixtures/MOD_A/adf/FD_XMAX"][:]
                attrs = dict(h5.attrs)
            sidecar_payload = json.loads(sidecar_summary.read_text(encoding="utf-8"))
            face_flux_payload = json.loads(face_flux_check_summary.read_text(encoding="utf-8"))
            low_order_driver_payload = json.loads(
                low_order_driver_summary.read_text(encoding="utf-8")
            )
            low_order_payload = json.loads(low_order_check.read_text(encoding="utf-8"))
            check_payload = json.loads(check_summary.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}
            sidecar_exists = sidecar.exists()
            homogeneous_exists = homogeneous.exists()

        self.assertEqual(rc, 0)
        self.assertIn("openmc2donjon_low_order_driver_contract_passed", stream.getvalue())
        self.assertIn("openmc2donjon_adf_sidecar_passed", stream.getvalue())
        self.assertTrue(sidecar_exists)
        self.assertTrue(homogeneous_exists)
        np.testing.assert_allclose(fuel_xmin, [1.1, 1.1])
        np.testing.assert_allclose(mod_xmax, [1.0, 0.9])
        self.assertEqual(attrs["adf_kind"], "flux-ratio-test")
        self.assertEqual(attrs["adf_real"], "false")
        self.assertEqual(sidecar_payload["decision"], "openmc2donjon_adf_sidecar_passed")
        self.assertFalse(sidecar_payload["adf_real"])
        self.assertEqual(
            face_flux_payload["decision"],
            "openmc2donjon_face_flux_contract_passed",
        )
        self.assertEqual(low_order_driver_payload["adapter_mode"], "raw-driver-bundle")
        self.assertEqual(low_order_driver_payload["raw_driver_h5"], str(raw_driver))
        self.assertEqual(
            low_order_payload["decision"],
            "openmc2donjon_low_order_driver_contract_passed",
        )
        self.assertEqual(check_payload["decision"], "mgxs_input_contract_passed")
        required_labels = {
            "mgxs",
            "mcompo",
            "run-summary",
            "check-summary",
            "adf-source",
            "adf-summary",
            "surface-flux",
            "low-order-driver",
            "low-order-driver-summary",
            "low-order-driver-check-summary",
            "homogeneous-face-flux",
            "homogeneous-face-flux-summary",
            "face-flux-check-summary",
            "adf-sidecar-summary",
            "recipe",
        }
        self.assertEqual(set(labels), required_labels)
        self.assertEqual(
            labels["low-order-driver-check-summary"]["summary_decision"],
            "openmc2donjon_low_order_driver_contract_passed",
        )
        self.assertEqual(
            labels["adf-sidecar-summary"]["summary_decision"],
            "openmc2donjon_adf_sidecar_passed",
        )
        self.assertEqual(
            labels["face-flux-check-summary"]["summary_decision"],
            "openmc2donjon_face_flux_contract_passed",
        )

    def test_run_dir_builds_flux_ratio_adf_with_external_homogeneous_flux(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            surface_flux = tmp / "surface_flux.h5"
            homogeneous_flux = tmp / "homogeneous_face_flux.h5"
            run_dir = tmp / "production_run"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            _write_surface_flux(surface_flux)
            _write_homogeneous_face_flux(homogeneous_flux)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                        "--build-flux-ratio-adf",
                        "--adf-surface-flux",
                        f"{surface_flux}::heterogeneous_face_flux",
                        "--homogeneous-face-flux",
                        f"{homogeneous_flux}::homogeneous_face_flux",
                        "--adf-faces",
                        "FD_XMIN,FD_XMAX",
                        "--adf-kind",
                        "flux-ratio-external-hom",
                        "--adf-real",
                        "true",
                        "--require-volume",
                        "--require-transport-dataset",
                    ]
                )

            hdf5 = run_dir / "mgxs_library.h5"
            sidecar_summary = run_dir / "adf_sidecar_summary.json"
            face_flux_check_summary = run_dir / "face_flux_check_summary.json"
            low_order_driver = run_dir / "low_order_driver.h5"
            generated_homogeneous_summary = run_dir / "homogeneous_face_flux_summary.json"
            manifest = run_dir / "manifest.json"
            with h5py.File(hdf5, "r") as h5:
                fuel_xmin = h5["mixtures/FUEL_A/adf/FD_XMIN"][:]
                mod_xmax = h5["mixtures/MOD_A/adf/FD_XMAX"][:]
                attrs = dict(h5.attrs)
            sidecar_payload = json.loads(sidecar_summary.read_text(encoding="utf-8"))
            face_flux_payload = json.loads(face_flux_check_summary.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest_payload["artifacts"]}

        self.assertEqual(rc, 0)
        self.assertIn("openmc2donjon_adf_sidecar_passed", stream.getvalue())
        self.assertFalse(low_order_driver.exists())
        self.assertFalse(generated_homogeneous_summary.exists())
        np.testing.assert_allclose(fuel_xmin, [1.1, 1.1])
        np.testing.assert_allclose(mod_xmax, [1.0, 0.9])
        self.assertEqual(attrs["adf_kind"], "flux-ratio-external-hom")
        self.assertEqual(attrs["adf_real"], "true")
        self.assertEqual(sidecar_payload["adf_homogeneous_face_flux"], str(homogeneous_flux))
        self.assertEqual(
            sidecar_payload["adf_surface_flux_dataset"],
            "heterogeneous_face_flux",
        )
        self.assertEqual(
            sidecar_payload["adf_homogeneous_face_flux_dataset"],
            "homogeneous_face_flux",
        )
        self.assertEqual(
            face_flux_payload["decision"],
            "openmc2donjon_face_flux_contract_passed",
        )
        self.assertEqual(face_flux_payload["surface_flux_dataset"], "heterogeneous_face_flux")
        self.assertEqual(face_flux_payload["homogeneous_face_flux_dataset"], "homogeneous_face_flux")
        required_labels = {
            "mgxs",
            "mcompo",
            "run-summary",
            "check-summary",
            "adf-source",
            "adf-summary",
            "surface-flux",
            "homogeneous-face-flux",
            "face-flux-check-summary",
            "adf-sidecar-summary",
            "recipe",
        }
        self.assertEqual(set(labels), required_labels)
        self.assertEqual(
            labels["adf-sidecar-summary"]["summary_decision"],
            "openmc2donjon_adf_sidecar_passed",
        )
        self.assertEqual(
            labels["face-flux-check-summary"]["summary_decision"],
            "openmc2donjon_face_flux_contract_passed",
        )
        self.assertEqual(labels["surface-flux"]["source"], str(surface_flux))
        self.assertEqual(labels["homogeneous-face-flux"]["source"], str(homogeneous_flux))

    def test_run_dir_dry_run_uses_standard_paths_without_writing(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "dry_run_dir"

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--dry-run",
                        "--run-dir",
                        str(run_dir),
                        "--check",
                    ]
                )

            rendered = stream.getvalue()
            run_dir_exists = run_dir.exists()

        self.assertEqual(rc, 0)
        self.assertIn(f"hdf5: {run_dir / 'mgxs_library.h5'} (not written)", rendered)
        self.assertIn(f"ascii_output: {run_dir / 'out.mcompo.txt'} (not written)", rendered)
        self.assertIn(f"summary_json: {run_dir / 'run_summary.json'} (not written)", rendered)
        self.assertIn(
            f"check_summary_json: {run_dir / 'check_summary.json'} (not written)",
            rendered,
        )
        self.assertFalse(run_dir_exists)

    def test_run_dir_refuses_existing_managed_artifacts_without_force(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            run_dir = tmp / "production_run"
            run_dir.mkdir()
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            (run_dir / "mgxs_library.h5").write_text("existing\n", encoding="utf-8")

            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--run-dir",
                        str(run_dir),
                    ]
                )

        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--force-run-dir", err.getvalue())

    def test_extra_artifact_requires_run_dir(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            extra = tmp / "notes.txt"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            extra.write_text("notes\n", encoding="utf-8")

            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--extra-artifact",
                        f"notes={extra}",
                    ]
                )

        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--extra-artifact requires --run-dir", err.getvalue())

    def test_recipe_to_multicompo_with_checked_hdf5(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            hdf5 = tmp / "mgxs.h5"
            output = tmp / "out.mcompo.txt"
            summary = tmp / "summary.json"
            check_summary = tmp / "check_summary.json"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--keep-hdf5",
                        str(hdf5),
                        "-o",
                        str(output),
                        "--summary-json",
                        str(summary),
                        "--check",
                        "--require-volume",
                        "--require-transport-dataset",
                        "--check-summary-json",
                        str(check_summary),
                    ]
                )

            payload = json.loads(check_summary.read_text(encoding="utf-8"))
            conversion_payload = json.loads(summary.read_text(encoding="utf-8"))
            output_exists = output.exists()

        self.assertEqual(rc, 0)
        self.assertTrue(output_exists)
        self.assertEqual(payload["decision"], "mgxs_input_contract_passed")
        assert_from_openmc_summary(self, conversion_payload)
        self.assertTrue(conversion_payload["checked"])
        self.assertTrue(conversion_payload["check_passed"])
        self.assertEqual(conversion_payload["check_summary_json"], str(check_summary))
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())

    def test_recipe_check_failure_does_not_write_output(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            hdf5 = tmp / "mgxs.h5"
            output = tmp / "out.mcompo.txt"
            check_summary = tmp / "check_summary.json"
            conversion_summary = tmp / "conversion_summary.json"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--keep-hdf5",
                        str(hdf5),
                        "-o",
                        str(output),
                        "--summary-json",
                        str(conversion_summary),
                        "--check",
                        "--require-adf",
                        "--check-summary-json",
                        str(check_summary),
                    ]
                )

            payload = json.loads(check_summary.read_text(encoding="utf-8"))
            output_exists = output.exists()
            hdf5_exists = hdf5.exists()
            conversion_summary_exists = conversion_summary.exists()

        self.assertEqual(rc, 1)
        self.assertTrue(hdf5_exists)
        self.assertFalse(output_exists)
        self.assertFalse(conversion_summary_exists)
        self.assertEqual(payload["decision"], "mgxs_input_contract_failed")
        self.assertIn("mgxs_input_contract_failed", stream.getvalue())


def _write_adf_sidecar(path: Path) -> None:
    values = np.array(
        [
            [[1.01, 1.02], [0.99, 0.98]],
            [[1.03, 1.04], [0.97, 0.96]],
        ]
    )
    with h5py.File(path, "w") as h5:
        h5.attrs["adf_kind"] = "production"
        h5.attrs["adf_real"] = "true"
        dataset = h5.create_dataset("adf", data=values)
        dataset.attrs["mixture_names"] = np.asarray(["FUEL_A", "MOD_A"], dtype="S")
        dataset.attrs["face_names"] = np.asarray(["FD_XMIN", "FD_XMAX"], dtype="S")


def _write_sph_sidecar(path: Path) -> None:
    values = np.array(
        [
            [1.10, 0.90],
            [0.95, 1.05],
        ],
        dtype=float,
    )
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.sph-sidecar.v1"
        h5.attrs["sph_kind"] = "fixture"
        h5.attrs["sph_real"] = True
        h5.attrs["sph_applied"] = False
        dataset = h5.create_dataset("sph", data=values)
        dataset.attrs["mixture_names"] = np.asarray(["FUEL_A", "MOD_A"], dtype="S")


def _write_surface_flux(path: Path) -> None:
    values = np.array(
        [
            [[11.0, 22.0], [9.0, 18.0]],
            [[33.0, 44.0], [30.0, 36.0]],
        ],
        dtype=float,
    )
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset("heterogeneous_face_flux", data=values)
        dataset.attrs["mixture_names"] = np.asarray(["FUEL_A", "MOD_A"], dtype="S")
        dataset.attrs["face_names"] = np.asarray(["FD_XMIN", "FD_XMAX"], dtype="S")


def _write_low_order_raw(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        volume = h5.create_dataset(
            "volume_flux",
            data=np.asarray([[10.0, 20.0], [30.0, 40.0]], dtype=float),
        )
        current = h5.create_dataset(
            "net_current_density",
            data=np.zeros((2, 2, 2), dtype=float),
        )
        names = np.asarray(["FUEL_A", "MOD_A"], dtype="S")
        volume.attrs["mixture_names"] = names
        current.attrs["mixture_names"] = names


def _write_homogeneous_face_flux(path: Path) -> None:
    values = np.array(
        [
            [[10.0, 20.0], [9.0, 20.0]],
            [[30.0, 40.0], [30.0, 40.0]],
        ],
        dtype=float,
    )
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset("homogeneous_face_flux", data=values)
        dataset.attrs["mixture_names"] = np.asarray(["FUEL_A", "MOD_A"], dtype="S")
        dataset.attrs["face_names"] = np.asarray(["FD_XMIN", "FD_XMAX"], dtype="S")


if __name__ == "__main__":
    unittest.main()

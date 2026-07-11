"""FastAPI backend tests split by endpoint family."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.web_test_utils import (
    WEB_AVAILABLE as _WEB_AVAILABLE,
    TestClient,
    write_fake_hdf5 as _write_fake_hdf5,
)


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class ConvertEndpointTests(unittest.TestCase):
    def test_mock_mode_returns_conversion_preview(self) -> None:
        from openmc2donjon.web.convert import CONVERT_SCHEMA
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/convert",
            json={
                "input_path": "/mock/home/openmc-runs/c5g7/handoff.h5",
                "format": "multicompo",
                "dry_run": True,
                "overwrite": False,
                "check": True,
                "production": False,
                "warn_unknown_energy_mesh": True,
                "require_known_energy_mesh": False,
                "comment": "C5G7 dry run",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], CONVERT_SCHEMA)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["converted"])
        self.assertEqual(payload["format"], "multicompo")
        self.assertEqual(payload["writer_backend"], "ascii")
        self.assertIn("--format multicompo", payload["cli_command_text"])
        self.assertIn("--dry-run", payload["cli_command"])
        self.assertNotIn("--overwrite", payload["cli_command"])
        self.assertIn("--comment", payload["cli_command"])
        self.assertIn("C5G7 dry run", payload["cli_command"])
        self.assertFalse(payload["summary_written"])
        # The default output is derived from the input directory, and a
        # dry run reports what the file-status probe will say: nothing
        # written yet.
        self.assertEqual(
            payload["output_path"],
            "/mock/home/openmc-runs/c5g7/handoff.mcompo.txt",
        )
        self.assertFalse(payload["output_exists"])
        self.assertIsNone(payload["output_size"])
        self.assertEqual(
            payload["summary_path"],
            "/mock/home/openmc-runs/c5g7/convert_summary.json",
        )
        self.assertEqual(payload["preflight"]["inputs"][0]["energy_mesh_id"], "casmo_7")

    def test_mock_mode_write_registers_output_with_mock_filesystem(self) -> None:
        """A non-dry mock convert must agree with the mock file endpoints.

        Regression test for the mock demo contradiction where the
        convert response claimed a written artifact (184,320 bytes at a
        hardcoded path) that the file-status probe and file browser
        reported as missing forever.
        """

        from openmc2donjon.web.files import _MOCK_WRITTEN_FILES
        from openmc2donjon.web.server import create_app

        self.addCleanup(_MOCK_WRITTEN_FILES.clear)
        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/convert",
            json={
                "input_path": "/mock/home/openmc-runs/c5g7/handoff.h5",
                "format": "multicompo",
                "dry_run": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["converted"])
        self.assertTrue(payload["output_exists"])
        output_path = payload["output_path"]
        self.assertEqual(output_path, "/mock/home/openmc-runs/c5g7/handoff.mcompo.txt")

        status = client.get("/api/file-status", params={"path": output_path}).json()
        self.assertTrue(status["exists"])
        self.assertEqual(status["kind"], "file")
        self.assertEqual(status["size"], payload["output_size"])

        preview = client.get("/api/text-preview", params={"path": output_path}).json()
        self.assertEqual(preview["file_size"], payload["output_size"])
        self.assertFalse(preview["truncated"])

        listing = client.get(
            "/api/files", params={"path": "/mock/home/openmc-runs/c5g7"}
        ).json()
        sizes = {entry["name"]: entry["size"] for entry in listing["entries"]}
        self.assertEqual(sizes.get("handoff.mcompo.txt"), payload["output_size"])
        self.assertIn("convert_summary.json", sizes)

        summary_status = client.get(
            "/api/file-status", params={"path": payload["summary_path"]}
        ).json()
        self.assertTrue(payload["summary_written"])
        self.assertTrue(summary_status["exists"])

    def test_mock_mode_openmc_sph_handoff_reports_33g_sph_shape(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/convert",
            json={
                "input_path": "/mock/home/openmc-runs/openmc-sph-minicase/mgxs_with_openmc_sph.h5",
                "output_path": (
                    "/mock/home/openmc-runs/openmc-sph-minicase/out.macrolib.txt"
                ),
                "format": "macrolib",
                "dry_run": True,
                "overwrite": False,
                "check": True,
                "production": True,
                "warn_unknown_energy_mesh": True,
                "require_known_energy_mesh": False,
                "comment": "OpenMC-side SPH corrected handoff",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["format"], "macrolib")
        self.assertIn("--production", payload["cli_command"])
        preflight_input = payload["preflight"]["inputs"][0]
        self.assertEqual(preflight_input["energy_groups"], 33)
        self.assertEqual(preflight_input["legendre_order"], 3)
        self.assertEqual(preflight_input["mixtures"], 2)
        self.assertEqual(preflight_input["sph_calculations"], 2)
        self.assertEqual(preflight_input["uncertainty"]["max_rel"], 4.13e-2)

    def test_live_mode_dry_run_runs_preflight_without_writing(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "handoff.h5"
            output_path = Path(tmp) / "handoff.mcompo.txt"
            _write_fake_hdf5(input_path)

            client = TestClient(create_app(mock_mode=False))
            response = client.post(
                "/api/convert",
                json={
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "format": "multicompo",
                    "dry_run": True,
                    "overwrite": False,
                    # The fake HDF5 intentionally has a non-zero row-balance
                    # residual; this dry-run still proves the endpoint
                    # validates and returns a structured preflight summary.
                    "check": True,
                    "production": False,
                    "warn_unknown_energy_mesh": True,
                    "require_known_energy_mesh": False,
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertFalse(output_path.exists())
            self.assertEqual(payload["writer_backend"], "ascii")
            self.assertTrue(payload["dry_run"])
            self.assertFalse(payload["converted"])
            self.assertFalse(payload["summary_written"])
            self.assertFalse((Path(tmp) / "convert_summary.json").exists())
            self.assertIn("--dry-run", payload["cli_command"])
            self.assertEqual(payload["output_path"], str(output_path.resolve()))
            self.assertEqual(payload["preflight"]["inputs"][0]["mixtures"], 2)

    def test_live_mode_converts_and_refuses_accidental_overwrite(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "handoff.h5"
            output_path = Path(tmp) / "handoff.mcompo.txt"
            _write_fake_hdf5(input_path)

            client = TestClient(create_app(mock_mode=False))
            response = client.post(
                "/api/convert",
                json={
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "format": "multicompo",
                    "dry_run": False,
                    "overwrite": False,
                    "check": False,
                    "production": False,
                    "warn_unknown_energy_mesh": False,
                    "require_known_energy_mesh": False,
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["converted"])
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)
            self.assertEqual(payload["output_size"], output_path.stat().st_size)
            summary_path = Path(payload["summary_path"])
            self.assertTrue(payload["summary_written"])
            self.assertEqual(summary_path, (Path(tmp) / "convert_summary.json").resolve())
            self.assertTrue(summary_path.exists())
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary_payload["schema"], "openmc2donjon.convert.v1")
            self.assertEqual(summary_payload["writer_backend"], "ascii")
            self.assertEqual(summary_payload["output_path"], str(output_path.resolve()))
            self.assertIn("--summary-json", summary_payload["cli_command"])

            conflict = client.post(
                "/api/convert",
                json={
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "format": "multicompo",
                    "dry_run": False,
                    "overwrite": False,
                    "check": False,
                    "production": False,
                    "warn_unknown_energy_mesh": False,
                    "require_known_energy_mesh": False,
                },
            )
            self.assertEqual(conflict.status_code, 409)
            self.assertIn("already exists", conflict.json()["detail"])

    def test_convert_request_accepts_pygan_writer_backend(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/convert",
            json={
                "input_path": "/mock/home/openmc-runs/c5g7/handoff.h5",
                "format": "multicompo",
                "writer_backend": "pygan",
                "dry_run": True,
                "overwrite": False,
                "check": True,
                "production": False,
                "warn_unknown_energy_mesh": True,
                "require_known_energy_mesh": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["writer_backend"], "pygan")
        self.assertIn("--writer-backend", payload["cli_command"])
        self.assertIn("pygan", payload["cli_command"])

@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class OpenmcWorkflowEndpointTests(unittest.TestCase):
    def test_mock_mode_plans_one_step_openmc_handoff(self) -> None:
        from openmc2donjon.web.openmc_workflow import OPENMC_WORKFLOW_SCHEMA
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/openmc-workflow/plan",
            json={
                "workflow": "one-step",
                "recipe_path": "/mock/home/openmc-runs/export_recipe.py",
                "statepoint_path": "/mock/home/openmc-runs/statepoint.h5",
                "load_statepoint": True,
                "format": "multicompo",
                "output_path": "/mock/home/openmc-runs/out.mcompo.txt",
                "run_dir": "/mock/home/openmc-runs/c5g7",
                "keep_hdf5_path": "/mock/home/openmc-runs/c5g7/mgxs_library.h5",
                "check": True,
                "production": True,
                "strict_dry_run": True,
                "h_factor_default": 200.0,
                "require_known_energy_mesh": True,
                "warn_unknown_energy_mesh": True,
                "equivalence": "direct",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], OPENMC_WORKFLOW_SCHEMA)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["mock_mode"])
        self.assertEqual(payload["workflow"], "one-step")
        self.assertEqual(len(payload["commands"]), 1)
        command = payload["commands"][0]["text"]
        self.assertIn("openmc2donjon-from-openmc", command)
        self.assertIn("--production", command)
        self.assertIn("--strict-dry-run", command)
        self.assertIn("--require-known-energy-mesh", command)
        self.assertIn("--h-factor-default 200.0", command)
        artifact_paths = {artifact["path"] for artifact in payload["artifacts"]}
        self.assertIn("/mock/home/openmc-runs/c5g7/mgxs_library.h5", artifact_paths)

    def test_mock_mode_two_step_plan_has_export_and_convert_commands(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/openmc-workflow/plan",
            json={
                "workflow": "two-step",
                "recipe_path": "/mock/home/openmc-runs/export_recipe.py",
                "statepoint_path": "/mock/home/openmc-runs/statepoint.h5",
                "load_statepoint": True,
                "format": "macrolib",
                "output_path": "/mock/home/openmc-runs/out.macrolib.txt",
                "run_dir": "/mock/home/openmc-runs/c5g7",
                "keep_hdf5_path": "/mock/home/openmc-runs/c5g7/mgxs_library.h5",
                "check": True,
                "production": True,
                "strict_dry_run": False,
                "equivalence": "direct",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        labels = [command["label"] for command in payload["commands"]]
        self.assertEqual(labels, ["Export MGXS HDF5", "Convert HDF5 to ASCII"])
        export_text, convert_text = [command["text"] for command in payload["commands"]]
        self.assertIn("openmc2donjon-export", export_text)
        self.assertIn("openmc2donjon /mock/home/openmc-runs/c5g7/mgxs_library.h5", convert_text)
        self.assertIn("--format macrolib", convert_text)
        self.assertIn("--check", convert_text)
        self.assertIn("--production", convert_text)

    def test_mock_mode_two_step_adf_inserts_augment_command(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/openmc-workflow/plan",
            json={
                "workflow": "two-step",
                "recipe_path": "/mock/home/openmc-runs/export_recipe.py",
                "statepoint_path": "/mock/home/openmc-runs/statepoint.h5",
                "load_statepoint": True,
                "format": "multicompo",
                "output_path": "/mock/home/openmc-runs/out.mcompo.txt",
                "run_dir": "/mock/home/openmc-runs/c5g7",
                "keep_hdf5_path": "/mock/home/openmc-runs/c5g7/mgxs_library.h5",
                "check": True,
                "production": False,
                "equivalence": "adf",
                "adf_source": "/mock/home/openmc-runs/c5g7/adf_sidecar.h5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        labels = [command["label"] for command in payload["commands"]]
        self.assertEqual(labels, ["Export MGXS HDF5", "Augment ADF/DF", "Convert HDF5 to ASCII"])
        augment_text = payload["commands"][1]["text"]
        convert_text = payload["commands"][2]["text"]
        self.assertIn("augment-adf", augment_text)
        self.assertIn("--adf-source /mock/home/openmc-runs/c5g7/adf_sidecar.h5", augment_text)
        self.assertIn("/mock/home/openmc-runs/c5g7/mgxs_library_adf.h5", convert_text)
        artifact_paths = {artifact["path"] for artifact in payload["artifacts"]}
        self.assertIn("/mock/home/openmc-runs/c5g7/mgxs_library_adf.h5", artifact_paths)

    def test_live_mode_reports_missing_recipe_as_not_ready(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        response = client.post(
            "/api/openmc-workflow/plan",
            json={
                "workflow": "one-step",
                "recipe_path": "/definitely/missing/export_recipe.py",
                "statepoint_path": "",
                "load_statepoint": False,
                "format": "multicompo",
                "output_path": "/tmp/out.mcompo.txt",
                "run_dir": "",
                "keep_hdf5_path": "/tmp/mgxs_library.h5",
                "check": True,
                "production": False,
                "equivalence": "direct",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["recipe"]["status"], "fail")
        self.assertIn("not found", checks["recipe"]["message"])
        self.assertEqual(checks["statepoint"]["status"], "skipped")

    def test_workspace_root_rejects_openmc_workflow_paths_outside_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw, tempfile.TemporaryDirectory() as other_raw:
            root = Path(root_raw)
            outside_recipe = Path(other_raw) / "export_recipe.py"
            outside_recipe.write_text("# outside\n", encoding="utf-8")
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.post(
                "/api/openmc-workflow/plan",
                json={
                    "workflow": "one-step",
                    "recipe_path": str(outside_recipe),
                    "statepoint_path": "",
                    "load_statepoint": False,
                    "format": "multicompo",
                    "output_path": str(root / "out.mcompo.txt"),
                    "run_dir": "",
                    "keep_hdf5_path": str(root / "mgxs_library.h5"),
                    "check": True,
                    "production": False,
                    "equivalence": "direct",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["recipe"]["status"], "fail")
        self.assertIn("outside web workspace root", checks["recipe"]["message"])

    def test_workspace_root_tilde_alias_works_for_openmc_workflow_plan(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw:
            root = Path(root_raw)
            (root / "export_recipe.py").write_text("# recipe\n", encoding="utf-8")
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.post(
                "/api/openmc-workflow/plan",
                json={
                    "workflow": "one-step",
                    "recipe_path": "~/export_recipe.py",
                    "statepoint_path": "",
                    "load_statepoint": False,
                    "format": "multicompo",
                    "output_path": "~/out.mcompo.txt",
                    "run_dir": "",
                    "keep_hdf5_path": "~/mgxs_library.h5",
                    "check": True,
                    "production": False,
                    "equivalence": "direct",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["recipe"]["status"], "pass")
        self.assertEqual(checks["ASCII output directory"]["status"], "pass")
        self.assertEqual(checks["HDF5 handoff directory"]["status"], "pass")

    def test_rejects_invalid_h_factor_default(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/openmc-workflow/plan",
            json={
                "workflow": "one-step",
                "recipe_path": "/mock/home/openmc-runs/export_recipe.py",
                "format": "multicompo",
                "h_factor_default": "not-a-number",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("h_factor_default", response.json()["detail"])

@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class BundleInspectEndpointTests(unittest.TestCase):
    def test_mock_mode_returns_c5g7_bundle_manifest_fixture(self) -> None:
        from openmc2donjon.web.bundle import BUNDLE_INSPECT_SCHEMA
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/bundle/inspect",
            params={
                "manifest": "/mock/home/openmc-runs/c5g7/bundle/manifest.json",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], BUNDLE_INSPECT_SCHEMA)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["artifact_count"], 3)
        labels = {artifact["label"] for artifact in payload["artifacts"]}
        self.assertEqual(labels, {"mgxs", "mcompo", "conversion-summary"})
        self.assertEqual(
            payload["donjon_defaults"],
            {
                "format": "multicompo",
                "ascii_path": "/mock/home/openmc-runs/c5g7/bundle/out.mcompo.txt",
                "mixture_count": 9,
                "summary_path": "/mock/home/openmc-runs/c5g7/bundle/convert_summary.json",
                "summary_schema": "openmc2donjon.convert.v1",
                "ok": True,
                "converted": True,
                "dry_run": False,
                "preflight_ok": True,
                "preflight_decision": "mgxs_input_contract_passed",
                "production_requested": True,
            },
        )

    def test_mock_mode_rejects_unknown_bundle_manifest(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/bundle/inspect",
            params={"manifest": "/mock/home/openmc-runs/c5g7/nope.json"},
        )

        self.assertEqual(response.status_code, 404)

        missing_dir = client.get(
            "/api/bundle/inspect",
            params={"manifest": "/mock/home/not-a-run/bundle/manifest.json"},
        )
        self.assertEqual(missing_dir.status_code, 404)

    def test_mock_mode_derives_minicase_bundle_manifest(self) -> None:
        """Any mock run dir's bundle manifest is served, not only c5g7.

        Regression test for the bundle-validation leg 404ing every
        manifest except the hardcoded c5g7 one, which dead-ended the
        OpenMC-SPH minicase chain.
        """

        from openmc2donjon.web.bundle import BUNDLE_INSPECT_SCHEMA
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/bundle/inspect",
            params={
                "manifest": (
                    "/mock/home/openmc-runs/openmc-sph-minicase/bundle/manifest.json"
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], BUNDLE_INSPECT_SCHEMA)
        self.assertTrue(payload["ok"])
        labels = {artifact["label"] for artifact in payload["artifacts"]}
        self.assertIn("mgxs", labels)
        self.assertIn("macrolib", labels)
        defaults = payload["donjon_defaults"]
        # The corrected MACROLIB is the validated DONJON NSPH consume
        # route, so the derived defaults must point at it.
        self.assertEqual(defaults["format"], "macrolib")
        self.assertEqual(
            defaults["ascii_path"],
            "/mock/home/openmc-runs/openmc-sph-minicase/bundle/out.macrolib.txt",
        )
        self.assertEqual(defaults["mixture_count"], 2)

    def test_live_mode_validates_real_bundle_manifest(self) -> None:
        from openmc2donjon.bundle import ArtifactSpec, bundle_artifacts
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = tmp / "mgxs_library.h5"
            source.write_text("mock hdf5 bytes", encoding="utf-8")
            bundle_dir = tmp / "bundle"
            with contextlib.redirect_stdout(io.StringIO()):
                bundle_artifacts(
                    output_dir=bundle_dir,
                    artifacts=[ArtifactSpec("mgxs", source)],
                )

            response = client.get(
                "/api/bundle/inspect",
                params={"manifest": str(bundle_dir / "manifest.json")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["artifact_count"], 1)
        self.assertEqual(payload["artifacts"][0]["label"], "mgxs")
        self.assertTrue(payload["artifacts"][0]["ok"])
        self.assertEqual(payload["messages"], [])
        self.assertIsNone(payload["donjon_defaults"])

    def test_live_mode_reads_convert_summary_for_donjon_defaults(self) -> None:
        from openmc2donjon.bundle import ArtifactSpec, bundle_artifacts
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = tmp / "mgxs_library.h5"
            source.write_text("mock hdf5 bytes", encoding="utf-8")
            mcompo = tmp / "out.mcompo.txt"
            mcompo.write_text("ASCII handoff", encoding="utf-8")
            summary = tmp / "convert_summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.convert.v1",
                        "ok": True,
                        "decision": "openmc2donjon_convert_passed",
                        "converted": True,
                        "dry_run": False,
                        "format": "multicompo",
                        "output_path": "/runs/case/out.mcompo.txt",
                        "preflight_ok": True,
                        "preflight": {
                            "decision": "mgxs_input_contract_passed",
                            "inputs": [
                                {
                                    "path": "/runs/case/mgxs_library.h5",
                                    "mixtures": 9,
                                }
                            ],
                        },
                        "cli_command": [
                            "openmc2donjon",
                            "/runs/case/mgxs_library.h5",
                            "-o",
                            "/runs/case/out.mcompo.txt",
                            "--check",
                            "--production",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            bundle_dir = tmp / "bundle"
            with contextlib.redirect_stdout(io.StringIO()):
                bundle_artifacts(
                    output_dir=bundle_dir,
                    artifacts=[
                        ArtifactSpec("mgxs", source),
                        ArtifactSpec("mcompo", mcompo),
                        ArtifactSpec("conversion-summary", summary),
                    ],
                )

            response = client.get(
                "/api/bundle/inspect",
                params={"manifest": str(bundle_dir / "manifest.json")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["donjon_defaults"],
            {
                "format": "multicompo",
                "ascii_path": "/runs/case/out.mcompo.txt",
                "mixture_count": 9,
                "summary_path": str((bundle_dir / "convert_summary.json").resolve()),
                "summary_schema": "openmc2donjon.convert.v1",
                "ok": True,
                "converted": True,
                "dry_run": False,
                "preflight_ok": True,
                "preflight_decision": "mgxs_input_contract_passed",
                "production_requested": True,
            },
        )

    def test_live_mode_rejects_non_object_manifest_json(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        with tempfile.TemporaryDirectory() as tmp_raw:
            path = Path(tmp_raw) / "manifest.json"
            path.write_text("[]", encoding="utf-8")
            response = client.get(
                "/api/bundle/inspect",
                params={"manifest": str(path)},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("JSON root must be an object", response.json()["detail"])

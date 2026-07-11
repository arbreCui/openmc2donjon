"""FastAPI backend tests split by endpoint family."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.web_test_utils import WEB_AVAILABLE as _WEB_AVAILABLE, TestClient


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class PyGanWebEndpointTests(unittest.TestCase):
    def test_pygan_doctor_endpoint_reports_backend_status(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/pygan/doctor")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "openmc2donjon.pygan-doctor.v1")
        self.assertTrue(payload["mock_mode"])
        self.assertIn("available", payload)
        self.assertIn("modules", payload)

    def test_pygan_doctor_legacy_alias_reports_backend_status(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/pygan-doctor")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "openmc2donjon.pygan-doctor.v1")
        self.assertTrue(payload["mock_mode"])
        self.assertIn("available", payload)
        self.assertIn("modules", payload)

    def test_mock_pygan_compare_writers_endpoint_returns_report(self) -> None:
        from openmc2donjon.web.pygan import PYGAN_COMPARE_WEB_SCHEMA
        from openmc2donjon.web.server import create_app
        from openmc2donjon.writer_compare import WRITER_COMPARISON_SCHEMA

        client = TestClient(create_app(mock_mode=True))
        response = client.post(
            "/api/pygan/compare-writers",
            json={
                "input_h5": "/mock/home/openmc-runs/c5g7/handoff.h5",
                "format": "multicompo",
                "summary_json": "/mock/home/openmc-runs/c5g7/writer_compare.json",
                "keep_dir": "/mock/home/openmc-runs/c5g7/writer_compare",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], WRITER_COMPARISON_SCHEMA)
        self.assertEqual(payload["web_schema"], PYGAN_COMPARE_WEB_SCHEMA)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["mock_mode"])
        self.assertIn("compare-writers", payload["cli_command"])
        self.assertIn("--summary-json", payload["cli_command"])
        self.assertEqual(payload["issue_count"], 0)

    def test_live_pygan_compare_writers_endpoint_dispatches_comparison(self) -> None:
        from openmc2donjon.web.server import create_app
        from openmc2donjon.writer_compare import WriterComparisonReport

        def fake_compare(*args: object, **kwargs: object) -> WriterComparisonReport:
            self.assertEqual(args[0], "input.h5")
            self.assertEqual(kwargs["output_format"], "macrolib")
            self.assertEqual(kwargs["root_name"], "ROOT")
            self.assertEqual(kwargs["mixture_names"], ["M1", "M2"])
            self.assertEqual(kwargs["rtol"], 2.0e-6)
            return WriterComparisonReport(
                input_h5="input.h5",
                output_format="macrolib",
                ok=True,
                rtol=2.0e-6,
                atol=1.0e-8,
                compared_payloads=4,
                compared_real_payloads=2,
                max_abs_diff=0.0,
                max_rel_diff=0.0,
                issues=(),
            )

        client = TestClient(create_app(mock_mode=False))
        with patch("openmc2donjon.web.pygan.compare_writer_backends", side_effect=fake_compare):
            response = client.post(
                "/api/pygan/compare-writers",
                json={
                    "input_h5": "input.h5",
                    "format": "macrolib",
                    "root_name": "ROOT",
                    "mixtures": ["M1", "M2"],
                    "rtol": 2.0e-6,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["format"], "macrolib")
        self.assertFalse(payload["mock_mode"])
        self.assertEqual(payload["compared_payloads"], 4)

@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class CommandCatalogEndpointTests(unittest.TestCase):
    def test_catalog_endpoint_returns_all_cli_commands_plus_direct_convert(self) -> None:
        from openmc2donjon.commands import adf, diagnostics, sph, web
        from openmc2donjon.web.commands import COMMANDS_SCHEMA
        from openmc2donjon.web.server import create_app

        expected_cli_names = {
            spec.name
            for spec in (
                *adf.command_specs(),
                *sph.command_specs(),
                *diagnostics.command_specs(),
                *web.command_specs(),
            )
        }

        client = TestClient(create_app(mock_mode=False))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], COMMANDS_SCHEMA)
        command_ids = {command["id"] for command in payload["commands"]}
        self.assertIn("direct-convert", command_ids)
        self.assertIn("openmc2donjon-export", command_ids)
        self.assertIn("openmc2donjon-from-openmc", command_ids)
        self.assertTrue(
            expected_cli_names <= command_ids,
            f"missing command ids: {sorted(expected_cli_names - command_ids)}",
        )

    def test_catalog_marks_direct_converter_as_ready_web_workflow(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        commands = {command["id"]: command for command in response.json()["commands"]}
        direct = commands["direct-convert"]
        self.assertEqual(direct["status"], "ready")
        self.assertEqual(
            direct["web_path"],
            "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
        )
        self.assertIn("HDF5 handoff", direct["use_when"])
        self.assertIn("DONJON ASCII", direct["produces"])
        self.assertIn("preview", direct["next_step"].lower())
        self.assertIn("MULTICOMPO", direct["tags"])
        self.assertIn("openmc2donjon mgxs_library.h5", direct["cli"])

        check = commands["check"]
        self.assertIn("before converting", check["use_when"])
        self.assertIn("does not write", check["produces"])
        self.assertIn("write the ASCII output", check["next_step"])

    def test_catalog_web_paths_deep_link_to_matching_workflow_surfaces(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        commands = {command["id"]: command for command in response.json()["commands"]}
        self.assertEqual(
            commands["check"]["web_path"],
            "/convert?intent=check&format=multicompo&check=1&production=1",
        )
        self.assertEqual(
            commands["openmc2donjon-export"]["web_path"],
            "/openmc?workflow=two-step",
        )
        self.assertEqual(
            commands["openmc2donjon-from-openmc"]["web_path"],
            "/openmc?workflow=one-step",
        )
        self.assertEqual(
            commands["make-adf-sidecar"]["web_path"],
            "/equivalence?kind=adf-sidecar",
        )
        self.assertEqual(
            commands["augment-adf"]["web_path"],
            "/equivalence?kind=augment-adf",
        )
        self.assertEqual(
            commands["make-sph-sidecar"]["web_path"],
            "/equivalence?kind=sph-sidecar",
        )
        self.assertEqual(
            commands["make-openmc-sph-sidecar"]["web_path"],
            "/equivalence?kind=openmc-sph-sidecar",
        )
        self.assertEqual(
            commands["make-sph-update-table"]["web_path"],
            "/builder?command=make-sph-update-table",
        )
        self.assertEqual(
            commands["augment-sph"]["web_path"],
            "/equivalence?kind=augment-sph",
        )
        self.assertEqual(commands["diff"]["web_path"], "/builder?command=diff")
        self.assertEqual(commands["pygan-doctor"]["web_path"], "/pygan")
        self.assertEqual(
            commands["compare-writers"]["web_path"],
            "/pygan",
        )
        self.assertEqual(commands["doctor"]["web_path"], "/builder?command=doctor")
        self.assertEqual(commands["bundle"]["web_path"], "/builder?command=bundle")
        self.assertEqual(
            commands["make-low-order-driver"]["web_path"],
            "/builder?command=make-low-order-driver",
        )

    def test_catalog_has_a_web_path_for_every_command_except_cli_only(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        missing = [
            command["id"]
            for command in response.json()["commands"]
            if not command.get("web_path")
        ]
        # pygan-inspect-compo has no web surface (no builder spec exists),
        # so it is the only CLI-only entry allowed to omit web_path.
        self.assertEqual(missing, ["pygan-inspect-compo"])

    def test_catalog_statuses_agree_with_coverage_legend(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        commands = {command["id"]: command for command in response.json()["commands"]}

        # serve only has a command builder, and the legend classifies
        # builders as partial, not ready.
        serve = commands["serve"]
        self.assertEqual(serve["status"], "partial")
        self.assertEqual(serve["status_label"], "Command builder ready")
        self.assertEqual(serve["web_path"], "/builder?command=serve")

        # No structured builder spec exists for pygan-inspect-compo, so the
        # catalog must not advertise one; the legend's CLI-only status applies.
        inspect_compo = commands["pygan-inspect-compo"]
        self.assertEqual(inspect_compo["status"], "planned")
        self.assertEqual(inspect_compo["status_label"], "CLI only")
        self.assertIsNone(inspect_compo["web_path"])

    def test_catalog_entries_include_user_guidance(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        for command in response.json()["commands"]:
            with self.subTest(command=command["id"]):
                self.assertIsInstance(command["use_when"], str)
                self.assertIsInstance(command["produces"], str)
                self.assertIsInstance(command["next_step"], str)
                self.assertGreater(len(command["use_when"]), 20)
                self.assertGreater(len(command["produces"]), 20)
                self.assertGreater(len(command["next_step"]), 20)

    def test_catalog_group_counts_are_consistent(self) -> None:
        from collections import Counter

        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        counts = Counter(command["group"] for command in payload["commands"])
        groups = {group["id"]: group for group in payload["groups"]}
        self.assertEqual(set(counts), set(groups))
        for group_id, count in counts.items():
            self.assertEqual(groups[group_id]["command_count"], count)

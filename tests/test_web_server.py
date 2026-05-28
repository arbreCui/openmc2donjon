"""Smoke tests for the openmc2donjon FastAPI backend.

These tests need both the ``[web]`` extra (``fastapi`` /
``uvicorn``) and the ``[dev]`` extra (``httpx`` for
``fastapi.testclient``). When either is missing the tests skip
cleanly so the regular ``tests`` CI job - which only installs the
core package - is not affected. The dedicated ``web-backend`` CI
job installs ``.[web,dev]`` and therefore exercises them.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


try:  # pragma: no cover - import guard exercised via skip path
    from fastapi.testclient import TestClient

    _WEB_AVAILABLE = True
except ImportError:
    _WEB_AVAILABLE = False


def _write_fake_hdf5(path: Path) -> None:
    """Materialise a small HDF5 matching the converter input contract.

    7 groups, 2 mixtures, P0 scatter, no ADF/SPH. Just enough that
    ``inspect_file`` succeeds and ``identify_mesh`` can be exercised.
    """

    import h5py
    import numpy as np

    # CASMO-7 bounds so the catalog match endpoint returns a hit.
    energy_bounds = np.array(
        [10000000.0, 821000.0, 5530.0, 4.0, 0.625, 0.14, 0.058, 9.999999999999999e-06],
        dtype=float,
    )
    ngroups = 7
    with h5py.File(path, "w") as h5:
        h5.attrs["schema_version"] = "openmc2donjon.mgxs.v1"
        h5.attrs["energy_groups"] = ngroups
        h5.attrs["legendre_order"] = 0
        h5.attrs["scatter_axes"] = "moment,from,to"
        h5.create_dataset("energy_bounds", data=energy_bounds)
        mixtures = h5.create_group("mixtures")
        for index, name in enumerate(("M1_UO2", "M2_MOD"), start=1):
            mix = mixtures.create_group(name)
            mix.attrs["volume"] = float(index)
            mix.attrs["temperature"] = 600.0
            mix.attrs["fissionable"] = bool(name == "M1_UO2")
            mix.create_dataset("total", data=np.full(ngroups, 0.5 * index))
            mix.create_dataset("absorption", data=np.full(ngroups, 0.05 * index))
            fission = np.full(ngroups, 0.01 * index)
            chi = np.zeros(ngroups, dtype=float)
            chi[0] = 1.0
            mix.create_dataset("fission", data=fission)
            mix.create_dataset("nu_fission", data=2.5 * fission)
            mix.create_dataset("chi", data=chi)
            mix.create_dataset("transport_total", data=np.full(ngroups, 0.5 * index))
            scatter = np.zeros((1, ngroups, ngroups), dtype=float)
            # Strictly down-scattering diagonal + single off-diagonal.
            for g in range(ngroups):
                scatter[0, g, g] = 0.2 * index
                if g + 1 < ngroups:
                    scatter[0, g, g + 1] = 0.01 * index
            scatter_dataset = mix.create_dataset("scatter_matrix", data=scatter)
            scatter_dataset.attrs["axes"] = "moment,from,to"


def _minimal_openmc_sph_physics_summary() -> dict[str, object]:
    return {
        "schema": "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
        "route": "OpenMC CE reference + OpenMC MG same geometry -> OpenMC-side SPH",
        "handoff_dir": "/tmp/handoff",
        "mixture_count": 2,
        "energy_groups": 33,
        "legendre_order": 3,
        "mixture_names": ["CS_FUEL", "CS_MOD"],
        "decisions": {
            "openmc_sph": "openmc2donjon_openmc_sph_sidecar_passed",
            "sph_augment": "openmc2donjon_sph_augment_passed",
        },
        "normalization": {
            "method": "power",
            "factor": 1.0,
            "formula": "sph = normalized_openmc_mg_flux / openmc_ce_reference_flux",
        },
        "flux_uncertainty": {
            "ce_max_relative_std_dev": 0.01,
            "mg_max_relative_std_dev": 0.02,
            "ce_dataset": "openmc_volume_flux",
            "mg_dataset": "openmc_mg_flux",
        },
        "sph": {
            "kind": "openmc-ce-mg",
            "real": True,
            "applied_to_xs": False,
            "minimum": 0.9,
            "maximum": 1.1,
            "mean": 1.0,
            "max_abs_delta_from_unity": 0.1,
            "clipped_count": 0,
        },
        "handoff": {
            "augmented_hdf5_has_sph": True,
            "ascii_nsp_block_count": 2,
            "ascii_path": "/tmp/handoff/out.mcompo.txt",
            "augmented_hdf5_path": "/tmp/handoff/mgxs_with_sph.h5",
        },
        "per_mixture": [
            {
                "mixture": "CS_FUEL",
                "ce_flux_min": 1.0,
                "ce_flux_max": 2.0,
                "mg_flux_min": 1.0,
                "mg_flux_max": 2.1,
                "normalized_mg_over_ce_min": 0.9,
                "normalized_mg_over_ce_max": 1.1,
                "sph_min": 0.9,
                "sph_max": 1.1,
                "sph_mean": 1.0,
                "max_abs_sph_minus_1": 0.1,
            }
        ],
    }


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class HealthEndpointTests(unittest.TestCase):
    def test_live_mode_payload(self) -> None:
        from openmc2donjon import __version__
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["mock_mode"])
        self.assertEqual(payload["version"], __version__)
        self.assertIn("pygan_backend", payload)
        self.assertIn("available", payload["pygan_backend"])
        self.assertIn("missing_modules", payload["pygan_backend"])
        self.assertEqual(payload["filesystem_scope"]["mode"], "unrestricted")
        self.assertIsNone(payload["filesystem_scope"]["workspace_root"])

    def test_mock_mode_payload(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["mock_mode"])
        self.assertIn("pygan_backend", payload)
        self.assertEqual(payload["filesystem_scope"]["mode"], "mock")
        self.assertIsNone(payload["filesystem_scope"]["workspace_root"])

    def test_workspace_root_payload(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        scope = response.json()["filesystem_scope"]
        self.assertEqual(scope["mode"], "workspace")
        self.assertEqual(scope["workspace_root"], str(root.resolve()))


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class FilesystemScopeEndpointTests(unittest.TestCase):
    def test_workspace_root_allows_inspect_inside_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = root / "handoff.h5"
            _write_fake_hdf5(handoff)
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.get("/api/inspect", params={"path": str(handoff)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["path"], str(handoff.resolve()))

    def test_workspace_root_rejects_inspect_outside_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw, tempfile.TemporaryDirectory() as other_raw:
            outside = Path(other_raw) / "handoff.h5"
            _write_fake_hdf5(outside)
            client = TestClient(create_app(mock_mode=False, workspace_root=Path(root_raw)))
            response = client.get("/api/inspect", params={"path": str(outside)})

        self.assertEqual(response.status_code, 403)
        self.assertIn("outside web workspace root", response.json()["detail"])

    def test_workspace_root_rejects_directory_listing_outside_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw, tempfile.TemporaryDirectory() as other_raw:
            client = TestClient(create_app(mock_mode=False, workspace_root=Path(root_raw)))
            response = client.get("/api/files", params={"path": other_raw})

        self.assertEqual(response.status_code, 403)
        self.assertIn("outside web workspace root", response.json()["detail"])

    def test_workspace_root_tilde_aliases_to_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw:
            root = Path(root_raw)
            (root / "handoff.h5").write_bytes(b"not inspected here")
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.get("/api/files", params={"path": "~"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["path"], str(root.resolve()))
        self.assertIn("handoff.h5", {entry["name"] for entry in payload["entries"]})

    def test_workspace_root_rejects_file_status_outside_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw, tempfile.TemporaryDirectory() as other_raw:
            client = TestClient(create_app(mock_mode=False, workspace_root=Path(root_raw)))
            response = client.get(
                "/api/file-status",
                params={"path": str(Path(other_raw) / "artifact.mcompo.txt")},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("outside web workspace root", response.json()["detail"])

    def test_workspace_root_rejects_text_preview_outside_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw, tempfile.TemporaryDirectory() as other_raw:
            outside = Path(other_raw) / "out.mcompo.txt"
            outside.write_text("ASCII", encoding="utf-8")
            client = TestClient(create_app(mock_mode=False, workspace_root=Path(root_raw)))
            response = client.get("/api/text-preview", params={"path": str(outside)})

        self.assertEqual(response.status_code, 403)
        self.assertIn("outside web workspace root", response.json()["detail"])

    def test_workspace_root_rejects_convert_output_outside_root(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw, tempfile.TemporaryDirectory() as other_raw:
            root = Path(root_raw)
            input_path = root / "handoff.h5"
            _write_fake_hdf5(input_path)
            output_path = Path(other_raw) / "out.mcompo.txt"
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.post(
                "/api/convert",
                json={
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "format": "multicompo",
                    "dry_run": True,
                    "check": False,
                    "production": False,
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("outside web workspace root", response.json()["detail"])

    def test_workspace_root_rejects_bundle_artifact_outside_root(self) -> None:
        from openmc2donjon.bundle import SCHEMA as BUNDLE_SCHEMA
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as root_raw, tempfile.TemporaryDirectory() as other_raw:
            root = Path(root_raw)
            outside = Path(other_raw) / "convert_summary.json"
            outside.write_text("{}", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": BUNDLE_SCHEMA,
                        "artifact_count": 1,
                        "artifacts": [
                            {
                                "label": "conversion-summary",
                                "path": str(outside),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.get(
                "/api/bundle/inspect",
                params={"manifest": str(manifest)},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("outside web workspace root", response.json()["detail"])


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
            "/openmc?intent=export&workflow=two-step",
        )
        self.assertEqual(
            commands["openmc2donjon-from-openmc"]["web_path"],
            "/openmc?intent=from-openmc&workflow=one-step",
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
            "/pygan?tab=compare",
        )
        self.assertEqual(commands["doctor"]["web_path"], "/builder?command=doctor")
        self.assertEqual(commands["bundle"]["web_path"], "/builder?command=bundle")
        self.assertEqual(
            commands["make-low-order-driver"]["web_path"],
            "/builder?command=make-low-order-driver",
        )

    def test_catalog_has_a_web_path_for_every_command(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/commands")

        self.assertEqual(response.status_code, 200)
        missing = [
            command["id"]
            for command in response.json()["commands"]
            if not command.get("web_path")
        ]
        self.assertEqual(missing, [])

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


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class CorsBehaviourTests(unittest.TestCase):
    def test_default_origin_is_allowed_without_configuration(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app())
        response = client.get(
            "/api/health", headers={"Origin": "http://localhost:3000"}
        )

        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )

    def test_extra_origins_are_added_not_replaced(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(
            create_app(extra_origins=("http://example.local:5173",)),
        )
        default_response = client.get(
            "/api/health", headers={"Origin": "http://localhost:3000"}
        )
        extra_response = client.get(
            "/api/health", headers={"Origin": "http://example.local:5173"}
        )

        self.assertEqual(
            default_response.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )
        self.assertEqual(
            extra_response.headers.get("access-control-allow-origin"),
            "http://example.local:5173",
        )

    def test_unlisted_origin_does_not_receive_allow_header(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(
            create_app(extra_origins=("http://example.local:5173",)),
        )
        response = client.get(
            "/api/health", headers={"Origin": "http://evil.example.com"}
        )

        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_extra_origins_are_deduplicated(self) -> None:
        from openmc2donjon.web.server import DEFAULT_CORS_ORIGINS, create_app

        # Passing one of the defaults explicitly must not yield a
        # duplicate entry in the underlying middleware allow-list.
        duplicated = (DEFAULT_CORS_ORIGINS[0], "http://example.local:5173")
        app = create_app(extra_origins=duplicated)

        middleware = next(
            mw for mw in app.user_middleware if mw.cls.__name__ == "CORSMiddleware"
        )
        allow_origins = middleware.kwargs.get("allow_origins")
        self.assertIsNotNone(allow_origins)
        self.assertEqual(
            allow_origins.count(DEFAULT_CORS_ORIGINS[0]),
            1,
            f"default origin appeared twice in {allow_origins!r}",
        )
        self.assertIn("http://example.local:5173", allow_origins)


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class InspectEndpointTests(unittest.TestCase):
    def test_mock_mode_returns_bundled_inspect_fixture(self) -> None:
        from openmc2donjon.web.server import INSPECT_SCHEMA, create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/inspect", params={"path": "/any.h5"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], INSPECT_SCHEMA)
        self.assertEqual(payload["energy_groups"], 7)
        self.assertEqual(payload["legendre_order"], 1)
        self.assertEqual(payload["mixture_count"], 9)
        self.assertEqual(payload["sph_calculations"], 9)
        self.assertEqual(
            tuple(payload["adf_faces"]), ("XMIN", "XMAX", "YMIN", "YMAX")
        )
        self.assertEqual(payload["mesh_match"]["id"], "casmo_7")
        # energy_bounds is required for the S3 spectrum chart X axis.
        bounds = payload["energy_bounds"]
        self.assertEqual(len(bounds), 8)
        self.assertGreater(bounds[0], bounds[-1])  # descending CASMO-7
        # M3-C: peek surface for non-handoff files; mock fixture
        # carries sample values.
        attr_names = {a["name"] for a in payload["root_attrs"]}
        self.assertIn("schema_version", attr_names)
        top_names = {t["name"] for t in payload["top_level_keys"]}
        self.assertEqual(top_names, {"energy_bounds", "mixtures"})
        # M3-D: peek totals + truncation flag.
        self.assertEqual(payload["root_attrs_total"], 5)
        self.assertEqual(payload["top_level_keys_total"], 2)
        self.assertFalse(payload["peek_truncated"])

    def test_mock_mode_returns_bundled_mixture_fixture(self) -> None:
        from openmc2donjon.web.server import MIXTURE_SCHEMA, create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/inspect/mixture",
            params={"path": "/any.h5", "mixture": "M3_MOX_70"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], MIXTURE_SCHEMA)
        self.assertEqual(payload["mixture"], "M3_MOX_70")
        self.assertEqual(len(payload["cross_sections"]["total"]), 7)
        self.assertEqual(payload["scatter"]["shape"], [2, 7, 7])
        self.assertEqual(payload["scatter"]["moment_index"], 0)
        self.assertEqual(len(payload["scatter"]["values"]), 7)
        self.assertEqual(len(payload["scatter"]["values"][0]), 7)

    def test_mock_mode_mixture_endpoint_honors_mixture_param(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/inspect/mixture",
            params={"path": "/any.h5", "mixture": "M1_UO2"},
        )

        self.assertEqual(response.status_code, 200)
        # Same fixture data, but the mixture field reflects the request.
        self.assertEqual(response.json()["mixture"], "M1_UO2")

    def test_mock_mode_mixture_endpoint_rejects_unknown_mixture(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/inspect/mixture",
            params={"path": "/any.h5", "mixture": "NOT_REAL"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"])

    def test_mock_mode_mixture_endpoint_returns_scaled_p1(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        p0 = client.get(
            "/api/inspect/mixture",
            params={"path": "/any.h5", "mixture": "M3_MOX_70", "moment": 0},
        ).json()
        p1 = client.get(
            "/api/inspect/mixture",
            params={"path": "/any.h5", "mixture": "M3_MOX_70", "moment": 1},
        ).json()

        self.assertEqual(p0["scatter"]["moment_index"], 0)
        self.assertEqual(p1["scatter"]["moment_index"], 1)
        # P1 is a scaled clone, same shape.
        self.assertEqual(
            len(p1["scatter"]["values"]), len(p0["scatter"]["values"])
        )
        # Find a non-zero element in P0 and confirm P1 = 0.1 * P0 there.
        for row_p0, row_p1 in zip(
            p0["scatter"]["values"], p1["scatter"]["values"], strict=True
        ):
            for v0, v1 in zip(row_p0, row_p1, strict=True):
                if v0 != 0.0:
                    self.assertAlmostEqual(v1, 0.1 * v0, places=8)
                    return
        self.fail("expected at least one non-zero P0 entry in mock fixture")

    def test_mock_mode_non_fissionable_mixture_nulls_fission_family(
        self,
    ) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        # M5_MOD is the moderator in the handoff fixture
        # (``fissionable: false``) - the mock branch should strip the
        # fission family so the spectrum chart's zero-series guard and
        # the scatter heatmap both get exercised against a realistic
        # non-fissionable shape.
        response = client.get(
            "/api/inspect/mixture",
            params={"path": "/any.h5", "mixture": "M5_MOD"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        xs = payload["cross_sections"]
        self.assertIsNotNone(xs["total"])
        self.assertIsNotNone(xs["absorption"])
        self.assertIsNone(xs["fission"])
        self.assertIsNone(xs["nu_fission"])
        self.assertIsNone(xs["chi"])
        # Scatter remains present (moderator absolutely scatters).
        self.assertIsNotNone(payload["scatter"])
        self.assertEqual(len(payload["scatter"]["values"]), 7)

    def test_mock_mode_fissionable_mixture_keeps_fission_family(
        self,
    ) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        # M3_MOX_70 is fissionable in the handoff fixture - the mock
        # branch must not strip its fission family.
        response = client.get(
            "/api/inspect/mixture",
            params={"path": "/any.h5", "mixture": "M3_MOX_70"},
        )
        self.assertEqual(response.status_code, 200)
        xs = response.json()["cross_sections"]
        self.assertIsNotNone(xs["fission"])
        self.assertIsNotNone(xs["nu_fission"])
        self.assertIsNotNone(xs["chi"])

    def test_mock_mode_mixture_endpoint_rejects_out_of_range_moment(
        self,
    ) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/inspect/mixture",
            params={
                "path": "/any.h5",
                "mixture": "M3_MOX_70",
                "moment": 2,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("scatter moment", response.json()["detail"])

    def test_live_mode_path_not_found_returns_404(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        response = client.get(
            "/api/inspect",
            params={"path": "/definitely/does/not/exist.h5"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"])

    def test_live_mode_non_hdf5_returns_400(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False
        ) as fh:
            fh.write("definitely not an hdf5 file")
            text_path = fh.name
        try:
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/inspect", params={"path": text_path})
            self.assertEqual(response.status_code, 400)
            self.assertIn("not an HDF5", response.json()["detail"])
        finally:
            Path(text_path).unlink(missing_ok=True)

    def test_live_mode_inspect_real_file(self) -> None:
        from openmc2donjon.web.server import INSPECT_SCHEMA, create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff.h5"
            _write_fake_hdf5(path)

            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/inspect", params={"path": str(path)})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["schema"], INSPECT_SCHEMA)
            self.assertEqual(payload["energy_groups"], 7)
            self.assertEqual(payload["mixture_count"], 2)
            self.assertEqual(payload["std_dev_datasets"], 0)
            self.assertEqual(payload["std_dev_expected_datasets"], 14)
            self.assertIsNotNone(payload["mesh_match"])
            self.assertEqual(payload["mesh_match"]["id"], "casmo_7")
            mixture_names = sorted(m["name"] for m in payload["mixtures"])
            self.assertEqual(mixture_names, ["M1_UO2", "M2_MOD"])
            # energy_bounds is read from the same h5 open as the mesh ID.
            self.assertEqual(len(payload["energy_bounds"]), 8)
            self.assertAlmostEqual(payload["energy_bounds"][0], 10000000.0)

    def test_live_mode_mixture_endpoint_returns_arrays(self) -> None:
        from openmc2donjon.web.server import MIXTURE_SCHEMA, create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff.h5"
            _write_fake_hdf5(path)
            client = TestClient(create_app(mock_mode=False))

            response = client.get(
                "/api/inspect/mixture",
                params={"path": str(path), "mixture": "M1_UO2"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["schema"], MIXTURE_SCHEMA)
            self.assertEqual(payload["mixture"], "M1_UO2")
            self.assertEqual(payload["energy_groups"], 7)
            self.assertEqual(len(payload["cross_sections"]["total"]), 7)
            self.assertEqual(payload["scatter"]["shape"], [1, 7, 7])
            self.assertEqual(len(payload["scatter"]["values"]), 7)

    def test_live_mode_mixture_not_found_returns_404(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff.h5"
            _write_fake_hdf5(path)
            client = TestClient(create_app(mock_mode=False))

            response = client.get(
                "/api/inspect/mixture",
                params={"path": str(path), "mixture": "NOT_A_MIXTURE"},
            )
            self.assertEqual(response.status_code, 404)
            self.assertIn("not found", response.json()["detail"])

    def test_live_mode_inspect_peek_surfaces_non_handoff_structure(
        self,
    ) -> None:
        """A non-MGXS HDF5 should still produce a useful peek payload.

        Files like boundary-currents exports show ``ok=false`` because
        they have no ``/mixtures`` group, but the user still benefits
        from seeing the top-level groups and root attrs - that's how
        they identify "ah, this is an OpenMC tally export".
        """

        import h5py
        import numpy as np

        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "currents.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["source"] = "OpenMC surface current export"
                h5.attrs["batches"] = 20
                h5.attrs["particles"] = 1000
                h5.create_dataset(
                    "energy_bounds",
                    data=np.array([1e7, 1e6, 1e5, 1e4, 1.0], dtype=float),
                )
                h5.create_group("boundary_currents")
                h5.create_group("surface_flux")

            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/inspect", params={"path": str(path)})
            self.assertEqual(response.status_code, 200)
            payload = response.json()

            self.assertFalse(payload["ok"])
            self.assertEqual(payload["mixture_count"], 0)

            attrs = {a["name"]: a["value"] for a in payload["root_attrs"]}
            self.assertEqual(attrs["source"], "OpenMC surface current export")
            self.assertEqual(attrs["batches"], 20)
            self.assertEqual(attrs["particles"], 1000)

            top = {t["name"]: t for t in payload["top_level_keys"]}
            self.assertEqual(top["boundary_currents"]["kind"], "group")
            self.assertEqual(top["surface_flux"]["kind"], "group")
            self.assertEqual(top["energy_bounds"]["kind"], "dataset")
            self.assertEqual(top["energy_bounds"]["shape"], [5])

    def test_live_mode_inspect_peek_caps_root_attrs_and_reports_total(
        self,
    ) -> None:
        """A pathological HDF5 with hundreds of attrs must not flood the
        peek payload; the cap kicks in and the total stays honest."""

        import h5py

        from openmc2donjon.web.server import (
            _PEEK_MAX_ROOT_ATTRS,
            create_app,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "many_attrs.h5"
            with h5py.File(path, "w") as h5:
                for index in range(_PEEK_MAX_ROOT_ATTRS + 10):
                    h5.attrs[f"attr_{index:03d}"] = index
                h5.create_group("only")

            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/inspect", params={"path": str(path)})
            self.assertEqual(response.status_code, 200)
            payload = response.json()

            self.assertEqual(len(payload["root_attrs"]), _PEEK_MAX_ROOT_ATTRS)
            self.assertEqual(
                payload["root_attrs_total"], _PEEK_MAX_ROOT_ATTRS + 10
            )
            self.assertEqual(payload["top_level_keys_total"], 1)
            self.assertTrue(payload["peek_truncated"])

    def test_live_mode_scatter_moment_out_of_range_returns_404(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff.h5"
            _write_fake_hdf5(path)
            client = TestClient(create_app(mock_mode=False))

            response = client.get(
                "/api/inspect/mixture",
                params={"path": str(path), "mixture": "M1_UO2", "moment": 3},
            )
            self.assertEqual(response.status_code, 404)
            self.assertIn("scatter moment", response.json()["detail"])


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class OpenMCSphPhysicsSummaryEndpointTests(unittest.TestCase):
    def test_mock_mode_returns_bundled_openmc_sph_physics_summary(self) -> None:
        from openmc2donjon.web.openmc_sph_summary import (
            OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA,
        )
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/openmc-sph-summary",
            params={"path": "/mock/home/openmc-runs/openmc-sph-minicase/physics_summary.json"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA)
        self.assertEqual(payload["mixture_count"], 3)
        self.assertEqual(payload["energy_groups"], 33)
        self.assertEqual(payload["legendre_order"], 3)
        self.assertEqual(payload["sph"]["kind"], "openmc-ce-mg")
        self.assertTrue(payload["handoff"]["augmented_hdf5_has_sph"])
        self.assertGreater(payload["handoff"]["ascii_nsp_block_count"], 0)

    def test_live_mode_reads_openmc_sph_physics_summary_json(self) -> None:
        from openmc2donjon.web.openmc_sph_summary import (
            OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA,
        )
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "physics_summary.json"
            path.write_text(
                json.dumps(_minimal_openmc_sph_physics_summary()),
                encoding="utf-8",
            )
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/openmc-sph-summary", params={"path": str(path)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA)
        self.assertEqual(payload["requested_path"], str(path.resolve()))
        self.assertEqual(payload["mixture_names"], ["CS_FUEL", "CS_MOD"])

    def test_live_mode_rejects_non_summary_json(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "not_summary.json"
            path.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/openmc-sph-summary", params={"path": str(path)})

        self.assertEqual(response.status_code, 422)
        self.assertIn("invalid OpenMC SPH physics summary", response.json()["detail"])


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class FilesEndpointTests(unittest.TestCase):
    def test_live_mode_lists_real_directory(self) -> None:
        from openmc2donjon.web.server import FILES_SCHEMA, create_app

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "alpha.h5").write_bytes(b"x" * 16)
            (base / "beta.txt").write_text("hello")
            (base / "child").mkdir()

            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/files", params={"path": str(base)})
            self.assertEqual(response.status_code, 200)
            payload = response.json()

            self.assertEqual(payload["schema"], FILES_SCHEMA)
            self.assertEqual(payload["path"], str(base.resolve()))
            self.assertEqual(payload["parent"], str(base.resolve().parent))
            names = sorted(entry["name"] for entry in payload["entries"])
            self.assertEqual(names, ["alpha.h5", "beta.txt", "child"])

            kinds = {e["name"]: e["kind"] for e in payload["entries"]}
            self.assertEqual(kinds["alpha.h5"], "file")
            self.assertEqual(kinds["beta.txt"], "file")
            self.assertEqual(kinds["child"], "dir")

            sizes = {e["name"]: e["size"] for e in payload["entries"]}
            self.assertEqual(sizes["alpha.h5"], 16)
            self.assertIsNone(sizes["child"])

    def test_live_mode_returns_404_for_missing_path(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=False))
        response = client.get(
            "/api/files", params={"path": "/definitely/not/here"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"])

    def test_live_mode_returns_400_when_path_is_a_file(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
            fh.write(b"not a directory")
            tmppath = fh.name
        try:
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/files", params={"path": tmppath})
            self.assertEqual(response.status_code, 400)
            self.assertIn("not a directory", response.json()["detail"])
        finally:
            Path(tmppath).unlink(missing_ok=True)

    def test_mock_mode_root_returns_top_level_entries(self) -> None:
        from openmc2donjon.web.server import FILES_SCHEMA, create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/files", params={"path": "/mock/home"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["schema"], FILES_SCHEMA)
        self.assertEqual(payload["path"], "/mock/home")
        # ``/mock/home``'s naive Path parent would be ``/mock`` which is
        # not in the tree; the endpoint reports None so the frontend
        # disables the up-button instead of offering a 404 trap.
        self.assertIsNone(payload["parent"])
        names = [entry["name"] for entry in payload["entries"]]
        self.assertIn("openmc-runs", names)
        self.assertIn("scratch", names)

    def test_mock_mode_nested_dir_parent_points_back_into_tree(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/files",
            params={"path": "/mock/home/openmc-runs"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["path"], "/mock/home/openmc-runs")
        self.assertEqual(payload["parent"], "/mock/home")

    def test_mock_mode_normalizes_trailing_slash(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/files", params={"path": "~/openmc-runs/"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["path"], "/mock/home/openmc-runs")

    def test_mock_mode_lists_nested_directory_with_h5_files(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/files",
            params={"path": "/mock/home/openmc-runs/c5g7"},
        )
        self.assertEqual(response.status_code, 200)
        names = [entry["name"] for entry in response.json()["entries"]]
        self.assertIn("handoff.h5", names)
        self.assertIn("handoff_aug.h5", names)

    def test_mock_mode_unknown_path_returns_404(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/files", params={"path": "/mock/home/does/not/exist"}
        )
        self.assertEqual(response.status_code, 404)

    def test_mock_mode_tilde_aliases_to_home(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/files", params={"path": "~"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["path"], "/mock/home")

    def test_mock_mode_lists_openmc_side_sph_minicase_files(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/files",
            params={"path": "/mock/home/openmc-runs/openmc-sph-minicase"},
        )
        self.assertEqual(response.status_code, 200)
        names = {entry["name"] for entry in response.json()["entries"]}
        self.assertIn("mgxs_library.h5", names)
        self.assertIn("openmc_ce_flux.h5", names)
        self.assertIn("openmc_mg_flux.h5", names)
        self.assertIn("mgxs_with_openmc_sph.h5", names)
        self.assertIn("physics_summary.json", names)


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class FileStatusEndpointTests(unittest.TestCase):
    def test_live_mode_reports_file_directory_and_missing_path(self) -> None:
        from openmc2donjon.web.server import FILE_STATUS_SCHEMA, create_app

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            file_path = base / "artifact.mcompo.txt"
            file_path.write_text("ascii handoff")

            client = TestClient(create_app(mock_mode=False))

            file_response = client.get(
                "/api/file-status", params={"path": str(file_path)}
            )
            self.assertEqual(file_response.status_code, 200)
            file_payload = file_response.json()
            self.assertEqual(file_payload["schema"], FILE_STATUS_SCHEMA)
            self.assertTrue(file_payload["exists"])
            self.assertEqual(file_payload["kind"], "file")
            self.assertEqual(file_payload["size"], len("ascii handoff"))
            self.assertIsNone(file_payload["detail"])

            dir_response = client.get("/api/file-status", params={"path": str(base)})
            self.assertEqual(dir_response.status_code, 200)
            dir_payload = dir_response.json()
            self.assertTrue(dir_payload["exists"])
            self.assertEqual(dir_payload["kind"], "dir")
            self.assertIsNone(dir_payload["size"])

            missing_response = client.get(
                "/api/file-status", params={"path": str(base / "missing.h5")}
            )
            self.assertEqual(missing_response.status_code, 200)
            missing_payload = missing_response.json()
            self.assertFalse(missing_payload["exists"])
            self.assertEqual(missing_payload["kind"], "missing")
            self.assertIn("not found", missing_payload["detail"])

    def test_mock_mode_reports_tree_entries(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))

        dir_response = client.get("/api/file-status", params={"path": "~"})
        self.assertEqual(dir_response.status_code, 200)
        self.assertEqual(dir_response.json()["path"], "/mock/home")
        self.assertEqual(dir_response.json()["kind"], "dir")

        file_response = client.get(
            "/api/file-status",
            params={"path": "/mock/home/openmc-runs/c5g7/handoff.h5"},
        )
        self.assertEqual(file_response.status_code, 200)
        file_payload = file_response.json()
        self.assertTrue(file_payload["exists"])
        self.assertEqual(file_payload["kind"], "file")
        self.assertEqual(file_payload["size"], 832_000)

        missing_response = client.get(
            "/api/file-status",
            params={"path": "/mock/home/openmc-runs/c5g7/out.mcompo.txt"},
        )
        self.assertEqual(missing_response.status_code, 200)
        self.assertFalse(missing_response.json()["exists"])
        self.assertEqual(missing_response.json()["kind"], "missing")


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class TextPreviewEndpointTests(unittest.TestCase):
    def test_mock_mode_returns_ascii_output_preview(self) -> None:
        from openmc2donjon.web.server import TEXT_PREVIEW_SCHEMA, create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/text-preview",
            params={"path": "/mock/home/openmc-runs/c5g7/handoff.mcompo.txt"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], TEXT_PREVIEW_SCHEMA)
        self.assertEqual(payload["path"], "/mock/home/openmc-runs/c5g7/handoff.mcompo.txt")
        self.assertIn("L_MULTICOMPO", payload["text"])
        self.assertIn("SCAT00", payload["text"])
        self.assertFalse(payload["truncated"])

    def test_live_mode_caps_text_preview_by_lines(self) -> None:
        from openmc2donjon.web.server import TEXT_PREVIEW_SCHEMA, create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.mcompo.txt"
            path.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")

            client = TestClient(create_app(mock_mode=False))
            response = client.get(
                "/api/text-preview",
                params={"path": str(path), "max_bytes": 64, "max_lines": 2},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], TEXT_PREVIEW_SCHEMA)
        self.assertEqual(payload["text"], "line-1\nline-2")
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["truncated_by"], ["lines"])
        self.assertEqual(payload["displayed_lines"], 2)

    def test_live_mode_rejects_binary_preview(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "binary.dat"
            path.write_bytes(b"abc\x00def")

            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/text-preview", params={"path": str(path)})

        self.assertEqual(response.status_code, 400)
        self.assertIn("binary", response.json()["detail"])


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
        self.assertEqual(
            payload["summary_path"],
            "/mock/home/openmc-runs/c5g7/convert_summary.json",
        )
        self.assertEqual(payload["preflight"]["inputs"][0]["energy_mesh_id"], "casmo_7")

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
        self.assertEqual(labels, ["Export MGXS HDF5", "Inject ADF/DF", "Convert HDF5 to ASCII"])
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


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")

class UvicornLogLevelMappingTests(unittest.TestCase):
    def _ns(self, **kwargs: object) -> object:
        import argparse

        defaults: dict[str, object] = {
            "verbose": 0,
            "quiet": False,
            "log_level": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_default_is_info(self) -> None:
        from openmc2donjon.commands.web import _uvicorn_log_level

        self.assertEqual(_uvicorn_log_level(self._ns()), "info")

    def test_quiet_maps_to_error(self) -> None:
        from openmc2donjon.commands.web import _uvicorn_log_level

        self.assertEqual(_uvicorn_log_level(self._ns(quiet=True)), "error")

    def test_double_verbose_maps_to_debug(self) -> None:
        from openmc2donjon.commands.web import _uvicorn_log_level

        self.assertEqual(_uvicorn_log_level(self._ns(verbose=2)), "debug")

    def test_explicit_log_level_overrides_everything(self) -> None:
        from openmc2donjon.commands.web import _uvicorn_log_level

        self.assertEqual(
            _uvicorn_log_level(
                self._ns(verbose=2, quiet=True, log_level="WARNING"),
            ),
            "warning",
        )

    def test_loopback_host_detection(self) -> None:
        from openmc2donjon.commands.web import _is_loopback_host

        self.assertTrue(_is_loopback_host("localhost"))
        self.assertTrue(_is_loopback_host("127.0.0.1"))
        self.assertTrue(_is_loopback_host("[::1]"))
        self.assertFalse(_is_loopback_host("0.0.0.0"))
        self.assertFalse(_is_loopback_host("192.168.1.10"))

    def test_non_loopback_live_mode_requires_workspace_or_explicit_unsafe(self) -> None:
        from openmc2donjon.commands.web import _requires_workspace_guard

        self.assertTrue(
            _requires_workspace_guard(
                host="0.0.0.0",
                mock=False,
                workspace_root=None,
                unsafe_remote=False,
            )
        )
        self.assertFalse(
            _requires_workspace_guard(
                host="127.0.0.1",
                mock=False,
                workspace_root=None,
                unsafe_remote=False,
            )
        )
        self.assertFalse(
            _requires_workspace_guard(
                host="0.0.0.0",
                mock=True,
                workspace_root=None,
                unsafe_remote=False,
            )
        )
        self.assertFalse(
            _requires_workspace_guard(
                host="0.0.0.0",
                mock=False,
                workspace_root=Path("/tmp"),
                unsafe_remote=False,
            )
        )
        self.assertFalse(
            _requires_workspace_guard(
                host="0.0.0.0",
                mock=False,
                workspace_root=None,
                unsafe_remote=True,
            )
        )


if __name__ == "__main__":
    unittest.main()

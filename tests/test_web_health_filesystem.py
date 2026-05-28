"""FastAPI backend tests split by endpoint family."""

from __future__ import annotations

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

    def test_directory_listing_is_capped_for_large_live_directories(self) -> None:
        from openmc2donjon.web.server import FILES_ENTRY_LIMIT, create_app

        with tempfile.TemporaryDirectory() as root_raw:
            root = Path(root_raw)
            for index in range(FILES_ENTRY_LIMIT + 7):
                (root / f"artifact_{index:04d}.h5").write_bytes(b"HDF5")
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.get("/api/files", params={"path": "~"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["entries"]), FILES_ENTRY_LIMIT)
        self.assertEqual(payload["total_entries"], FILES_ENTRY_LIMIT + 7)
        self.assertEqual(payload["entry_limit"], FILES_ENTRY_LIMIT)
        self.assertTrue(payload["truncated"])

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

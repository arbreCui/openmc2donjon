"""Smoke tests for the openmc2donjon FastAPI backend.

These tests need both the ``[web]`` extra (``fastapi`` /
``uvicorn``) and the ``[dev]`` extra (``httpx`` for
``fastapi.testclient``). When either is missing the tests skip
cleanly so the regular ``tests`` CI job - which only installs the
core package - is not affected. The dedicated ``web-backend`` CI
job installs ``.[web,dev]`` and therefore exercises them.
"""

from __future__ import annotations

import unittest


try:  # pragma: no cover - import guard exercised via skip path
    from fastapi.testclient import TestClient

    _WEB_AVAILABLE = True
except ImportError:
    _WEB_AVAILABLE = False


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

    def test_mock_mode_payload(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["mock_mode"])


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


if __name__ == "__main__":
    unittest.main()

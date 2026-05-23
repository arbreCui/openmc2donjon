"""Smoke tests for the openmc2donjon FastAPI backend.

These tests need both the ``[web]`` extra (``fastapi`` /
``uvicorn``) and the ``[dev]`` extra (``httpx`` for
``fastapi.testclient``). When either is missing the tests skip
cleanly so the regular ``tests`` CI job - which only installs the
core package - is not affected. The dedicated ``web-backend`` CI
job installs ``.[web,dev]`` and therefore exercises them.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


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
            scatter = np.zeros((1, ngroups, ngroups), dtype=float)
            # Strictly down-scattering diagonal + single off-diagonal.
            for g in range(ngroups):
                scatter[0, g, g] = 0.2 * index
                if g + 1 < ngroups:
                    scatter[0, g, g + 1] = 0.01 * index
            scatter_dataset = mix.create_dataset("scatter_matrix", data=scatter)
            scatter_dataset.attrs["axes"] = "moment,from,to"


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

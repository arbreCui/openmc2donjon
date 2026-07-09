"""FastAPI backend tests split by endpoint family."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.web_test_utils import (
    WEB_AVAILABLE as _WEB_AVAILABLE,
    TestClient,
    minimal_openmc_sph_physics_summary as _minimal_openmc_sph_physics_summary,
    write_fake_hdf5 as _write_fake_hdf5,
)


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
            # energy_bounds is read from the same h5 open as the mesh ID
            # (ascending low-to-high per the HDF5 input contract).
            self.assertEqual(len(payload["energy_bounds"]), 8)
            self.assertAlmostEqual(payload["energy_bounds"][0], 9.999999999999999e-06)
            self.assertAlmostEqual(payload["energy_bounds"][-1], 10000000.0)

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
        self.assertEqual(payload["mixture_count"], 2)
        self.assertEqual(payload["mixture_names"], ["CS_FUEL", "CS_MOD"])
        self.assertEqual(payload["energy_groups"], 33)
        self.assertEqual(payload["legendre_order"], 3)
        self.assertEqual(
            payload["quality"]["decision"],
            "openmc_ce_mg_sph_production_quality",
        )
        self.assertEqual(payload["sph"]["kind"], "openmc-ce-mg")
        self.assertEqual(payload["sph"]["clipped_count"], 0)
        self.assertTrue(payload["handoff"]["augmented_hdf5_has_sph"])
        self.assertGreater(payload["handoff"]["ascii_nsp_block_count"], 0)
        self.assertEqual(payload["donjon_consumption"]["target_mix"], 1)
        self.assertAlmostEqual(
            payload["donjon_consumption"]["expected_g1"],
            1.11109312,
        )

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

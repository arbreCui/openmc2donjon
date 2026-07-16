"""FastAPI backend tests split by endpoint family."""

from __future__ import annotations

import hashlib
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
        self.assertTrue(payload["mock_mode"])
        self.assertEqual(payload["schema"], INSPECT_SCHEMA)
        # Mock mode echoes the requested path so the result header names
        # the file the user asked for.
        self.assertEqual(payload["path"], "/any.h5")
        self.assertEqual(payload["energy_groups"], 7)
        self.assertEqual(payload["legendre_order"], 1)
        self.assertEqual(payload["mixture_count"], 9)
        # File-level state points agree with the per-mixture rows, and
        # the uncertainty story matches mock convert's preflight
        # (uncertainty checked 72/72 for the same demo file).
        self.assertEqual(payload["state_points"], 1)
        self.assertEqual(payload["std_dev_datasets"], 72)
        self.assertEqual(payload["std_dev_expected_datasets"], 72)
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
        self.assertEqual(payload["openmc_provenance"]["status"], "legacy")
        self.assertFalse(
            payload["openmc_provenance"]["capabilities"]["reference_bound"]
        )

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

    def test_mock_mode_mixture_detail_matches_roster_volume(self) -> None:
        """Per-mixture detail must agree with the handoff roster rows.

        Regression test for the mock detail card serving the canned
        M3_MOX_70 volume (9.6) for mixtures whose roster row says
        otherwise (e.g. M7_REFL is 96.0).
        """

        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        handoff = client.get("/api/inspect", params={"path": "/any.h5"}).json()
        roster = {mix["name"]: mix["volume"] for mix in handoff["mixtures"]}

        for name in ("M7_REFL", "M5_MOD", "M3_MOX_70"):
            detail = client.get(
                "/api/inspect/mixture",
                params={"path": "/any.h5", "mixture": name},
            ).json()
            self.assertEqual(detail["volume"], roster[name])

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
            self.assertFalse(payload["mock_mode"])
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

    def test_live_mode_reports_pre_applied_sph_provenance(self) -> None:
        import h5py

        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sph_applied.h5"
            _write_fake_hdf5(path)
            with h5py.File(path, "a") as h5:
                h5.attrs["sph_applied"] = True
                h5.attrs["sph_applied_source"] = "/runs/openmc_sph.h5"
                h5.attrs["sph_apply_operator"] = "divide-xs-by-nsph"
                h5.attrs["sph_kind"] = "openmc-ce-mg-rate"

            payload = (
                TestClient(create_app(mock_mode=False))
                .get("/api/inspect", params={"path": str(path)})
                .json()
            )

            self.assertTrue(payload["sph_applied"])
            self.assertEqual(payload["sph_applied_source"], "/runs/openmc_sph.h5")
            self.assertEqual(payload["sph_apply_operator"], "divide-xs-by-nsph")
            self.assertEqual(payload["sph_kind"], "openmc-ce-mg-rate")
            self.assertEqual(payload["sph_calculations"], 0)

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
            self.assertEqual(payload["scatter"]["axes"], "moment,from,to")
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
            self.assertEqual(payload["openmc_provenance"]["status"], "legacy")
            self.assertFalse(payload["openmc_provenance"]["integrity"]["ok"])

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
        # The demo preset and the summary card must name the same
        # corrected artifacts: the fixture points at the flat minicase
        # paths, not a nonexistent handoff/ subdirectory.
        self.assertEqual(
            payload["handoff"]["ascii_path"],
            "/mock/home/openmc-runs/openmc-sph-minicase/out.macrolib.txt",
        )
        self.assertEqual(
            payload["handoff"]["augmented_hdf5_path"],
            "/mock/home/openmc-runs/openmc-sph-minicase/mgxs_with_openmc_sph.h5",
        )
        self.assertEqual(payload["evidence_audit"]["origin"], "mock_fixture")
        self.assertIsNone(
            payload["evidence_audit"]["all_referenced_handoff_artifacts_present"]
        )
        self.assertEqual(
            payload["evidence_audit"]["physics_acceptance"],
            "not_evaluated",
        )

    def test_mock_summary_fixture_paths_exist_in_mock_tree(self) -> None:
        """Every /mock path in the fixture resolves in the mock browser.

        Regression test for the fixture's artifact paths 404ing in the
        mock file browser (handoff/ and mg_case_iterNN directories that
        never existed in the mock tree).
        """

        import re

        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        payload = client.get(
            "/api/openmc-sph-summary",
            params={"path": "/mock/home/openmc-runs/openmc-sph-minicase/physics_summary.json"},
        ).json()
        paths = sorted(
            {
                match.split("::")[0]
                for match in re.findall(r"/mock/[^\"]*", json.dumps(payload))
            }
        )
        self.assertTrue(paths)
        missing = [
            path
            for path in paths
            if not client.get("/api/file-status", params={"path": path}).json()[
                "exists"
            ]
        ]
        self.assertEqual(missing, [])

    def test_live_mode_reads_openmc_sph_physics_summary_json(self) -> None:
        from openmc2donjon.web.openmc_sph_summary import (
            OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA,
        )
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "physics_summary.json"
            payload_on_disk = _minimal_openmc_sph_physics_summary()
            handoff = payload_on_disk["handoff"]
            augmented = Path(tmp) / "mgxs_with_openmc_sph.h5"
            ascii_path = Path(tmp) / "out.macrolib.txt"
            augmented.write_bytes(b"hdf5")
            ascii_path.write_text("ASCII", encoding="utf-8")
            handoff["augmented_hdf5_path"] = str(augmented)
            handoff["ascii_path"] = str(ascii_path)
            path.write_text(json.dumps(payload_on_disk), encoding="utf-8")
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/openmc-sph-summary", params={"path": str(path)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA)
        self.assertEqual(payload["requested_path"], str(path.resolve()))
        self.assertEqual(payload["mixture_names"], ["CS_FUEL", "CS_MOD"])
        self.assertEqual(payload["evidence_audit"]["origin"], "live_file")
        self.assertTrue(
            payload["evidence_audit"]["all_referenced_handoff_artifacts_present"]
        )
        self.assertTrue(
            all(
                item["status"] == "present"
                for item in payload["evidence_audit"]["referenced_handoff_artifacts"]
            )
        )

    def test_live_summary_marks_stale_referenced_artifacts_missing(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "physics_summary.json"
            payload_on_disk = _minimal_openmc_sph_physics_summary()
            payload_on_disk["handoff"]["augmented_hdf5_path"] = str(
                Path(tmp) / "missing_sph.h5"
            )
            payload_on_disk["handoff"]["ascii_path"] = str(
                Path(tmp) / "missing.macrolib.txt"
            )
            path.write_text(json.dumps(payload_on_disk), encoding="utf-8")
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/openmc-sph-summary", params={"path": str(path)})

        self.assertEqual(response.status_code, 200)
        audit = response.json()["evidence_audit"]
        self.assertFalse(audit["all_referenced_handoff_artifacts_present"])
        self.assertEqual(
            [item["status"] for item in audit["referenced_handoff_artifacts"]],
            ["missing", "missing"],
        )

    def test_live_mode_rejects_unbound_native_dragon_sph_declarations(self) -> None:
        from openmc2donjon.web.openmc_sph_summary import (
            NATIVE_DRAGON_SPH_PHYSICS_SUMMARY_SCHEMA,
        )
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_on_disk = _minimal_openmc_sph_physics_summary()
            payload_on_disk["schema"] = NATIVE_DRAGON_SPH_PHYSICS_SUMMARY_SCHEMA
            payload_on_disk["quality"] = {
                "decision": "native_sph_physics_passed",
                "structural_passed": True,
                "production_ready": True,
                "demonstration_quality": True,
                "max_flux_relative_std_dev": 0.09,
                "production_flux_relative_std_dev_threshold": 0.1,
                "demonstration_flux_relative_std_dev_threshold": 0.2,
                "notes": [],
            }
            payload_on_disk["handoff"]["augmented_hdf5_has_sph"] = False
            artifacts = {
                "augmented_hdf5_path": root / "reference.h5",
                "reference_macrolib_path": root / "reference.macrolib.txt",
                "macrolib_ascii_path": root / "native_sph.macrolib.txt",
                "verification_macrolib_path": root / "verify.macrolib.txt",
                "result_listing_path": root / "donjon.result",
            }
            for artifact in artifacts.values():
                artifact.write_bytes(b"evidence")
            payload_on_disk["handoff"].update(
                {key: str(value) for key, value in artifacts.items()}
            )
            payload_on_disk["native_sph"] = {
                "converged": True,
                "one_speed_convergence_provable": True,
                "final_flux_solve_converged": True,
                "flux_nonconvergence_count": 0,
                "factors_unmodified": True,
                "negative_factor_correction_count": 0,
                "oscillation_stop_count": 0,
                "normal_end": True,
                "iterations": 70,
                "epsilon": 1.0e-6,
                "final_rms_factor_update": 9.45e-7,
            }
            payload_on_disk["eigenvalue_validation"] = {
                "openmc_keff": 1.11231,
                "openmc_keff_std_dev": 0.00059,
                "reference_physical_balance_kind": "finite-domain-keff",
                "reference_physical_balance_keff": 1.11228,
                "reference_physical_balance_delta_pcm": -3.0,
                "reference_physical_balance_z": -0.05,
                "reference_collision_balance_kinf": 1.18,
                "reference_finite_balance_available": True,
                "reference_finite_balance_keff": 1.11228,
                "reference_leakage": 0.04,
                "reference_rate_balance_keff": 1.11228,
                "reference_rate_balance_delta_pcm": -3.0,
                "reference_rate_balance_z": -0.05,
                "donjon_keff": 1.11160,
                "donjon_delta_pcm": -71.0,
                "donjon_z": -1.2,
                "max_abs_z": 2.0,
            }
            payload_on_disk["geometry"] = {
                "kind": "hexagonal",
                "boundary_conditions": "radial vacuum; axial reflective",
            }
            payload_on_disk["component_balance"] = {}
            payload_on_disk["acceptance_checks"] = {
                "donjon_normal_end": True,
                "native_sph_converged": True,
                "native_sph_factors_unmodified": True,
                "native_sph_not_stopped_by_oscillation": True,
                "one_speed_convergence_provable": True,
                "final_flux_solve_converged": True,
                "energy_coverage_passed": True,
                "leakage_balance_available_when_required": True,
                "reference_physical_balance_within_openmc_uncertainty": True,
                "reference_rate_balance_within_openmc_uncertainty": True,
                "donjon_keff_within_openmc_uncertainty": True,
                "empirical_eigenvalue_multiplier_used": False,
                "adf_used": False,
            }
            path = root / "physics_summary.json"
            path.write_text(json.dumps(payload_on_disk), encoding="utf-8")
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/openmc-sph-summary", params={"path": str(path)})

            # Both the validator declaration and the raw solver record must
            # independently prove one-speed convergence.  SNGMRE reaching
            # MAXIT can otherwise look like a clean normal end.
            payload_on_disk["native_sph"]["one_speed_convergence_provable"] = False
            path.write_text(json.dumps(payload_on_disk), encoding="utf-8")
            unproved_solver = client.get(
                "/api/openmc-sph-summary", params={"path": str(path)}
            )
            payload_on_disk["native_sph"]["one_speed_convergence_provable"] = True
            payload_on_disk["acceptance_checks"][
                "one_speed_convergence_provable"
            ] = False
            path.write_text(json.dumps(payload_on_disk), encoding="utf-8")
            unproved_check = client.get(
                "/api/openmc-sph-summary", params={"path": str(path)}
            )
            payload_on_disk["acceptance_checks"][
                "one_speed_convergence_provable"
            ] = True

            # Recorded booleans cannot override contradictory raw solver
            # evidence.  A normal end with final-transport warnings or a
            # negative-factor reset must remain rejected.
            payload_on_disk["native_sph"].update(
                {
                    "final_flux_solve_converged": False,
                    "flux_nonconvergence_count": 208,
                    "factors_unmodified": False,
                    "negative_factor_correction_count": 1,
                }
            )
            path.write_text(json.dumps(payload_on_disk), encoding="utf-8")
            contradictory = client.get(
                "/api/openmc-sph-summary", params={"path": str(path)}
            )

        self.assertEqual(response.status_code, 200)
        audit = response.json()["evidence_audit"]
        self.assertEqual(audit["physics_acceptance"], "failed")
        self.assertFalse(audit["all_referenced_handoff_artifacts_present"])
        self.assertFalse(audit["evidence_integrity"]["verified"])
        self.assertFalse(
            audit["evidence_integrity"]["handoff_sha256_manifest_complete"]
        )
        self.assertEqual(len(audit["referenced_handoff_artifacts"]), 8)
        self.assertEqual(
            unproved_solver.json()["evidence_audit"]["physics_acceptance"],
            "failed",
        )
        self.assertEqual(
            unproved_check.json()["evidence_audit"]["physics_acceptance"],
            "failed",
        )
        self.assertEqual(
            contradictory.json()["evidence_audit"]["physics_acceptance"],
            "failed",
        )

    def test_live_native_summary_revalidates_hash_receipt_and_openmc_provenance(
        self,
    ) -> None:
        import h5py
        import numpy as np

        from openmc2donjon.macrolib import write_macrolib
        from openmc2donjon.native_sph_validation import validate_native_sph
        from openmc2donjon.web.server import create_app
        from tests.test_native_sph_validation import (
            _bind_clean_execution_deck,
            _mixture,
            _write_converter_receipt,
            _write_energy_coverage,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference_h5 = root / "reference.h5"
            reference_ascii = root / "reference.macrolib.txt"
            sph_ascii = root / "sph.macrolib.txt"
            verify_ascii = root / "verify.macrolib.txt"
            result = root / "donjon.result"
            receipt = root / "converter_summary.json"
            coverage = root / "energy_coverage.json"
            summary = root / "physics_summary.json"

            reference = _mixture(
                total=1.0, scatter=0.1, nusigf=0.9, flux=10.0
            )
            corrected = _mixture(
                total=1.1,
                scatter=0.11,
                nusigf=0.99,
                flux=10.0 / 1.1,
                sph=1.1,
            )
            write_macrolib(
                [reference],
                np.array([1.0, 2.0]),
                reference_ascii,
                reference_keff=1.0,
                reference_kinf=1.0,
            )
            write_macrolib(
                [corrected],
                np.array([1.0, 2.0]),
                sph_ascii,
                reference_keff=1.0,
                reference_kinf=1.0,
            )
            write_macrolib(
                [corrected],
                np.array([1.0, 2.0]),
                verify_ascii,
                reference_keff=1.0,
            )
            with h5py.File(reference_h5, "w") as h5:
                h5.attrs["reference_keff"] = 1.0
                h5.attrs["reference_keff_std_dev"] = 0.01
                h5.create_dataset(
                    "mixture_names", data=np.asarray(["fuel"], dtype="S")
                )
                h5.create_group("mixtures").create_group("fuel")
                h5.create_dataset("openmc_volume_flux", data=[[10.0]])
                h5.create_dataset(
                    "openmc_volume_flux_std_dev", data=[[0.1]]
                )
            result.write_text(
                "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 ;\n"
                "EPSPH  1.0E-06   (CONVERGENCE CRITERION)\n"
                "SPHEQU: ITER= 12 ERROR= 8.0E-07 ERR 2= 5.0E-07\n"
                "SPHEQU: ENDING OF SPH CONVERGENCE AFTER 12 ITERATIONS.\n"
                "normal end of execution for donjon 5 Version 5.1.0\n",
                encoding="utf-8",
            )
            deck = _bind_clean_execution_deck(result)
            _write_converter_receipt(
                receipt,
                input_path=reference_h5,
                output_path=reference_ascii,
            )
            _write_energy_coverage(coverage)
            validate_native_sph(
                reference_h5,
                reference_ascii,
                sph_ascii,
                verify_ascii,
                result,
                output_json=summary,
                energy_coverage_json=coverage,
                converter_receipt_json=receipt,
                execution_deck=deck,
            )

            client = TestClient(create_app(mock_mode=False))
            accepted_response = client.get(
                "/api/openmc-sph-summary", params={"path": str(summary)}
            )
            self.assertEqual(
                accepted_response.status_code, 200, accepted_response.text
            )
            accepted = accepted_response.json()
            self.assertEqual(
                accepted["evidence_audit"]["physics_acceptance"], "passed"
            )
            self.assertTrue(
                accepted["evidence_audit"]["evidence_integrity"]["verified"]
            )

            baseline_h5 = reference_h5.read_bytes()
            baseline_receipt = receipt.read_bytes()
            baseline_summary = summary.read_bytes()
            baseline_sph = sph_ascii.read_bytes()

            sph_ascii.write_bytes(baseline_sph + b"tampered\n")
            hash_tamper = client.get(
                "/api/openmc-sph-summary", params={"path": str(summary)}
            ).json()["evidence_audit"]
            self.assertFalse(
                hash_tamper["all_referenced_handoff_artifacts_hash_verified"]
            )
            self.assertFalse(hash_tamper["evidence_integrity"]["verified"])
            self.assertEqual(hash_tamper["physics_acceptance"], "failed")
            sph_ascii.write_bytes(baseline_sph)

            with h5py.File(reference_h5, "a") as h5:
                h5["openmc_volume_flux"][0, 0] = 11.0
            receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
            receipt_payload["input_sha256"] = hashlib.sha256(
                reference_h5.read_bytes()
            ).hexdigest()
            receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")
            summary_payload = json.loads(summary.read_text(encoding="utf-8"))
            summary_payload["handoff"]["evidence_sha256"][
                "augmented_hdf5_path"
            ] = hashlib.sha256(reference_h5.read_bytes()).hexdigest()
            summary_payload["handoff"]["evidence_sha256"][
                "converter_receipt_path"
            ] = hashlib.sha256(receipt.read_bytes()).hexdigest()
            summary.write_text(json.dumps(summary_payload), encoding="utf-8")
            provenance_tamper = client.get(
                "/api/openmc-sph-summary", params={"path": str(summary)}
            ).json()["evidence_audit"]
            self.assertTrue(
                provenance_tamper["all_referenced_handoff_artifacts_hash_verified"]
            )
            self.assertFalse(provenance_tamper["evidence_integrity"]["verified"])
            self.assertFalse(
                provenance_tamper["evidence_integrity"]["openmc_provenance"][
                    "valid"
                ]
            )

            reference_h5.write_bytes(baseline_h5)
            receipt.write_bytes(baseline_receipt)
            summary.write_bytes(baseline_summary)
            receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
            receipt_payload["output_sha256"] = "0" * 64
            receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")
            summary_payload = json.loads(summary.read_text(encoding="utf-8"))
            summary_payload["handoff"]["evidence_sha256"][
                "converter_receipt_path"
            ] = hashlib.sha256(receipt.read_bytes()).hexdigest()
            summary.write_text(json.dumps(summary_payload), encoding="utf-8")
            receipt_tamper = client.get(
                "/api/openmc-sph-summary", params={"path": str(summary)}
            ).json()["evidence_audit"]
            self.assertTrue(
                receipt_tamper["all_referenced_handoff_artifacts_hash_verified"]
            )
            self.assertFalse(receipt_tamper["evidence_integrity"]["verified"])
            self.assertFalse(
                receipt_tamper["evidence_integrity"]["converter_receipt"][
                    "valid"
                ]
            )
            self.assertEqual(receipt_tamper["physics_acceptance"], "failed")

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
        # The SPH demo planner needs a browsable recipe to reach READY.
        self.assertIn("export_recipe.py", names)
        self.assertIn("out_uncorrected.macrolib.txt", names)

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
        lines = {line.strip() for line in payload["text"].splitlines()}
        self.assertIn("L_MULTICOMPO", lines)
        self.assertIn("SCAT00", lines)
        # The anatomy scan must agree with mock convert's preflight for
        # the C5G7 story (ADF 9 mixtures / 4 faces + SPH 9): all the
        # equivalence and structural blocks the real writer emits are
        # visible in the "complete" mock preview.
        for block in (
            "GLOBAL",
            "STATE-VECTOR",
            "MIXTURES",
            "CALCULATIONS",
            "TREE",
            "ISOTOPESLIST",
            "STRD",
            "ENERGY",
            "ADF",
            "HADF",
            "NSPH",
            "L_LIBRARY",
        ):
            self.assertIn(block, lines)
        # STATE-VECTOR shape matches the file being previewed:
        # 9 mixtures / 7 groups / 9 calculations for C5G7.
        state_line = payload["text"].splitlines()[
            payload["text"].splitlines().index("STATE-VECTOR") + 1
        ]
        self.assertEqual(state_line.split()[:3], ["9", "7", "9"])
        self.assertFalse(payload["truncated"])

    def test_mock_mode_minicase_macrolib_preview_carries_group_nsp(self) -> None:
        """The SPH minicase MACROLIB preview matches its physics story.

        Regression test for the mock preview lacking ENERGY/NSPH while
        the physics-summary fixture claims macrolib_ascii_nsp_block_count
        of 33 and the preflight reports 2 mixtures / 33 groups.
        """

        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/text-preview",
            params={
                "path": "/mock/home/openmc-runs/openmc-sph-minicase/out.macrolib.txt"
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        raw_lines = payload["text"].splitlines()
        lines = {line.strip() for line in raw_lines}
        self.assertIn("L_MACROLIB", lines)
        for block in ("STATE-VECTOR", "ENERGY", "VOLUME", "GROUP", "NSPH"):
            self.assertIn(block, lines)
        # No ADF: the minicase preflight reports adf_mixtures = 0.
        self.assertNotIn("ADF", lines)
        self.assertNotIn("HADF", lines)
        # One GROUP/*/NSPH block per group, matching the physics-summary
        # fixture's macrolib_ascii_nsp_block_count of 33.
        self.assertEqual(sum(1 for line in raw_lines if line.strip() == "NSPH"), 33)
        # STATE-VECTOR shape: 33 groups / 2 mixtures.
        state_line = raw_lines[raw_lines.index("STATE-VECTOR") + 1]
        self.assertEqual(state_line.split()[:2], ["33", "2"])
        # The complete artifact fits inside the default preview budget.
        self.assertFalse(payload["truncated"])
        # The mock browser reports the same size the preview serves.
        status = client.get(
            "/api/file-status",
            params={
                "path": "/mock/home/openmc-runs/openmc-sph-minicase/out.macrolib.txt"
            },
        ).json()
        self.assertEqual(status["size"], payload["file_size"])

    def test_mock_mode_uncorrected_macrolib_preview_has_no_nsp(self) -> None:
        from openmc2donjon.web.server import create_app

        client = TestClient(create_app(mock_mode=True))
        response = client.get(
            "/api/text-preview",
            params={
                "path": (
                    "/mock/home/openmc-runs/openmc-sph-minicase/"
                    "out_uncorrected.macrolib.txt"
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        lines = {line.strip() for line in response.json()["text"].splitlines()}
        self.assertIn("L_MACROLIB", lines)
        self.assertNotIn("NSPH", lines)

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
        self.assertEqual(payload["text"], "line-1\nline-2\n")
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["truncated_by"], ["lines"])
        self.assertEqual(payload["displayed_lines"], 2)

    def test_live_mode_preserves_complete_deck_bytes_and_reports_sha256(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.x2m"
            raw = b"PROCEDURE TEST ;\r\nQUIT .\r\n"
            path.write_bytes(raw)

            client = TestClient(create_app(mock_mode=False))
            response = client.get(
                "/api/text-preview",
                params={"path": str(path), "max_bytes": 64, "max_lines": 20},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["text"].encode("utf-8"), raw)
        self.assertEqual(payload["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(payload["truncated"])

    def test_live_mode_rejects_invalid_utf8_instead_of_replacing_it(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.x2m"
            path.write_bytes(b"QUIT .\n\xff")
            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/text-preview", params={"path": str(path)})

        self.assertEqual(response.status_code, 400)
        self.assertIn("valid UTF-8", response.json()["detail"])

    def test_live_mode_rejects_binary_preview(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "binary.dat"
            path.write_bytes(b"abc\x00def")

            client = TestClient(create_app(mock_mode=False))
            response = client.get("/api/text-preview", params={"path": str(path)})

        self.assertEqual(response.status_code, 400)
        self.assertIn("binary", response.json()["detail"])

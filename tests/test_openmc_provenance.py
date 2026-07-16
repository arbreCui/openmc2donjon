from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import h5py
import numpy as np

from openmc2donjon.bundle import ArtifactSpec, bundle_artifacts, validate_bundle
from openmc2donjon.openmc_provenance import (
    OPENMC_PROVENANCE_DATASET,
    OPENMC_PROVENANCE_GROUP,
    collect_openmc_provenance,
    file_sha256,
    provenance_before_hdf5_mutation,
    provenance_digest,
    read_openmc_provenance,
    refresh_openmc_provenance_after_hdf5_mutation,
    write_openmc_provenance,
)


class OpenmcProvenanceTests(unittest.TestCase):
    def test_bundle_recomputes_standalone_provenance_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            handoff = root / "mgxs.h5"
            with h5py.File(handoff, "w") as h5:
                h5.attrs["source"] = "OpenMC mgxs.Library"
                h5.create_dataset("total", data=np.asarray([0.25, 0.50]))
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
                declared_metadata={"input_closure_complete": True},
            )
            record = write_openmc_provenance(handoff, record)
            output = root / "out.mcompo.txt"
            output.write_text("ASCII payload\n", encoding="utf-8")
            provenance_json = root / "openmc_provenance.json"
            provenance_json.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            run_summary = root / "run_summary.json"
            run_summary.write_text(
                json.dumps(
                    {
                        "format": "multicompo",
                        "hdf5_sha256": file_sha256(handoff),
                        "output_sha256": file_sha256(output),
                        "openmc_provenance": record,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            bundle_dir = root / "bundle"
            bundle_artifacts(
                output_dir=bundle_dir,
                artifacts=[
                    ArtifactSpec("mgxs", handoff),
                    ArtifactSpec("mcompo", output),
                    ArtifactSpec("run-summary", run_summary),
                    ArtifactSpec("openmc-provenance", provenance_json),
                ],
            )
            manifest_path = bundle_dir / "manifest.json"
            self.assertTrue(validate_bundle(manifest_path).ok)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            provenance_entry = next(
                item
                for item in manifest["artifacts"]
                if item["label"] == "openmc-provenance"
            )
            bundled_provenance = bundle_dir / provenance_entry["bundled_path"]
            tampered = json.loads(bundled_provenance.read_text(encoding="utf-8"))
            tampered["producer"]["platform"] = "tampered"
            bundled_provenance.write_text(
                json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            provenance_entry["size_bytes"] = bundled_provenance.stat().st_size
            provenance_entry["sha256"] = file_sha256(bundled_provenance)
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            report = validate_bundle(manifest_path)

            self.assertFalse(report.ok)
            self.assertTrue(
                any("record is invalid" in message for message in report.messages),
                report.messages,
            )

    def test_bundle_rejects_source_changed_after_provenance_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
                declared_metadata={"input_closure_complete": True},
            )
            handoff = root / "mgxs.h5"
            with h5py.File(handoff, "w") as h5:
                h5.attrs["source"] = "OpenMC mgxs.Library"
            write_openmc_provenance(handoff, record)
            provenance_json = root / "openmc_provenance.json"
            provenance_json.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            run_summary = root / "run_summary.json"
            run_summary.write_text(
                json.dumps({"openmc_provenance": record}) + "\n",
                encoding="utf-8",
            )
            files["recipe"].write_text("# changed after collection\n", encoding="utf-8")
            bundle_dir = root / "bundle"
            bundle_artifacts(
                output_dir=bundle_dir,
                artifacts=[
                    ArtifactSpec("mgxs", handoff),
                    ArtifactSpec("run-summary", run_summary),
                    ArtifactSpec("recipe", files["recipe"]),
                    ArtifactSpec("openmc-provenance", provenance_json),
                ],
            )

            report = validate_bundle(bundle_dir / "manifest.json")

            self.assertFalse(report.ok)
            self.assertTrue(
                any("bundled source recipe" in message for message in report.messages),
                report.messages,
            )

    def test_collects_complete_transport_provenance_and_embeds_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
                declared_metadata={
                    "input_closure_complete": True,
                    "threads": 4,
                    "mpi_ranks": 2,
                },
            )

            self.assertEqual(record["status"], "complete")
            self.assertEqual(record["missing"], [])
            self.assertTrue(record["capabilities"]["reference_bound"])
            self.assertTrue(record["capabilities"]["export_replayable"])
            self.assertTrue(record["capabilities"]["transport_reproducible"])
            self.assertEqual(record["openmc"]["version"], "0.15.2")
            self.assertEqual(record["openmc"]["statepoint_format_version"], "18.1")
            self.assertEqual(record["simulation"]["particles"], 5000)
            self.assertEqual(record["simulation"]["batches"], 80)
            self.assertEqual(record["simulation"]["inactive"], 20)
            self.assertEqual(record["simulation"]["seed"], 71)
            self.assertEqual(record["simulation"]["threads"], 4)
            self.assertEqual(record["nuclear_data"]["library_count"], 1)
            self.assertEqual(
                record["nuclear_data"]["selection"], "used-materials"
            )
            self.assertIsNotNone(record["fingerprints"]["model_sha256"])

            handoff = root / "mgxs.h5"
            with h5py.File(handoff, "w") as h5:
                h5.attrs["source"] = "OpenMC mgxs.Library"
            write_openmc_provenance(handoff, record)
            loaded = read_openmc_provenance(handoff)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded["digest_sha256"], record["digest_sha256"])
            self.assertTrue(loaded["integrity"]["ok"])
            self.assertEqual(loaded["status"], "complete")

    def test_rejects_arbitrary_hdf5_as_statepoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            with h5py.File(files["statepoint"], "r+") as h5:
                h5.attrs["filetype"] = "summary"
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
                declared_metadata={"input_closure_complete": True},
            )

            self.assertFalse(record["capabilities"]["reference_bound"])
            self.assertIn("statepoint.openmc_hdf5", record["missing"])

    def test_reader_detects_payload_and_root_mirror_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
            )
            handoff = root / "mgxs.h5"
            with h5py.File(handoff, "w") as h5:
                h5.attrs["source"] = "OpenMC mgxs.Library"
            write_openmc_provenance(handoff, record)
            with h5py.File(handoff, "r+") as h5:
                h5.attrs["openmc_provenance_status"] = "complete"
                payload = json.loads(
                    h5[OPENMC_PROVENANCE_GROUP][OPENMC_PROVENANCE_DATASET][()]
                )
                payload["capabilities"]["reference_bound"] = False
                del h5[OPENMC_PROVENANCE_GROUP][OPENMC_PROVENANCE_DATASET]
                h5[OPENMC_PROVENANCE_GROUP].create_dataset(
                    OPENMC_PROVENANCE_DATASET,
                    data=json.dumps(payload),
                    dtype=h5py.string_dtype("utf-8"),
                )

            loaded = read_openmc_provenance(handoff)
            assert loaded is not None
            self.assertFalse(loaded["integrity"]["ok"])
            rendered = "\n".join(loaded["integrity"]["issues"])
            self.assertIn("digest", rendered)
            self.assertIn("capabilities", rendered)
            self.assertIn("status mirrors", rendered)

    def test_reader_detects_mgxs_dataset_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
            )
            handoff = root / "mgxs.h5"
            with h5py.File(handoff, "w") as h5:
                h5.attrs["source"] = "OpenMC mgxs.Library"
                h5.create_dataset("total", data=np.asarray([0.25, 0.50]))
            write_openmc_provenance(handoff, record)
            with h5py.File(handoff, "r+") as h5:
                h5["total"][0] = 99.0

            loaded = read_openmc_provenance(handoff)

            assert loaded is not None
            self.assertFalse(loaded["integrity"]["ok"])
            self.assertTrue(
                any(
                    "MGXS payload digest" in issue
                    for issue in loaded["integrity"]["issues"]
                )
            )

    def test_authorized_postprocessor_can_rebind_final_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            handoff = root / "mgxs.h5"
            with h5py.File(handoff, "w") as h5:
                h5.attrs["source"] = "OpenMC mgxs.Library"
                h5.create_dataset("total", data=np.asarray([0.25, 0.50]))
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
            )
            initial = write_openmc_provenance(handoff, record)
            captured = provenance_before_hdf5_mutation(handoff)
            with h5py.File(handoff, "r+") as h5:
                h5["total"][0] = 0.30
            refreshed = refresh_openmc_provenance_after_hdf5_mutation(
                handoff,
                captured,
            )

            assert refreshed is not None
            self.assertTrue(refreshed["integrity"]["ok"])
            self.assertNotEqual(
                refreshed["handoff"]["payload_sha256"],
                initial["handoff"]["payload_sha256"],
            )

    def test_conflicting_statepoint_and_recipe_metadata_blocks_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
                declared_metadata={
                    "input_closure_complete": True,
                    "particles": 999,
                },
            )

            self.assertEqual(record["simulation"]["particles"], 5000)
            self.assertIn("conflict.simulation.particles", record["missing"])
            self.assertTrue(record["capabilities"]["reference_bound"])
            self.assertFalse(record["capabilities"]["export_replayable"])
            self.assertFalse(record["capabilities"]["transport_reproducible"])

    def test_renders_array_openmc_version_canonically(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            with h5py.File(files["statepoint"], "r+") as h5:
                h5.attrs["openmc_version"] = np.asarray([0, 15, 4])

            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
            )

            self.assertEqual(record["openmc"]["version"], "0.15.4")

    def test_frozen_reference_remains_valid_after_original_sources_are_removed(
        self,
    ) -> None:
        """Downstream native SPH consumes the handoff; it does not rerun OpenMC."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            record = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
                declared_metadata={"input_closure_complete": True},
            )
            handoff = root / "mgxs.h5"
            with h5py.File(handoff, "w") as h5:
                h5.attrs["source"] = "OpenMC mgxs.Library"
            write_openmc_provenance(handoff, record)

            for source in root.iterdir():
                if source != handoff and source.is_file():
                    source.unlink()

            loaded = read_openmc_provenance(handoff)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertTrue(loaded["integrity"]["ok"])
            self.assertTrue(loaded["capabilities"]["reference_bound"])
            self.assertTrue(loaded["capabilities"]["transport_reproducible"])
            self.assertEqual(loaded["digest_sha256"], record["digest_sha256"])

    def test_digest_is_key_order_independent_and_content_sensitive(self) -> None:
        left = {"schema": "x", "nested": {"a": 1, "b": 2}}
        right = {"nested": {"b": 2, "a": 1}, "schema": "x"}
        changed = {"schema": "x", "nested": {"a": 1, "b": 3}}
        self.assertEqual(provenance_digest(left), provenance_digest(right))
        self.assertNotEqual(provenance_digest(left), provenance_digest(changed))

    def test_does_not_treat_current_cross_sections_environment_as_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            materials = root / "materials-without-cross-sections.xml"
            materials.write_text(
                '<materials><material id="1"><nuclide name="U235"/></material></materials>',
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"OPENMC_CROSS_SECTIONS": str(files["cross_sections"])},
            ):
                record = collect_openmc_provenance(
                    recipe_path=files["recipe"],
                    statepoint_path=files["statepoint"],
                    statepoint_loaded=True,
                    declared_files={
                        "geometry": files["geometry"],
                        "materials": materials,
                        "settings": files["settings"],
                    },
                )
            self.assertIsNone(record["nuclear_data"]["cross_sections"])
            self.assertIn(
                "nuclear_data.cross_sections.sha256", record["missing"]
            )

    def test_transport_replay_requires_explicit_model_input_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = self._write_complete_case(root)
            helper = root / "model_helper.py"
            helper.write_text("MODEL_VERSION = 1\n", encoding="utf-8")

            unclosed = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                },
            )
            closed = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                    "model_helper": helper,
                },
                declared_metadata={"input_closure_complete": True},
            )

            self.assertIn("model.input_closure_attested", unclosed["missing"])
            self.assertFalse(unclosed["capabilities"]["export_replayable"])
            self.assertTrue(closed["capabilities"]["transport_reproducible"])
            first_fingerprint = closed["fingerprints"]["model_sha256"]
            helper.write_text("MODEL_VERSION = 2\n", encoding="utf-8")
            changed = collect_openmc_provenance(
                recipe_path=files["recipe"],
                statepoint_path=files["statepoint"],
                statepoint_loaded=True,
                declared_files={
                    "geometry": files["geometry"],
                    "materials": files["materials"],
                    "settings": files["settings"],
                    "model_helper": helper,
                },
                declared_metadata={"input_closure_complete": True},
            )
            self.assertNotEqual(
                changed["fingerprints"]["model_sha256"], first_fingerprint
            )

    @staticmethod
    def _write_complete_case(root: Path) -> dict[str, Path]:
        recipe = root / "export_recipe.py"
        recipe.write_text("def build_library():\n    return None\n", encoding="utf-8")
        geometry = root / "geometry.xml"
        geometry.write_text("<geometry/>\n", encoding="utf-8")
        settings = root / "settings.xml"
        settings.write_text(
            """<settings>
  <run_mode>eigenvalue</run_mode>
  <particles>5000</particles>
  <batches>80</batches>
  <inactive>20</inactive>
  <generations_per_batch>1</generations_per_batch>
  <seed>71</seed>
  <temperature><method>interpolation</method></temperature>
</settings>
""",
            encoding="utf-8",
        )
        library = root / "U235.h5"
        library.write_bytes(b"evaluated nuclear data\n")
        unused = root / "Xe135.h5"
        unused.write_bytes(b"must not be selected\n")
        cross_sections = root / "cross_sections.xml"
        cross_sections.write_text(
            """<cross_sections>
  <library materials="U235" path="U235.h5" type="neutron"/>
  <library materials="Xe135" path="Xe135.h5" type="neutron"/>
</cross_sections>
""",
            encoding="utf-8",
        )
        materials = root / "materials.xml"
        materials.write_text(
            """<materials>
  <cross_sections>cross_sections.xml</cross_sections>
  <material id="1"><nuclide name="U235"/></material>
</materials>
""",
            encoding="utf-8",
        )
        statepoint = root / "statepoint.80.h5"
        with h5py.File(statepoint, "w") as h5:
            h5.attrs["filetype"] = "statepoint"
            h5.attrs["openmc_version"] = "0.15.2"
            h5.attrs["git_sha1"] = "abc123"
            h5.attrs["version"] = np.asarray([18, 1])
            h5.create_dataset("run_mode", data=np.bytes_("eigenvalue"))
            h5.create_dataset("n_particles", data=5000)
            h5.create_dataset("n_batches", data=80)
            h5.create_dataset("n_inactive", data=20)
            h5.create_dataset("seed", data=71)
            h5.create_dataset("stride", data=152917)
        return {
            "recipe": recipe,
            "geometry": geometry,
            "materials": materials,
            "settings": settings,
            "cross_sections": cross_sections,
            "statepoint": statepoint,
        }


if __name__ == "__main__":
    unittest.main()

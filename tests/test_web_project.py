from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
from fastapi.testclient import TestClient

from openmc2donjon.web.project import project_status
from openmc2donjon.web.server import create_app
from openmc2donjon.production_policy import (
    canonical_production_thresholds,
    production_preflight_policy_payload,
)
from openmc2donjon.openmc_provenance import (
    collect_openmc_provenance,
    write_openmc_provenance,
)


class ProjectStatusTests(unittest.TestCase):
    def test_directory_without_manifest_is_unconfigured_not_irena(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = project_status(Path(tmp))
            self.assertFalse(status["configured"])
            self.assertEqual(status["required_components"], 0)
            self.assertEqual(status["components"], [])
            self.assertFalse(status["handoffs_ready"])
            self.assertFalse(status["physics_accepted"])
            self.assertFalse(status["ready_for_consumer"])
            self.assertIsNone(status["template"])
            self.assertIn("missing openmc2donjon.project.json", status["configuration_issues"])

    def test_one_component_generic_project_is_not_forced_to_five(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "components/fuel.h5",
                        "output": "outputs/fuel.mcompo.txt",
                        "contract": "converter-hdf5",
                        "format": "multicompo",
                    }
                ],
            )
            input_path = root / "components" / "fuel.h5"
            input_path.parent.mkdir()
            with h5py.File(input_path, "w") as h5:
                h5.create_group("mixtures")
            output = root / "outputs" / "fuel.mcompo.txt"
            output.parent.mkdir()
            output.write_text("SIGNATURE\nL_MULTICOMPO\n", encoding="utf-8")
            _write_receipt(input_path, output, require_physical_sph=False)

            status = project_status(root)
            self.assertTrue(status["configured"])
            self.assertEqual(status["required_components"], 1)
            self.assertEqual(status["accepted_inputs"], 1)
            self.assertEqual(status["accepted_outputs"], 1)
            self.assertEqual(status["ready_components"], 1)
            self.assertTrue(status["handoffs_ready"])
            self.assertFalse(status["physics_accepted"])
            self.assertTrue(status["ready_for_consumer"])
            self.assertEqual(status["components"][0]["label"], "Fuel")
            self.assertEqual(status["components"][0]["evidence"]["state"], "not-required")
            self.assertEqual(status["acceptance_mode"], "handoff-only")
            self.assertFalse(status["acceptance_required"])
            self.assertEqual(status["acceptance"]["state"], "not-required")
            self.assertEqual(status["acceptance"]["basis"], "not-required")

            receipt_path = output.with_name(f"{output.name}.convert.json")
            receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            nonproduction_payload = json.loads(json.dumps(receipt_payload))
            nonproduction_payload["production_requested"] = False
            nonproduction_payload["preflight_policy"] = {
                "level": "engineering",
                "production_requested": False,
                "preflight_executed": True,
            }
            receipt_path.write_text(
                json.dumps(nonproduction_payload), encoding="utf-8"
            )
            nonproduction = project_status(root)
            self.assertEqual(
                nonproduction["components"][0]["output"]["state"], "rejected"
            )
            self.assertFalse(nonproduction["handoffs_ready"])
            self.assertIn(
                "production_requested=true",
                " ".join(nonproduction["components"][0]["output"]["issues"]),
            )

            flag_only_payload = json.loads(json.dumps(receipt_payload))
            flag_only_payload.pop("preflight")
            receipt_path.write_text(json.dumps(flag_only_payload), encoding="utf-8")
            flag_only = project_status(root)["components"][0]["output"]
            self.assertEqual(flag_only["state"], "rejected")
            self.assertIn("auditable MGXS preflight", " ".join(flag_only["issues"]))

            failed_input_payload = json.loads(json.dumps(receipt_payload))
            failed_input_payload["preflight"]["inputs"][0]["ok"] = False
            receipt_path.write_text(json.dumps(failed_input_payload), encoding="utf-8")
            failed_input = project_status(root)["components"][0]["output"]
            self.assertEqual(failed_input["state"], "rejected")
            self.assertIn("failed input", " ".join(failed_input["issues"]))

    def test_irena_template_accepts_only_strict_handoff_and_identified_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                template="irena30-colorset-core",
                components=[
                    {
                        "id": "int_ext",
                        "label": "INT",
                        "input": "colorsets/int_ext/mgxs_sph_applied.h5",
                        "output": "cpo/irena30_int.mcompo.txt",
                        "contract": "irena30-colorset-sph",
                        "format": "multicompo",
                        "identity": "int_ext",
                        "metadata": {"target": "INT", "neighbors": "EXT"},
                    }
                ],
            )
            colorset = root / "colorsets" / "int_ext"
            colorset.mkdir(parents=True)
            handoff = colorset / "mgxs_sph_applied.h5"
            _write_applied_handoff(handoff)
            output = root / "cpo" / "irena30_int.mcompo.txt"
            output.parent.mkdir(parents=True)
            output.write_text(
                "SIGNATURE\n4 4 4\nL_MULTICOMPO\nCOMMENT\nIRENA-30 int_ext physical rate-SPH\n",
                encoding="utf-8",
            )
            _write_receipt(handoff, output, require_physical_sph=True)

            status = project_status(root)
            row = status["components"][0]
            self.assertEqual(row["contract"], "irena30-colorset-sph")
            self.assertEqual(row["handoff"]["state"], "accepted")
            self.assertEqual(row["output"]["state"], "accepted")
            self.assertEqual(status["required_components"], 1)
            self.assertTrue(status["ready_for_consumer"])

    def test_generic_physical_sph_project_accepts_any_domain_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "assembly-a",
                        "label": "Assembly A",
                        "input": "assembly/mgxs_sph_applied.h5",
                        "output": "assembly/library.mcompo.txt",
                        "contract": "physical-sph",
                        "format": "multicompo",
                    }
                ],
            )
            handoff = root / "assembly" / "mgxs_sph_applied.h5"
            handoff.parent.mkdir(parents=True)
            _write_applied_handoff(handoff, domains=1)
            output = root / "assembly" / "library.mcompo.txt"
            output.write_text("SIGNATURE\nL_MULTICOMPO\n", encoding="utf-8")
            _write_receipt(handoff, output, require_physical_sph=True)

            row = project_status(root)["components"][0]
            self.assertEqual(row["contract"], "physical-sph")
            self.assertEqual(row["handoff"]["state"], "accepted")
            self.assertEqual(row["output"]["state"], "accepted")

    def test_handoff_only_releases_declared_consumer_without_a_physics_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "fuel.h5",
                        "output": "fuel.mcompo.txt",
                    }
                ],
                consumer_kind="declared-full-core",
            )
            handoff = root / "fuel.h5"
            with h5py.File(handoff, "w") as h5:
                h5.create_group("mixtures")
            output = root / "fuel.mcompo.txt"
            output.write_text("SIGNATURE\nL_MULTICOMPO\n", encoding="utf-8")
            _write_receipt(handoff, output, require_physical_sph=False)

            status = project_status(root)
            self.assertTrue(status["handoffs_ready"])
            self.assertFalse(status["physics_accepted"])
            self.assertEqual(status["acceptance_mode"], "handoff-only")
            self.assertEqual(status["acceptance_basis"], "not-required")
            self.assertTrue(status["ready_for_consumer"])

    def test_native_sph_component_requires_live_physics_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "shield",
                        "label": "Shield",
                        "input": "shield/reference.h5",
                        "output": "shield/native_sph.macrolib.txt",
                        "receipt": "shield/converter_summary.json",
                        "physics_summary": "shield/physics_summary.json",
                        "contract": "native-sph",
                        "format": "macrolib",
                        "identity": "SHIELD",
                        "metadata": {"node_side_cm": 10.1036},
                    }
                ],
            )
            component = root / "shield"
            component.mkdir()
            reference = component / "reference.h5"
            with h5py.File(reference, "w") as h5:
                h5.create_group("mixtures")
            output = component / "native_sph.macrolib.txt"
            output.write_text("SIGNATURE\nL_MACROLIB\n", encoding="utf-8")
            summary = component / "physics_summary.json"
            payload = _write_native_summary(
                summary,
                output=output,
                reference_h5=reference,
                mixture_names=["SHIELD", "NEIGHBOR"],
            )

            status = project_status(root)
            row = status["components"][0]
            self.assertEqual(row["handoff"]["state"], "accepted")
            self.assertEqual(row["output"]["state"], "rejected")
            self.assertIn(
                "complete live deck and MACROLIB evidence chain",
                " ".join(row["output"]["issues"]),
            )
            self.assertFalse(status["ready_for_consumer"])

            wrong_receipt = json.loads(json.dumps(payload))
            wrong_receipt["handoff"]["converter_receipt_path"] = str(summary)
            summary.write_text(json.dumps(wrong_receipt), encoding="utf-8")
            misbound = project_status(root)["components"][0]["output"]
            self.assertEqual(misbound["state"], "rejected")
            self.assertIn(
                "Converter receipt does not match the project receipt",
                " ".join(misbound["issues"]),
            )

            hashless = json.loads(json.dumps(payload))
            hashless["handoff"].pop("evidence_sha256")
            summary.write_text(json.dumps(hashless), encoding="utf-8")
            rejected = project_status(root)["components"][0]["output"]
            self.assertEqual(rejected["state"], "rejected")
            self.assertIn("SHA-256 manifest", " ".join(rejected["issues"]))

            result_listing = Path(payload["handoff"]["result_listing_path"])
            original_listing = result_listing.read_text(encoding="utf-8")
            result_listing.write_text(original_listing + "tampered\n", encoding="utf-8")
            summary.write_text(json.dumps(payload), encoding="utf-8")
            rejected = project_status(root)["components"][0]["output"]
            self.assertEqual(rejected["state"], "rejected")
            self.assertIn("hash mismatch", " ".join(rejected["issues"]))
            result_listing.write_text(original_listing, encoding="utf-8")

            payload["geometry"]["coarse_node_side_cm"] = 9.9950212
            summary.write_text(json.dumps(payload), encoding="utf-8")
            rejected = project_status(root)["components"][0]["output"]
            self.assertEqual(rejected["state"], "rejected")
            self.assertIn("node side", " ".join(rejected["issues"]))

            payload["geometry"]["coarse_node_side_cm"] = 10.1036
            payload["acceptance_checks"]["empirical_eigenvalue_multiplier_used"] = True
            summary.write_text(json.dumps(payload), encoding="utf-8")
            rejected = project_status(root)["components"][0]["output"]
            self.assertEqual(rejected["state"], "rejected")
            self.assertIn("empirical", " ".join(rejected["issues"]))

            payload["acceptance_checks"]["empirical_eigenvalue_multiplier_used"] = False
            payload["native_sph"]["one_speed_convergence_provable"] = False
            summary.write_text(json.dumps(payload), encoding="utf-8")
            unproved = project_status(root)["components"][0]["output"]
            self.assertEqual(unproved["state"], "rejected")
            self.assertIn(
                "one_speed_convergence_provable",
                " ".join(unproved["issues"]),
            )

            # Old PNL-style summaries only repeated high-level booleans.  They
            # did not contain an auditable raw one-speed/final-solve record.
            payload.pop("native_sph")
            payload["acceptance_checks"] = {
                "donjon_normal_end": True,
                "native_sph_converged": True,
                "energy_coverage_passed": True,
                "reference_rate_balance_within_openmc_uncertainty": True,
                "donjon_keff_within_openmc_uncertainty": True,
                "empirical_eigenvalue_multiplier_used": False,
                "adf_used": False,
            }
            summary.write_text(json.dumps(payload), encoding="utf-8")
            legacy = project_status(root)["components"][0]["output"]
            self.assertEqual(legacy["state"], "rejected")
            self.assertIn("raw solver evidence", " ".join(legacy["issues"]))

    def test_native_sph_legacy_receipt_is_readable_but_never_reused_as_receipt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "assembly",
                        "label": "Legacy assembly",
                        "input": "assembly/reference.h5",
                        "output": "assembly/native_sph.macrolib.txt",
                        "receipt": "assembly/physics_summary.json",
                        "contract": "native-sph",
                        "format": "macrolib",
                    }
                ],
            )

            status = project_status(root)
            self.assertTrue(status["configured"])
            row = status["components"][0]
            self.assertEqual(row["paths"]["receipt"], "")
            self.assertEqual(
                row["paths"]["physics_summary"],
                str((root / "assembly" / "physics_summary.json").resolve()),
            )
            self.assertEqual(row["output"]["state"], "missing")
            self.assertIn(
                "declare a distinct Converter receipt and physics_summary",
                " ".join(row["output"]["issues"]),
            )

            manifest = json.loads(
                (root / "openmc2donjon.project.json").read_text(encoding="utf-8")
            )
            manifest["components"][0]["physics_summary"] = (
                "assembly/physics_summary.json"
            )
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            response = client.post(
                "/api/project/manifest",
                json={"root": str(root), "manifest": manifest},
            )
            self.assertEqual(response.status_code, 422)
            self.assertIn(
                "receipt and physics_summary must be different files",
                response.json()["detail"],
            )

    def test_native_sph_component_rejects_an_already_applied_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fullcore",
                        "label": "Full core",
                        "input": "fullcore/reference.h5",
                        "output": "fullcore/native_sph.macrolib.txt",
                        "receipt": "fullcore/converter_summary.json",
                        "physics_summary": "fullcore/physics_summary.json",
                        "contract": "native-sph",
                        "format": "macrolib",
                    }
                ],
            )
            reference = root / "fullcore" / "reference.h5"
            reference.parent.mkdir()
            with h5py.File(reference, "w") as h5:
                h5.create_group("mixtures")
                h5.attrs["sph_applied"] = True

            applied = project_status(root)["components"][0]["handoff"]
            self.assertEqual(applied["state"], "rejected")
            self.assertIn("sph_applied=true", " ".join(applied["issues"]))

            with h5py.File(reference, "w") as h5:
                h5.create_group("mixtures")
                h5.attrs["sph_applied"] = False
                h5.attrs["sph_apply_operator"] = "divide-xs-by-nsph"

            marked = project_status(root)["components"][0]["handoff"]
            self.assertEqual(marked["state"], "rejected")
            self.assertIn("applied-SPH markers", " ".join(marked["issues"]))

    def test_rejects_stale_output_when_handoff_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "fuel.h5",
                        "output": "fuel.mcompo.txt",
                    }
                ],
            )
            handoff = root / "fuel.h5"
            with h5py.File(handoff, "w") as h5:
                h5.create_group("mixtures")
            output = root / "fuel.mcompo.txt"
            output.write_text("SIGNATURE\nL_MULTICOMPO\n", encoding="utf-8")
            _write_receipt(handoff, output, require_physical_sph=False)

            with h5py.File(handoff, "a") as h5:
                h5.attrs["post_conversion_change"] = True

            row = project_status(root)["components"][0]
            self.assertEqual(row["handoff"]["state"], "accepted")
            self.assertEqual(row["output"]["state"], "rejected")
            self.assertIn("input hash", " ".join(row["output"]["issues"]))

    def test_rejects_manifest_paths_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "bad",
                        "label": "Bad",
                        "input": "../outside.h5",
                        "output": "out.mcompo.txt",
                    }
                ],
            )
            status = project_status(root)
            self.assertFalse(status["configured"])
            self.assertTrue(
                any("inside the project root" in issue for issue in status["configuration_issues"])
            )

    def test_accepts_only_an_explicit_evidence_backed_project_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "fuel.h5",
                        "output": "fuel.mcompo.txt",
                    }
                ],
                acceptance={"decision": "acceptance/decision.json"},
            )
            handoff = root / "fuel.h5"
            with h5py.File(handoff, "w") as h5:
                h5.create_group("mixtures")
            output = root / "fuel.mcompo.txt"
            output.write_text("SIGNATURE\nL_MULTICOMPO\n", encoding="utf-8")
            _write_receipt(handoff, output, require_physical_sph=False)
            evidence = root / "references" / "physics.json"
            evidence.parent.mkdir()
            evidence.write_text('{"comparison":"passed"}\n', encoding="utf-8")
            decision = root / "acceptance" / "decision.json"
            decision.parent.mkdir()

            missing = project_status(root)
            self.assertTrue(missing["handoffs_ready"])
            self.assertFalse(missing["physics_accepted"])
            self.assertFalse(missing["ready_for_consumer"])
            self.assertFalse(missing["ready_for_core"])
            self.assertEqual(missing["acceptance"]["state"], "missing")

            decision_payload = {
                "schema": "openmc2donjon.acceptance.v1",
                "status": "accepted",
                "summary": "Independent model comparison passed.",
                "criteria": [
                    {
                        "id": "reference-comparison",
                        "label": "Independent reference comparison",
                        "status": "passed",
                        "evidence": [
                            {
                                "label": "Physics comparison",
                                "path": "references/physics.json",
                                "sha256": _sha256(evidence),
                            }
                        ],
                    }
                ],
            }
            pending_payload = json.loads(json.dumps(decision_payload))
            pending_payload["status"] = "pending"
            decision.write_text(json.dumps(pending_payload), encoding="utf-8")
            pending = project_status(root)
            self.assertEqual(pending["acceptance"]["state"], "pending")
            self.assertTrue(pending["handoffs_ready"])
            self.assertFalse(pending["physics_accepted"])
            self.assertFalse(pending["ready_for_consumer"])

            decision.write_text(
                json.dumps(decision_payload),
                encoding="utf-8",
            )

            accepted_status = project_status(root)
            acceptance = accepted_status["acceptance"]
            self.assertEqual(acceptance["state"], "accepted")
            self.assertEqual(acceptance["basis"], "project-declared")
            self.assertEqual(
                acceptance["machine_validation"]["state"], "not-declared"
            )
            self.assertEqual(acceptance["criteria"][0]["status"], "passed")
            self.assertEqual(acceptance["criteria"][0]["evidence"][0]["state"], "present")
            self.assertTrue(accepted_status["handoffs_ready"])
            self.assertTrue(accepted_status["physics_accepted"])
            self.assertTrue(accepted_status["project_declared_acceptance"])
            self.assertFalse(accepted_status["machine_verified_acceptance"])
            self.assertTrue(accepted_status["ready_for_consumer"])

            del decision_payload["criteria"][0]["evidence"][0]["sha256"]
            decision.write_text(json.dumps(decision_payload), encoding="utf-8")
            unverified = project_status(root)
            self.assertEqual(unverified["acceptance"]["state"], "invalid")
            self.assertEqual(
                unverified["acceptance"]["criteria"][0]["evidence"][0]["state"],
                "hash-unverified",
            )
            self.assertTrue(unverified["handoffs_ready"])
            self.assertFalse(unverified["physics_accepted"])
            self.assertFalse(unverified["ready_for_consumer"])

            decision_payload["criteria"][0]["evidence"][0]["sha256"] = _sha256(evidence)
            decision.write_text(json.dumps(decision_payload), encoding="utf-8")

            evidence.write_text('{"comparison":"changed"}\n', encoding="utf-8")
            stale_status = project_status(root)
            stale = stale_status["acceptance"]
            self.assertEqual(stale["state"], "invalid")
            self.assertTrue(any("hash mismatch" in issue for issue in stale["issues"]))
            self.assertTrue(stale_status["handoffs_ready"])
            self.assertFalse(stale_status["physics_accepted"])
            self.assertFalse(stale_status["ready_for_consumer"])

    def test_irena_machine_validator_closes_only_with_live_bound_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            machine_summary = root / "fullcore" / "fullcore_validation.json"
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fullcore",
                        "label": "Strict full core",
                        "input": "fullcore/reference.h5",
                        "output": "fullcore/native_sph.macrolib.txt",
                        "receipt": "fullcore/converter_summary.json",
                        "physics_summary": "fullcore/physics_summary.json",
                        "contract": "native-sph",
                        "format": "macrolib",
                        "evidence": [
                            {
                                "id": "fullcore-validation",
                                "label": "Full-core validation",
                                "path": "fullcore/fullcore_validation.json",
                            }
                        ],
                    }
                ],
                acceptance={
                    "decision": "acceptance/decision.json",
                    "validator": {
                        "contract": "irena30-orbit-fullcore-v1",
                        "summary": "fullcore/fullcore_validation.json",
                        "component": "fullcore",
                    },
                },
                consumer_kind="irena30-donjon-fullcore",
            )
            component = root / "fullcore"
            component.mkdir()
            reference = component / "reference.h5"
            with h5py.File(reference, "w") as h5:
                h5.create_group("mixtures")
            output = component / "native_sph.macrolib.txt"
            output.write_text("SIGNATURE\nL_MACROLIB\n", encoding="utf-8")
            physics_summary = component / "physics_summary.json"
            native_payload = _write_native_summary(
                physics_summary,
                output=output,
                reference_h5=reference,
                mixture_names=["ORBIT01", "ORBIT02"],
            )
            ledger_evidence = root / "acceptance" / "model-criteria.json"
            ledger_evidence.parent.mkdir()
            ledger_evidence.write_text('{"owner":"accepted"}\n', encoding="utf-8")
            decision = root / "acceptance" / "decision.json"
            decision.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.acceptance.v1",
                        "status": "accepted",
                        "summary": "The project owner marked every criterion passed.",
                        "criteria": [
                            {
                                "id": "owner-ledger",
                                "label": "Owner ledger",
                                "status": "passed",
                                "evidence": [
                                    {
                                        "path": "acceptance/model-criteria.json",
                                        "sha256": _sha256(ledger_evidence),
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            handwritten_only = project_status(root)
            self.assertFalse(handwritten_only["handoffs_ready"])
            self.assertFalse(handwritten_only["physics_accepted"])
            self.assertFalse(handwritten_only["ready_for_consumer"])
            self.assertEqual(handwritten_only["acceptance_basis"], "machine-verified")
            self.assertEqual(handwritten_only["acceptance"]["state"], "pending")
            self.assertEqual(
                handwritten_only["acceptance"]["machine_validation"]["state"],
                "missing",
            )

            region_verify = component / "region_verify.macrolib.txt"
            edi_output = component / "edi_output.macrolib.txt"
            result_listing = component / "fullcore.result"
            region_verify.write_text("91-region verification\n", encoding="utf-8")
            edi_output.write_text("21-orbit edition\n", encoding="utf-8")
            result_listing.write_text("normal end\n", encoding="utf-8")
            payload = _write_fullcore_machine_summary(
                machine_summary,
                native_payload=native_payload,
                physics_summary=physics_summary,
                reference_h5=reference,
                region_verify=region_verify,
                edi_output=edi_output,
                result_listing=result_listing,
            )

            accepted = project_status(root)
            self.assertEqual(accepted["acceptance"]["state"], "pending")
            self.assertEqual(
                accepted["acceptance"]["machine_validation"]["state"], "passed"
            )
            self.assertFalse(accepted["physics_accepted"])
            self.assertFalse(accepted["machine_verified_acceptance"])
            self.assertFalse(accepted["project_declared_acceptance"])
            self.assertFalse(accepted["ready_for_consumer"])

            payload["decision"] = "irena30_orbit_fullcore_review_required"
            payload["acceptance_checks"]["position_power"] = False
            machine_summary.write_text(json.dumps(payload), encoding="utf-8")
            rejected = project_status(root)
            self.assertEqual(rejected["acceptance"]["state"], "rejected")
            self.assertEqual(
                rejected["acceptance"]["machine_validation"]["state"], "rejected"
            )
            self.assertFalse(rejected["physics_accepted"])
            self.assertFalse(rejected["ready_for_consumer"])

            payload["decision"] = "irena30_orbit_fullcore_physics_passed"
            payload["acceptance_checks"]["position_power"] = True
            machine_summary.write_text(json.dumps(payload), encoding="utf-8")
            result_listing.write_text("tampered after validation\n", encoding="utf-8")
            stale = project_status(root)
            self.assertEqual(stale["acceptance"]["state"], "invalid")
            self.assertEqual(
                stale["acceptance"]["machine_validation"]["state"], "invalid"
            )
            self.assertTrue(
                any("hash mismatch" in issue for issue in stale["acceptance"]["issues"])
            )
            self.assertFalse(stale["physics_accepted"])
            self.assertFalse(stale["ready_for_consumer"])

    def test_strict_irena_template_cannot_remove_its_machine_validator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                template="irena30-fullcore-physical",
                components=[
                    {
                        "id": "fullcore",
                        "label": "Strict full core",
                        "input": "fullcore/reference.h5",
                        "output": "fullcore/native_sph.macrolib.txt",
                        "receipt": "fullcore/converter_summary.json",
                        "physics_summary": "fullcore/physics_summary.json",
                        "contract": "native-sph",
                        "format": "macrolib",
                    }
                ],
                acceptance={"decision": "acceptance/decision.json"},
                consumer_kind="irena30-donjon-fullcore",
            )

            status = project_status(root)
            self.assertFalse(status["configured"])
            self.assertIn(
                "strict IRENA full-core projects must declare acceptance.validator",
                status["configuration_issues"],
            )

    def test_manifest_editor_cannot_downgrade_a_strict_irena_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                template="irena30-fullcore-physical",
                components=[
                    {
                        "id": "fullcore",
                        "label": "Strict full core",
                        "input": "fullcore/reference.h5",
                        "output": "fullcore/native_sph.macrolib.txt",
                        "receipt": "fullcore/converter_summary.json",
                        "physics_summary": "fullcore/physics_summary.json",
                        "contract": "native-sph",
                        "format": "macrolib",
                    }
                ],
                acceptance={
                    "decision": "acceptance/decision.json",
                    "validator": {
                        "contract": "irena30-orbit-fullcore-v1",
                        "summary": "fullcore/fullcore_validation.json",
                        "component": "fullcore",
                    },
                },
                consumer_kind="irena30-donjon-fullcore",
            )
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            original = json.loads(
                (root / "openmc2donjon.project.json").read_text(encoding="utf-8")
            )
            handoff_attempt = {
                **original,
                "acceptance_mode": "handoff-only",
            }
            handoff_response = client.post(
                "/api/project/manifest",
                json={"root": str(root), "manifest": handoff_attempt},
            )
            self.assertEqual(handoff_response.status_code, 422)
            self.assertIn(
                "strict IRENA full-core projects cannot use handoff-only mode",
                handoff_response.json()["detail"],
            )

            downgraded = dict(original)
            downgraded.pop("template")
            downgraded.pop("acceptance")
            downgraded["acceptance_mode"] = "handoff-only"

            response = client.post(
                "/api/project/manifest",
                json={"root": str(root), "manifest": downgraded},
            )

            self.assertEqual(response.status_code, 422)
            self.assertIn(
                "strict IRENA full-core template identity cannot be removed",
                response.json()["detail"],
            )
            self.assertEqual(
                json.loads(
                    (root / "openmc2donjon.project.json").read_text(
                        encoding="utf-8"
                    )
                ),
                original,
            )

    def test_strict_irena_template_declares_a_missing_deck_and_remains_on_hold(
        self,
    ) -> None:
        root = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "project_templates"
            / "irena30_fullcore"
        )

        status = project_status(root)

        self.assertTrue(status["configured"])
        component = status["components"][0]
        declaration = component["native_sph"]
        self.assertEqual(
            declaration["deck_path"],
            str((root / "fullcore" / "irena30_orbit_fullcore_native_sph.x2m").resolve()),
        )
        self.assertEqual(
            declaration["working_directory"],
            str((root / "fullcore").resolve()),
        )
        self.assertFalse(Path(declaration["deck_path"]).exists())
        self.assertEqual(component["output"]["state"], "missing")
        self.assertEqual(status["acceptance_basis"], "machine-verified")
        self.assertFalse(status["handoffs_ready"])
        self.assertFalse(status["physics_accepted"])
        self.assertFalse(status["ready_for_consumer"])

    def test_create_project_writes_a_handoff_only_starter_and_all_parent_directories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "new-project"
            client = TestClient(create_app(mock_mode=False))
            response = client.post(
                "/api/project/create",
                json={"root": str(root), "name": "Assembly study"},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["configured"])
            self.assertEqual(payload["name"], "Assembly study")
            self.assertEqual(payload["required_components"], 1)
            self.assertEqual(payload["components"][0]["contract"], "converter-hdf5")
            self.assertEqual(
                payload["components"][0]["conversion"]["writer_backend"],
                "ascii",
            )
            self.assertEqual(payload["acceptance_mode"], "handoff-only")
            self.assertFalse(payload["acceptance_required"])
            self.assertEqual(payload["acceptance"]["state"], "not-required")
            self.assertEqual(payload["acceptance_basis"], "not-required")
            self.assertTrue((root / "openmc2donjon.project.json").is_file())
            self.assertFalse((root / "acceptance" / "decision.json").exists())
            self.assertTrue((root / "components" / "component-1").is_dir())
            self.assertTrue((root / "outputs").is_dir())
            self.assertTrue((root / "diagnostics").is_dir())

            input_path = root / "components" / "component-1" / "mgxs_library.h5"
            with h5py.File(input_path, "w") as h5:
                h5.create_group("mixtures")
            output = root / "outputs" / "component-1.mcompo.txt"
            output.write_text("SIGNATURE\nL_MULTICOMPO\n", encoding="utf-8")
            _write_receipt(input_path, output, require_physical_sph=False)
            completed = client.get(
                "/api/project/status",
                params={"root": str(root)},
            ).json()
            self.assertTrue(completed["handoffs_ready"])
            self.assertTrue(completed["ready_for_consumer"])
            self.assertFalse(completed["physics_accepted"])
            self.assertEqual(completed["acceptance_basis"], "not-required")

            duplicate = client.post("/api/project/create", json={"root": str(root)})
            self.assertEqual(duplicate.status_code, 409)

    def test_create_project_records_initial_pygan_writer_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pygan-project"
            client = TestClient(create_app(mock_mode=False))
            response = client.post(
                "/api/project/create",
                json={"root": str(root), "writer_backend": "pygan"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                response.json()["components"][0]["conversion"]["writer_backend"],
                "pygan",
            )
            manifest = json.loads(
                (root / "openmc2donjon.project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["components"][0]["conversion"],
                {"writer_backend": "pygan"},
            )

    def test_create_project_physics_gated_starts_pending_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "gated-project"
            client = TestClient(create_app(mock_mode=False))
            response = client.post(
                "/api/project/create",
                json={
                    "root": str(root),
                    "name": "Gated assembly study",
                    "acceptance_mode": "physics-gated",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["acceptance_mode"], "physics-gated")
            self.assertTrue(payload["acceptance_required"])
            self.assertEqual(payload["acceptance_basis"], "project-declared")
            self.assertEqual(payload["acceptance"]["state"], "pending")
            self.assertFalse(payload["ready_for_consumer"])
            self.assertTrue((root / "acceptance" / "decision.json").is_file())
            manifest = json.loads(
                (root / "openmc2donjon.project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["acceptance_mode"], "physics-gated")
            self.assertEqual(
                manifest["acceptance"]["decision"],
                "acceptance/decision.json",
            )

    def test_create_project_rejects_unknown_acceptance_mode_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bad-mode"
            client = TestClient(create_app(mock_mode=False))
            response = client.post(
                "/api/project/create",
                json={"root": str(root), "acceptance_mode": "automatic-physics"},
            )

            self.assertEqual(response.status_code, 422)
            self.assertIn("acceptance_mode", response.json()["detail"])
            self.assertFalse(root.exists())

    def test_manifest_editor_gets_and_saves_arbitrary_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel assembly",
                        "input": "components/fuel.h5",
                        "output": "outputs/fuel.mcompo.txt",
                    }
                ],
            )
            client = TestClient(
                create_app(mock_mode=False, workspace_root=Path(tmp))
            )

            loaded = client.get(
                "/api/project/manifest",
                params={"root": str(root)},
            )
            self.assertEqual(loaded.status_code, 200)
            loaded_payload = loaded.json()
            self.assertEqual(
                loaded_payload["schema"],
                "openmc2donjon.project-manifest.v1",
            )
            self.assertEqual(loaded_payload["root"], str(root.resolve()))
            manifest = loaded_payload["manifest"]
            manifest["components"].append(
                {
                    "id": "reflector",
                    "label": "Reflector region",
                    "input": "components/reflector.h5",
                    "output": "outputs/reflector.macrolib.txt",
                    "receipt": "receipts/reflector.convert.json",
                    "contract": "native-sph",
                    "format": "macrolib",
                    "evidence": [
                        {
                            "id": "run-log",
                            "label": "Run log",
                            "path": "diagnostics/reflector/run.json",
                        }
                    ],
                }
            )

            saved = client.post(
                "/api/project/manifest",
                json={"root": str(root), "manifest": manifest},
            )
            self.assertEqual(saved.status_code, 200)
            on_disk = json.loads(
                (root / "openmc2donjon.project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [item["id"] for item in on_disk["components"]],
                ["fuel", "reflector"],
            )
            self.assertTrue((root / "components").is_dir())
            self.assertTrue((root / "outputs").is_dir())
            self.assertTrue((root / "receipts").is_dir())
            self.assertTrue((root / "diagnostics" / "reflector").is_dir())
            refreshed = client.get(
                "/api/project/status",
                params={"root": str(root)},
            )
            self.assertEqual(refreshed.status_code, 200)
            self.assertTrue(refreshed.json()["configured"])
            self.assertEqual(refreshed.json()["required_components"], 2)

    def test_native_sph_execution_declaration_resolves_paths_and_bootstraps_directories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fullcore",
                        "label": "Full core",
                        "input": "handoff/reference.h5",
                        "output": "handoff/native_sph.macrolib.txt",
                        "receipt": "handoff/converter_summary.json",
                        "physics_summary": "handoff/physics_summary.json",
                        "contract": "native-sph",
                        "format": "macrolib",
                    }
                ],
            )
            manifest_path = root / "openmc2donjon.project.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["components"][0]["native_sph"] = {
                "deck": "decks/fullcore/native_sph.x2m",
                "working_directory": "runs/fullcore-native-sph",
            }
            client = TestClient(
                create_app(mock_mode=False, workspace_root=Path(tmp))
            )

            saved = client.post(
                "/api/project/manifest",
                json={"root": str(root), "manifest": manifest},
            )

            self.assertEqual(saved.status_code, 200)
            self.assertTrue((root / "decks" / "fullcore").is_dir())
            self.assertTrue((root / "runs" / "fullcore-native-sph").is_dir())
            self.assertFalse((root / "decks" / "fullcore" / "native_sph.x2m").exists())
            status = client.get(
                "/api/project/status",
                params={"root": str(root)},
            )
            self.assertEqual(status.status_code, 200)
            component = status.json()["components"][0]
            self.assertEqual(
                component["native_sph"],
                {
                    "deck_path": str(
                        (root / "decks" / "fullcore" / "native_sph.x2m").resolve()
                    ),
                    "working_directory": str(
                        (root / "runs" / "fullcore-native-sph").resolve()
                    ),
                },
            )

    def test_native_sph_execution_declaration_fails_closed_without_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "fuel.h5",
                        "output": "fuel.mcompo.txt",
                    }
                ],
            )
            occupied = root / "occupied"
            occupied.write_text("not a directory\n", encoding="utf-8")
            (root / "occupied-deck.x2m").mkdir()
            manifest_path = root / "openmc2donjon.project.json"
            original_text = manifest_path.read_text(encoding="utf-8")
            original = json.loads(original_text)
            native_component = {
                **original["components"][0],
                "contract": "native-sph",
                "format": "macrolib",
            }
            invalid_declarations = (
                (
                    {
                        **original["components"][0],
                        "native_sph": {
                            "deck": "decks/case.x2m",
                            "working_directory": "runs/case",
                        },
                    },
                    "only valid for native-sph components",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {"working_directory": "runs/case"},
                    },
                    "native_sph.deck must be a non-empty relative path",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {"deck": "decks/case.x2m"},
                    },
                    "native_sph.working_directory must be a non-empty relative path",
                ),
                (
                    {**native_component, "native_sph": None},
                    "native_sph must be an object",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {
                            "deck": str(root / "decks" / "case.x2m"),
                            "working_directory": "runs/case",
                        },
                    },
                    "native_sph.deck must be a relative path",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {
                            "deck": "decks/case.x2m",
                            "working_directory": "../outside",
                        },
                    },
                    "native_sph.working_directory must stay inside the project root",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {
                            "deck": "decks/case.txt",
                            "working_directory": "runs/case",
                        },
                    },
                    "native_sph.deck must end with .x2m",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {
                            "deck": "decks/case.x2m",
                            "working_directory": "occupied",
                        },
                    },
                    "native_sph.working_directory must be a directory",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {
                            "deck": "occupied-deck.x2m",
                            "working_directory": "runs/case",
                        },
                    },
                    "native_sph.deck must be a regular file",
                ),
                (
                    {
                        **native_component,
                        "native_sph": {
                            "deck": "same.x2m",
                            "working_directory": "same.x2m",
                        },
                    },
                    "native_sph.deck and working_directory must be different paths",
                ),
            )
            client = TestClient(create_app(mock_mode=False, workspace_root=root))

            for component, expected_issue in invalid_declarations:
                with self.subTest(expected_issue=expected_issue):
                    manifest = {**original, "components": [component]}
                    rejected = client.post(
                        "/api/project/manifest",
                        json={"root": str(root), "manifest": manifest},
                    )
                    self.assertEqual(rejected.status_code, 422)
                    self.assertIn(expected_issue, rejected.json()["detail"])
                    self.assertEqual(
                        manifest_path.read_text(encoding="utf-8"),
                        original_text,
                    )

    def test_manifest_editor_rejects_invalid_schema_paths_and_contracts_without_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(
                root,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "fuel.h5",
                        "output": "fuel.mcompo.txt",
                    }
                ],
            )
            manifest_path = root / "openmc2donjon.project.json"
            original_text = manifest_path.read_text(encoding="utf-8")
            original = json.loads(original_text)
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            invalid_manifests = (
                (
                    {**original, "schema": "unknown.project.v9"},
                    "schema must be openmc2donjon.project.v1",
                ),
                (
                    {
                        **original,
                        "components": [
                            {**original["components"][0], "input": "../outside.h5"}
                        ],
                    },
                    "must stay inside the project root",
                ),
                (
                    {
                        **original,
                        "components": [
                            {**original["components"][0], "contract": "magic-xs"}
                        ],
                    },
                    "contract must be one of",
                ),
                (
                    {
                        **original,
                        "acceptance_mode": "physics-gated",
                    },
                    "physics-gated projects must declare acceptance.decision",
                ),
                (
                    {
                        **original,
                        "acceptance_mode": "handoff-only",
                        "acceptance": {"decision": "acceptance/decision.json"},
                    },
                    "handoff-only projects must not declare an acceptance ledger",
                ),
            )

            for manifest, expected_issue in invalid_manifests:
                with self.subTest(expected_issue=expected_issue):
                    rejected = client.post(
                        "/api/project/manifest",
                        json={"root": str(root), "manifest": manifest},
                    )
                    self.assertEqual(rejected.status_code, 422)
                    self.assertIn("project manifest rejected", rejected.json()["detail"])
                    self.assertIn(expected_issue, rejected.json()["detail"])
                    self.assertEqual(
                        manifest_path.read_text(encoding="utf-8"),
                        original_text,
                    )

    def test_manifest_editor_obeys_filesystem_scope_and_mock_mode(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_raw, tempfile.TemporaryDirectory() as outside_raw:
            workspace = Path(workspace_raw)
            outside = Path(outside_raw)
            _write_manifest(
                outside,
                components=[
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "fuel.h5",
                        "output": "fuel.mcompo.txt",
                    }
                ],
            )
            manifest = json.loads(
                (outside / "openmc2donjon.project.json").read_text(encoding="utf-8")
            )
            scoped = TestClient(
                create_app(mock_mode=False, workspace_root=workspace)
            )

            denied_get = scoped.get(
                "/api/project/manifest",
                params={"root": str(outside)},
            )
            denied_save = scoped.post(
                "/api/project/manifest",
                json={"root": str(outside), "manifest": manifest},
            )
            self.assertEqual(denied_get.status_code, 403)
            self.assertEqual(denied_save.status_code, 403)

            mock = TestClient(create_app(mock_mode=True))
            mock_get = mock.get(
                "/api/project/manifest",
                params={"root": str(outside)},
            )
            mock_save = mock.post(
                "/api/project/manifest",
                json={"root": str(outside), "manifest": manifest},
            )
            self.assertEqual(mock_get.status_code, 409)
            self.assertEqual(mock_save.status_code, 409)


def _write_manifest(
    root: Path,
    *,
    components: list[dict[str, object]],
    template: str | None = None,
    acceptance: dict[str, object] | None = None,
    consumer_kind: str = "external",
) -> None:
    payload: dict[str, object] = {
        "schema": "openmc2donjon.project.v1",
        "name": "Test project",
        "components": components,
        "consumer": {"kind": consumer_kind, "label": "External", "href": "/donjon"},
    }
    if template is not None:
        payload["template"] = template
    if acceptance is not None:
        payload["acceptance"] = acceptance
    (root / "openmc2donjon.project.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_receipt(input_path: Path, output: Path, *, require_physical_sph: bool) -> None:
    receipt = output.with_name(f"{output.name}.convert.json")
    thresholds = canonical_production_thresholds()
    receipt.write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.convert.v1",
                "ok": True,
                "converted": True,
                "dry_run": False,
                "format": "multicompo",
                "production_requested": True,
                "preflight_policy": production_preflight_policy_payload(
                    production_requested=True,
                    preflight_executed=True,
                    thresholds=thresholds,
                ),
                "preflight_ok": True,
                "preflight": {
                    "schema": "openmc2donjon.mgxs-input-contract.v1",
                    "decision": "mgxs_input_contract_passed",
                    "inputs": [
                        _production_preflight_input(
                            thresholds,
                            path=str(input_path),
                        )
                    ],
                },
                "physical_sph_required": require_physical_sph,
                "input_path": str(input_path),
                "input_sha256": _sha256(input_path),
                "output_path": str(output),
                "output_sha256": _sha256(output),
            }
        ),
        encoding="utf-8",
    )


def _production_preflight_input(
    thresholds: dict[str, float],
    *,
    path: str | None = None,
) -> dict[str, object]:
    return {
        "path": path,
        "ok": True,
        "scatter_row_balance": {
            "fail_threshold": thresholds["scatter_row_balance_fail"]
        },
        "physics_checks": {
            "chi_sum_tolerance": thresholds["chi_sum_tolerance"],
            "transport_p1_fail_threshold": thresholds["transport_p1_fail"],
        },
        "uncertainty": {
            "checked": True,
            "require_coverage": True,
            "warn_threshold": thresholds["uncertainty_warn"],
            "fail_threshold": thresholds["uncertainty_fail"],
            "production_fail_threshold": thresholds[
                "uncertainty_production_fail"
            ],
            "mean_abs_floor": thresholds["uncertainty_mean_abs_floor"],
        },
    }


def _write_applied_handoff(path: Path, *, domains: int = 7) -> None:
    names = [f"domain_{index}" for index in range(1, domains + 1)]
    with h5py.File(path, "w") as h5:
        h5.create_dataset("mixture_names", data=np.asarray(names, dtype="S"))
        mixtures = h5.create_group("mixtures")
        for index, name in enumerate(names, start=1):
            mixtures.create_group(name).attrs["source_domain_index"] = index
        h5.attrs["sph_applied"] = True
        h5.attrs["sph_applied_source"] = "openmc_sph.h5"
        h5.attrs["sph_apply_operator"] = "divide-xs-by-nsph"
        h5.attrs["sph_kind"] = "openmc-ce-mg-rate"
        h5.attrs["sph_real"] = True
        h5.attrs["sph_derivation"] = "rate-preserving-ce-mg-fixed-point"
        h5.attrs["sph_target"] = "rate"
        h5.attrs["sph_flux_normalization"] = "power"
        h5.attrs["sph_zero_flux_policy"] = "reject"
        h5.attrs["sph_identity_bin_count"] = 0
        h5.attrs["sph_floored_bin_count"] = 0
        h5.attrs["sph_frozen_group_bin_count"] = 0
        h5.attrs["sph_clipped_count"] = 0
        h5.attrs["sph_max_update_residual"] = 0.01


def _write_native_summary(
    path: Path,
    *,
    output: Path,
    reference_h5: Path,
    mixture_names: list[str],
) -> dict[str, object]:
    reference_macrolib = path.with_name("reference.macrolib.txt")
    verification_macrolib = path.with_name("verification.macrolib.txt")
    result_listing = path.with_name("native_sph.result")
    converter_receipt = path.with_name("converter_summary.json")
    for evidence in (reference_macrolib, verification_macrolib, result_listing):
        evidence.write_text("live native-SPH evidence\n", encoding="utf-8")
    openmc_provenance = _bind_complete_openmc_provenance(reference_h5)
    thresholds = canonical_production_thresholds()
    converter_receipt.write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.convert.v1",
                "ok": True,
                "converted": True,
                "dry_run": False,
                "format": "macrolib",
                "production_requested": True,
                "preflight_policy": production_preflight_policy_payload(
                    production_requested=True,
                    preflight_executed=True,
                    thresholds=thresholds,
                ),
                "preflight_ok": True,
                "preflight": {
                    "schema": "openmc2donjon.mgxs-input-contract.v1",
                    "decision": "mgxs_input_contract_passed",
                    "inputs": [
                        _production_preflight_input(
                            thresholds,
                            path=str(reference_h5.resolve()),
                        )
                    ],
                },
                "physical_sph_required": False,
                "input_path": str(reference_h5.resolve()),
                "input_sha256": _sha256(reference_h5),
                "openmc_provenance": openmc_provenance,
                "output_path": str(reference_macrolib.resolve()),
                "output_sha256": _sha256(reference_macrolib),
            }
        ),
        encoding="utf-8",
    )
    evidence_sha256 = {
        "augmented_hdf5_path": _sha256(reference_h5),
        "reference_macrolib_path": _sha256(reference_macrolib),
        "macrolib_ascii_path": _sha256(output),
        "verification_macrolib_path": _sha256(verification_macrolib),
        "result_listing_path": _sha256(result_listing),
        "converter_receipt_path": _sha256(converter_receipt),
    }
    payload: dict[str, object] = {
        "schema": "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1",
        "mixture_names": mixture_names,
        "quality": {
            "production_ready": True,
            "structural_passed": True,
            "decision": "native_sph_physics_passed",
        },
        "geometry": {
            "kind": "hexagonal",
            "coarse_node_side_cm": 10.1036,
            "homogenization_volume_includes_node_catchall": True,
            "boundary_conditions": "radial vacuum; axial reflective",
        },
        "sph": {"clipped_count": 0},
        "native_sph": {
            "normal_end": True,
            "converged": True,
            "one_speed_convergence_provable": True,
            "final_flux_solve_converged": True,
            "factors_unmodified": True,
            "flux_nonconvergence_count": 0,
            "negative_factor_correction_count": 0,
            "oscillation_stop_count": 0,
        },
        "eigenvalue_validation": {
            "reference_physical_balance_kind": "finite-domain-keff",
            "reference_physical_balance_keff": 1.001,
            "reference_physical_balance_delta_pcm": 5.0,
            "reference_physical_balance_z": 0.1,
            "reference_collision_balance_kinf": 1.02,
            "reference_finite_balance_available": True,
            "reference_finite_balance_keff": 1.001,
            "reference_leakage": 0.02,
        },
        "acceptance_checks": {
            "donjon_normal_end": True,
            "native_sph_converged": True,
            "native_sph_factors_unmodified": True,
            "native_sph_not_stopped_by_oscillation": True,
            "one_speed_convergence_provable": True,
            "final_flux_solve_converged": True,
            "energy_coverage_passed": True,
            "converter_receipt_linked": True,
            "leakage_balance_available_when_required": True,
            "reference_physical_balance_within_openmc_uncertainty": True,
            "reference_rate_balance_within_openmc_uncertainty": True,
            "donjon_keff_within_openmc_uncertainty": True,
            "empirical_eigenvalue_multiplier_used": False,
            "adf_used": False,
        },
        "handoff": {
            "macrolib_ascii_path": str(output),
            "augmented_hdf5_path": str(reference_h5),
            "reference_macrolib_path": str(reference_macrolib),
            "verification_macrolib_path": str(verification_macrolib),
            "result_listing_path": str(result_listing),
            "converter_receipt_path": str(converter_receipt),
            "evidence_sha256": evidence_sha256,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _write_fullcore_machine_summary(
    path: Path,
    *,
    native_payload: dict[str, object],
    physics_summary: Path,
    reference_h5: Path,
    region_verify: Path,
    edi_output: Path,
    result_listing: Path,
) -> dict[str, object]:
    quality = native_payload["quality"]
    assert isinstance(quality, dict)
    evidence_paths = {
        "physics_summary": physics_summary,
        "reference_h5": reference_h5,
        "region_verify": region_verify,
        "edi_output": edi_output,
        "result_listing": result_listing,
    }
    payload: dict[str, object] = {
        "schema": "openmc2donjon.irena30-orbit-fullcore-physics.v1",
        "decision": "irena30_orbit_fullcore_physics_passed",
        "acceptance_checks": {
            "native_sph": True,
            "finite_balance": True,
            "position_power": True,
            "evidence_provenance": True,
        },
        "native_sph": {
            "summary_schema": native_payload["schema"],
            "summary_decision": quality["decision"],
        },
        "evidence": {
            **{label: str(item) for label, item in evidence_paths.items()},
            "input_sha256": {
                label: _sha256(item) for label, item in evidence_paths.items()
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind_complete_openmc_provenance(input_path: Path) -> dict[str, object]:
    source_dir = input_path.with_suffix(".openmc-sources")
    source_dir.mkdir(exist_ok=True)
    recipe = source_dir / "export_recipe.py"
    geometry = source_dir / "geometry.xml"
    materials = source_dir / "materials.xml"
    settings = source_dir / "settings.xml"
    cross_sections = source_dir / "cross_sections.xml"
    library = source_dir / "U235.h5"
    statepoint = source_dir / "statepoint.20.h5"
    recipe.write_text("# test recipe\n", encoding="utf-8")
    geometry.write_text("<geometry/>\n", encoding="utf-8")
    settings.write_text(
        "<settings><run_mode>eigenvalue</run_mode><particles>1000</particles>"
        "<batches>20</batches><inactive>5</inactive>"
        "<generations_per_batch>1</generations_per_batch><seed>19</seed>"
        "</settings>\n",
        encoding="utf-8",
    )
    library.write_bytes(b"test evaluated data\n")
    cross_sections.write_text(
        '<cross_sections><library materials="U235" path="U235.h5" '
        'type="neutron"/></cross_sections>\n',
        encoding="utf-8",
    )
    materials.write_text(
        "<materials><cross_sections>cross_sections.xml</cross_sections>"
        '<material id="1"><nuclide name="U235"/></material></materials>\n',
        encoding="utf-8",
    )
    with h5py.File(statepoint, "w") as h5:
        h5.attrs["filetype"] = "statepoint"
        h5.attrs["openmc_version"] = np.asarray([0, 15, 4])
        h5.attrs["version"] = np.asarray([18, 1])
        h5.create_dataset("run_mode", data=np.bytes_("eigenvalue"))
        h5.create_dataset("n_particles", data=1000)
        h5.create_dataset("n_batches", data=20)
        h5.create_dataset("n_inactive", data=5)
        h5.create_dataset("generations_per_batch", data=1)
        h5.create_dataset("seed", data=19)
        h5.create_dataset("stride", data=152917)
    record = collect_openmc_provenance(
        recipe_path=recipe,
        statepoint_path=statepoint,
        statepoint_loaded=True,
        declared_files={
            "geometry": geometry,
            "materials": materials,
            "settings": settings,
        },
        declared_metadata={"input_closure_complete": True},
    )
    assert record["capabilities"]["transport_reproducible"] is True
    return write_openmc_provenance(input_path, record)


if __name__ == "__main__":
    unittest.main()

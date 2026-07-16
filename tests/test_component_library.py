from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

import h5py
import numpy as np
import pytest

from openmc2donjon.component_library import (
    AcceptedComponent,
    ComponentPosition,
    assemble_accepted_component_library,
    expand_component_library,
)
from openmc2donjon.macrolib import read_macrolib_ascii, write_macrolib
from openmc2donjon.multicompo import MixtureXS
from openmc2donjon.native_sph_validation import SCHEMA as NATIVE_SPH_SCHEMA
from openmc2donjon.openmc_provenance import (
    collect_openmc_provenance,
    write_openmc_provenance,
)
from openmc2donjon.production_policy import (
    canonical_production_thresholds,
    production_preflight_policy_payload,
)


def test_assembles_declared_mixtures_without_averaging_or_empirical_factor() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        int_source = root / "int_ext.macrolib.txt"
        pnl_source = root / "pnl_ext.macrolib.txt"
        int_summary = root / "int_summary.json"
        pnl_summary = root / "pnl_summary.json"
        output = root / "component_library.macrolib.txt"
        receipt = root / "component_library.json"

        write_macrolib(
            [_mixture("INT", 1.1, 0.95), _mixture("EXT", 2.1, 1.05)],
            np.array([1.0, 2.0, 3.0]),
            int_source,
        )
        write_macrolib(
            [_mixture("PNL", 3.1, 0.75), _mixture("EXT", 4.1, 1.15)],
            np.array([1.0, 2.0, 3.0]),
            pnl_source,
        )
        _write_summary(int_summary, int_source, ["INT", "EXT"])
        _write_summary(pnl_summary, pnl_source, ["PNL", "EXT"])

        payload = assemble_accepted_component_library(
            [
                AcceptedComponent("inner", int_source, int_summary, "INT"),
                AcceptedComponent("shield", pnl_source, pnl_summary, "PNL"),
            ],
            output,
            summary_json=receipt,
        )

        merged = read_macrolib_ascii(output)
        assert payload["component_names"] == ["inner", "shield"]
        assert payload["physics_policy"]["cross_section_averaging"] is False
        np.testing.assert_allclose(merged.ntot0[0], [1.1, 1.1])
        np.testing.assert_allclose(merged.ntot0[1], [3.1, 3.1])
        np.testing.assert_allclose(merged.sph[0], [0.95, 0.95])
        np.testing.assert_allclose(merged.sph[1], [0.75, 0.75])
        assert receipt.is_file()


def test_rejects_unaccepted_or_mismatched_physics_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.macrolib.txt"
        other = root / "other.macrolib.txt"
        summary = root / "physics.json"
        write_macrolib(
            [_mixture("fuel", 1.0, 1.0)],
            np.array([1.0, 2.0, 3.0]),
            source,
        )
        other.write_text("not selected\n", encoding="utf-8")
        _write_summary(summary, other, ["fuel"])

        with pytest.raises(ValueError, match="does not match"):
            assemble_accepted_component_library(
                [AcceptedComponent("fuel", source, summary, "fuel")],
                root / "out.macrolib.txt",
            )

        _write_summary(summary, source, ["fuel"], production_ready=False)
        with pytest.raises(ValueError, match="not production-ready"):
            assemble_accepted_component_library(
                [AcceptedComponent("fuel", source, summary, "fuel")],
                root / "out.macrolib.txt",
            )


def test_rejects_legacy_or_contradictory_native_solver_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "pnl_ext.macrolib.txt"
        summary = root / "pnl_ext.physics.json"
        write_macrolib(
            [_mixture("PNL", 1.0, 1.0)],
            np.array([1.0, 2.0, 3.0]),
            source,
        )
        _write_summary(summary, source, ["PNL"])

        accepted = json.loads(summary.read_text(encoding="utf-8"))

        hashless = json.loads(json.dumps(accepted))
        hashless["handoff"].pop("evidence_sha256")
        summary.write_text(json.dumps(hashless), encoding="utf-8")
        with pytest.raises(ValueError, match="no evidence SHA-256 manifest"):
            assemble_accepted_component_library(
                [AcceptedComponent("shield", source, summary, "PNL")],
                root / "out.macrolib.txt",
            )

        missing_deck = json.loads(json.dumps(accepted))
        missing_deck["handoff"].pop("execution_deck_path")
        missing_deck["handoff"]["evidence_sha256"].pop("execution_deck_path")
        summary.write_text(json.dumps(missing_deck), encoding="utf-8")
        with pytest.raises(ValueError, match="executed CLE-2000 deck"):
            assemble_accepted_component_library(
                [AcceptedComponent("shield", source, summary, "PNL")],
                root / "out.macrolib.txt",
            )

        result_listing = Path(accepted["handoff"]["result_listing_path"])
        original_listing = result_listing.read_text(encoding="utf-8")
        result_listing.write_text(original_listing + "tampered\n", encoding="utf-8")
        summary.write_text(json.dumps(accepted), encoding="utf-8")
        with pytest.raises(ValueError, match="result listing evidence hash mismatch"):
            assemble_accepted_component_library(
                [AcceptedComponent("shield", source, summary, "PNL")],
                root / "out.macrolib.txt",
            )
        result_listing.write_text(original_listing, encoding="utf-8")

        converter_receipt = Path(accepted["handoff"]["converter_receipt_path"])
        original_receipt = converter_receipt.read_text(encoding="utf-8")
        broken_receipt = json.loads(original_receipt)
        broken_receipt["input_sha256"] = "0" * 64
        converter_receipt.write_text(json.dumps(broken_receipt), encoding="utf-8")
        receipt_mismatch = json.loads(json.dumps(accepted))
        receipt_mismatch["handoff"]["evidence_sha256"][
            "converter_receipt_path"
        ] = _sha256(converter_receipt)
        summary.write_text(json.dumps(receipt_mismatch), encoding="utf-8")
        with pytest.raises(ValueError, match="Converter receipt input hash"):
            assemble_accepted_component_library(
                [AcceptedComponent("shield", source, summary, "PNL")],
                root / "out.macrolib.txt",
            )
        converter_receipt.write_text(original_receipt, encoding="utf-8")

        for raw_gate in (
            "one_speed_convergence_provable",
            "final_flux_solve_converged",
            "factors_unmodified",
        ):
            payload = json.loads(json.dumps(accepted))
            payload["native_sph"][raw_gate] = False
            summary.write_text(json.dumps(payload), encoding="utf-8")
            with pytest.raises(ValueError, match=raw_gate):
                assemble_accepted_component_library(
                    [AcceptedComponent("shield", source, summary, "PNL")],
                    root / "out.macrolib.txt",
                )

        payload = json.loads(json.dumps(accepted))
        payload["eigenvalue_validation"]["reference_physical_balance_kind"] = "collision-balance-kinf"
        summary.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="vacuum geometry requires"):
            assemble_accepted_component_library(
                [AcceptedComponent("shield", source, summary, "PNL")],
                root / "out.macrolib.txt",
            )

        # This is the legacy PNL-style bypass: production_ready and a few old
        # checks say pass, but the raw solver/final-solve evidence is absent.
        payload = json.loads(json.dumps(accepted))
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
        with pytest.raises(ValueError, match="raw solver evidence"):
            assemble_accepted_component_library(
                [AcceptedComponent("shield", source, summary, "PNL")],
                root / "out.macrolib.txt",
            )


def test_expands_accepted_components_in_declared_position_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.macrolib.txt"
        source_summary = root / "source.physics.json"
        library = root / "components.macrolib.txt"
        library_summary = root / "components.summary.json"
        expanded = root / "positions.macrolib.txt"
        expanded_summary = root / "positions.summary.json"
        write_macrolib(
            [_mixture("INT", 1.1, 0.95), _mixture("EXT", 2.1, 1.05)],
            np.array([1.0, 2.0, 3.0]),
            source,
        )
        _write_summary(source_summary, source, ["INT", "EXT"])
        assemble_accepted_component_library(
            [
                AcceptedComponent("inner", source, source_summary, "INT"),
                AcceptedComponent("outer", source, source_summary, "EXT"),
            ],
            library,
            summary_json=library_summary,
        )

        payload = expand_component_library(
            library,
            library_summary,
            [
                ComponentPosition("R0P00_INT", "inner"),
                ComponentPosition("R1P00_EXT", "outer"),
                ComponentPosition("R1P01_INT", "inner"),
            ],
            expanded,
            summary_json=expanded_summary,
        )

        mapped = read_macrolib_ascii(expanded)
        assert payload["position_count"] == 3
        assert [row["component"] for row in payload["assignments"]] == [
            "inner",
            "outer",
            "inner",
        ]
        np.testing.assert_allclose(mapped.ntot0[:, 0], [1.1, 2.1, 1.1])
        np.testing.assert_allclose(mapped.sph[:, 0], [0.95, 1.05, 0.95])
        assert payload["physics_policy"]["cross_section_fitting"] is False


def test_expand_rejects_tampered_component_library() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.macrolib.txt"
        source_summary = root / "source.physics.json"
        library = root / "components.macrolib.txt"
        library_summary = root / "components.summary.json"
        write_macrolib(
            [_mixture("INT", 1.1, 0.95)],
            np.array([1.0, 2.0, 3.0]),
            source,
        )
        _write_summary(source_summary, source, ["INT"])
        assemble_accepted_component_library(
            [AcceptedComponent("inner", source, source_summary, "INT")],
            library,
            summary_json=library_summary,
        )
        library.write_text(library.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="hash does not match"):
            expand_component_library(
                library,
                library_summary,
                [ComponentPosition("R0P00_INT", "inner")],
                root / "expanded.macrolib.txt",
            )


def _mixture(name: str, total: float, sph: float) -> MixtureXS:
    return MixtureXS(
        name=name,
        total=np.full(2, total),
        absorption=np.full(2, total - 0.1),
        fission=np.full(2, 0.2),
        nu_fission=np.full(2, 0.5),
        chi=np.array([1.0, 0.0]),
        scatter_matrix=np.array([np.eye(2) * 0.1]),
        fissionable=True,
        volume=2.0,
        transport_total=np.full(2, total),
        flux_weight=np.array([4.0, 2.0]),
        sph=np.full(2, sph),
    )


def _write_summary(
    path: Path,
    macrolib: Path,
    names: list[str],
    *,
    production_ready: bool = True,
) -> None:
    reference_h5 = path.with_name(f"{path.stem}.reference.h5")
    reference_macrolib = path.with_name(f"{path.stem}.reference.macrolib.txt")
    verification_macrolib = path.with_name(f"{path.stem}.verification.macrolib.txt")
    result_listing = path.with_name(f"{path.stem}.result")
    converter_receipt = path.with_name(f"{path.stem}.converter.json")
    energy_coverage = path.with_name(f"{path.stem}.energy-coverage.json")
    execution_deck = path.with_name(f"{path.stem}.x2m")
    with h5py.File(reference_h5, "w") as h5:
        h5.create_dataset("reference", data=np.asarray([1.0]))
    openmc_provenance = _bind_complete_openmc_provenance(reference_h5)
    reference_macrolib.write_bytes(macrolib.read_bytes())
    verification_macrolib.write_bytes(macrolib.read_bytes())
    deck_text = (
        "MODULE SPH: FLUD: OUT: END: ;\n"
        "LINKED_LIST MACROREF MACROSPH TRACK SYSTEM FLUX ;\n"
        "MACROSPH := SPH: MACROREF TRACK :: EDIT 0 MAXI 300 EPSI 1.0E-6 ;\n"
        "SYSTEM := OUT: MACROSPH TRACK :: EDIT 0 ;\n"
        "FLUX := FLUD: SYSTEM TRACK :: EDIT 0 ;\n"
        "SPH_ASC := MACROSPH ;\n"
        "END: ;\n"
    )
    execution_deck.write_text(deck_text, encoding="utf-8")
    result_listing.write_text(
        deck_text + "live native-SPH result evidence\n", encoding="utf-8"
    )
    energy_coverage.write_text(
        json.dumps({"schema": "openmc2donjon.energy-coverage.v1"}),
        encoding="utf-8",
    )
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
                        {
                            "ok": True,
                            "scatter_row_balance": {
                                "fail_threshold": thresholds[
                                    "scatter_row_balance_fail"
                                ]
                            },
                            "physics_checks": {
                                "chi_sum_tolerance": thresholds[
                                    "chi_sum_tolerance"
                                ],
                                "transport_p1_fail_threshold": thresholds[
                                    "transport_p1_fail"
                                ],
                            },
                            "uncertainty": {
                                "checked": True,
                                "require_coverage": True,
                                "warn_threshold": thresholds["uncertainty_warn"],
                                "fail_threshold": thresholds["uncertainty_fail"],
                                "production_fail_threshold": thresholds[
                                    "uncertainty_production_fail"
                                ],
                                "mean_abs_floor": thresholds[
                                    "uncertainty_mean_abs_floor"
                                ],
                            },
                        }
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
        "macrolib_ascii_path": _sha256(macrolib),
        "verification_macrolib_path": _sha256(verification_macrolib),
        "result_listing_path": _sha256(result_listing),
        "energy_coverage_path": _sha256(energy_coverage),
        "converter_receipt_path": _sha256(converter_receipt),
        "execution_deck_path": _sha256(execution_deck),
    }
    path.write_text(
        json.dumps(
            {
                "schema": NATIVE_SPH_SCHEMA,
                "mixture_names": names,
                "quality": {
                    "production_ready": production_ready,
                    "structural_passed": production_ready,
                    "decision": (
                        "native_sph_physics_passed" if production_ready else "native_sph_review_required"
                    ),
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
                "sph": {"clipped_count": 0},
                "geometry": {
                    "kind": "hexagonal",
                    "coarse_node_side_cm": 10.1036,
                    "homogenization_volume_includes_node_catchall": True,
                    "boundary_conditions": "radial vacuum; axial reflective",
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
                "handoff": {
                    "macrolib_ascii_path": str(macrolib.resolve()),
                    "augmented_hdf5_path": str(reference_h5.resolve()),
                    "reference_macrolib_path": str(reference_macrolib.resolve()),
                    "verification_macrolib_path": str(verification_macrolib.resolve()),
                    "result_listing_path": str(result_listing.resolve()),
                    "energy_coverage_path": str(energy_coverage.resolve()),
                    "converter_receipt_path": str(converter_receipt.resolve()),
                    "execution_deck_path": str(execution_deck.resolve()),
                    "evidence_sha256": evidence_sha256,
                },
            }
        ),
        encoding="utf-8",
    )


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

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np


class OpenMCCeMgSphMinicaseExampleTests(unittest.TestCase):
    def test_example_python_files_are_parseable(self) -> None:
        for name in (
            "build_ce_case.py",
            "colorset_model.py",
            "export_recipe.py",
            "prepare_mg_case.py",
            "summarize_damping_sweep.py",
            "summarize_outputs.py",
        ):
            path = _example_dir() / name
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_model_declares_openmc_ce_mg_sph_contract(self) -> None:
        text = (_example_dir() / "colorset_model.py").read_text(encoding="utf-8")

        self.assertIn('ENERGY_MESH_ID = "ecco_33"', text)
        self.assertIn("LEGENDRE_ORDER = 3", text)
        self.assertIn('MG_MACRO_SCATTER_FORMAT = "histogram"', text)
        self.assertIn("MG_MACRO_HISTOGRAM_BINS = 16", text)
        self.assertIn("OPENMC2DONJON_COLORSET_VARIANT", text)
        self.assertIn("five_region_2d", text)
        self.assertIn("REGION_SPECS_BY_VARIANT", text)
        self.assertIn("DOMAIN_IDS = tuple(spec.cell_id for spec in REGION_SPECS)", text)
        self.assertIn("VOLUME_FLUX_TALLY_NAME", text)
        self.assertIn("reverse_openmc_energy_filter_flux", text)
        self.assertIn("write_openmc_volume_flux_hdf5", text)
        self.assertIn('"sph_route"', text)
        self.assertIn("OpenMC CE reference + OpenMC MG same geometry", text)
        self.assertIn('"colorset_variant"', text)
        self.assertIn('"output_region_count"', text)

    def test_recipe_uses_explicit_domain_specs_and_flux_postprocess(self) -> None:
        text = (_example_dir() / "export_recipe.py").read_text(encoding="utf-8")

        self.assertIn("from openmc2donjon import DomainExportSpec", text)
        self.assertIn("def domain_specs(library):", text)
        self.assertIn("colorset_region", text)
        self.assertIn("def extra_tallies(library):", text)
        self.assertIn("build_volume_flux_tally", text)
        self.assertIn("def postprocess_hdf5(output_path, statepoint_path, summary):", text)
        self.assertIn("append_volume_flux_hdf5", text)

    def test_prepare_mg_case_builds_openmc_mg_model_from_ce_statepoint(self) -> None:
        text = (_example_dir() / "prepare_mg_case.py").read_text(encoding="utf-8")

        self.assertIn("library.create_mg_mode()", text)
        self.assertIn('energy_mode="multi-group"', text)
        self.assertIn("--scatter-format", text)
        self.assertIn("--histogram-bins", text)
        self.assertIn("mgxs_path = (mg_dir / args.mgxs_name).resolve()", text)
        self.assertIn("materials.cross_sections = str(mgxs_path)", text)
        self.assertIn("mgxs_file.export_to_hdf5", text)
        self.assertIn("apply_sph_to_openmc_mgxs_hdf5", text)
        self.assertIn("--sph-source", text)
        self.assertIn("--raw-mgxs-name", text)
        self.assertIn("build_mg_tallies", text)

    def test_readme_and_workflow_keep_donjon_loop_out_of_the_route(self) -> None:
        readme = (_example_dir() / "README.md").read_text(encoding="utf-8")
        script = (_example_dir() / "run_workflow.sh").read_text(encoding="utf-8")

        self.assertIn("OpenMC continuous-energy reference", readme)
        self.assertIn("OpenMC multi-group macro calculation", readme)
        self.assertIn("using the selected energy mesh", readme)
        self.assertIn("limited to 33 groups", readme)
        self.assertIn("CS_FUEL  -> DONJON mixture 1", readme)
        self.assertIn("CS_MOD   -> DONJON mixture 2", readme)
        self.assertIn("CS_ABS   -> DONJON mixture 3", readme)
        self.assertIn("OPENMC2DONJON_COLORSET_VARIANT=five_region_2d", readme)
        self.assertIn("CS_FUEL_L -> fuel-like output region", readme)
        self.assertIn("CS_REF    -> reflector-like output region", readme)
        self.assertIn("does **not** use a DONJON feedback loop", readme)
        self.assertIn("H16 histogram scatter", readme)
        self.assertIn("SPH(region, group)", readme)
        self.assertIn("SPH_ITERATIONS=1", readme)
        self.assertIn("SPH_DAMPING=1.0", readme)
        self.assertIn("summarize_damping_sweep.py", readme)
        self.assertIn("--input-format openmc-mgxs", readme)

        self.assertIn("build_ce_case.py", script)
        self.assertIn("prepare_mg_case.py", script)
        self.assertIn("MG_MACRO_SCATTER_FORMAT", script)
        self.assertIn("colorset variant: $COLORSET_VARIANT", script)
        self.assertIn("--scatter-format \"$MG_MACRO_SCATTER_FORMAT\"", script)
        self.assertIn("ITER_MG_MACRO_SUMMARY=\"$OUT_DIR/mg_macro_summary.json\"", script)
        self.assertIn("--summary-json \"$ITER_MG_MACRO_SUMMARY\"", script)
        self.assertIn("SPH_ITERATIONS", script)
        self.assertIn("--damping \"$SPH_DAMPING\"", script)
        self.assertIn("--clip-min \"$SPH_CLIP_MIN\"", script)
        self.assertIn("--clip-max \"$SPH_CLIP_MAX\"", script)
        self.assertIn("--previous-sph \"$PREVIOUS_SPH\"", script)
        self.assertIn("--dataset-name openmc_volume_flux", script)
        self.assertIn("--dataset-name openmc_mg_flux", script)
        self.assertIn("make-openmc-sph-sidecar", script)
        self.assertIn("--require-reference-flux-std-dev", script)
        self.assertIn("--require-mg-flux-std-dev", script)
        self.assertIn("OPENMC_LIB_DIR", readme)
        self.assertIn("OPENMC_LIB_DIR", script)
        self.assertIn("DYLD_LIBRARY_PATH", script)
        self.assertIn("LD_LIBRARY_PATH", script)
        self.assertNotIn("run-sph-loop", script)

    def test_next_validation_target_points_to_five_region_variant(self) -> None:
        target = (_example_dir() / "NEXT_PHYSICS_VALIDATION.md").read_text(encoding="utf-8")

        self.assertIn("OPENMC2DONJON_COLORSET_VARIANT=five_region_2d", target)
        self.assertIn("5 to 9 output regions", target)
        self.assertIn("uncorrected DONJON handoff", target)
        self.assertIn("SPH-corrected DONJON handoff", target)
        self.assertIn("same scripts as the three-region", target)

    def test_donjon_consume_smoke_is_documented_as_downstream_handoff(self) -> None:
        readme = (_example_dir() / "README.md").read_text(encoding="utf-8")
        evidence = (_example_dir() / "PRODUCTION_EVIDENCE.md").read_text(encoding="utf-8")
        wrapper = (_example_dir() / "run_donjon_consume_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("run_donjon_consume_smoke.sh", readme)
        self.assertIn("DSPH:", readme)
        self.assertIn("MAC:", readme)
        self.assertIn("GROUP/*/NSPH", readme)
        self.assertIn("not a k-effective benchmark", readme)

        self.assertIn("scripts/run_donjon_sph_consume_smoke.sh", wrapper)
        self.assertIn(
            'RUN_TAG="${RUN_TAG:-openmc_ce_mg_33g_sph_macrolib_donjon_smoke}"',
            wrapper,
        )
        self.assertIn("out_with_openmc_sph.macrolib.txt", wrapper)

        self.assertIn("DONJON consume smoke", evidence)
        self.assertIn("expected_mix3_g1=1.05946788", evidence)
        self.assertIn("pn_ntot0_ratio=1.05946786", evidence)
        self.assertIn("DSPH:", evidence)
        self.assertIn("MAC:", evidence)

    def test_donjon_solve_diagnostic_is_documented_as_review_evidence(self) -> None:
        readme = (_example_dir() / "README.md").read_text(encoding="utf-8")
        evidence = (_example_dir() / "PRODUCTION_EVIDENCE.md").read_text(encoding="utf-8")
        script = (_example_dir() / "run_donjon_solve_diagnostic.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("run_donjon_solve_diagnostic.sh", readme)
        self.assertIn("donjon_solve_summary.json", readme)
        self.assertIn("not a benchmark acceptance\ngate", readme)
        self.assertIn("uncorrected and SPH-corrected", readme)
        self.assertIn("matching 3 x 2 `CAR2D` colorset", readme)
        self.assertIn("area-weights the repeated left-fuel cells", readme)
        self.assertIn("TRIVAT/TRIVAA/FLUD", readme)

        self.assertIn("DONJON solve diagnostic", evidence)
        self.assertIn("diffusion k=0.8899511", evidence)
        self.assertIn("spn3 k=0.9084644", evidence)
        self.assertIn("not as a\nk-effective benchmark", evidence)

        self.assertIn("donjon_solve_diagnostic_recorded", script)
        self.assertIn("DUAL 1 1 SPN 3 SCAT 2", script)
        self.assertIn("out_uncorrected.macrolib.txt", script)
        self.assertIn("sph_corrected", script)
        self.assertIn("CAR2D 3 2", script)
        self.assertIn("1 2 4", script)
        self.assertIn("1 3 5", script)
        self.assertIn("cell_mixture_map", script)
        self.assertIn("flux_shape_mean_relative_residual", script)

    def test_production_evidence_fixture_records_openmc_sph_handoff_quality(self) -> None:
        evidence = (_example_dir() / "PRODUCTION_EVIDENCE.md").read_text(encoding="utf-8")
        fixture = _repo_root() / "src/openmc2donjon/web/fixtures/openmc_sph_physics_summary.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))

        self.assertIn("openmc_ce_mg_sph_production_quality", evidence)
        self.assertIn("not a DONJON feedback loop", evidence)
        self.assertIn("MACROLIB handoff", evidence)
        self.assertEqual(
            payload["schema"],
            "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
        )
        self.assertEqual(payload["route"], "OpenMC CE reference + OpenMC MG same geometry -> OpenMC-side SPH")
        self.assertEqual(payload["energy_groups"], 33)
        self.assertEqual(
            payload["mixture_names"],
            ["CS_FUEL_L", "CS_MOD", "CS_FUEL_U", "CS_ABS", "CS_REF"],
        )
        self.assertEqual(payload["handoff_scatter"]["format"], "legendre")
        self.assertEqual(payload["handoff_scatter"]["legendre_order"], 3)
        self.assertEqual(payload["mg_macro_scatter"]["scatter_format"], "histogram")
        self.assertEqual(payload["mg_macro_scatter"]["histogram_bins"], 16)
        self.assertEqual(payload["quality"]["decision"], "openmc_ce_mg_sph_production_quality")
        self.assertTrue(payload["quality"]["production_ready"])
        self.assertLessEqual(
            payload["flux_uncertainty"]["ce_max_relative_std_dev"],
            payload["quality"]["production_flux_relative_std_dev_threshold"],
        )
        self.assertLessEqual(
            payload["flux_uncertainty"]["mg_max_relative_std_dev"],
            payload["quality"]["production_flux_relative_std_dev_threshold"],
        )
        self.assertEqual(payload["sph"]["clipped_count"], 0)
        self.assertAlmostEqual(payload["sph"]["minimum"], 0.922629545852)
        self.assertAlmostEqual(payload["sph"]["maximum"], 1.0180355502)
        self.assertEqual(payload["handoff"]["accepted_sph_consumption_format"], "macrolib")
        self.assertEqual(payload["handoff"]["macrolib_ascii_nsp_block_count"], 33)
        self.assertTrue(payload["handoff"]["augmented_hdf5_has_sph"])
        self.assertEqual(payload["donjon_consumption"]["status"], "passed")
        self.assertAlmostEqual(
            payload["donjon_consumption"]["expected_mix3_g1"],
            0.93348071,
        )
        self.assertAlmostEqual(
            payload["donjon_consumption"]["pn_ntot0_ratio"],
            0.933480726,
        )
        self.assertEqual(
            payload["donjon_solve_diagnostic"]["decision"],
            "donjon_solve_diagnostic_recorded",
        )
        self.assertAlmostEqual(
            payload["donjon_solve_diagnostic"]["modes"]["spn3"]["k_effective"],
            1.300365,
        )
        self.assertAlmostEqual(
            payload["donjon_solve_diagnostic"]["modes"]["spn3"]["vs_openmc_ce"][
                "flux_shape_mean_relative_residual"
            ],
            0.22490191950241656,
        )
        self.assertLess(
            payload["reaction_rate_preservation"]["after_sph_update_frozen_flux"][
                "max_relative_residual"
            ],
            1.0e-10,
        )
        self.assertGreater(
            payload["reaction_rate_preservation"]["current_solve"]["max_relative_residual"],
            0.05,
        )

    def test_summary_script_writes_physics_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp)
            _write_summary_fixture(handoff)
            module = _load_summary_module()

            rc = module.main(["--handoff-dir", str(handoff)])

            self.assertEqual(rc, 0)
            payload = json.loads((handoff / "physics_summary.json").read_text(encoding="utf-8"))
            markdown = (handoff / "physics_summary.md").read_text(encoding="utf-8")
            self.assertEqual(
                payload["schema"],
                "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
            )
            self.assertEqual(payload["mixture_count"], 2)
            self.assertEqual(payload["energy_groups"], 2)
            self.assertEqual(payload["legendre_order"], 3)
            self.assertEqual(payload["mg_macro_scatter"]["scatter_format"], "histogram")
            self.assertEqual(payload["mg_macro_scatter"]["histogram_bins"], 16)
            self.assertEqual(payload["handoff"]["ascii_nsp_block_count"], 1)
            self.assertEqual(payload["handoff"]["accepted_sph_consumption_format"], "macrolib")
            self.assertEqual(payload["handoff"]["macrolib_ascii_nsp_block_count"], 1)
            self.assertTrue(payload["handoff"]["augmented_hdf5_has_sph"])
            self.assertEqual(payload["quality"]["decision"], "openmc_ce_mg_sph_production_quality")
            self.assertTrue(payload["quality"]["production_ready"])
            self.assertTrue(payload["quality"]["demonstration_quality"])
            self.assertIn("reaction_rate_preservation", payload)
            preservation = payload["reaction_rate_preservation"]
            self.assertAlmostEqual(
                preservation["current_solve"]["max_relative_residual"],
                0.2,
            )
            self.assertAlmostEqual(
                preservation["after_sph_update_frozen_flux"]["max_relative_residual"],
                0.0,
            )
            self.assertEqual(len(payload["sph_iterations"]), 1)
            self.assertIn("OpenMC CE/MG SPH Physics Summary", markdown)
            self.assertIn("## Quality", markdown)
            self.assertIn("## SPH Iterations", markdown)
            self.assertIn("## Reaction-Rate Preservation", markdown)
            self.assertIn("Accepted SPH consumption format", markdown)
            self.assertIn("CS_FUEL", markdown)

    def test_summary_records_sph_iteration_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp)
            _write_summary_fixture(handoff)
            _write_iteration_summary(handoff, 1, sph_min=0.8, sph_max=1.4)
            _write_iteration_summary(
                handoff,
                2,
                sph_min=0.7,
                sph_max=1.6,
                previous_sph=str(handoff / "openmc_sph_sidecar_iter01.h5"),
            )
            (handoff / "sph_apply_summary_iter02.json").write_text(
                json.dumps(
                    {
                        "decision": "openmc2donjon_sph_apply_passed",
                        "input_format": "openmc-mgxs",
                        "input_h5": str(handoff / "mg_case_iter02/mgxs_unapplied.h5"),
                        "output_h5": str(handoff / "mg_case_iter02/mgxs.h5"),
                        "sph_source": str(handoff / "openmc_sph_sidecar_iter01.h5"),
                        "scaled_dataset_count": 12,
                        "sph_min": 0.8,
                        "sph_max": 1.4,
                    }
                ),
                encoding="utf-8",
            )
            module = _load_summary_module()

            summary = module.summarize_handoff(handoff)
            markdown = module.render_markdown(summary)

            self.assertEqual(len(summary["sph_iterations"]), 2)
            self.assertEqual(summary["sph_iterations"][0]["iteration"], 1)
            self.assertEqual(
                summary["sph_iterations"][1]["previous_sph"],
                str(handoff / "openmc_sph_sidecar_iter01.h5"),
            )
            self.assertEqual(
                summary["sph_iterations"][1]["openmc_mgxs_apply"]["input_format"],
                "openmc-mgxs",
            )
            self.assertEqual(
                summary["sph_iterations"][1]["openmc_mgxs_apply"]["scaled_dataset_count"],
                12,
            )
            self.assertIn("openmc-mgxs, 12 datasets", markdown)

    def test_summary_marks_noisy_flux_as_statistical_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp)
            _write_summary_fixture(handoff, flux_std_scale=0.60)
            module = _load_summary_module()

            summary = module.summarize_handoff(handoff)

            self.assertEqual(
                summary["quality"]["decision"],
                "openmc_ce_mg_sph_statistical_review_required",
            )
            self.assertFalse(summary["quality"]["production_ready"])
            self.assertFalse(summary["quality"]["demonstration_quality"])
            self.assertGreater(summary["quality"]["max_flux_relative_std_dev"], 0.30)

    def test_damping_sweep_summary_compares_physics_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_10 = root / "damping_1p0"
            case_05 = root / "damping_0p5" / "handoff"
            case_10.mkdir(parents=True)
            case_05.mkdir(parents=True)
            _write_sweep_physics_summary(
                case_10 / "physics_summary.json",
                damping=1.0,
                current_residual=0.24,
                after_residual=0.09,
            )
            _write_sweep_physics_summary(
                case_05 / "physics_summary.json",
                damping=0.5,
                current_residual=0.18,
                after_residual=0.03,
            )
            module = _load_sweep_module()

            summary = module.summarize_sweep(
                [
                    f"undamped={case_10 / 'physics_summary.json'}",
                    f"damped={case_05.parent}",
                ]
            )
            markdown = module.render_markdown(summary)

            self.assertEqual(summary["schema"], "openmc2donjon.openmc-ce-mg-sph-damping-sweep.v1")
            self.assertEqual(summary["case_count"], 2)
            self.assertEqual(summary["best_by_after_update_residual"]["label"], "damped")
            self.assertEqual(summary["best_by_current_solve_residual"]["label"], "damped")
            self.assertIn("OpenMC-side SPH Damping Sweep", markdown)
            self.assertIn("undamped", markdown)
            self.assertIn("damped", markdown)
            self.assertIn("Best frozen-flux residual", markdown)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _example_dir() -> Path:
    return _repo_root() / "examples/openmc_ce_mg_33g_sph_minicase"


def _load_summary_module():
    path = _example_dir() / "summarize_outputs.py"
    spec = importlib.util.spec_from_file_location("_openmc2donjon_minicase_summary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_sweep_module():
    path = _example_dir() / "summarize_damping_sweep.py"
    spec = importlib.util.spec_from_file_location("_openmc2donjon_damping_sweep", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_summary_fixture(handoff: Path, *, flux_std_scale: float = 0.01) -> None:
    names = np.array(["CS_FUEL", "CS_MOD"], dtype=h5py.string_dtype(encoding="utf-8"))
    energy_bounds = np.array([0.0, 1.0, 2.0])
    sph = {
        "CS_FUEL": np.array([0.9, 1.1]),
        "CS_MOD": np.array([1.0, 1.2]),
    }
    with h5py.File(handoff / "mgxs_library.h5", "w") as h5:
        h5.attrs["legendre_order"] = 3
        h5.create_dataset("energy_bounds", data=energy_bounds)
        h5.create_dataset("mixture_names", data=names)
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("CS_FUEL")
        fuel.create_dataset("absorption", data=np.array([0.5, 0.25]))
        fuel.create_dataset("fission", data=np.array([0.2, 0.1]))
        fuel.create_dataset("nu_fission", data=np.array([0.5, 0.25]))
        mod = mixtures.create_group("CS_MOD")
        mod.create_dataset("absorption", data=np.array([0.1, 0.2]))
        mod.create_dataset("fission", data=np.array([0.0, 0.0]))
        mod.create_dataset("nu_fission", data=np.array([0.0, 0.0]))
    with h5py.File(handoff / "mgxs_with_openmc_sph.h5", "w") as h5:
        h5.create_dataset("energy_bounds", data=energy_bounds)
        h5.create_dataset("mixture_names", data=names)
        mixtures = h5.create_group("mixtures")
        for name, values in sph.items():
            mixtures.create_group(name).create_dataset("sph", data=values)
    _write_flux_h5(
        handoff / "openmc_ce_flux.h5",
        "openmc_volume_flux",
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        flux_std_scale=flux_std_scale,
    )
    _write_flux_h5(
        handoff / "openmc_mg_flux.h5",
        "openmc_mg_flux",
        np.array([[0.9, 2.2], [3.0, 4.8]]),
        flux_std_scale=flux_std_scale,
    )
    with h5py.File(handoff / "openmc_sph_sidecar.h5", "w") as h5:
        h5.create_dataset("sph", data=np.array([[0.9, 1.1], [1.0, 1.2]]))
    (handoff / "openmc_sph_summary.json").write_text(
        json.dumps(
            {
                "decision": "openmc2donjon_openmc_sph_sidecar_passed",
                "flux_normalization": "power",
                "formula": "sph = normalized_openmc_mg_flux / openmc_ce_reference_flux",
                "normalization_factor": 1.0,
                "sph_kind": "openmc-ce-mg",
                "sph_real": True,
                "sph_min": 0.9,
                "sph_max": 1.2,
                "raw_update_minimum": 0.9,
                "raw_update_maximum": 1.2,
                "reference_flux_max_relative_std_dev": flux_std_scale,
                "mg_flux_max_relative_std_dev": flux_std_scale,
                "clipped_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (handoff / "mg_macro_summary.json").write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.openmc-ce-mg-sph-mg-macro.v1",
                "scatter_format": "histogram",
                "histogram_bins": 16,
                "legendre_order": None,
            }
        ),
        encoding="utf-8",
    )
    (handoff / "sph_augment_summary.json").write_text(
        json.dumps(
            {
                "decision": "openmc2donjon_sph_augment_passed",
                "sph_applied": False,
            }
        ),
        encoding="utf-8",
    )
    (handoff / "out_with_openmc_sph.mcompo.txt").write_text("NSPH\n", encoding="utf-8")
    (handoff / "out_with_openmc_sph.macrolib.txt").write_text("NSPH\n", encoding="utf-8")


def _write_iteration_summary(
    handoff: Path,
    iteration: int,
    *,
    sph_min: float,
    sph_max: float,
    previous_sph: str | None = None,
) -> None:
    (handoff / f"openmc_sph_summary_iter{iteration:02d}.json").write_text(
        json.dumps(
            {
                "decision": "openmc2donjon_openmc_sph_sidecar_passed",
                "sph_min": sph_min,
                "sph_max": sph_max,
                "raw_update_minimum": 0.8,
                "raw_update_maximum": 1.4,
                "damping": 0.5,
                "reference_flux_max_relative_std_dev": 0.02,
                "mg_flux_max_relative_std_dev": 0.03,
                "clipped_count": 0,
                "normalization_factor": 1.0,
                "previous_sph": previous_sph,
                "mg_flux": str(handoff / f"openmc_mg_flux_iter{iteration:02d}.h5::openmc_mg_flux"),
                "output_h5": str(handoff / f"openmc_sph_sidecar_iter{iteration:02d}.h5"),
                "output_table": str(handoff / f"openmc_sph_iter{iteration:02d}.csv"),
            }
        ),
        encoding="utf-8",
    )


def _write_flux_h5(
    path: Path,
    dataset_name: str,
    values: np.ndarray,
    *,
    flux_std_scale: float,
) -> None:
    with h5py.File(path, "w") as h5:
        h5.create_dataset(dataset_name, data=values)
        h5.create_dataset(f"{dataset_name}_std_dev", data=values * flux_std_scale)


def _write_sweep_physics_summary(
    path: Path,
    *,
    damping: float,
    current_residual: float,
    after_residual: float,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
                "quality": {
                    "decision": "openmc_ce_mg_sph_demonstration_quality",
                    "max_flux_relative_std_dev": 0.08,
                    "production_ready": False,
                },
                "sph": {
                    "minimum": 0.8,
                    "maximum": 1.2,
                },
                "sph_iterations": [
                    {
                        "iteration": 1,
                        "damping": damping,
                        "raw_update_minimum": 0.7,
                        "raw_update_maximum": 1.3,
                    }
                ],
                "reaction_rate_preservation": {
                    "current_solve": {
                        "max_relative_residual": current_residual,
                        "mean_relative_residual": current_residual / 2.0,
                        "valid_bins": 4,
                        "worst": {
                            "reaction": "absorption",
                            "mixture": "CS_ABS",
                            "group": 1,
                            "relative_residual": current_residual,
                        },
                    },
                    "after_sph_update_frozen_flux": {
                        "max_relative_residual": after_residual,
                        "mean_relative_residual": after_residual / 2.0,
                        "valid_bins": 4,
                        "worst": {
                            "reaction": "absorption",
                            "mixture": "CS_ABS",
                            "group": 1,
                            "relative_residual": after_residual,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()

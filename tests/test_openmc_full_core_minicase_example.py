from __future__ import annotations

from pathlib import Path
import unittest


class OpenMCFullCoreMinicaseExampleTests(unittest.TestCase):
    def test_example_python_files_are_parseable(self) -> None:
        for name in (
            "build_model.py",
            "export_recipe.py",
            "fake_full_core_low_order_solver.py",
            "full_core_model.py",
            "make_sph_loop_fixture.py",
        ):
            path = _example_dir() / name
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_model_declares_full_core_domain_map(self) -> None:
        text = (_example_dir() / "full_core_model.py").read_text(encoding="utf-8")

        self.assertIn('DOMAIN_MODE = "full_core_assembly"', text)
        self.assertIn("CORE_SHAPE = (3, 3)", text)
        self.assertIn("AXIAL_LAYERS = 1", text)
        self.assertIn("ASM_Y{y_index:02d}_X{x_index:02d}", text)
        self.assertIn("DOMAIN_VOLUME_BY_ID", text)
        self.assertIn("VOLUME_FLUX_TALLY_NAME", text)
        self.assertIn("energy_filter_order[:, ::-1]", text)
        self.assertIn('"group_order"] = "mgxs_donjon"', text)
        self.assertIn('"spatial_mapping"', text)

    def test_recipe_preserves_one_domain_per_assembly_position(self) -> None:
        text = (_example_dir() / "export_recipe.py").read_text(encoding="utf-8")

        self.assertIn("from openmc2donjon import DomainExportSpec", text)
        self.assertIn("def domain_specs(library):", text)
        self.assertIn("volume=float(_full_core.DOMAIN_VOLUME_BY_ID[int(domain.id)])", text)
        self.assertIn('"source_domain_id"', text)
        self.assertIn('"assembly_x"', text)
        self.assertIn('"assembly_y"', text)
        self.assertIn('"axial_layer"', text)
        self.assertIn("append_volume_flux_hdf5", text)

    def test_readme_states_full_core_mapping(self) -> None:
        text = (_example_dir() / "README.md").read_text(encoding="utf-8")

        self.assertIn("OpenMC builds one 3D core", text)
        self.assertIn("ASM_Y01_X01", text)
        self.assertIn("ASM_Y03_X03", text)
        self.assertIn("one MGXS domain per assembly position", text)
        self.assertIn("openmc2donjon-from-openmc --production", text)

    def test_smoke_script_uses_production_entrypoint(self) -> None:
        text = (_example_dir() / "run_smoke.sh").read_text(encoding="utf-8")

        self.assertIn("Strict production dry-run", text)
        self.assertIn("--production", text)
        self.assertIn("OPENMC2DONJON_FULL_CORE_MINICASE_DIR", text)
        self.assertIn("OPENMC2DONJON-FULL-CORE-MINICASE-2G", text)
        self.assertIn("full-core assembly-wise readback OK", text)
        self.assertIn("openmc_volume_flux is not tagged as MGXS/DONJON group order", text)
        self.assertIn("Full-core SPH loop handoff", text)
        self.assertIn("make_sph_loop_fixture.py", text)
        self.assertIn("run-sph-loop", text)
        self.assertIn("validate-bundle", text)
        self.assertIn("full-core SPH loop readback OK", text)
        self.assertIn("Real DONJON low-order solve smoke", text)
        self.assertIn("openmc2donjon.donjon_deck_runner", text)
        self.assertIn('--runner "$DONJON_RUNNER"', text)
        self.assertIn("extract-donjon-volume-flux", text)
        self.assertIn("real DONJON full-core solve OK", text)
        self.assertIn("Real DONJON-backed SPH loop smoke", text)
        self.assertIn("make-donjon-sph-loop-config", text)
        self.assertIn("full-core-real-donjon-sph-loop", text)
        self.assertIn("--flux-normalization auto", text)
        self.assertIn("--acceptance-min-completed-iterations 2", text)
        self.assertIn("--acceptance-require-final-solve", text)
        self.assertIn("power-normalized real DONJON SPH loop should not clip", text)
        self.assertIn("auto normalization did not resolve to power", text)
        self.assertIn("normalization factor is not positive", text)
        self.assertIn("normalization={summary['workflows'][0]['flux_normalization']}", text)
        self.assertIn("real DONJON full-core SPH loop mechanical smoke OK", text)
        self.assertIn(
            "DONJON runner unavailable; skipping real full-core low-order solve smoke",
            text,
        )
        self.assertIn("h_factor_datasets", text)
        self.assertIn("transport_total_datasets", text)
        self.assertIn("volume_attributes", text)

    def test_sph_fixture_writes_one_flux_unknown_per_assembly(self) -> None:
        text = (_example_dir() / "make_sph_loop_fixture.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("np.arange(1, len(mixture_names) + 1", text)
        self.assertIn('"reference_flux": f"{mgxs.resolve()}::openmc_volume_flux"', text)
        self.assertIn('"map_h5": str(flux_map.resolve())', text)
        self.assertIn('"iterations": 2', text)
        self.assertIn('"require_converged": True', text)

    def test_full_core_solver_uses_previous_sph_to_close_the_loop(self) -> None:
        text = (_example_dir() / "fake_full_core_low_order_solver.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("0.5 * reference", text)
        self.assertIn("previous_sph", text)
        self.assertIn("openmc_volume_flux", text)
        self.assertIn('"L_FLUX"', text)

    def test_real_donjon_template_matches_nine_assembly_order(self) -> None:
        template = (
            _example_dir() / "templates" / "solve_lflux_dump.x2m.in"
        ).read_text(encoding="utf-8")

        self.assertIn("CAR2D 3 3", template)
        self.assertIn("1 2 3", template)
        self.assertIn("4 5 6", template)
        self.assertIn("7 8 9", template)
        self.assertIn("TRIVAT:", template)
        self.assertIn("TRIVAA:", template)
        self.assertIn("FLUD:", template)
        self.assertIn("UTL: FLUX :: IMPR STATE-VECTOR * DUMP ;", template)
        self.assertIn("FULL CORE MINICASE REAL DONJON", template)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _example_dir() -> Path:
    return _repo_root() / "examples/openmc_full_core_minicase"


if __name__ == "__main__":
    unittest.main()

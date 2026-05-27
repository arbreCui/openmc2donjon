from __future__ import annotations

from pathlib import Path
import unittest


class ReleaseCheckScriptTests(unittest.TestCase):
    def test_default_release_check_runs_openmc_hex_minicase(self) -> None:
        text = _release_check().read_text(encoding="utf-8")

        default_section, remainder = text.split(
            'if [[ "$RUN_LOCAL_CANDIDATES" -eq 1 ]]; then',
            maxsplit=1,
        )
        candidate_section, accepted_section = remainder.split(
            'echo "== Accepted baseline manifest =="',
            maxsplit=1,
        )
        self.assertIn("== OpenMC hex minicase smoke ==", default_section)
        self.assertIn("examples/openmc_hex_minicase/run_smoke.sh", default_section)
        self.assertIn(
            "== OpenMC full-core assembly-wise minicase smoke ==",
            default_section,
        )
        self.assertIn(
            "scripts/run_openmc_full_core_production_smoke.sh",
            default_section,
        )
        self.assertIn('RUN_REAL_DONJON="$RUN_DONJON"', default_section)
        self.assertIn("== External face-flux adapter smoke ==", default_section)
        self.assertIn("examples/external_face_flux_adapter/run_smoke.sh", default_section)
        self.assertIn("== DRAGON SPH macrolib handoff smoke ==", default_section)
        self.assertIn("scripts/run_dragon_sph_handoff_smoke.sh", default_section)
        self.assertIn("== DONJON SPH consume smoke ==", default_section)
        self.assertIn("scripts/run_donjon_sph_consume_smoke.sh", default_section)
        self.assertIn("== DONJON SPH solver response smoke ==", default_section)
        self.assertIn("scripts/run_donjon_sph_solver_response_smoke.sh", default_section)
        self.assertIn("make-sph-update-table --help", default_section)
        self.assertIn("openmc2donjon.donjon_deck_runner --help", default_section)
        self.assertNotIn("extract-donjon-volume-flux --help", default_section)
        self.assertNotIn("run-sph-iteration --help", default_section)
        self.assertNotIn("run-sph-loop --help", default_section)
        self.assertNotIn("make-donjon-sph-loop-config --help", default_section)
        self.assertNotIn("make-sph-loop-scaffold --help", default_section)
        self.assertNotIn("prepare-openmc-sph-loop --help", default_section)
        self.assertNotIn("== OpenMC-to-SPH-loop entrypoint smoke ==", default_section)
        self.assertNotIn("examples/openmc_sph_loop_entrypoint/run_smoke.sh", default_section)
        self.assertIn('RUN_REAL_DONJON="$RUN_DONJON"', default_section)
        self.assertNotIn("== SPH iteration loop smoke ==", default_section)
        self.assertNotIn("examples/sph_iteration_loop/run_smoke.sh", default_section)
        self.assertNotIn("== Generic DONJON SPH loop adapter smoke ==", default_section)
        self.assertNotIn("examples/donjon_sph_loop_adapter/run_smoke.sh", default_section)
        self.assertNotIn("== Minimal SPH loop user-case smoke ==", default_section)
        self.assertNotIn("examples/sph_loop_minicase/run_smoke.sh", default_section)
        self.assertIn("== External SPH handoff smoke ==", default_section)
        self.assertIn("examples/external_sph_handoff/run_smoke.sh", default_section)
        self.assertIn("== Energy mesh contract smoke ==", default_section)
        self.assertIn("scripts/run_energy_mesh_contract_smoke.sh", default_section)
        self.assertIn("pygan-doctor --help", default_section)
        self.assertIn("pygan-inspect-compo --help", default_section)
        self.assertIn("compare-writers --help", default_section)
        self.assertIn("== PyGan backend smoke ==", default_section)
        self.assertIn("scripts/run_pygan_backend_smoke.sh", default_section)
        self.assertIn("== C5G7 ADF source reconstruction smoke ==", accepted_section)
        self.assertIn("scripts/run_c5g7_adf_source_smoke.sh", accepted_section)
        self.assertIn("== C5G7 DONJON face-flux regeneration smoke ==", accepted_section)
        self.assertIn("scripts/run_c5g7_donjon_face_flux_smoke.sh", accepted_section)
        self.assertIn("== C5G7 from-OpenMC flux-ratio ADF smoke ==", accepted_section)
        self.assertIn("scripts/run_c5g7_from_openmc_adf_smoke.sh", accepted_section)
        self.assertIn("== C5G7 SPH solver response smoke ==", accepted_section)
        self.assertIn("scripts/run_c5g7_sph_solver_response_smoke.sh", accepted_section)
        self.assertNotIn("== C5G7 SPH iteration from DONJON flux smoke ==", accepted_section)
        self.assertNotIn(
            "scripts/run_c5g7_sph_iteration_from_donjon_flux_smoke.sh",
            accepted_section,
        )
        self.assertNotIn("== C5G7 fixed-OpenMC SPH loop smoke ==", accepted_section)
        self.assertNotIn("scripts/run_c5g7_fixed_openmc_sph_loop_smoke.sh", accepted_section)
        self.assertIn("== OpenMC hex DONJON k-eff comparison ==", accepted_section)
        self.assertIn("examples/openmc_hex_minicase/run_keff_comparison.sh", accepted_section)
        self.assertNotIn("examples/openmc_hex_minicase/run_smoke.sh", candidate_section)

    def test_c5g7_sph_solver_response_uses_external_table_entrypoint(self) -> None:
        text = (_repo_root() / "scripts/run_c5g7_sph_solver_response_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("c5g7_external_sph_table.csv", text)
        self.assertIn("--mode table", text)
        self.assertIn("--table \"$SPH_TABLE\"", text)
        self.assertIn("source_table", text)

    def test_c5g7_sph_iteration_smoke_uses_real_flux_datasets(self) -> None:
        text = (
            _repo_root() / "scripts/run_c5g7_sph_iteration_from_donjon_flux_smoke.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("openmc_volume_flux", text)
        self.assertIn("donjon_volume_flux", text)
        self.assertIn("make-sph-update-table", text)
        self.assertIn("--mode table", text)
        self.assertIn("c5g7-donjon-flux-iteration-smoke", text)
        self.assertIn("DSPH:", text)
        self.assertIn("TRIVAA:", text)
        self.assertIn("openmc2donjon_c5g7_sph_iteration_solver_response_passed", text)

    def test_c5g7_fixed_openmc_sph_loop_keeps_base_xs_fixed(self) -> None:
        text = (_repo_root() / "scripts/run_c5g7_fixed_openmc_sph_loop_smoke.sh").read_text(
            encoding="utf-8"
        )
        config_writer = (
            _repo_root() / "examples/donjon_openmc2donjon/c5g7_sph_loop/make_config.py"
        ).read_text(encoding="utf-8")

        self.assertIn("fixed OpenMC base XS", text)
        self.assertIn("run-sph-loop", text)
        self.assertIn("c5g7_sph_loop/make_config.py", text)
        self.assertIn("openmc2donjon.donjon_deck_runner", config_writer)
        self.assertIn("final_to_initial_flux_residual_ratio", text)
        self.assertIn("max_final_clipped_count", config_writer)
        self.assertIn("solve_lflux_dump.x2m.in", text)
        self.assertIn('"final_solve": True', config_writer)
        self.assertIn('"postprocess"', config_writer)
        self.assertIn("openmc2donjon_sph_loop_passed", text)
        self.assertIn("ITER1_SIDECAR", text)
        self.assertIn("extract-donjon-volume-flux", text)
        self.assertIn("mesh_donjon_volume_flux", text)
        self.assertIn("openmc2donjon_c5g7_fixed_openmc_sph_loop_passed", text)

    def test_openmc_full_core_release_gate_calls_production_smoke(self) -> None:
        text = (
            _repo_root() / "scripts/run_openmc_full_core_production_smoke.sh"
        ).read_text(encoding="utf-8")
        example = (
            _repo_root() / "examples/openmc_full_core_minicase/run_smoke.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("examples/openmc_full_core_minicase/run_smoke.sh", text)
        self.assertIn('RUN_REAL_DONJON="${RUN_REAL_DONJON:-0}"', text)
        self.assertIn("--require-openmc-volume-flux", example)
        self.assertIn("require_production_audit", example)
        self.assertIn("production_audit", example)

    def test_legacy_minicase_keeps_reference_flux_uncertainty_contract(self) -> None:
        release_text = _release_check().read_text(encoding="utf-8")
        default_section = release_text.split(
            'if [[ "$RUN_LOCAL_CANDIDATES" -eq 1 ]]; then',
            maxsplit=1,
        )[0]
        smoke_text = (
            _repo_root() / "examples/sph_loop_minicase/run_smoke.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn("== Minimal SPH loop user-case smoke ==", default_section)
        self.assertNotIn("examples/sph_loop_minicase/run_smoke.sh", default_section)
        self.assertIn(
            'config["acceptance"]["require_reference_flux_std_dev"] is True',
            smoke_text,
        )
        self.assertIn(
            'config["acceptance"]["max_reference_flux_std_dev_rel"] == 1.0e-2',
            smoke_text,
        )
        self.assertIn(
            'checks["require_reference_flux_std_dev"]["passed"] is True',
            smoke_text,
        )
        self.assertIn(
            'checks["max_reference_flux_std_dev_rel"]["passed"] is True',
            smoke_text,
        )
        self.assertIn(
            'metadata["reference_flux"]["std_dev_dataset"] == "openmc_volume_flux_std_dev"',
            smoke_text,
        )
        self.assertIn(
            'metadata["reference_flux"]["std_dev_max_rel"] - 1.0e-3',
            smoke_text,
        )

    def test_release_gate_covers_energy_mesh_contract(self) -> None:
        release_text = _release_check().read_text(encoding="utf-8")
        default_section = release_text.split(
            'if [[ "$RUN_LOCAL_CANDIDATES" -eq 1 ]];',
            maxsplit=1,
        )[0]
        smoke_text = (
            _repo_root() / "scripts/run_energy_mesh_contract_smoke.sh"
        ).read_text(encoding="utf-8")
        scripts_readme = (_repo_root() / "scripts/README.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("== Energy mesh contract smoke ==", default_section)
        self.assertIn("scripts/run_energy_mesh_contract_smoke.sh", default_section)
        self.assertIn('load_energy_mesh("casmo_7")', smoke_text)
        self.assertIn("--warn-unknown-energy-mesh", smoke_text)
        self.assertIn("--require-known-energy-mesh", smoke_text)
        self.assertIn('record["energy_mesh_id"] == "casmo_7"', smoke_text)
        self.assertIn(
            '"does not match a bundled known energy mesh" in item',
            smoke_text,
        )
        self.assertIn("run_energy_mesh_contract_smoke.sh", scripts_readme)

    def test_release_gate_covers_optional_pygan_backend_smoke(self) -> None:
        release_text = _release_check().read_text(encoding="utf-8")
        default_section = release_text.split(
            'if [[ "$RUN_LOCAL_CANDIDATES" -eq 1 ]];',
            maxsplit=1,
        )[0]
        smoke_text = (
            _repo_root() / "scripts/run_pygan_backend_smoke.sh"
        ).read_text(encoding="utf-8")
        scripts_readme = (_repo_root() / "scripts/README.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("== PyGan backend smoke ==", default_section)
        self.assertIn("scripts/run_pygan_backend_smoke.sh", default_section)
        self.assertIn("pygan-doctor --help", default_section)
        self.assertIn("pygan-inspect-compo --help", default_section)
        self.assertIn("compare-writers --help", default_section)
        self.assertIn("pygan-doctor --summary-json", smoke_text)
        self.assertIn("compare-writers", smoke_text)
        self.assertIn("--format multicompo", smoke_text)
        self.assertIn("--format macrolib", smoke_text)
        self.assertIn("pygan-inspect-compo", smoke_text)
        self.assertIn("DONJON ingest of PyGan ASCII outputs", smoke_text)
        self.assertIn("MODULE NCR: END: ABORT: ;", smoke_text)
        self.assertIn("SEQ_ASCII CPO_ASC", smoke_text)
        self.assertIn("SEQ_ASCII MACRO_ASC", smoke_text)
        self.assertIn("SEQ_ASCII NCR_ASC", smoke_text)
        self.assertIn("MACRO_NCR := NCR: CPO", smoke_text)
        self.assertIn("NCR_ASC := MACRO_NCR", smoke_text)
        self.assertIn("OPENMC2DONJON PYGAN DONJON INGEST OK", smoke_text)
        self.assertIn("DONJON NCR extracted MACROLIB matches PyGan direct MACROLIB", smoke_text)
        self.assertIn("DONJON runner unavailable", smoke_text)
        self.assertIn("PyGan backend smoke skipped", smoke_text)
        self.assertIn("openmc2donjon PyGan backend smoke: PASS", smoke_text)
        self.assertIn("run_pygan_backend_smoke.sh", scripts_readme)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _release_check() -> Path:
    return _repo_root() / "scripts/release_check.sh"


if __name__ == "__main__":
    unittest.main()

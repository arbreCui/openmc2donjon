"""Write the C5G7 fixed-OpenMC SPH loop JSON config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    repo_root = _repo_root()
    example_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="config JSON to write")
    parser.add_argument("--output-dir", type=Path, required=True, help="SPH loop run directory")
    parser.add_argument("--mgxs", type=Path, required=True, help="fixed OpenMC MGXS HDF5")
    parser.add_argument(
        "--reference-flux",
        type=Path,
        required=True,
        help="HDF5 containing openmc_volume_flux and DONJON scalar map metadata",
    )
    parser.add_argument(
        "--donjon-root",
        type=Path,
        default=Path("/Users/wen/dragon-5.1/Donjon"),
        help="DONJON installation root containing rdonjon",
    )
    parser.add_argument(
        "--driver",
        type=Path,
        default=None,
        help="optional DONJON deck runner script; default uses the packaged module",
    )
    parser.add_argument(
        "--solve-template",
        type=Path,
        default=example_dir / "templates/solve_lflux_dump.x2m.in",
        help="C5G7 DONJON solve deck template",
    )
    parser.add_argument(
        "--apply-template",
        type=Path,
        default=repo_root / "examples/donjon_sph_loop_adapter/templates/apply_nsph_mac.x2m.in",
        help="DONJON DSPH/MAC apply deck template",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used by solver/postprocess commands",
    )
    parser.add_argument("--damping", type=float, default=0.1)
    parser.add_argument("--clip-min", type=float, default=0.5)
    parser.add_argument("--clip-max", type=float, default=2.0)
    parser.add_argument("--run-tag", default="c5g7_fixed_openmc_sph_loop")
    parser.add_argument(
        "--stage-prefix",
        default="odj_c5g7_sph",
        help="short /tmp staging prefix used to avoid DONJON 120-column path limits",
    )
    parser.add_argument(
        "--case-dir",
        default="openmc2donjon/case_runs/c5g7_fixed_openmc_sph_loop",
        help="DONJON data-relative directory where rendered decks are written",
    )
    args = parser.parse_args(argv)
    driver_prefix = (
        [args.python_bin, str(args.driver)]
        if args.driver is not None
        else [args.python_bin, "-m", "openmc2donjon.donjon_deck_runner"]
    )

    payload = {
        "schema": "openmc2donjon.sph-loop-config.v1",
        "input_h5": str(args.mgxs),
        "output_dir": str(args.output_dir),
        "reference_flux": f"{args.reference_flux}::openmc_volume_flux",
        "iterations": 2,
        "final_solve": True,
        "format": "macrolib",
        "damping": args.damping,
        "clip_min": args.clip_min,
        "clip_max": args.clip_max,
        "map_h5": str(args.reference_flux),
        "sph_kind": "c5g7-fixed-openmc-loop",
        "sph_real": False,
        "sph_applied": False,
        "source_label": "C5G7 fixed OpenMC XS SPH loop",
        "acceptance": {
            "min_completed_iterations": 2,
            "require_final_solve": True,
            "max_sph_rel_change": 0.15,
            "max_flux_ratio_residual": 2.2,
            "max_final_to_initial_flux_residual_ratio": 1.25,
            "max_final_clipped_fraction": 0.0,
            "max_final_clipped_count": 0,
            "sph_minimum_floor": args.clip_min,
            "sph_maximum_ceiling": args.clip_max,
            "max_keff_step_pcm": 5.0,
            "max_final_keff_delta_pcm": 5.0,
            "fail_on_violation": True,
        },
        "solver": {
            "command": [
                *driver_prefix,
                "solve",
                "--donjon-root",
                str(args.donjon_root),
                "--deck-template",
                str(args.solve_template),
                "--macrolib",
                "{ascii_input}",
                "--result",
                "{result}",
                "--iteration",
                "{iteration}",
                "--case-id",
                f"{args.run_tag}_iter{{iteration}}_solve",
                "--case-dir",
                args.case_dir,
                "--work-dir",
                f"/tmp/{args.stage_prefix}_solve_iter{{iteration}}",
            ],
            "result": "donjon_flux.result",
        },
        "postprocess": {
            "command": [
                *driver_prefix,
                "apply",
                "--donjon-root",
                str(args.donjon_root),
                "--deck-template",
                str(args.apply_template),
                "--macrolib",
                "{workflow_ascii}",
                "--output",
                "{output}",
                "--iteration",
                "{iteration1}",
                "--case-id",
                f"{args.run_tag}_iter{{iteration1}}_apply",
                "--case-dir",
                args.case_dir,
                "--work-dir",
                f"/tmp/{args.stage_prefix}_apply_iter{{iteration1}}",
            ],
            "output": "corrected_pn.macrolib.txt",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


if __name__ == "__main__":
    raise SystemExit(main())

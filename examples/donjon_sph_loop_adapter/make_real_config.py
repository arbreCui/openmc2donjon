"""Write a ``run-sph-loop`` config that calls a real DONJON deck runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mgxs", type=Path, required=True)
    parser.add_argument("--reference-flux", type=Path, required=True)
    parser.add_argument("--flux-map", type=Path, required=True)
    parser.add_argument(
        "--donjon-root",
        type=Path,
        default=Path("/Users/wen/dragon-5.1/Donjon"),
    )
    parser.add_argument(
        "--driver",
        type=Path,
        default=Path(__file__).with_name("donjon_deck_runner.py"),
    )
    parser.add_argument(
        "--solve-template",
        type=Path,
        default=Path(__file__).with_name("templates") / "solve_lflux_dump.x2m.in",
    )
    parser.add_argument(
        "--apply-template",
        type=Path,
        default=Path(__file__).with_name("templates") / "apply_nsph_mac.x2m.in",
    )
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--clip-min", type=float, default=0.5)
    parser.add_argument("--clip-max", type=float, default=3.0)
    parser.add_argument("--case-id-prefix", default="openmc2donjon_sph_loop")
    parser.add_argument(
        "--stage-prefix",
        default="odj_sph_loop",
        help="short /tmp staging prefix used to avoid DONJON 120-column path limits",
    )
    args = parser.parse_args(argv)

    config = {
        "schema": "openmc2donjon.sph-loop-config.v1",
        "input_h5": str(args.mgxs),
        "output_dir": str(args.output_dir),
        "reference_flux": f"{args.reference_flux}::openmc_volume_flux",
        "map_h5": str(args.flux_map),
        "iterations": args.iterations,
        "format": "macrolib",
        "final_solve": True,
        "damping": args.damping,
        "clip_min": args.clip_min,
        "clip_max": args.clip_max,
        "sph_kind": "donjon-sph-loop-real-adapter",
        "sph_real": False,
        "sph_applied": False,
        "source_label": "Generic DONJON SPH loop real deck adapter",
        "solver": {
            "command": [
                args.python_bin,
                str(args.driver),
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
                f"{args.case_id_prefix}_solve_iter{{iteration}}",
                "--work-dir",
                f"/tmp/{args.stage_prefix}_solve_iter{{iteration}}",
            ],
            "result": "donjon_flux.result",
        },
        "postprocess": {
            "command": [
                args.python_bin,
                str(args.driver),
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
                f"{args.case_id_prefix}_apply_iter{{iteration1}}",
                "--work-dir",
                f"/tmp/{args.stage_prefix}_apply_iter{{iteration1}}",
            ],
            "output": "corrected.macrolib.txt",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"DONJON real deck SPH loop config: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

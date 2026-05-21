"""Write the C5G7 fixed-OpenMC SPH loop JSON config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
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
        "--helper",
        type=Path,
        default=None,
        help="DONJON solve/apply helper script; default resolves from the repo root",
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
    args = parser.parse_args(argv)

    helper = args.helper if args.helper is not None else _repo_root() / "scripts" / (
        "c5g7_fixed_openmc_sph_loop_donjon.py"
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
        "solver": {
            "command": [
                args.python_bin,
                str(helper),
                "solve",
                "--donjon-root",
                str(args.donjon_root),
                "--macrolib",
                "{ascii_input}",
                "--result",
                "{result}",
                "--iteration",
                "{iteration}",
                "--run-tag",
                args.run_tag,
            ],
            "result": "donjon_flux.result",
        },
        "postprocess": {
            "command": [
                args.python_bin,
                str(helper),
                "apply",
                "--donjon-root",
                str(args.donjon_root),
                "--raw-macrolib",
                "{workflow_ascii}",
                "--output",
                "{output}",
                "--iteration",
                "{iteration1}",
                "--run-tag",
                args.run_tag,
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

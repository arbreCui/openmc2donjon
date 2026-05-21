"""Write a reusable ``run-sph-loop`` config for the DONJON adapter example."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a generic DONJON SPH loop adapter config."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mgxs", type=Path, required=True)
    parser.add_argument("--reference-flux", type=Path, required=True)
    parser.add_argument("--flux-map", type=Path, required=True)
    parser.add_argument(
        "--driver",
        type=Path,
        default=Path(__file__).with_name("fake_donjon_driver.py"),
    )
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--damping", type=float, default=0.5)
    args = parser.parse_args(argv)

    config = {
        "schema": "openmc2donjon.sph-loop-config.v1",
        "input_h5": str(args.mgxs),
        "output_dir": str(args.output_dir),
        "reference_flux": f"{args.reference_flux}::openmc_volume_flux",
        "map_h5": str(args.flux_map),
        "iterations": 2,
        "format": "macrolib",
        "final_solve": True,
        "damping": args.damping,
        "clip_min": 0.5,
        "clip_max": 3.0,
        "sph_kind": "donjon-sph-loop-adapter-smoke",
        "sph_real": False,
        "sph_applied": False,
        "source_label": "Generic DONJON SPH loop adapter",
        "solver": {
            "command": [
                args.python_bin,
                str(args.driver),
                "solve",
                "--macrolib",
                "{ascii_input}",
                "--result",
                "{result}",
                "--iteration",
                "{iteration}",
            ],
            "result": "donjon_flux.result",
        },
        "postprocess": {
            "command": [
                args.python_bin,
                str(args.driver),
                "apply",
                "--input",
                "{workflow_ascii}",
                "--output",
                "{output}",
                "--sph",
                "{sph_sidecar}",
                "--iteration",
                "{iteration1}",
            ],
            "output": "corrected.macrolib.txt",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"DONJON SPH loop adapter config: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

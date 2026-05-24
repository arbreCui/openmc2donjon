"""Write a run-sph-loop config that uses the packaged DONJON deck runner."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from openmc2donjon.donjon_sph_config import write_donjon_sph_loop_config


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
        "--solve-template",
        type=Path,
        default=Path(__file__).with_name("templates") / "solve_lflux_dump.x2m.in",
    )
    parser.add_argument(
        "--apply-template",
        type=Path,
        default=None,
        help="default: packaged openmc2donjon DSPH/MAC apply template",
    )
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--clip-min", type=float, default=0.5)
    parser.add_argument("--clip-max", type=float, default=3.0)
    parser.add_argument("--case-id-prefix", default="sph_loop_minicase")
    parser.add_argument("--stage-prefix", default="odj_sph_loop_minicase")
    parser.add_argument(
        "--case-dir",
        default="openmc2donjon/case_runs/sph_loop_minicase",
        help="DONJON data-relative directory for rendered decks",
    )
    args = parser.parse_args(argv)

    write_donjon_sph_loop_config(
        args.output,
        input_h5=args.mgxs,
        output_dir=args.output_dir,
        solve_template=args.solve_template,
        apply_template=args.apply_template,
        flux_map=args.flux_map,
        reference_flux=args.reference_flux,
        donjon_root=args.donjon_root,
        python_bin=args.python_bin,
        iterations=args.iterations,
        damping=args.damping,
        clip_min=args.clip_min,
        clip_max=args.clip_max,
        flux_normalization="none",
        case_id_prefix=args.case_id_prefix,
        stage_prefix=args.stage_prefix,
        case_dir=args.case_dir,
        sph_kind="sph-loop-minicase-donjon",
        source_label="SPH loop minicase DONJON runner",
        acceptance={
            "preset": "production",
            "require_mgxs_std_dev_coverage": True,
            "require_reference_flux_std_dev": True,
            "max_reference_flux_std_dev_rel": 1.0e-2,
        },
    )
    print(f"SPH loop minicase DONJON config: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

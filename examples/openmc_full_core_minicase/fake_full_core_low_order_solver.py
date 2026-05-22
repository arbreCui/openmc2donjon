"""Full-core low-order solver stub for the OpenMC assembly-wise minicase.

The real production slot is DONJON.  This deterministic stand-in keeps the
same narrow contract used by ``run-sph-loop``: read the current ASCII handoff,
write a DONJON-like ``L_FLUX`` dump, then stage the corrected ASCII for the
next solve.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import h5py
import numpy as np

from openmc2donjon import lcm_ascii as lcm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Full-core SPH loop low-order solver stub."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    solve = subparsers.add_parser("solve", help="write a deterministic L_FLUX dump")
    solve.add_argument("--input-h5", type=Path, required=True)
    solve.add_argument("--macrolib", type=Path, required=True)
    solve.add_argument("--result", type=Path, required=True)
    solve.add_argument("--iteration", type=int, required=True)
    solve.add_argument("--previous-sph", type=Path)

    apply = subparsers.add_parser("apply", help="stage the corrected macrolib")
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--sph", type=Path, required=True)
    apply.add_argument("--iteration", type=int, required=True)

    args = parser.parse_args(argv)
    if args.command == "solve":
        return _solve(
            input_h5=args.input_h5,
            macrolib=args.macrolib,
            result=args.result,
            iteration=args.iteration,
            previous_sph=args.previous_sph,
        )
    return _apply(args.input, args.output, args.sph, args.iteration)


def _solve(
    *,
    input_h5: Path,
    macrolib: Path,
    result: Path,
    iteration: int,
    previous_sph: Path | None,
) -> int:
    if not input_h5.exists():
        raise SystemExit(f"missing MGXS input: {input_h5}")
    if not macrolib.exists():
        raise SystemExit(f"missing macrolib input: {macrolib}")
    reference = _read_reference_flux(input_h5)

    # First low-order solve is intentionally biased.  Once the loop has written
    # a previous SPH sidecar, the stand-in reports the OpenMC reference flux.
    has_sph = (
        previous_sph is not None
        and str(previous_sph) not in {"", "."}
        and previous_sph.exists()
    )
    flux = reference if has_sph else 0.5 * reference
    _write_flux_dump(result, flux)
    print(f"full-core minicase solve iteration={iteration}")
    print(f"  input_macrolib={macrolib}")
    print(f"  previous_sph={previous_sph if has_sph else '<none>'}")
    print(f"  l_flux_dump={result}")
    return 0


def _apply(input_path: Path, output: Path, sph: Path, iteration: int) -> int:
    if not input_path.exists():
        raise SystemExit(f"missing workflow macrolib: {input_path}")
    if not sph.exists():
        raise SystemExit(f"missing SPH sidecar: {sph}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_path, output)
    print(f"full-core minicase apply iteration={iteration}")
    print(f"  corrected_macrolib={output}")
    return 0


def _read_reference_flux(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        if "openmc_volume_flux" not in h5:
            raise SystemExit(f"{path}: missing /openmc_volume_flux")
        flux = np.asarray(h5["openmc_volume_flux"][:], dtype=float)
    if flux.ndim != 2:
        raise SystemExit(f"{path}: openmc_volume_flux must be two-dimensional")
    if not np.all(np.isfinite(flux)) or np.any(flux <= 0.0):
        raise SystemExit(f"{path}: openmc_volume_flux must be positive finite")
    return flux


def _write_flux_dump(path: Path, volume_flux: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mixture_count, group_count = volume_flux.shape
    blocks: list[lcm.LcmBlock] = [
        lcm.string_block(1, "SIGNATURE", "L_FLUX", width=12),
        lcm.block(1, "STATE-VECTOR", 1, [mixture_count, group_count]),
        lcm.block(1, "FLUX", 10, count=group_count),
    ]
    for group_index in range(group_count):
        blocks.append(lcm.list_item(2, group_index + 1))
        blocks.append(
            lcm.LcmBlock(
                3,
                0,
                2,
                mixture_count,
                data=tuple(float(value) for value in volume_flux[:, group_index]),
                trailing=f"{group_index + 1:08d}",
            )
        )
    blocks.extend([lcm.control(-2), lcm.control(-1)])
    lcm.write_lcm_ascii(blocks, path)


if __name__ == "__main__":
    raise SystemExit(main())

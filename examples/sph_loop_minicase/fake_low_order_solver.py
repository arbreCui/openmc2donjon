"""Tiny low-order solver stub for the SPH loop minicase.

Production users replace this script with a DONJON runner.  The important
contract is deliberately small: consume the current ASCII macrolib, write a
DONJON-like L_FLUX dump, then optionally copy the SPH-corrected macrolib into
the file that the next low-order solve should consume.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from openmc2donjon import lcm_ascii as lcm


REFERENCE_GROUPS = (
    (1.0, 80.0, 3.0, 120.0),
    (10.0, 800.0, 30.0, 600.0),
)
HALF_REFERENCE_GROUPS = (
    (1.0, 40.0, 3.0, 60.0),
    (10.0, 400.0, 30.0, 300.0),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SPH loop minicase solver stub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    solve = subparsers.add_parser("solve", help="write a deterministic L_FLUX dump")
    solve.add_argument("--macrolib", type=Path, required=True)
    solve.add_argument("--result", type=Path, required=True)
    solve.add_argument("--iteration", type=int, required=True)

    apply = subparsers.add_parser("apply", help="stage the corrected macrolib")
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--sph", type=Path, required=True)
    apply.add_argument("--iteration", type=int, required=True)

    args = parser.parse_args(argv)
    if args.command == "solve":
        return _solve(args.macrolib, args.result, args.iteration)
    return _apply(args.input, args.output, args.sph, args.iteration)


def _solve(macrolib: Path, result: Path, iteration: int) -> int:
    if not macrolib.exists():
        raise SystemExit(f"missing macrolib input: {macrolib}")
    groups = HALF_REFERENCE_GROUPS if iteration == 0 else REFERENCE_GROUPS
    _write_flux_dump(result, groups)
    print(f"minicase solve iteration={iteration}")
    print(f"  input_macrolib={macrolib}")
    print(f"  l_flux_dump={result}")
    return 0


def _apply(input_path: Path, output: Path, sph: Path, iteration: int) -> int:
    if not input_path.exists():
        raise SystemExit(f"missing workflow macrolib: {input_path}")
    if not sph.exists():
        raise SystemExit(f"missing SPH sidecar: {sph}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_path, output)
    print(f"minicase apply iteration={iteration}")
    print(f"  corrected_macrolib={output}")
    return 0


def _write_flux_dump(path: Path, groups: tuple[tuple[float, ...], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[lcm.LcmBlock] = [
        lcm.string_block(1, "SIGNATURE", "L_FLUX", width=12),
        lcm.block(1, "STATE-VECTOR", 1, [len(groups[0]), len(groups)]),
        lcm.block(1, "FLUX", 10, count=len(groups)),
    ]
    for group_index, values in enumerate(groups, start=1):
        blocks.append(lcm.list_item(2, group_index))
        blocks.append(
            lcm.LcmBlock(
                3,
                0,
                2,
                len(values),
                data=tuple(float(value) for value in values),
                trailing=f"{group_index:08d}",
            )
        )
    blocks.extend([lcm.control(-2), lcm.control(-1)])
    lcm.write_lcm_ascii(blocks, path)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate DONJON ADF carry-through against the MGXS HDF5 source."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii
from openmc2donjon.multicompo import MixtureXS, read_mgxs_hdf5


DEFAULT_MGXS = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_assembly_p1_adf_production.h5"
)
DEFAULT_RESULT = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/"
    "c5g7_adf_production_carrythrough.result"
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    max_abs: float
    max_rel: float
    location: tuple[int, ...]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare MACROLIB/ADF values printed by DONJON with the ADF "
            "datasets embedded in an OpenMC MGXS HDF5 file."
        )
    )
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--rtol", type=float, default=2.0e-5)
    parser.add_argument("--atol", type=float, default=2.0e-6)
    args = parser.parse_args()

    mixtures, _ = read_mgxs_hdf5(args.mgxs)
    expected = _expected_adf(mixtures)
    macrolib = read_macrolib_ascii(args.result)

    missing = [name for name in expected if name not in macrolib.adf]
    extra = [name for name in macrolib.adf if name not in expected]
    if missing or extra:
        raise ValueError(
            "ADF name mismatch: "
            f"missing in DONJON={missing or 'none'}, extra in DONJON={extra or 'none'}"
        )

    checks = [
        _check(name, macrolib.adf[name], values, args)
        for name, values in expected.items()
    ]

    print(f"MGXS mixtures: {', '.join(mix.name for mix in mixtures)}")
    print(f"DONJON macrolib: {macrolib.ngroups} groups, {macrolib.nmixtures} mixtures")
    print(f"ADF names: {', '.join(expected)}")
    print(f"tolerance: rtol={args.rtol:.1e}, atol={args.atol:.1e}")
    print()
    for result in checks:
        status = "OK" if result.ok else "FAIL"
        location = ",".join(str(index) for index in result.location)
        print(
            f"{status:4s} {result.name:8s} "
            f"max_abs={result.max_abs:.6e} "
            f"max_rel={result.max_rel:.6e} "
            f"at=({location})"
        )

    return 0 if all(result.ok for result in checks) else 1


def _expected_adf(mixtures: list[MixtureXS]) -> dict[str, np.ndarray]:
    if not mixtures:
        raise ValueError("MGXS file contains no mixtures")
    names = tuple(mixtures[0].adf or {})
    if not names:
        raise ValueError("MGXS file does not contain ADF data")
    for mix in mixtures:
        if tuple(mix.adf or {}) != names:
            raise ValueError(
                f"mixture {mix.name}: ADF names {tuple(mix.adf or {})!r} "
                f"do not match {names!r}"
            )
    return {name: np.stack([mix.adf[name] for mix in mixtures]) for name in names}


def _check(name: str, actual: np.ndarray, expected: np.ndarray, args) -> CheckResult:
    if actual.shape != expected.shape:
        raise ValueError(f"{name}: shape mismatch {actual.shape} != {expected.shape}")
    diff = np.abs(actual - expected)
    if diff.size == 0:
        return CheckResult(name, True, 0.0, 0.0, ())
    location = tuple(int(index) for index in np.unravel_index(np.argmax(diff), diff.shape))
    scale = np.maximum(np.abs(expected), args.atol)
    rel = diff / scale
    return CheckResult(
        name=name,
        ok=bool(np.allclose(actual, expected, rtol=args.rtol, atol=args.atol)),
        max_abs=float(diff.max()),
        max_rel=float(rel.max()),
        location=location,
    )


if __name__ == "__main__":
    raise SystemExit(main())

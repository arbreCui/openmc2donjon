#!/usr/bin/env python3
"""Validate DONJON NCR macrolib output against the OpenMC MGXS HDF5 source."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii
from openmc2donjon.multicompo import _select_mixtures, read_mgxs_hdf5


DEFAULT_MGXS = Path("/Users/wen/openmc-workspace/c5g7_converter_test/mgxs_library.h5")
DEFAULT_RESULT = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/openmc2donjon_ncr_smoke.result"
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
        description="Compare DONJON NCR L_MACROLIB dump with OpenMC MGXS data."
    )
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--rtol", type=float, default=2.0e-5)
    parser.add_argument("--atol", type=float, default=2.0e-6)
    parser.add_argument(
        "--h-factor-default",
        type=float,
        default=None,
        help="constant H-FACTOR fallback to mirror smoke-only converter output",
    )
    parser.add_argument(
        "--mixture",
        action="append",
        default=None,
        help="compare only the named source mixture; repeat to keep several",
    )
    args = parser.parse_args()

    mixtures, energy_bounds = read_mgxs_hdf5(
        args.mgxs,
        h_factor_default=args.h_factor_default,
    )
    mixtures = _select_mixtures(mixtures, args.mixture)
    macrolib = read_macrolib_ascii(args.result)

    expected_total = np.stack([mix.total for mix in mixtures])
    expected_transport_total = np.stack(
        [
            mix.total if mix.transport_total is None else mix.transport_total
            for mix in mixtures
        ]
    )
    expected_nusigf = np.stack([mix.nu_fission for mix in mixtures])
    expected_chi = np.stack([mix.chi for mix in mixtures])
    expected_diff = 1.0 / (3.0 * expected_transport_total)
    expected_h_factor = _expected_optional_h_factor(mixtures)

    checks = [
        _check("ENERGY", macrolib.energy, np.asarray(energy_bounds)[::-1], args),
        _check("NTOT0", macrolib.ntot0, expected_total, args),
        _check("DIFF", macrolib.diff, expected_diff, args),
        _check("NUSIGF", macrolib.nusigf, expected_nusigf, args),
        _check("CHI", macrolib.chi, expected_chi, args),
    ]
    for moment in range(mixtures[0].nmoments):
        expected_sigs = np.stack(
            [mix.scatter_matrix[moment].sum(axis=1) for mix in mixtures]
        )
        expected_scat = np.stack([mix.scatter_matrix[moment] for mix in mixtures])
        checks.extend(
            [
                _check(
                    f"SIGS{moment:02d}",
                    _require_moment(macrolib.sigs, moment, "SIGS"),
                    expected_sigs,
                    args,
                ),
                _check(
                    f"SCAT{moment:02d}",
                    _require_moment(macrolib.scatter, moment, "SCAT"),
                    expected_scat,
                    args,
                ),
            ]
        )
    if expected_h_factor is not None:
        if macrolib.h_factor is None:
            raise ValueError("DONJON macrolib is missing H-FACTOR")
        checks.append(_check("H-FACTOR", macrolib.h_factor, expected_h_factor, args))

    print(f"MGXS mixtures: {', '.join(mix.name for mix in mixtures)}")
    print(f"DONJON macrolib: {macrolib.ngroups} groups, {macrolib.nmixtures} mixtures")
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


def _require_moment(values: dict[int, np.ndarray], moment: int, prefix: str) -> np.ndarray:
    if moment not in values:
        raise ValueError(f"DONJON macrolib is missing {prefix}{moment:02d}")
    return values[moment]


def _expected_optional_h_factor(mixtures) -> np.ndarray | None:
    present = [mix.h_factor is not None for mix in mixtures]
    if not any(present):
        return None
    if not all(present):
        raise ValueError("MGXS H-FACTOR data must be present for all mixtures or none")
    return np.stack([mix.h_factor for mix in mixtures])


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

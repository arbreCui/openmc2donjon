#!/usr/bin/env python3
"""Summarize the locked C5G7 assembly-wise DONJON validation target.

The target has two parts:

1. DONJON assembly-wise k-eff from OpenMC homogenized MGXS.
2. Production ADF data, not just converter carry-through or bounded diagnostics.

By default this script reports the current status and exits successfully if the
available files can be read. Use ``--strict`` to make it fail until both target
parts are satisfied.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii
from openmc2donjon.multicompo import MixtureXS, read_mgxs_hdf5


DEFAULT_KEFF_RESULT = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/c5g7ap1_target.result"
)
DEFAULT_ADF_MGXS = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_assembly_p1_adf_production.h5"
)
DEFAULT_ADF_RESULT = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/"
    "c5g7_adf_production_carrythrough.result"
)
DEFAULT_ADF_CANDIDATE = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_adf_candidate_mu_donjon.h5"
)
DEFAULT_OPENMC_KEFF = 1.18798


@dataclass
class Check:
    name: str
    status: str
    detail: str
    values: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def main() -> int:
    args = _parse_args()
    checks = [
        _check_keff(args.keff_result, args.reference_keff, args.keff_tolerance_pcm),
        _check_adf_payload(
            args.adf_mgxs,
            args.adf_result,
            rtol=args.adf_rtol,
            atol=args.adf_atol,
        ),
        _check_real_adf(args.adf_mgxs),
        _check_adf_candidate(args.adf_candidate),
    ]
    target_ready = _target_ready(checks)

    if args.json:
        print(
            json.dumps(
                {
                    "target_ready": target_ready,
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _print_report(checks, target_ready)

    if args.strict and not target_ready:
        return 1
    return 0 if all(check.status != "FAIL" for check in checks) else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keff-result", type=Path, default=DEFAULT_KEFF_RESULT)
    parser.add_argument("--reference-keff", type=float, default=DEFAULT_OPENMC_KEFF)
    parser.add_argument("--keff-tolerance-pcm", type=float, default=200.0)
    parser.add_argument("--adf-mgxs", type=Path, default=DEFAULT_ADF_MGXS)
    parser.add_argument("--adf-result", type=Path, default=DEFAULT_ADF_RESULT)
    parser.add_argument("--adf-candidate", type=Path, default=DEFAULT_ADF_CANDIDATE)
    parser.add_argument("--adf-rtol", type=float, default=2.0e-5)
    parser.add_argument("--adf-atol", type=float, default=2.0e-6)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero until k-eff and production ADF checks both pass",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _check_keff(path: Path, reference: float, tolerance_pcm: float) -> Check:
    try:
        text = path.read_text()
        keff = _parse_keff(text)
    except Exception as exc:
        return Check(
            "donjon_assembly_keff",
            "FAIL",
            f"could not read DONJON k-eff result: {exc}",
            {"path": str(path)},
        )

    delta_pcm = (keff - reference) * 1.0e5
    status = "OK" if abs(delta_pcm) <= tolerance_pcm else "WARN"
    return Check(
        "donjon_assembly_keff",
        status,
        (
            f"k-eff={keff:.10f}, reference={reference:.10f}, "
            f"delta={delta_pcm:+.1f} pcm, tolerance={tolerance_pcm:.1f} pcm"
        ),
        {
            "path": str(path),
            "keff": keff,
            "reference_keff": reference,
            "delta_pcm": delta_pcm,
            "tolerance_pcm": tolerance_pcm,
        },
    )


def _parse_keff(text: str) -> float:
    patterns = (
        r"EFFECTIVE MULTIPLICATION FACTOR\s*=\s*([0-9.+\-Ee]+)",
        r"C5G7 ASSEMBLY K-EFFECTIVE\s+([0-9.+\-Ee]+)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return float(matches[-1])
    raise ValueError("no effective multiplication factor found")


def _check_adf_payload(path: Path, result: Path, *, rtol: float, atol: float) -> Check:
    try:
        mixtures, _ = read_mgxs_hdf5(path)
        expected = _expected_adf(mixtures)
        macrolib = read_macrolib_ascii(result)
    except Exception as exc:
        return Check(
            "adf_payload_carrythrough",
            "FAIL",
            f"could not read ADF payload inputs: {exc}",
            {"mgxs": str(path), "result": str(result)},
        )

    missing = [name for name in expected if name not in macrolib.adf]
    extra = [name for name in macrolib.adf if name not in expected]
    if missing or extra:
        return Check(
            "adf_payload_carrythrough",
            "FAIL",
            "ADF names differ between MGXS and DONJON macrolib",
            {
                "mgxs": str(path),
                "result": str(result),
                "missing": missing,
                "extra": extra,
            },
        )

    max_abs = 0.0
    max_rel = 0.0
    for name, expected_values in expected.items():
        actual = macrolib.adf[name]
        if actual.shape != expected_values.shape:
            return Check(
                "adf_payload_carrythrough",
                "FAIL",
                f"ADF {name} shape mismatch {actual.shape} != {expected_values.shape}",
                {"mgxs": str(path), "result": str(result), "name": name},
            )
        diff = np.abs(actual - expected_values)
        scale = np.maximum(np.abs(expected_values), atol)
        max_abs = max(max_abs, float(np.max(diff)))
        max_rel = max(max_rel, float(np.max(diff / scale)))

    status = "OK" if max_abs <= atol or max_rel <= rtol else "FAIL"
    return Check(
        "adf_payload_carrythrough",
        status,
        (
            f"{len(expected)} ADF faces preserved through NCR/EDI; "
            f"max_abs={max_abs:.3e}, max_rel={max_rel:.3e}"
        ),
        {
            "mgxs": str(path),
            "result": str(result),
            "adf_names": list(expected),
            "max_abs": max_abs,
            "max_rel": max_rel,
            "rtol": rtol,
            "atol": atol,
        },
    )


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


def _check_real_adf(path: Path) -> Check:
    try:
        with h5py.File(path, "r") as h5:
            attrs = _string_attrs(h5.attrs)
            source = attrs.get("adf_source", "")
            kind = attrs.get("adf_kind", attrs.get("adf_provenance", ""))
            real_flag = attrs.get("adf_real", "").lower() in {"1", "true", "yes"}
    except Exception as exc:
        return Check(
            "production_adf",
            "FAIL",
            f"could not inspect ADF MGXS file: {exc}",
            {"mgxs": str(path)},
        )

    diagnostic_sources = ("build_c5g7_adf_candidate.py", "diagnostic", "bounded")
    is_diagnostic = any(token in source.lower() for token in diagnostic_sources)
    is_production = real_flag or kind.lower() in {
        "production",
        "heterogeneous_surface_flux",
        "heterogeneous_surface_flux_over_homogeneous_nodal_flux",
    }

    status = "OK" if is_production and not is_diagnostic else "WARN"
    detail = (
        "production ADF provenance is present"
        if status == "OK"
        else (
            "ADF payload is not marked as production/real; current file is a "
            "converter smoke or bounded diagnostic"
        )
    )
    return Check(
        "production_adf",
        status,
        detail,
        {
            "mgxs": str(path),
            "adf_source": source,
            "adf_kind": kind,
            "adf_real": real_flag,
        },
    )


def _check_adf_candidate(path: Path) -> Check:
    if not path.exists():
        return Check(
            "adf_candidate_stability",
            "WARN",
            "no ADF candidate diagnostic file found",
            {"path": str(path)},
        )
    try:
        with h5py.File(path, "r") as h5:
            adf = np.asarray(h5["adf_candidate"][:], dtype=float)
            valid = np.asarray(h5["valid_adf_mask"][:], dtype=bool)
            interior = np.asarray(h5["interior_face_mask"][:], dtype=bool)
            surface_source = _attr_text(h5.attrs.get("surface_flux_source", ""))
            homogeneous_source = _attr_text(h5.attrs.get("homogeneous_face_source", ""))
    except Exception as exc:
        return Check(
            "adf_candidate_stability",
            "WARN",
            f"could not inspect ADF candidate diagnostic: {exc}",
            {"path": str(path)},
        )

    interior_mask = np.broadcast_to(interior[:, :, np.newaxis, :], valid.shape)
    valid_values = adf[valid]
    interior_values = adf[valid & interior_mask]
    invalid = int(valid.size - np.count_nonzero(valid))
    invalid_interior = int(np.count_nonzero((~valid) & interior_mask))
    return Check(
        "adf_candidate_stability",
        "WARN",
        (
            "diagnostic only: "
            f"valid={np.count_nonzero(valid)}/{valid.size}, "
            f"invalid={invalid}, interior_invalid={invalid_interior}, "
            f"interior_median={np.median(interior_values):.5g}, "
            f"interior_max={np.max(interior_values):.5g}, "
            f"surface={surface_source or 'unknown'}, "
            f"homogeneous={homogeneous_source or 'unknown'}"
        ),
        {
            "path": str(path),
            "valid": int(np.count_nonzero(valid)),
            "total": int(valid.size),
            "invalid": invalid,
            "invalid_interior": invalid_interior,
            "valid_min": float(np.min(valid_values)),
            "valid_median": float(np.median(valid_values)),
            "valid_max": float(np.max(valid_values)),
            "interior_min": float(np.min(interior_values)),
            "interior_median": float(np.median(interior_values)),
            "interior_max": float(np.max(interior_values)),
            "surface_flux_source": surface_source,
            "homogeneous_face_source": homogeneous_source,
        },
    )


def _string_attrs(attrs) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in attrs.items():
        if isinstance(value, bytes):
            out[key] = value.decode()
        elif isinstance(value, np.bytes_):
            out[key] = value.decode()
        else:
            out[key] = str(value)
    return out


def _attr_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.bytes_):
        return value.decode()
    return str(value)


def _target_ready(checks: list[Check]) -> bool:
    required = {"donjon_assembly_keff", "adf_payload_carrythrough", "production_adf"}
    return all(check.ok for check in checks if check.name in required)


def _print_report(checks: list[Check], target_ready: bool) -> None:
    print("C5G7 locked validation target: DONJON assembly-wise k-eff + production ADF")
    print(f"target_ready={target_ready}")
    print()
    for check in checks:
        print(f"{check.status:4s} {check.name}: {check.detail}")


if __name__ == "__main__":
    raise SystemExit(main())

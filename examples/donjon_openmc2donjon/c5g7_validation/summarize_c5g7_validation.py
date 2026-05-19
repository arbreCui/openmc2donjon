#!/usr/bin/env python3
"""Summarize the C5G7 production assembly-wise DONJON validation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import h5py
import numpy as np

from openmc2donjon.macrolib import read_macrolib_ascii
from openmc2donjon.multicompo import read_mgxs_hdf5


ROOT = Path("/Users/wen/dragon-5.1")
DATA = ROOT / "Donjon/data/openmc2donjon"
RESULTS = ROOT / "Donjon/Darwin_arm64"

DEFAULT_MGXS = DATA / "c5g7_assembly_p1_adf_production.h5"
DEFAULT_MACROLIB_LISTING = RESULTS / "c5g7_adf_production_carrythrough.result"
DEFAULT_DIFFUSION_LISTING = RESULTS / "c5g7pa_diffusion_keff.result"
DEFAULT_SPN3_LISTING = RESULTS / "c5g7pa_spn3_keff.result"
DEFAULT_SPN3_SCAT1_LISTING = RESULTS / "c5g7pa_spn3_scat1_keff.result"
DEFAULT_NSSF_2G_LISTING = RESULTS / "c5g7pa_2g_nssf_adf_effect.result"
DEFAULT_AUDIT_JSON = DATA / "c5g7_assembly_p1_adf_production_audit.json"
DEFAULT_OPENMC_KEFF = 1.18798


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--macrolib-listing", type=Path, default=DEFAULT_MACROLIB_LISTING)
    parser.add_argument("--diffusion-listing", type=Path, default=DEFAULT_DIFFUSION_LISTING)
    parser.add_argument("--spn3-listing", type=Path, default=DEFAULT_SPN3_LISTING)
    parser.add_argument("--spn3-scat1-listing", type=Path, default=DEFAULT_SPN3_SCAT1_LISTING)
    parser.add_argument("--nssf-2g-listing", type=Path, default=DEFAULT_NSSF_2G_LISTING)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--openmc-keff", type=float, default=DEFAULT_OPENMC_KEFF)
    args = parser.parse_args()

    mixtures, _ = read_mgxs_hdf5(args.mgxs)
    macrolib = read_macrolib_ascii(args.macrolib_listing)
    adf_rows = compare_adf(mixtures, macrolib)

    print("C5G7 production assembly-wise validation")
    print(f"  MGXS: {args.mgxs}")
    print(f"  NCR listing: {args.macrolib_listing}")
    print(f"  mixtures={len(mixtures)} groups={mixtures[0].ngroups}")
    print()

    print("Production ADF metadata")
    with h5py.File(args.mgxs, "r") as h5:
        for key in (
            "adf_kind",
            "adf_real",
            "adf_method",
            "adf_surface_flux_source",
            "adf_homogeneous_face_source",
            "adf_invalid_count",
            "adf_invalid_interior_count",
            "adf_clip_min",
            "adf_clip_max",
        ):
            if key in h5.attrs:
                print(f"  {key}: {attr_text(h5.attrs[key])}")
    print()

    print("ADF payload comparison: OpenMC HDF5 -> NCR L_MACROLIB")
    for row in adf_rows:
        print(
            f"  {row['name']:<8s} range=[{row['min']:.8g}, {row['max']:.8g}] "
            f"max_abs={row['max_abs']:.3e} max_rel={row['max_rel']:.3e}"
        )
    print()

    if args.audit_json.exists():
        audit = json.loads(args.audit_json.read_text())
        print("MGXS consistency audit")
        print(f"  bad_group_entries={audit['bad_group_entry_count']}")
        print(f"  row_balance_bad_entries={audit['row_balance_bad_entry_count']}")
        print(
            "  row_balance_residual_max_abs="
            f"{audit['row_balance_residual_max_abs']:.3e}"
        )
        print()

    print("DONJON keff")
    for label, path in (
        ("diffusion", args.diffusion_listing),
        ("SPN3", args.spn3_listing),
        ("SPN3 SCAT1", args.spn3_scat1_listing),
    ):
        if not path.exists():
            continue
        keff = extract_keff(path)
        abs_pcm = (keff - args.openmc_keff) * 1.0e5
        rel_pcm = (keff / args.openmc_keff - 1.0) * 1.0e5
        print(
            f"  {label:<9s} k={keff:.10f} "
            f"delta_k={abs_pcm:+.1f} pcm delta_rel={rel_pcm:+.1f} pcm"
        )
    print(f"  OpenMC reference k={args.openmc_keff:.5f}")

    if args.nssf_2g_listing.exists():
        adf_keff, nodf_keff = extract_nssf_anm_pair(args.nssf_2g_listing)
        delta = adf_keff - nodf_keff
        print()
        print("ADF-active solver smoke")
        print(f"  listing={args.nssf_2g_listing}")
        print("  derivative=2-group flux-weighted NSSF/ANM smoke")
        print(f"  ADF  k={adf_keff:.8f}")
        print(f"  NODF k={nodf_keff:.8f}")
        print(f"  ADF-NODF delta_k={delta:+.8f} ({delta * 1.0e5:+.1f} pcm)")
    return 0


def compare_adf(mixtures, macrolib) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for name in sorted(macrolib.adf):
        expected = np.stack([mix.adf[name] for mix in mixtures])
        actual = macrolib.adf[name]
        if actual.shape != expected.shape:
            raise ValueError(f"{name}: ADF shape mismatch {actual.shape} != {expected.shape}")
        diff = np.abs(actual - expected)
        rel = diff / np.maximum(np.abs(expected), 1.0e-12)
        rows.append(
            {
                "name": name,
                "min": float(actual.min()),
                "max": float(actual.max()),
                "max_abs": float(diff.max()),
                "max_rel": float(rel.max()),
            }
        )
    return rows


def extract_keff(path: Path) -> float:
    text = path.read_text(errors="replace")
    matches = re.findall(
        r"EFFECTIVE MULTIPLICATION FACTOR\s*=\s*([0-9.+\-Ee]+)", text
    )
    if not matches:
        matches = re.findall(r"K-EFFECTIVE\s+([0-9.+\-Ee]+)", text)
    if not matches:
        raise ValueError(f"no keff found in {path}")
    return float(matches[-1])


def extract_labeled_echo(path: Path, label: str) -> float:
    text = path.read_text(errors="replace")
    pattern = rf"{re.escape(label)}\s+([0-9.+\-Ee]+)"
    matches = re.findall(pattern, text)
    if not matches:
        raise ValueError(f"no labeled value {label!r} found in {path}")
    return float(matches[-1])


def extract_nssf_anm_pair(path: Path) -> tuple[float, float]:
    text = path.read_text(errors="replace")
    matches = re.findall(r"NSSFL4:\s+ANM KEFF=\s*([0-9.+\-Ee]+)", text)
    if len(matches) >= 2:
        return float(matches[0]), float(matches[1])
    return (
        extract_labeled_echo(
            path,
            "OPENMC2DONJON C5G7 2G NSSF ADF K-EFFECTIVE",
        ),
        extract_labeled_echo(
            path,
            "OPENMC2DONJON C5G7 2G NSSF NODF K-EFFECTIVE",
        ),
    )


def attr_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.bytes_):
        return value.decode()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())

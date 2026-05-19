#!/usr/bin/env python3
"""Validate the DRAGON exact-pin C5G7 EDI assembly homogenization run."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


DEFAULT_DECK = Path(
    "/Users/wen/dragon-5.1/Dragon/data/openmc2donjon/c5g7_moc_region_edi.x2m"
)
DEFAULT_RESULT = Path(
    "/Users/wen/dragon-5.1/Dragon/Darwin_arm64/c5g7_moc_region_edi.result"
)
DEFAULT_REFERENCE_KEFF = 1.18798


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", type=Path, default=DEFAULT_DECK)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--reference-keff", type=float, default=DEFAULT_REFERENCE_KEFF)
    parser.add_argument("--keff-tolerance-pcm", type=float, default=100.0)
    parser.add_argument("--expected-nmerge", type=int, default=9)
    parser.add_argument("--expected-ngcond", type=int, default=7)
    parser.add_argument("--expected-region-map", type=int, default=3757)
    parser.add_argument("--expected-edition-name", default="C5G7REG")
    parser.add_argument(
        "--expect-edi-currents",
        action="store_true",
        help="Require the EDI_CURR face-current records to be present.",
    )
    parser.add_argument(
        "--expect-adf",
        action="store_true",
        help="Require an EDI ADF directory/state to be present.",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    checks = validate(
        args.deck,
        args.result,
        args.reference_keff,
        args.keff_tolerance_pcm,
        args.expected_nmerge,
        args.expected_ngcond,
        args.expected_region_map,
        args.expected_edition_name,
        args.expect_edi_currents,
        args.expect_adf,
    )

    ready = all(check.ok for check in checks)
    print("DRAGON C5G7 exact-pin EDI assembly reference")
    print(f"ready={ready}")
    print("")
    for check in checks:
        print(f"{'OK' if check.ok else 'FAIL':4s} {check.name}: {check.detail}")
    return 0 if ready or not args.strict else 1


def validate(
    deck: Path,
    result: Path,
    reference_keff: float,
    keff_tolerance_pcm: float,
    expected_nmerge: int,
    expected_ngcond: int,
    expected_region_map: int,
    expected_edition_name: str,
    expect_edi_currents: bool = False,
    expect_adf: bool = False,
) -> list[Check]:
    checks: list[Check] = []
    deck_text = _read(deck)
    result_text = _read(result)

    region_map = _region_map_count(deck_text)
    checks.append(
        Check(
            "region_merge_map",
            region_map == expected_region_map,
            f"{region_map} entries, expected {expected_region_map}",
        )
    )

    keff = _last_float(result_text, r"FINAL KEFF=\s*([0-9.E+-]+)")
    if keff is None:
        checks.append(Check("moc_keff", False, "FINAL KEFF not found"))
    else:
        delta_pcm = (keff - reference_keff) * 1.0e5
        checks.append(
            Check(
                "moc_keff",
                abs(delta_pcm) <= keff_tolerance_pcm,
                (
                    f"k-eff={keff:.10f}, reference={reference_keff:.10f}, "
                    f"delta={delta_pcm:+.1f} pcm, tolerance={keff_tolerance_pcm:.1f} pcm"
                ),
            )
        )

    nmerge = _last_int(result_text, r"\bNMERGE\s+([0-9]+)\s+\(NUMBER OF MERGED REGIONS\)")
    checks.append(
        Check(
            "edi_nmerge",
            nmerge == expected_nmerge,
            f"NMERGE={nmerge}, expected {expected_nmerge}",
        )
    )

    ngcond = _last_int(
        result_text, r"\bNGCOND\s+([0-9]+)\s+\(NUMBER OF CONDENSED ENERGY GROUPS\)"
    )
    checks.append(
        Check(
            "edi_ngcond",
            ngcond == expected_ngcond,
            f"NGCOND={ngcond}, expected {expected_ngcond}",
        )
    )

    checks.append(
        Check(
            "edi_save_directory",
            expected_edition_name in result_text
            and "MERGED/CONDENSED SET OF X-S SAVED" in result_text,
            f"{expected_edition_name} saved in EDI macrolib directory",
        )
    )

    deck_requests_currents = "EDI_CURR" in deck_text
    nfunl = _last_int(
        result_text, r"\bNFUNL\s+([0-9]+)\s+\(NUMBER OF SPHERICAL HARMONICS COMPONENTS\)"
    )
    has_current_records = (
        "COURX-INTG" in result_text and "COURY-INTG" in result_text
    ) or "EDI_CURR probe" in result_text
    checks.append(
        Check(
            "edi_current_source",
            has_current_records if expect_edi_currents else True,
            (
                f"requested={deck_requests_currents}, NFUNL={nfunl}, "
                f"COURX/COURY present={has_current_records}"
            ),
        )
    )

    idf_values = [
        int(value)
        for value in re.findall(r"\bIDF\s+([0-9]+)\s+\(=0/2 BOUNDARY FLUXES", result_text)
    ]
    has_adf = any(value > 0 for value in idf_values)
    checks.append(
        Check(
            "adf_source",
            has_adf if expect_adf else True,
            (
                "ADF directory/state present"
                if has_adf
                else "no ADF directory/state detected; current assembly EDI is macro-only"
            ),
        )
    )

    checks.append(
        Check(
            "normal_end",
            "normal end of execution for dragon" in result_text,
            "DRAGON listing reports normal end",
        )
    )
    return checks


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def _region_map_count(deck_text: str) -> int:
    match = re.search(r"\bMERGE\s+REGION\b(?P<body>.*?)\bCOND\s+NONE\b", deck_text, re.S)
    if not match:
        return 0
    return len(re.findall(r"\b[0-9]+\b", match.group("body")))


def _last_float(text: str, pattern: str) -> float | None:
    matches = re.findall(pattern, text)
    return float(matches[-1]) if matches else None


def _last_int(text: str, pattern: str) -> int | None:
    matches = re.findall(pattern, text)
    return int(matches[-1]) if matches else None


if __name__ == "__main__":
    raise SystemExit(main())

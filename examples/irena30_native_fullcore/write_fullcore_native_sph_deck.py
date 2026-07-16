#!/usr/bin/env python3
"""Write the strict 91-position IRENA full-core DRAGON native-SPH deck.

This generator is deliberately separate from ``write_donjon_decks.py``.
That module consumes already-qualified component records; this one performs a
direct native-SPH solve against a Converter-produced full-core reference
MACROLIB using either 91 independent positions or 21 strict global D3 orbits.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys


N_POSITIONS = 91
SIDE_CM = "10.103629710818451"
AXIAL_HEIGHT_CM = "10.0"
MAX_SEQ_ASCII_PATH = 64


def _mixture_numbers(values: tuple[int, ...]) -> str:
    """Return 91 DRAGON HEXZ mixture ids in blocks of ten."""

    return "\n".join(
        "  " + " ".join(str(value) for value in values[start : start + 10])
        for start in range(0, N_POSITIONS, 10)
    )


def _d3_orbit_map() -> tuple[int, ...]:
    """Load the benchmark's exact 21-orbit map from its sibling module."""

    path = Path(__file__).with_name("global_orbits.py")
    spec = importlib.util.spec_from_file_location(
        "_openmc2donjon_irena_fullcore_global_orbits", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load IRENA global orbit map: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return tuple(module.MIXTURE_MAP)


def _mapping(mapping: str) -> tuple[tuple[int, ...], str]:
    if mapping == "independent":
        values = tuple(range(1, N_POSITIONS + 1))
        comment = (
            "91 independent position mixtures; each MIX id is the physical "
            "ring/position ordinal."
        )
    elif mapping == "d3-orbits":
        values = _d3_orbit_map()
        comment = (
            "21 global D3 symmetry-orbit mixtures repeated over 91 physical "
            "positions; reference order is global_orbits.py ORBITS."
        )
    else:  # argparse prevents this; retain a direct-call invariant.
        raise ValueError(f"unknown full-core mapping: {mapping}")
    if len(values) != N_POSITIONS:
        raise RuntimeError(
            f"full-core mapping must contain {N_POSITIONS} positions, found {len(values)}"
        )
    mixture_ids = sorted(set(values))
    if mixture_ids != list(range(1, max(mixture_ids) + 1)):
        raise RuntimeError("full-core mapping mixture ids must be consecutive from 1")
    return values, comment


TEMPLATE = """* IRENA-30 direct 91-position full-core native SPH.
* Fine OpenMC full core -> Converter reference MACROLIB -> DRAGON SNT SPH.
* Mapping: {mapping_comment}
MODULE GEO: SNT: SPH: ASM: FLU: OUT: EDI: GREP: END: ;
LINKED_LIST MACROREF MACROSPH GEOM TRACK SYSTEM FLUX VERIFY REGVERIFY EDIRES ;
REAL Kref Kcalc ;
SEQ_ASCII REF_ASC :: FILE '{reference}' ;
SEQ_ASCII SPH_ASC :: FILE '{sph_output}' ;
SEQ_ASCII VERIFY_ASC :: FILE '{verify_output}' ;
SEQ_ASCII REGION_ASC :: FILE '{region_verify_output}' ;
SEQ_ASCII EDI_ASC :: FILE '{edi_output}' ;

MACROREF := REF_ASC ;
GREP: MACROREF :: GETVAL 'K-EFFECTIVE ' 1 >>Kref<< ;

GEOM := GEO: :: HEXZ 91 1 EDIT 1
  Z- REFL Z+ REFL
  HBC COMPLETE VOID
  SIDE {side} SPLITL 2
  MESHZ 0.0 {height}
  MIX
{mixtures}
;

TRACK := SNT: GEOM ::
  EDIT 1 DIAM 1 SN 8 SCAT 2
  LIVO 3 3 MAXI 1000 EPSI 1.0E-08
;

MACROSPH := SPH: MACROREF TRACK ::
  EDIT 4 MACRO SN STD ITER 300 1.0E-06 MAXNB 20
;

SYSTEM := ASM: MACROSPH TRACK :: ARM ;
FLUX := FLU: SYSTEM MACROSPH TRACK ::
  EDIT 0 TYPE K EXTE 500 1.0E-07 THER 1000 1.0E-08 UNKT 1.0E-08
;
GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>Kcalc<< ;

VERIFY := OUT: FLUX GEOM MACROSPH TRACK :: EDIT 0 INTG MIX ;
* REGVERIFY preserves the 91 physical HEXZ positions for power validation.
REGVERIFY := OUT: FLUX GEOM MACROSPH TRACK :: EDIT 0 INTG IN ;
* EDIRES is a 21-orbit aggregate in d3-orbits mode and is balance-only.
* It must never be expanded and used as a 91-position power distribution.
EDIRES := EDI: MACROSPH TRACK FLUX :: EDIT 2 MERG MIX COND SAVE ;

ECHO 'OPENMC2DONJON IRENA30 FULLCORE NATIVE SPH REFERENCE K-EFFECTIVE' Kref ;
ECHO 'OPENMC2DONJON IRENA30 FULLCORE NATIVE SPH FINAL K-EFFECTIVE' Kcalc ;
SPH_ASC := MACROSPH ;
VERIFY_ASC := VERIFY ;
REGION_ASC := REGVERIFY ;
EDI_ASC := EDIRES ;
END: ;
"""


def _seq_ascii_path(parser: argparse.ArgumentParser, path: Path, option: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute() or ".." in expanded.parts:
        parser.error(
            f"{option} must be a working-directory-relative path without '..'"
        )
    if not expanded.parts or expanded == Path("."):
        parser.error(f"{option} must name a relative FILE artifact")
    text = str(expanded)
    if len(text) > MAX_SEQ_ASCII_PATH:
        parser.error(
            f"{option} exceeds the conservative {MAX_SEQ_ASCII_PATH}-character "
            f"DONJON SEQ_ASCII limit: {expanded}"
        )
    if "'" in text or "\n" in text or "\r" in text:
        parser.error(f"{option} contains a character not supported by SEQ_ASCII")
    return expanded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference",
        type=Path,
        required=True,
        help=(
            "working-directory-relative path to the Converter "
            "mapping-compatible reference MACROLIB"
        ),
    )
    parser.add_argument(
        "--sph-output",
        type=Path,
        required=True,
        help="working-directory-relative path for the corrected native-SPH MACROLIB",
    )
    parser.add_argument(
        "--verify-output",
        type=Path,
        required=True,
        help="working-directory-relative path for the OUT: mixture verification MACROLIB",
    )
    parser.add_argument(
        "--region-verify-output",
        type=Path,
        required=True,
        help=(
            "working-directory-relative path for the OUT: INTG IN 91-physical-position "
            "verification MACROLIB used by the power-shape gate"
        ),
    )
    parser.add_argument(
        "--edi-output",
        type=Path,
        required=True,
        help=(
            "working-directory-relative path for the EDI: mixture-aggregated reaction-rate "
            "object used only for global balance (21 entries in d3-orbits mode)"
        ),
    )
    parser.add_argument(
        "--mapping",
        choices=("independent", "d3-orbits"),
        default="independent",
        help=(
            "independent keeps 91 mixtures; d3-orbits ties the 21 strict "
            "global full-core symmetry orbits"
        ),
    )
    parser.add_argument("--output", type=Path, required=True, help="deck path")
    args = parser.parse_args(argv)

    reference = _seq_ascii_path(parser, args.reference, "--reference")
    sph_output = _seq_ascii_path(parser, args.sph_output, "--sph-output")
    verify_output = _seq_ascii_path(parser, args.verify_output, "--verify-output")
    region_verify_output = _seq_ascii_path(
        parser, args.region_verify_output, "--region-verify-output"
    )
    edi_output = _seq_ascii_path(parser, args.edi_output, "--edi-output")
    mixture_map, mapping_comment = _mapping(args.mapping)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        TEMPLATE.format(
            reference=reference,
            sph_output=sph_output,
            verify_output=verify_output,
            region_verify_output=region_verify_output,
            edi_output=edi_output,
            side=SIDE_CM,
            height=AXIAL_HEIGHT_CM,
            mixtures=_mixture_numbers(mixture_map),
            mapping_comment=mapping_comment,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

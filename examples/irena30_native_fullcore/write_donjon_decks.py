#!/usr/bin/env python3
"""Write IRENA full-core SN and SPN decks from a 91-position MACROLIB."""

from __future__ import annotations

import argparse
from pathlib import Path


N_POSITIONS = 91
SIDE_CM = "10.103629710818451"
MAX_SEQ_ASCII_PATH = 64


def _mixture_numbers() -> str:
    return "\n".join(
        "  " + " ".join(str(value) for value in range(start, min(start + 10, 92)))
        for start in range(1, 92, 10)
    )


COMMON = """* IRENA-specific 91-position consumer of legacy local components.
* Component records were expanded without averaging, fitting, or full-core SPH.
LINKED_LIST MACRO GEOM TRACK SYSTEM FLUX EDIRES ;
REAL keff ;
SEQ_ASCII MACRO_ASC :: FILE '{macrolib}' ;
SEQ_ASCII EDI_ASC :: FILE '{edi}' ;
MACRO := MACRO_ASC ;
GEOM := GEO: :: HEXZ 91 1 EDIT 0
  Z- REFL Z+ REFL HBC COMPLETE VOID
  SIDE {side} SPLITL 2
  MESHZ 0.0 10.0
  MIX
{mixtures}
;
"""


SN = """MODULE GEO: SNT: ASM: FLU: EDI: GREP: END: ;
{common}
TRACK := SNT: GEOM :: EDIT 0 DIAM 1 SN {sn_order} SCAT {scatter_moments} ;
SYSTEM := ASM: MACRO TRACK :: ARM ;
FLUX := FLU: SYSTEM MACRO TRACK :: EDIT 1 TYPE K EXTE 500 1.0E-5 ;
EDIRES := EDI: MACRO TRACK FLUX :: EDIT 2 MERG MIX COND SAVE ;
EDI_ASC := EDIRES ;
GREP: FLUX :: GETVAL 'K-EFFECTIVE' 1 >>keff<< ;
ECHO 'OPENMC2DONJON IRENA30 COMPONENT FULLCORE SN K-EFFECTIVE' keff ;
END: ;
"""


SPN = """MODULE GEO: TRIVAT: TRIVAA: FLUD: EDI: GREP: END: ;
{common}
TRACK := TRIVAT: GEOM ::
  TITLE 'IRENA30 legacy component diagnostic SPN'
  EDIT 1 MAXR 20000 DUAL 1 1 SPN {spn_order} SCAT {scatter_moments}
;
SYSTEM := TRIVAA: MACRO TRACK :: EDIT 0 ;
FLUX := FLUD: SYSTEM TRACK :: EDIT 1 ADI 5 EXTE 500 1.0E-6 ACCE 5 3 ;
EDIRES := EDI: MACRO TRACK FLUX :: EDIT 2 MERG MIX COND SAVE ;
EDI_ASC := EDIRES ;
GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;
ECHO 'OPENMC2DONJON IRENA30 COMPONENT FULLCORE SPN K-EFFECTIVE' keff ;
END: ;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macrolib", type=Path, required=True)
    parser.add_argument("--sn-edi", type=Path, required=True)
    parser.add_argument("--spn-edi", type=Path, required=True)
    parser.add_argument("--deck-dir", type=Path, required=True)
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--sn-order", type=int, default=8)
    parser.add_argument("--spn-order", type=int, default=3)
    parser.add_argument(
        "--scatter-moments",
        type=int,
        default=2,
        help=(
            "number of scattering moments consumed; IRENA defaults to the "
            "P0+P1 route used by the independently accepted 91-position baseline"
        ),
    )
    args = parser.parse_args()
    for path in (args.macrolib, args.sn_edi, args.spn_edi):
        if not path.is_absolute():
            parser.error("DONJON SEQ_ASCII paths must be absolute")
        if len(str(path)) > MAX_SEQ_ASCII_PATH:
            parser.error(
                f"SEQ_ASCII path exceeds {MAX_SEQ_ASCII_PATH} characters: {path}"
            )
    if args.sn_order <= 0 or args.spn_order <= 0 or args.scatter_moments <= 0:
        parser.error("SN order, SPN order, and scattering-moment count must be positive")
    common_args = {
        "macrolib": args.macrolib,
        "side": SIDE_CM,
        "mixtures": _mixture_numbers(),
    }
    args.deck_dir.mkdir(parents=True, exist_ok=True)
    sn_path = args.deck_dir / f"irena30_component_fullcore_sn_{args.stamp}.x2m"
    spn_path = args.deck_dir / f"irena30_component_fullcore_spn_{args.stamp}.x2m"
    sn_common = COMMON.format(edi=args.sn_edi, **common_args)
    spn_common = COMMON.format(edi=args.spn_edi, **common_args)
    sn_path.write_text(
        SN.format(
            common=sn_common,
            sn_order=args.sn_order,
            scatter_moments=args.scatter_moments,
        ),
        encoding="utf-8",
    )
    spn_path.write_text(
        SPN.format(
            common=spn_common,
            spn_order=args.spn_order,
            scatter_moments=args.scatter_moments,
        ),
        encoding="utf-8",
    )
    print(f"wrote {sn_path}")
    print(f"wrote {spn_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

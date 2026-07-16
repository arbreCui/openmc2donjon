#!/usr/bin/env python3
"""Write the strict seven-hex DRAGON native-SPH deck for one IRENA colorset."""

from __future__ import annotations

import argparse
from pathlib import Path


TEMPLATE = """* IRENA {case}: OpenMC fine -> Converter reference -> DRAGON native SPH.
* Mixtures preserve every active center/neighbor position; 0 denotes physical OUT.
* No ADF, global eigenvalue factor, clipping, frozen group, or flux floor.
MODULE GEO: {modules} SPH: OUT: GREP: END: ;
LINKED_LIST MACROREF MACROSPH GEOM TRACK SYSTEM FLUX VERIFY_EDIT ;
REAL Kref Kcalc ;
SEQ_ASCII REF_ASC :: FILE '{reference}' ;
SEQ_ASCII SPH_ASC :: FILE '{sph_output}' ;
SEQ_ASCII VERIFY_ASC :: FILE '{verify_output}' ;

MACROREF := REF_ASC ;
GREP: MACROREF :: GETVAL 'K-EFFECTIVE ' 1 >>Kref<< ;

GEOM := GEO: :: HEX 7
  EDIT 1
  HBC COMPLETE ALBE 1.0
  SIDE {side:.7f} SPLITL 2
  MIX {mix_map}
;

{tracking}

MACROSPH := SPH: MACROREF TRACK ::
  EDIT 4 MACRO {sph_mode} STD ITER {iterations} {epsilon:.1E} MAXNB 20
;
SPH_ASC := MACROSPH ;

{system_flux}
GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>Kcalc<< ;
VERIFY_EDIT := OUT: FLUX GEOM MACROSPH TRACK :: EDIT 0 INTG MIX ;

ECHO 'OPENMC2DONJON NATIVE SPH REFERENCE K-EFFECTIVE' Kref ;
ECHO 'OPENMC2DONJON NATIVE SPH FINAL K-EFFECTIVE' Kcalc ;
VERIFY_ASC := VERIFY_EDIT ;
END: ;
"""


SN_TRACKING = """TRACK := SNT: GEOM ::
  EDIT 1 DIAM 1 SN {sn_order} SCAT {scatter_moments}
  {acceleration} MAXI {inner_iterations} EPSI {inner_epsilon:.1E}
;"""


SN_SYSTEM_FLUX = """SYSTEM := ASM: MACROSPH TRACK :: ARM ;
FLUX := FLU: SYSTEM MACROSPH TRACK ::
  EDIT 0 TYPE K EXTE 500 1.0E-7 THER 1000 1.0E-8 UNKT 1.0E-8
;"""


SPN_TRACKING = """TRACK := TRIVAT: GEOM ::
  TITLE 'IRENA {case} native SPH SPN3'
  EDIT 1 MAXR 1000 DUAL 1 1 SPN 3 SCAT {scatter_moments}
;"""


SPN_SYSTEM_FLUX = """SYSTEM := TRIVAA: MACROSPH TRACK :: EDIT 0 ;
FLUX := FLUD: SYSTEM TRACK ::
  EDIT 0 ADI 5 EXTE 200 1.0E-7 ACCE 5 3
;"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--sph-output", type=Path, required=True)
    parser.add_argument("--verify-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--side",
        type=float,
        required=True,
        help="declared downstream node side in cm; must match the fine colorset",
    )
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--epsilon", type=float, default=1.0e-6)
    parser.add_argument(
        "--solver",
        choices=("sn", "spn"),
        default="sn",
        help="DRAGON macro solver used by native SPH; SN supports P1 scattering",
    )
    parser.add_argument("--sn-order", type=int, default=8)
    parser.add_argument(
        "--sn-acceleration",
        choices=("gmres", "dsa", "livolant"),
        default="livolant",
        help=(
            "one-speed scattering acceleration; Livolant emits auditable "
            "nonconvergence markers in DRAGON 5.1"
        ),
    )
    parser.add_argument(
        "--sn-gmres-restart",
        type=int,
        default=20,
        help="GMRES restart dimension for each SN one-speed solve",
    )
    parser.add_argument(
        "--sn-inner-iterations",
        type=int,
        default=1000,
        help="maximum iterations for each SN one-speed solve",
    )
    parser.add_argument(
        "--sn-inner-epsilon",
        type=float,
        default=1.0e-8,
        help="convergence criterion for each SN one-speed solve",
    )
    parser.add_argument("--sn-dsa-interval", type=int, default=5)
    parser.add_argument("--sn-dsa-order", type=int, default=0)
    parser.add_argument("--sn-dsa-solver", type=int, choices=(1, 2), default=2)
    parser.add_argument("--sn-livolant-free", type=int, default=3)
    parser.add_argument("--sn-livolant-accelerated", type=int, default=3)
    parser.add_argument(
        "--mix-map",
        default="1,2,3,4,5,6,7",
        help="seven comma-separated HEX mixture ids in center/neighbor order; 0 is OUT",
    )
    parser.add_argument(
        "--scatter-moments",
        type=int,
        default=2,
        help=(
            "number of scattering moments consumed; IRENA defaults to P0+P1 "
            "to match its independently accepted full-core transport baseline"
        ),
    )
    args = parser.parse_args(argv)

    for path in (args.reference, args.sph_output, args.verify_output):
        if not path.is_absolute():
            parser.error("DRAGON SEQ_ASCII paths must be absolute")
    if (
        args.side <= 0.0
        or args.iterations <= 0
        or args.epsilon <= 0.0
        or args.scatter_moments <= 0
        or args.sn_order <= 0
        or args.sn_gmres_restart <= 0
        or args.sn_inner_iterations <= 0
        or args.sn_inner_epsilon <= 0.0
        or args.sn_dsa_interval < 0
        or args.sn_dsa_order < 0
        or args.sn_livolant_free <= 0
        or args.sn_livolant_accelerated <= 0
    ):
        parser.error(
            "side, iterations, epsilon, SN controls, and scatter-moment count must be positive"
        )
    if args.solver == "spn" and args.scatter_moments > 1:
        parser.error(
            "DRAGON TRIVAT native-SPH does not implement anisotropic scattering; "
            "use --solver sn or --scatter-moments 1"
        )
    try:
        mix_map = tuple(int(value.strip()) for value in args.mix_map.split(","))
    except ValueError:
        parser.error("--mix-map must contain integers")
    if len(mix_map) != 7 or any(value < 0 for value in mix_map):
        parser.error("--mix-map must contain seven non-negative mixture ids")
    active = sorted(value for value in mix_map if value > 0)
    if not active or active != list(range(1, len(active) + 1)):
        parser.error("positive --mix-map ids must be consecutive from 1")
    if args.solver == "sn":
        if args.sn_acceleration == "gmres":
            acceleration = f"GMRES {args.sn_gmres_restart}"
        elif args.sn_acceleration == "dsa":
            acceleration = (
                f"DSA {args.sn_dsa_interval} {args.sn_dsa_order} "
                f"{args.sn_dsa_solver}"
            )
        else:
            acceleration = (
                f"LIVO {args.sn_livolant_free} "
                f"{args.sn_livolant_accelerated}"
            )
        modules = "SNT: ASM: FLU:"
        tracking = SN_TRACKING.format(
            sn_order=args.sn_order,
            scatter_moments=args.scatter_moments,
            gmres_restart=args.sn_gmres_restart,
            inner_iterations=args.sn_inner_iterations,
            inner_epsilon=args.sn_inner_epsilon,
            acceleration=acceleration,
        )
        system_flux = SN_SYSTEM_FLUX
        sph_mode = "SN"
    else:
        modules = "TRIVAT: TRIVAA: FLUD:"
        tracking = SPN_TRACKING.format(
            case=args.case,
            scatter_moments=args.scatter_moments,
        )
        system_flux = SPN_SYSTEM_FLUX
        sph_mode = "PN"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        TEMPLATE.format(
            case=args.case,
            modules=modules,
            reference=args.reference,
            sph_output=args.sph_output,
            verify_output=args.verify_output,
            side=args.side,
            mix_map=" ".join(str(value) for value in mix_map),
            iterations=args.iterations,
            epsilon=args.epsilon,
            scatter_moments=args.scatter_moments,
            tracking=tracking,
            system_flux=system_flux,
            sph_mode=sph_mode,
        ),
        encoding="utf-8",
    )
    print(f"wrote native-SPH deck: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

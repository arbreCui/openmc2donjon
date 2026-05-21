"""DONJON command helper for the C5G7 fixed-OpenMC SPH loop smoke."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    solve = subparsers.add_parser("solve", help="run one DONJON flux solve")
    solve.add_argument("--donjon-root", type=Path, required=True)
    solve.add_argument("--macrolib", type=Path, required=True)
    solve.add_argument("--result", type=Path, required=True)
    solve.add_argument("--iteration", type=int, required=True)
    solve.add_argument("--run-tag", default="c5g7_fixed_openmc_sph_loop")

    apply = subparsers.add_parser("apply", help="apply NSPH factors with DSPH/MAC")
    apply.add_argument("--donjon-root", type=Path, required=True)
    apply.add_argument("--raw-macrolib", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--iteration", type=int, required=True)
    apply.add_argument("--run-tag", default="c5g7_fixed_openmc_sph_loop")

    args = parser.parse_args(argv)
    if args.command == "solve":
        return _solve(args)
    if args.command == "apply":
        return _apply(args)
    raise AssertionError(args.command)


def _solve(args: argparse.Namespace) -> int:
    _require_file(args.macrolib)
    donjon_root = args.donjon_root
    case_id = f"{args.run_tag}_iter{args.iteration}"
    deck_rel = f"openmc2donjon/case_runs/c5g7_fixed_openmc_sph_loop/{case_id}_solve.x2m"
    deck_path = donjon_root / "data" / deck_rel
    short_macrolib = Path("/tmp") / f"{case_id}.macrolib.txt"

    deck_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.macrolib, short_macrolib)
    _write_solve_deck(deck_path, short_macrolib, args.iteration)
    _run_rdonjon(donjon_root, deck_rel)

    produced = donjon_root / "Darwin_arm64" / f"{case_id}_solve.result"
    _require_file(produced)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(produced, args.result)
    print(f"C5G7 solve iteration={args.iteration} result={args.result}")
    return 0


def _apply(args: argparse.Namespace) -> int:
    _require_file(args.raw_macrolib)
    donjon_root = args.donjon_root
    case_id = f"{args.run_tag}_iter{args.iteration}"
    deck_rel = f"openmc2donjon/case_runs/c5g7_fixed_openmc_sph_loop/{case_id}_apply.x2m"
    deck_path = donjon_root / "data" / deck_rel
    short_raw = Path("/tmp") / f"{case_id}.raw_sph.macrolib.txt"
    short_corrected = Path("/tmp") / f"{case_id}.corrected_pn.macrolib.txt"

    deck_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.raw_macrolib, short_raw)
    if short_corrected.exists():
        short_corrected.unlink()
    _write_apply_deck(deck_path, short_raw, short_corrected, args.iteration)
    _run_rdonjon(donjon_root, deck_rel)

    _require_file(short_corrected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(short_corrected, args.output)
    print(f"C5G7 SPH apply iteration={args.iteration} output={args.output}")
    return 0


def _run_rdonjon(donjon_root: Path, deck_rel: str) -> None:
    runner = donjon_root / "rdonjon"
    if not runner.exists():
        raise FileNotFoundError(f"missing DONJON runner: {runner}")
    completed = subprocess.run(
        [str(runner), "-q", deck_rel],
        cwd=donjon_root,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"DONJON failed for {deck_rel} with exit code {completed.returncode}")


def _write_solve_deck(deck: Path, macrolib: Path, iteration: int) -> None:
    deck.write_text(
        f"""* C5G7 assembly-wise fixed-OpenMC SPH loop solve, iteration {iteration}.
MODULE GEO: TRIVAT: TRIVAA: FLUD: GREP: UTL: END: ABORT: ;
LINKED_LIST MACRO GEOM TRACK SYS FLUX ;
REAL keff ;
SEQ_ASCII MACRO_ASC :: FILE '{macrolib}' ;

MACRO := MACRO_ASC ;
GEOM := GEO: :: CAR2D 3 3
  EDIT 0
  X- REFL X+ VOID
  Y- REFL Y+ VOID
  MIX
  1 2 3
  4 5 6
  7 8 9
  MESHX
  0.00000000 21.42000000 42.84000000 64.26000000
  MESHY
  0.00000000 21.42000000 42.84000000 64.26000000
;

TRACK := TRIVAT: GEOM ::
  TITLE 'C5G7 fixed OpenMC XS SPH loop iteration {iteration}' EDIT 1 MAXR 109
  DUAL 1 1 ;
SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;
FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 700 1.E-6 ;
GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;
ECHO 'OPENMC2DONJON C5G7 FIXED OPENMC SPH LOOP ITER {iteration} K-EFFECTIVE' keff ;
UTL: FLUX :: IMPR STATE-VECTOR * DUMP ;
END: ;
""",
        encoding="utf-8",
    )


def _write_apply_deck(
    deck: Path,
    raw_sph_macrolib: Path,
    corrected_macrolib: Path,
    iteration: int,
) -> None:
    deck.write_text(
        f"""* C5G7 fixed-OpenMC SPH loop DSPH/MAC apply, iteration {iteration}.
MODULE DSPH: MAC: END: ABORT: ;
LINKED_LIST SPHSRC DMACROPN OPTIMPN MACROPN ;
SEQ_ASCII SPH_ASC :: FILE '{raw_sph_macrolib}' ;
SEQ_ASCII PN_ASC :: FILE '{corrected_macrolib}' ;

SPHSRC := SPH_ASC ;
DMACROPN OPTIMPN := DSPH: SPHSRC :: EDIT 1 SPH PN ;
MACROPN := SPHSRC ;
MACROPN := MAC: MACROPN OPTIMPN ;
PN_ASC := MACROPN ;
END: ;
""",
        encoding="utf-8",
    )


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


if __name__ == "__main__":
    raise SystemExit(main())

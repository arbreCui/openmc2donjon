#!/usr/bin/env python3
"""Generate a DONJON assembly-wise k-eff input for the C5G7 converter case."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py


DEFAULT_OPENMC_DIR = Path("/Users/wen/openmc-workspace/c5g7_converter_test")
DEFAULT_MGXS = DEFAULT_OPENMC_DIR / "mgxs_library_assembly.h5"
DEFAULT_CPO = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_assembly.mcompo"
)
DEFAULT_OUT = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_assembly_keff.x2m"
)
PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--cpo", type=Path, default=DEFAULT_CPO)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dual-degree", type=int, default=1)
    parser.add_argument("--dual-quadrature", type=int, default=1)
    parser.add_argument("--max-outer", type=int, default=700)
    parser.add_argument("--spn-order", type=int, default=0)
    parser.add_argument("--scat-order", type=int, default=1)
    parser.add_argument("--no-grep", action="store_true")
    args = parser.parse_args()

    mix_names, mesh_dim = _read_mix_names(args.mgxs)
    text = _build_deck(
        mix_names,
        mesh_dim,
        args.cpo,
        args.dual_degree,
        args.dual_quadrature,
        args.max_outer,
        args.spn_order,
        args.scat_order,
        emit_grep=not args.no_grep,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(f"Wrote {args.out}")
    print(f"Assembly mesh: {mesh_dim} x {mesh_dim}, mixtures={len(mix_names)}")
    return 0


def _read_mix_names(path: Path) -> tuple[list[str], int]:
    with h5py.File(path, "r") as h5:
        names = list(h5["mixtures"])
        mesh_dim = int(h5.attrs.get("mesh_dimension", round(len(names) ** 0.5)))
    if mesh_dim * mesh_dim != len(names):
        raise ValueError(
            f"expected a square assembly mesh, got {len(names)} mixtures "
            f"and mesh_dimension={mesh_dim}"
        )
    return [str(name) for name in names], mesh_dim


def _build_deck(
    mix_names: list[str],
    mesh_dim: int,
    cpo_path: Path,
    dual_degree: int,
    dual_quadrature: int,
    max_outer: int,
    spn_order: int,
    scat_order: int,
    *,
    emit_grep: bool,
) -> str:
    nmix = len(mix_names)
    mesh_values = [i * ASSEMBLY_PITCH for i in range(mesh_dim + 1)]
    mix_map = list(range(1, nmix + 1))
    maxr = nmix + 100

    lines: list[str] = [
        "*----",
        "*  C5G7 OpenMC -> DONJON assembly-wise k-eff input.",
        "*  Each assembly-sized node consumes one homogenized OpenMC MGXS mixture.",
        f"*  Mesh: {mesh_dim} x {mesh_dim}, pitch={ASSEMBLY_PITCH:.8f} cm.",
        f"*  TRIVAT: DUAL {dual_degree} {dual_quadrature}.",
        f"*  SPN: {spn_order if spn_order else 'off'}.",
        "*----",
        "MODULE GEO: NCR: TRIVAT: TRIVAA: FLUD: "
        + ("GREP: " if emit_grep else "")
        + "END: ABORT: ;",
        "LINKED_LIST CPO MACRO GEOM TRACK SYS FLUX ;",
        "REAL keff ;",
        f"SEQ_ASCII CPO_ASC :: FILE '{cpo_path}' ;",
        "",
        "CPO := CPO_ASC ;",
        f"MACRO := NCR: CPO :: EDIT 1 MACRO NMIX {nmix}",
        "  COMPO CPO CPO",
    ]
    lines.extend(f"  MIX {i} USE ENDMIX (* {name} *)" for i, name in enumerate(mix_names, 1))
    lines.extend(
        [
            ";",
            "",
            f"GEOM := GEO: :: CAR2D {mesh_dim} {mesh_dim}",
            "  EDIT 0",
            "  X- REFL X+ VOID",
            "  Y- REFL Y+ VOID",
            "  MIX",
        ]
    )
    for row in _rows(mix_map, mesh_dim):
        lines.extend(_wrap_ints(row, per_line=mesh_dim, indent="  "))
    lines.append("  MESHX")
    lines.extend(_wrap_reals(mesh_values, per_line=4, indent="  "))
    lines.append("  MESHY")
    lines.extend(_wrap_reals(mesh_values, per_line=4, indent="  "))
    lines.extend(
        [
            ";",
            "",
            "TRACK := TRIVAT: GEOM ::",
            f"  TITLE 'C5G7 OpenMC converter assembly-wise smoke' EDIT 1 MAXR {maxr}",
            _trivat_options(dual_degree, dual_quadrature, spn_order, scat_order),
            "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
            f"FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE {max_outer} 1.E-6 ;",
        ]
    )
    if emit_grep:
        lines.extend(
            [
                "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
                "ECHO 'OPENMC2DONJON C5G7 ASSEMBLY K-EFFECTIVE' keff ;",
            ]
        )
    lines.append("END: ;")
    return "\n".join(lines) + "\n"


def _rows(values: list[int], width: int) -> list[list[int]]:
    return [values[i : i + width] for i in range(0, len(values), width)]


def _trivat_options(
    dual_degree: int, dual_quadrature: int, spn_order: int, scat_order: int
) -> str:
    parts = [f"DUAL {dual_degree} {dual_quadrature}"]
    if spn_order > 0:
        parts.append(f"SPN {spn_order} SCAT {scat_order}")
    return "  " + " ".join(parts) + " ;"


def _wrap_ints(values: list[int], *, per_line: int, indent: str) -> list[str]:
    return [
        indent + " ".join(str(value) for value in values[i : i + per_line])
        for i in range(0, len(values), per_line)
    ]


def _wrap_reals(values: list[float], *, per_line: int, indent: str) -> list[str]:
    return [
        indent + " ".join(f"{value:.8f}" for value in values[i : i + per_line])
        for i in range(0, len(values), per_line)
    ]


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a DRAGON5 MCCGT/MOC deck for the local C5G7 2D benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from generate_c5g7_keff_input import (
    MAT_ID_TO_NAME,
    PIN_RADIUS,
    PITCH,
    SIDE,
    find_material,
    load_openmc_geometry,
)
from openmc2donjon.multicompo import read_mgxs_hdf5
from openmc2donjon.scatter import dense_to_triplet


DEFAULT_OPENMC_DIR = Path("/Users/wen/openmc-workspace/c5g7_converter_test")
DEFAULT_MGXS = DEFAULT_OPENMC_DIR / "mgxs_library.h5"
DEFAULT_OUT = Path("/Users/wen/dragon-5.1/Dragon/data/openmc2donjon/c5g7_moc.x2m")
DEFAULT_EDITION_NAME = "C5G7REG"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openmc-dir", type=Path, default=DEFAULT_OPENMC_DIR)
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--angles", type=int, default=16)
    parser.add_argument("--density", type=float, default=12.0)
    parser.add_argument("--polar", type=int, default=3)
    parser.add_argument(
        "--track-anis",
        type=int,
        default=1,
        help="NXT flux anisotropy order. Use 2 when testing EDI_CURR/current edits.",
    )
    parser.add_argument("--mccgt-epsi", type=float, default=1.0e-5)
    parser.add_argument("--flux-epsi", type=float, default=1.0e-5)
    parser.add_argument(
        "--edition",
        choices=("none", "region"),
        default="none",
        help="Optionally append a region-mapped EDI: assembly homogenization step.",
    )
    parser.add_argument(
        "--assembly-mesh",
        type=int,
        default=3,
        help="Assembly mesh per side used by --edition region.",
    )
    parser.add_argument(
        "--edition-name",
        default=DEFAULT_EDITION_NAME,
        help="EDI SAVE ON directory name for --edition region.",
    )
    parser.add_argument(
        "--edi-currents",
        action="store_true",
        help="Request EDI_CURR in the region edition. Requires anisotropic MCCG flux unknowns.",
    )
    parser.add_argument(
        "--probe-currents",
        action="store_true",
        help="Append GREP probes for COURX-INTG/COURY-INTG after an EDI_CURR run.",
    )
    args = parser.parse_args()

    if args.assembly_mesh <= 0:
        parser.error("--assembly-mesh must be positive")
    if args.track_anis <= 0:
        parser.error("--track-anis must be positive")

    mixtures, energy_bounds = read_mgxs_hdf5(args.mgxs)
    mix_by_name = {mix.name: index for index, mix in enumerate(mixtures, start=1)}
    missing = sorted(set(MAT_ID_TO_NAME.values()) - set(mix_by_name))
    if missing:
        raise SystemExit(f"missing mixtures in MGXS HDF5: {', '.join(missing)}")

    mat_id_to_mix = {mat_id: mix_by_name[name] for mat_id, name in MAT_ID_TO_NAME.items()}
    pin_materials = _pin_materials(args.openmc_dir / "geometry.xml")

    text = _build_deck(
        mixtures,
        energy_bounds,
        pin_materials,
        mat_id_to_mix,
        angles=args.angles,
        density=args.density,
        polar=args.polar,
        track_anis=args.track_anis,
        mccgt_epsi=args.mccgt_epsi,
        flux_epsi=args.flux_epsi,
        edition=args.edition,
        assembly_mesh=args.assembly_mesh,
        edition_name=args.edition_name,
        edi_currents=args.edi_currents,
        probe_currents=args.probe_currents,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(f"Wrote {args.out}")
    print(f"Pin map: {len(pin_materials[0])} x {len(pin_materials)}")
    print(f"MOC tracking: TISO {args.angles} {args.density:g}, LCMD {args.polar}")
    print(f"NXT flux anisotropy: {args.track_anis}")
    print(f"MAC scattering moments: {mixtures[0].scatter_matrix.shape[0]}")
    if args.edition != "none":
        print(f"EDI edition: {args.edition}, assembly mesh {args.assembly_mesh} x {args.assembly_mesh}")
        if args.edition == "region":
            print(f"EDI region map entries: {len(_assembly_region_merge(pin_materials, args.assembly_mesh))}")
        if args.probe_currents:
            print("EDI current probe: enabled")
    return 0


def _pin_materials(geometry_xml: Path) -> list[list[int]]:
    surfaces, cells = load_openmc_geometry(geometry_xml)
    npins = round(SIDE / PITCH)
    if abs(npins * PITCH - SIDE) > 1.0e-8:
        raise ValueError("C5G7 side is not divisible by pin pitch")

    z = 0.5
    rows: list[list[int]] = []
    mirrored = 0
    for py in range(npins):
        y_donjon = (py + 0.5) * PITCH
        y_openmc = -y_donjon
        row: list[int] = []
        for px in range(npins):
            x = (px + 0.5) * PITCH
            material = find_material(x, y_openmc, z, surfaces, cells)
            if material is None:
                material = find_material(y_donjon, -x, z, surfaces, cells)
                if material is not None:
                    mirrored += 1
            if material is None:
                raise ValueError(f"pin center outside OpenMC cells: x={x}, y={y_openmc}")
            row.append(material)
        rows.append(row)
    if mirrored:
        print(f"Unfolded {mirrored} pins across the OpenMC diagonal symmetry.")
    return rows


def _build_deck(
    mixtures,
    energy_bounds: np.ndarray,
    pin_materials: list[list[int]],
    mat_id_to_mix: dict[int, int],
    *,
    angles: int,
    density: float,
    polar: int,
    track_anis: int,
    mccgt_epsi: float,
    flux_epsi: float,
    edition: str,
    assembly_mesh: int,
    edition_name: str,
    edi_currents: bool,
    probe_currents: bool,
) -> str:
    npins = len(pin_materials)
    if any(len(row) != npins for row in pin_materials):
        raise ValueError("pin material map must be square")
    if edition == "region" and npins % assembly_mesh != 0:
        raise ValueError(
            f"{npins} pins per side cannot be divided into {assembly_mesh} assembly bins"
        )
    mesh = [i * PITCH for i in range(npins + 1)]

    lines: list[str] = [
        "*----",
        "*  C5G7 2D quarter-core DRAGON5 MOC reference deck.",
        "*  Generated from the local OpenMC C5G7 XML pin map and MGXS HDF5.",
        "*----",
        "MODULE GEO: NXT: MCCGT: MAC: ASM: FLU: "
        + ("EDI: " if edition != "none" else "")
        + ("GREP: " if probe_currents else "")
        + "END: ;",
        "LINKED_LIST GEOM MACRO TRACK SYS FLUX"
        + (" EDITION" if edition != "none" else "")
        + (" BRANCH" if probe_currents else "")
        + " ;",
        *(
            ["REAL O2D_CURX O2D_CURY ;"]
            if probe_currents
            else []
        ),
        "SEQ_BINARY C5G7_TRK ;",
        "",
        _macrolib_block(mixtures, energy_bounds),
        "",
        f"GEOM := GEO: :: CAR2D {npins} {npins}",
        "  EDIT 0",
        "  X- REFL X+ VOID",
        "  Y- REFL Y+ VOID",
        "  CELL",
    ]
    for row in pin_materials:
        lines.extend(_wrap_strings([_cell_name(mat_id) for mat_id in row], per_line=12))
    lines.append("  MESHX")
    lines.extend(_wrap_reals(mesh, per_line=8, indent="  "))
    lines.append("  MESHY")
    lines.extend(_wrap_reals(mesh, per_line=8, indent="  "))
    lines.extend(_cell_definitions(mat_id_to_mix))
    lines.extend(
        [
            ";",
            "",
            "TRACK C5G7_TRK := NXT: GEOM ::",
            "  EDIT 1",
            "  MAXR 20000",
            *([f"  ANIS {track_anis}"] if track_anis > 1 else []),
            f"  ALLG TISO {angles} {density:.8E}",
            ";",
            "",
            "TRACK := MCCGT: TRACK C5G7_TRK GEOM ::",
            "  EDIT 2",
            f"  LCMD {polar} AAC 150 TMT SCR 0 EPSI {mccgt_epsi:.6E}",
            "  MAXI 1 KRYL 0 HDD 0.0",
            ";",
            "",
            "SYS := ASM: MACRO TRACK C5G7_TRK :: ARM EDIT 1 ;",
            "",
            "FLUX := FLU: MACRO SYS TRACK C5G7_TRK ::",
            f"  EDIT 1 TYPE K EXTE 100 {flux_epsi:.6E}",
            ";",
        ]
    )
    if edition == "region":
        lines.extend(
            _edi_region_block(
                edition_name,
                _assembly_region_merge(pin_materials, assembly_mesh),
                edi_currents,
            )
        )
        if probe_currents:
            if not edi_currents:
                raise ValueError("--probe-currents requires --edi-currents")
            lines.extend(_edi_current_probe_block(edition_name))
    lines.extend(
        [
            "",
            'ECHO "openmc2donjon DRAGON C5G7 MOC completed" ;',
            "END: ;",
        ]
    )
    return "\n".join(lines) + "\n"


def _macrolib_block(mixtures, energy_bounds: np.ndarray) -> str:
    energy_desc = np.asarray(energy_bounds, dtype=float)[::-1]
    anis = mixtures[0].scatter_matrix.shape[0]
    lines = [
        "MACRO := MAC: ::",
        f"  EDIT 1 NGRO {mixtures[0].ngroups} NMIX {len(mixtures)} NIFI 1 ANIS {anis}",
        "  CTRA NONE",
        "  ENER",
        *_wrap_reals(energy_desc, per_line=4, indent="    "),
        "  READ INPUT",
    ]
    for index, mix in enumerate(mixtures, start=1):
        lines.extend(_mixture_xs(index, mix))
    lines.append(";")
    return "\n".join(lines)


def _mixture_xs(index: int, mix) -> list[str]:
    lines = [
        f"  MIX {index} (* {mix.name} *)",
        "    TOTAL",
        *_wrap_reals(mix.total, per_line=4, indent="      "),
    ]
    if mix.fissionable:
        lines.extend(
            [
                "    NUSIGF",
                *_wrap_reals(mix.nu_fission, per_line=4, indent="      "),
                "    CHI",
                *_wrap_reals(mix.chi, per_line=4, indent="      "),
            ]
        )
    lines.append("    SCAT")
    for moment in mix.scatter_matrix:
        triplet = dense_to_triplet(moment)
        for to_group, (njjs, ijjs) in enumerate(
            zip(triplet.njjs, triplet.ijjs, strict=True), start=1
        ):
            start = sum(int(n) for n in triplet.njjs[: to_group - 1])
            stop = start + int(njjs)
            values = triplet.scat[start:stop]
            payload = [f"{int(njjs)}", f"{int(ijjs)}"]
            payload.extend(f"{value:.8E}" for value in values)
            lines.append("      " + " ".join(payload))
    return lines


def _cell_definitions(mat_id_to_mix: dict[int, int]) -> list[str]:
    mod_mix = mat_id_to_mix[8]
    lines = [
        "",
        "  ::: MOD := GEO: CAR2D 1 1",
        f"    MESHX 0.0 {PITCH:.8f}",
        f"    MESHY 0.0 {PITCH:.8f}",
        f"    MIX {mod_mix}",
        "  ;",
    ]
    for mat_id in MAT_ID_TO_NAME:
        if mat_id == 8:
            continue
        mix = mat_id_to_mix[mat_id]
        lines.extend(
            [
                "",
                f"  ::: {_cell_name(mat_id)} := GEO: CARCEL 1",
                f"    RADIUS 0.0 {PIN_RADIUS:.8f}",
                f"    MESHX 0.0 {PITCH:.8f}",
                f"    MESHY 0.0 {PITCH:.8f}",
                f"    MIX {mix} {mod_mix}",
                "  ;",
            ]
        )
    return lines


def _edi_region_block(
    edition_name: str, region_merge: list[int], edi_currents: bool
) -> list[str]:
    lines = [
        "",
        "*  Region-wise assembly merge: each pin region is mapped to a 3x3 assembly bin.",
        "EDITION := EDI: MACRO TRACK FLUX GEOM ::",
        "  EDIT 2 UPS SAVE ON " + _quote_dragon_name(edition_name),
        "  MERGE REGION",
    ]
    lines.extend(_wrap_ints(region_merge, per_line=18, indent="  "))
    lines.append("  COND NONE")
    if edi_currents:
        lines.append("  EDI_CURR")
    lines.append(";")
    return lines


def _edi_current_probe_block(edition_name: str) -> list[str]:
    return [
        "",
        "*  Force a readback of current records so the listing proves they exist.",
        "BRANCH := EDITION :: STEP UP "
        + _quote_dragon_name(edition_name)
        + " STEP UP MACROLIB STEP UP GROUP STEP AT 1 ;",
        "GREP: BRANCH :: GETVAL 'COURX-INTG' 1 >>O2D_CURX<< ;",
        "GREP: BRANCH :: GETVAL 'COURY-INTG' 1 >>O2D_CURY<< ;",
        'ECHO "openmc2donjon EDI_CURR probe COURX=" O2D_CURX " COURY=" O2D_CURY ;',
    ]


def _assembly_region_merge(
    pin_materials: list[list[int]], assembly_mesh: int
) -> list[int]:
    npins = len(pin_materials)
    if npins % assembly_mesh != 0:
        raise ValueError(
            f"{npins} pins per side cannot be divided into {assembly_mesh} assembly bins"
        )
    pins_per_assembly = npins // assembly_mesh
    entries: list[int] = []
    for y_index, row in enumerate(pin_materials):
        assembly_y = y_index // pins_per_assembly
        for x_index, mat_id in enumerate(row):
            assembly_x = x_index // pins_per_assembly
            assembly_id = assembly_y * assembly_mesh + assembly_x + 1
            entries.append(assembly_id)
            if mat_id != 8:
                entries.append(assembly_id)
    return entries


def _quote_dragon_name(name: str) -> str:
    if len(name) > 12:
        raise ValueError("DRAGON LCM directory names are limited to 12 characters")
    return "'" + name.replace("'", "''") + "'"


def _cell_name(mat_id: int) -> str:
    if mat_id == 8:
        return "MOD"
    return {
        1: "UO2",
        2: "M43",
        3: "M70",
        4: "M87",
        5: "FC",
        6: "GT",
    }[mat_id]


def _wrap_strings(values: list[str], *, per_line: int) -> list[str]:
    return [
        "  " + " ".join(values[i : i + per_line])
        for i in range(0, len(values), per_line)
    ]


def _wrap_ints(values: list[int], *, per_line: int, indent: str) -> list[str]:
    return [
        indent + " ".join(str(value) for value in values[i : i + per_line])
        for i in range(0, len(values), per_line)
    ]


def _wrap_reals(values, *, per_line: int, indent: str) -> list[str]:
    real_values = [float(value) for value in values]
    return [
        indent + " ".join(f"{value:.8E}" for value in real_values[i : i + per_line])
        for i in range(0, len(real_values), per_line)
    ]


if __name__ == "__main__":
    raise SystemExit(main())

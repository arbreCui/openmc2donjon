#!/usr/bin/env python3
"""Generate a DONJON k-eff smoke input for the OpenMC C5G7 converter case.

The OpenMC C5G7 XML used for converter development is pin-heterogeneous and
expanded into explicit cells.  This script samples that geometry onto a fine
Cartesian mesh and writes a DONJON ``CAR2D`` diffusion/SPN input using the
converter-produced MULTICOMPO.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

DEFAULT_OPENMC_DIR = Path("/Users/wen/openmc-workspace/c5g7_converter_test")
DEFAULT_MGXS = DEFAULT_OPENMC_DIR / "mgxs_library.h5"
DEFAULT_CPO = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_ingest.mcompo.txt"
)
DEFAULT_OUT = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_keff_diffusion.x2m"
)

PITCH = 1.26
SIDE = 64.26
PIN_RADIUS = 0.54
MAT_ID_TO_NAME = {
    1: "UO2",
    2: "MOX43",
    3: "MOX70",
    4: "MOX87",
    5: "FC",
    6: "GT",
    8: "MOD",
}


@dataclass(frozen=True)
class Surface:
    kind: str
    coeffs: tuple[float, ...]

    def value(self, x: float, y: float, z: float) -> float:
        if self.kind == "z-cylinder":
            x0, y0, radius = self.coeffs
            return (x - x0) ** 2 + (y - y0) ** 2 - radius**2
        if self.kind == "z-plane":
            return z - self.coeffs[0]
        if self.kind == "plane":
            a, b, c, d = self.coeffs
            return a * x + b * y + c * z - d
        raise ValueError(f"unsupported OpenMC surface type {self.kind!r}")


@dataclass(frozen=True)
class Cell:
    material_id: int
    region: "Node"


class Node:
    def contains(self, x: float, y: float, z: float, surfaces: dict[int, Surface]) -> bool:
        raise NotImplementedError


@dataclass(frozen=True)
class Halfspace(Node):
    surface_id: int
    sense: int

    def contains(self, x: float, y: float, z: float, surfaces: dict[int, Surface]) -> bool:
        value = surfaces[self.surface_id].value(x, y, z)
        return value >= -1.0e-10 if self.sense > 0 else value <= 1.0e-10


@dataclass(frozen=True)
class And(Node):
    children: tuple[Node, ...]

    def contains(self, x: float, y: float, z: float, surfaces: dict[int, Surface]) -> bool:
        return all(child.contains(x, y, z, surfaces) for child in self.children)


@dataclass(frozen=True)
class Or(Node):
    children: tuple[Node, ...]

    def contains(self, x: float, y: float, z: float, surfaces: dict[int, Surface]) -> bool:
        return any(child.contains(x, y, z, surfaces) for child in self.children)


class RegionParser:
    _TOKEN_RE = re.compile(r"-?\d+|[()|]")

    def __init__(self, text: str) -> None:
        self.tokens = self._TOKEN_RE.findall(text)
        self.i = 0

    def parse(self) -> Node:
        node = self._parse_or()
        if self.i != len(self.tokens):
            raise ValueError(f"unparsed region tokens remain: {self.tokens[self.i:]}")
        return node

    def _parse_or(self) -> Node:
        nodes = [self._parse_and()]
        while self._peek() == "|":
            self.i += 1
            nodes.append(self._parse_and())
        return nodes[0] if len(nodes) == 1 else Or(tuple(nodes))

    def _parse_and(self) -> Node:
        nodes: list[Node] = []
        while self.i < len(self.tokens) and self._peek() not in {")", "|"}:
            nodes.append(self._parse_factor())
        if not nodes:
            raise ValueError("empty intersection in OpenMC region expression")
        return nodes[0] if len(nodes) == 1 else And(tuple(nodes))

    def _parse_factor(self) -> Node:
        token = self._peek()
        if token == "(":
            self.i += 1
            node = self._parse_or()
            if self._peek() != ")":
                raise ValueError("missing ')' in OpenMC region expression")
            self.i += 1
            return node
        self.i += 1
        value = int(token)
        return Halfspace(abs(value), 1 if value > 0 else -1)

    def _peek(self) -> str | None:
        if self.i >= len(self.tokens):
            return None
        return self.tokens[self.i]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openmc-dir", type=Path, default=DEFAULT_OPENMC_DIR)
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--cpo", type=Path, default=DEFAULT_CPO)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--subdiv",
        type=int,
        default=2,
        help="Cartesian subcells per 1.26 cm C5G7 pin pitch.",
    )
    parser.add_argument(
        "--sampling",
        choices=("pin", "region"),
        default="pin",
        help="Use pin-center XML layout plus analytic pin radii, or sample every region.",
    )
    parser.add_argument(
        "--dual-degree",
        type=int,
        default=3,
        help="TRIVAT mixed-dual finite-element degree.",
    )
    parser.add_argument(
        "--dual-quadrature",
        type=int,
        default=1,
        help="TRIVAT mixed-dual quadrature type.",
    )
    parser.add_argument(
        "--max-outer",
        type=int,
        default=500,
        help="Maximum FLUD outer iterations.",
    )
    parser.add_argument(
        "--spn-order",
        type=int,
        default=0,
        help="Optional TRIVAT SPN order, for example 5. Zero means diffusion.",
    )
    parser.add_argument(
        "--scat-order",
        type=int,
        default=1,
        help="TRIVAT SCAT option used together with SPN.",
    )
    parser.add_argument(
        "--no-grep",
        action="store_true",
        help="Skip GREP/ECHO extraction and leave k-effective in the FLUD listing.",
    )
    args = parser.parse_args()

    if args.subdiv <= 0:
        raise SystemExit("--subdiv must be positive")

    surfaces, cells = load_openmc_geometry(args.openmc_dir / "geometry.xml")
    mix_by_name = read_mix_names_from_mgxs(args.mgxs)
    mat_id_to_mix = {
        mat_id: mix_by_name[name] for mat_id, name in MAT_ID_TO_NAME.items()
    }
    if args.sampling == "pin":
        mesh = sample_pin_geometry(surfaces, cells, mat_id_to_mix, args.subdiv)
    else:
        mesh = sample_region_geometry(surfaces, cells, mat_id_to_mix, args.subdiv)
    write_x2m(
        args.out,
        args.cpo,
        mesh,
        args.subdiv,
        args.dual_degree,
        args.dual_quadrature,
        args.max_outer,
        args.spn_order,
        args.scat_order,
        not args.no_grep,
    )

    nx = len(mesh[0])
    ny = len(mesh)
    counts: dict[int, int] = {}
    for row in mesh:
        for mix in row:
            counts[mix] = counts.get(mix, 0) + 1
    print(f"Wrote {args.out}")
    print(f"Mesh: {nx} x {ny} Cartesian cells, subdiv={args.subdiv}")
    print("Mix cell counts:", " ".join(f"{mix}:{counts[mix]}" for mix in sorted(counts)))
    return 0


def load_openmc_geometry(path: Path) -> tuple[dict[int, Surface], list[Cell]]:
    root = ET.parse(path).getroot()
    surfaces: dict[int, Surface] = {}
    for elem in root.findall("surface"):
        sid = int(elem.attrib["id"])
        coeffs = tuple(float(x) for x in elem.attrib["coeffs"].split())
        surfaces[sid] = Surface(elem.attrib["type"], coeffs)

    cells: list[Cell] = []
    for elem in root.findall("cell"):
        material = elem.attrib.get("material")
        region = elem.attrib.get("region")
        if material is None or region is None:
            continue
        cells.append(Cell(int(material), RegionParser(region).parse()))
    return surfaces, cells


def read_mix_names_from_mgxs(path: Path) -> dict[str, int]:
    import h5py

    with h5py.File(path, "r") as h5:
        names = list(h5["mixtures"])
    mix_by_name = {str(name): index for index, name in enumerate(names, start=1)}
    missing = sorted(set(MAT_ID_TO_NAME.values()) - set(mix_by_name))
    if missing:
        raise ValueError(f"missing MGXS mixtures: {', '.join(missing)}")
    return mix_by_name


def sample_pin_geometry(
    surfaces: dict[int, Surface],
    cells: list[Cell],
    mat_id_to_mix: dict[int, int],
    subdiv: int,
) -> list[list[int]]:
    npins = round(SIDE / PITCH)
    if abs(npins * PITCH - SIDE) > 1.0e-8:
        raise ValueError("SIDE is not divisible by the C5G7 pin pitch")

    z = 0.5
    pin_materials: list[list[int]] = []
    mirrored = 0
    misses: list[tuple[float, float]] = []
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
                row.append(8)
                if len(misses) < 10:
                    misses.append((x, y_openmc))
            else:
                row.append(material)
        pin_materials.append(row)
    if misses:
        shown = ", ".join(f"({x:.3f},{y:.3f})" for x, y in misses)
        raise ValueError(f"pin centers outside OpenMC cells: {shown}")
    if mirrored:
        print(f"Unfolded {mirrored} pins across the OpenMC diagonal symmetry.")

    dx = PITCH / subdiv
    mod_mix = mat_id_to_mix[8]
    mesh: list[list[int]] = []
    for py in range(npins):
        for sy in range(subdiv):
            y_local = (sy + 0.5) * dx - PITCH / 2.0
            row: list[int] = []
            for px in range(npins):
                material = pin_materials[py][px]
                for sx in range(subdiv):
                    x_local = (sx + 0.5) * dx - PITCH / 2.0
                    in_pin = x_local**2 + y_local**2 <= PIN_RADIUS**2
                    if material == 8 or not in_pin:
                        row.append(mod_mix)
                    else:
                        row.append(mat_id_to_mix[material])
            mesh.append(row)
    return mesh


def sample_region_geometry(
    surfaces: dict[int, Surface],
    cells: list[Cell],
    mat_id_to_mix: dict[int, int],
    subdiv: int,
) -> list[list[int]]:
    n = round(SIDE / (PITCH / subdiv))
    if abs(n * (PITCH / subdiv) - SIDE) > 1.0e-8:
        raise ValueError("SIDE is not divisible by the requested mesh spacing")
    dx = SIDE / n
    z = 0.5
    mesh: list[list[int]] = []
    misses: list[tuple[float, float]] = []
    mirrored = 0
    for j in range(n):
        y_donjon = (j + 0.5) * dx
        y_openmc = -y_donjon
        row: list[int] = []
        for i in range(n):
            x = (i + 0.5) * dx
            material = find_material(x, y_openmc, z, surfaces, cells)
            if material is None:
                # The OpenMC C5G7 XML is stored as a diagonal-symmetry wedge.
                # Unfold the missing half of the quarter core by reflecting
                # across the x == -y OpenMC diagonal.
                material = find_material(y_donjon, -x, z, surfaces, cells)
                if material is not None:
                    mirrored += 1
            if material is None:
                row.append(0)
                if len(misses) < 10:
                    misses.append((x, y_openmc))
            else:
                row.append(mat_id_to_mix[material])
        mesh.append(row)
    if misses:
        shown = ", ".join(f"({x:.3f},{y:.3f})" for x, y in misses)
        raise ValueError(f"sample points outside OpenMC cells: {shown}")
    if mirrored:
        print(f"Unfolded {mirrored} cells across the OpenMC diagonal symmetry.")
    return mesh


def find_material(
    x: float,
    y: float,
    z: float,
    surfaces: dict[int, Surface],
    cells: list[Cell],
) -> int | None:
    for cell in cells:
        if cell.region.contains(x, y, z, surfaces):
            return cell.material_id
    return None


def write_x2m(
    path: Path,
    cpo_path: Path,
    mesh: list[list[int]],
    subdiv: int,
    dual_degree: int,
    dual_quadrature: int,
    max_outer: int,
    spn_order: int,
    scat_order: int,
    emit_grep: bool,
) -> None:
    nx = len(mesh[0])
    ny = len(mesh)
    if nx != ny:
        raise ValueError("C5G7 smoke mesh is expected to be square")

    mesh_values = [i * SIDE / nx for i in range(nx + 1)]
    maxr = nx * ny + 100

    lines: list[str] = [
        "*----",
        "*  C5G7 OpenMC -> DONJON k-eff smoke input.",
        "*  Geometry is sampled from OpenMC XML onto a fine CAR2D mesh.",
        f"*  Mesh: {nx} x {ny}, {subdiv} subcells per 1.26 cm pitch.",
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
        "MACRO := NCR: CPO :: EDIT 1 MACRO NMIX 7",
        "  COMPO CPO CPO",
    ]
    lines.extend(f"  MIX {i} USE ENDMIX" for i in range(1, 8))
    lines.extend(
        [
            ";",
            "",
            f"GEOM := GEO: :: CAR2D {nx} {ny}",
            "  EDIT 0",
            "  X- REFL X+ VOID",
            "  Y- REFL Y+ VOID",
            "  MIX",
        ]
    )
    for row in mesh:
        lines.extend(_wrap_ints(row, per_line=24, indent="  "))
    lines.append("  MESHX")
    lines.extend(_wrap_reals(mesh_values, per_line=6, indent="  "))
    lines.append("  MESHY")
    lines.extend(_wrap_reals(mesh_values, per_line=6, indent="  "))
    lines.extend(
        [
            ";",
            "",
            "TRACK := TRIVAT: GEOM ::",
            f"  TITLE 'C5G7 OpenMC converter diffusion smoke' EDIT 1 MAXR {maxr}",
            _trivat_options(dual_degree, dual_quadrature, spn_order, scat_order),
            "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
            f"FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE {max_outer} 1.E-6 ;",
        ]
    )
    if emit_grep:
        lines.extend(
            [
                "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
                "ECHO 'OPENMC2DONJON C5G7 DIFFUSION K-EFFECTIVE' keff ;",
            ]
        )
    lines.append("END: ;")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


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


def _trivat_options(
    dual_degree: int,
    dual_quadrature: int,
    spn_order: int,
    scat_order: int,
) -> str:
    text = f"  DUAL {dual_degree} {dual_quadrature}"
    if spn_order:
        text += f" SPN {spn_order} SCAT {scat_order}"
    return text + " ;"


if __name__ == "__main__":
    raise SystemExit(main())

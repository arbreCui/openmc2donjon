"""C5G7 recipe for the production OpenMC statepoint export workflow.

This recipe is intentionally case-specific.  It lets the generic
``openmc2donjon-export --recipe`` path reproduce the accepted C5G7 HDF5 handoff
from a saved OpenMC statepoint.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import openmc
import openmc.mgxs as mgxs

from openmc2donjon import DomainExportSpec


DEFAULT_C5G7_DIR = Path("/Users/wen/openmc-workspace/c5g7_converter_test")
PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH
SIDE = 3 * ASSEMBLY_PITCH
C5G7_7G_BOUNDS = [
    1.0e-5,
    5.17947468e-4,
    2.68269580e-2,
    1.38949549e0,
    7.19685673e1,
    3.72759372e3,
    1.93069773e5,
    1.0e7,
]


def build_library():
    previous_cwd = Path.cwd()
    os.chdir(_c5g7_dir())
    try:
        materials = openmc.Materials.from_xml("materials.xml")
        for material in materials:
            if material._macroscopic is None:
                material.add_macroscopic(material.name)
        geometry = openmc.Geometry.from_xml("geometry.xml", materials=materials)

        library = mgxs.Library(geometry)
        library.energy_groups = mgxs.EnergyGroups(C5G7_7G_BOUNDS)
        # The accepted C5G7 statepoint was generated with OpenMC's
        # consistent nu-scatter matrix tally set. Keep that choice explicit so
        # the recipe/statepoint parity check remains a true locked-baseline
        # reproduction instead of silently switching scatter definitions.
        library.mgxs_types = [
            "total",
            "absorption",
            "fission",
            "nu-fission",
            "chi",
            "consistent nu-scatter matrix",
        ]
        if _domain_mode() == "material":
            library.domain_type = "material"
            library.domains = list(geometry.get_all_materials().values())
        else:
            mesh = openmc.RegularMesh(mesh_id=1001, name="C5G7 assembly mesh")
            mesh.dimension = (_assembly_mesh(), _assembly_mesh(), 1)
            mesh.lower_left = (0.0, -SIDE, 0.0)
            mesh.upper_right = (SIDE, 0.0, 1.0)
            library.domain_type = "mesh"
            library.domains = [mesh]
        library.by_nuclide = False
        library.legendre_order = _legendre_order()
        library.build_library()

        tallies = openmc.Tallies()
        library.add_to_tallies_file(tallies, merge=True)
        return library
    finally:
        os.chdir(previous_cwd)


def domain_specs(library):
    if _domain_mode() == "material":
        return None
    return _assembly_specs(library.domains[0], _assembly_mesh())


def scatter_mgxs_type():
    return "consistent nu-scatter matrix"


def root_attrs():
    attrs = {
        "scatter_axes": "moment,G_in,G_out",
        "domain_mode": _domain_mode(),
    }
    if _domain_mode() == "assembly":
        attrs.update(
            {
                "mesh_dimension": _assembly_mesh(),
                "mesh_lower_left": np.asarray((0.0, -SIDE, 0.0), dtype=float),
                "mesh_upper_right": np.asarray((SIDE, 0.0, 1.0), dtype=float),
            }
        )
    return attrs


def postprocess_hdf5(output_path, library):
    if getattr(library, "legendre_order", 0) > 0:
        _add_p1_transport_total(Path(output_path))
    adf_source = os.environ.get("C5G7_ADF_SOURCE")
    if adf_source:
        _copy_adf_payload(Path(adf_source), Path(output_path))


def _assembly_specs(domain: object, assembly_mesh: int) -> list[DomainExportSpec]:
    full_volume = (SIDE / assembly_mesh) ** 2
    specs = []
    for y_index in range(assembly_mesh):
        for x_index in range(assembly_mesh):
            source_x = max(x_index, y_index)
            source_y = min(x_index, y_index)
            subdomain = (source_x + 1, assembly_mesh - source_y, 1)
            specs.append(
                DomainExportSpec(
                    domain=domain,
                    name=f"ASM_Y{y_index + 1:02d}_X{x_index + 1:02d}",
                    xs_kwargs={"subdomains": [subdomain]},
                    volume=full_volume,
                    attrs={
                        "mesh_index": np.asarray(
                            (x_index + 1, y_index + 1, 1),
                            dtype=np.int32,
                        ),
                        "source_subdomain": np.asarray(subdomain, dtype=np.int32),
                    },
                )
            )
    return specs


def _add_p1_transport_total(output: Path) -> None:
    import h5py

    with h5py.File(output, "r+") as h5:
        for name, group in h5["mixtures"].items():
            if "transport_total" in group:
                continue
            scatter = np.asarray(group["scatter_matrix"][:], dtype=float)
            if scatter.shape[0] <= 1:
                continue
            transport_total = np.asarray(group["total"][:], dtype=float) - scatter[1].sum(
                axis=1
            )
            if np.any(transport_total <= 0.0):
                raise ValueError(
                    f"non-positive transport total in domain {name}: {transport_total}"
                )
            group.create_dataset("transport_total", data=transport_total)


def _copy_adf_payload(source: Path, output: Path) -> None:
    import h5py

    with h5py.File(source, "r") as src, h5py.File(output, "r+") as dst:
        for key, value in src.attrs.items():
            if str(key).startswith("adf"):
                dst.attrs[key] = value

        src_mixtures = src["mixtures"]
        dst_mixtures = dst["mixtures"]
        for name, src_group in src_mixtures.items():
            if name not in dst_mixtures:
                raise ValueError(f"ADF source mixture {name!r} is missing in output")
            if "adf" not in src_group:
                continue
            dst_group = dst_mixtures[name]
            if "adf" in dst_group:
                del dst_group["adf"]
            dataset = dst_group.create_dataset("adf", data=src_group["adf"][:])
            for attr_key, attr_value in src_group["adf"].attrs.items():
                dataset.attrs[attr_key] = attr_value


def _c5g7_dir() -> Path:
    return Path(os.environ.get("C5G7_DIR", DEFAULT_C5G7_DIR)).resolve()


def _domain_mode() -> str:
    value = os.environ.get("C5G7_DOMAIN_MODE", "assembly")
    if value not in {"assembly", "material"}:
        raise ValueError("C5G7_DOMAIN_MODE must be assembly or material")
    return value


def _assembly_mesh() -> int:
    value = int(os.environ.get("C5G7_ASSEMBLY_MESH", "3"))
    if value <= 0:
        raise ValueError("C5G7_ASSEMBLY_MESH must be positive")
    return value


def _legendre_order() -> int:
    value = int(os.environ.get("C5G7_LEGENDRE_ORDER", "1"))
    if value < 0:
        raise ValueError("C5G7_LEGENDRE_ORDER must be non-negative")
    return value

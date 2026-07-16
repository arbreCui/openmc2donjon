"""Editable OpenMC MGXS export recipe for openmc2donjon.

Copy this file into an OpenMC case directory and edit the settings below. The
recipe is consumed by:

    openmc2donjon-from-openmc --recipe export_recipe.py --statepoint statepoint.h5
"""

from __future__ import annotations

from pathlib import Path

import openmc
import openmc.mgxs as mgxs

from openmc2donjon import DomainExportSpec

# Edit these paths for the case. Relative paths are resolved from this file.
CASE_DIR = Path(__file__).resolve().parent
MATERIALS_XML = CASE_DIR / "materials.xml"
GEOMETRY_XML = CASE_DIR / "geometry.xml"
SETTINGS_XML = CASE_DIR / "settings.xml"
TALLIES_XML = CASE_DIR / "tallies.xml"

# Add local Python modules, CAD/mesh sources, or other model-defining files
# imported by this recipe. Their content hashes become part of the portable
# model fingerprint and the managed research bundle.
EXTRA_MODEL_SOURCES: dict[str, Path] = {}

# OpenMC does not necessarily store launcher topology in a statepoint. Set
# these only from the actual run receipt; do not infer them from the current
# shell when exporting an old statepoint.
RUN_THREADS: int | None = None
RUN_MPI_RANKS: int | None = None

# Energy boundaries must be ascending in eV. Replace this with the group
# structure used for the OpenMC MGXS run.
ENERGY_BOUNDS_EV = [
    1.0e-5,
    6.25e-1,
    5.53e3,
    8.21e5,
    2.0e7,
]
ENERGY_GROUP_STRUCTURE = "EDIT-ME-4g"

# The production converter path maps each exported domain or subdomain to one
# DONJON mixture. For assembly-wise output, make these domains assemblies.
DOMAIN_TYPE = "cell"
DOMAIN_MODE = "assembly"
DOMAIN_ID_WHITELIST: set[int] | None = None
DOMAIN_NAME_PREFIX = "ASM"

# For strict production dry-runs, provide explicit homogenized domain volumes.
# Fill either a per-domain table or one default value. If both are left unset,
# openmc2donjon falls back to domain.volume when OpenMC provides it; otherwise
# strict dry-run reports a volume warning.
DOMAIN_VOLUME_BY_ID_CM3: dict[int, float] = {}
DEFAULT_DOMAIN_VOLUME_CM3: float | None = None

LEGENDRE_ORDER = 1
MGXS_TYPES = [
    "total",
    "absorption",
    "fission",
    "kappa-fission",
    "nu-fission",
    "chi",
    "scatter matrix",
    "transport",
]


def build_library():
    materials = openmc.Materials.from_xml(str(MATERIALS_XML))
    geometry = openmc.Geometry.from_xml(str(GEOMETRY_XML), materials=materials)

    library = mgxs.Library(geometry)
    library.energy_groups = mgxs.EnergyGroups(ENERGY_BOUNDS_EV)
    library.mgxs_types = MGXS_TYPES
    library.domain_type = DOMAIN_TYPE
    library.domains = select_domains(geometry)
    library.by_nuclide = False
    library.legendre_order = LEGENDRE_ORDER

    library.build_library()
    return library


def select_domains(geometry):
    if DOMAIN_TYPE == "cell":
        domains = list(geometry.get_all_cells().values())
    elif DOMAIN_TYPE == "material":
        domains = list(geometry.get_all_materials().values())
    else:
        raise ValueError(f"edit select_domains() for DOMAIN_TYPE={DOMAIN_TYPE!r}")

    if DOMAIN_ID_WHITELIST is not None:
        domains = [domain for domain in domains if domain.id in DOMAIN_ID_WHITELIST]
    if not domains:
        raise ValueError("no MGXS domains selected")
    return domains


def domain_names(library):
    return {
        domain.id: stable_domain_name(domain, index)
        for index, domain in enumerate(library.domains, start=1)
    }


def domain_specs(library):
    return [
        DomainExportSpec(
            domain=domain,
            name=stable_domain_name(domain, index),
            volume=domain_volume_cm3(domain),
            attrs={
                "source_domain_id": int(domain.id),
                "source_domain_type": DOMAIN_TYPE,
            },
        )
        for index, domain in enumerate(library.domains, start=1)
    ]


def stable_domain_name(domain, index: int) -> str:
    raw_name = getattr(domain, "name", "") or f"{DOMAIN_TYPE}_{domain.id}"
    cleaned = "".join(
        char if char.isalnum() else "_"
        for char in raw_name.upper()
    ).strip("_")
    if not cleaned:
        cleaned = f"{DOMAIN_TYPE.upper()}_{domain.id}"
    return f"{DOMAIN_NAME_PREFIX}_{index:03d}_{cleaned[:20]}"


def domain_volume_cm3(domain) -> float | None:
    if domain.id in DOMAIN_VOLUME_BY_ID_CM3:
        return float(DOMAIN_VOLUME_BY_ID_CM3[domain.id])
    if DEFAULT_DOMAIN_VOLUME_CM3 is not None:
        return float(DEFAULT_DOMAIN_VOLUME_CM3)
    return None


def load_statepoint(library, statepoint_path):
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        library.load_from_statepoint(statepoint)
        keff = getattr(statepoint, "keff", None)
        if keff is not None:
            print(f"OpenMC keff = {keff}")


def provenance_files():
    """Declare every small source file needed to reconstruct the fine model."""

    return {
        "materials": MATERIALS_XML,
        "geometry": GEOMETRY_XML,
        "settings": SETTINGS_XML,
        "tallies": TALLIES_XML,
        **EXTRA_MODEL_SOURCES,
    }


def provenance_metadata():
    """Record launcher details that are not reliably stored by OpenMC."""

    return {
        # Set this true only after provenance_files() includes every imported
        # Python module, CAD/DAGMC/mesh file, external source, weight window,
        # and other file that can change the OpenMC model or tallies.
        "input_closure_complete": True,
        "threads": RUN_THREADS,
        "mpi_ranks": RUN_MPI_RANKS,
    }


def extra_tallies(library):
    """Return case-specific non-MGXS tallies to include in tallies.xml.

    Leave this empty for a plain MGXS export.  Add surface-current or other
    auxiliary tallies here if they are needed for ADF/DF or diagnostics.
    """

    return []


def root_attrs():
    return {
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "spatial_mapping": "one exported OpenMC MGXS domain -> one DONJON mixture",
        "energy_group_count": len(ENERGY_BOUNDS_EV) - 1,
        "legendre_order": LEGENDRE_ORDER,
        "recipe": Path(__file__).name,
    }


# For mesh or other explicit subdomain exports, replace domain_specs(library)
# with a subdomain mapping. Each returned DomainExportSpec becomes one DONJON
# mixture.
#
# def domain_specs(library):
#     mesh = library.domains[0]
#     return [
#         DomainExportSpec(
#             domain=mesh,
#             name="ASM_Y01_X01",
#             xs_kwargs={"subdomains": [(1, 1, 1)]},
#             volume=1.0,
#             attrs={"mesh_index": [1, 1, 1]},
#         ),
#     ]

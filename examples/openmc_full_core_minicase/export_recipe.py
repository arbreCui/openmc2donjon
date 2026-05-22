"""openmc2donjon recipe for the full-core assembly-wise minicase.

Set ``OPENMC2DONJON_FULL_CORE_MINICASE_DIR`` to the directory containing the
generated OpenMC XML files before running ``openmc2donjon-from-openmc``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from openmc2donjon import DomainExportSpec


def _load_full_core_module():
    path = Path(__file__).with_name("full_core_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_full_core_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import full-core model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_full_core = _load_full_core_module()


def build_library():
    return _full_core.build_library(case_dir=_full_core.default_case_dir())


def domain_specs(library):
    names = _full_core.domain_names(library)
    return [
        DomainExportSpec(
            domain=domain,
            name=names[int(domain.id)],
            volume=float(_full_core.DOMAIN_VOLUME_BY_ID[int(domain.id)]),
            attrs=_domain_attrs(int(domain.id)),
        )
        for domain in library.domains
    ]


def _domain_attrs(domain_id):
    assembly = _full_core.DOMAIN_BY_ID[domain_id]
    return {
        "source_domain_id": domain_id,
        "source_domain_type": _full_core.DOMAIN_TYPE,
        "assembly_x": assembly.x_index,
        "assembly_y": assembly.y_index,
        "axial_layer": assembly.axial_layer,
        "assembly_material_tag": assembly.material_key,
    }


def domain_names(library):
    return _full_core.domain_names(library)


def extra_tallies(library):
    return [_full_core.build_volume_flux_tally()]


def load_statepoint(library, statepoint_path):
    return _full_core.load_statepoint(library, statepoint_path)


def root_attrs():
    return _full_core.root_attrs()


def postprocess_hdf5(output_path, statepoint_path, summary):
    if statepoint_path is None:
        return
    _full_core.append_volume_flux_hdf5(
        output_path=output_path,
        statepoint_path=statepoint_path,
        mixture_names=[domain.name for domain in summary.domains],
    )

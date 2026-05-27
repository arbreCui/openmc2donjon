"""openmc2donjon export recipe for the OpenMC CE/MG SPH colorset.

Set ``OPENMC2DONJON_COLORSET_DIR`` to the directory containing the generated
continuous-energy OpenMC XML files before running ``openmc2donjon-from-openmc``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from openmc2donjon import DomainExportSpec


def _load_colorset_module():
    path = Path(__file__).with_name("colorset_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_colorset_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import colorset model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_colorset = _load_colorset_module()


def build_library():
    return _colorset.build_library(case_dir=_colorset.default_case_dir())


def domain_specs(library):
    names = _colorset.domain_names(library)
    return [
        DomainExportSpec(
            domain=domain,
            name=names[int(domain.id)],
            volume=float(_colorset.DOMAIN_VOLUME_BY_ID[int(domain.id)]),
            attrs={
                "source_domain_id": int(domain.id),
                "source_domain_type": _colorset.DOMAIN_TYPE,
                "colorset_region": names[int(domain.id)],
            },
        )
        for domain in library.domains
    ]


def domain_names(library):
    return _colorset.domain_names(library)


def extra_tallies(library):
    return [_colorset.build_volume_flux_tally()]


def load_statepoint(library, statepoint_path):
    return _colorset.load_statepoint(library, statepoint_path)


def root_attrs():
    return _colorset.root_attrs()


def postprocess_hdf5(output_path, statepoint_path, summary):
    if statepoint_path is None:
        return
    _colorset.append_volume_flux_hdf5(
        output_path=output_path,
        statepoint_path=statepoint_path,
        mixture_names=[domain.name for domain in summary.domains],
    )

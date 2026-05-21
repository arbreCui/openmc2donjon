"""openmc2donjon export recipe for the production minicase.

Set ``OPENMC2DONJON_MINICASE_DIR`` to the directory containing the generated
OpenMC XML files before running ``openmc2donjon-from-openmc``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from openmc2donjon import DomainExportSpec


def _load_minicase_module():
    path = Path(__file__).with_name("minicase_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_minicase_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import minicase model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_minicase = _load_minicase_module()


def build_library():
    return _minicase.build_library(case_dir=_minicase.default_case_dir())


def domain_specs(library):
    names = _minicase.domain_names(library)
    return [
        DomainExportSpec(
            domain=domain,
            name=names[int(domain.id)],
            volume=float(_minicase.DOMAIN_VOLUME_BY_ID[int(domain.id)]),
            attrs={
                "source_domain_id": int(domain.id),
                "source_domain_type": _minicase.DOMAIN_TYPE,
            },
        )
        for domain in library.domains
    ]


def domain_names(library):
    return _minicase.domain_names(library)


def extra_tallies(library):
    return [_minicase.build_surface_flux_tally()]


def load_statepoint(library, statepoint_path):
    return _minicase.load_statepoint(library, statepoint_path)


def root_attrs():
    return _minicase.root_attrs()

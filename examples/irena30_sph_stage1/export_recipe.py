"""openmc2donjon export recipe for the IRENA SPH Stage 1 assembly.

Set ``OPENMC2DONJON_IRENA_SPH_DIR`` to the directory containing the generated
continuous-energy OpenMC XML files before running ``openmc2donjon-from-openmc``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from openmc2donjon import DomainExportSpec


def _load_model_module():
    path = Path(__file__).with_name("irena_hex_sph_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_irena_sph_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import IRENA SPH model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_model = _load_model_module()


def build_library():
    return _model.build_library(case_dir=_model.default_case_dir())


def domain_specs(library):
    volume = _model.container_volume_cm3(_model._load_rnr_module())
    return [
        DomainExportSpec(
            domain=domain,
            name=_model.REGION_NAME,
            volume=volume,
            attrs={
                "source_domain_id": int(domain.id),
                "source_domain_type": _model.DOMAIN_TYPE,
                "irena_mixture_label": "INT",
            },
        )
        for domain in library.domains
    ]


def domain_names(library):
    return _model.domain_names(library)


def load_statepoint(library, statepoint_path):
    return _model.load_statepoint(library, statepoint_path)


def root_attrs():
    return _model.root_attrs()

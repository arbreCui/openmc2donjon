"""openmc2donjon export recipe for the IRENA SPH Stage 2 CSD colorset.

Set ``OPENMC2DONJON_IRENA_SPH2_DIR`` to the generated CE case directory
before running the exporter.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from openmc2donjon import DomainExportSpec


def _load_model_module():
    path = Path(__file__).with_name("irena_csd_colorset_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_irena_sph2_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import Stage 2 model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_model = _load_model_module()


def build_library():
    return _model.build_library(case_dir=_model.default_case_dir())


def domain_specs(library):
    colorset_common, _openmc_colorset, _explicit7 = _model._load_ce_compare_modules()
    volume = _model.assembly_volume_cm3(colorset_common)
    names = _model.domain_names(library)
    specs = []
    for domain in library.domains:
        match = _model._CELL_NAME_RE.match(domain.name or "")
        position, kind = int(match.group(1)), match.group(2)
        specs.append(
            DomainExportSpec(
                domain=domain,
                name=names[int(domain.id)],
                volume=volume,
                attrs={
                    "source_domain_id": int(domain.id),
                    "source_domain_type": _model.DOMAIN_TYPE,
                    "irena_mixture_label": kind,
                    "colorset_position": position,
                },
            )
        )
    return specs


def domain_names(library):
    return _model.domain_names(library)


def load_statepoint(library, statepoint_path):
    return _model.load_statepoint(library, statepoint_path)


def root_attrs():
    return _model.root_attrs()

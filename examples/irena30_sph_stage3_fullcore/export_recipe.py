"""openmc2donjon export recipe for the IRENA SPH Stage 3 full core.

The exporter derives the generated CE case directory from the selected
statepoint. ``OPENMC2DONJON_IRENA_SPH3_DIR`` remains available for dry runs
that do not load a statepoint.

Note on group ordering: unlike ``examples/irena30_zrefl_hex`` (an OpenMC
multi-group-mode statepoint, which needs ``order_groups="decreasing"``),
this recipe reads a CONTINUOUS-ENERGY statepoint where the mgxs default
group indexing (group 1 = highest energy first) already matches the
converter contract (index 0 = highest energy); no override is passed,
following ``examples/irena30_sph_stage2_csd``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from openmc2donjon import DomainExportSpec


def _load_model_module():
    path = Path(__file__).with_name("ce_core_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_irena_sph3_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import Stage 3 model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_model = _load_model_module()


def build_library(statepoint_path=None):
    case_dir = (
        Path(statepoint_path).resolve().parent
        if statepoint_path is not None
        else _model.default_case_dir()
    )
    return _model.build_library(case_dir=case_dir)


def domain_specs(library):
    names = _model.domain_names(library)
    volume = _model.hex_cell_volume_cm3(17.5)
    specs = []
    for domain in library.domains:
        match = _model._CORE_CELL_RE.match(domain.name or "")
        if not match:
            raise RuntimeError(f"unexpected domain cell name: {domain.name!r}")
        ring, pos, label = int(match.group(1)), int(match.group(2)), match.group(3)
        specs.append(
            DomainExportSpec(
                domain=domain,
                name=names[int(domain.id)],
                volume=volume,
                attrs={
                    "source_domain_id": int(domain.id),
                    "source_domain_type": _model.DOMAIN_TYPE,
                    "hex_ring": ring,
                    "hex_position": pos,
                    "irena_mixture_label": label,
                    "hex_pitch_cm": 17.5,
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

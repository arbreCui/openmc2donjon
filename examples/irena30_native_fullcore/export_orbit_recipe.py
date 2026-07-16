"""Converter recipe for the strict IRENA 21-orbit full-core CE reference."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from openmc2donjon import DomainExportSpec


def _load_model_module():
    path = Path(__file__).with_name("irena_orbit_ce_model.py")
    spec = importlib.util.spec_from_file_location(
        "_openmc2donjon_irena_orbit_ce_model", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import strict IRENA orbit model: {path}")
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
    specs = []
    for domain in library.domains:
        orbit = _model.orbit_for_domain(domain)
        members = [
            {"ring": ring, "position": position}
            for ring, position in orbit.members
        ]
        specs.append(
            DomainExportSpec(
                domain=domain,
                name=_model.exported_orbit_name(orbit),
                volume=_model.orbit_volume_cm3(orbit),
                attrs={
                    "source_domain_id": int(domain.id),
                    "source_domain_type": _model.DOMAIN_TYPE,
                    "irena_orbit_id": orbit.id,
                    "irena_orbit_number": orbit.number,
                    "irena_orbit_ring": orbit.ring,
                    "irena_orbit_representative": orbit.representative,
                    "irena_orbit_material": orbit.material,
                    "irena_orbit_multiplicity": orbit.multiplicity,
                    "irena_orbit_members_json": json.dumps(
                        members, sort_keys=True, separators=(",", ":")
                    ),
                    "transport_time_pooling": True,
                    "post_hoc_cross_section_averaging": False,
                    "single_node_volume_cm3": _model.node_volume_cm3(),
                },
            )
        )
    return specs


def domain_names(library):
    return _model.domain_names(library)


def load_statepoint(library, statepoint_path):
    return _model.load_statepoint(library, statepoint_path)


def scatter_mgxs_type():
    return "consistent nu-scatter matrix"


def root_attrs():
    return _model.root_attrs()


def extra_tallies(library):
    """Support ``openmc2donjon-export --write-tallies`` for this recipe."""

    return _model.build_reference_tallies(library.geometry)


def postprocess_hdf5(library, output_path, statepoint_path, summary):
    if statepoint_path is None:
        return
    _model.postprocess_hdf5(
        output_path=Path(output_path),
        statepoint_path=Path(statepoint_path),
        library=library,
        mixture_names=[domain.name for domain in summary.domains],
    )

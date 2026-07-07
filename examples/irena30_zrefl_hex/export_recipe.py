"""openmc2donjon export recipe for the IRENA-30 ZREFL hex case.

Set ``OPENMC2DONJON_IRENA_ZREFL_DIR`` to the generated OpenMC case directory
before running ``openmc2donjon-from-openmc``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from openmc2donjon import DomainExportSpec


def _load_irena_module():
    path = Path(__file__).with_name("irena_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_irena_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import IRENA model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_irena = _load_irena_module()
_CELL_RE = re.compile(r"^r(\d+)p(\d+)_L00_(INT|EXT|CSD|DSDF|PNL)$")


def build_library():
    return _irena.build_library(case_dir=_irena.default_case_dir())


def domain_specs(library):
    names = _irena.domain_names(library)
    volume = _irena.hex_cell_volume_cm3(17.5)
    specs = []
    for domain in library.domains:
        match = _CELL_RE.match(domain.name or "")
        if not match:
            raise RuntimeError(f"unexpected domain cell name: {domain.name!r}")
        ring, pos, label = int(match.group(1)), int(match.group(2)), match.group(3)
        specs.append(
            DomainExportSpec(
                domain=domain,
                name=names[int(domain.id)],
                volume=volume,
                # OpenMC multi-group-mode statepoints return mgxs arrays in
                # ascending-energy order (the opposite of CE-mode statepoints);
                # request decreasing order explicitly so the exported datasets
                # follow the converter contract (index 0 = highest energy).
                xs_kwargs={"order_groups": "decreasing"},
                attrs={
                    "source_domain_id": int(domain.id),
                    "source_domain_type": _irena.DOMAIN_TYPE,
                    "hex_ring": ring,
                    "hex_position": pos,
                    "irena_mixture_label": label,
                    "hex_pitch_cm": 17.5,
                },
            )
        )
    return specs


def domain_names(library):
    return _irena.domain_names(library)


def load_statepoint(library, statepoint_path):
    return _irena.load_statepoint(library, statepoint_path)


def root_attrs():
    return _irena.root_attrs()

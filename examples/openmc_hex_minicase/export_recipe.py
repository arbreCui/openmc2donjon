"""openmc2donjon export recipe for the OpenMC hex minicase.

Set ``OPENMC2DONJON_HEX_MINICASE_DIR`` to the generated OpenMC case directory
before running ``openmc2donjon-from-openmc``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_hex_module():
    path = Path(__file__).with_name("hex_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_hex_model", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import hex model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_hex = _load_hex_module()


def build_library():
    return _hex.build_library(case_dir=_hex.default_case_dir())


def domain_names(library):
    return _hex.domain_names(library)


def load_statepoint(library, statepoint_path):
    return _hex.load_statepoint(library, statepoint_path)


def root_attrs():
    return _hex.root_attrs()

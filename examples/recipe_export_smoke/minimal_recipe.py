"""Tiny recipe for exercising the openmc2donjon statepoint export workflow.

This is not a physics benchmark.  It is a minimal MGXS-like object used by
``scripts/run_recipe_export_smoke.sh`` to prove the recipe/statepoint CLI path
without requiring a full OpenMC model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Domain:
    name: str
    id: int
    volume: float
    fissionable: bool


class EnergyGroups:
    group_edges = np.array([1.0e-5, 1.0, 1.0e7], dtype=float)


class MGXS:
    def __init__(self, values) -> None:
        self.values = np.asarray(values, dtype=float)

    def get_xs(self, **_kwargs):
        return self.values


class TinyLibrary:
    def __init__(self) -> None:
        self.energy_groups = EnergyGroups()
        self.domains = [
            Domain("fuel position A", 1, 100.0, True),
            Domain("moderator position A", 2, 80.0, False),
        ]
        self.loaded_statepoint = None
        self.data = {
            (1, "total"): [0.48, 0.65],
            (1, "absorption"): [0.05, 0.08],
            (1, "fission"): [0.010, 0.020],
            (1, "nu-fission"): [0.025, 0.050],
            (1, "chi"): [1.0, 0.0],
            (1, "scatter matrix"): [[0.40, 0.03], [0.02, 0.55]],
            (1, "transport"): [0.45, 0.63],
            (2, "total"): [0.30, 0.57],
            (2, "absorption"): [0.01, 0.03],
            (2, "scatter matrix"): [[0.28, 0.01], [0.02, 0.52]],
            (2, "transport"): [0.29, 0.57],
        }

    def get_mgxs(self, domain, mgxs_type):
        key = (domain.id, mgxs_type)
        if key not in self.data:
            raise KeyError(key)
        return MGXS(self.data[key])


def build_library():
    return TinyLibrary()


def load_statepoint(library, statepoint_path):
    # A real OpenMC recipe can omit this hook; the runner will then call
    # library.load_from_statepoint(openmc.StatePoint(...)).
    library.loaded_statepoint = str(Path(statepoint_path))


def domain_names():
    return {
        1: "FUEL_A",
        2: "MOD_A",
    }


def root_attrs(library):
    return {
        "domain_mode": "recipe_smoke",
        "statepoint_marker": library.loaded_statepoint,
    }

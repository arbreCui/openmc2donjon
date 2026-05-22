"""Minimal OpenMC recipe that also exports SPH reference volume flux."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np


REFERENCE_FLUX = np.array([[80.0, 800.0], [120.0, 600.0]], dtype=float)


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
    library.loaded_statepoint = str(Path(statepoint_path))


def domain_names():
    return {
        1: "FUEL_A",
        2: "MOD_A",
    }


def root_attrs(library):
    return {
        "domain_mode": "openmc_sph_loop_entrypoint",
        "statepoint_marker": library.loaded_statepoint or "",
    }


def postprocess_hdf5(output_path, summary):
    names = np.asarray([domain.name for domain in summary.domains], dtype="S")
    with h5py.File(output_path, "a") as h5:
        dataset = h5.create_dataset("openmc_volume_flux", data=REFERENCE_FLUX)
        dataset.attrs["mixture_names"] = names

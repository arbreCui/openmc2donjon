from __future__ import annotations

from pathlib import Path
from typing import Any


try:  # pragma: no cover - import guard exercised via skip path
    from fastapi.testclient import TestClient

    WEB_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when web extras are absent
    TestClient = None  # type: ignore[assignment]
    WEB_AVAILABLE = False


def write_fake_hdf5(path: Path) -> None:
    """Materialise a small HDF5 matching the converter input contract."""

    import h5py
    import numpy as np

    # CASMO-7 bounds (ascending low-to-high per the HDF5 input contract) so the
    # catalog match endpoint returns a hit.
    energy_bounds = np.array(
        [9.999999999999999e-06, 0.058, 0.14, 0.625, 4.0, 5530.0, 821000.0, 10000000.0],
        dtype=float,
    )
    ngroups = 7
    with h5py.File(path, "w") as h5:
        h5.attrs["schema_version"] = "openmc2donjon.mgxs.v1"
        h5.attrs["energy_groups"] = ngroups
        h5.attrs["legendre_order"] = 0
        h5.attrs["scatter_axes"] = "moment,from,to"
        h5.create_dataset("energy_bounds", data=energy_bounds)
        mixtures = h5.create_group("mixtures")
        for index, name in enumerate(("M1_UO2", "M2_MOD"), start=1):
            mix = mixtures.create_group(name)
            mix.attrs["volume"] = float(index)
            mix.attrs["temperature"] = 600.0
            mix.attrs["fissionable"] = bool(name == "M1_UO2")
            mix.create_dataset("total", data=np.full(ngroups, 0.5 * index))
            mix.create_dataset("absorption", data=np.full(ngroups, 0.05 * index))
            is_fissionable = name == "M1_UO2"
            fission = (
                np.full(ngroups, 0.01 * index)
                if is_fissionable
                else np.zeros(ngroups, dtype=float)
            )
            chi = np.zeros(ngroups, dtype=float)
            if is_fissionable:
                chi[0] = 1.0
            mix.create_dataset("fission", data=fission)
            mix.create_dataset("nu_fission", data=2.5 * fission)
            mix.create_dataset("chi", data=chi)
            mix.create_dataset("transport_total", data=np.full(ngroups, 0.5 * index))
            scatter = np.zeros((1, ngroups, ngroups), dtype=float)
            for g in range(ngroups):
                scatter[0, g, g] = 0.2 * index
                if g + 1 < ngroups:
                    scatter[0, g, g + 1] = 0.01 * index
            scatter_dataset = mix.create_dataset("scatter_matrix", data=scatter)
            scatter_dataset.attrs["axes"] = "moment,from,to"


def minimal_openmc_sph_physics_summary() -> dict[str, Any]:
    return {
        "schema": "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
        "route": "OpenMC CE reference + OpenMC MG same geometry -> OpenMC-side SPH",
        "handoff_dir": "/tmp/handoff",
        "mixture_count": 2,
        "energy_groups": 33,
        "legendre_order": 3,
        "mixture_names": ["CS_FUEL", "CS_MOD"],
        "decisions": {
            "openmc_sph": "openmc2donjon_openmc_sph_sidecar_passed",
            "sph_augment": "openmc2donjon_sph_augment_passed",
        },
        "normalization": {
            "method": "power",
            "factor": 1.0,
            "formula": "sph = normalized_openmc_mg_flux / openmc_ce_reference_flux",
        },
        "flux_uncertainty": {
            "ce_max_relative_std_dev": 0.01,
            "mg_max_relative_std_dev": 0.02,
            "ce_dataset": "openmc_volume_flux",
            "mg_dataset": "openmc_mg_flux",
        },
        "sph": {
            "kind": "openmc-ce-mg",
            "real": True,
            "applied_to_xs": False,
            "minimum": 0.9,
            "maximum": 1.1,
            "mean": 1.0,
            "max_abs_delta_from_unity": 0.1,
            "clipped_count": 0,
        },
        "handoff": {
            "augmented_hdf5_has_sph": True,
            "ascii_nsp_block_count": 2,
            "ascii_path": "/tmp/handoff/out.mcompo.txt",
            "augmented_hdf5_path": "/tmp/handoff/mgxs_with_sph.h5",
        },
        "per_mixture": [
            {
                "mixture": "CS_FUEL",
                "ce_flux_min": 1.0,
                "ce_flux_max": 2.0,
                "mg_flux_min": 1.0,
                "mg_flux_max": 2.1,
                "normalized_mg_over_ce_min": 0.9,
                "normalized_mg_over_ce_max": 1.1,
                "sph_min": 0.9,
                "sph_max": 1.1,
                "sph_mean": 1.0,
                "max_abs_sph_minus_1": 0.1,
            }
        ],
    }

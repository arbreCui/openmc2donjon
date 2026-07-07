"""Build deterministic inputs for the OpenMC CE/MG SPH sidecar minicase."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


ENERGY_BOUNDS = np.array([1.0e-5, 1.0, 1.0e7], dtype=float)
MIXTURE_NAMES = ("FUEL_A", "MOD_B")
REFERENCE_FLUX = np.array(
    [
        [1.21, 0.81],
        [0.64, 1.44],
    ],
    dtype=float,
)
MG_FLUX = np.ones((2, 2), dtype=float)
REFERENCE_FLUX_STD_DEV = np.array(
    [
        [0.0121, 0.0081],
        [0.0064, 0.0144],
    ],
    dtype=float,
)
MG_FLUX_STD_DEV = np.array(
    [
        [0.010, 0.010],
        [0.010, 0.010],
    ],
    dtype=float,
)
DAMPING = 0.5
EXPECTED_SPH = np.power(REFERENCE_FLUX / MG_FLUX, DAMPING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write deterministic MGXS, CE flux, and MG flux inputs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory where example input files will be written",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    mgxs = output_dir / "mgxs_library.h5"
    ce_flux = output_dir / "openmc_ce_flux.h5"
    mg_flux = output_dir / "openmc_mg_flux.h5"
    reference = output_dir / "reference_expected.h5"

    _write_mgxs(mgxs)
    _write_flux(
        ce_flux,
        dataset_name="openmc_volume_flux",
        values=REFERENCE_FLUX,
        std_dev=REFERENCE_FLUX_STD_DEV,
    )
    _write_flux(
        mg_flux,
        dataset_name="openmc_mg_flux",
        values=MG_FLUX,
        std_dev=MG_FLUX_STD_DEV,
    )
    _write_reference(reference)

    print("OpenMC CE/MG SPH sidecar minicase inputs")
    print(f"  mgxs: {mgxs}")
    print(f"  ce_flux: {ce_flux}::openmc_volume_flux")
    print(f"  mg_flux: {mg_flux}::openmc_mg_flux")
    print(f"  reference: {reference}")
    return 0


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.attrs["domain_mode"] = "openmc_ce_mg_sph_minicase"
        h5.attrs["spatial_mapping"] = (
            "one OpenMC CE/MG output region -> one DONJON mixture"
        )
        _write_string_dataset(h5, "mixture_names", MIXTURE_NAMES)
        h5.create_dataset("energy_bounds", data=ENERGY_BOUNDS)
        mixtures = h5.create_group("mixtures")
        _write_mixture(
            mixtures,
            "FUEL_A",
            fissionable=True,
            volume=64.0,
            total=np.array([0.50, 0.70]),
            absorption=np.array([0.05, 0.10]),
            fission=np.array([0.010, 0.020]),
            nu_fission=np.array([0.025, 0.050]),
            chi=np.array([1.0, 0.0]),
            scatter=np.array([[[0.40, 0.05], [0.02, 0.58]]]),
            transport=np.array([0.45, 0.63]),
        )
        _write_mixture(
            mixtures,
            "MOD_B",
            fissionable=False,
            volume=64.0,
            total=np.array([0.30, 0.60]),
            absorption=np.array([0.02, 0.04]),
            fission=np.array([0.0, 0.0]),
            nu_fission=np.array([0.0, 0.0]),
            chi=np.array([0.0, 0.0]),
            scatter=np.array([[[0.27, 0.01], [0.03, 0.53]]]),
            transport=np.array([0.29, 0.57]),
        )


def _write_mixture(
    mixtures,
    name: str,
    *,
    fissionable: bool,
    volume: float,
    total: np.ndarray,
    absorption: np.ndarray,
    fission: np.ndarray,
    nu_fission: np.ndarray,
    chi: np.ndarray,
    scatter: np.ndarray,
    transport: np.ndarray,
) -> None:
    group = mixtures.create_group(name)
    group.attrs["fissionable"] = bool(fissionable)
    group.attrs["scatter_axes"] = "moment,from,to"
    group.attrs["volume"] = float(volume)
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset("fission", data=fission)
    group.create_dataset("nu_fission", data=nu_fission)
    group.create_dataset("chi", data=chi)
    group.create_dataset("scatter_matrix", data=scatter)
    group.create_dataset("transport_total", data=transport)


def _write_flux(
    path: Path,
    *,
    dataset_name: str,
    values: np.ndarray,
    std_dev: np.ndarray | None = None,
) -> None:
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset(dataset_name, data=values)
        dataset.attrs["group_order"] = "mgxs_donjon"
        dataset.attrs["mixture_names"] = np.asarray(MIXTURE_NAMES, dtype="S")
        if std_dev is not None:
            std_dataset = h5.create_dataset(f"{dataset_name}_std_dev", data=std_dev)
            std_dataset.attrs["group_order"] = "mgxs_donjon"
            std_dataset.attrs["mixture_names"] = np.asarray(MIXTURE_NAMES, dtype="S")
            std_dataset.attrs["std_dev_of"] = dataset_name


def _write_reference(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.openmc-sph-minicase-reference.v1"
        h5.attrs["damping"] = DAMPING
        h5.create_dataset("sph", data=EXPECTED_SPH)
        _write_string_dataset(h5, "mixture_names", MIXTURE_NAMES)


def _write_string_dataset(parent, name: str, values: tuple[str, ...]) -> None:
    dtype = h5py.string_dtype(encoding="utf-8")
    parent.create_dataset(name, data=np.asarray(values, dtype=object), dtype=dtype)


if __name__ == "__main__":
    raise SystemExit(main())

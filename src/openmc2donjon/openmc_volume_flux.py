"""Helpers for writing OpenMC volume-flux reference maps."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Iterable

import numpy as np

from . import __version__
from .constants import MGXS_DONJON_GROUP_ORDER


DATASET_NAME = "openmc_volume_flux"
STD_DEV_DATASET_NAME = "openmc_volume_flux_std_dev"
SCHEMA = "openmc2donjon.openmc-volume-flux.v1"
DEFAULT_SOURCE_GROUP_ORDER = "openmc_energy_filter_reversed"


@dataclass(frozen=True)
class OpenMCVolumeFluxReport:
    output_h5: Path
    dataset: str
    mixture_names: tuple[str, ...]
    energy_groups: int
    source_group_order: str
    minimum: float
    maximum: float
    std_dev_dataset: str | None = None
    max_relative_std_dev: float | None = None


def reverse_openmc_energy_filter_flux(
    values: np.ndarray | Iterable[float],
    *,
    mixture_count: int,
    energy_groups: int,
) -> np.ndarray:
    """Return a volume-flux tally in MGXS/DONJON group order."""

    if mixture_count <= 0:
        raise ValueError("mixture_count must be positive")
    if energy_groups <= 0:
        raise ValueError("energy_groups must be positive")
    array = np.asarray(values, dtype=float).squeeze()
    expected = (int(mixture_count), int(energy_groups))
    try:
        reshaped = array.reshape(expected)
    except ValueError as exc:
        raise ValueError(
            f"OpenMC volume-flux tally cannot be reshaped to {expected}; "
            f"got {array.shape}"
        ) from exc
    return reshaped[:, ::-1].copy()


def write_openmc_volume_flux_hdf5(
    output_h5: str | PathLike[str],
    values: np.ndarray | Iterable[Iterable[float]],
    *,
    mixture_names: Iterable[str],
    std_dev: np.ndarray | Iterable[Iterable[float]] | None = None,
    dataset_name: str = DATASET_NAME,
    std_dev_dataset_name: str = STD_DEV_DATASET_NAME,
    source_group_order: str = DEFAULT_SOURCE_GROUP_ORDER,
    replace: bool = True,
) -> OpenMCVolumeFluxReport:
    """Append a canonical ``/openmc_volume_flux`` dataset to an MGXS HDF5 file."""

    import h5py

    path = Path(output_h5)
    names = _as_mixture_names(mixture_names)
    flux = _as_flux_array(values, names=names, dataset_name=dataset_name)
    flux_std_dev = _as_std_dev_array(
        std_dev,
        expected_shape=flux.shape,
        dataset_name=std_dev_dataset_name,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "a") as h5:
        if dataset_name in h5:
            if not replace:
                raise FileExistsError(f"{path}: /{dataset_name} already exists")
            del h5[dataset_name]
        if std_dev_dataset_name in h5 and replace:
            del h5[std_dev_dataset_name]
        if std_dev_dataset_name in h5 and flux_std_dev is not None:
            raise FileExistsError(f"{path}: /{std_dev_dataset_name} already exists")
        _write_flux_dataset(
            h5,
            dataset_name,
            flux,
            names=names,
            source_group_order=source_group_order,
        )
        if flux_std_dev is not None:
            _write_flux_dataset(
                h5,
                std_dev_dataset_name,
                flux_std_dev,
                names=names,
                source_group_order=source_group_order,
            )

    return OpenMCVolumeFluxReport(
        output_h5=path,
        dataset=dataset_name,
        mixture_names=names,
        energy_groups=int(flux.shape[1]),
        source_group_order=str(source_group_order),
        minimum=float(np.min(flux)),
        maximum=float(np.max(flux)),
        std_dev_dataset=std_dev_dataset_name if flux_std_dev is not None else None,
        max_relative_std_dev=(
            None
            if flux_std_dev is None
            else float(np.max(flux_std_dev / np.abs(flux)))
        ),
    )


def _as_mixture_names(values: Iterable[str]) -> tuple[str, ...]:
    names = tuple(str(value) for value in values)
    if not names:
        raise ValueError("mixture_names must not be empty")
    if any(not name for name in names):
        raise ValueError("mixture_names must not contain empty names")
    if len(set(names)) != len(names):
        raise ValueError("mixture_names must be unique")
    return names


def _as_flux_array(
    values: np.ndarray | Iterable[Iterable[float]],
    *,
    names: tuple[str, ...],
    dataset_name: str,
) -> np.ndarray:
    flux = np.asarray(values, dtype=float)
    if flux.ndim != 2:
        raise ValueError(f"{dataset_name} values must have shape (mixture, group)")
    if flux.shape[0] != len(names):
        raise ValueError(
            f"{dataset_name} mixture axis must match mixture_names: "
            f"{flux.shape[0]} != {len(names)}"
        )
    if flux.shape[1] <= 0:
        raise ValueError(f"{dataset_name} must contain at least one energy group")
    if not np.all(np.isfinite(flux)):
        raise ValueError(f"{dataset_name} values must be finite")
    if np.any(flux <= 0.0):
        raise ValueError(f"{dataset_name} values must be positive")
    return flux


def _as_std_dev_array(
    values: np.ndarray | Iterable[Iterable[float]] | None,
    *,
    expected_shape: tuple[int, int],
    dataset_name: str,
) -> np.ndarray | None:
    if values is None:
        return None
    std_dev = np.asarray(values, dtype=float)
    if std_dev.shape != expected_shape:
        raise ValueError(
            f"{dataset_name} shape must match openmc_volume_flux shape: "
            f"{std_dev.shape} != {expected_shape}"
        )
    if not np.all(np.isfinite(std_dev)):
        raise ValueError(f"{dataset_name} values must be finite")
    if np.any(std_dev < 0.0):
        raise ValueError(f"{dataset_name} values must be non-negative")
    return std_dev


def _write_flux_dataset(
    h5,
    name: str,
    values: np.ndarray,
    *,
    names: tuple[str, ...],
    source_group_order: str,
) -> None:
    dataset = h5.create_dataset(name, data=values)
    dataset.attrs["schema"] = SCHEMA
    dataset.attrs["package_version"] = __version__
    dataset.attrs["layout"] = "[mixture, group]"
    dataset.attrs["group_order"] = MGXS_DONJON_GROUP_ORDER
    dataset.attrs["source_group_order"] = str(source_group_order)
    dataset.attrs["mixture_names"] = np.asarray(names, dtype="S")

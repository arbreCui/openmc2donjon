"""Helpers for writing OpenMC volume-flux reference maps."""

from __future__ import annotations

from dataclasses import dataclass
import json
from os import PathLike
from pathlib import Path
from typing import Iterable

import numpy as np

from . import __version__
from .constants import MGXS_DONJON_GROUP_ORDER
from .hdf5_names import read_mixture_names


DATASET_NAME = "openmc_volume_flux"
STD_DEV_DATASET_NAME = "openmc_volume_flux_std_dev"
SCHEMA = "openmc2donjon.openmc-volume-flux.v1"
PASS_DECISION = "openmc2donjon_volume_flux_export_passed"
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
    statepoint: Path | None = None
    tally_name: str | None = None


def export_openmc_volume_flux(
    statepoint: str | PathLike[str],
    output_h5: str | PathLike[str],
    *,
    mgxs_h5: str | PathLike[str] | None = None,
    tally_name: str = DATASET_NAME,
    dataset_name: str = DATASET_NAME,
    std_dev_dataset_name: str | None = None,
    mixture_names: Iterable[str] | None = None,
    energy_groups: int | None = None,
    source_group_order: str = DEFAULT_SOURCE_GROUP_ORDER,
    force: bool = False,
    summary_json: str | PathLike[str] | None = None,
) -> OpenMCVolumeFluxReport:
    """Export an OpenMC statepoint volume-flux tally as canonical HDF5.

    The written dataset has shape ``(mixture, group)`` and carries the
    ``group_order='mgxs_donjon'`` and ``mixture_names`` attributes required by
    ``make-openmc-sph-sidecar``.  OpenMC EnergyFilter tally bins are
    low-to-high; values are reversed along the energy axis by default.
    """

    try:
        import openmc
    except ImportError as exc:  # pragma: no cover - depends on user environment
        raise RuntimeError(
            "OpenMC is required to export a volume-flux tally from a statepoint"
        ) from exc

    statepoint_path = Path(statepoint)
    output_path = Path(output_h5)
    if not statepoint_path.exists():
        raise FileNotFoundError(f"statepoint does not exist: {statepoint_path}")
    if output_path.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_path}")

    names, ngroups = _resolve_metadata(
        mgxs_h5=None if mgxs_h5 is None else Path(mgxs_h5),
        mixture_names=tuple(mixture_names) if mixture_names is not None else None,
        energy_groups=energy_groups,
    )
    with openmc.StatePoint(str(statepoint_path)) as sp:
        tally = sp.get_tally(name=tally_name)
        mean = tally.get_values(scores=["flux"], value="mean")
        std_dev = tally.get_values(scores=["flux"], value="std_dev")

    flux = reverse_openmc_energy_filter_flux(
        mean,
        mixture_count=len(names),
        energy_groups=ngroups,
    )
    flux_std_dev = reverse_openmc_energy_filter_flux(
        std_dev,
        mixture_count=len(names),
        energy_groups=ngroups,
    )
    report = write_openmc_flux_hdf5(
        output_path,
        flux,
        mixture_names=names,
        std_dev=flux_std_dev,
        dataset_name=dataset_name,
        std_dev_dataset_name=(
            std_dev_dataset_name
            if std_dev_dataset_name is not None
            else f"{dataset_name}_std_dev"
        ),
        source_group_order=source_group_order,
        replace=True,
        statepoint=statepoint_path,
        tally_name=tally_name,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(Path(summary_json), report)
    return report


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

    return write_openmc_flux_hdf5(
        output_h5,
        values,
        mixture_names=mixture_names,
        std_dev=std_dev,
        dataset_name=dataset_name,
        std_dev_dataset_name=std_dev_dataset_name,
        source_group_order=source_group_order,
        replace=replace,
    )


def write_openmc_flux_hdf5(
    output_h5: str | PathLike[str],
    values: np.ndarray | Iterable[Iterable[float]],
    *,
    mixture_names: Iterable[str],
    std_dev: np.ndarray | Iterable[Iterable[float]] | None = None,
    dataset_name: str = DATASET_NAME,
    std_dev_dataset_name: str = STD_DEV_DATASET_NAME,
    source_group_order: str = DEFAULT_SOURCE_GROUP_ORDER,
    replace: bool = True,
    statepoint: str | PathLike[str] | None = None,
    tally_name: str | None = None,
) -> OpenMCVolumeFluxReport:
    """Append a canonical OpenMC flux matrix to an HDF5 file.

    ``dataset_name`` lets the same writer produce both CE reference flux
    (typically ``openmc_volume_flux``) and MG macro flux
    (for example ``openmc_mg_flux``) for OpenMC-side SPH equivalence.
    """

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
        statepoint=None if statepoint is None else Path(statepoint),
        tally_name=tally_name,
    )


def print_report(report: OpenMCVolumeFluxReport) -> None:
    print("OpenMC-to-DONJON volume flux export")
    print(f"  schema: {SCHEMA}")
    if report.statepoint is not None:
        print(f"  statepoint: {report.statepoint}")
    if report.tally_name is not None:
        print(f"  tally: {report.tally_name}")
    print(f"  output: {report.output_h5}::{report.dataset}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"group_order={MGXS_DONJON_GROUP_ORDER} "
        f"source_group_order={report.source_group_order}"
    )
    print(
        "  flux range: "
        f"min={report.minimum:.6g} max={report.maximum:.6g}"
    )
    if report.std_dev_dataset is not None:
        print(
            f"  std_dev: {report.std_dev_dataset} "
            f"max_rel={report.max_relative_std_dev:.6g}"
        )
    print()
    print("Volume flux export decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: OpenMCVolumeFluxReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": PASS_DECISION,
        "statepoint": None if report.statepoint is None else str(report.statepoint),
        "tally_name": report.tally_name,
        "output_h5": str(report.output_h5),
        "dataset": report.dataset,
        "std_dev_dataset": report.std_dev_dataset,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "energy_groups": report.energy_groups,
        "group_order": MGXS_DONJON_GROUP_ORDER,
        "source_group_order": report.source_group_order,
        "min": report.minimum,
        "max": report.maximum,
        "max_relative_std_dev": report.max_relative_std_dev,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_mixture_names(values: Iterable[str]) -> tuple[str, ...]:
    names = tuple(str(value) for value in values)
    if not names:
        raise ValueError("mixture_names must not be empty")
    if any(not name for name in names):
        raise ValueError("mixture_names must not contain empty names")
    if len(set(names)) != len(names):
        raise ValueError("mixture_names must be unique")
    return names


def _resolve_metadata(
    *,
    mgxs_h5: Path | None,
    mixture_names: tuple[str, ...] | None,
    energy_groups: int | None,
) -> tuple[tuple[str, ...], int]:
    mgxs_names: tuple[str, ...] | None = None
    mgxs_groups: int | None = None
    if mgxs_h5 is not None:
        import h5py

        with h5py.File(mgxs_h5, "r") as h5:
            if "mixtures" not in h5:
                raise ValueError(f"{mgxs_h5}: missing /mixtures group")
            mgxs_names = read_mixture_names(h5)
            if "energy_groups" in h5.attrs:
                mgxs_groups = int(h5.attrs["energy_groups"])
            elif "energy_bounds" in h5:
                mgxs_groups = int(np.asarray(h5["energy_bounds"][:]).size - 1)
            else:
                raise ValueError(f"{mgxs_h5}: missing energy group metadata")
    names = mixture_names or mgxs_names
    if not names:
        raise ValueError("mixture names must be supplied, either via --mgxs or --mixture-names")
    groups = int(energy_groups if energy_groups is not None else mgxs_groups or 0)
    if groups <= 0:
        raise ValueError("energy group count must be supplied, either via --mgxs or --energy-groups")
    return _as_mixture_names(names), groups


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

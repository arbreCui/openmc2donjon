"""Canonicalize low-order driver outputs for ADF/DF workflows."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from . import __version__
from .adf_augment import parse_faces
from .adf_sidecar import DEFAULT_CARTESIAN_FACES
from .homogeneous_face_flux import load_net_current, load_volume_flux


SCHEMA = "openmc2donjon.low-order-driver.v1"
PASS_DECISION = "openmc2donjon_low_order_driver_passed"


@dataclass(frozen=True)
class LowOrderDriverReport:
    input_h5: Path
    output_h5: Path
    volume_flux_source: Path
    volume_flux_dataset: str
    net_current_source: Path
    net_current_dataset: str
    mixture_names: tuple[str, ...]
    face_names: tuple[str, ...]
    energy_groups: int
    source_label: str
    volume_flux_minimum: float
    volume_flux_median: float
    volume_flux_maximum: float
    net_current_minimum: float
    net_current_median: float
    net_current_maximum: float


def create_low_order_driver(
    input_h5: Path,
    output_h5: Path,
    *,
    volume_flux: str | Path,
    net_current: str | Path,
    faces: tuple[str, ...] | None = None,
    source_label: str = "external low-order driver",
    force: bool = False,
    summary_json: Path | None = None,
) -> LowOrderDriverReport:
    """Write a canonical low-order driver HDF5 handoff.

    The command does not solve the low-order equations. It validates and
    normalizes driver outputs from another code into the layout consumed by
    ``make-homogeneous-face-flux``:

    ``/volume_flux`` as ``(mixture, group)`` and
    ``/net_current_density`` as ``(mixture, face, group)``.
    """

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")

    face_names = tuple(faces or DEFAULT_CARTESIAN_FACES)
    face_names = tuple(parse_faces(",".join(face_names)) or ())
    if not face_names:
        raise ValueError("at least one face must be selected")

    metadata = _read_mgxs_metadata(input_h5)
    mixture_names = metadata["mixture_names"]
    energy_bounds = metadata["energy_bounds"]
    energy_groups = int(energy_bounds.size - 1)

    volume = load_volume_flux(
        volume_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
    )
    current = load_net_current(
        net_current,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        face_names=face_names,
    )
    _validate_values(volume.values, current.values)

    _write_hdf5(
        output_h5,
        energy_bounds=energy_bounds,
        mixture_names=mixture_names,
        face_names=face_names,
        volume_flux_values=volume.values,
        net_current_values=current.values,
        input_h5=input_h5,
        volume_flux_source=volume.path,
        volume_flux_dataset=volume.dataset_path,
        net_current_source=current.path,
        net_current_dataset=current.dataset_path,
        source_label=source_label,
    )

    volume_stats = _stats(volume.values)
    current_stats = _stats(current.values)
    report = LowOrderDriverReport(
        input_h5=input_h5,
        output_h5=output_h5,
        volume_flux_source=volume.path,
        volume_flux_dataset=volume.dataset_path,
        net_current_source=current.path,
        net_current_dataset=current.dataset_path,
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
        source_label=source_label,
        volume_flux_minimum=volume_stats["min"],
        volume_flux_median=volume_stats["median"],
        volume_flux_maximum=volume_stats["max"],
        net_current_minimum=current_stats["min"],
        net_current_median=current_stats["median"],
        net_current_maximum=current_stats["max"],
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: LowOrderDriverReport) -> None:
    print("OpenMC-to-DONJON low-order driver handoff")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_h5}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"faces={','.join(report.face_names)}"
    )
    print(f"  source: {report.source_label}")
    print(
        "  volume_flux range: "
        f"min={report.volume_flux_minimum:.6g} "
        f"median={report.volume_flux_median:.6g} "
        f"max={report.volume_flux_maximum:.6g}"
    )
    print(
        "  net_current_density range: "
        f"min={report.net_current_minimum:.6g} "
        f"median={report.net_current_median:.6g} "
        f"max={report.net_current_maximum:.6g}"
    )
    print()
    print("Low-order driver decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: LowOrderDriverReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": PASS_DECISION,
        "input_h5": str(report.input_h5),
        "output_h5": str(report.output_h5),
        "source_label": report.source_label,
        "volume_flux": str(report.volume_flux_source),
        "volume_flux_dataset": report.volume_flux_dataset,
        "net_current": str(report.net_current_source),
        "net_current_dataset": report.net_current_dataset,
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
        "volume_flux_min": report.volume_flux_minimum,
        "volume_flux_median": report.volume_flux_median,
        "volume_flux_max": report.volume_flux_maximum,
        "net_current_min": report.net_current_minimum,
        "net_current_median": report.net_current_median,
        "net_current_max": report.net_current_maximum,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_mgxs_metadata(path: Path) -> dict[str, np.ndarray | tuple[str, ...]]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError("input HDF5 must contain a /mixtures group")
        if "energy_bounds" not in h5:
            raise ValueError("input HDF5 must contain /energy_bounds")
        energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
        if energy_bounds.ndim != 1 or energy_bounds.size < 2:
            raise ValueError("/energy_bounds must be a one-dimensional group edge array")
        mixture_names = tuple(str(name) for name in h5["mixtures"])
        if not mixture_names:
            raise ValueError("input HDF5 contains no mixtures")
    return {"energy_bounds": energy_bounds, "mixture_names": mixture_names}


def _validate_values(volume_flux: np.ndarray, net_current: np.ndarray) -> None:
    if not np.all(np.isfinite(volume_flux)) or not np.all(np.isfinite(net_current)):
        raise ValueError("low-order driver values must be finite")
    if np.any(volume_flux <= 0.0):
        raise ValueError("volume_flux values must be positive")


def _write_hdf5(
    path: Path,
    *,
    energy_bounds: np.ndarray,
    mixture_names: tuple[str, ...],
    face_names: tuple[str, ...],
    volume_flux_values: np.ndarray,
    net_current_values: np.ndarray,
    input_h5: Path,
    volume_flux_source: Path,
    volume_flux_dataset: str,
    net_current_source: Path,
    net_current_dataset: str,
    source_label: str,
) -> None:
    import h5py

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["source_mgxs"] = str(input_h5)
        h5.attrs["source_label"] = source_label
        h5.attrs["volume_flux_source"] = str(volume_flux_source)
        h5.attrs["volume_flux_dataset"] = volume_flux_dataset
        h5.attrs["net_current_source"] = str(net_current_source)
        h5.attrs["net_current_dataset"] = net_current_dataset
        h5.create_dataset("energy_bounds", data=energy_bounds)
        h5.create_dataset("mixture_names", data=np.asarray(mixture_names, dtype="S"))
        h5.create_dataset("face_names", data=np.asarray(face_names, dtype="S"))

        volume_dataset = h5.create_dataset("volume_flux", data=volume_flux_values)
        volume_dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        volume_dataset.attrs["layout"] = "[mixture, group]"

        current_dataset = h5.create_dataset("net_current_density", data=net_current_values)
        current_dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        current_dataset.attrs["face_names"] = np.asarray(face_names, dtype="S")
        current_dataset.attrs["layout"] = "[mixture, face, group]"
        current_dataset.attrs["sign_convention"] = "positive outward"


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "max": float(np.max(values)),
    }

"""Canonicalize low-order driver outputs for ADF/DF workflows."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from . import __version__
from .adf_augment import parse_faces
from .adf_sidecar import DEFAULT_CARTESIAN_FACES
from .homogeneous_face_flux import (
    load_net_current,
    load_volume_flux,
    reconstruct_homogeneous_face_flux,
)


SCHEMA = "openmc2donjon.low-order-driver.v1"
PASS_DECISION = "openmc2donjon_low_order_driver_passed"
CHECK_SCHEMA = "openmc2donjon.low-order-driver-contract.v1"
CHECK_PASS_DECISION = "openmc2donjon_low_order_driver_contract_passed"
CHECK_FAIL_DECISION = "openmc2donjon_low_order_driver_contract_failed"


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
    net_current_sign_convention_input: str | None = None
    net_current_sign_convention_source: str | None = None
    net_current_sign_convention_output: str = "positive outward"
    net_current_sign_multiplier: float = 1.0


@dataclass(frozen=True)
class LowOrderDriverCheckReport:
    input_h5: Path
    driver_h5: Path
    ok: bool
    decision: str
    mixture_names: tuple[str, ...] = ()
    face_names: tuple[str, ...] = ()
    energy_groups: int = 0
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    volume_flux_minimum: float | None = None
    volume_flux_median: float | None = None
    volume_flux_maximum: float | None = None
    net_current_minimum: float | None = None
    net_current_median: float | None = None
    net_current_maximum: float | None = None
    homogeneous_face_flux_minimum: float | None = None
    homogeneous_face_flux_median: float | None = None
    homogeneous_face_flux_maximum: float | None = None


def create_low_order_driver(
    input_h5: Path,
    output_h5: Path,
    *,
    volume_flux: str | Path,
    net_current: str | Path,
    faces: tuple[str, ...] | None = None,
    net_current_sign_convention: str | None = None,
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
        sign_convention=net_current_sign_convention,
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
        net_current_sign_convention_input=current.current_sign_convention_input,
        net_current_sign_convention_source=current.current_sign_convention_source,
        net_current_sign_convention_output=current.current_sign_convention_output,
        net_current_sign_multiplier=current.current_sign_multiplier,
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
        net_current_sign_convention_input=current.current_sign_convention_input,
        net_current_sign_convention_source=current.current_sign_convention_source,
        net_current_sign_convention_output=current.current_sign_convention_output
        or "positive outward",
        net_current_sign_multiplier=current.current_sign_multiplier,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def check_low_order_driver(
    input_h5: Path,
    driver_h5: Path,
    *,
    faces: tuple[str, ...] | None = None,
    face_widths: tuple[float, ...] | None = None,
    summary_json: Path | None = None,
) -> LowOrderDriverCheckReport:
    """Validate a canonical low-order driver handoff against an MGXS handoff."""

    input_h5 = Path(input_h5)
    driver_h5 = Path(driver_h5)
    errors: list[str] = []
    warnings: list[str] = []
    mixture_names: tuple[str, ...] = ()
    face_names: tuple[str, ...] = ()
    energy_groups = 0
    volume = current = homogeneous = None

    try:
        metadata = _read_mgxs_metadata(input_h5)
        mixture_names = metadata["mixture_names"]
        energy_bounds = metadata["energy_bounds"]
        energy_groups = int(energy_bounds.size - 1)
        expected_faces = None if faces is None else tuple(parse_faces(",".join(faces)) or ())
        if expected_faces is not None and not expected_faces:
            raise ValueError("at least one expected face must be selected")
        payload = _read_canonical_driver(
            driver_h5,
            energy_bounds=energy_bounds,
            mixture_names=mixture_names,
            expected_faces=expected_faces,
        )
        volume = payload["volume_flux"]
        current = payload["net_current"]
        face_names = payload["face_names"]

        if "source_label" not in payload["attrs"]:
            warnings.append("driver root attribute source_label is missing")
        if face_widths is not None:
            widths = _resolve_face_widths(face_widths, face_names)
            transport_total = _read_transport_total(input_h5, mixture_names, energy_groups)
            diffusion = 1.0 / (3.0 * transport_total)
            homogeneous = reconstruct_homogeneous_face_flux(
                volume,
                current,
                diffusion=diffusion,
                face_widths=widths,
            )
            if np.any(homogeneous <= 0.0):
                errors.append("reconstructed homogeneous face flux has non-positive bins")
    except Exception as exc:
        errors.append(str(exc))

    ok = not errors
    report = LowOrderDriverCheckReport(
        input_h5=input_h5,
        driver_h5=driver_h5,
        ok=ok,
        decision=CHECK_PASS_DECISION if ok else CHECK_FAIL_DECISION,
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
        errors=tuple(errors),
        warnings=tuple(warnings),
        **_check_stats(volume, current, homogeneous),
    )
    print_check_report(report)
    if summary_json is not None:
        write_check_summary(summary_json, report)
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
    print(
        "  net_current_sign: "
        f"input={report.net_current_sign_convention_input or 'positive outward'} "
        f"source={report.net_current_sign_convention_source or 'default'} "
        f"multiplier={report.net_current_sign_multiplier:g} "
        f"output={report.net_current_sign_convention_output}"
    )
    print()
    print("Low-order driver decision")
    print(f"  {PASS_DECISION}")


def print_check_report(report: LowOrderDriverCheckReport) -> None:
    print("OpenMC-to-DONJON low-order driver contract")
    print(f"  schema: {CHECK_SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  driver: {report.driver_h5}")
    status = "PASS" if report.ok else "FAIL"
    print(
        f"  {status} mixtures={len(report.mixture_names)} "
        f"groups={report.energy_groups} faces={','.join(report.face_names) or 'none'}"
    )
    if report.volume_flux_minimum is not None:
        print(
            "  volume_flux range: "
            f"min={report.volume_flux_minimum:.6g} "
            f"median={report.volume_flux_median:.6g} "
            f"max={report.volume_flux_maximum:.6g}"
        )
    if report.net_current_minimum is not None:
        print(
            "  net_current_density range: "
            f"min={report.net_current_minimum:.6g} "
            f"median={report.net_current_median:.6g} "
            f"max={report.net_current_maximum:.6g}"
        )
    if report.homogeneous_face_flux_minimum is not None:
        print(
            "  homogeneous_face_flux range: "
            f"min={report.homogeneous_face_flux_minimum:.6g} "
            f"median={report.homogeneous_face_flux_median:.6g} "
            f"max={report.homogeneous_face_flux_maximum:.6g}"
        )
    for warning in report.warnings:
        print(f"  WARN {warning}")
    for error in report.errors:
        print(f"  FAIL {error}")
    print()
    print("Low-order driver contract decision")
    print(f"  {report.decision}")


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
        "net_current_sign_convention_input": report.net_current_sign_convention_input,
        "net_current_sign_convention_source": report.net_current_sign_convention_source,
        "net_current_sign_convention_output": report.net_current_sign_convention_output,
        "net_current_sign_multiplier": report.net_current_sign_multiplier,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_check_summary(path: Path, report: LowOrderDriverCheckReport) -> None:
    payload = {
        "schema": CHECK_SCHEMA,
        "package_version": __version__,
        "decision": report.decision,
        "ok": report.ok,
        "input_h5": str(report.input_h5),
        "driver_h5": str(report.driver_h5),
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "volume_flux_min": report.volume_flux_minimum,
        "volume_flux_median": report.volume_flux_median,
        "volume_flux_max": report.volume_flux_maximum,
        "net_current_min": report.net_current_minimum,
        "net_current_median": report.net_current_median,
        "net_current_max": report.net_current_maximum,
        "homogeneous_face_flux_min": report.homogeneous_face_flux_minimum,
        "homogeneous_face_flux_median": report.homogeneous_face_flux_median,
        "homogeneous_face_flux_max": report.homogeneous_face_flux_maximum,
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


def _read_canonical_driver(
    path: Path,
    *,
    energy_bounds: np.ndarray,
    mixture_names: tuple[str, ...],
    expected_faces: tuple[str, ...] | None,
) -> dict[str, object]:
    import h5py

    if not path.exists():
        raise FileNotFoundError(f"low-order driver HDF5 does not exist: {path}")
    with h5py.File(path, "r") as h5:
        attrs = {str(key): h5.attrs[key] for key in h5.attrs}
        schema = _decode_text(h5.attrs.get("schema", ""))
        if schema != SCHEMA:
            raise ValueError(f"driver schema must be {SCHEMA!r}, got {schema!r}")
        for name in ("energy_bounds", "mixture_names", "face_names", "volume_flux", "net_current_density"):
            if name not in h5:
                raise ValueError(f"driver missing /{name}")
        driver_energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
        if driver_energy_bounds.shape != energy_bounds.shape or not np.array_equal(
            driver_energy_bounds,
            energy_bounds,
        ):
            raise ValueError("driver /energy_bounds does not match MGXS /energy_bounds")

        driver_mixtures = tuple(_decode_name_array(h5["mixture_names"][:]).reshape(-1))
        if driver_mixtures != mixture_names:
            raise ValueError(
                f"driver mixture_names {driver_mixtures!r} do not match MGXS {mixture_names!r}"
            )
        face_names = tuple(_decode_name_array(h5["face_names"][:]).reshape(-1))
        if not face_names:
            raise ValueError("driver face_names is empty")
        if expected_faces is not None and face_names != expected_faces:
            raise ValueError(
                f"driver face_names {face_names!r} do not match expected {expected_faces!r}"
            )

        volume = np.asarray(h5["volume_flux"][:], dtype=float)
        current = np.asarray(h5["net_current_density"][:], dtype=float)
        expected_volume_shape = (len(mixture_names), energy_bounds.size - 1)
        expected_current_shape = (len(mixture_names), len(face_names), energy_bounds.size - 1)
        if volume.shape != expected_volume_shape:
            raise ValueError(f"driver /volume_flux shape {volume.shape} != {expected_volume_shape}")
        if current.shape != expected_current_shape:
            raise ValueError(
                f"driver /net_current_density shape {current.shape} != {expected_current_shape}"
            )
        sign = _decode_text(h5["net_current_density"].attrs.get("sign_convention", ""))
        if sign != "positive outward":
            raise ValueError(
                "driver /net_current_density sign_convention must be 'positive outward'"
            )
    _validate_values(volume, current)
    return {
        "attrs": attrs,
        "volume_flux": volume,
        "net_current": current,
        "face_names": face_names,
    }


def _read_transport_total(
    path: Path,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> np.ndarray:
    import h5py

    out = np.zeros((len(mixture_names), energy_groups), dtype=float)
    with h5py.File(path, "r") as h5:
        for index, name in enumerate(mixture_names):
            dataset = f"mixtures/{name}/transport_total"
            if dataset not in h5:
                raise ValueError(f"mixture {name}: missing transport_total dataset")
            values = np.asarray(h5[dataset][:], dtype=float).reshape(-1)
            if values.shape != (energy_groups,):
                raise ValueError(
                    f"mixture {name}: transport_total shape {values.shape} != ({energy_groups},)"
                )
            if np.any(values <= 0.0) or not np.all(np.isfinite(values)):
                raise ValueError(f"mixture {name}: transport_total must be positive and finite")
            out[index] = values
    return out


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
    net_current_sign_convention_input: str | None,
    net_current_sign_convention_source: str | None,
    net_current_sign_convention_output: str | None,
    net_current_sign_multiplier: float,
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
        h5.attrs["net_current_sign_convention_input"] = (
            net_current_sign_convention_input or "positive outward"
        )
        h5.attrs["net_current_sign_convention_source"] = (
            net_current_sign_convention_source or "default"
        )
        h5.attrs["net_current_sign_convention_output"] = (
            net_current_sign_convention_output or "positive outward"
        )
        h5.attrs["net_current_sign_multiplier"] = float(net_current_sign_multiplier)
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


def _resolve_face_widths(
    face_widths: tuple[float, ...],
    face_names: tuple[str, ...],
) -> tuple[float, ...]:
    if len(face_widths) == 1:
        out = tuple(float(face_widths[0]) for _ in face_names)
    else:
        out = tuple(float(value) for value in face_widths)
    if len(out) != len(face_names):
        raise ValueError("face width count must be one or match the number of faces")
    if any((not np.isfinite(value) or value <= 0.0) for value in out):
        raise ValueError("face widths must be positive and finite")
    return out


def _check_stats(
    volume: np.ndarray | None,
    current: np.ndarray | None,
    homogeneous: np.ndarray | None,
) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "volume_flux_minimum": None,
        "volume_flux_median": None,
        "volume_flux_maximum": None,
        "net_current_minimum": None,
        "net_current_median": None,
        "net_current_maximum": None,
        "homogeneous_face_flux_minimum": None,
        "homogeneous_face_flux_median": None,
        "homogeneous_face_flux_maximum": None,
    }
    if volume is not None:
        stats = _stats(volume)
        out.update(
            volume_flux_minimum=stats["min"],
            volume_flux_median=stats["median"],
            volume_flux_maximum=stats["max"],
        )
    if current is not None:
        stats = _stats(current)
        out.update(
            net_current_minimum=stats["min"],
            net_current_median=stats["median"],
            net_current_maximum=stats["max"],
        )
    if homogeneous is not None:
        stats = _stats(homogeneous)
        out.update(
            homogeneous_face_flux_minimum=stats["min"],
            homogeneous_face_flux_median=stats["median"],
            homogeneous_face_flux_maximum=stats["max"],
        )
    return out


def _decode_name_array(values: object) -> np.ndarray:
    raw = np.asarray(values)
    out = np.empty(raw.shape, dtype=object)
    for index in np.ndindex(raw.shape):
        out[index] = _decode_text(raw[index])
    return out


def _decode_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8").rstrip("\x00")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8").rstrip("\x00")
    if hasattr(value, "item"):
        return _decode_text(value.item())
    return str(value)


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "max": float(np.max(values)),
    }

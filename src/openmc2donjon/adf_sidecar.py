"""Create ADF sidecar HDF5 files from an MGXS handoff."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from .adf_augment import parse_faces
from .hdf5_names import read_mixture_names


SCHEMA = "openmc2donjon.adf-sidecar.v1"
PASS_DECISION = "openmc2donjon_adf_sidecar_passed"
DEFAULT_CARTESIAN_FACES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
SURFACE_FLUX_DATASETS = (
    "surface_flux/mean",
    "heterogeneous_face_flux",
    "surface_flux_proxy",
    "surface_flux",
    "adf_surface_flux",
)
HOMOGENEOUS_FACE_FLUX_DATASETS = (
    "homogeneous_face_flux",
    "homogeneous_face_flux/mean",
    "homogeneous/face_flux",
    "face_flux/homogeneous",
    "homogeneous_flux",
)


@dataclass(frozen=True)
class AdfSidecarReport:
    input_h5: Path
    output_h5: Path
    mode: str
    mixture_names: tuple[str, ...]
    face_names: tuple[str, ...]
    energy_groups: int
    value: float | None = None
    adf_kind: str = ""
    adf_real: bool = False
    invalid_count: int = 0
    invalid_filled_count: int = 0
    clip_min: float | None = None
    clip_max: float | None = None
    minimum: float | None = None
    median: float | None = None
    maximum: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class FaceFluxPayload:
    values: np.ndarray
    face_names: tuple[str, ...]
    path: Path
    dataset_path: str


def create_unity_adf_sidecar(
    input_h5: Path,
    output_h5: Path,
    *,
    faces: tuple[str, ...] | None = None,
    value: float = 1.0,
    force: bool = False,
    summary_json: Path | None = None,
) -> AdfSidecarReport:
    """Create a compact root ``/adf`` sidecar filled with one constant value.

    This is an identity discontinuity-factor payload for workflow integration
    and plumbing tests.  It is deliberately marked ``adf_real=false``.
    """

    import h5py

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("--value must be positive and finite")

    face_names = tuple(faces or DEFAULT_CARTESIAN_FACES)
    face_names = tuple(parse_faces(",".join(face_names)) or ())
    if not face_names:
        raise ValueError("at least one ADF face must be selected")

    with h5py.File(input_h5, "r") as h5:
        mixture_names = _mixture_names(h5)
        energy_groups = _energy_groups(h5)

    values = np.full(
        (len(mixture_names), len(face_names), energy_groups),
        float(value),
        dtype=float,
    )
    report = AdfSidecarReport(
        input_h5=input_h5,
        output_h5=output_h5,
        mode="unity",
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
        value=float(value),
        adf_kind="unity",
        adf_real=False,
        minimum=float(value),
        median=float(value),
        maximum=float(value),
        metadata={
            "adf_source": "openmc2donjon make-adf-sidecar --mode unity",
            "adf_definition": (
                "identity discontinuity factors for workflow integration; "
                "replace with physics ADF/DF values for production neutronics"
            ),
        },
    )
    _write_sidecar(output_h5, values, report, force=True)
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def create_flux_ratio_adf_sidecar(
    input_h5: Path,
    output_h5: Path,
    *,
    surface_flux: str | Path,
    homogeneous_face_flux: str | Path,
    faces: tuple[str, ...] | None = None,
    force: bool = False,
    summary_json: Path | None = None,
    invalid_fill: float | None = None,
    clip_min: float | None = None,
    clip_max: float | None = None,
    adf_kind: str = "flux-ratio",
    adf_real: bool = True,
    adf_source_label: str | None = None,
) -> AdfSidecarReport:
    """Create an ADF sidecar from heterogeneous and homogeneous face fluxes."""

    import h5py

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    _validate_fill_and_clip(invalid_fill, clip_min, clip_max)

    expected_faces = None if faces is None else tuple(parse_faces(",".join(faces)) or ())
    with h5py.File(input_h5, "r") as h5:
        mixture_names = _mixture_names(h5)
        energy_groups = _energy_groups(h5)

    surface = load_face_flux_payload(
        surface_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        expected_faces=expected_faces,
        candidates=SURFACE_FLUX_DATASETS,
        label="surface flux",
        allow_negative=False,
    )
    homogeneous = load_face_flux_payload(
        homogeneous_face_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        expected_faces=surface.face_names,
        candidates=HOMOGENEOUS_FACE_FLUX_DATASETS,
        label="homogeneous face flux",
        allow_negative=True,
    )
    if homogeneous.face_names != surface.face_names:
        raise ValueError(
            "surface and homogeneous face flux names differ: "
            f"{surface.face_names!r} != {homogeneous.face_names!r}"
        )

    values, invalid_count, invalid_filled_count = _adf_from_flux_ratio(
        surface.values,
        homogeneous.values,
        invalid_fill=invalid_fill,
        clip_min=clip_min,
        clip_max=clip_max,
    )
    stats = _stats(values)
    report = AdfSidecarReport(
        input_h5=input_h5,
        output_h5=output_h5,
        mode="flux-ratio",
        mixture_names=mixture_names,
        face_names=surface.face_names,
        energy_groups=energy_groups,
        adf_kind=adf_kind,
        adf_real=adf_real,
        invalid_count=invalid_count,
        invalid_filled_count=invalid_filled_count,
        clip_min=clip_min,
        clip_max=clip_max,
        minimum=stats["min"],
        median=stats["median"],
        maximum=stats["max"],
        metadata={
            "adf_source": adf_source_label
            or "openmc2donjon make-adf-sidecar --mode flux-ratio",
            "adf_definition": (
                "ADF = heterogeneous face flux / homogeneous face flux"
            ),
            "adf_surface_flux": str(surface.path),
            "adf_surface_flux_dataset": surface.dataset_path,
            "adf_homogeneous_face_flux": str(homogeneous.path),
            "adf_homogeneous_face_flux_dataset": homogeneous.dataset_path,
        },
    )
    _write_sidecar(output_h5, values, report, force=True)
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: AdfSidecarReport) -> None:
    print("OpenMC-to-DONJON ADF sidecar")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_h5}")
    value = "" if report.value is None else f" value={report.value:g}"
    print(
        f"  mode={report.mode}{value} "
        f"mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"faces={','.join(report.face_names)}"
    )
    print(f"  adf_kind={report.adf_kind or report.mode} adf_real={_bool_text(report.adf_real)}")
    if report.minimum is not None and report.median is not None and report.maximum is not None:
        print(
            "  ADF range: "
            f"min={report.minimum:.6g} median={report.median:.6g} max={report.maximum:.6g}"
        )
    if report.invalid_count:
        print(
            f"  invalid_bins={report.invalid_count} "
            f"filled={report.invalid_filled_count}"
        )
    print()
    print("ADF sidecar decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: AdfSidecarReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": PASS_DECISION,
        "input_h5": str(report.input_h5),
        "output_h5": str(report.output_h5),
        "mode": report.mode,
        "adf_kind": report.adf_kind or report.mode,
        "adf_real": report.adf_real,
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
        "value": report.value,
        "invalid_count": report.invalid_count,
        "invalid_filled_count": report.invalid_filled_count,
        "clip_min": report.clip_min,
        "clip_max": report.clip_max,
        "min": report.minimum,
        "median": report.median,
        "max": report.maximum,
    }
    if report.metadata:
        payload.update(report.metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_face_flux_payload(
    reference: str | Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    expected_faces: tuple[str, ...] | None,
    candidates: tuple[str, ...],
    label: str,
    allow_negative: bool = False,
) -> FaceFluxPayload:
    """Load face flux values normalized to ``(mixture, face, group)``."""

    import h5py

    path, requested_dataset = _split_dataset_reference(reference)
    if not path.exists():
        raise FileNotFoundError(f"{label} HDF5 does not exist: {path}")
    with h5py.File(path, "r") as h5:
        obj, dataset_path = _select_dataset(
            h5,
            requested=requested_dataset,
            candidates=candidates,
            label=label,
        )
        values = np.asarray(obj[:], dtype=float)
        declared_faces = _names_from_hdf5(obj, h5, ("face_names", "faces", "adf_names"))
        face_names = _resolve_face_names(
            declared_faces,
            expected_faces=expected_faces,
            face_count=_infer_face_count(values, energy_groups),
            label=f"{label} {path}:{dataset_path}",
        )
        declared_mixtures = _names_from_hdf5(
            obj,
            h5,
            ("mixture_names", "mixtures", "domain_names"),
        )
        normalized = _normalize_face_flux_values(
            values,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            face_names=face_names,
            declared_mixtures=declared_mixtures,
            label=f"{label} {path}:{dataset_path}",
            allow_negative=allow_negative,
        )
    return FaceFluxPayload(
        values=normalized,
        face_names=face_names,
        path=path,
        dataset_path=dataset_path,
    )


def _write_sidecar(
    output_h5: Path,
    values: np.ndarray,
    report: AdfSidecarReport,
    *,
    force: bool,
) -> None:
    import h5py

    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    output_h5.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_h5, "w") as h5:
        h5.attrs["schema"] = SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["adf_kind"] = report.adf_kind or report.mode
        h5.attrs["adf_real"] = _bool_text(report.adf_real)
        h5.attrs["source_mgxs"] = str(report.input_h5)
        h5.attrs["adf_invalid_count"] = int(report.invalid_count)
        h5.attrs["adf_invalid_filled_count"] = int(report.invalid_filled_count)
        if report.clip_min is not None and report.clip_max is not None:
            h5.attrs["adf_clip_min"] = float(report.clip_min)
            h5.attrs["adf_clip_max"] = float(report.clip_max)
            h5.attrs["adf_clip_policy"] = "clip_after_invalid_fill"
        if report.metadata:
            for key, value in report.metadata.items():
                h5.attrs[str(key)] = value
        dataset = h5.create_dataset("adf", data=values)
        dataset.attrs["mixture_names"] = np.asarray(report.mixture_names, dtype="S")
        dataset.attrs["face_names"] = np.asarray(report.face_names, dtype="S")


def _split_dataset_reference(reference: str | Path) -> tuple[Path, str | None]:
    raw = str(reference)
    if "::" not in raw:
        return Path(raw), None
    path, dataset = raw.split("::", 1)
    dataset = dataset.strip("/")
    if not dataset:
        raise ValueError(f"empty dataset in HDF5 reference: {reference}")
    return Path(path), dataset


def _select_dataset(h5, *, requested: str | None, candidates: tuple[str, ...], label: str):
    if requested is not None:
        if requested not in h5:
            raise ValueError(f"{label} dataset not found: /{requested}")
        obj = h5[requested]
        if hasattr(obj, "keys"):
            raise ValueError(f"{label} path is a group, not a dataset: /{requested}")
        return obj, requested

    for dataset_path in candidates:
        if dataset_path not in h5:
            continue
        obj = h5[dataset_path]
        if not hasattr(obj, "keys"):
            return obj, dataset_path
    rendered = ", ".join(f"/{candidate}" for candidate in candidates)
    raise ValueError(f"{label} HDF5 must contain one of: {rendered}")


def _infer_face_count(values: np.ndarray, energy_groups: int) -> int:
    if values.ndim == 3:
        if values.shape[-1] == energy_groups:
            return int(values.shape[-2])
        if values.shape[-2] == energy_groups:
            return int(values.shape[-1])
    if values.ndim == 4:
        if values.shape[-2] == energy_groups:
            return int(values.shape[-1])
        if values.shape[-1] == energy_groups:
            return int(values.shape[-2])
    raise ValueError(
        "face flux values must have shape (M,F,G), (M,G,F), "
        "(Y,X,G,F), or (Y,X,F,G)"
    )


def _resolve_face_names(
    declared: Any,
    *,
    expected_faces: tuple[str, ...] | None,
    face_count: int,
    label: str,
) -> tuple[str, ...]:
    declared_names = None if declared is None else tuple(_flatten_names(declared))
    if expected_faces is not None:
        if len(expected_faces) != face_count:
            raise ValueError(
                f"{label}: expected {len(expected_faces)} faces, but flux has {face_count}"
            )
        if declared_names is not None and declared_names != expected_faces:
            raise ValueError(
                f"{label}: declared faces {declared_names!r} do not match "
                f"expected faces {expected_faces!r}"
            )
        return expected_faces
    if declared_names is None:
        return tuple(f"FD_{index + 1:05d}" for index in range(face_count))
    if len(declared_names) != face_count:
        raise ValueError(
            f"{label}: declared {len(declared_names)} faces, but flux has {face_count}"
        )
    return declared_names


def _normalize_face_flux_values(
    values: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    face_names: tuple[str, ...],
    declared_mixtures: Any,
    label: str,
    allow_negative: bool,
) -> np.ndarray:
    if values.ndim == 3:
        normalized = _normalize_rank3_flux(
            values,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            face_names=face_names,
            declared_mixtures=declared_mixtures,
            label=label,
        )
    elif values.ndim == 4:
        normalized = _normalize_rank4_flux(
            values,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            face_names=face_names,
            declared_mixtures=declared_mixtures,
            label=label,
        )
    else:
        raise ValueError(f"{label}: expected 3D or 4D face flux dataset")
    if not np.all(np.isfinite(normalized)):
        raise ValueError(f"{label}: flux values must be finite")
    if not allow_negative and np.any(normalized < 0.0):
        raise ValueError(f"{label}: flux values must be non-negative")
    return normalized


def _normalize_rank3_flux(
    values: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    face_names: tuple[str, ...],
    declared_mixtures: Any,
    label: str,
) -> np.ndarray:
    if values.shape == (len(mixture_names), len(face_names), energy_groups):
        normalized = values
    elif values.shape == (len(mixture_names), energy_groups, len(face_names)):
        normalized = np.transpose(values, (0, 2, 1))
    else:
        raise ValueError(
            f"{label}: shape {values.shape} is not compatible with "
            f"{len(mixture_names)} mixtures, {len(face_names)} faces, "
            f"{energy_groups} groups"
        )
    declared_names = None if declared_mixtures is None else tuple(_flatten_names(declared_mixtures))
    if declared_names is None:
        return normalized
    if set(declared_names) != set(mixture_names):
        raise ValueError(
            f"{label}: declared mixtures {declared_names!r} do not match "
            f"MGXS mixtures {mixture_names!r}"
        )
    if declared_names == mixture_names:
        return normalized
    index_by_name = {name: index for index, name in enumerate(declared_names)}
    return np.stack([normalized[index_by_name[name]] for name in mixture_names])


def _normalize_rank4_flux(
    values: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    face_names: tuple[str, ...],
    declared_mixtures: Any,
    label: str,
) -> np.ndarray:
    if values.shape[-2:] == (energy_groups, len(face_names)):
        grid_values = np.moveaxis(values, -1, -2)
    elif values.shape[-2:] == (len(face_names), energy_groups):
        grid_values = values
    else:
        raise ValueError(
            f"{label}: last dimensions {values.shape[-2:]} are not "
            f"(groups, faces) or (faces, groups)"
        )
    if declared_mixtures is None:
        raise ValueError(f"{label}: 4D flux datasets require mixture_names")
    names = np.asarray(_decode_name_array(declared_mixtures), dtype=object)
    if names.shape != grid_values.shape[:2]:
        raise ValueError(
            f"{label}: mixture_names shape {names.shape} does not match "
            f"flux mesh shape {grid_values.shape[:2]}"
        )
    out: dict[str, np.ndarray] = {}
    for index in np.ndindex(names.shape):
        name = str(names[index])
        if name in out:
            raise ValueError(f"{label}: duplicate mixture name {name!r} in flux mesh")
        out[name] = grid_values[index]
    if set(out) != set(mixture_names):
        raise ValueError(
            f"{label}: flux mesh mixtures {tuple(out)!r} do not match "
            f"MGXS mixtures {mixture_names!r}"
        )
    return np.stack([out[name] for name in mixture_names])


def _adf_from_flux_ratio(
    surface: np.ndarray,
    homogeneous: np.ndarray,
    *,
    invalid_fill: float | None,
    clip_min: float | None,
    clip_max: float | None,
) -> tuple[np.ndarray, int, int]:
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.divide(surface, homogeneous)
    valid = (
        np.isfinite(raw)
        & np.isfinite(surface)
        & np.isfinite(homogeneous)
        & (surface > 0.0)
        & (homogeneous > 0.0)
        & (raw > 0.0)
    )
    invalid_count = int(raw.size - np.count_nonzero(valid))
    if invalid_count and invalid_fill is None:
        raise ValueError(
            f"flux-ratio ADF has {invalid_count} invalid bin(s); pass "
            "--invalid-fill for an explicit fill policy"
        )
    safe = np.array(raw, dtype=float, copy=True)
    invalid_filled_count = 0
    if invalid_count:
        invalid_filled_count = invalid_count
        safe[~valid] = float(invalid_fill)
        safe = np.nan_to_num(
            safe,
            nan=float(invalid_fill),
            posinf=float(invalid_fill),
            neginf=float(invalid_fill),
        )
    if clip_min is not None and clip_max is not None:
        safe = np.clip(safe, clip_min, clip_max)
    if not np.all(np.isfinite(safe)) or np.any(safe <= 0.0):
        raise ValueError("ADF values must be positive and finite after fill/clip")
    return safe, invalid_count, invalid_filled_count


def _validate_fill_and_clip(
    invalid_fill: float | None,
    clip_min: float | None,
    clip_max: float | None,
) -> None:
    if invalid_fill is not None and (not np.isfinite(invalid_fill) or invalid_fill <= 0.0):
        raise ValueError("--invalid-fill must be positive and finite")
    if (clip_min is None) ^ (clip_max is None):
        raise ValueError("--clip-min and --clip-max must be supplied together")
    if clip_min is not None and clip_max is not None:
        if not np.isfinite(clip_min) or not np.isfinite(clip_max):
            raise ValueError("--clip-min and --clip-max must be finite")
        if clip_min <= 0.0:
            raise ValueError("--clip-min must be positive")
        if clip_min > clip_max:
            raise ValueError("--clip-min must be <= --clip-max")


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "max": float(np.max(values)),
    }


def _names_from_hdf5(obj, root, keys: tuple[str, ...]):
    for owner in (obj, root):
        for key in keys:
            if key in owner.attrs:
                return owner.attrs[key]
    for key in keys:
        if key in root and not hasattr(root[key], "keys"):
            return root[key][:]
    return None


def _flatten_names(values: Any) -> tuple[str, ...]:
    return tuple(str(name) for name in _decode_name_array(values).reshape(-1))


def _decode_name_array(values: Any) -> np.ndarray:
    raw = np.asarray(values)
    if raw.shape == ():
        return np.asarray(_decode_text(raw[()]), dtype=object)
    out = np.empty(raw.shape, dtype=object)
    for index in np.ndindex(raw.shape):
        out[index] = _decode_text(raw[index])
    return out


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8").rstrip("\x00")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8").rstrip("\x00")
    if hasattr(value, "item"):
        return _decode_text(value.item())
    return str(value)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _mixture_names(h5) -> tuple[str, ...]:
    return read_mixture_names(h5)


def _energy_groups(h5) -> int:
    if "energy_groups" in h5.attrs:
        ngroups = int(h5.attrs["energy_groups"])
    elif "energy_bounds" in h5:
        ngroups = int(h5["energy_bounds"].shape[0]) - 1
    else:
        raise ValueError("input HDF5 must define energy_groups or energy_bounds")
    if ngroups <= 0:
        raise ValueError("energy group count must be positive")
    return ngroups

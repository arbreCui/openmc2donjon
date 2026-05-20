"""Build homogeneous face-flux HDF5 inputs for flux-ratio ADF sidecars."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from .adf_augment import parse_faces
from .adf_sidecar import DEFAULT_CARTESIAN_FACES


SCHEMA = "openmc2donjon.homogeneous-face-flux.v1"
PASS_DECISION = "openmc2donjon_homogeneous_face_flux_passed"
VOLUME_FLUX_DATASETS = (
    "volume_flux/average",
    "volume_flux",
    "scalar_flux",
    "flux",
)
NET_CURRENT_DATASETS = (
    "net_current_density",
    "net_current",
    "boundary_currents/net",
    "current_density",
)


@dataclass(frozen=True)
class HomogeneousFaceFluxReport:
    input_h5: Path
    output_h5: Path
    volume_flux_source: Path
    volume_flux_dataset: str
    net_current_source: Path
    net_current_dataset: str
    mixture_names: tuple[str, ...]
    face_names: tuple[str, ...]
    energy_groups: int
    face_widths: tuple[float, ...]
    minimum: float
    median: float
    maximum: float
    nonpositive_count: int
    net_current_sign_convention_input: str | None = None
    net_current_sign_convention_source: str | None = None
    net_current_sign_convention_output: str | None = None
    net_current_sign_multiplier: float = 1.0


@dataclass(frozen=True)
class LoadedArray:
    values: np.ndarray
    path: Path
    dataset_path: str
    current_sign_convention_input: str | None = None
    current_sign_convention_source: str | None = None
    current_sign_convention_output: str | None = None
    current_sign_multiplier: float = 1.0


def create_homogeneous_face_flux(
    input_h5: Path,
    output_h5: Path,
    *,
    volume_flux: str | Path,
    net_current: str | Path,
    faces: tuple[str, ...] | None = None,
    face_widths: tuple[float, ...] | None = None,
    net_current_sign_convention: str | None = None,
    force: bool = False,
    summary_json: Path | None = None,
) -> HomogeneousFaceFluxReport:
    """Reconstruct homogeneous face flux with a diffusion current relation.

    The convention is outward net current density per face:

    ``phi_face = phi_avg - J_out * width / (2 D)``.
    """

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")

    face_names = tuple(faces or DEFAULT_CARTESIAN_FACES)
    face_names = tuple(parse_faces(",".join(face_names)) or ())
    widths = _resolve_face_widths(face_widths, face_names)
    metadata = _read_mgxs(input_h5)
    mixture_names = metadata["mixture_names"]
    energy_bounds = metadata["energy_bounds"]
    diffusion = metadata["diffusion"]
    energy_groups = diffusion.shape[1]

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
    values = reconstruct_homogeneous_face_flux(
        volume.values,
        current.values,
        diffusion=diffusion,
        face_widths=widths,
    )
    if not np.all(np.isfinite(values)):
        raise ValueError("homogeneous face flux contains non-finite values")

    _write_hdf5(
        output_h5,
        values=values,
        energy_bounds=energy_bounds,
        mixture_names=mixture_names,
        face_names=face_names,
        face_widths=widths,
        input_h5=input_h5,
        volume_flux=volume,
        net_current=current,
    )
    stats = _stats(values)
    report = HomogeneousFaceFluxReport(
        input_h5=input_h5,
        output_h5=output_h5,
        volume_flux_source=volume.path,
        volume_flux_dataset=volume.dataset_path,
        net_current_source=current.path,
        net_current_dataset=current.dataset_path,
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
        face_widths=widths,
        minimum=stats["min"],
        median=stats["median"],
        maximum=stats["max"],
        nonpositive_count=int(np.count_nonzero(values <= 0.0)),
        net_current_sign_convention_input=current.current_sign_convention_input,
        net_current_sign_convention_source=current.current_sign_convention_source,
        net_current_sign_convention_output=current.current_sign_convention_output,
        net_current_sign_multiplier=current.current_sign_multiplier,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def reconstruct_homogeneous_face_flux(
    volume_flux: np.ndarray,
    net_current: np.ndarray,
    *,
    diffusion: np.ndarray,
    face_widths: tuple[float, ...],
) -> np.ndarray:
    """Return homogeneous face flux as ``(M, F, G)``."""

    volume_flux = np.asarray(volume_flux, dtype=float)
    net_current = np.asarray(net_current, dtype=float)
    diffusion = np.asarray(diffusion, dtype=float)
    widths = np.asarray(face_widths, dtype=float)
    if volume_flux.ndim != 2:
        raise ValueError("volume_flux must have shape (M, G)")
    if net_current.ndim != 3:
        raise ValueError("net_current must have shape (M, F, G)")
    if diffusion.shape != volume_flux.shape:
        raise ValueError(f"diffusion shape {diffusion.shape} != volume_flux shape {volume_flux.shape}")
    if net_current.shape != (volume_flux.shape[0], widths.size, volume_flux.shape[1]):
        raise ValueError(
            "net_current shape must be "
            f"({volume_flux.shape[0]}, {widths.size}, {volume_flux.shape[1]})"
        )
    if not np.all(np.isfinite(volume_flux)) or not np.all(np.isfinite(net_current)):
        raise ValueError("volume_flux and net_current values must be finite")
    if np.any(diffusion <= 0.0) or not np.all(np.isfinite(diffusion)):
        raise ValueError("diffusion values must be positive and finite")
    return volume_flux[:, np.newaxis, :] - (
        net_current * widths[np.newaxis, :, np.newaxis] / (2.0 * diffusion[:, np.newaxis, :])
    )


def load_volume_flux(
    reference: str | Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> LoadedArray:
    values, path, dataset_path, declared_mixtures, _declared_faces, _declared_sign = _load_dataset(
        reference,
        candidates=VOLUME_FLUX_DATASETS,
        label="volume flux",
    )
    normalized = _normalize_volume_flux(
        values,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        declared_mixtures=declared_mixtures,
        label=f"volume flux {path}:{dataset_path}",
    )
    return LoadedArray(values=normalized, path=path, dataset_path=dataset_path)


def load_net_current(
    reference: str | Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    face_names: tuple[str, ...],
    sign_convention: str | None = None,
) -> LoadedArray:
    values, path, dataset_path, declared_mixtures, declared_faces, declared_sign = _load_dataset(
        reference,
        candidates=NET_CURRENT_DATASETS,
        label="net current",
    )
    normalized = _normalize_net_current(
        values,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        face_names=face_names,
        declared_mixtures=declared_mixtures,
        declared_faces=declared_faces,
        label=f"net current {path}:{dataset_path}",
    )
    signed_values, sign_input, sign_source, sign_multiplier = _apply_net_current_sign_convention(
        normalized,
        declared_sign=declared_sign,
        override=sign_convention,
        label=f"net current {path}:{dataset_path}",
    )
    return LoadedArray(
        values=signed_values,
        path=path,
        dataset_path=dataset_path,
        current_sign_convention_input=sign_input,
        current_sign_convention_source=sign_source,
        current_sign_convention_output="positive outward",
        current_sign_multiplier=sign_multiplier,
    )


def print_report(report: HomogeneousFaceFluxReport) -> None:
    print("OpenMC-to-DONJON homogeneous face flux")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_h5}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"faces={','.join(report.face_names)}"
    )
    print(
        "  homogeneous_face_flux range: "
        f"min={report.minimum:.6g} median={report.median:.6g} max={report.maximum:.6g}"
    )
    if report.nonpositive_count:
        print(f"  nonpositive_bins={report.nonpositive_count}")
    if report.net_current_sign_convention_input is not None:
        print(
            "  net_current_sign: "
            f"input={report.net_current_sign_convention_input} "
            f"source={report.net_current_sign_convention_source} "
            f"multiplier={report.net_current_sign_multiplier:g} "
            f"output={report.net_current_sign_convention_output}"
        )
    print()
    print("Homogeneous face flux decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: HomogeneousFaceFluxReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": PASS_DECISION,
        "input_h5": str(report.input_h5),
        "output_h5": str(report.output_h5),
        "volume_flux": str(report.volume_flux_source),
        "volume_flux_dataset": report.volume_flux_dataset,
        "net_current": str(report.net_current_source),
        "net_current_dataset": report.net_current_dataset,
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
        "face_widths": list(report.face_widths),
        "min": report.minimum,
        "median": report.median,
        "max": report.maximum,
        "nonpositive_count": report.nonpositive_count,
        "net_current_sign_convention_input": report.net_current_sign_convention_input,
        "net_current_sign_convention_source": report.net_current_sign_convention_source,
        "net_current_sign_convention_output": report.net_current_sign_convention_output,
        "net_current_sign_multiplier": report.net_current_sign_multiplier,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_mgxs(path: Path) -> dict[str, Any]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError("input HDF5 must contain a /mixtures group")
        if "energy_bounds" not in h5:
            raise ValueError("input HDF5 must contain /energy_bounds")
        energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
        mixture_names = tuple(str(name) for name in h5["mixtures"])
        if not mixture_names:
            raise ValueError("input HDF5 contains no mixtures")
        diffusion = np.zeros((len(mixture_names), energy_bounds.size - 1), dtype=float)
        for index, name in enumerate(mixture_names):
            group = h5["mixtures"][name]
            if "transport_total" not in group:
                raise ValueError(f"mixture {name}: missing transport_total dataset")
            transport_total = np.asarray(group["transport_total"][:], dtype=float).reshape(-1)
            if transport_total.shape != (energy_bounds.size - 1,):
                raise ValueError(
                    f"mixture {name}: transport_total shape {transport_total.shape} "
                    f"does not match group count {energy_bounds.size - 1}"
                )
            if np.any(transport_total <= 0.0) or not np.all(np.isfinite(transport_total)):
                raise ValueError(f"mixture {name}: transport_total must be positive and finite")
            diffusion[index] = 1.0 / (3.0 * transport_total)
    return {
        "energy_bounds": energy_bounds,
        "mixture_names": mixture_names,
        "diffusion": diffusion,
    }


def _write_hdf5(
    path: Path,
    *,
    values: np.ndarray,
    energy_bounds: np.ndarray,
    mixture_names: tuple[str, ...],
    face_names: tuple[str, ...],
    face_widths: tuple[float, ...],
    input_h5: Path,
    volume_flux: LoadedArray,
    net_current: LoadedArray,
) -> None:
    import h5py

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["source"] = "diffusion current reconstruction"
        h5.attrs["formula"] = "phi_face = phi_avg - J_out * width / (2D)"
        h5.attrs["diffusion_source"] = "D = 1 / (3 * transport_total)"
        h5.attrs["source_mgxs"] = str(input_h5)
        h5.attrs["volume_flux"] = str(volume_flux.path)
        h5.attrs["volume_flux_dataset"] = volume_flux.dataset_path
        h5.attrs["net_current"] = str(net_current.path)
        h5.attrs["net_current_dataset"] = net_current.dataset_path
        h5.attrs["net_current_sign_convention_input"] = (
            net_current.current_sign_convention_input or "unknown"
        )
        h5.attrs["net_current_sign_convention_source"] = (
            net_current.current_sign_convention_source or "unknown"
        )
        h5.attrs["net_current_sign_convention_output"] = (
            net_current.current_sign_convention_output or "positive outward"
        )
        h5.attrs["net_current_sign_multiplier"] = float(net_current.current_sign_multiplier)
        h5.create_dataset("energy_bounds", data=energy_bounds)
        h5.create_dataset("mixture_names", data=np.asarray(mixture_names, dtype="S"))
        h5.create_dataset("face_names", data=np.asarray(face_names, dtype="S"))
        h5.create_dataset("face_widths", data=np.asarray(face_widths, dtype=float))
        dataset = h5.create_dataset("homogeneous_face_flux", data=values)
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        dataset.attrs["face_names"] = np.asarray(face_names, dtype="S")
        dataset.attrs["layout"] = "[mixture, face, group]"


def _load_dataset(
    reference: str | Path,
    *,
    candidates: tuple[str, ...],
    label: str,
) -> tuple[np.ndarray, Path, str, Any, Any, str | None]:
    import h5py

    path, requested = _split_dataset_reference(reference)
    if not path.exists():
        raise FileNotFoundError(f"{label} HDF5 does not exist: {path}")
    with h5py.File(path, "r") as h5:
        dataset_path = requested
        if dataset_path is None:
            for candidate in candidates:
                if candidate in h5 and not hasattr(h5[candidate], "keys"):
                    dataset_path = candidate
                    break
        if dataset_path is None:
            rendered = ", ".join(f"/{candidate}" for candidate in candidates)
            raise ValueError(f"{label} HDF5 must contain one of: {rendered}")
        if dataset_path not in h5:
            raise ValueError(f"{label} dataset not found: /{dataset_path}")
        obj = h5[dataset_path]
        if hasattr(obj, "keys"):
            raise ValueError(f"{label} path is a group, not a dataset: /{dataset_path}")
        values = np.asarray(obj[:], dtype=float)
        declared_mixtures = _names_from_hdf5(obj, h5, ("mixture_names", "mixtures", "domain_names"))
        declared_faces = _names_from_hdf5(obj, h5, ("face_names", "faces", "boundary_names"))
        declared_sign = _text_from_hdf5(
            obj,
            h5,
            ("sign_convention", "net_current_sign_convention", "current_sign_convention"),
        )
    return values, path, dataset_path, declared_mixtures, declared_faces, declared_sign


def _normalize_volume_flux(
    values: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    declared_mixtures: Any,
    label: str,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.ndim == 2:
        if values.shape != (len(mixture_names), energy_groups):
            raise ValueError(
                f"{label}: shape {values.shape} is not compatible with "
                f"({len(mixture_names)}, {energy_groups})"
            )
        declared_names = None if declared_mixtures is None else tuple(_flatten_names(declared_mixtures))
        return _reorder_by_declared_mixtures(values, declared_names, mixture_names, label)
    if values.ndim == 3:
        if values.shape[-1] != energy_groups:
            raise ValueError(f"{label}: last dimension must be energy group count {energy_groups}")
        if declared_mixtures is None:
            raise ValueError(f"{label}: 3D volume flux requires mixture_names mesh")
        names = _decode_name_array(declared_mixtures)
        if names.shape != values.shape[:2]:
            raise ValueError(
                f"{label}: mixture_names shape {names.shape} does not match "
                f"flux mesh shape {values.shape[:2]}"
            )
        return _mesh_values_to_mixture_order(values, names, mixture_names, label)
    raise ValueError(f"{label}: expected 2D or 3D dataset")


def _normalize_net_current(
    values: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    face_names: tuple[str, ...],
    declared_mixtures: Any,
    declared_faces: Any,
    label: str,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    declared_face_names = None if declared_faces is None else tuple(_flatten_names(declared_faces))
    if values.ndim == 3:
        face_count = len(declared_face_names or face_names)
        if values.shape == (len(mixture_names), face_count, energy_groups):
            normalized = values
        elif values.shape == (len(mixture_names), energy_groups, face_count):
            normalized = np.transpose(values, (0, 2, 1))
        else:
            raise ValueError(
                f"{label}: shape {values.shape} is not compatible with "
                f"{len(mixture_names)} mixtures, {len(face_names)} faces, {energy_groups} groups"
            )
        declared_names = None if declared_mixtures is None else tuple(_flatten_names(declared_mixtures))
        normalized = _reorder_by_declared_mixtures(
            normalized,
            declared_names,
            mixture_names,
            label,
        )
        return _reorder_by_declared_faces(normalized, declared_face_names, face_names, label)
    if values.ndim == 4:
        face_count = len(declared_face_names or face_names)
        if values.shape[-2:] == (face_count, energy_groups):
            grid_values = values
        elif values.shape[-2:] == (energy_groups, face_count):
            grid_values = np.moveaxis(values, -1, -2)
        else:
            raise ValueError(
                f"{label}: last dimensions {values.shape[-2:]} are not "
                f"(groups, faces) or (faces, groups)"
            )
        if declared_mixtures is None:
            raise ValueError(f"{label}: 4D net current requires mixture_names mesh")
        names = _decode_name_array(declared_mixtures)
        if names.shape != grid_values.shape[:2]:
            raise ValueError(
                f"{label}: mixture_names shape {names.shape} does not match "
                f"current mesh shape {grid_values.shape[:2]}"
            )
        normalized = _mesh_values_to_mixture_order(grid_values, names, mixture_names, label)
        return _reorder_by_declared_faces(normalized, declared_face_names, face_names, label)
    raise ValueError(f"{label}: expected 3D or 4D dataset")


def _mesh_values_to_mixture_order(
    values: np.ndarray,
    names: np.ndarray,
    mixture_names: tuple[str, ...],
    label: str,
) -> np.ndarray:
    out: dict[str, np.ndarray] = {}
    for index in np.ndindex(names.shape):
        name = str(names[index])
        if name in out:
            raise ValueError(f"{label}: duplicate mixture name {name!r} in mesh")
        out[name] = values[index]
    if set(out) != set(mixture_names):
        raise ValueError(
            f"{label}: mesh mixtures {tuple(out)} do not match MGXS mixtures {mixture_names}"
        )
    return np.stack([out[name] for name in mixture_names])


def _reorder_by_declared_mixtures(
    values: np.ndarray,
    declared_names: tuple[str, ...] | None,
    mixture_names: tuple[str, ...],
    label: str,
) -> np.ndarray:
    if declared_names is None or declared_names == mixture_names:
        return values
    if set(declared_names) != set(mixture_names):
        raise ValueError(
            f"{label}: declared mixtures {declared_names!r} do not match "
            f"MGXS mixtures {mixture_names!r}"
        )
    index_by_name = {name: index for index, name in enumerate(declared_names)}
    return np.stack([values[index_by_name[name]] for name in mixture_names])


def _reorder_by_declared_faces(
    values: np.ndarray,
    declared_names: tuple[str, ...] | None,
    face_names: tuple[str, ...],
    label: str,
) -> np.ndarray:
    if declared_names is None or declared_names == face_names:
        return values
    if set(declared_names) != set(face_names):
        raise ValueError(
            f"{label}: declared faces {declared_names!r} do not match "
            f"expected faces {face_names!r}"
        )
    if len(set(declared_names)) != len(declared_names):
        raise ValueError(f"{label}: duplicate face names in declared faces")
    index_by_name = {name: index for index, name in enumerate(declared_names)}
    return values[:, [index_by_name[name] for name in face_names], :]


def _apply_net_current_sign_convention(
    values: np.ndarray,
    *,
    declared_sign: str | None,
    override: str | None,
    label: str,
) -> tuple[np.ndarray, str, str, float]:
    raw_override = None if override is None else str(override).strip()
    if raw_override and _normalize_sign_words(raw_override) != "auto":
        raw = raw_override
        source = "argument"
    elif declared_sign:
        raw = declared_sign
        source = "hdf5"
    else:
        raw = "positive outward"
        source = "default"
    canonical, multiplier = _net_current_sign_multiplier(raw, label)
    return values * multiplier, canonical, source, multiplier


def _net_current_sign_multiplier(raw: str, label: str) -> tuple[str, float]:
    normalized = _normalize_sign_words(raw)
    if normalized in {
        "positive outward",
        "outward positive",
        "outward",
        "outward normal",
        "positive outward normal",
    }:
        return "positive outward", 1.0
    if normalized in {
        "positive inward",
        "inward positive",
        "inward",
        "inward normal",
        "positive inward normal",
    }:
        return "positive inward", -1.0
    raise ValueError(
        f"{label}: unsupported net-current sign convention {raw!r}; "
        "use positive-outward or positive-inward"
    )


def _normalize_sign_words(raw: str) -> str:
    return " ".join(
        str(raw)
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


def _resolve_face_widths(
    face_widths: tuple[float, ...] | None,
    face_names: tuple[str, ...],
) -> tuple[float, ...]:
    if face_widths is None:
        out = (1.0,) * len(face_names)
    elif len(face_widths) == 1:
        out = tuple(float(face_widths[0]) for _ in face_names)
    else:
        out = tuple(float(value) for value in face_widths)
    if len(out) != len(face_names):
        raise ValueError("face width count must be one or match the number of faces")
    if any((not np.isfinite(value) or value <= 0.0) for value in out):
        raise ValueError("face widths must be positive and finite")
    return out


def _split_dataset_reference(reference: str | Path) -> tuple[Path, str | None]:
    raw = str(reference)
    if "::" not in raw:
        return Path(raw), None
    path, dataset = raw.split("::", 1)
    dataset = dataset.strip("/")
    if not dataset:
        raise ValueError(f"empty dataset in HDF5 reference: {reference}")
    return Path(path), dataset


def _names_from_hdf5(obj, root, keys: tuple[str, ...]):
    for owner in (obj, root):
        for key in keys:
            if key in owner.attrs:
                return owner.attrs[key]
    for key in keys:
        if key in root and not hasattr(root[key], "keys"):
            return root[key][:]
    return None


def _text_from_hdf5(obj, root, keys: tuple[str, ...]) -> str | None:
    for owner in (obj, root):
        for key in keys:
            if key in owner.attrs:
                return _decode_text(owner.attrs[key])
    for key in keys:
        if key in root and not hasattr(root[key], "keys"):
            values = np.asarray(root[key][()])
            if values.shape == ():
                return _decode_text(values[()])
            if values.size == 1:
                return _decode_text(values.reshape(-1)[0])
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


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "max": float(np.max(values)),
    }

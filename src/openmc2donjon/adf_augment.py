"""Inject assembly discontinuity factors into an MGXS HDF5 handoff."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from .constants import DONJON_ADF_NAME_WIDTH


SCHEMA = "openmc2donjon.adf-augment.v1"
FACE_ATTR_KEYS = ("face_names", "names", "adf_names")


@dataclass(frozen=True)
class AdfAugmentReport:
    input_h5: Path
    adf_source: Path
    output_h5: Path
    mixture_names: tuple[str, ...]
    face_names: tuple[str, ...]
    energy_groups: int


def augment_hdf5_with_adf(
    input_h5: Path,
    *,
    adf_source: Path,
    output_h5: Path,
    expected_faces: tuple[str, ...] | None = None,
    force: bool = False,
    adf_kind: str | None = None,
    adf_real: str | None = None,
    adf_source_label: str | None = None,
    summary_json: Path | None = None,
) -> AdfAugmentReport:
    """Copy ``input_h5`` to ``output_h5`` and inject ADF datasets."""

    import h5py

    input_h5 = Path(input_h5)
    adf_source = Path(adf_source)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if not adf_source.exists():
        raise FileNotFoundError(f"ADF source does not exist: {adf_source}")
    if _same_path(input_h5, output_h5):
        raise ValueError("output HDF5 must be different from input HDF5")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")

    with h5py.File(input_h5, "r") as h5:
        mixture_names = _input_mixture_names(h5)
        ngroups = _energy_groups(h5)

    sidecar = load_adf_source(
        adf_source,
        mixture_names=mixture_names,
        energy_groups=ngroups,
        expected_faces=expected_faces,
    )

    output_h5.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_h5, output_h5)
    with h5py.File(output_h5, "r+") as h5:
        _write_adf_payload(h5, sidecar.adf, sidecar.face_names)
        _write_adf_attrs(
            h5,
            sidecar.root_adf_attrs,
            adf_source=adf_source,
            face_names=sidecar.face_names,
            adf_kind=adf_kind,
            adf_real=adf_real,
            adf_source_label=adf_source_label,
        )

    report = AdfAugmentReport(
        input_h5=input_h5,
        adf_source=adf_source,
        output_h5=output_h5,
        mixture_names=mixture_names,
        face_names=sidecar.face_names,
        energy_groups=ngroups,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


@dataclass(frozen=True)
class LoadedAdf:
    adf: dict[str, dict[str, np.ndarray]]
    face_names: tuple[str, ...]
    root_adf_attrs: dict[str, Any]


def load_adf_source(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    expected_faces: tuple[str, ...] | None = None,
) -> LoadedAdf:
    """Load ADF values from a supported HDF5 sidecar layout."""

    import h5py

    with h5py.File(path, "r") as h5:
        root_adf_attrs = {
            str(key): _json_safe_attr(value)
            for key, value in h5.attrs.items()
            if str(key).startswith("adf")
        }
        if "mixtures" in h5 and hasattr(h5["mixtures"], "keys"):
            adf = _load_from_mixtures(h5["mixtures"], mixture_names, energy_groups)
        elif "adf" in h5:
            adf = _load_from_adf_root(h5["adf"], mixture_names, energy_groups)
        else:
            raise ValueError("ADF source must contain /mixtures/*/adf or /adf")

    face_names = _validate_and_order_adf(
        adf,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        expected_faces=expected_faces,
    )
    return LoadedAdf(adf=adf, face_names=face_names, root_adf_attrs=root_adf_attrs)


def print_report(report: AdfAugmentReport) -> None:
    print("OpenMC-to-DONJON ADF augment")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  adf_source: {report.adf_source}")
    print(f"  output: {report.output_h5}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"faces={','.join(report.face_names)}"
    )
    print()
    print("ADF augment decision")
    print("  openmc2donjon_adf_augment_passed")


def write_summary(path: Path, report: AdfAugmentReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": "openmc2donjon_adf_augment_passed",
        "input_h5": str(report.input_h5),
        "adf_source": str(report.adf_source),
        "output_h5": str(report.output_h5),
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _input_mixture_names(h5) -> tuple[str, ...]:
    if "mixtures" not in h5 or not hasattr(h5["mixtures"], "keys"):
        raise ValueError("input HDF5 must contain a /mixtures group")
    names = tuple(str(name) for name in h5["mixtures"])
    if not names:
        raise ValueError("input HDF5 contains no mixtures")
    return names


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


def _load_from_mixtures(
    mixtures_group,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> dict[str, dict[str, np.ndarray]]:
    out: dict[str, dict[str, np.ndarray]] = {}
    missing: list[str] = []
    for mixture_name in mixture_names:
        if mixture_name not in mixtures_group:
            missing.append(mixture_name)
            continue
        group = mixtures_group[mixture_name]
        for adf_name in ("adf", "ADF", "discontinuity_factors"):
            if adf_name in group:
                out[mixture_name] = _adf_object_to_faces(
                    group[adf_name],
                    mixture_name=mixture_name,
                    energy_groups=energy_groups,
                )
                break
        else:
            missing.append(mixture_name)
    if missing:
        rendered = ", ".join(missing[:8])
        if len(missing) > 8:
            rendered += f", ... ({len(missing)} total)"
        raise ValueError(f"ADF source is missing ADF data for mixture(s): {rendered}")
    return out


def _load_from_adf_root(
    obj,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> dict[str, dict[str, np.ndarray]]:
    if hasattr(obj, "keys"):
        keys = tuple(str(key) for key in obj)
        if all(name in obj for name in mixture_names):
            return {
                mixture_name: _adf_object_to_faces(
                    obj[mixture_name],
                    mixture_name=mixture_name,
                    energy_groups=energy_groups,
                )
                for mixture_name in mixture_names
            }
        return _load_face_group_layout(obj, mixture_names, energy_groups)
    return _load_root_dataset_layout(obj, mixture_names, energy_groups)


def _load_face_group_layout(
    group,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> dict[str, dict[str, np.ndarray]]:
    declared_mixtures = _names_from_attrs(group, ("mixture_names", "mixtures"))
    if declared_mixtures is None:
        raise ValueError("/adf group layout must use mixture keys or define mixture_names")
    if tuple(declared_mixtures) != mixture_names:
        raise ValueError(
            "/adf mixture_names do not match input mixtures: "
            f"{tuple(declared_mixtures)!r} != {mixture_names!r}"
        )
    out = {name: {} for name in mixture_names}
    for face_name in group:
        face = _validate_face_name(str(face_name))
        values = np.asarray(group[face_name][:], dtype=float)
        if values.shape != (len(mixture_names), energy_groups):
            raise ValueError(
                f"/adf/{face_name} must have shape "
                f"({len(mixture_names)}, {energy_groups})"
            )
        for index, mixture_name in enumerate(mixture_names):
            out[mixture_name][face] = values[index]
    return out


def _load_root_dataset_layout(
    dataset,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> dict[str, dict[str, np.ndarray]]:
    declared_mixtures = _names_from_attrs(dataset, ("mixture_names", "mixtures"))
    if declared_mixtures is None:
        raise ValueError("/adf dataset must define mixture_names")
    if tuple(declared_mixtures) != mixture_names:
        raise ValueError(
            "/adf mixture_names do not match input mixtures: "
            f"{tuple(declared_mixtures)!r} != {mixture_names!r}"
        )
    face_names = _face_names_from_attrs(dataset)
    values = np.asarray(dataset[:], dtype=float)
    if values.ndim != 3:
        raise ValueError("/adf dataset must have shape (M, F, G)")
    if values.shape != (len(mixture_names), len(face_names), energy_groups):
        raise ValueError(
            "/adf dataset must have shape "
            f"({len(mixture_names)}, {len(face_names)}, {energy_groups})"
        )
    out = {name: {} for name in mixture_names}
    for mix_index, mixture_name in enumerate(mixture_names):
        for face_index, face_name in enumerate(face_names):
            out[mixture_name][face_name] = values[mix_index, face_index]
    return out


def _adf_object_to_faces(
    obj,
    *,
    mixture_name: str,
    energy_groups: int,
) -> dict[str, np.ndarray]:
    if hasattr(obj, "keys"):
        out: dict[str, np.ndarray] = {}
        for raw_face_name in obj:
            face_name = _validate_face_name(str(raw_face_name))
            out[face_name] = _vector(
                obj[raw_face_name][:],
                energy_groups,
                f"{mixture_name}/adf/{face_name}",
            )
        return out

    values = np.asarray(obj[:], dtype=float)
    face_names = _face_names_from_attrs(obj)
    if values.ndim == 1:
        if len(face_names) != 1:
            raise ValueError(f"mixture {mixture_name}: 1D ADF requires one face name")
        return {face_names[0]: _vector(values, energy_groups, f"{mixture_name}/adf")}
    if values.ndim == 2:
        if values.shape != (len(face_names), energy_groups):
            raise ValueError(
                f"mixture {mixture_name}: ADF dataset must have shape "
                f"({len(face_names)}, {energy_groups})"
            )
        return {
            face_name: _vector(values[index], energy_groups, f"{mixture_name}/adf/{face_name}")
            for index, face_name in enumerate(face_names)
        }
    raise ValueError(f"mixture {mixture_name}: ADF dataset must be 1D or 2D")


def _validate_and_order_adf(
    adf: dict[str, dict[str, np.ndarray]],
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    expected_faces: tuple[str, ...] | None,
) -> tuple[str, ...]:
    missing = [name for name in mixture_names if name not in adf]
    if missing:
        raise ValueError(f"ADF source is missing mixture(s): {', '.join(missing)}")
    first_faces = tuple(adf[mixture_names[0]])
    face_names = expected_faces or first_faces
    face_names = tuple(_validate_face_name(name) for name in face_names)
    if not face_names:
        raise ValueError("ADF source contains no faces")
    for mixture_name in mixture_names:
        faces = tuple(adf[mixture_name])
        if set(faces) != set(face_names):
            raise ValueError(
                f"mixture {mixture_name}: ADF faces {faces!r} do not match "
                f"expected faces {face_names!r}"
            )
        adf[mixture_name] = {face_name: adf[mixture_name][face_name] for face_name in face_names}
        for face_name in face_names:
            values = _vector(
                adf[mixture_name][face_name],
                energy_groups,
                f"{mixture_name}/adf/{face_name}",
            )
            if not np.all(np.isfinite(values)):
                raise ValueError(f"{mixture_name}/adf/{face_name}: ADF values must be finite")
            if np.any(values <= 0.0):
                raise ValueError(f"{mixture_name}/adf/{face_name}: ADF values must be positive")
            adf[mixture_name][face_name] = values
    return face_names


def _write_adf_payload(h5, adf: dict[str, dict[str, np.ndarray]], face_names: tuple[str, ...]) -> None:
    mixtures = h5["mixtures"]
    for mixture_name, faces in adf.items():
        group = mixtures[mixture_name]
        for stale_name in ("adf", "ADF", "discontinuity_factors"):
            if stale_name in group:
                del group[stale_name]
        adf_group = group.create_group("adf", track_order=True)
        adf_group.attrs["face_names"] = np.asarray(face_names, dtype="S")
        for face_name in face_names:
            adf_group.create_dataset(face_name, data=faces[face_name])


def _write_adf_attrs(
    h5,
    source_attrs: dict[str, Any],
    *,
    adf_source: Path,
    face_names: tuple[str, ...],
    adf_kind: str | None,
    adf_real: str | None,
    adf_source_label: str | None,
) -> None:
    for key in list(h5.attrs):
        if str(key).startswith("adf"):
            del h5.attrs[key]
    for key, value in source_attrs.items():
        h5.attrs[str(key)] = value
    h5.attrs["adf_injector"] = "openmc2donjon augment-adf"
    h5.attrs["adf_sidecar"] = str(adf_source)
    h5.attrs["adf_face_names"] = np.asarray(face_names, dtype="S")
    if adf_source_label is not None:
        h5.attrs["adf_source"] = adf_source_label
    elif "adf_source" not in h5.attrs:
        h5.attrs["adf_source"] = str(adf_source)
    if adf_kind is not None:
        h5.attrs["adf_kind"] = adf_kind
    elif "adf_kind" not in h5.attrs:
        h5.attrs["adf_kind"] = "sidecar"
    if adf_real is not None:
        h5.attrs["adf_real"] = adf_real


def _face_names_from_attrs(obj) -> tuple[str, ...]:
    names = _names_from_attrs(obj, FACE_ATTR_KEYS)
    if names is None:
        values = np.asarray(obj[:])
        if values.ndim == 1:
            names = ["FD_B"]
        elif values.ndim >= 2:
            names = [f"FD_{index + 1:05d}" for index in range(values.shape[-2])]
        else:
            raise ValueError("ADF face names are missing and shape is invalid")
    return tuple(_validate_face_name(name) for name in names)


def _names_from_attrs(obj, keys: tuple[str, ...]) -> list[str] | None:
    for key in keys:
        if key in obj.attrs:
            raw = obj.attrs[key]
            if isinstance(raw, (str, bytes)):
                return [_attr_text(raw)]
            raw_array = np.asarray(raw)
            if raw_array.shape == ():
                return [_attr_text(raw_array[()])]
            return [_attr_text(value) for value in raw_array.reshape(-1)]
    return None


def _vector(values: Any, energy_groups: int, label: str) -> np.ndarray:
    out = np.asarray(values, dtype=float).reshape(-1)
    if out.shape != (energy_groups,):
        raise ValueError(f"{label}: expected shape ({energy_groups},), got {out.shape}")
    return out


def _validate_face_name(name: str) -> str:
    if not name:
        raise ValueError("ADF face name must not be empty")
    if len(name) > DONJON_ADF_NAME_WIDTH:
        raise ValueError(
            f"ADF face name {name!r} is longer than {DONJON_ADF_NAME_WIDTH} characters"
        )
    return name


def _attr_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8").rstrip("\x00")
    if hasattr(value, "item"):
        item = value.item()
        if isinstance(item, bytes):
            return item.decode("utf-8").rstrip("\x00")
        return str(item)
    return str(value)


def _json_safe_attr(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray):
        if value.dtype.kind == "S":
            return [_attr_text(item) for item in value]
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def parse_faces(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    faces = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not faces:
        raise ValueError("--faces must list at least one face")
    return tuple(_validate_face_name(face) for face in faces)

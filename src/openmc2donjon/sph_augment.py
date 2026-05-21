"""Inject SPH equivalence factors into an MGXS HDF5 handoff."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__


SCHEMA = "openmc2donjon.sph-augment.v1"
SIDECAR_SCHEMA = "openmc2donjon.sph-sidecar.v1"


@dataclass(frozen=True)
class SphAugmentReport:
    input_h5: Path
    sph_source: Path
    output_h5: Path
    mixture_names: tuple[str, ...]
    energy_groups: int
    sph_kind: str
    sph_real: bool
    sph_applied: bool


@dataclass(frozen=True)
class SphSidecarReport:
    input_h5: Path
    output_h5: Path
    mixture_names: tuple[str, ...]
    energy_groups: int
    value: float | None
    source: Path | None
    sph_min: float
    sph_max: float
    sph_kind: str
    sph_real: bool
    sph_applied: bool


@dataclass(frozen=True)
class LoadedSph:
    sph: dict[str, np.ndarray]
    root_sph_attrs: dict[str, Any]


def create_unity_sph_sidecar(
    input_h5: Path,
    output_h5: Path,
    *,
    value: float = 1.0,
    force: bool = False,
    sph_kind: str = "unity",
    sph_real: bool = False,
    sph_applied: bool = False,
    summary_json: Path | None = None,
) -> SphSidecarReport:
    """Create a constant SPH sidecar matching an MGXS handoff."""

    import h5py

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("--value must be positive and finite")

    with h5py.File(input_h5, "r") as h5:
        mixture_names = _input_mixture_names(h5)
        ngroups = _energy_groups(h5)

    values = np.full((len(mixture_names), ngroups), float(value), dtype=float)
    _write_sidecar_file(
        output_h5,
        input_h5=input_h5,
        values=values,
        mixture_names=mixture_names,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        source=None,
    )

    report = SphSidecarReport(
        input_h5=input_h5,
        output_h5=output_h5,
        mixture_names=mixture_names,
        energy_groups=ngroups,
        value=float(value),
        source=None,
        sph_min=float(np.min(values)),
        sph_max=float(np.max(values)),
        sph_kind=sph_kind,
        sph_real=bool(sph_real),
        sph_applied=bool(sph_applied),
    )
    print_sidecar_report(report)
    if summary_json is not None:
        write_sidecar_summary(summary_json, report)
    return report


def create_macrolib_sph_sidecar(
    input_h5: Path,
    output_h5: Path,
    *,
    macrolib_ascii: Path,
    force: bool = False,
    sph_kind: str = "macrolib-nsph",
    sph_real: bool = True,
    sph_applied: bool = False,
    summary_json: Path | None = None,
) -> SphSidecarReport:
    """Create an SPH sidecar by extracting ``NSPH`` from a DONJON macrolib."""

    import h5py

    from .macrolib import read_macrolib_ascii

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    macrolib_ascii = Path(macrolib_ascii)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if not macrolib_ascii.exists():
        raise FileNotFoundError(f"macrolib ASCII does not exist: {macrolib_ascii}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")

    with h5py.File(input_h5, "r") as h5:
        mixture_names = _input_mixture_names(h5)
        ngroups = _energy_groups(h5)

    macrolib = read_macrolib_ascii(macrolib_ascii)
    if macrolib.sph is None:
        raise ValueError(f"macrolib has no GROUP/*/NSPH payload: {macrolib_ascii}")
    values = np.asarray(macrolib.sph, dtype=float)
    expected_shape = (len(mixture_names), ngroups)
    if values.shape != expected_shape:
        raise ValueError(
            "macrolib NSPH shape does not match MGXS metadata: "
            f"{values.shape} != {expected_shape}"
        )
    sph = {
        mixture_name: np.asarray(values[index], dtype=float)
        for index, mixture_name in enumerate(mixture_names)
    }
    _validate_sph(sph, mixture_names=mixture_names, energy_groups=ngroups)
    values = np.stack([sph[name] for name in mixture_names])

    _write_sidecar_file(
        output_h5,
        input_h5=input_h5,
        values=values,
        mixture_names=mixture_names,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        source=macrolib_ascii,
    )

    report = SphSidecarReport(
        input_h5=input_h5,
        output_h5=output_h5,
        mixture_names=mixture_names,
        energy_groups=ngroups,
        value=None,
        source=macrolib_ascii,
        sph_min=float(np.min(values)),
        sph_max=float(np.max(values)),
        sph_kind=sph_kind,
        sph_real=bool(sph_real),
        sph_applied=bool(sph_applied),
    )
    print_sidecar_report(report)
    if summary_json is not None:
        write_sidecar_summary(summary_json, report)
    return report


def augment_hdf5_with_sph(
    input_h5: Path,
    *,
    sph_source: Path,
    output_h5: Path,
    force: bool = False,
    sph_kind: str | None = None,
    sph_real: str | bool | None = None,
    sph_applied: str | bool | None = None,
    sph_source_label: str | None = None,
    summary_json: Path | None = None,
) -> SphAugmentReport:
    """Copy ``input_h5`` to ``output_h5`` and inject per-mixture SPH vectors."""

    import h5py

    input_h5 = Path(input_h5)
    sph_source = Path(sph_source)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if not sph_source.exists():
        raise FileNotFoundError(f"SPH source does not exist: {sph_source}")
    if _same_path(input_h5, output_h5):
        raise ValueError("output HDF5 must be different from input HDF5")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")

    with h5py.File(input_h5, "r") as h5:
        mixture_names = _input_mixture_names(h5)
        ngroups = _energy_groups(h5)

    loaded = load_sph_source(
        sph_source,
        mixture_names=mixture_names,
        energy_groups=ngroups,
    )

    output_h5.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_h5, output_h5)
    with h5py.File(output_h5, "r+") as h5:
        _write_sph_payload(h5, loaded.sph, mixture_names)
        resolved_kind = str(sph_kind or loaded.root_sph_attrs.get("sph_kind", "external"))
        resolved_real = _bool_setting(
            sph_real,
            loaded.root_sph_attrs.get("sph_real", True),
            "--sph-real",
        )
        resolved_applied = _bool_setting(
            sph_applied,
            loaded.root_sph_attrs.get("sph_applied", False),
            "--sph-applied",
        )
        _write_sph_attrs(
            h5,
            sph_kind=resolved_kind,
            sph_real=resolved_real,
            sph_applied=resolved_applied,
            sph_source=sph_source,
            sph_source_label=sph_source_label,
        )

    report = SphAugmentReport(
        input_h5=input_h5,
        sph_source=sph_source,
        output_h5=output_h5,
        mixture_names=mixture_names,
        energy_groups=ngroups,
        sph_kind=resolved_kind,
        sph_real=resolved_real,
        sph_applied=resolved_applied,
    )
    print_augment_report(report)
    if summary_json is not None:
        write_augment_summary(summary_json, report)
    return report


def load_sph_source(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> LoadedSph:
    """Load SPH values from a supported HDF5 sidecar layout."""

    import h5py

    with h5py.File(path, "r") as h5:
        root_attrs = {
            str(key): _json_safe_attr(value)
            for key, value in h5.attrs.items()
            if str(key).startswith("sph")
        }
        if "mixtures" in h5 and hasattr(h5["mixtures"], "keys"):
            sph = _load_from_mixtures(h5["mixtures"], mixture_names, energy_groups)
        elif "sph" in h5:
            sph = _load_from_sph_root(h5["sph"], mixture_names, energy_groups)
        else:
            raise ValueError("SPH source must contain /mixtures/*/sph or /sph")

    _validate_sph(sph, mixture_names=mixture_names, energy_groups=energy_groups)
    return LoadedSph(sph=sph, root_sph_attrs=root_attrs)


def print_sidecar_report(report: SphSidecarReport) -> None:
    print("OpenMC-to-DONJON SPH sidecar")
    print(f"  schema: {SIDECAR_SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_h5}")
    if report.source is not None:
        print(f"  source: {report.source}")
    value = "varies" if report.value is None else f"{report.value:g}"
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"value={value} sph_kind={report.sph_kind} "
        f"range={report.sph_min:g}..{report.sph_max:g}"
    )
    print()
    print("SPH sidecar decision")
    print("  openmc2donjon_sph_sidecar_passed")


def print_augment_report(report: SphAugmentReport) -> None:
    print("OpenMC-to-DONJON SPH augment")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  sph_source: {report.sph_source}")
    print(f"  output: {report.output_h5}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"sph_kind={report.sph_kind} sph_real={report.sph_real} "
        f"sph_applied={report.sph_applied}"
    )
    print()
    print("SPH augment decision")
    print("  openmc2donjon_sph_augment_passed")


def write_sidecar_summary(path: Path, report: SphSidecarReport) -> None:
    payload = {
        "schema": SIDECAR_SCHEMA,
        "package_version": __version__,
        "decision": "openmc2donjon_sph_sidecar_passed",
        "input_h5": str(report.input_h5),
        "output_h5": str(report.output_h5),
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "value": report.value,
        "source": None if report.source is None else str(report.source),
        "sph_min": report.sph_min,
        "sph_max": report.sph_max,
        "sph_kind": report.sph_kind,
        "sph_real": report.sph_real,
        "sph_applied": report.sph_applied,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_augment_summary(path: Path, report: SphAugmentReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": "openmc2donjon_sph_augment_passed",
        "input_h5": str(report.input_h5),
        "sph_source": str(report.sph_source),
        "output_h5": str(report.output_h5),
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "sph_kind": report.sph_kind,
        "sph_real": report.sph_real,
        "sph_applied": report.sph_applied,
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
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    missing: list[str] = []
    for mixture_name in mixture_names:
        if mixture_name not in mixtures_group:
            missing.append(mixture_name)
            continue
        group = mixtures_group[mixture_name]
        for dataset_name in ("sph", "SPH", "NSPH"):
            if dataset_name in group:
                out[mixture_name] = _vector(
                    group[dataset_name][:],
                    energy_groups,
                    f"{mixture_name}/{dataset_name}",
                )
                break
        else:
            missing.append(mixture_name)
    if missing:
        rendered = ", ".join(missing[:8])
        if len(missing) > 8:
            rendered += f", ... ({len(missing)} total)"
        raise ValueError(f"SPH source is missing SPH data for mixture(s): {rendered}")
    return out


def _load_from_sph_root(
    obj,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> dict[str, np.ndarray]:
    if hasattr(obj, "keys"):
        missing = [name for name in mixture_names if name not in obj]
        if missing:
            raise ValueError(f"/sph group is missing mixture(s): {', '.join(missing)}")
        return {
            mixture_name: _vector(
                obj[mixture_name][:],
                energy_groups,
                f"/sph/{mixture_name}",
            )
            for mixture_name in mixture_names
        }

    declared_mixtures = _names_from_attrs(obj, ("mixture_names", "mixtures"))
    if declared_mixtures is None:
        raise ValueError("/sph dataset must define mixture_names")
    if tuple(declared_mixtures) != mixture_names:
        raise ValueError(
            "/sph mixture_names do not match input mixtures: "
            f"{tuple(declared_mixtures)!r} != {mixture_names!r}"
        )
    values = np.asarray(obj[:], dtype=float)
    if values.shape != (len(mixture_names), energy_groups):
        raise ValueError(
            f"/sph must have shape ({len(mixture_names)}, {energy_groups}), "
            f"got {values.shape}"
        )
    return {
        mixture_name: np.asarray(values[index], dtype=float)
        for index, mixture_name in enumerate(mixture_names)
    }


def _write_sph_payload(
    h5,
    sph: dict[str, np.ndarray],
    mixture_names: tuple[str, ...],
) -> None:
    mixtures = h5["mixtures"]
    for mixture_name in mixture_names:
        target = mixtures[mixture_name]
        values = np.asarray(sph[mixture_name], dtype=float)
        if "states" in target and hasattr(target["states"], "keys"):
            for state_name in target["states"]:
                _replace_dataset(target["states"][state_name], "sph", values)
        else:
            _replace_dataset(target, "sph", values)


def _write_sph_attrs(
    h5,
    *,
    sph_kind: str,
    sph_real: bool,
    sph_applied: bool,
    sph_source: Path,
    sph_source_label: str | None,
) -> None:
    h5.attrs["sph_kind"] = sph_kind
    h5.attrs["sph_real"] = bool(sph_real)
    h5.attrs["sph_applied"] = bool(sph_applied)
    h5.attrs["sph_source"] = sph_source_label or str(sph_source)
    h5.attrs["sph_schema"] = SCHEMA
    h5.attrs["sph_package_version"] = __version__


def _replace_dataset(group, name: str, values: np.ndarray) -> None:
    if name in group:
        del group[name]
    group.create_dataset(name, data=np.asarray(values, dtype=float))


def _validate_sph(
    sph: dict[str, np.ndarray],
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> None:
    missing = [name for name in mixture_names if name not in sph]
    if missing:
        raise ValueError(f"SPH source is missing mixture(s): {', '.join(missing)}")
    for mixture_name in mixture_names:
        values = _vector(sph[mixture_name], energy_groups, f"{mixture_name}/sph")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"mixture {mixture_name}: SPH values must be finite")
        if np.any(values <= 0.0):
            raise ValueError(f"mixture {mixture_name}: SPH values must be positive")
        sph[mixture_name] = values


def _vector(values: np.ndarray, energy_groups: int, label: str) -> np.ndarray:
    out = np.asarray(values, dtype=float).reshape(-1)
    if out.shape != (energy_groups,):
        raise ValueError(f"{label} must have shape ({energy_groups},), got {out.shape}")
    return out


def _names_from_attrs(obj, keys: tuple[str, ...]) -> tuple[str, ...] | None:
    for key in keys:
        if key not in obj.attrs:
            continue
        raw = obj.attrs[key]
        if isinstance(raw, (bytes, str, np.bytes_)):
            return (_attr_text(raw),)
        return tuple(_attr_text(value) for value in raw)
    return None


def _write_sidecar_file(
    output_h5: Path,
    *,
    input_h5: Path,
    values: np.ndarray,
    mixture_names: tuple[str, ...],
    sph_kind: str,
    sph_real: bool,
    sph_applied: bool,
    source: Path | None,
) -> None:
    import h5py

    output_h5.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_h5, "w") as h5:
        h5.attrs["schema"] = SIDECAR_SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["sph_kind"] = sph_kind
        h5.attrs["sph_real"] = bool(sph_real)
        h5.attrs["sph_applied"] = bool(sph_applied)
        h5.attrs["source_mgxs"] = str(input_h5)
        if source is not None:
            h5.attrs["source_macrolib"] = str(source)
        dataset = h5.create_dataset("sph", data=np.asarray(values, dtype=float))
        _write_string_attr(dataset.attrs, "mixture_names", mixture_names)


def _write_string_attr(attrs, name: str, values: tuple[str, ...]) -> None:
    import h5py

    attrs.create(name, np.asarray(values, dtype=h5py.string_dtype("utf-8")))


def _bool_setting(value: str | bool | None, default: Any, option: str) -> bool:
    if value is None:
        return _bool_attr(default)
    if isinstance(value, bool):
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{option} must be true or false")


def _bool_attr(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return bool(value)
    text = _attr_text(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"cannot interpret boolean attribute value {value!r}")


def _attr_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.bytes_):
        return value.decode()
    return str(value)


def _json_safe_attr(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_json_safe_attr(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode()
    return value


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except FileNotFoundError:
        return left.absolute() == right.absolute()

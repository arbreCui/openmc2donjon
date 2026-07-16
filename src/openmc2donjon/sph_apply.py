"""Apply OpenMC-side SPH factors directly to MGXS HDF5 data."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np

from . import __version__
from .hdf5_names import read_mixture_names
from .openmc_provenance import (
    provenance_before_hdf5_mutation,
    refresh_openmc_provenance_after_hdf5_mutation,
)
from .sph_augment import load_sph_source


SCHEMA = "openmc2donjon.sph-apply.v1"

VECTOR_XS_DATASETS = (
    "total",
    "absorption",
    "fission",
    "nu_fission",
    "transport_total",
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa-fission",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
)
OPENMC_MGXS_VECTOR_DATASETS = (
    "total",
    "absorption",
    "fission",
    "nu-fission",
    "kappa-fission",
)
SPH_DATASETS = ("sph", "SPH", "NSPH")


@dataclass(frozen=True)
class SphApplyReport:
    input_h5: Path
    sph_source: Path
    output_h5: Path
    mixture_names: tuple[str, ...]
    energy_groups: int
    scaled_dataset_count: int
    sph_min: float
    sph_max: float
    operator: str = "divide-xs-by-nsph"
    input_format: str = "converter"


@dataclass(frozen=True)
class AppliedMixture:
    datasets: dict[str, np.ndarray]
    scaled_names: tuple[str, ...]


def print_report(report: SphApplyReport) -> None:
    """Print the user-facing SPH application report."""

    print("OpenMC-to-DONJON SPH-applied MGXS")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  sph source: {report.sph_source}")
    print(f"  output: {report.output_h5}")
    print(f"  input format: {report.input_format}")
    print(f"  operator: {report.operator}")
    print(f"  mixtures: {len(report.mixture_names)}")
    print(f"  energy groups: {report.energy_groups}")
    print(f"  scaled datasets: {report.scaled_dataset_count}")
    print(f"  SPH range: {report.sph_min:.6g} .. {report.sph_max:.6g}")
    print("")
    print("SPH apply decision")
    print("  openmc2donjon_sph_apply_passed")


def write_summary(path: Path, report: SphApplyReport) -> None:
    """Write a machine-readable SPH application summary."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary_payload(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def summary_payload(report: SphApplyReport) -> dict[str, Any]:
    """Return the JSON-serializable SPH application payload."""

    return {
        "schema": SCHEMA,
        "decision": "openmc2donjon_sph_apply_passed",
        "input_h5": str(report.input_h5),
        "sph_source": str(report.sph_source),
        "output_h5": str(report.output_h5),
        "input_format": report.input_format,
        "operator": report.operator,
        "mixtures": list(report.mixture_names),
        "energy_groups": report.energy_groups,
        "scaled_dataset_count": report.scaled_dataset_count,
        "sph_min": report.sph_min,
        "sph_max": report.sph_max,
    }


def apply_sph_to_mixture_arrays(
    datasets: dict[str, np.ndarray],
    sph: np.ndarray,
    *,
    scatter_axes: str = "moment,from,to",
) -> AppliedMixture:
    """Return MGXS arrays corrected by the DONJON ``NSPH`` divisor convention.

    ``NSPH`` is carried as an equivalence factor consumed by DONJON ``DSPH`` /
    ``MAC``. To build an already-corrected MGXS table for the next OpenMC MG
    iteration, each group-wise macroscopic cross section is divided by that
    factor. Scatter matrices are scaled by incoming/from group so row balance is
    preserved. ``chi`` is intentionally untouched because it is a normalized
    outgoing fission spectrum, not a macroscopic reaction coefficient.
    """

    sph_vector = _sph_vector(sph)
    corrected: dict[str, np.ndarray] = {}
    scaled: list[str] = []
    for name, values in datasets.items():
        array = np.asarray(values, dtype=float)
        if name in VECTOR_XS_DATASETS or _is_std_dev_of_scaled_vector(name):
            corrected[name] = _scale_vector(array, sph_vector, name)
            scaled.append(name)
        elif name in ("scatter_matrix", "scatter_matrix_std_dev"):
            corrected[name] = apply_sph_to_scatter_matrix(
                array,
                sph_vector,
                scatter_axes=scatter_axes,
                label=name,
            )
            scaled.append(name)
        else:
            corrected[name] = array.copy()
    return AppliedMixture(datasets=corrected, scaled_names=tuple(scaled))


def apply_sph_to_scatter_matrix(
    values: np.ndarray,
    sph: np.ndarray,
    *,
    scatter_axes: str = "moment,from,to",
    label: str = "scatter_matrix",
) -> np.ndarray:
    """Divide scatter rows by SPH using the incoming/from-group axis."""

    matrix = np.asarray(values, dtype=float)
    sph_vector = _sph_vector(sph)
    if matrix.ndim == 2:
        _require_shape(matrix.shape, (sph_vector.size, sph_vector.size), label)
        return matrix / sph_vector[:, None]
    if matrix.ndim != 3:
        raise ValueError(f"{label} must be 2D or 3D, got shape {matrix.shape}")
    axes = _scatter_axes(scatter_axes)
    if axes == ("moment", "from", "to"):
        if matrix.shape[1:] != (sph_vector.size, sph_vector.size):
            raise ValueError(
                f"{label} shape {matrix.shape} is not compatible with {sph_vector.size} groups"
            )
        return matrix / sph_vector[None, :, None]
    if axes == ("from", "to", "moment"):
        if matrix.shape[:2] != (sph_vector.size, sph_vector.size):
            raise ValueError(
                f"{label} shape {matrix.shape} is not compatible with {sph_vector.size} groups"
            )
        return matrix / sph_vector[:, None, None]
    raise ValueError(
        f"unsupported scatter_axes {scatter_axes!r}; expected moment,from,to or from,to,moment"
    )


def apply_sph_to_hdf5(
    input_h5: Path,
    *,
    sph_source: Path,
    output_h5: Path,
    force: bool = False,
) -> SphApplyReport:
    """Copy an MGXS HDF5 handoff and write SPH-corrected XS datasets.

    This variant handles the converter-facing ``/mixtures/<name>`` layout.
    Active ``sph`` / ``NSPH`` datasets are removed to prevent a downstream
    converter from applying the same factors again; the values are preserved
    as ``applied_sph`` provenance datasets.
    """

    import h5py

    input_h5 = Path(input_h5)
    sph_source = Path(sph_source)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if not sph_source.exists():
        raise FileNotFoundError(f"SPH source does not exist: {sph_source}")
    if input_h5.resolve() == output_h5.resolve():
        raise ValueError("output HDF5 must be different from input HDF5")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    openmc_provenance = provenance_before_hdf5_mutation(input_h5)

    with h5py.File(input_h5, "r") as h5:
        mixture_names = read_mixture_names(h5)
        energy_groups = _energy_groups(h5)
    loaded = load_sph_source(
        sph_source,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
    )

    output_h5.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_h5, output_h5)
    scaled_count = 0
    sph_matrix = np.stack([loaded.sph[name] for name in mixture_names])
    with h5py.File(output_h5, "r+") as h5:
        for mixture_name in mixture_names:
            mixture_group = h5["mixtures"][mixture_name]
            scaled_count += _apply_to_mixture_group(
                mixture_group,
                loaded.sph[mixture_name],
            )
        h5.attrs["sph_applied"] = True
        h5.attrs["sph_apply_schema"] = SCHEMA
        h5.attrs["sph_apply_operator"] = "divide-xs-by-nsph"
        h5.attrs["sph_applied_source"] = str(sph_source)
        h5.attrs["sph_package_version"] = __version__
        _copy_sph_provenance_attrs(h5, loaded.root_sph_attrs)
    refresh_openmc_provenance_after_hdf5_mutation(
        output_h5,
        openmc_provenance,
    )

    return SphApplyReport(
        input_h5=input_h5,
        sph_source=sph_source,
        output_h5=output_h5,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        scaled_dataset_count=scaled_count,
        sph_min=float(np.min(sph_matrix)),
        sph_max=float(np.max(sph_matrix)),
    )


def apply_sph_to_openmc_mgxs_hdf5(
    input_h5: Path,
    *,
    sph_source: Path,
    output_h5: Path,
    force: bool = False,
) -> SphApplyReport:
    """Copy an OpenMC-native MGXS file and divide XS by SPH factors.

    OpenMC MG-mode ``mgxs.h5`` files use macroscopic groups named ``set1``,
    ``set2``, ... instead of the converter-facing ``/mixtures/<name>`` layout.
    The mapping is therefore by sidecar order: first SPH mixture -> ``set1``,
    second -> ``set2``, and so on.
    """

    import h5py

    input_h5 = Path(input_h5)
    sph_source = Path(sph_source)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if not sph_source.exists():
        raise FileNotFoundError(f"SPH source does not exist: {sph_source}")
    if input_h5.resolve() == output_h5.resolve():
        raise ValueError("output HDF5 must be different from input HDF5")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    openmc_provenance = provenance_before_hdf5_mutation(input_h5)

    with h5py.File(input_h5, "r") as h5:
        energy_groups = _energy_groups(h5)
        macroscopic_names = _openmc_macroscopic_names(h5)
    mixture_names = _sph_source_mixture_names(sph_source)
    if len(macroscopic_names) != len(mixture_names):
        raise ValueError(
            "OpenMC MGXS macroscopic count does not match SPH sidecar mixture count: "
            f"{len(macroscopic_names)} != {len(mixture_names)}"
        )
    loaded = load_sph_source(
        sph_source,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
    )

    output_h5.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_h5, output_h5)
    scaled_count = 0
    sph_matrix = np.stack([loaded.sph[name] for name in mixture_names])
    with h5py.File(output_h5, "r+") as h5:
        for macro_name, mixture_name in zip(macroscopic_names, mixture_names, strict=True):
            scaled_count += _apply_to_openmc_macro_group(h5[macro_name], loaded.sph[mixture_name])
        h5.attrs["sph_applied"] = True
        h5.attrs["sph_apply_schema"] = SCHEMA
        h5.attrs["sph_apply_operator"] = "divide-xs-by-nsph"
        h5.attrs["sph_apply_input_format"] = "openmc-mgxs"
        h5.attrs["sph_applied_source"] = str(sph_source)
        h5.attrs["sph_package_version"] = __version__
        h5.attrs["sph_applied_mixture_names"] = np.asarray(mixture_names, dtype="S")
        h5.attrs["sph_applied_macroscopic_names"] = np.asarray(macroscopic_names, dtype="S")
        _copy_sph_provenance_attrs(h5, loaded.root_sph_attrs)
    refresh_openmc_provenance_after_hdf5_mutation(
        output_h5,
        openmc_provenance,
    )

    return SphApplyReport(
        input_h5=input_h5,
        sph_source=sph_source,
        output_h5=output_h5,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        scaled_dataset_count=scaled_count,
        sph_min=float(np.min(sph_matrix)),
        sph_max=float(np.max(sph_matrix)),
        input_format="openmc-mgxs",
    )


def _copy_sph_provenance_attrs(h5: Any, attrs: dict[str, Any]) -> None:
    if "sph_kind" in attrs:
        h5.attrs["sph_kind"] = attrs["sph_kind"]
    h5.attrs["sph_real"] = bool(attrs.get("sph_real", True))
    for name in (
        "sph_derivation",
        "sph_target",
        "sph_flux_normalization",
        "sph_raw_update_minimum",
        "sph_raw_update_maximum",
        "sph_max_update_residual",
        "sph_zero_flux_policy",
        "sph_identity_bin_count",
        "sph_floored_bin_count",
        "sph_frozen_group_bin_count",
        "sph_tie_mixture_groups",
        "sph_tied_bin_count",
        "sph_clipped_count",
    ):
        if name in attrs:
            h5.attrs[name] = attrs[name]


def _apply_to_mixture_group(group: Any, sph: np.ndarray) -> int:
    scaled = 0
    if "states" in group and hasattr(group["states"], "keys"):
        for state_name in group["states"]:
            scaled += _apply_to_calculation_group(group["states"][state_name], sph)
        _replace_dataset(group, "applied_sph", sph)
        _remove_sph_datasets(group)
        return scaled
    return _apply_to_calculation_group(group, sph)


def _apply_to_calculation_group(group: Any, sph: np.ndarray) -> int:
    datasets = {
        name: np.asarray(group[name][:], dtype=float)
        for name in group
        if hasattr(group[name], "shape")
    }
    scatter_axes = _text_attr(group.attrs.get("scatter_axes", "moment,from,to"))
    applied = apply_sph_to_mixture_arrays(
        datasets,
        sph,
        scatter_axes=scatter_axes,
    )
    for name in applied.scaled_names:
        _replace_dataset(group, name, applied.datasets[name])
    _replace_dataset(group, "applied_sph", _sph_vector(sph))
    _remove_sph_datasets(group)
    return len(applied.scaled_names)


def _apply_to_openmc_macro_group(group: Any, sph: np.ndarray) -> int:
    scaled = 0
    vector = _sph_vector(sph)
    for child_name in group:
        child = group[child_name]
        if hasattr(child, "keys") and "scatter_data" in child:
            scaled += _apply_to_openmc_temperature_group(child, vector)
    return scaled


def _apply_to_openmc_temperature_group(group: Any, sph: np.ndarray) -> int:
    scaled = 0
    for name in OPENMC_MGXS_VECTOR_DATASETS:
        if name in group:
            _replace_dataset(
                group,
                name,
                _scale_vector(np.asarray(group[name][:], dtype=float), sph, name),
            )
            scaled += 1
    if "scatter_data" in group and "scatter_matrix" in group["scatter_data"]:
        _replace_dataset(
            group["scatter_data"],
            "scatter_matrix",
            _apply_sph_to_openmc_scatter_data(group["scatter_data"], sph),
        )
        scaled += 1
    return scaled


def _apply_sph_to_openmc_scatter_data(scatter_data: Any, sph: np.ndarray) -> np.ndarray:
    g_min = np.asarray(scatter_data["g_min"][:], dtype=int)
    g_max = np.asarray(scatter_data["g_max"][:], dtype=int)
    matrix = np.asarray(scatter_data["scatter_matrix"][:], dtype=float)
    if g_min.shape != (sph.size,) or g_max.shape != (sph.size,):
        raise ValueError(
            "OpenMC scatter g_min/g_max shape is not compatible with "
            f"{sph.size} groups"
        )
    spans = g_max - g_min + 1
    if np.any(spans < 0):
        raise ValueError("OpenMC scatter g_min/g_max contain negative spans")
    span_total = int(np.sum(spans))
    if span_total <= 0:
        return matrix.copy()
    if matrix.size % span_total != 0:
        raise ValueError(
            "OpenMC scatter_matrix length is not divisible by sparse span count: "
            f"{matrix.size} % {span_total}"
        )
    order = matrix.size // span_total
    corrected = matrix.copy()
    offset = 0
    for group_index, span in enumerate(spans):
        width = int(span) * order
        corrected[offset : offset + width] /= sph[group_index]
        offset += width
    return corrected


def _remove_sph_datasets(group: Any) -> None:
    for name in SPH_DATASETS:
        if name in group:
            del group[name]


def _replace_dataset(group: Any, name: str, values: np.ndarray) -> None:
    if name in group:
        del group[name]
    group.create_dataset(name, data=np.asarray(values, dtype=float))


def _scale_vector(values: np.ndarray, sph: np.ndarray, label: str) -> np.ndarray:
    _require_shape(values.shape, (sph.size,), label)
    return values / sph


def _is_std_dev_of_scaled_vector(name: str) -> bool:
    if not name.endswith("_std_dev"):
        return False
    base = name[: -len("_std_dev")]
    return base in VECTOR_XS_DATASETS


def _sph_vector(values: np.ndarray) -> np.ndarray:
    vector = np.asarray(values, dtype=float).reshape(-1)
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError("SPH vector must be one-dimensional and non-empty")
    if not np.all(np.isfinite(vector)):
        raise ValueError("SPH vector must contain finite values")
    if np.any(vector <= 0.0):
        raise ValueError("SPH vector must contain positive values")
    return vector


def _scatter_axes(value: str) -> tuple[str, str, str]:
    axes = tuple(part.strip().lower() for part in str(value).split(","))
    if len(axes) != 3:
        raise ValueError(f"scatter_axes must contain three comma-separated axes, got {value!r}")
    return axes  # type: ignore[return-value]


def _text_attr(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8")
    return str(value)


def _require_shape(actual: tuple[int, ...], expected: tuple[int, ...], label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} must have shape {expected}, got {actual}")


def _energy_groups(h5: Any) -> int:
    if "energy_groups" in h5.attrs:
        groups = int(h5.attrs["energy_groups"])
    elif "energy_bounds" in h5:
        groups = int(h5["energy_bounds"].shape[0]) - 1
    else:
        raise ValueError("input HDF5 must define energy_groups or energy_bounds")
    if groups <= 0:
        raise ValueError("energy group count must be positive")
    return groups


def _openmc_macroscopic_names(h5: Any) -> tuple[str, ...]:
    names = [
        str(name)
        for name in h5.keys()
        if hasattr(h5[name], "keys") and _is_openmc_set_group(str(name))
    ]
    names.sort(key=_openmc_set_sort_key)
    if not names:
        raise ValueError("OpenMC MGXS HDF5 must contain setN macroscopic groups")
    return tuple(names)


def _is_openmc_set_group(name: str) -> bool:
    suffix = name.removeprefix("set")
    return name.startswith("set") and suffix.isdigit()


def _openmc_set_sort_key(name: str) -> tuple[int, str]:
    suffix = name.removeprefix("set")
    if suffix.isdigit():
        return (int(suffix), name)
    return (10**9, name)


def _sph_source_mixture_names(path: Path) -> tuple[str, ...]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "sph" in h5 and not hasattr(h5["sph"], "keys"):
            raw = h5["sph"].attrs.get("mixture_names")
            if raw is None:
                raw = h5["sph"].attrs.get("mixtures")
            if raw is None:
                raise ValueError("/sph dataset must define mixture_names")
            return tuple(_decode_name(value) for value in raw)
        if "sph" in h5 and hasattr(h5["sph"], "keys"):
            return tuple(str(name) for name in h5["sph"].keys())
        if "mixtures" in h5 and hasattr(h5["mixtures"], "keys"):
            return tuple(str(name) for name in h5["mixtures"].keys())
    raise ValueError("SPH source must contain /sph or /mixtures")


def _decode_name(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8")
    return str(value)

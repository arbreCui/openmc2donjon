"""Export OpenMC MGXS-like libraries to the openmc2donjon HDF5 contract.

The exporter is intentionally duck-typed.  It does not import OpenMC at module
import time; instead it expects an object with the parts of the OpenMC
``mgxs.Library`` interface that are needed here:

- ``energy_groups`` with ``group_edges`` or ``groups``;
- ``domains``;
- ``get_mgxs(domain, mgxs_type)`` returning objects with ``get_xs()``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .energy_groups import energy_bounds_sha256


MGXS_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "total": ("total",),
    "absorption": ("absorption",),
    "fission": ("fission",),
    "kappa_fission": ("kappa-fission", "kappa_fission"),
    "nu_fission": ("nu-fission", "nu_fission"),
    "chi": ("chi",),
    "scatter_matrix": ("scatter matrix", "scatter_matrix"),
    "transport_total": ("transport", "transport_total"),
    "inverse_velocity": ("inverse-velocity", "inverse_velocity"),
}
NU_SCATTER_MGXS_TYPES = ("consistent nu-scatter matrix", "nu-scatter matrix")


@dataclass(frozen=True)
class ExportedDomain:
    """Summary for one exported spatial domain."""

    name: str
    source: Any
    xs_kwargs: Mapping[str, Any] | None = None
    scatter_mgxs_type: str = "scatter matrix"


@dataclass(frozen=True)
class DomainExportSpec:
    """Describe one OpenMC MGXS domain or mesh subdomain export."""

    domain: Any
    name: str | None = None
    xs_kwargs: Mapping[str, Any] | None = None
    volume: float | None = None
    attrs: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ExportSummary:
    """Machine-readable summary of an export operation."""

    output_path: Path
    energy_groups: int
    legendre_order: int
    domains: tuple[ExportedDomain, ...]
    scatter_mgxs_type: str = "scatter matrix"


def export_openmc_mgxs_library(
    library: Any,
    output_path: str | Path,
    *,
    domain_specs: Sequence[DomainExportSpec | Mapping[str, Any]] | None = None,
    domain_names: Mapping[Any, str] | None = None,
    root_attrs: Mapping[str, Any] | None = None,
    scatter_mgxs_type: str | None = None,
    overwrite: bool = True,
) -> ExportSummary:
    """Write an OpenMC MGXS-like library to the HDF5 input contract.

    Parameters
    ----------
    library:
        OpenMC ``mgxs.Library`` or a compatible object.
    output_path:
        HDF5 file to write.
    domain_specs:
        Optional explicit export specs. Use this for mesh or cell subdomains
        where a single OpenMC domain produces multiple DONJON mixtures.
    domain_names:
        Optional mapping from domain object, domain id, or domain name to a
        stable output name.
    root_attrs:
        Optional HDF5 root attributes to copy into the output file.
    scatter_mgxs_type:
        Optional explicit OpenMC MGXS type to use for DONJON scattering. When
        omitted, only ordinary ``scatter matrix`` MGXS is accepted. ``nu`` or
        ``consistent nu`` scattering can be exported only by explicitly naming
        that MGXS type here.
    overwrite:
        If ``False``, fail when the output file already exists.
    """

    import h5py

    path = Path(output_path)
    if path.exists() and not overwrite:
        raise FileExistsError(path)

    energy_bounds = _energy_bounds_from_library(library)
    ngroups = len(energy_bounds) - 1
    if ngroups <= 0:
        raise ValueError("energy group structure must contain at least one group")

    specs = _export_specs_from_library(library, domain_specs)
    if not specs:
        raise ValueError("library contains no domains")
    scatter_type_label = _scatter_mgxs_type_label(scatter_mgxs_type)

    exported: list[tuple[ExportedDomain, dict[str, Any]]] = []
    legendre_order = 0
    used_names: set[str] = set()
    for index, spec in enumerate(specs, start=1):
        name = _domain_name(spec.domain, index, domain_names, used_names, spec.name)
        data = _domain_data(
            library,
            spec.domain,
            ngroups,
            xs_kwargs=spec.xs_kwargs,
            scatter_mgxs_type=scatter_mgxs_type,
        )
        if spec.volume is not None:
            data["volume"] = float(spec.volume)
        legendre_order = max(legendre_order, data["scatter_matrix"].shape[0] - 1)
        exported.append(
            (
                ExportedDomain(
                    name=name,
                    source=spec.domain,
                    xs_kwargs=spec.xs_kwargs,
                    scatter_mgxs_type=str(data["scatter_mgxs_type"]),
                ),
                data | {"attrs": spec.attrs or {}},
            )
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = ngroups
        h5.attrs["legendre_order"] = legendre_order
        h5.attrs["source"] = "OpenMC mgxs.Library"
        h5.attrs["openmc_scatter_mgxs_type"] = scatter_type_label
        for attr_key, attr_value in (root_attrs or {}).items():
            _write_hdf5_attr(h5, str(attr_key), attr_value)
        h5.attrs["energy_bounds_sha256"] = energy_bounds_sha256(energy_bounds)
        h5.create_dataset("energy_bounds", data=energy_bounds)
        mixtures = h5.create_group("mixtures")
        for domain_summary, data in exported:
            group = mixtures.create_group(domain_summary.name)
            group.attrs["fissionable"] = bool(data["fissionable"])
            group.attrs["scatter_format"] = "legendre"
            group.attrs["scatter_axes"] = "moment,from,to"
            group.attrs["openmc_scatter_mgxs_type"] = str(data["scatter_mgxs_type"])
            if data["volume"] is not None:
                group.attrs["volume"] = float(data["volume"])
            for attr_key, attr_value in data["attrs"].items():
                _write_hdf5_attr(group, str(attr_key), attr_value)
            for key in (
                "total",
                "absorption",
                "fission",
                "kappa_fission",
                "nu_fission",
                "chi",
                "transport_total",
                "inverse_velocity",
            ):
                value = data.get(key)
                if value is not None:
                    group.create_dataset(key, data=value)
                std_dev = data.get(f"{key}_std_dev")
                if std_dev is not None:
                    group.create_dataset(f"{key}_std_dev", data=std_dev)
            group.create_dataset(
                "scatter_matrix",
                data=_pad_scatter_moments(data["scatter_matrix"], legendre_order + 1),
            )
            scatter_std_dev = data.get("scatter_matrix_std_dev")
            if scatter_std_dev is not None:
                group.create_dataset(
                    "scatter_matrix_std_dev",
                    data=_pad_scatter_moments(scatter_std_dev, legendre_order + 1),
                )

    return ExportSummary(
        output_path=path,
        energy_groups=ngroups,
        legendre_order=legendre_order,
        domains=tuple(domain for domain, _data in exported),
        scatter_mgxs_type=scatter_type_label,
    )


def _export_specs_from_library(
    library: Any,
    domain_specs: Sequence[DomainExportSpec | Mapping[str, Any]] | None,
) -> list[DomainExportSpec]:
    if domain_specs is None:
        return [
            DomainExportSpec(domain=domain)
            for domain in getattr(library, "domains", []) or []
        ]
    specs: list[DomainExportSpec] = []
    for spec in domain_specs:
        if isinstance(spec, DomainExportSpec):
            specs.append(spec)
        else:
            specs.append(DomainExportSpec(**dict(spec)))
    return specs


def _domain_data(
    library: Any,
    domain: Any,
    ngroups: int,
    *,
    xs_kwargs: Mapping[str, Any] | None,
    scatter_mgxs_type: str | None,
) -> dict[str, Any]:
    total = _required_vector(library, domain, "total", ngroups, xs_kwargs=xs_kwargs)
    absorption = _required_vector(
        library,
        domain,
        "absorption",
        ngroups,
        xs_kwargs=xs_kwargs,
    )
    scatter, scatter_std_dev, actual_scatter_mgxs_type = _required_scatter(
        library,
        domain,
        ngroups,
        xs_kwargs=xs_kwargs,
        scatter_mgxs_type=scatter_mgxs_type,
    )

    fission = _optional_vector(library, domain, "fission", ngroups, xs_kwargs=xs_kwargs)
    kappa_fission = _optional_vector(
        library,
        domain,
        "kappa_fission",
        ngroups,
        xs_kwargs=xs_kwargs,
    )
    nu_fission = _optional_vector(library, domain, "nu_fission", ngroups, xs_kwargs=xs_kwargs)
    chi = _optional_vector(library, domain, "chi", ngroups, xs_kwargs=xs_kwargs)
    has_fission_source = (
        nu_fission is not None
        and chi is not None
        and np.sum(np.abs(nu_fission)) > 1.0e-12
        and np.sum(np.abs(chi)) > 1.0e-12
    )
    if fission is None:
        fission = np.zeros(ngroups, dtype=float)
    if nu_fission is None:
        nu_fission = np.zeros(ngroups, dtype=float)
    if chi is None:
        chi = np.zeros(ngroups, dtype=float)

    return {
        "total": total,
        "total_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "total",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "absorption": absorption,
        "absorption_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "absorption",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "fission": fission,
        "fission_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "fission",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "kappa_fission": kappa_fission,
        "kappa_fission_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "kappa_fission",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "nu_fission": nu_fission,
        "nu_fission_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "nu_fission",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "chi": chi,
        "chi_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "chi",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "scatter_matrix": scatter,
        "scatter_matrix_std_dev": scatter_std_dev,
        "scatter_mgxs_type": actual_scatter_mgxs_type,
        "transport_total": _optional_vector(
            library,
            domain,
            "transport_total",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "transport_total_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "transport_total",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "inverse_velocity": _optional_vector(
            library,
            domain,
            "inverse_velocity",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "inverse_velocity_std_dev": _optional_vector_std_dev(
            library,
            domain,
            "inverse_velocity",
            ngroups,
            xs_kwargs=xs_kwargs,
        ),
        "volume": _domain_volume(domain),
        "fissionable": bool(_domain_fissionable(domain, has_fission_source)),
    }


def _required_vector(
    library: Any,
    domain: Any,
    key: str,
    ngroups: int,
    *,
    xs_kwargs: Mapping[str, Any] | None,
) -> np.ndarray:
    vector = _optional_vector(library, domain, key, ngroups, xs_kwargs=xs_kwargs)
    if vector is None:
        raise ValueError(f"domain {_domain_label(domain)}: missing required MGXS {key!r}")
    return vector


def _optional_vector(
    library: Any,
    domain: Any,
    key: str,
    ngroups: int,
    *,
    xs_kwargs: Mapping[str, Any] | None,
) -> np.ndarray | None:
    mgxs = _get_mgxs_optional(library, domain, key)
    if mgxs is None:
        return None
    return _as_group_vector(
        _mgxs_values(mgxs, xs_kwargs=xs_kwargs),
        ngroups,
        _domain_label(domain),
        key,
    )


def _optional_vector_std_dev(
    library: Any,
    domain: Any,
    key: str,
    ngroups: int,
    *,
    xs_kwargs: Mapping[str, Any] | None,
) -> np.ndarray | None:
    mgxs = _get_mgxs_optional(library, domain, key)
    if mgxs is None:
        return None
    values = _mgxs_std_dev(mgxs, xs_kwargs=xs_kwargs)
    if values is None:
        return None
    return _as_group_vector(
        values,
        ngroups,
        _domain_label(domain),
        f"{key}_std_dev",
    )


def _required_scatter(
    library: Any,
    domain: Any,
    ngroups: int,
    *,
    xs_kwargs: Mapping[str, Any] | None,
    scatter_mgxs_type: str | None,
) -> tuple[np.ndarray, np.ndarray | None, str]:
    mgxs_type_names = _scatter_mgxs_type_candidates(scatter_mgxs_type)
    mgxs, actual_type = _get_mgxs_optional_with_type(
        library,
        domain,
        "scatter_matrix",
        mgxs_type_names=mgxs_type_names,
    )
    if mgxs is None:
        if scatter_mgxs_type is None:
            nu_type = _find_available_mgxs_type(library, domain, NU_SCATTER_MGXS_TYPES)
            if nu_type is not None:
                raise ValueError(
                    f"domain {_domain_label(domain)}: missing ordinary OpenMC MGXS "
                    f"'scatter matrix'; found {nu_type!r}. DONJON scattering "
                    "expects ordinary scattering by default. Add 'scatter matrix' "
                    "to library.mgxs_types, or explicitly pass "
                    f"scatter_mgxs_type={nu_type!r} if nu-scatter is intentional."
                )
        raise ValueError(
            f"domain {_domain_label(domain)}: missing required MGXS "
            f"{' / '.join(mgxs_type_names)}"
        )
    scatter = _as_scatter_moments(
        _mgxs_values(mgxs, xs_kwargs=xs_kwargs),
        ngroups,
        _domain_label(domain),
    )
    std_dev_values = _mgxs_std_dev(mgxs, xs_kwargs=xs_kwargs)
    scatter_std_dev = (
        None
        if std_dev_values is None
        else _as_scatter_moments(
            std_dev_values,
            ngroups,
            _domain_label(domain),
        )
    )
    return scatter, scatter_std_dev, actual_type or _scatter_mgxs_type_label(scatter_mgxs_type)


def _get_mgxs_optional(library: Any, domain: Any, key: str) -> Any | None:
    mgxs, _mgxs_type = _get_mgxs_optional_with_type(library, domain, key)
    return mgxs


def _get_mgxs_optional_with_type(
    library: Any,
    domain: Any,
    key: str,
    *,
    mgxs_type_names: Sequence[str] | None = None,
) -> tuple[Any | None, str | None]:
    for mgxs_type in mgxs_type_names or MGXS_TYPE_ALIASES[key]:
        try:
            return library.get_mgxs(domain, mgxs_type), mgxs_type
        except (KeyError, ValueError, LookupError, AttributeError):
            continue
        except TypeError:
            try:
                return library.get_mgxs(domain=domain, mgxs_type=mgxs_type), mgxs_type
            except (KeyError, ValueError, LookupError, AttributeError):
                continue
    return None, None


def _find_available_mgxs_type(
    library: Any,
    domain: Any,
    mgxs_type_names: Sequence[str],
) -> str | None:
    _mgxs, mgxs_type = _get_mgxs_optional_with_type(
        library,
        domain,
        "scatter_matrix",
        mgxs_type_names=mgxs_type_names,
    )
    return mgxs_type


def _scatter_mgxs_type_candidates(scatter_mgxs_type: str | None) -> tuple[str, ...]:
    if scatter_mgxs_type is None:
        return MGXS_TYPE_ALIASES["scatter_matrix"]
    value = str(scatter_mgxs_type).strip()
    if not value:
        raise ValueError("scatter_mgxs_type must not be empty")
    return (value,)


def _scatter_mgxs_type_label(scatter_mgxs_type: str | None) -> str:
    return _scatter_mgxs_type_candidates(scatter_mgxs_type)[0]


def _mgxs_values(mgxs: Any, *, xs_kwargs: Mapping[str, Any] | None) -> np.ndarray:
    extra_kwargs = dict(xs_kwargs or {})
    if hasattr(mgxs, "get_xs"):
        for base_kwargs in (
            {"nuclides": "sum"},
            {"nuclides": "sum", "xs_type": "macro"},
            {},
        ):
            kwargs = {**base_kwargs, **extra_kwargs}
            try:
                return np.asarray(mgxs.get_xs(**kwargs), dtype=float)
            except TypeError:
                continue
    for attr in ("mean", "xs", "data"):
        if hasattr(mgxs, attr):
            value = getattr(mgxs, attr)
            if callable(value):
                value = value()
            return np.asarray(value, dtype=float)
    raise TypeError(f"cannot extract XS values from {type(mgxs)!r}")


def _mgxs_std_dev(mgxs: Any, *, xs_kwargs: Mapping[str, Any] | None) -> np.ndarray | None:
    for attr in ("std_dev", "stddev", "std"):
        if hasattr(mgxs, attr):
            value = getattr(mgxs, attr)
            if callable(value):
                value = value()
            return np.asarray(value, dtype=float)
    if not hasattr(mgxs, "get_xs"):
        return None
    if not _get_xs_has_value_parameter(mgxs.get_xs):
        return None
    extra_kwargs = dict(xs_kwargs or {})
    for base_kwargs in (
        {"nuclides": "sum", "value": "std_dev"},
        {"nuclides": "sum", "xs_type": "macro", "value": "std_dev"},
        {"value": "std_dev"},
    ):
        kwargs = {**base_kwargs, **extra_kwargs}
        try:
            return np.asarray(mgxs.get_xs(**kwargs), dtype=float)
        except (TypeError, ValueError, LookupError, AttributeError, KeyError):
            continue
    return None


def _get_xs_has_value_parameter(method: Any) -> bool:
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False
    return "value" in parameters


def _as_group_vector(
    values: np.ndarray,
    ngroups: int,
    domain_name: str,
    field_name: str,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float).squeeze()
    if arr.ndim == 0:
        if ngroups == 1:
            return np.asarray([float(arr)], dtype=float)
        raise ValueError(f"domain {domain_name}: {field_name} is scalar, expected {ngroups}")
    if arr.ndim > 1:
        ones_removed = np.squeeze(arr)
        arr = np.asarray(ones_removed, dtype=float)
    if arr.ndim != 1 or arr.shape[0] != ngroups:
        raise ValueError(
            f"domain {domain_name}: {field_name} must be a length-{ngroups} vector, "
            f"got shape {np.asarray(values).shape}"
        )
    return arr.astype(float, copy=False)


def _as_scatter_moments(values: np.ndarray, ngroups: int, domain_name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float).squeeze()
    if ngroups == 1:
        if arr.ndim == 0:
            return np.asarray([[[float(arr)]]], dtype=float)
        if arr.ndim == 1:
            return arr.reshape((arr.shape[0], 1, 1))
    if arr.shape == (ngroups, ngroups):
        return arr.reshape((1, ngroups, ngroups))
    if arr.ndim != 3:
        raise ValueError(
            f"domain {domain_name}: scatter matrix must be 2D or 3D, got shape {arr.shape}"
        )
    # OpenMC ScatterMatrixXS.get_xs(moment="all") returns [from, to, moment].
    # In a 2-group P1 calculation this shape is (2, 2, 2), so the usual shape
    # inference is ambiguous. Prefer OpenMC's native moment-last convention.
    if arr.shape[:2] == (ngroups, ngroups):
        return np.moveaxis(arr, -1, 0)
    if arr.shape[1:] == (ngroups, ngroups):
        return arr
    raise ValueError(
        f"domain {domain_name}: scatter matrix shape {arr.shape} is incompatible with "
        f"{ngroups} groups"
    )


def _pad_scatter_moments(scatter: np.ndarray, nmoments: int) -> np.ndarray:
    if scatter.shape[0] == nmoments:
        return scatter
    if scatter.shape[0] > nmoments:
        raise ValueError("scatter has more moments than the requested output order")
    padded = np.zeros((nmoments, scatter.shape[1], scatter.shape[2]), dtype=float)
    padded[: scatter.shape[0], :, :] = scatter
    return padded


def _energy_bounds_from_library(library: Any) -> np.ndarray:
    groups = getattr(library, "energy_groups", None)
    for source in (groups, library):
        if source is None:
            continue
        for attr in ("group_edges", "groups", "energy_bounds"):
            if hasattr(source, attr):
                value = getattr(source, attr)
                if callable(value):
                    value = value()
                bounds = np.asarray(value, dtype=float).squeeze()
                if bounds.ndim != 1 or bounds.size < 2:
                    raise ValueError("energy bounds must be a one-dimensional array")
                if bounds[0] > bounds[-1]:
                    bounds = bounds[::-1]
                return bounds
    raise ValueError("cannot find energy group bounds on library")


def _domain_name(
    domain: Any,
    index: int,
    domain_names: Mapping[Any, str] | None,
    used: set[str],
    preferred_name: str | None = None,
) -> str:
    raw = preferred_name or _mapped_domain_name(domain, domain_names)
    if raw is None:
        raw = getattr(domain, "name", None) or getattr(domain, "id", None) or f"domain_{index}"
    name = _safe_hdf5_name(str(raw))
    if not name:
        name = f"domain_{index}"
    base = name
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def _mapped_domain_name(domain: Any, domain_names: Mapping[Any, str] | None) -> str | None:
    if domain_names is None:
        return None
    candidates = [
        domain,
        getattr(domain, "id", None),
        getattr(domain, "name", None),
        str(domain),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            if candidate in domain_names:
                return str(domain_names[candidate])
        except TypeError:
            continue
    return None


def _safe_hdf5_name(name: str) -> str:
    return name.strip().replace("/", "_").replace("\x00", "_")


def _domain_label(domain: Any) -> str:
    return str(getattr(domain, "name", None) or getattr(domain, "id", None) or domain)


def _domain_volume(domain: Any) -> float | None:
    for attr in ("volume", "vol"):
        if hasattr(domain, attr):
            value = getattr(domain, attr)
            if callable(value):
                value = value()
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _domain_fissionable(domain: Any, fallback: bool) -> bool:
    if hasattr(domain, "fissionable"):
        return bool(getattr(domain, "fissionable"))
    fill = getattr(domain, "fill", None)
    if fill is not None and hasattr(fill, "fissionable"):
        return bool(getattr(fill, "fissionable"))
    return fallback


def _write_hdf5_attr(target: Any, key: str, value: Any) -> None:
    if isinstance(value, (list, tuple)):
        target.attrs[key] = np.asarray(value)
    else:
        target.attrs[key] = value

"""Export OpenMC MGXS-like libraries to the openmc2donjon HDF5 contract.

The exporter is intentionally duck-typed.  It does not import OpenMC at module
import time; instead it expects an object with the parts of the OpenMC
``mgxs.Library`` interface that are needed here:

- ``energy_groups`` with ``group_edges`` or ``groups``;
- ``domains``;
- ``get_mgxs(domain, mgxs_type)`` returning objects with ``get_xs()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np


MGXS_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "total": ("total",),
    "absorption": ("absorption",),
    "fission": ("fission",),
    "nu_fission": ("nu-fission", "nu_fission"),
    "chi": ("chi",),
    "scatter_matrix": ("scatter matrix", "scatter_matrix"),
    "transport_total": ("transport", "transport_total"),
    "inverse_velocity": ("inverse-velocity", "inverse_velocity"),
}


@dataclass(frozen=True)
class ExportedDomain:
    """Summary for one exported spatial domain."""

    name: str
    source: Any


@dataclass(frozen=True)
class ExportSummary:
    """Machine-readable summary of an export operation."""

    output_path: Path
    energy_groups: int
    legendre_order: int
    domains: tuple[ExportedDomain, ...]


def export_openmc_mgxs_library(
    library: Any,
    output_path: str | Path,
    *,
    domain_names: Mapping[Any, str] | None = None,
    overwrite: bool = True,
) -> ExportSummary:
    """Write an OpenMC MGXS-like library to the HDF5 input contract.

    Parameters
    ----------
    library:
        OpenMC ``mgxs.Library`` or a compatible object.
    output_path:
        HDF5 file to write.
    domain_names:
        Optional mapping from domain object, domain id, or domain name to a
        stable output name.
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

    domains = list(getattr(library, "domains", []) or [])
    if not domains:
        raise ValueError("library contains no domains")

    exported: list[tuple[ExportedDomain, dict[str, Any]]] = []
    legendre_order = 0
    used_names: set[str] = set()
    for index, domain in enumerate(domains, start=1):
        name = _domain_name(domain, index, domain_names, used_names)
        data = _domain_data(library, domain, ngroups)
        legendre_order = max(legendre_order, data["scatter_matrix"].shape[0] - 1)
        exported.append((ExportedDomain(name=name, source=domain), data))

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = ngroups
        h5.attrs["legendre_order"] = legendre_order
        h5.attrs["source"] = "OpenMC mgxs.Library"
        h5.create_dataset("energy_bounds", data=energy_bounds)
        mixtures = h5.create_group("mixtures")
        for domain_summary, data in exported:
            group = mixtures.create_group(domain_summary.name)
            group.attrs["fissionable"] = bool(data["fissionable"])
            group.attrs["scatter_format"] = "legendre"
            group.attrs["scatter_axes"] = "moment,from,to"
            group.attrs["volume"] = float(data["volume"])
            for key in (
                "total",
                "absorption",
                "fission",
                "nu_fission",
                "chi",
                "transport_total",
                "inverse_velocity",
            ):
                value = data.get(key)
                if value is not None:
                    group.create_dataset(key, data=value)
            group.create_dataset(
                "scatter_matrix",
                data=_pad_scatter_moments(data["scatter_matrix"], legendre_order + 1),
            )

    return ExportSummary(
        output_path=path,
        energy_groups=ngroups,
        legendre_order=legendre_order,
        domains=tuple(domain for domain, _data in exported),
    )


def _domain_data(library: Any, domain: Any, ngroups: int) -> dict[str, Any]:
    total = _required_vector(library, domain, "total", ngroups)
    absorption = _required_vector(library, domain, "absorption", ngroups)
    scatter = _required_scatter(library, domain, ngroups)

    fission = _optional_vector(library, domain, "fission", ngroups)
    nu_fission = _optional_vector(library, domain, "nu_fission", ngroups)
    chi = _optional_vector(library, domain, "chi", ngroups)
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
        "absorption": absorption,
        "fission": fission,
        "nu_fission": nu_fission,
        "chi": chi,
        "scatter_matrix": scatter,
        "transport_total": _optional_vector(library, domain, "transport_total", ngroups),
        "inverse_velocity": _optional_vector(library, domain, "inverse_velocity", ngroups),
        "volume": _domain_volume(domain),
        "fissionable": bool(_domain_fissionable(domain, has_fission_source)),
    }


def _required_vector(library: Any, domain: Any, key: str, ngroups: int) -> np.ndarray:
    vector = _optional_vector(library, domain, key, ngroups)
    if vector is None:
        raise ValueError(f"domain {_domain_label(domain)}: missing required MGXS {key!r}")
    return vector


def _optional_vector(
    library: Any,
    domain: Any,
    key: str,
    ngroups: int,
) -> np.ndarray | None:
    mgxs = _get_mgxs_optional(library, domain, key)
    if mgxs is None:
        return None
    return _as_group_vector(_mgxs_values(mgxs), ngroups, _domain_label(domain), key)


def _required_scatter(library: Any, domain: Any, ngroups: int) -> np.ndarray:
    mgxs = _get_mgxs_optional(library, domain, "scatter_matrix")
    if mgxs is None:
        raise ValueError(
            f"domain {_domain_label(domain)}: missing required MGXS 'scatter matrix'"
        )
    return _as_scatter_moments(_mgxs_values(mgxs), ngroups, _domain_label(domain))


def _get_mgxs_optional(library: Any, domain: Any, key: str) -> Any | None:
    for mgxs_type in MGXS_TYPE_ALIASES[key]:
        try:
            return library.get_mgxs(domain, mgxs_type)
        except (KeyError, ValueError, LookupError, AttributeError):
            continue
        except TypeError:
            try:
                return library.get_mgxs(domain=domain, mgxs_type=mgxs_type)
            except (KeyError, ValueError, LookupError, AttributeError):
                continue
    return None


def _mgxs_values(mgxs: Any) -> np.ndarray:
    if hasattr(mgxs, "get_xs"):
        for kwargs in (
            {"nuclides": "sum"},
            {"nuclides": "sum", "xs_type": "macro"},
            {},
        ):
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


def _as_group_vector(
    values: np.ndarray,
    ngroups: int,
    domain_name: str,
    field_name: str,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float).squeeze()
    if arr.ndim == 0:
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
    if arr.shape == (ngroups, ngroups):
        return arr.reshape((1, ngroups, ngroups))
    if arr.ndim != 3:
        raise ValueError(
            f"domain {domain_name}: scatter matrix must be 2D or 3D, got shape {arr.shape}"
        )
    if arr.shape[1:] == (ngroups, ngroups):
        return arr
    if arr.shape[:2] == (ngroups, ngroups):
        return np.moveaxis(arr, -1, 0)
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
) -> str:
    raw = _mapped_domain_name(domain, domain_names)
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


def _domain_volume(domain: Any) -> float:
    for attr in ("volume", "vol"):
        if hasattr(domain, attr):
            value = getattr(domain, attr)
            if callable(value):
                value = value()
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 1.0


def _domain_fissionable(domain: Any, fallback: bool) -> bool:
    if hasattr(domain, "fissionable"):
        return bool(getattr(domain, "fissionable"))
    fill = getattr(domain, "fill", None)
    if fill is not None and hasattr(fill, "fissionable"):
        return bool(getattr(fill, "fissionable"))
    return fallback

"""Small HDF5 dataset metadata helpers used by production audits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Hdf5DatasetMetadata:
    requested_source: str
    source: str
    path: Path
    dataset: str
    shape: tuple[int, ...]
    group_order: str | None
    mixture_names: tuple[str, ...]
    energy_groups: int | None


def read_hdf5_dataset_metadata(
    source: str | Path,
    *,
    default_datasets: tuple[str, ...],
) -> Hdf5DatasetMetadata:
    """Read shape, mixture order, and group-order metadata for a dataset."""

    import h5py

    requested = str(source)
    path, dataset = split_dataset_reference(requested)
    with h5py.File(path, "r") as h5:
        dataset_path = dataset or _first_dataset(h5, default_datasets, requested)
        obj = h5[dataset_path]
        if hasattr(obj, "keys"):
            raise ValueError(f"HDF5 path is a group, not a dataset: /{dataset_path}")
        shape = tuple(int(value) for value in obj.shape)
        mixture_names = _names_from_hdf5(
            obj,
            h5,
            ("mixture_names", "mixtures", "domain_names"),
        )
        group_order = _text_attr(obj, h5, "group_order")
        energy_groups = _energy_groups(obj, h5, shape)
    return Hdf5DatasetMetadata(
        requested_source=requested,
        source=f"{path}::{dataset_path}",
        path=path,
        dataset=dataset_path,
        shape=shape,
        group_order=group_order,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
    )


def split_dataset_reference(reference: str | Path) -> tuple[Path, str | None]:
    raw = str(reference)
    if "::" not in raw:
        return Path(raw), None
    path, dataset = raw.split("::", 1)
    dataset = dataset.strip("/")
    if not dataset:
        raise ValueError(f"empty dataset reference in {raw!r}")
    return Path(path), dataset


def _first_dataset(h5: Any, candidates: tuple[str, ...], source: str) -> str:
    for candidate in candidates:
        if candidate in h5 and not hasattr(h5[candidate], "keys"):
            return candidate
    rendered = ", ".join(f"/{name}" for name in candidates)
    raise ValueError(f"{source} must contain one of: {rendered}")


def _text_attr(obj: Any, root: Any, name: str) -> str | None:
    for attrs in (obj.attrs, root.attrs):
        if name not in attrs:
            continue
        value = attrs[name]
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if isinstance(value, np.bytes_):
            return value.astype(str).item()
        return str(value)
    return None


def _names_from_hdf5(
    obj: Any,
    root: Any,
    candidates: tuple[str, ...],
) -> tuple[str, ...]:
    for candidate in candidates:
        if candidate in obj.attrs:
            return _flatten_names(obj.attrs[candidate])
    for candidate in candidates:
        if candidate in root.attrs:
            return _flatten_names(root.attrs[candidate])
    for candidate in candidates:
        if candidate in root and not hasattr(root[candidate], "keys"):
            return _flatten_names(root[candidate][:])
    return ()


def _flatten_names(raw: Any) -> tuple[str, ...]:
    arr = np.asarray(raw)
    out: list[str] = []
    for value in arr.reshape(-1):
        if isinstance(value, bytes):
            out.append(value.decode("utf-8").rstrip("\x00").strip())
        elif isinstance(value, np.bytes_):
            out.append(value.astype(str).item().rstrip("\x00").strip())
        else:
            out.append(str(value).rstrip("\x00").strip())
    return tuple(out)


def _energy_groups(obj: Any, root: Any, shape: tuple[int, ...]) -> int | None:
    for attrs in (obj.attrs, root.attrs):
        if "energy_groups" in attrs:
            return int(attrs["energy_groups"])
    if "energy_bounds" in root and not hasattr(root["energy_bounds"], "keys"):
        return int(root["energy_bounds"].shape[0]) - 1
    if len(shape) >= 2:
        return int(shape[1])
    if len(shape) == 1:
        return int(shape[0])
    return None

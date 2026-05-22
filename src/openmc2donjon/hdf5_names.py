"""Small HDF5 naming helpers shared by converter workflows."""

from __future__ import annotations

from typing import Any

import numpy as np


def decode_hdf5_names(values: Any) -> tuple[str, ...]:
    """Decode a byte/string HDF5 name vector to Python strings."""

    array = np.asarray(values).reshape(-1)
    names: list[str] = []
    for value in array:
        if isinstance(value, bytes):
            names.append(value.decode("utf-8"))
        else:
            names.append(str(value))
    return tuple(names)


def read_mixture_names(h5) -> tuple[str, ...]:
    """Return the canonical mixture order for an MGXS HDF5 file.

    New exporter-produced files declare ``/mixture_names`` because HDF5 group
    iteration order is not a reliable physics ordering contract.  Older files
    fall back to the existing ``/mixtures`` group key order.
    """

    if "mixtures" not in h5 or not hasattr(h5["mixtures"], "keys"):
        raise ValueError("input HDF5 must contain a /mixtures group")

    group_names = tuple(str(name) for name in h5["mixtures"].keys())
    if not group_names:
        raise ValueError("input HDF5 contains no mixtures")

    if "mixture_names" not in h5:
        return group_names

    names = decode_hdf5_names(h5["mixture_names"][:])
    if not names:
        raise ValueError("/mixture_names is empty")
    if len(set(names)) != len(names):
        raise ValueError("/mixture_names contains duplicate entries")
    missing = [name for name in names if name not in h5["mixtures"]]
    extra = sorted(set(group_names) - set(names))
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing mixture group(s): {', '.join(missing)}")
        if extra:
            details.append(f"undeclared mixture group(s): {', '.join(extra)}")
        raise ValueError(
            "/mixture_names does not match /mixtures: " + "; ".join(details)
        )
    return names


def write_string_dataset(parent, name: str, values: tuple[str, ...] | list[str]) -> None:
    """Write a UTF-8 string vector dataset."""

    import h5py

    dtype = h5py.string_dtype(encoding="utf-8")
    parent.create_dataset(
        name,
        data=np.asarray(list(values), dtype=object),
        dtype=dtype,
    )

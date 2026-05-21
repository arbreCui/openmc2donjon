"""Adapter template for externally computed homogeneous face fluxes.

Edit this file for a production solver by replacing the raw dataset path and
metadata handling. The output HDF5 is intentionally small and canonical:

    /homogeneous_face_flux  shape=(mixture, face, group)
    /mixture_names
    /face_names
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


SCHEMA = "openmc2donjon.external-face-flux.v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mgxs_h5", type=Path, help="openmc2donjon MGXS HDF5 handoff")
    parser.add_argument("raw_h5", type=Path, help="external solver HDF5 file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="canonical homogeneous-face-flux HDF5 output",
    )
    parser.add_argument(
        "--dataset",
        default="solver/face_flux",
        help="raw dataset path inside raw_h5 (default: solver/face_flux)",
    )
    parser.add_argument(
        "--faces",
        required=True,
        help="comma-separated canonical face order expected by the MGXS/ADF workflow",
    )
    parser.add_argument(
        "--layout",
        choices=("MFG", "MGF"),
        default="MGF",
        help="raw rank-3 dataset layout: MFG=(mixture,face,group), MGF=(mixture,group,face)",
    )
    parser.add_argument(
        "--source-label",
        default="external homogeneous face-flux adapter",
        help="provenance label written to output attributes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the output file if it already exists",
    )
    args = parser.parse_args(argv)

    mixture_names, energy_groups = _read_mgxs_metadata(args.mgxs_h5)
    face_names = _parse_faces(args.faces)
    values = _read_raw_values(
        args.raw_h5,
        args.dataset,
        layout=args.layout,
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
    )
    _write_output(
        args.output,
        values,
        mixture_names=mixture_names,
        face_names=face_names,
        mgxs_h5=args.mgxs_h5,
        raw_h5=args.raw_h5,
        raw_dataset=args.dataset,
        source_label=args.source_label,
        force=args.force,
    )
    print("external homogeneous face-flux adapter")
    print(f"  input: {args.raw_h5}::{args.dataset.strip('/')}")
    print(f"  output: {args.output}")
    print(
        f"  wrote {len(mixture_names)} mixture(s), {len(face_names)} face(s), "
        f"{energy_groups} group(s)"
    )
    return 0


def _read_mgxs_metadata(path: Path) -> tuple[tuple[str, ...], int]:
    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError(f"{path}: missing /mixtures group")
        mixture_names = tuple(str(name) for name in h5["mixtures"])
        if not mixture_names:
            raise ValueError(f"{path}: no mixtures found")
        if "energy_groups" in h5.attrs:
            energy_groups = int(h5.attrs["energy_groups"])
        elif "energy_bounds" in h5:
            energy_groups = int(h5["energy_bounds"].shape[0]) - 1
        else:
            raise ValueError(f"{path}: missing energy_groups or energy_bounds")
    return mixture_names, energy_groups


def _read_raw_values(
    path: Path,
    dataset_path: str,
    *,
    layout: str,
    mixture_names: tuple[str, ...],
    face_names: tuple[str, ...],
    energy_groups: int,
) -> np.ndarray:
    dataset_path = dataset_path.strip("/")
    with h5py.File(path, "r") as h5:
        if dataset_path not in h5:
            raise ValueError(f"{path}: raw dataset not found: /{dataset_path}")
        dataset = h5[dataset_path]
        values = np.asarray(dataset[:], dtype=float)
        raw_mixtures = _names_from_hdf5(dataset, h5, ("mixture_names", "mixtures"))
        raw_faces = _names_from_hdf5(dataset, h5, ("face_names", "faces", "boundary_names"))
    if values.ndim != 3:
        raise ValueError(f"{path}: raw face flux must be rank 3, got shape {values.shape}")
    if layout == "MGF":
        values = np.transpose(values, (0, 2, 1))
    if values.shape[2] != energy_groups:
        raise ValueError(
            f"{path}: raw group axis has {values.shape[2]} entries, expected {energy_groups}"
        )
    values = _reorder_axis(
        values,
        axis=0,
        declared=raw_mixtures,
        expected=mixture_names,
        label="mixture",
    )
    values = _reorder_axis(
        values,
        axis=1,
        declared=raw_faces,
        expected=face_names,
        label="face",
    )
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError("homogeneous face flux values must be positive and finite")
    return values


def _reorder_axis(
    values: np.ndarray,
    *,
    axis: int,
    declared: tuple[str, ...] | None,
    expected: tuple[str, ...],
    label: str,
) -> np.ndarray:
    if declared is None:
        if values.shape[axis] != len(expected):
            raise ValueError(
                f"raw {label} axis has {values.shape[axis]} entries, expected {len(expected)}"
            )
        return values
    if set(declared) != set(expected):
        raise ValueError(f"raw {label} names {declared!r} do not match expected {expected!r}")
    order = [declared.index(name) for name in expected]
    return np.take(values, order, axis=axis)


def _write_output(
    path: Path,
    values: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
    face_names: tuple[str, ...],
    mgxs_h5: Path,
    raw_h5: Path,
    raw_dataset: str,
    source_label: str,
    force: bool,
) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = SCHEMA
        h5.attrs["source"] = source_label
        h5.attrs["source_mgxs"] = str(mgxs_h5)
        h5.attrs["source_raw_h5"] = str(raw_h5)
        h5.attrs["source_raw_dataset"] = raw_dataset.strip("/")
        h5.create_dataset("mixture_names", data=np.asarray(mixture_names, dtype="S"))
        h5.create_dataset("face_names", data=np.asarray(face_names, dtype="S"))
        dataset = h5.create_dataset("homogeneous_face_flux", data=values)
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        dataset.attrs["face_names"] = np.asarray(face_names, dtype="S")


def _names_from_hdf5(dataset, root, keys: tuple[str, ...]) -> tuple[str, ...] | None:
    for key in keys:
        if key in dataset.attrs:
            return tuple(_decode_name(value) for value in np.asarray(dataset.attrs[key]).reshape(-1))
        if key in root and not hasattr(root[key], "keys"):
            return tuple(_decode_name(value) for value in np.asarray(root[key][:]).reshape(-1))
    return None


def _decode_name(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8").rstrip("\x00")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8").rstrip("\x00")
    return str(value)


def _parse_faces(value: str) -> tuple[str, ...]:
    faces = tuple(item.strip() for item in value.split(",") if item.strip())
    if not faces:
        raise ValueError("--faces must name at least one face")
    return faces


if __name__ == "__main__":
    raise SystemExit(main())

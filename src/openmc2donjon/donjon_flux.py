"""Extract canonical volume flux from DONJON ``L_FLUX`` ASCII dumps."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from . import lcm_ascii as lcm


SCHEMA = "openmc2donjon.donjon-volume-flux.v1"
PASS_DECISION = "openmc2donjon_donjon_volume_flux_passed"


@dataclass(frozen=True)
class DonjonVolumeFluxReport:
    input_h5: Path
    flux_dump: Path
    output_h5: Path
    map_h5: Path | None
    mixture_names: tuple[str, ...]
    energy_groups: int
    flux_vector_count: int
    flux_unknown_count: int
    scalar_flux_ids: tuple[int, ...]
    minimum: float
    maximum: float
    source_label: str


def extract_donjon_volume_flux(
    input_h5: str | Path,
    flux_dump: str | Path,
    output_h5: str | Path,
    *,
    map_h5: str | Path | None = None,
    scalar_flux_ids: dict[str, int] | None = None,
    scalar_flux_column: int = 0,
    list_offset: int = 0,
    source_label: str = "DONJON L_FLUX scalar unknown extraction",
    force: bool = False,
    summary_json: str | Path | None = None,
) -> DonjonVolumeFluxReport:
    """Write DONJON scalar flux unknowns as canonical ``(mixture, group)`` HDF5.

    ``flux_dump`` must be a DONJON text result containing a ``UTL: FLUX ::
    IMPR STATE-VECTOR * DUMP`` block.  The group flux vectors are read from
    unnamed real list records.  The scalar unknown ID for each mixture can be
    supplied explicitly with ``scalar_flux_ids`` or through ``map_h5``.
    """

    input_path = Path(input_h5)
    flux_path = Path(flux_dump)
    output_path = Path(output_h5)
    map_path = None if map_h5 is None else Path(map_h5)
    if not input_path.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_path}")
    if not flux_path.exists():
        raise FileNotFoundError(f"DONJON flux dump does not exist: {flux_path}")
    if map_path is not None and not map_path.exists():
        raise FileNotFoundError(f"flux map HDF5 does not exist: {map_path}")
    if output_path.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_path}")
    if scalar_flux_column < 0:
        raise ValueError("scalar_flux_column must be zero-based and non-negative")
    if list_offset < 0:
        raise ValueError("list_offset must be non-negative")
    if map_path is not None and scalar_flux_ids is not None:
        raise ValueError("use either map_h5 or scalar_flux_ids, not both")
    if map_path is None and scalar_flux_ids is None:
        raise ValueError("missing scalar flux map; use map_h5 or scalar_flux_ids")

    mixture_names, energy_bounds = _read_mgxs_metadata(input_path)
    energy_groups = int(energy_bounds.size - 1)
    flux_vectors = _read_flux_vectors(
        flux_path,
        energy_groups=energy_groups,
        list_offset=list_offset,
    )
    if map_path is not None:
        ids, mesh_payload = _load_ids_from_map_h5(
            map_path,
            mixture_names=mixture_names,
            scalar_flux_column=scalar_flux_column,
        )
    else:
        ids = _normalize_scalar_flux_ids(scalar_flux_ids or {}, mixture_names=mixture_names)
        mesh_payload = None

    values = _values_from_ids(flux_vectors, ids)
    if mesh_payload is not None:
        mesh_ids = np.asarray(mesh_payload["scalar_flux_ids"], dtype=int)
        mesh_payload = dict(mesh_payload)
        mesh_payload["volume_flux"] = _values_from_ids(
            flux_vectors,
            mesh_ids.reshape(-1),
        ).reshape(mesh_ids.shape + (energy_groups,))
    _write_output(
        output_path,
        input_h5=input_path,
        flux_dump=flux_path,
        map_h5=map_path,
        energy_bounds=energy_bounds,
        mixture_names=mixture_names,
        scalar_flux_ids=ids,
        volume_flux=values,
        mesh_payload=mesh_payload,
        source_label=source_label,
    )
    report = DonjonVolumeFluxReport(
        input_h5=input_path,
        flux_dump=flux_path,
        output_h5=output_path,
        map_h5=map_path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        flux_vector_count=int(flux_vectors.shape[0]),
        flux_unknown_count=int(flux_vectors.shape[1]),
        scalar_flux_ids=tuple(int(value) for value in ids),
        minimum=float(np.min(values)),
        maximum=float(np.max(values)),
        source_label=source_label,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(Path(summary_json), report)
    return report


def print_report(report: DonjonVolumeFluxReport) -> None:
    print("OpenMC-to-DONJON DONJON volume flux extraction")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  flux_dump: {report.flux_dump}")
    print(f"  output: {report.output_h5}")
    if report.map_h5 is not None:
        print(f"  map_h5: {report.map_h5}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"unknowns={report.flux_unknown_count}"
    )
    print(
        f"  scalar_flux_ids={','.join(str(value) for value in report.scalar_flux_ids)} "
        f"range={report.minimum:g}..{report.maximum:g}"
    )
    print()
    print("DONJON volume flux extraction decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: DonjonVolumeFluxReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "input": str(report.input_h5),
        "flux_dump": str(report.flux_dump),
        "output_h5": str(report.output_h5),
        "map_h5": None if report.map_h5 is None else str(report.map_h5),
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "energy_groups": report.energy_groups,
        "flux_vector_count": report.flux_vector_count,
        "flux_unknown_count": report.flux_unknown_count,
        "scalar_flux_ids": list(report.scalar_flux_ids),
        "minimum": report.minimum,
        "maximum": report.maximum,
        "source_label": report.source_label,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_mgxs_metadata(path: Path) -> tuple[tuple[str, ...], np.ndarray]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError("input HDF5 is missing /mixtures")
        if "energy_bounds" not in h5:
            raise ValueError("input HDF5 is missing /energy_bounds")
        mixture_names = tuple(str(name) for name in h5["mixtures"].keys())
        energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
    if not mixture_names:
        raise ValueError("input HDF5 has no mixtures")
    if energy_bounds.ndim != 1 or energy_bounds.size < 2:
        raise ValueError("energy_bounds must be a one-dimensional group-boundary vector")
    return mixture_names, energy_bounds


def _read_flux_vectors(path: Path, *, energy_groups: int, list_offset: int) -> np.ndarray:
    vectors = [
        np.asarray(block.data, dtype=float)
        for block in lcm.read_lcm_ascii(path)
        if block.name is None
        and block.data is not None
        and block.type_code == 2
        and block.trailing
    ]
    start = int(list_offset)
    stop = start + int(energy_groups)
    if len(vectors) < stop:
        raise ValueError(
            f"{path}: found {len(vectors)} unnamed real list vector(s), "
            f"need {stop} for list_offset={list_offset} and {energy_groups} group(s)"
        )
    selected = vectors[start:stop]
    lengths = {vector.size for vector in selected}
    if len(lengths) != 1:
        raise ValueError(f"{path}: inconsistent flux vector lengths {sorted(lengths)}")
    return np.stack(selected)


def _load_ids_from_map_h5(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    scalar_flux_column: int,
) -> tuple[np.ndarray, dict[str, np.ndarray] | None]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "scalar_flux_ids" in h5:
            dataset = h5["scalar_flux_ids"]
            values = np.asarray(dataset[:], dtype=int)
            declared = _names_from_hdf5(
                dataset,
                h5,
                ("mixture_names", "mixtures", "domain_names"),
            )
            return _normalize_id_vector(values, declared, mixture_names), None
        if "kn" not in h5:
            raise ValueError(f"{path}: expected /scalar_flux_ids or /kn")
        if "mixture_names" not in h5:
            raise ValueError(f"{path}: /kn maps require /mixture_names")
        kn = np.asarray(h5["kn"][:], dtype=int)
        names = _decode_name_array(h5["mixture_names"][:])

    if kn.ndim == 1:
        if scalar_flux_column != 0:
            raise ValueError("scalar_flux_column must be 0 when /kn is one-dimensional")
        flat_ids = kn.reshape(-1)
    elif kn.ndim == 2:
        if scalar_flux_column >= kn.shape[1]:
            raise ValueError(
                f"scalar_flux_column {scalar_flux_column} outside /kn width {kn.shape[1]}"
            )
        flat_ids = kn[:, scalar_flux_column]
    else:
        raise ValueError(f"{path}: /kn must be one- or two-dimensional")

    if names.size != flat_ids.size:
        raise ValueError(
            f"{path}: /mixture_names contains {names.size} entries but /kn maps "
            f"{flat_ids.size} element(s)"
        )
    ids = _ids_from_mesh(flat_ids, names.reshape(-1), mixture_names=mixture_names)
    mesh_shape = names.shape
    mesh_payload = {
        "mixture_names": names,
        "scalar_flux_ids": flat_ids.reshape(mesh_shape),
    }
    return ids, mesh_payload


def _normalize_scalar_flux_ids(
    ids_by_name: dict[str, int],
    *,
    mixture_names: tuple[str, ...],
) -> np.ndarray:
    missing = [name for name in mixture_names if name not in ids_by_name]
    extra = sorted(set(ids_by_name) - set(mixture_names))
    if missing:
        raise ValueError(f"scalar flux map is missing mixture(s): {', '.join(missing)}")
    if extra:
        raise ValueError(f"scalar flux map contains unknown mixture(s): {', '.join(extra)}")
    ids = np.asarray([ids_by_name[name] for name in mixture_names], dtype=int)
    _validate_ids(ids)
    return ids


def _normalize_id_vector(
    values: np.ndarray,
    declared_mixtures: Any,
    mixture_names: tuple[str, ...],
) -> np.ndarray:
    values = np.asarray(values, dtype=int).reshape(-1)
    if values.size != len(mixture_names):
        raise ValueError(
            f"scalar_flux_ids must have {len(mixture_names)} value(s), got {values.size}"
        )
    if declared_mixtures is not None:
        declared = tuple(_flatten_names(declared_mixtures))
        if set(declared) != set(mixture_names):
            raise ValueError(
                f"scalar_flux_ids mixture names {declared!r} do not match {mixture_names!r}"
            )
        order = [declared.index(name) for name in mixture_names]
        values = values[order]
    _validate_ids(values)
    return values


def _ids_from_mesh(
    flat_ids: np.ndarray,
    flat_names: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
) -> np.ndarray:
    out = np.empty(len(mixture_names), dtype=int)
    for index, mixture in enumerate(mixture_names):
        matches = np.flatnonzero(flat_names == mixture)
        if matches.size == 0:
            raise ValueError(f"flux map is missing mixture {mixture!r}")
        ids = np.unique(flat_ids[matches])
        ids = ids[ids > 0]
        if ids.size != 1:
            raise ValueError(
                f"flux map mixture {mixture!r} must resolve to one positive scalar flux id"
            )
        out[index] = int(ids[0])
    _validate_ids(out)
    return out


def _values_from_ids(flux_vectors: np.ndarray, scalar_flux_ids: np.ndarray) -> np.ndarray:
    _validate_ids(scalar_flux_ids)
    max_id = int(np.max(scalar_flux_ids))
    if max_id > flux_vectors.shape[1]:
        raise ValueError(
            f"scalar flux id {max_id} exceeds DONJON vector length {flux_vectors.shape[1]}"
        )
    values = flux_vectors[:, scalar_flux_ids.astype(int) - 1].T
    if not np.all(np.isfinite(values)):
        raise ValueError("extracted flux values must be finite")
    if np.any(values <= 0.0):
        raise ValueError("extracted flux values must be positive")
    return values


def _validate_ids(values: np.ndarray) -> None:
    if values.size == 0:
        raise ValueError("scalar flux map is empty")
    if np.any(values <= 0):
        raise ValueError("scalar flux ids must be positive one-based DONJON unknown ids")


def _write_output(
    path: Path,
    *,
    input_h5: Path,
    flux_dump: Path,
    map_h5: Path | None,
    energy_bounds: np.ndarray,
    mixture_names: tuple[str, ...],
    scalar_flux_ids: np.ndarray,
    volume_flux: np.ndarray,
    mesh_payload: dict[str, np.ndarray] | None,
    source_label: str,
) -> None:
    import h5py

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["source"] = source_label
        h5.attrs["input_h5"] = str(input_h5)
        h5.attrs["flux_dump"] = str(flux_dump)
        if map_h5 is not None:
            h5.attrs["map_h5"] = str(map_h5)
        h5.create_dataset("energy_bounds", data=np.asarray(energy_bounds, dtype=float))
        h5.create_dataset("mixture_names", data=np.asarray(mixture_names, dtype="S"))
        ids = h5.create_dataset("scalar_flux_ids", data=np.asarray(scalar_flux_ids, dtype=int))
        ids.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        volume = h5.create_dataset("volume_flux", data=np.asarray(volume_flux, dtype=float))
        volume.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        donjon = h5.create_dataset("donjon_volume_flux", data=np.asarray(volume_flux, dtype=float))
        donjon.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        if mesh_payload is not None:
            h5.create_dataset(
                "mesh_mixture_names",
                data=np.asarray(mesh_payload["mixture_names"], dtype="S"),
            )
            h5.create_dataset(
                "mesh_scalar_flux_ids",
                data=np.asarray(mesh_payload["scalar_flux_ids"], dtype=int),
            )
            mesh_volume = h5.create_dataset(
                "mesh_volume_flux",
                data=np.asarray(mesh_payload["volume_flux"], dtype=float),
            )
            mesh_volume.attrs["mixture_names"] = np.asarray(
                mesh_payload["mixture_names"],
                dtype="S",
            )
            mesh_donjon = h5.create_dataset(
                "mesh_donjon_volume_flux",
                data=np.asarray(mesh_payload["volume_flux"], dtype=float),
            )
            mesh_donjon.attrs["mixture_names"] = np.asarray(
                mesh_payload["mixture_names"],
                dtype="S",
            )


def _names_from_hdf5(obj: Any, root: Any, candidates: tuple[str, ...]) -> Any:
    for candidate in candidates:
        if candidate in obj.attrs:
            return obj.attrs[candidate]
    for candidate in candidates:
        if candidate in root.attrs:
            return root.attrs[candidate]
    for candidate in candidates:
        if candidate in root and not hasattr(root[candidate], "keys"):
            return root[candidate][:]
    return None


def _flatten_names(raw: Any) -> tuple[str, ...]:
    arr = np.asarray(raw)
    out: list[str] = []
    for item in arr.reshape(-1):
        if isinstance(item, bytes):
            out.append(item.decode("utf-8"))
        else:
            out.append(str(item))
    return tuple(out)


def _decode_name_array(raw: Any) -> np.ndarray:
    arr = np.asarray(raw)
    out = np.empty(arr.shape, dtype=object)
    for index, item in np.ndenumerate(arr):
        if isinstance(item, bytes):
            out[index] = item.decode("utf-8")
        else:
            out[index] = str(item)
    return out

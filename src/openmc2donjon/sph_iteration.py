"""Build SPH update tables from reference and low-order fluxes."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import numpy as np

from . import __version__
from .sph_augment import load_sph_source


SCHEMA = "openmc2donjon.sph-iteration-table.v1"
PASS_DECISION = "openmc2donjon_sph_iteration_table_passed"
FLUX_DATASETS = (
    "volume_flux",
    "flux",
    "scalar_flux",
    "reference_flux",
    "low_order_flux",
    "phi",
)


@dataclass(frozen=True)
class LoadedMatrix:
    values: np.ndarray
    path: Path
    dataset_path: str | None = None


@dataclass(frozen=True)
class SphUpdateTableReport:
    input_h5: Path
    output_table: Path
    reference_flux_source: Path
    reference_flux_dataset: str | None
    low_order_flux_source: Path
    low_order_flux_dataset: str | None
    previous_sph_source: Path | None
    previous_sph_dataset: str | None
    mixture_names: tuple[str, ...]
    energy_groups: int
    damping: float
    clip_min: float | None
    clip_max: float | None
    reference_flux_minimum: float
    reference_flux_maximum: float
    low_order_flux_minimum: float
    low_order_flux_maximum: float
    raw_update_minimum: float
    raw_update_maximum: float
    previous_sph_minimum: float
    previous_sph_maximum: float
    sph_minimum: float
    sph_maximum: float
    clipped_count: int
    source_label: str


def create_sph_update_table(
    input_h5: Path,
    output_table: Path,
    *,
    reference_flux: str | Path,
    low_order_flux: str | Path,
    previous_sph: str | Path | None = None,
    damping: float = 1.0,
    clip_min: float | None = None,
    clip_max: float | None = None,
    source_label: str = "external low-order SPH iteration",
    force: bool = False,
    summary_json: Path | None = None,
) -> SphUpdateTableReport:
    """Write the next SPH factors as a CSV table.

    The update is multiplicative and damped:

    ``next_sph = previous_sph * (reference_flux / low_order_flux) ** damping``.

    If no previous SPH source is supplied, unity factors are used.
    """

    input_h5 = Path(input_h5)
    output_table = Path(output_table)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_table.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_table}")
    _validate_update_options(damping=damping, clip_min=clip_min, clip_max=clip_max)

    mixture_names, energy_groups = _read_mgxs_metadata(input_h5)
    reference = _load_matrix_source(
        reference_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=("reference_flux", "flux", "phi", "value"),
        label="reference flux",
    )
    low_order = _load_matrix_source(
        low_order_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=("low_order_flux", "flux", "phi", "value"),
        label="low-order flux",
    )
    previous = _load_previous_sph(
        previous_sph,
        input_h5=input_h5,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
    )

    _validate_flux(reference.values, "reference flux")
    _validate_flux(low_order.values, "low-order flux")
    _validate_sph(previous.values, "previous SPH")

    raw_update = reference.values / low_order.values
    updated = previous.values * np.power(raw_update, float(damping))
    clipped_count = 0
    if clip_min is not None or clip_max is not None:
        before = updated.copy()
        lower = -np.inf if clip_min is None else float(clip_min)
        upper = np.inf if clip_max is None else float(clip_max)
        updated = np.clip(updated, lower, upper)
        clipped_count = int(np.count_nonzero(before != updated))
    _validate_sph(updated, "updated SPH")

    _write_sph_table(output_table, mixture_names=mixture_names, values=updated)
    report = SphUpdateTableReport(
        input_h5=input_h5,
        output_table=output_table,
        reference_flux_source=reference.path,
        reference_flux_dataset=reference.dataset_path,
        low_order_flux_source=low_order.path,
        low_order_flux_dataset=low_order.dataset_path,
        previous_sph_source=None if previous_sph is None else previous.path,
        previous_sph_dataset=None if previous_sph is None else previous.dataset_path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        damping=float(damping),
        clip_min=None if clip_min is None else float(clip_min),
        clip_max=None if clip_max is None else float(clip_max),
        reference_flux_minimum=float(np.min(reference.values)),
        reference_flux_maximum=float(np.max(reference.values)),
        low_order_flux_minimum=float(np.min(low_order.values)),
        low_order_flux_maximum=float(np.max(low_order.values)),
        raw_update_minimum=float(np.min(raw_update)),
        raw_update_maximum=float(np.max(raw_update)),
        previous_sph_minimum=float(np.min(previous.values)),
        previous_sph_maximum=float(np.max(previous.values)),
        sph_minimum=float(np.min(updated)),
        sph_maximum=float(np.max(updated)),
        clipped_count=clipped_count,
        source_label=source_label,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: SphUpdateTableReport) -> None:
    print("OpenMC-to-DONJON SPH iteration table")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_table}")
    print(f"  reference_flux: {report.reference_flux_source}")
    if report.reference_flux_dataset is not None:
        print(f"  reference_flux_dataset: {report.reference_flux_dataset}")
    print(f"  low_order_flux: {report.low_order_flux_source}")
    if report.low_order_flux_dataset is not None:
        print(f"  low_order_flux_dataset: {report.low_order_flux_dataset}")
    if report.previous_sph_source is not None:
        print(f"  previous_sph: {report.previous_sph_source}")
        if report.previous_sph_dataset is not None:
            print(f"  previous_sph_dataset: {report.previous_sph_dataset}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"damping={report.damping:g} clipped={report.clipped_count}"
    )
    print(
        "  update range: "
        f"{report.raw_update_minimum:g}..{report.raw_update_maximum:g} "
        f"SPH range: {report.sph_minimum:g}..{report.sph_maximum:g}"
    )
    print()
    print("SPH iteration table decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: SphUpdateTableReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "input": str(report.input_h5),
        "output_table": str(report.output_table),
        "reference_flux": str(report.reference_flux_source),
        "reference_flux_dataset": report.reference_flux_dataset,
        "low_order_flux": str(report.low_order_flux_source),
        "low_order_flux_dataset": report.low_order_flux_dataset,
        "previous_sph": None
        if report.previous_sph_source is None
        else str(report.previous_sph_source),
        "previous_sph_dataset": report.previous_sph_dataset,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "energy_groups": report.energy_groups,
        "damping": report.damping,
        "clip_min": report.clip_min,
        "clip_max": report.clip_max,
        "reference_flux_minimum": report.reference_flux_minimum,
        "reference_flux_maximum": report.reference_flux_maximum,
        "low_order_flux_minimum": report.low_order_flux_minimum,
        "low_order_flux_maximum": report.low_order_flux_maximum,
        "raw_update_minimum": report.raw_update_minimum,
        "raw_update_maximum": report.raw_update_maximum,
        "previous_sph_minimum": report.previous_sph_minimum,
        "previous_sph_maximum": report.previous_sph_maximum,
        "sph_minimum": report.sph_minimum,
        "sph_maximum": report.sph_maximum,
        "clipped_count": report.clipped_count,
        "source_label": report.source_label,
        "formula": "next_sph = previous_sph * (reference_flux / low_order_flux) ** damping",
    }
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_mgxs_metadata(path: Path) -> tuple[tuple[str, ...], int]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError("input HDF5 is missing /mixtures")
        mixture_names = tuple(str(name) for name in h5["mixtures"].keys())
        if "energy_groups" in h5.attrs:
            energy_groups = int(h5.attrs["energy_groups"])
        elif "energy_bounds" in h5:
            energy_groups = int(np.asarray(h5["energy_bounds"][:]).size - 1)
        else:
            raise ValueError("input HDF5 is missing energy_groups metadata")
    if not mixture_names:
        raise ValueError("input HDF5 has no mixtures")
    if energy_groups <= 0:
        raise ValueError("input HDF5 energy group count must be positive")
    return mixture_names, energy_groups


def _load_matrix_source(
    source: str | Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    value_columns: tuple[str, ...],
    label: str,
) -> LoadedMatrix:
    path, dataset = _split_dataset_reference(source)
    if not path.exists():
        raise FileNotFoundError(f"{label} source does not exist: {path}")
    if _looks_like_hdf5(path) or dataset is not None:
        values, dataset_path = _load_hdf5_matrix(
            path,
            dataset=dataset,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            label=label,
        )
        return LoadedMatrix(values=values, path=path, dataset_path=dataset_path)
    values = _load_csv_matrix(
        path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=value_columns,
        label=label,
    )
    return LoadedMatrix(values=values, path=path, dataset_path=None)


def _load_previous_sph(
    source: str | Path | None,
    *,
    input_h5: Path,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> LoadedMatrix:
    if source is None:
        return LoadedMatrix(
            values=np.ones((len(mixture_names), energy_groups), dtype=float),
            path=Path("unity"),
            dataset_path=None,
        )
    path, dataset = _split_dataset_reference(source)
    if not path.exists():
        raise FileNotFoundError(f"previous SPH source does not exist: {path}")
    if _looks_like_hdf5(path) or dataset is not None:
        if dataset is None:
            loaded = load_sph_source(
                path,
                mixture_names=mixture_names,
                energy_groups=energy_groups,
            )
            values = np.stack([loaded.sph[name] for name in mixture_names])
            return LoadedMatrix(values=values, path=path, dataset_path="sph")
        values, dataset_path = _load_hdf5_matrix(
            path,
            dataset=dataset,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            label="previous SPH",
        )
        return LoadedMatrix(values=values, path=path, dataset_path=dataset_path)
    values = _load_csv_matrix(
        path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=("sph", "nsph", "value"),
        label="previous SPH",
    )
    return LoadedMatrix(values=values, path=path, dataset_path=None)


def _load_hdf5_matrix(
    path: Path,
    *,
    dataset: str | None,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    label: str,
) -> tuple[np.ndarray, str]:
    import h5py

    with h5py.File(path, "r") as h5:
        dataset_path = dataset
        if dataset_path is None:
            for candidate in FLUX_DATASETS:
                if candidate in h5 and not hasattr(h5[candidate], "keys"):
                    dataset_path = candidate
                    break
        if dataset_path is None:
            rendered = ", ".join(f"/{name}" for name in FLUX_DATASETS)
            raise ValueError(f"{label} HDF5 must contain one of: {rendered}")
        if dataset_path not in h5:
            raise ValueError(f"{label} dataset not found: /{dataset_path}")
        obj = h5[dataset_path]
        if hasattr(obj, "keys"):
            raise ValueError(f"{label} path is a group, not a dataset: /{dataset_path}")
        values = np.asarray(obj[:], dtype=float)
        declared = _names_from_hdf5(obj, h5, ("mixture_names", "mixtures", "domain_names"))
    return _normalize_matrix(values, declared, mixture_names, energy_groups, label), dataset_path


def _load_csv_matrix(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    value_columns: tuple[str, ...],
    label: str,
) -> np.ndarray:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{label} CSV must have a header row")
        fieldnames = [str(name).strip() for name in reader.fieldnames]
        rows = [
            {str(key).strip(): value for key, value in row.items()}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    if not rows:
        raise ValueError(f"{label} CSV contains no data rows")

    mixture_column = _find_column(fieldnames, ("mixture", "mixture_name", "name"))
    if mixture_column is None:
        raise ValueError(f"{label} CSV must define a mixture, mixture_name, or name column")
    group_column = _find_column(fieldnames, ("group", "energy_group", "g"))
    value_column = _find_column(fieldnames, value_columns)
    if group_column is not None and value_column is not None:
        return _load_long_csv(
            rows,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            mixture_column=mixture_column,
            group_column=group_column,
            value_column=value_column,
            label=label,
        )

    group_columns = _group_columns(fieldnames, mixture_column)
    group_indices = [index for index, _column in group_columns]
    if len(set(group_indices)) != len(group_indices):
        raise ValueError(f"{label} wide CSV contains duplicate group columns")
    if group_indices and group_indices != list(range(energy_groups)):
        raise ValueError(
            f"{label} wide CSV must define contiguous group columns 1..{energy_groups}"
        )
    if len(group_columns) == energy_groups:
        return _load_wide_csv(
            rows,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            mixture_column=mixture_column,
            group_columns=group_columns,
            label=label,
        )
    raise ValueError(
        f"{label} CSV must be long form (mixture,group,value) or wide form "
        f"(mixture plus {energy_groups} group columns)"
    )


def _load_long_csv(
    rows: list[dict[str, str]],
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    mixture_column: str,
    group_column: str,
    value_column: str,
    label: str,
) -> np.ndarray:
    values = {name: np.full(energy_groups, np.nan, dtype=float) for name in mixture_names}
    seen: set[tuple[str, int]] = set()
    valid = set(mixture_names)
    for row_index, row in enumerate(rows, start=2):
        mixture = str(row.get(mixture_column, "")).strip()
        if mixture not in valid:
            raise ValueError(f"{label} row {row_index}: unknown mixture {mixture!r}")
        group = _parse_group_index(str(row.get(group_column, "")).strip(), energy_groups, row_index, label)
        key = (mixture, group)
        if key in seen:
            raise ValueError(f"{label} row {row_index}: duplicate {mixture} group {group + 1}")
        seen.add(key)
        values[mixture][group] = _parse_float(row.get(value_column, ""), row_index, value_column, label)
    _require_complete(values, label)
    return np.stack([values[name] for name in mixture_names])


def _load_wide_csv(
    rows: list[dict[str, str]],
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    mixture_column: str,
    group_columns: list[tuple[int, str]],
    label: str,
) -> np.ndarray:
    values: dict[str, np.ndarray] = {}
    valid = set(mixture_names)
    for row_index, row in enumerate(rows, start=2):
        mixture = str(row.get(mixture_column, "")).strip()
        if mixture not in valid:
            raise ValueError(f"{label} row {row_index}: unknown mixture {mixture!r}")
        if mixture in values:
            raise ValueError(f"{label} row {row_index}: duplicate mixture {mixture!r}")
        vector = np.empty(energy_groups, dtype=float)
        for group_index, column in group_columns:
            vector[group_index] = _parse_float(row.get(column, ""), row_index, column, label)
        values[mixture] = vector
    missing = [name for name in mixture_names if name not in values]
    if missing:
        raise ValueError(f"{label} CSV is missing mixture(s): {', '.join(missing)}")
    return np.stack([values[name] for name in mixture_names])


def _write_sph_table(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    values: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mixture", "group", "sph"))
        for mixture_index, mixture in enumerate(mixture_names):
            for group_index, value in enumerate(values[mixture_index], start=1):
                writer.writerow((mixture, group_index, f"{float(value):.12g}"))


def _normalize_matrix(
    values: np.ndarray,
    declared_mixtures: Any,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    label: str,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    expected_shape = (len(mixture_names), energy_groups)
    if values.shape == expected_shape:
        if declared_mixtures is None:
            return values
        declared = tuple(_flatten_names(declared_mixtures))
        if not declared:
            return values
        if set(declared) != set(mixture_names):
            raise ValueError(
                f"{label}: declared mixture names {declared!r} do not match "
                f"{mixture_names!r}"
            )
        order = [declared.index(name) for name in mixture_names]
        return values[order, :]

    if values.ndim >= 3 and values.shape[-1] == energy_groups:
        return _mesh_values_to_mixture_order(
            values,
            declared_mixtures,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            label=label,
        )

    raise ValueError(
        f"{label}: shape {values.shape} is not compatible with "
        f"({len(mixture_names)}, {energy_groups}) or mesh-shaped "
        f"(..., {energy_groups})"
    )


def _mesh_values_to_mixture_order(
    values: np.ndarray,
    declared_mixtures: Any,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    label: str,
) -> np.ndarray:
    if declared_mixtures is None:
        raise ValueError(
            f"{label}: mesh-shaped HDF5 datasets must declare mixture_names, "
            "mixtures, or domain_names"
        )
    declared = _decode_name_array(declared_mixtures)
    spatial_shape = values.shape[:-1]
    if declared.shape != spatial_shape:
        if declared.size != int(np.prod(spatial_shape)):
            raise ValueError(
                f"{label}: declared mixture name shape {declared.shape} does not "
                f"match mesh shape {spatial_shape}"
            )
        declared = declared.reshape(spatial_shape)

    flat_names = declared.reshape(-1)
    flat_values = values.reshape((-1, energy_groups))
    ordered = np.empty((len(mixture_names), energy_groups), dtype=float)
    for mixture_index, mixture in enumerate(mixture_names):
        matches = np.flatnonzero(flat_names == mixture)
        if matches.size == 0:
            raise ValueError(f"{label}: mesh is missing mixture {mixture!r}")
        if matches.size > 1:
            raise ValueError(
                f"{label}: mesh contains mixture {mixture!r} more than once; "
                "SPH iteration tables require one flux vector per mixture"
            )
        ordered[mixture_index, :] = flat_values[int(matches[0]), :]
    return ordered


def _validate_update_options(
    *,
    damping: float,
    clip_min: float | None,
    clip_max: float | None,
) -> None:
    if not np.isfinite(damping) or damping < 0.0 or damping > 1.0:
        raise ValueError("--damping must be finite and within 0..1")
    if clip_min is not None and (not np.isfinite(clip_min) or clip_min <= 0.0):
        raise ValueError("--clip-min must be positive and finite")
    if clip_max is not None and (not np.isfinite(clip_max) or clip_max <= 0.0):
        raise ValueError("--clip-max must be positive and finite")
    if clip_min is not None and clip_max is not None and clip_min > clip_max:
        raise ValueError("--clip-min must be less than or equal to --clip-max")


def _validate_flux(values: np.ndarray, label: str) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} values must be finite")
    if np.any(values <= 0.0):
        raise ValueError(f"{label} values must be positive")


def _validate_sph(values: np.ndarray, label: str) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} values must be finite")
    if np.any(values <= 0.0):
        raise ValueError(f"{label} values must be positive")


def _split_dataset_reference(reference: str | Path) -> tuple[Path, str | None]:
    raw = str(reference)
    if "::" not in raw:
        return Path(raw), None
    path, dataset = raw.split("::", 1)
    dataset = dataset.strip("/")
    if not dataset:
        raise ValueError(f"empty dataset reference in {raw!r}")
    return Path(path), dataset


def _looks_like_hdf5(path: Path) -> bool:
    return path.suffix.lower() in {".h5", ".hdf5", ".hdf"}


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


def _find_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {_normalize_column(name): name for name in fieldnames}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _group_columns(fieldnames: list[str], mixture_column: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for name in fieldnames:
        if name == mixture_column:
            continue
        match = re.fullmatch(r"(?:sph|nsph|flux|phi|group|g)?_?(\d+)", _normalize_column(name))
        if match is None:
            continue
        out.append((int(match.group(1)) - 1, name))
    out.sort(key=lambda item: item[0])
    return out


def _normalize_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _parse_group_index(raw: str, energy_groups: int, row_index: int, label: str) -> int:
    try:
        group = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label} row {row_index}: group must be an integer") from exc
    if group < 1 or group > energy_groups:
        raise ValueError(f"{label} row {row_index}: group {group} outside 1..{energy_groups}")
    return group - 1


def _parse_float(raw: Any, row_index: int, column: str, label: str) -> float:
    text = str(raw or "").strip()
    if not text:
        raise ValueError(f"{label} row {row_index}: missing value in {column}")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"{label} row {row_index}: {column} must be a floating-point value"
        ) from exc


def _require_complete(values: dict[str, np.ndarray], label: str) -> None:
    missing: list[str] = []
    for mixture, vector in values.items():
        missing_groups = np.flatnonzero(~np.isfinite(vector)) + 1
        if missing_groups.size:
            rendered = ",".join(str(int(group)) for group in missing_groups[:8])
            if missing_groups.size > 8:
                rendered += ",..."
            missing.append(f"{mixture}: groups {rendered}")
    if missing:
        raise ValueError(f"{label} CSV is incomplete: " + "; ".join(missing))

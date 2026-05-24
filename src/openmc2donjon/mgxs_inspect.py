"""Lightweight inspection for converter-facing MGXS HDF5 files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py

from .mgxs_input_contract import OPTIONAL_VECTOR_DATASETS, REQUIRED_DATASETS, SPH_DATASETS


SCHEMA = "openmc2donjon.mgxs-inspect.v1"
H_FACTOR_DATASETS = (
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
)


@dataclass(frozen=True)
class MixtureInspection:
    name: str
    state_points: int
    fissionable: bool | None
    volume: float | None
    required_present: int
    required_total: int
    optional_datasets: tuple[str, ...]
    adf_faces: tuple[str, ...]
    sph: bool
    scatter_shape: tuple[int, ...] | None
    scatter_axes: str | None
    std_dev_datasets: int
    std_dev_expected_datasets: int
    attr_keys: tuple[str, ...]


@dataclass
class Hdf5Inspection:
    path: str
    ok: bool = True
    energy_groups: int | None = None
    legendre_order: int | None = None
    energy_bounds_shape: tuple[int, ...] | None = None
    energy_min: float | None = None
    energy_max: float | None = None
    root_attr_keys: tuple[str, ...] = ()
    burnup_axis: str | None = None
    burnup_axis_values: int | None = None
    mixture_count: int = 0
    calculation_count: int = 0
    state_points: int | None = None
    fissionable_mixtures: int = 0
    required_complete: int = 0
    transport_total: int = 0
    h_factor: int = 0
    inverse_velocity: int = 0
    flux_weight: int = 0
    adf_mixtures: int = 0
    adf_faces: tuple[str, ...] = ()
    sph_calculations: int = 0
    std_dev_datasets: int = 0
    std_dev_expected_datasets: int = 0
    scatter_axes: tuple[str, ...] = ()
    scatter_shapes: tuple[tuple[int, ...], ...] = ()
    mixtures: list[MixtureInspection] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.issues.append(message)


def inspect_files(
    paths: list[Path],
    *,
    limit: int = 20,
    all_mixtures: bool = False,
    summary_json: Path | None = None,
) -> list[Hdf5Inspection]:
    """Inspect HDF5 files, print a human report, and optionally write JSON."""

    reports = [inspect_file(path) for path in paths]
    print("OpenMC-to-DONJON MGXS inspect")
    print(f"  schema: {SCHEMA}")
    print()
    for report in reports:
        print_report(report, limit=limit, all_mixtures=all_mixtures)
    if summary_json is not None:
        write_summary(summary_json, reports)
    return reports


def inspect_file(path: Path) -> Hdf5Inspection:
    report = Hdf5Inspection(path=str(path))
    if not path.is_file():
        report.fail(f"input file does not exist: {path}")
        return report
    try:
        with h5py.File(path, "r") as h5:
            _inspect_open_h5(h5, report)
    except OSError as exc:
        report.fail(f"cannot open HDF5 file: {exc}")
    return report


def _inspect_open_h5(h5: h5py.File, report: Hdf5Inspection) -> None:
    report.root_attr_keys = tuple(sorted(str(key) for key in h5.attrs))
    report.energy_groups = _int_attr(h5.attrs, "energy_groups")
    report.legendre_order = _int_attr(h5.attrs, "legendre_order")
    if "energy_bounds" in h5 and isinstance(h5["energy_bounds"], h5py.Dataset):
        energy = h5["energy_bounds"]
        report.energy_bounds_shape = tuple(int(value) for value in energy.shape)
        if energy.size:
            values = energy[:]
            report.energy_min = float(values.reshape(-1)[0])
            report.energy_max = float(values.reshape(-1)[-1])
    else:
        report.fail("/energy_bounds dataset is missing")

    burnup_axis = _burnup_axis(h5)
    if burnup_axis is not None:
        report.burnup_axis, report.burnup_axis_values = burnup_axis

    if "mixtures" not in h5 or not isinstance(h5["mixtures"], h5py.Group):
        report.fail("/mixtures group is missing")
        return

    mixtures = h5["mixtures"]
    report.mixture_count = len(mixtures)
    state_counts: list[int] = []
    adf_layouts: list[tuple[str, ...]] = []
    scatter_axes_seen: set[str] = set()
    scatter_shapes_seen: set[tuple[int, ...]] = set()

    for name, group in mixtures.items():
        if not isinstance(group, h5py.Group):
            report.fail(f"/mixtures/{name} is not a group")
            continue
        info, calculations = _inspect_mixture(str(name), group, h5)
        report.mixtures.append(info)
        state_counts.append(info.state_points)
        report.calculation_count += calculations
        if info.fissionable:
            report.fissionable_mixtures += 1
        if info.required_present == info.required_total:
            report.required_complete += calculations
        if "transport_total" in info.optional_datasets:
            report.transport_total += calculations
        if any(name in info.optional_datasets for name in H_FACTOR_DATASETS):
            report.h_factor += calculations
        if "inverse_velocity" in info.optional_datasets:
            report.inverse_velocity += calculations
        if "flux_weight" in info.optional_datasets:
            report.flux_weight += calculations
        if info.adf_faces:
            report.adf_mixtures += calculations
            adf_layouts.append(info.adf_faces)
        if info.sph:
            report.sph_calculations += calculations
        report.std_dev_datasets += info.std_dev_datasets
        report.std_dev_expected_datasets += info.std_dev_expected_datasets
        if info.scatter_axes:
            scatter_axes_seen.add(info.scatter_axes)
        if info.scatter_shape:
            scatter_shapes_seen.add(info.scatter_shape)

    if state_counts:
        report.state_points = state_counts[0] if len(set(state_counts)) == 1 else None
        if report.state_points is None:
            report.fail(f"mixtures have mixed state counts: {state_counts}")
    if adf_layouts:
        first = adf_layouts[0]
        report.adf_faces = first
        if any(layout != first for layout in adf_layouts):
            report.fail("ADF face layouts differ between mixtures")
    report.scatter_axes = tuple(sorted(scatter_axes_seen))
    report.scatter_shapes = tuple(sorted(scatter_shapes_seen))


def _inspect_mixture(
    name: str,
    group: h5py.Group,
    h5: h5py.File,
) -> tuple[MixtureInspection, int]:
    if "states" in group and isinstance(group["states"], h5py.Group):
        states = group["states"]
        state_names = _sorted_state_names(states)
        first_group = states[state_names[0]] if state_names else group
        calculation_groups = tuple(
            states[state_name]
            for state_name in state_names
            if isinstance(states[state_name], h5py.Group)
        )
        calculations = len(state_names)
    else:
        first_group = group
        calculation_groups = (group,)
        calculations = 1

    parent_attrs = group.attrs if first_group is not group else None
    fissionable = _bool_attr(first_group.attrs, parent_attrs, "fissionable")
    volume = _float_attr(first_group.attrs, parent_attrs, "volume")
    optional = tuple(name for name in OPTIONAL_VECTOR_DATASETS if name in first_group)
    adf_faces = _adf_faces(first_group)
    sph = any(name in first_group for name in SPH_DATASETS)
    scatter = first_group.get("scatter_matrix")
    scatter_shape = (
        tuple(int(value) for value in scatter.shape)
        if isinstance(scatter, h5py.Dataset)
        else None
    )
    scatter_axes = _scatter_axes(first_group, group, h5)
    present_required = sum(1 for field in REQUIRED_DATASETS if field in first_group)
    std_dev_datasets = 0
    std_dev_expected_datasets = 0
    for calculation_group in calculation_groups:
        present, expected = _std_dev_coverage_counts(calculation_group)
        std_dev_datasets += present
        std_dev_expected_datasets += expected
    attrs = set(str(key) for key in group.attrs)
    attrs.update(str(key) for key in first_group.attrs)

    return (
        MixtureInspection(
            name=name,
            state_points=calculations,
            fissionable=fissionable,
            volume=volume,
            required_present=present_required,
            required_total=len(REQUIRED_DATASETS),
            optional_datasets=optional,
            adf_faces=adf_faces,
            sph=sph,
            scatter_shape=scatter_shape,
            scatter_axes=scatter_axes,
            std_dev_datasets=std_dev_datasets,
            std_dev_expected_datasets=std_dev_expected_datasets,
            attr_keys=tuple(sorted(attrs)),
        ),
        calculations,
    )


def print_report(
    report: Hdf5Inspection,
    *,
    limit: int,
    all_mixtures: bool,
) -> None:
    status = "OK" if report.ok else "WARN"
    print(f"== {Path(report.path).name} ==")
    print(f"  {status}  path: {report.path}")
    print(
        "        "
        f"energy_groups={report.energy_groups} legendre_order={report.legendre_order} "
        f"energy_bounds={_render_shape(report.energy_bounds_shape)}"
    )
    if report.energy_min is not None and report.energy_max is not None:
        print(f"        energy_range_eV={report.energy_min:g}..{report.energy_max:g}")
    print(f"        root_attrs={_render_list(report.root_attr_keys)}")
    print(
        "        "
        f"mixtures={report.mixture_count} calculations={report.calculation_count} "
        f"state_points={_render_state_points(report.state_points)} "
        f"fissionable={report.fissionable_mixtures}"
    )
    if report.burnup_axis:
        print(f"        burnup_axis={report.burnup_axis} values={report.burnup_axis_values}")
    else:
        print("        burnup_axis=none")
    calculation_count = report.calculation_count or report.mixture_count
    print(
        "        coverage="
        f"required={report.required_complete}/{calculation_count} "
        f"transport_total={report.transport_total}/{calculation_count} "
        f"h_factor={report.h_factor}/{calculation_count} "
        f"inverse_velocity={report.inverse_velocity}/{calculation_count} "
        f"flux_weight={report.flux_weight}/{calculation_count} "
        f"sph={report.sph_calculations}/{calculation_count} "
        f"std_dev={report.std_dev_datasets}/{report.std_dev_expected_datasets}"
    )
    print(
        "        scatter="
        f"axes={_render_list(report.scatter_axes)} shapes={_render_shapes(report.scatter_shapes)}"
    )
    if report.adf_mixtures:
        print(
            "        adf="
            f"{report.adf_mixtures}/{calculation_count} faces={_render_list(report.adf_faces)}"
        )
    else:
        print("        adf=none")
    for issue in report.issues[:8]:
        print(f"        WARN: {issue}")
    if len(report.issues) > 8:
        print(f"        ... {len(report.issues) - 8} more issue(s)")
    print("        mixtures:")
    visible = report.mixtures if all_mixtures else report.mixtures[: max(limit, 0)]
    for index, mixture in enumerate(visible, start=1):
        print(
            f"          {index:4d} {mixture.name} "
            f"states={mixture.state_points} "
            f"fissionable={_render_bool(mixture.fissionable)} "
            f"volume={_render_optional(mixture.volume)} "
            f"required={mixture.required_present}/{mixture.required_total} "
            f"optional={_render_list(mixture.optional_datasets)} "
            f"adf={_render_list(mixture.adf_faces)} "
            f"sph={_render_bool(mixture.sph)}"
        )
    remaining = len(report.mixtures) - len(visible)
    if remaining > 0:
        print(f"          ... {remaining} more mixture(s)")
    print()


def write_summary(path: Path, reports: list[Hdf5Inspection]) -> None:
    payload = {
        "schema": SCHEMA,
        "inputs": [_report_payload(report) for report in reports],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _report_payload(report: Hdf5Inspection) -> dict[str, Any]:
    return {
        "path": report.path,
        "ok": report.ok,
        "energy_groups": report.energy_groups,
        "legendre_order": report.legendre_order,
        "energy_bounds_shape": report.energy_bounds_shape,
        "energy_min": report.energy_min,
        "energy_max": report.energy_max,
        "root_attr_keys": list(report.root_attr_keys),
        "burnup_axis": report.burnup_axis,
        "burnup_axis_values": report.burnup_axis_values,
        "mixture_count": report.mixture_count,
        "calculation_count": report.calculation_count,
        "state_points": report.state_points,
        "fissionable_mixtures": report.fissionable_mixtures,
        "required_complete": report.required_complete,
        "transport_total": report.transport_total,
        "h_factor": report.h_factor,
        "inverse_velocity": report.inverse_velocity,
        "flux_weight": report.flux_weight,
        "adf_mixtures": report.adf_mixtures,
        "adf_faces": list(report.adf_faces),
        "sph_calculations": report.sph_calculations,
        "std_dev_datasets": report.std_dev_datasets,
        "std_dev_expected_datasets": report.std_dev_expected_datasets,
        "scatter_axes": list(report.scatter_axes),
        "scatter_shapes": [list(shape) for shape in report.scatter_shapes],
        "issues": list(report.issues),
        "mixtures": [
            {
                "name": mixture.name,
                "state_points": mixture.state_points,
                "fissionable": mixture.fissionable,
                "volume": mixture.volume,
                "required_present": mixture.required_present,
                "required_total": mixture.required_total,
                "optional_datasets": list(mixture.optional_datasets),
                "adf_faces": list(mixture.adf_faces),
                "sph": mixture.sph,
                "scatter_shape": (
                    None if mixture.scatter_shape is None else list(mixture.scatter_shape)
                ),
                "scatter_axes": mixture.scatter_axes,
                "std_dev_datasets": mixture.std_dev_datasets,
                "std_dev_expected_datasets": mixture.std_dev_expected_datasets,
                "attr_keys": list(mixture.attr_keys),
            }
            for mixture in report.mixtures
        ],
    }


def _std_dev_coverage_counts(group: h5py.Group) -> tuple[int, int]:
    mean_datasets = tuple(
        name
        for name in REQUIRED_DATASETS + OPTIONAL_VECTOR_DATASETS
        if name in group and isinstance(group[name], h5py.Dataset)
    )
    present = sum(
        1
        for name in mean_datasets
        if f"{name}_std_dev" in group and isinstance(group[f"{name}_std_dev"], h5py.Dataset)
    )
    return present, len(mean_datasets)


def _burnup_axis(h5: h5py.File) -> tuple[str, int] | None:
    if "state_points" in h5 and isinstance(h5["state_points"], h5py.Group):
        for name in h5["state_points"]:
            if str(name).lower() in {"burn", "burnup"} and isinstance(
                h5["state_points"][name], h5py.Dataset
            ):
                return f"/state_points/{name}", int(h5["state_points"][name].size)
    for name in ("burnup_values", "burnup"):
        if name in h5 and isinstance(h5[name], h5py.Dataset):
            return f"/{name}", int(h5[name].size)
        if name in h5.attrs:
            value = h5.attrs[name]
            try:
                return f"/attrs/{name}", len(value)
            except TypeError:
                return f"/attrs/{name}", 1
    return None


def _adf_faces(group: h5py.Group) -> tuple[str, ...]:
    for name in ("adf", "ADF", "discontinuity_factors"):
        if name not in group:
            continue
        obj = group[name]
        if isinstance(obj, h5py.Group):
            return tuple(str(face_name) for face_name in obj)
        if isinstance(obj, h5py.Dataset):
            values_shape = obj.shape
            names = _attr_names(obj)
            if names:
                return tuple(names)
            if len(values_shape) == 1:
                return ("FD_B",)
            if len(values_shape) == 2:
                return tuple(f"FD_{index + 1:05d}" for index in range(values_shape[0]))
    return ()


def _scatter_axes(group: h5py.Group, mixture_group: h5py.Group, h5: h5py.File) -> str | None:
    for attrs in (group.attrs, mixture_group.attrs, h5.attrs):
        for key in ("scatter_axes", "axes"):
            if key in attrs:
                return _attr_text(attrs[key])
    return None


def _attr_names(dataset: h5py.Dataset) -> list[str]:
    for key in ("names", "face_names", "adf_names"):
        if key not in dataset.attrs:
            continue
        raw = dataset.attrs[key]
        if isinstance(raw, (bytes, str)):
            return [_attr_text(raw)]
        return [_attr_text(value) for value in raw]
    return []


def _bool_attr(attrs: h5py.AttributeManager, parent_attrs, name: str) -> bool | None:
    value = _attr_with_parent(attrs, parent_attrs, name)
    if value is None:
        return None
    return bool(value)


def _float_attr(attrs: h5py.AttributeManager, parent_attrs, name: str) -> float | None:
    value = _attr_with_parent(attrs, parent_attrs, name)
    if value is None:
        return None
    return float(value)


def _int_attr(attrs: h5py.AttributeManager, name: str) -> int | None:
    if name not in attrs:
        return None
    return int(attrs[name])


def _attr_with_parent(attrs: h5py.AttributeManager, parent_attrs, name: str) -> Any | None:
    if name in attrs:
        return attrs[name]
    if parent_attrs is not None and name in parent_attrs:
        return parent_attrs[name]
    return None


def _attr_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "decode"):
        return value.decode("utf-8")
    return str(value)


def _sorted_state_names(states: h5py.Group) -> list[str]:
    def key(name: str) -> tuple[int, int | str]:
        try:
            return (0, int(name))
        except ValueError:
            return (1, name)

    return sorted((str(name) for name in states), key=key)


def _render_shape(shape: tuple[int, ...] | None) -> str:
    if shape is None:
        return "missing"
    return "(" + ",".join(str(item) for item in shape) + ")"


def _render_shapes(shapes: tuple[tuple[int, ...], ...]) -> str:
    if not shapes:
        return "none"
    return ", ".join(_render_shape(shape) for shape in shapes)


def _render_list(values: tuple[str, ...]) -> str:
    if not values:
        return "none"
    return ",".join(values)


def _render_optional(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _render_state_points(value: int | None) -> str:
    if value is None:
        return "mixed"
    return str(value)


def _render_bool(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"

#!/usr/bin/env python3
"""Validate converter-facing OpenMC MGXS/ADF HDF5 input files."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py
import numpy as np


SCHEMA = "openmc2donjon.mgxs-input-contract.v1"
PASS_DECISION = "mgxs_input_contract_passed"
FAIL_DECISION = "mgxs_input_contract_failed"
VALID_MULTICOMPO_EXTENSIONS = (".mco", ".mcompo.txt")
VALID_MACROLIB_EXTENSIONS = (".macrolib.txt",)
REQUIRED_DATASETS = ("total", "absorption", "fission", "nu_fission", "chi", "scatter_matrix")
OPTIONAL_VECTOR_DATASETS = (
    "transport_total",
    "inverse_velocity",
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
)


@dataclass
class InputReport:
    path: str
    ok: bool = True
    energy_groups: int | None = None
    legendre_order: int | None = None
    mixtures: int = 0
    fissionable_mixtures: int = 0
    scatter_axes: list[str] = field(default_factory=list)
    transport_total_datasets: int = 0
    transport_total_derivable: int = 0
    adf_mixtures: int = 0
    adf_faces: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.issues.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def main() -> int:
    args = parse_args()
    expected_faces = split_csv(args.expected_adf_faces)
    reports = [
        validate_input(
            path,
            require_adf=args.require_adf,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            expected_adf_faces=expected_faces,
        )
        for path in args.input_h5
    ]

    output_issue = output_name_issue(args.output, args.format)
    ok = all(report.ok for report in reports) and output_issue is None
    decision = PASS_DECISION if ok else FAIL_DECISION

    print("OpenMC-to-DONJON MGXS input contract")
    print(f"  schema: {SCHEMA}")
    print()
    for report in reports:
        print_report(report)
    if args.output:
        status = "PASS" if output_issue is None else "FAIL"
        print(f"  {status}  output name: {args.output}")
        if output_issue:
            print(f"        {output_issue}")
        print()

    print("MGXS input contract decision")
    print(f"  {decision}")

    if args.summary_json:
        write_summary(args.summary_json, reports, decision, output_issue)

    return 0 if ok or not args.check else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_h5", type=Path, nargs="+", help="MGXS HDF5 input file")
    parser.add_argument(
        "--format",
        choices=("multicompo", "macrolib", "any"),
        default="any",
        help="expected converter output format for --output name checks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional intended converter output path; checks production extension",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="require ADF data for every mixture",
    )
    parser.add_argument(
        "--expected-adf-faces",
        default=None,
        help="comma-separated ADF face names expected on every ADF-bearing mixture",
    )
    parser.add_argument(
        "--require-transport-dataset",
        action="store_true",
        help="require an explicit transport_total dataset, not only P1-derived STRD",
    )
    parser.add_argument(
        "--require-volume",
        action="store_true",
        help="require a positive volume attribute on every mixture",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable summary JSON",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="return non-zero if any input violates the production contract",
    )
    return parser.parse_args()


def validate_input(
    path: Path,
    *,
    require_adf: bool,
    require_transport_dataset: bool,
    require_volume: bool,
    expected_adf_faces: list[str] | None,
) -> InputReport:
    report = InputReport(path=str(path))
    if not path.is_file():
        report.fail(f"input file does not exist: {path}")
        return report

    try:
        with h5py.File(path, "r") as h5:
            validate_open_h5(
                h5,
                report,
                require_adf=require_adf,
                require_transport_dataset=require_transport_dataset,
                require_volume=require_volume,
                expected_adf_faces=expected_adf_faces,
            )
    except OSError as exc:
        report.fail(f"cannot open HDF5 file: {exc}")
    return report


def validate_open_h5(
    h5: h5py.File,
    report: InputReport,
    *,
    require_adf: bool,
    require_transport_dataset: bool,
    require_volume: bool,
    expected_adf_faces: list[str] | None,
) -> None:
    ngroups = integer_attr(h5.attrs, "energy_groups")
    legendre_order = integer_attr(h5.attrs, "legendre_order")
    report.energy_groups = ngroups
    report.legendre_order = legendre_order

    if ngroups is None or ngroups <= 0:
        report.fail("/attrs energy_groups must be a positive integer")
        return
    if legendre_order is None or legendre_order < 0:
        report.fail("/attrs legendre_order must be a non-negative integer")
        return

    if "energy_bounds" not in h5:
        report.fail("/energy_bounds dataset is missing")
        return
    energy = np.asarray(h5["energy_bounds"][:], dtype=float).reshape(-1)
    if energy.shape != (ngroups + 1,):
        report.fail(f"/energy_bounds must have shape ({ngroups + 1},), got {energy.shape}")
    elif not np.all(np.isfinite(energy)):
        report.fail("/energy_bounds contains non-finite values")
    elif np.any(energy <= 0.0):
        report.fail("/energy_bounds must be positive eV values")
    elif not np.all(np.diff(energy) > 0.0):
        report.fail("/energy_bounds must be strictly ascending")

    if "mixtures" not in h5 or not isinstance(h5["mixtures"], h5py.Group):
        report.fail("/mixtures group is missing")
        return
    mixtures = h5["mixtures"]
    report.mixtures = len(mixtures)
    if report.mixtures == 0:
        report.fail("/mixtures group contains no mixtures")
        return

    adf_names_by_mix: list[tuple[str, ...]] = []
    for name, group in mixtures.items():
        if not isinstance(group, h5py.Group):
            report.fail(f"/mixtures/{name} must be an HDF5 group")
            continue
        validate_mixture(
            h5,
            group,
            str(name),
            ngroups,
            legendre_order,
            report,
            adf_names_by_mix,
            require_transport_dataset=require_transport_dataset,
            require_volume=require_volume,
        )

    validate_adf_layout(report, adf_names_by_mix, require_adf, expected_adf_faces)


def validate_mixture(
    h5: h5py.File,
    group: h5py.Group,
    name: str,
    ngroups: int,
    legendre_order: int,
    report: InputReport,
    adf_names_by_mix: list[tuple[str, ...]],
    *,
    require_transport_dataset: bool,
    require_volume: bool,
) -> None:
    missing = [field for field in REQUIRED_DATASETS if field not in group]
    if missing:
        report.fail(f"mixture {name}: missing dataset(s): {', '.join(missing)}")
        return

    if "fissionable" not in group.attrs:
        report.fail(f"mixture {name}: fissionable attribute is missing")
    elif bool(group.attrs["fissionable"]):
        report.fissionable_mixtures += 1

    if require_volume and "volume" not in group.attrs:
        report.fail(f"mixture {name}: volume attribute is missing")
    if "volume" in group.attrs and float(group.attrs["volume"]) <= 0.0:
        report.fail(f"mixture {name}: volume attribute must be positive")

    for field in REQUIRED_DATASETS[:-1]:
        validate_vector(group[field], ngroups, report, f"mixture {name}: {field}")

    scatter = np.asarray(group["scatter_matrix"][:], dtype=float)
    moments = validate_scatter(
        scatter,
        ngroups,
        legendre_order,
        scatter_axes(group, h5),
        report,
        name,
    )
    if not np.all(np.isfinite(scatter)):
        report.fail(f"mixture {name}: scatter_matrix contains non-finite values")

    for field in OPTIONAL_VECTOR_DATASETS:
        if field in group:
            validate_vector(group[field], ngroups, report, f"mixture {name}: {field}")

    if "transport_total" in group:
        report.transport_total_datasets += 1
        values = np.asarray(group["transport_total"][:], dtype=float).reshape(-1)
        if values.shape == (ngroups,) and np.any(values <= 0.0):
            report.fail(f"mixture {name}: transport_total must be positive")
        if values.shape == (ngroups,) and np.all(values > 0.0):
            report.transport_total_derivable += 1
    elif moments and moments > 1:
        report.transport_total_derivable += 1
    elif require_transport_dataset:
        report.fail(f"mixture {name}: transport_total dataset is required")
    else:
        report.warn(
            f"mixture {name}: STRD will fall back to total because no transport_total "
            "dataset or P1 scatter is available"
        )

    adf_names = adf_names_for_group(group, ngroups, report, name)
    adf_names_by_mix.append(tuple(adf_names))
    if adf_names:
        report.adf_mixtures += 1


def validate_vector(dataset: h5py.Dataset, ngroups: int, report: InputReport, label: str) -> None:
    values = np.asarray(dataset[:], dtype=float).reshape(-1)
    if values.shape != (ngroups,):
        report.fail(f"{label} must have shape ({ngroups},), got {values.shape}")
        return
    if not np.all(np.isfinite(values)):
        report.fail(f"{label} contains non-finite values")


def validate_scatter(
    values: np.ndarray,
    ngroups: int,
    legendre_order: int,
    axes: str | None,
    report: InputReport,
    mix_name: str,
) -> int | None:
    expected_moments = legendre_order + 1
    if axes and axes not in report.scatter_axes:
        report.scatter_axes.append(axes)

    if values.ndim == 2:
        if values.shape != (ngroups, ngroups):
            report.fail(
                f"mixture {mix_name}: scatter_matrix shape {values.shape} is not "
                f"({ngroups}, {ngroups})"
            )
            return None
        if expected_moments != 1:
            report.fail(
                f"mixture {mix_name}: 2D scatter_matrix is valid only for legendre_order=0"
            )
            return None
        return 1

    if values.ndim != 3:
        report.fail(f"mixture {mix_name}: scatter_matrix must be 2D or 3D")
        return None

    normalized = normalize_axes(axes)
    if normalized in {
        "moment,from,to",
        "moment,in,out",
        "moment,gin,gout",
        "legendre,from,to",
        "legendre,gin,gout",
    }:
        shape = values.shape
        expected = (expected_moments, ngroups, ngroups)
    elif normalized in {
        "from,to,moment",
        "in,out,moment",
        "gin,gout,moment",
        "from,to,legendre",
        "gin,gout,legendre",
    }:
        shape = values.shape
        expected = (ngroups, ngroups, expected_moments)
    elif axes is not None:
        report.fail(
            f"mixture {mix_name}: unsupported scatter_axes={axes!r}; expected "
            "'moment,G_in,G_out' or 'G_in,G_out,moment'"
        )
        return None
    elif (
        values.shape == (expected_moments, ngroups, ngroups)
        and values.shape == (ngroups, ngroups, expected_moments)
    ):
        report.fail(
            f"mixture {mix_name}: ambiguous scatter_matrix shape {values.shape}; "
            "set scatter_axes='moment,G_in,G_out' or 'G_in,G_out,moment'"
        )
        return None
    elif values.shape == (expected_moments, ngroups, ngroups):
        expected = values.shape
        shape = values.shape
        report.warn(f"mixture {mix_name}: scatter axes inferred as moment,G_in,G_out")
    elif values.shape == (ngroups, ngroups, expected_moments):
        expected = values.shape
        shape = values.shape
        report.warn(f"mixture {mix_name}: scatter axes inferred as G_in,G_out,moment")
    else:
        report.fail(
            f"mixture {mix_name}: scatter_matrix shape {values.shape} does not match "
            f"({expected_moments}, {ngroups}, {ngroups}) or "
            f"({ngroups}, {ngroups}, {expected_moments})"
        )
        return None

    if shape != expected:
        report.fail(f"mixture {mix_name}: scatter_matrix shape {shape} expected {expected}")
        return None
    return expected_moments


def adf_names_for_group(
    group: h5py.Group,
    ngroups: int,
    report: InputReport,
    mix_name: str,
) -> list[str]:
    for dataset_name in ("adf", "ADF", "discontinuity_factors"):
        if dataset_name not in group:
            continue
        obj = group[dataset_name]
        if isinstance(obj, h5py.Group):
            names: list[str] = []
            for face_name in obj:
                validate_adf_name(face_name, report, mix_name)
                validate_adf_values(
                    np.asarray(obj[face_name][:], dtype=float),
                    ngroups,
                    report,
                    mix_name,
                    face_name,
                )
                names.append(str(face_name))
            return names

        values = np.asarray(obj[:], dtype=float)
        names = adf_names_from_attrs(obj, values)
        if values.ndim == 1:
            if len(names) != 1:
                report.fail(
                    f"mixture {mix_name}: {dataset_name} has 1D values but {len(names)} names"
                )
                return []
            validate_adf_name(names[0], report, mix_name)
            validate_adf_values(values, ngroups, report, mix_name, names[0])
            return names
        if values.ndim == 2:
            if values.shape[1] != ngroups:
                report.fail(
                    f"mixture {mix_name}: {dataset_name} must have shape (N, {ngroups}), "
                    f"got {values.shape}"
                )
                return []
            if len(names) != values.shape[0]:
                report.fail(
                    f"mixture {mix_name}: {dataset_name} has {values.shape[0]} rows "
                    f"but {len(names)} face names"
                )
                return []
            for index, face_name in enumerate(names):
                validate_adf_name(face_name, report, mix_name)
                validate_adf_values(values[index], ngroups, report, mix_name, face_name)
            return names
        report.fail(f"mixture {mix_name}: {dataset_name} must be 1D, 2D, or a group")
        return []
    return []


def validate_adf_values(
    values: np.ndarray,
    ngroups: int,
    report: InputReport,
    mix_name: str,
    face_name: str,
) -> None:
    flat = np.asarray(values, dtype=float).reshape(-1)
    if flat.shape != (ngroups,):
        report.fail(f"mixture {mix_name}: ADF {face_name} must have shape ({ngroups},)")
        return
    if not np.all(np.isfinite(flat)):
        report.fail(f"mixture {mix_name}: ADF {face_name} contains non-finite values")
    if np.any(flat <= 0.0):
        report.fail(f"mixture {mix_name}: ADF {face_name} must be positive")


def validate_adf_name(name: str, report: InputReport, mix_name: str) -> None:
    if not name:
        report.fail(f"mixture {mix_name}: ADF name must not be empty")
    if len(name) > 8:
        report.fail(f"mixture {mix_name}: ADF name {name!r} is longer than 8 characters")


def validate_adf_layout(
    report: InputReport,
    adf_names_by_mix: list[tuple[str, ...]],
    require_adf: bool,
    expected_faces: list[str] | None,
) -> None:
    if not adf_names_by_mix:
        return
    first = adf_names_by_mix[0]
    report.adf_faces = list(first)
    if require_adf and not first:
        report.fail("ADF data is required but first mixture has none")
    if first and any(not names for names in adf_names_by_mix):
        report.fail("ADF data must be present for either all mixtures or none")
    if not first and any(names for names in adf_names_by_mix):
        report.fail("ADF data must be present for either all mixtures or none")
    for index, names in enumerate(adf_names_by_mix, start=1):
        if names != first:
            report.fail(
                f"mixture index {index}: ADF names {names!r} do not match first {first!r}"
            )
            break
    if expected_faces is not None and list(first) != expected_faces:
        report.fail(
            f"ADF faces {list(first)!r} do not match expected {expected_faces!r}"
        )


def adf_names_from_attrs(dataset: h5py.Dataset, values: np.ndarray) -> list[str]:
    for key in ("names", "face_names", "adf_names"):
        if key not in dataset.attrs:
            continue
        raw = dataset.attrs[key]
        if isinstance(raw, (bytes, str)):
            return [attr_text(raw)]
        return [attr_text(value) for value in raw]
    if values.ndim == 1:
        return ["FD_B"]
    return [f"FD_{index + 1:05d}" for index in range(values.shape[0])]


def scatter_axes(group: h5py.Group, h5: h5py.File) -> str | None:
    for source in (group.attrs, h5.attrs):
        for key in ("scatter_axes", "axes"):
            if key in source:
                return attr_text(source[key])
    return None


def normalize_axes(value: str | None) -> str | None:
    if value is None:
        return None
    return value.lower().replace(" ", "").replace("_", "")


def integer_attr(attrs: h5py.AttributeManager, name: str) -> int | None:
    if name not in attrs:
        return None
    try:
        return int(attrs[name])
    except (TypeError, ValueError):
        return None


def attr_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.bytes_):
        return value.decode()
    return str(value)


def split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def output_name_issue(path: Path | None, output_format: str) -> str | None:
    if path is None:
        return None
    name = str(path)
    if output_format == "multicompo":
        allowed = VALID_MULTICOMPO_EXTENSIONS
    elif output_format == "macrolib":
        allowed = VALID_MACROLIB_EXTENSIONS
    else:
        allowed = VALID_MULTICOMPO_EXTENSIONS + VALID_MACROLIB_EXTENSIONS
    if any(name.endswith(extension) for extension in allowed):
        return None
    return f"output should end with one of: {', '.join(allowed)}"


def print_report(report: InputReport) -> None:
    status = "PASS" if report.ok else "FAIL"
    print(f"== {Path(report.path).name} ==")
    print(f"  {status}  path: {report.path}")
    print(f"        energy_groups={report.energy_groups} legendre_order={report.legendre_order}")
    print(
        "        mixtures="
        f"{report.mixtures} fissionable={report.fissionable_mixtures} "
        f"transport_total={report.transport_total_datasets}/{report.mixtures} "
        f"strd_ready={report.transport_total_derivable}/{report.mixtures}"
    )
    axes = ",".join(report.scatter_axes) if report.scatter_axes else "<inferred>"
    print(f"        scatter_axes={axes}")
    if report.adf_mixtures:
        print(
            "        adf="
            f"{report.adf_mixtures}/{report.mixtures} faces={','.join(report.adf_faces)}"
        )
    else:
        print("        adf=none")
    for issue in report.issues[:12]:
        print(f"        FAIL: {issue}")
    if len(report.issues) > 12:
        print(f"        ... {len(report.issues) - 12} more issue(s)")
    for warning in report.warnings[:6]:
        print(f"        WARN: {warning}")
    if len(report.warnings) > 6:
        print(f"        ... {len(report.warnings) - 6} more warning(s)")
    print()


def write_summary(
    path: Path,
    reports: list[InputReport],
    decision: str,
    output_issue: str | None,
) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": decision,
        "output_issue": output_issue,
        "inputs": [
            {
                "path": report.path,
                "ok": report.ok,
                "energy_groups": report.energy_groups,
                "legendre_order": report.legendre_order,
                "mixtures": report.mixtures,
                "fissionable_mixtures": report.fissionable_mixtures,
                "scatter_axes": report.scatter_axes,
                "transport_total_datasets": report.transport_total_datasets,
                "transport_total_derivable": report.transport_total_derivable,
                "adf_mixtures": report.adf_mixtures,
                "adf_faces": report.adf_faces,
                "issues": report.issues,
                "warnings": report.warnings,
            }
            for report in reports
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

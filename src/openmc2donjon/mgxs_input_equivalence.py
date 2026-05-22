"""ADF/SPH contract checks for converter-facing MGXS HDF5 inputs."""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

from .constants import DONJON_ADF_NAME_WIDTH
from .mgxs_input_report import InputReport


SPH_DATASETS = ("sph", "SPH", "NSPH")


def validate_vector(
    dataset: h5py.Dataset,
    ngroups: int,
    report: InputReport,
    label: str,
) -> None:
    values = np.asarray(dataset[:], dtype=float).reshape(-1)
    if values.shape != (ngroups,):
        report.fail(f"{label} must have shape ({ngroups},), got {values.shape}")
        return
    if not np.all(np.isfinite(values)):
        report.fail(f"{label} contains non-finite values")


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
                    f"mixture {mix_name}: {dataset_name} has 1D values but "
                    f"{len(names)} names"
                )
                return []
            validate_adf_name(names[0], report, mix_name)
            validate_adf_values(values, ngroups, report, mix_name, names[0])
            return names
        if values.ndim == 2:
            if values.shape[1] != ngroups:
                report.fail(
                    f"mixture {mix_name}: {dataset_name} must have shape "
                    f"(N, {ngroups}), got {values.shape}"
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
    if len(name) > DONJON_ADF_NAME_WIDTH:
        report.fail(
            f"mixture {mix_name}: ADF name {name!r} is longer than "
            f"{DONJON_ADF_NAME_WIDTH} characters"
        )


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
                f"mixture index {index}: ADF names {names!r} do not match first "
                f"{first!r}"
            )
            break
    if expected_faces is not None and list(first) != expected_faces:
        report.fail(
            f"ADF faces {list(first)!r} do not match expected {expected_faces!r}"
        )


def sph_present_for_group(
    group: h5py.Group,
    ngroups: int,
    report: InputReport,
    mix_name: str,
) -> bool:
    present = [dataset_name for dataset_name in SPH_DATASETS if dataset_name in group]
    if len(present) > 1:
        report.fail(f"mixture {mix_name}: multiple SPH datasets found: {present}")
        return bool(present)
    if not present:
        return False

    dataset_name = present[0]
    validate_vector(
        group[dataset_name],
        ngroups,
        report,
        f"mixture {mix_name}: {dataset_name}",
    )
    values = np.asarray(group[dataset_name][:], dtype=float).reshape(-1)
    if values.shape == (ngroups,) and np.any(values <= 0.0):
        report.fail(f"mixture {mix_name}: {dataset_name} must be positive")
    return True


def validate_sph_layout(
    report: InputReport,
    sph_present_by_calc: list[bool],
    require_sph: bool,
) -> None:
    if not sph_present_by_calc:
        return
    if require_sph and not all(sph_present_by_calc):
        report.fail("SPH data is required but at least one calculation has none")
    if any(sph_present_by_calc) and not all(sph_present_by_calc):
        report.fail("SPH data must be present for either all calculations or none")


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


def attr_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.bytes_):
        return value.decode()
    return str(value)

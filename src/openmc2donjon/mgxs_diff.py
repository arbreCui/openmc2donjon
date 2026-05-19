"""Compare converter-facing MGXS HDF5 handoff files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py
import numpy as np


SCHEMA = "openmc2donjon.mgxs-diff.v1"
PASS_DECISION = "mgxs_hdf5_diff_passed"
FAIL_DECISION = "mgxs_hdf5_diff_failed"


@dataclass(frozen=True)
class DiffIssue:
    path: str
    kind: str
    message: str
    max_abs: float | None = None
    max_rel: float | None = None
    location: tuple[int, ...] | None = None


@dataclass
class Hdf5DiffReport:
    reference: str
    candidate: str
    ok: bool = True
    rtol: float = 0.0
    atol: float = 0.0
    compare_attrs: bool = True
    ignored_attrs: tuple[str, ...] = ()
    compared_datasets: int = 0
    compared_attrs: int = 0
    max_abs: float = 0.0
    max_rel: float = 0.0
    issues: list[DiffIssue] = field(default_factory=list)

    @property
    def decision(self) -> str:
        return PASS_DECISION if self.ok else FAIL_DECISION

    def fail(
        self,
        path: str,
        kind: str,
        message: str,
        *,
        max_abs: float | None = None,
        max_rel: float | None = None,
        location: tuple[int, ...] | None = None,
    ) -> None:
        self.ok = False
        self.issues.append(
            DiffIssue(
                path=path,
                kind=kind,
                message=message,
                max_abs=max_abs,
                max_rel=max_rel,
                location=location,
            )
        )
        if max_abs is not None:
            self.max_abs = max(self.max_abs, max_abs)
        if max_rel is not None:
            self.max_rel = max(self.max_rel, max_rel)


def diff_hdf5_files(
    reference: Path,
    candidate: Path,
    *,
    rtol: float = 0.0,
    atol: float = 0.0,
    compare_attrs: bool = True,
    ignored_attrs: tuple[str, ...] = (),
    summary_json: Path | None = None,
    max_diffs: int = 20,
) -> Hdf5DiffReport:
    """Compare two HDF5 files, print a report, and optionally write JSON."""

    report = compare_hdf5_files(
        reference,
        candidate,
        rtol=rtol,
        atol=atol,
        compare_attrs=compare_attrs,
        ignored_attrs=ignored_attrs,
    )
    print_report(report, max_diffs=max_diffs)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def compare_hdf5_files(
    reference: Path,
    candidate: Path,
    *,
    rtol: float = 0.0,
    atol: float = 0.0,
    compare_attrs: bool = True,
    ignored_attrs: tuple[str, ...] = (),
) -> Hdf5DiffReport:
    """Return a structural and numeric diff report for two HDF5 files."""

    report = Hdf5DiffReport(
        reference=str(reference),
        candidate=str(candidate),
        rtol=rtol,
        atol=atol,
        compare_attrs=compare_attrs,
        ignored_attrs=tuple(ignored_attrs),
    )
    if not reference.is_file():
        report.fail("/", "missing_reference", f"reference file does not exist: {reference}")
        return report
    if not candidate.is_file():
        report.fail("/", "missing_candidate", f"candidate file does not exist: {candidate}")
        return report

    try:
        with h5py.File(reference, "r") as ref, h5py.File(candidate, "r") as cand:
            _compare_objects(ref, cand, "/", report)
    except OSError as exc:
        report.fail("/", "open_error", f"cannot open HDF5 file: {exc}")
    return report


def _compare_objects(
    ref: h5py.Group | h5py.Dataset,
    cand: h5py.Group | h5py.Dataset,
    path: str,
    report: Hdf5DiffReport,
) -> None:
    if type(ref) is not type(cand):
        report.fail(
            path,
            "type",
            f"object type differs: reference={type(ref).__name__} candidate={type(cand).__name__}",
        )
        return

    if report.compare_attrs:
        _compare_attrs(ref, cand, path, report)

    if isinstance(ref, h5py.Dataset) and isinstance(cand, h5py.Dataset):
        _compare_datasets(ref, cand, path, report)
        return

    if not isinstance(ref, h5py.Group) or not isinstance(cand, h5py.Group):
        return

    ref_keys = set(ref.keys())
    cand_keys = set(cand.keys())
    for name in sorted(ref_keys - cand_keys):
        report.fail(_join(path, name), "missing", "object is missing from candidate")
    for name in sorted(cand_keys - ref_keys):
        report.fail(_join(path, name), "extra", "object is extra in candidate")
    for name in sorted(ref_keys & cand_keys):
        _compare_objects(ref[name], cand[name], _join(path, name), report)


def _compare_attrs(
    ref: h5py.Group | h5py.Dataset,
    cand: h5py.Group | h5py.Dataset,
    path: str,
    report: Hdf5DiffReport,
) -> None:
    ignored = set(report.ignored_attrs)
    ref_keys = {str(key) for key in ref.attrs if str(key) not in ignored}
    cand_keys = {str(key) for key in cand.attrs if str(key) not in ignored}
    for name in sorted(ref_keys - cand_keys):
        report.fail(f"{path}@{name}", "missing_attr", "attribute is missing from candidate")
    for name in sorted(cand_keys - ref_keys):
        report.fail(f"{path}@{name}", "extra_attr", "attribute is extra in candidate")
    for name in sorted(ref_keys & cand_keys):
        report.compared_attrs += 1
        _compare_values(
            ref.attrs[name],
            cand.attrs[name],
            f"{path}@{name}",
            "attr_value",
            report,
            check_dtype=False,
        )


def _compare_datasets(
    ref: h5py.Dataset,
    cand: h5py.Dataset,
    path: str,
    report: Hdf5DiffReport,
) -> None:
    report.compared_datasets += 1
    if ref.shape != cand.shape:
        report.fail(path, "shape", f"shape differs: reference={ref.shape} candidate={cand.shape}")
        return
    _compare_values(ref[()], cand[()], path, "dataset_value", report, check_dtype=True)


def _compare_values(
    ref_value: Any,
    cand_value: Any,
    path: str,
    kind: str,
    report: Hdf5DiffReport,
    *,
    check_dtype: bool,
) -> None:
    ref_array = np.asarray(ref_value)
    cand_array = np.asarray(cand_value)

    if ref_array.shape != cand_array.shape:
        report.fail(
            path,
            "shape" if kind == "dataset_value" else "attr_shape",
            f"shape differs: reference={ref_array.shape} candidate={cand_array.shape}",
        )
        return
    if check_dtype and ref_array.dtype != cand_array.dtype:
        report.fail(
            path,
            "dtype",
            f"dtype differs: reference={ref_array.dtype} candidate={cand_array.dtype}",
        )

    if _is_numeric(ref_array) and _is_numeric(cand_array):
        _compare_numeric_values(ref_array, cand_array, path, kind, report)
        return

    if not np.array_equal(ref_array, cand_array):
        report.fail(path, kind, "values differ")


def _compare_numeric_values(
    ref_array: np.ndarray,
    cand_array: np.ndarray,
    path: str,
    kind: str,
    report: Hdf5DiffReport,
) -> None:
    if ref_array.dtype.kind == "c" or cand_array.dtype.kind == "c":
        ref_numeric = np.asarray(ref_array, dtype=complex)
        cand_numeric = np.asarray(cand_array, dtype=complex)
    else:
        ref_numeric = np.asarray(ref_array, dtype=float)
        cand_numeric = np.asarray(cand_array, dtype=float)
    diff = np.abs(cand_numeric - ref_numeric)
    if diff.size == 0:
        return
    scale = np.maximum(np.abs(ref_numeric), np.finfo(float).tiny)
    rel = diff / scale
    max_index = int(np.argmax(diff))
    location = tuple(int(index) for index in np.unravel_index(max_index, diff.shape))
    max_abs = float(diff[location])
    max_rel = float(rel[location])
    report.max_abs = max(report.max_abs, max_abs)
    report.max_rel = max(report.max_rel, max_rel)
    allowed = report.atol + report.rtol * np.abs(ref_numeric)
    if not np.all(diff <= allowed):
        report.fail(
            path,
            kind,
            "numeric values differ",
            max_abs=max_abs,
            max_rel=max_rel,
            location=location,
        )


def print_report(report: Hdf5DiffReport, *, max_diffs: int = 20) -> None:
    print("OpenMC-to-DONJON MGXS HDF5 diff")
    print(f"  schema: {SCHEMA}")
    print(f"  reference: {report.reference}")
    print(f"  candidate: {report.candidate}")
    print(f"  tolerance: atol={report.atol:g} rtol={report.rtol:g}")
    print(f"  compare_attrs: {'yes' if report.compare_attrs else 'no'}")
    if report.ignored_attrs:
        print(f"  ignored_attrs: {','.join(report.ignored_attrs)}")
    print()
    print("HDF5 diff decision")
    print(f"  {report.decision}")
    print(
        "  "
        f"compared_datasets={report.compared_datasets} "
        f"compared_attrs={report.compared_attrs} "
        f"max_abs={report.max_abs:.6e} max_rel={report.max_rel:.6e}"
    )
    if report.issues:
        print("  differences:")
        for issue in report.issues[:max_diffs]:
            print(f"    - {issue.path}: {issue.kind}: {issue.message}{_issue_suffix(issue)}")
        if len(report.issues) > max_diffs:
            print(f"    ... {len(report.issues) - max_diffs} more difference(s)")


def write_summary(path: Path, report: Hdf5DiffReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": report.decision,
        "reference": report.reference,
        "candidate": report.candidate,
        "rtol": report.rtol,
        "atol": report.atol,
        "compare_attrs": report.compare_attrs,
        "ignored_attrs": list(report.ignored_attrs),
        "compared_datasets": report.compared_datasets,
        "compared_attrs": report.compared_attrs,
        "max_abs": report.max_abs,
        "max_rel": report.max_rel,
        "issues": [
            {
                "path": issue.path,
                "kind": issue.kind,
                "message": issue.message,
                "max_abs": issue.max_abs,
                "max_rel": issue.max_rel,
                "location": None if issue.location is None else list(issue.location),
            }
            for issue in report.issues
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _issue_suffix(issue: DiffIssue) -> str:
    parts: list[str] = []
    if issue.max_abs is not None:
        parts.append(f"max_abs={issue.max_abs:.6e}")
    if issue.max_rel is not None:
        parts.append(f"max_rel={issue.max_rel:.6e}")
    if issue.location is not None:
        parts.append(f"at={issue.location}")
    if not parts:
        return ""
    return " (" + ", ".join(parts) + ")"


def _is_numeric(array: np.ndarray) -> bool:
    return array.dtype.kind in {"b", "i", "u", "f", "c"}


def _join(parent: str, name: str) -> str:
    if parent == "/":
        return f"/{name}"
    return f"{parent}/{name}"

"""Preflight heterogeneous/homogeneous face-flux handoffs for ADF workflows."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from . import __version__
from .adf_augment import parse_faces
from .adf_sidecar import (
    HOMOGENEOUS_FACE_FLUX_DATASETS,
    SURFACE_FLUX_DATASETS,
    load_face_flux_payload,
)


SCHEMA = "openmc2donjon.face-flux-contract.v1"
PASS_DECISION = "openmc2donjon_face_flux_contract_passed"
FAIL_DECISION = "openmc2donjon_face_flux_contract_failed"
CHECK_EXCEPTIONS = (OSError, ValueError, KeyError, RuntimeError)


@dataclass(frozen=True)
class FaceFluxCheckReport:
    input_h5: Path
    surface_flux: str | Path
    homogeneous_face_flux: str | Path
    ok: bool
    decision: str
    mixture_names: tuple[str, ...] = ()
    face_names: tuple[str, ...] = ()
    energy_groups: int = 0
    surface_flux_source: Path | None = None
    surface_flux_dataset: str | None = None
    homogeneous_face_flux_source: Path | None = None
    homogeneous_face_flux_dataset: str | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    invalid_count: int = 0
    invalid_filled_count: int = 0
    nonpositive_surface_count: int = 0
    nonpositive_homogeneous_count: int = 0
    invalid_fill: float | None = None
    clip_min: float | None = None
    clip_max: float | None = None
    surface_flux_minimum: float | None = None
    surface_flux_median: float | None = None
    surface_flux_maximum: float | None = None
    homogeneous_face_flux_minimum: float | None = None
    homogeneous_face_flux_median: float | None = None
    homogeneous_face_flux_maximum: float | None = None
    adf_ratio_minimum: float | None = None
    adf_ratio_median: float | None = None
    adf_ratio_maximum: float | None = None


def check_face_flux(
    input_h5: Path,
    *,
    surface_flux: str | Path,
    homogeneous_face_flux: str | Path,
    faces: tuple[str, ...] | None = None,
    invalid_fill: float | None = None,
    clip_min: float | None = None,
    clip_max: float | None = None,
    summary_json: Path | None = None,
) -> FaceFluxCheckReport:
    """Validate face-flux inputs before building a flux-ratio ADF sidecar."""

    input_h5 = Path(input_h5)
    errors: list[str] = []
    warnings: list[str] = []
    mixture_names: tuple[str, ...] = ()
    face_names: tuple[str, ...] = ()
    energy_groups = 0
    surface = homogeneous = None
    raw_ratio = safe_ratio = None
    invalid_count = invalid_filled_count = 0
    nonpositive_surface_count = nonpositive_homogeneous_count = 0

    try:
        _validate_fill_and_clip(invalid_fill, clip_min, clip_max)
        mixture_names, energy_groups = _read_mgxs_metadata(input_h5)
        expected_faces = None if faces is None else tuple(parse_faces(",".join(faces)) or ())
        if expected_faces is not None and not expected_faces:
            raise ValueError("at least one expected face must be selected")
        surface = load_face_flux_payload(
            surface_flux,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            expected_faces=expected_faces,
            candidates=SURFACE_FLUX_DATASETS,
            label="surface flux",
            allow_negative=False,
        )
        homogeneous = load_face_flux_payload(
            homogeneous_face_flux,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            expected_faces=surface.face_names,
            candidates=HOMOGENEOUS_FACE_FLUX_DATASETS,
            label="homogeneous face flux",
            allow_negative=True,
        )
        if homogeneous.face_names != surface.face_names:
            raise ValueError(
                "surface and homogeneous face flux names differ: "
                f"{surface.face_names!r} != {homogeneous.face_names!r}"
            )
        face_names = surface.face_names
        raw_ratio, invalid_count, invalid_filled_count, safe_ratio = _ratio_contract(
            surface.values,
            homogeneous.values,
            invalid_fill=invalid_fill,
            clip_min=clip_min,
            clip_max=clip_max,
        )
        nonpositive_surface_count = int(np.count_nonzero(surface.values <= 0.0))
        nonpositive_homogeneous_count = int(np.count_nonzero(homogeneous.values <= 0.0))
        if invalid_count and invalid_fill is None:
            errors.append(
                f"flux-ratio ADF has {invalid_count} invalid bin(s); pass "
                "--invalid-fill for an explicit fill policy"
            )
        elif invalid_count:
            warnings.append(
                f"filled {invalid_count} invalid flux-ratio bin(s) with {invalid_fill:g}"
            )
    except CHECK_EXCEPTIONS as exc:
        errors.append(str(exc))

    ok = not errors
    report = FaceFluxCheckReport(
        input_h5=input_h5,
        surface_flux=surface_flux,
        homogeneous_face_flux=homogeneous_face_flux,
        ok=ok,
        decision=PASS_DECISION if ok else FAIL_DECISION,
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
        surface_flux_source=None if surface is None else surface.path,
        surface_flux_dataset=None if surface is None else surface.dataset_path,
        homogeneous_face_flux_source=None if homogeneous is None else homogeneous.path,
        homogeneous_face_flux_dataset=None if homogeneous is None else homogeneous.dataset_path,
        errors=tuple(errors),
        warnings=tuple(warnings),
        invalid_count=invalid_count,
        invalid_filled_count=invalid_filled_count,
        nonpositive_surface_count=nonpositive_surface_count,
        nonpositive_homogeneous_count=nonpositive_homogeneous_count,
        invalid_fill=invalid_fill,
        clip_min=clip_min,
        clip_max=clip_max,
        **_stats_payload(surface.values if surface is not None else None, "surface_flux"),
        **_stats_payload(
            homogeneous.values if homogeneous is not None else None,
            "homogeneous_face_flux",
        ),
        **_stats_payload(safe_ratio if safe_ratio is not None else raw_ratio, "adf_ratio"),
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: FaceFluxCheckReport) -> None:
    print("OpenMC-to-DONJON face-flux contract")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  surface_flux: {report.surface_flux}")
    if report.surface_flux_dataset is not None:
        print(f"  surface_flux_dataset: {report.surface_flux_dataset}")
    print(f"  homogeneous_face_flux: {report.homogeneous_face_flux}")
    if report.homogeneous_face_flux_dataset is not None:
        print(f"  homogeneous_face_flux_dataset: {report.homogeneous_face_flux_dataset}")
    status = "PASS" if report.ok else "FAIL"
    print(
        f"  {status} mixtures={len(report.mixture_names)} "
        f"groups={report.energy_groups} faces={','.join(report.face_names) or 'none'}"
    )
    _print_range(
        "surface_flux",
        report.surface_flux_minimum,
        report.surface_flux_median,
        report.surface_flux_maximum,
    )
    _print_range(
        "homogeneous_face_flux",
        report.homogeneous_face_flux_minimum,
        report.homogeneous_face_flux_median,
        report.homogeneous_face_flux_maximum,
    )
    _print_range(
        "adf_ratio",
        report.adf_ratio_minimum,
        report.adf_ratio_median,
        report.adf_ratio_maximum,
    )
    if report.invalid_count:
        print(
            f"  invalid_bins={report.invalid_count} "
            f"filled={report.invalid_filled_count}"
        )
    if report.nonpositive_surface_count or report.nonpositive_homogeneous_count:
        print(
            "  nonpositive_bins: "
            f"surface={report.nonpositive_surface_count} "
            f"homogeneous={report.nonpositive_homogeneous_count}"
        )
    for warning in report.warnings:
        print(f"  WARN {warning}")
    for error in report.errors:
        print(f"  FAIL {error}")
    print()
    print("Face-flux contract decision")
    print(f"  {report.decision}")


def write_summary(path: Path, report: FaceFluxCheckReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": report.decision,
        "ok": report.ok,
        "input_h5": str(report.input_h5),
        "surface_flux": str(report.surface_flux_source or report.surface_flux),
        "surface_flux_dataset": report.surface_flux_dataset,
        "homogeneous_face_flux": str(
            report.homogeneous_face_flux_source or report.homogeneous_face_flux
        ),
        "homogeneous_face_flux_dataset": report.homogeneous_face_flux_dataset,
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "invalid_count": report.invalid_count,
        "invalid_filled_count": report.invalid_filled_count,
        "nonpositive_surface_count": report.nonpositive_surface_count,
        "nonpositive_homogeneous_count": report.nonpositive_homogeneous_count,
        "invalid_fill": report.invalid_fill,
        "clip_min": report.clip_min,
        "clip_max": report.clip_max,
        "surface_flux_min": report.surface_flux_minimum,
        "surface_flux_median": report.surface_flux_median,
        "surface_flux_max": report.surface_flux_maximum,
        "homogeneous_face_flux_min": report.homogeneous_face_flux_minimum,
        "homogeneous_face_flux_median": report.homogeneous_face_flux_median,
        "homogeneous_face_flux_max": report.homogeneous_face_flux_maximum,
        "adf_ratio_min": report.adf_ratio_minimum,
        "adf_ratio_median": report.adf_ratio_median,
        "adf_ratio_max": report.adf_ratio_maximum,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_mgxs_metadata(path: Path) -> tuple[tuple[str, ...], int]:
    import h5py

    if not path.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {path}")
    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5 or not hasattr(h5["mixtures"], "keys"):
            raise ValueError("input HDF5 must contain a /mixtures group")
        mixture_names = tuple(str(name) for name in h5["mixtures"])
        if not mixture_names:
            raise ValueError("input HDF5 contains no mixtures")
        if "energy_groups" in h5.attrs:
            energy_groups = int(h5.attrs["energy_groups"])
        elif "energy_bounds" in h5:
            energy_groups = int(h5["energy_bounds"].shape[0]) - 1
        else:
            raise ValueError("input HDF5 must define energy_groups or energy_bounds")
    if energy_groups <= 0:
        raise ValueError("energy group count must be positive")
    return mixture_names, energy_groups


def _ratio_contract(
    surface: np.ndarray,
    homogeneous: np.ndarray,
    *,
    invalid_fill: float | None,
    clip_min: float | None,
    clip_max: float | None,
) -> tuple[np.ndarray, int, int, np.ndarray]:
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.divide(surface, homogeneous)
    valid = (
        np.isfinite(raw)
        & np.isfinite(surface)
        & np.isfinite(homogeneous)
        & (surface > 0.0)
        & (homogeneous > 0.0)
        & (raw > 0.0)
    )
    invalid_count = int(raw.size - np.count_nonzero(valid))
    safe = np.array(raw, dtype=float, copy=True)
    invalid_filled_count = 0
    if invalid_count and invalid_fill is not None:
        invalid_filled_count = invalid_count
        safe[~valid] = float(invalid_fill)
        safe = np.nan_to_num(
            safe,
            nan=float(invalid_fill),
            posinf=float(invalid_fill),
            neginf=float(invalid_fill),
        )
    if clip_min is not None and clip_max is not None:
        safe = np.clip(safe, clip_min, clip_max)
    if invalid_count == 0 or invalid_fill is not None:
        if not np.all(np.isfinite(safe)) or np.any(safe <= 0.0):
            raise ValueError("ADF ratio values must be positive and finite after fill/clip")
    return raw, invalid_count, invalid_filled_count, safe


def _validate_fill_and_clip(
    invalid_fill: float | None,
    clip_min: float | None,
    clip_max: float | None,
) -> None:
    if invalid_fill is not None and (not np.isfinite(invalid_fill) or invalid_fill <= 0.0):
        raise ValueError("--invalid-fill must be positive and finite")
    if (clip_min is None) ^ (clip_max is None):
        raise ValueError("--clip-min and --clip-max must be supplied together")
    if clip_min is not None and clip_max is not None:
        if not np.isfinite(clip_min) or not np.isfinite(clip_max):
            raise ValueError("--clip-min and --clip-max must be finite")
        if clip_min <= 0.0:
            raise ValueError("--clip-min must be positive")
        if clip_min > clip_max:
            raise ValueError("--clip-min must be <= --clip-max")


def _stats_payload(values: np.ndarray | None, prefix: str) -> dict[str, float | None]:
    stats = _stats(values)
    return {
        f"{prefix}_minimum": stats["min"],
        f"{prefix}_median": stats["median"],
        f"{prefix}_maximum": stats["max"],
    }


def _stats(values: np.ndarray | None) -> dict[str, float | None]:
    if values is None:
        return {"min": None, "median": None, "max": None}
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {"min": None, "median": None, "max": None}
    return {
        "min": float(np.min(finite)),
        "median": float(np.median(finite)),
        "max": float(np.max(finite)),
    }


def _print_range(
    label: str,
    minimum: float | None,
    median: float | None,
    maximum: float | None,
) -> None:
    if minimum is None or median is None or maximum is None:
        return
    print(f"  {label} range: min={minimum:.6g} median={median:.6g} max={maximum:.6g}")

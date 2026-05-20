"""Create ADF sidecar HDF5 files from an MGXS handoff."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from . import __version__
from .adf_augment import parse_faces


SCHEMA = "openmc2donjon.adf-sidecar.v1"
PASS_DECISION = "openmc2donjon_adf_sidecar_passed"
DEFAULT_CARTESIAN_FACES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")


@dataclass(frozen=True)
class AdfSidecarReport:
    input_h5: Path
    output_h5: Path
    mode: str
    mixture_names: tuple[str, ...]
    face_names: tuple[str, ...]
    energy_groups: int
    value: float


def create_unity_adf_sidecar(
    input_h5: Path,
    output_h5: Path,
    *,
    faces: tuple[str, ...] | None = None,
    value: float = 1.0,
    force: bool = False,
    summary_json: Path | None = None,
) -> AdfSidecarReport:
    """Create a compact root ``/adf`` sidecar filled with one constant value.

    This is an identity discontinuity-factor payload for workflow integration
    and plumbing tests.  It is deliberately marked ``adf_real=false``.
    """

    import h5py

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("--value must be positive and finite")

    face_names = tuple(faces or DEFAULT_CARTESIAN_FACES)
    face_names = tuple(parse_faces(",".join(face_names)) or ())
    if not face_names:
        raise ValueError("at least one ADF face must be selected")

    with h5py.File(input_h5, "r") as h5:
        mixture_names = _mixture_names(h5)
        energy_groups = _energy_groups(h5)

    values = np.full(
        (len(mixture_names), len(face_names), energy_groups),
        float(value),
        dtype=float,
    )
    output_h5.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_h5, "w") as h5:
        h5.attrs["schema"] = SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["adf_kind"] = "unity"
        h5.attrs["adf_real"] = "false"
        h5.attrs["adf_source"] = "openmc2donjon make-adf-sidecar --mode unity"
        h5.attrs["adf_definition"] = (
            "identity discontinuity factors for workflow integration; "
            "replace with physics ADF/DF values for production neutronics"
        )
        h5.attrs["source_mgxs"] = str(input_h5)
        dataset = h5.create_dataset("adf", data=values)
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        dataset.attrs["face_names"] = np.asarray(face_names, dtype="S")

    report = AdfSidecarReport(
        input_h5=input_h5,
        output_h5=output_h5,
        mode="unity",
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
        value=float(value),
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: AdfSidecarReport) -> None:
    print("OpenMC-to-DONJON ADF sidecar")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_h5}")
    print(
        f"  mode={report.mode} value={report.value:g} "
        f"mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"faces={','.join(report.face_names)}"
    )
    print("  adf_real=false")
    print()
    print("ADF sidecar decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: AdfSidecarReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": PASS_DECISION,
        "input_h5": str(report.input_h5),
        "output_h5": str(report.output_h5),
        "mode": report.mode,
        "adf_real": False,
        "energy_groups": report.energy_groups,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
        "value": report.value,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mixture_names(h5) -> tuple[str, ...]:
    if "mixtures" not in h5 or not hasattr(h5["mixtures"], "keys"):
        raise ValueError("input HDF5 must contain a /mixtures group")
    names = tuple(str(name) for name in h5["mixtures"])
    if not names:
        raise ValueError("input HDF5 contains no mixtures")
    return names


def _energy_groups(h5) -> int:
    if "energy_groups" in h5.attrs:
        ngroups = int(h5.attrs["energy_groups"])
    elif "energy_bounds" in h5:
        ngroups = int(h5["energy_bounds"].shape[0]) - 1
    else:
        raise ValueError("input HDF5 must define energy_groups or energy_bounds")
    if ngroups <= 0:
        raise ValueError("energy group count must be positive")
    return ngroups

"""Build the fixed-OpenMC SPH loop input scaffold."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
from typing import Any

import numpy as np

from . import __version__
from .constants import MGXS_DONJON_GROUP_ORDER
from .donjon_sph_config import write_donjon_sph_loop_config
from .hdf5_names import read_mixture_names
from .sph_iteration import _load_matrix_source


SCHEMA = "openmc2donjon.sph-loop-scaffold.v1"
PASS_DECISION = "openmc2donjon_sph_loop_scaffold_passed"
REFERENCE_FLUX_SCHEMA = "openmc2donjon.reference-flux.v1"
FLUX_MAP_SCHEMA = "openmc2donjon.low-order-flux-map.v1"


@dataclass(frozen=True)
class SphLoopScaffoldReport:
    input_h5: Path
    output_dir: Path
    reference_flux_source: Path
    reference_flux_dataset: str | None
    reference_flux_h5: Path
    flux_map_h5: Path
    loop_config: Path
    run_script: Path
    run_command: tuple[str, ...]
    mixture_names: tuple[str, ...]
    energy_groups: int
    scalar_flux_ids: tuple[int, ...]
    sequential_scalar_flux_map: bool
    warnings: tuple[str, ...]


def create_sph_loop_scaffold(
    input_h5: str | Path,
    output_dir: str | Path,
    *,
    reference_flux: str | Path,
    solve_template: str | Path,
    scalar_flux_ids: dict[str, int] | None = None,
    sequential_scalar_flux_map: bool = False,
    reference_output: str | Path | None = None,
    flux_map_output: str | Path | None = None,
    config_output: str | Path | None = None,
    run_script_output: str | Path | None = None,
    loop_output_dir: str | Path | None = None,
    output_format: str = "macrolib",
    final_solve: bool = True,
    iterations: int = 2,
    damping: float = 0.5,
    clip_min: float | None = 0.5,
    clip_max: float | None = 3.0,
    flux_normalization: str = "auto",
    sph_change_tolerance: float | None = None,
    flux_ratio_tolerance: float | None = None,
    min_iterations: int = 1,
    fail_on_nonconvergence: bool = False,
    donjon_root: str | Path = "/Users/wen/dragon-5.1/Donjon",
    apply_template: str | Path | None = None,
    python_bin: str | Path | None = None,
    case_id_prefix: str = "openmc2donjon_sph_loop",
    stage_prefix: str = "odj_sph_loop",
    case_dir: str = "openmc2donjon/case_runs/openmc2donjon_sph_loop",
    sph_kind: str = "donjon-sph-loop",
    sph_real: bool = False,
    sph_applied: bool = False,
    source_label: str = "OpenMC SPH loop scaffold",
    postprocess_output: str = "corrected.macrolib.txt",
    root_name: str | None = None,
    h_factor_default: float | None = None,
    acceptance: dict[str, Any] | None = None,
    force: bool = False,
    summary_json: str | Path | None = None,
) -> SphLoopScaffoldReport:
    input_path = Path(input_h5)
    output_root = Path(output_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_path}")
    if scalar_flux_ids is not None and sequential_scalar_flux_map:
        raise ValueError("use either scalar_flux_ids or sequential_scalar_flux_map, not both")
    if scalar_flux_ids is None and not sequential_scalar_flux_map:
        raise ValueError(
            "a DONJON scalar flux map is required; pass scalar_flux_ids or "
            "set sequential_scalar_flux_map for simple one-unknown-per-mixture decks"
        )

    mixture_names, energy_bounds = _read_mgxs_metadata(input_path)
    energy_groups = int(energy_bounds.size - 1)
    loaded_reference = _load_matrix_source(
        reference_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=("openmc_volume_flux", "reference_flux", "flux", "phi", "value"),
        label="OpenMC reference flux",
    )
    _validate_reference_flux(loaded_reference.values)

    ids = (
        np.arange(1, len(mixture_names) + 1, dtype=int)
        if sequential_scalar_flux_map
        else _ids_from_mapping(scalar_flux_ids or {}, mixture_names)
    )

    reference_path = (
        Path(reference_output) if reference_output else output_root / "reference_flux.h5"
    )
    flux_map_path = (
        Path(flux_map_output) if flux_map_output else output_root / "flux_map.h5"
    )
    config_path = (
        Path(config_output) if config_output else output_root / "loop_config.json"
    )
    run_script_path = (
        Path(run_script_output) if run_script_output else output_root / "run_sph_loop.sh"
    )
    loop_dir = Path(loop_output_dir) if loop_output_dir else output_root / "sph_loop"
    for path in (reference_path, flux_map_path, config_path, run_script_path):
        _require_absent(path, force=force)

    output_root.mkdir(parents=True, exist_ok=True)
    _write_reference_flux(
        reference_path,
        input_h5=input_path,
        reference_flux=str(reference_flux),
        reference_dataset=loaded_reference.dataset_path,
        energy_bounds=energy_bounds,
        mixture_names=mixture_names,
        values=loaded_reference.values,
        source_label=source_label,
    )
    _write_flux_map(
        flux_map_path,
        input_h5=input_path,
        energy_bounds=energy_bounds,
        mixture_names=mixture_names,
        scalar_flux_ids=ids,
        sequential=sequential_scalar_flux_map,
        source_label=source_label,
    )
    warnings = (
        (
            "sequential scalar flux map assumes DONJON unknown ids follow MGXS "
            "mixture order; override with --scalar-flux-map for production decks",
        )
        if sequential_scalar_flux_map
        else ()
    )
    write_donjon_sph_loop_config(
        config_path,
        input_h5=input_path,
        output_dir=loop_dir,
        solve_template=solve_template,
        flux_map=flux_map_path,
        reference_flux=f"{reference_path}::openmc_volume_flux",
        output_format=output_format,
        final_solve=final_solve,
        iterations=iterations,
        damping=damping,
        clip_min=clip_min,
        clip_max=clip_max,
        flux_normalization=flux_normalization,
        sph_change_tolerance=sph_change_tolerance,
        flux_ratio_tolerance=flux_ratio_tolerance,
        min_iterations=min_iterations,
        fail_on_nonconvergence=fail_on_nonconvergence,
        donjon_root=donjon_root,
        apply_template=apply_template,
        python_bin=python_bin,
        case_id_prefix=case_id_prefix,
        stage_prefix=stage_prefix,
        case_dir=case_dir,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        source_label=source_label,
        postprocess_output=postprocess_output,
        root_name=root_name,
        h_factor_default=h_factor_default,
        acceptance=acceptance,
        run_script=run_script_path,
    )
    run_command = _run_sph_loop_command(config_path, python_bin=python_bin)
    _write_run_script(run_script_path, run_command)

    report = SphLoopScaffoldReport(
        input_h5=input_path,
        output_dir=output_root,
        reference_flux_source=loaded_reference.path,
        reference_flux_dataset=loaded_reference.dataset_path,
        reference_flux_h5=reference_path,
        flux_map_h5=flux_map_path,
        loop_config=config_path,
        run_script=run_script_path,
        run_command=run_command,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        scalar_flux_ids=tuple(int(value) for value in ids),
        sequential_scalar_flux_map=bool(sequential_scalar_flux_map),
        warnings=warnings,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(Path(summary_json), report)
    return report


def parse_scalar_flux_map(raw: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        if "=" not in item:
            raise ValueError("--scalar-flux-map entries must look like mixture=id")
        name, value = (part.strip() for part in item.split("=", 1))
        if not name:
            raise ValueError("--scalar-flux-map mixture names must be non-empty")
        if name in out:
            raise ValueError(f"--scalar-flux-map repeats mixture {name!r}")
        try:
            scalar_id = int(value)
        except ValueError as exc:
            raise ValueError(f"--scalar-flux-map id for {name!r} must be an integer") from exc
        if scalar_id <= 0:
            raise ValueError(f"--scalar-flux-map id for {name!r} must be positive")
        out[name] = scalar_id
    if not out:
        raise ValueError("--scalar-flux-map must list at least one mixture=id entry")
    return out


def print_report(report: SphLoopScaffoldReport) -> None:
    print("OpenMC-to-DONJON SPH loop scaffold")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output_dir: {report.output_dir}")
    print(f"  reference_flux_source: {report.reference_flux_source}")
    if report.reference_flux_dataset is not None:
        print(f"  reference_flux_dataset: {report.reference_flux_dataset}")
    print(f"  reference_flux_h5: {report.reference_flux_h5}")
    print(f"  flux_map_h5: {report.flux_map_h5}")
    print(f"  loop_config: {report.loop_config}")
    print(f"  run_script: {report.run_script}")
    print(f"  run_command: {_shell_join(report.run_command)}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"scalar_flux_ids={','.join(str(value) for value in report.scalar_flux_ids)}"
    )
    for warning in report.warnings:
        print(f"  WARN: {warning}")
    print()
    print("SPH loop scaffold decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: SphLoopScaffoldReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "input_h5": str(report.input_h5),
        "output_dir": str(report.output_dir),
        "reference_flux_source": str(report.reference_flux_source),
        "reference_flux_dataset": report.reference_flux_dataset,
        "reference_flux_h5": str(report.reference_flux_h5),
        "flux_map_h5": str(report.flux_map_h5),
        "loop_config": str(report.loop_config),
        "run_script": str(report.run_script),
        "run_command": list(report.run_command),
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "energy_groups": report.energy_groups,
        "scalar_flux_ids": list(report.scalar_flux_ids),
        "sequential_scalar_flux_map": report.sequential_scalar_flux_map,
        "warnings": list(report.warnings),
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
        mixture_names = read_mixture_names(h5)
        energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
    if not mixture_names:
        raise ValueError("input HDF5 has no mixtures")
    if energy_bounds.ndim != 1 or energy_bounds.size < 2:
        raise ValueError("energy_bounds must be a one-dimensional group-boundary vector")
    return mixture_names, energy_bounds


def _ids_from_mapping(ids_by_name: dict[str, int], mixture_names: tuple[str, ...]) -> np.ndarray:
    missing = [name for name in mixture_names if name not in ids_by_name]
    extra = sorted(set(ids_by_name) - set(mixture_names))
    if missing:
        raise ValueError(f"scalar flux map is missing mixture(s): {', '.join(missing)}")
    if extra:
        raise ValueError(f"scalar flux map contains unknown mixture(s): {', '.join(extra)}")
    ids = np.asarray([ids_by_name[name] for name in mixture_names], dtype=int)
    if np.any(ids <= 0):
        raise ValueError("scalar flux ids must be positive one-based DONJON unknown ids")
    return ids


def _validate_reference_flux(values: np.ndarray) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError("OpenMC reference flux values must be finite")
    if np.any(values <= 0.0):
        raise ValueError("OpenMC reference flux values must be positive")


def _write_reference_flux(
    path: Path,
    *,
    input_h5: Path,
    reference_flux: str,
    reference_dataset: str | None,
    energy_bounds: np.ndarray,
    mixture_names: tuple[str, ...],
    values: np.ndarray,
    source_label: str,
) -> None:
    import h5py

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = REFERENCE_FLUX_SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["source"] = source_label
        h5.attrs["input_h5"] = str(input_h5)
        h5.attrs["reference_flux_source"] = str(reference_flux)
        if reference_dataset is not None:
            h5.attrs["reference_flux_dataset"] = str(reference_dataset)
        h5.create_dataset("energy_bounds", data=np.asarray(energy_bounds, dtype=float))
        h5.create_dataset("mixture_names", data=np.asarray(mixture_names, dtype="S"))
        for name in ("openmc_volume_flux", "reference_flux", "volume_flux"):
            dataset = h5.create_dataset(name, data=np.asarray(values, dtype=float))
            dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
            dataset.attrs["group_order"] = MGXS_DONJON_GROUP_ORDER


def _write_flux_map(
    path: Path,
    *,
    input_h5: Path,
    energy_bounds: np.ndarray,
    mixture_names: tuple[str, ...],
    scalar_flux_ids: np.ndarray,
    sequential: bool,
    source_label: str,
) -> None:
    import h5py

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = FLUX_MAP_SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["source"] = source_label
        h5.attrs["input_h5"] = str(input_h5)
        h5.attrs["sequential_scalar_flux_map"] = bool(sequential)
        h5.create_dataset("energy_bounds", data=np.asarray(energy_bounds, dtype=float))
        h5.create_dataset("mixture_names", data=np.asarray(mixture_names, dtype="S"))
        dataset = h5.create_dataset(
            "scalar_flux_ids",
            data=np.asarray(scalar_flux_ids, dtype=int),
        )
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")


def _run_sph_loop_command(config_path: Path, *, python_bin: str | Path | None) -> tuple[str, ...]:
    return (
        str(python_bin or "python3"),
        "-m",
        "openmc2donjon.cli",
        "run-sph-loop",
        "--config",
        str(config_path),
    )


def _write_run_script(path: Path, command: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec {_shell_join(command)} \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | 0o111)


def _shell_join(command: tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _require_absent(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {path}")

"""Collapse adjacent MGXS energy groups while preserving reference rates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from .constants import MGXS_DONJON_GROUP_ORDER
from .energy_groups import energy_bounds_sha256
from .hdf5_names import read_mixture_names


SCHEMA = "openmc2donjon.energy-collapse.v1"
VECTOR_XS = (
    "total",
    "transport_total",
    "absorption",
    "fission",
    "nu_fission",
    "kappa_fission",
    "inverse_velocity",
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
)


def collapse_energy_groups(
    input_h5: str | Path,
    output_h5: str | Path,
    *,
    groups: Iterable[Iterable[int]],
    energy_group_structure: str = "custom-collapsed",
    force: bool = False,
    summary_json: str | Path | None = None,
) -> dict[str, object]:
    """Collapse adjacent 1-based DONJON groups with integrated-flux weights.

    The group declaration must cover every source group exactly once, in
    order.  Vector cross sections and transfer matrices preserve reaction and
    scattering production rates against ``/openmc_volume_flux``.  No
    arithmetic averaging or fitted correction is used.
    """

    import h5py

    source_path = Path(input_h5)
    destination = Path(output_h5)
    mapping = tuple(tuple(int(group) for group in members) for members in groups)
    if not source_path.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {source_path}")
    if destination.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {destination}")

    with h5py.File(source_path, "r") as source:
        names = read_mixture_names(source)
        if "openmc_volume_flux" not in source:
            raise ValueError(
                "energy collapse requires /openmc_volume_flux for "
                "reaction-rate-preserving weights"
            )
        flux = np.asarray(source["openmc_volume_flux"][:], dtype=float)
        source_groups = int(source.attrs.get("energy_groups", flux.shape[1]))
        if flux.shape != (len(names), source_groups):
            raise ValueError("/openmc_volume_flux shape must match mixture/group order")
        if not np.all(np.isfinite(flux)) or np.any(flux <= 0.0):
            raise ValueError("/openmc_volume_flux must contain positive finite values")
        _validate_mapping(mapping, source_groups)
        indices = tuple(np.asarray(group, dtype=int) - 1 for group in mapping)

        bounds = np.asarray(source["energy_bounds"][:], dtype=float)
        if bounds.shape != (source_groups + 1,) or np.any(np.diff(bounds) <= 0.0):
            raise ValueError("/energy_bounds must be strictly ascending")
        collapsed_bounds = _collapsed_energy_bounds(bounds, mapping)

        destination.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(destination, "w") as output:
            for key, value in source.attrs.items():
                output.attrs[key] = value
            output.attrs["energy_groups"] = len(mapping)
            output.attrs["energy_group_count"] = len(mapping)
            output.attrs["energy_group_structure"] = str(energy_group_structure)
            output.attrs["energy_mesh_id"] = str(energy_group_structure)
            output.attrs["energy_bounds_sha256"] = energy_bounds_sha256(collapsed_bounds)
            output.attrs["energy_collapse_schema"] = SCHEMA
            output.attrs["energy_collapse_source"] = str(source_path)
            output.attrs["energy_collapse_weight"] = "openmc-volume-integrated-flux"
            output.attrs["energy_collapse_group_order"] = MGXS_DONJON_GROUP_ORDER
            output.attrs["energy_collapse_mapping"] = np.asarray(
                [_format_group(group) for group in mapping], dtype="S"
            )

            for name in source:
                if name in {
                    "energy_bounds",
                    "mixtures",
                    "openmc_volume_flux",
                    "openmc_volume_flux_std_dev",
                }:
                    continue
                source.copy(name, output)
            output.create_dataset("energy_bounds", data=collapsed_bounds)

            collapsed_flux = _collapse_flux(flux, indices)
            flux_dataset = output.create_dataset("openmc_volume_flux", data=collapsed_flux)
            _copy_attrs(source["openmc_volume_flux"], flux_dataset)

            if "openmc_volume_flux_std_dev" in source:
                flux_std = np.asarray(
                    source["openmc_volume_flux_std_dev"][:], dtype=float
                )
                if flux_std.shape != flux.shape:
                    raise ValueError(
                        "/openmc_volume_flux_std_dev shape must match reference flux"
                    )
                collapsed_std = np.stack(
                    [np.sum(np.abs(flux_std[:, group]), axis=1) for group in indices],
                    axis=1,
                )
                std_dataset = output.create_dataset(
                    "openmc_volume_flux_std_dev", data=collapsed_std
                )
                _copy_attrs(source["openmc_volume_flux_std_dev"], std_dataset)
                std_dataset.attrs["energy_uncertainty_method"] = (
                    "conservative-l1-bound-no-tally-covariance"
                )

            mixtures = output.create_group("mixtures")
            for mixture_index, name in enumerate(names):
                source_group = source["mixtures"][name]
                target = mixtures.create_group(name)
                for key, value in source_group.attrs.items():
                    target.attrs[key] = value
                _write_collapsed_mixture(
                    source_group,
                    target,
                    flux[mixture_index],
                    indices,
                )

    report: dict[str, object] = {
        "schema": SCHEMA,
        "decision": "openmc2donjon_energy_collapse_passed",
        "input_h5": str(source_path),
        "output_h5": str(destination),
        "source_energy_groups": source_groups,
        "energy_groups": len(mapping),
        "energy_group_structure": str(energy_group_structure),
        "groups": [list(group) for group in mapping],
        "weight": "openmc-volume-integrated-flux",
    }
    if summary_json is not None:
        path = Path(summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _write_collapsed_mixture(source, target, flux, groups) -> None:
    source_groups = len(flux)
    supported = set(VECTOR_XS) | {
        "chi",
        "scatter_matrix",
    }
    unsupported = [
        name
        for name, dataset in source.items()
        if not name.endswith("_std_dev")
        and name not in supported
        and getattr(dataset, "shape", ()) not in {(), (1,)}
    ]
    if unsupported:
        raise ValueError(
            f"mixture {source.name}: energy collapse does not support datasets "
            f"{unsupported}"
        )

    collapsed_flux = np.asarray([np.sum(flux[group]) for group in groups])
    for name in VECTOR_XS:
        if name not in source:
            continue
        values = np.asarray(source[name][:], dtype=float)
        if values.shape != (source_groups,):
            raise ValueError(f"mixture {source.name}: {name} must be group-wise")
        collapsed = np.asarray(
            [np.dot(values[group], flux[group]) / collapsed_flux[i] for i, group in enumerate(groups)]
        )
        dataset = target.create_dataset(name, data=collapsed)
        _copy_attrs(source[name], dataset)

    if "scatter_matrix" in source:
        scatter = np.asarray(source["scatter_matrix"][:], dtype=float)
        if scatter.ndim != 3 or scatter.shape[1:] != (source_groups, source_groups):
            raise ValueError("scatter_matrix must have shape (moment, from, to)")
        collapsed = np.zeros((scatter.shape[0], len(groups), len(groups)), dtype=float)
        for coarse_from, fine_from in enumerate(groups):
            denominator = collapsed_flux[coarse_from]
            for coarse_to, fine_to in enumerate(groups):
                block = scatter[:, fine_from, :][:, :, fine_to]
                collapsed[:, coarse_from, coarse_to] = np.sum(
                    block * flux[fine_from][np.newaxis, :, np.newaxis],
                    axis=(1, 2),
                ) / denominator
        dataset = target.create_dataset("scatter_matrix", data=collapsed)
        _copy_attrs(source["scatter_matrix"], dataset)

    if "chi" in source:
        chi = np.asarray(source["chi"][:], dtype=float)
        if chi.shape != (source_groups,):
            raise ValueError(f"mixture {source.name}: chi must be group-wise")
        collapsed_chi = np.asarray([np.sum(chi[group]) for group in groups])
        total = float(np.sum(collapsed_chi))
        if total > 0.0:
            collapsed_chi /= total
        dataset = target.create_dataset("chi", data=collapsed_chi)
        _copy_attrs(source["chi"], dataset)

    for name, dataset in source.items():
        if name in supported or name.endswith("_std_dev"):
            continue
        if dataset.shape in {(), (1,)}:
            source.copy(name, target)


def _collapse_flux(flux: np.ndarray, groups) -> np.ndarray:
    return np.stack([np.sum(flux[:, group], axis=1) for group in groups], axis=1)


def _collapsed_energy_bounds(
    ascending_bounds: np.ndarray,
    mapping: tuple[tuple[int, ...], ...],
) -> np.ndarray:
    descending = ascending_bounds[::-1]
    collapsed_descending = [descending[mapping[0][0] - 1]]
    collapsed_descending.extend(descending[group[-1]] for group in mapping)
    return np.asarray(collapsed_descending[::-1], dtype=float)


def _validate_mapping(mapping: tuple[tuple[int, ...], ...], source_groups: int) -> None:
    if not mapping or any(not group for group in mapping):
        raise ValueError("at least one non-empty output energy group is required")
    flattened = [group for members in mapping for group in members]
    expected = list(range(1, source_groups + 1))
    if flattened != expected:
        raise ValueError(
            "energy groups must cover every 1-based DONJON group exactly once "
            f"in order; expected {expected}, got {flattened}"
        )
    if any(list(group) != list(range(group[0], group[-1] + 1)) for group in mapping):
        raise ValueError("each collapsed energy group must be contiguous")


def _copy_attrs(source, target) -> None:
    for key, value in source.attrs.items():
        target.attrs[key] = value


def _format_group(group: tuple[int, ...]) -> str:
    return str(group[0]) if len(group) == 1 else f"{group[0]}-{group[-1]}"


def _parse_group(value: str) -> tuple[int, ...]:
    text = value.strip()
    try:
        if "-" in text:
            lower, upper = (int(item.strip()) for item in text.split("-", 1))
            if upper < lower:
                raise ValueError
            return tuple(range(lower, upper + 1))
        return (int(text),)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("group must use N or N-M syntax") from exc


def print_energy_collapse_result(report: dict[str, object]) -> None:
    """Render the energy-collapse report as the CLI JSON result."""

    print(json.dumps(report, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_h5", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--group", action="append", type=_parse_group, required=True)
    parser.add_argument("--energy-group-structure", default="custom-collapsed")
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    report = collapse_energy_groups(
        args.input_h5,
        args.output,
        groups=args.group,
        energy_group_structure=args.energy_group_structure,
        force=args.force,
        summary_json=args.summary_json,
    )
    print_energy_collapse_result(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

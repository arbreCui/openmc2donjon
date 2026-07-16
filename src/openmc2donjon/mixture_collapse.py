"""Collapse repeated OpenMC domains into reaction-rate-preserving components."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from .hdf5_names import read_mixture_names, write_string_dataset


SCHEMA = "openmc2donjon.component-collapse.v1"
VECTOR_XS = (
    "total",
    "transport_total",
    "absorption",
    "fission",
    "nu_fission",
    "kappa_fission",
    "inverse_velocity",
)


def collapse_components(
    input_h5: str | Path,
    output_h5: str | Path,
    *,
    groups: Iterable[tuple[str, Iterable[str]]],
    force: bool = False,
    summary_json: str | Path | None = None,
) -> dict[str, object]:
    """Write a component HDF5 with rate-preserving grouped cross sections.

    Every source mixture must appear exactly once.  The required
    ``/openmc_volume_flux`` field is the incident-flux weight for vector and
    scattering cross sections.  This is a physical component collapse, not an
    arithmetic average of position-wise MGXS values.
    """

    import h5py

    source_path = Path(input_h5)
    destination = Path(output_h5)
    normalized_groups = tuple(
        (str(output_name), tuple(str(name) for name in source_names))
        for output_name, source_names in groups
    )
    _validate_group_declaration(normalized_groups)
    if not source_path.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {source_path}")
    if destination.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {destination}")

    with h5py.File(source_path, "r") as source:
        source_names = read_mixture_names(source)
        _validate_group_coverage(normalized_groups, source_names)
        if "openmc_volume_flux" not in source:
            raise ValueError(
                "component collapse requires /openmc_volume_flux for "
                "reaction-rate-preserving weights"
            )
        flux = np.asarray(source["openmc_volume_flux"][:], dtype=float)
        ngroups = int(source.attrs.get("energy_groups", flux.shape[1]))
        if flux.shape != (len(source_names), ngroups):
            raise ValueError(
                "/openmc_volume_flux shape must match source mixture/group order"
            )
        if not np.all(np.isfinite(flux)) or np.any(flux <= 0.0):
            raise ValueError("/openmc_volume_flux must contain positive finite values")
        flux_std = (
            None
            if "openmc_volume_flux_std_dev" not in source
            else np.asarray(source["openmc_volume_flux_std_dev"][:], dtype=float)
        )
        by_name = {name: index for index, name in enumerate(source_names)}

        destination.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(destination, "w") as output:
            for key, value in source.attrs.items():
                output.attrs[key] = value
            output.attrs["component_collapse_schema"] = SCHEMA
            output.attrs["component_collapse_source"] = str(source_path)
            output.attrs["component_collapse_weight"] = "openmc-volume-integrated-flux"
            output.attrs["domain_mode"] = "component"

            for name in source:
                if name in {
                    "mixtures",
                    "mixture_names",
                    "openmc_volume_flux",
                    "openmc_volume_flux_std_dev",
                }:
                    continue
                source.copy(name, output)

            output_names = tuple(name for name, _members in normalized_groups)
            write_string_dataset(output, "mixture_names", list(output_names))
            output_mixtures = output.create_group("mixtures")
            collapsed_flux = np.zeros((len(output_names), ngroups), dtype=float)
            collapsed_flux_std = (
                None if flux_std is None else np.zeros_like(collapsed_flux)
            )

            for output_index, (output_name, members) in enumerate(normalized_groups):
                indices = np.asarray([by_name[name] for name in members], dtype=int)
                member_flux = flux[indices, :]
                class_flux = np.sum(member_flux, axis=0)
                collapsed_flux[output_index, :] = class_flux
                if collapsed_flux_std is not None:
                    # Tally covariance is unavailable.  The L1 sum is a safe
                    # upper bound for the standard deviation of the sum.
                    collapsed_flux_std[output_index, :] = np.sum(
                        np.abs(flux_std[indices, :]),
                        axis=0,
                    )

                member_groups = [source["mixtures"][name] for name in members]
                target = output_mixtures.create_group(output_name)
                _write_component_attrs(target, member_groups, members, output_index)
                _write_component_datasets(
                    target,
                    member_groups,
                    member_flux,
                    class_flux,
                    ngroups,
                )

            flux_dataset = output.create_dataset(
                "openmc_volume_flux",
                data=collapsed_flux,
            )
            _copy_flux_attrs(
                source["openmc_volume_flux"],
                flux_dataset,
                output_names,
            )
            if collapsed_flux_std is not None:
                std_dataset = output.create_dataset(
                    "openmc_volume_flux_std_dev",
                    data=collapsed_flux_std,
                )
                _copy_flux_attrs(
                    source["openmc_volume_flux_std_dev"],
                    std_dataset,
                    output_names,
                )
                std_dataset.attrs["component_uncertainty_method"] = (
                    "conservative-l1-bound-no-tally-covariance"
                )

    report: dict[str, object] = {
        "schema": SCHEMA,
        "input_h5": str(source_path),
        "output_h5": str(destination),
        "source_mixture_count": len(source_names),
        "component_count": len(normalized_groups),
        "energy_groups": ngroups,
        "groups": [
            {"component": name, "source_mixtures": list(members)}
            for name, members in normalized_groups
        ],
        "weight": "openmc-volume-integrated-flux",
        "decision": "openmc2donjon_component_collapse_passed",
    }
    if summary_json is not None:
        path = Path(summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _write_component_attrs(target, member_groups, members, output_index: int) -> None:
    first = member_groups[0]
    for key, value in first.attrs.items():
        if key in {"source_domain_id", "source_domain_index", "volume"}:
            continue
        target.attrs[key] = value
    volumes = np.asarray(
        [float(group.attrs.get("volume", 1.0)) for group in member_groups],
        dtype=float,
    )
    if not np.all(np.isfinite(volumes)) or np.any(volumes <= 0.0):
        raise ValueError(f"component {target.name}: source volumes must be positive")
    target.attrs["volume"] = float(np.sum(volumes))
    target.attrs["source_domain_index"] = output_index + 1
    target.attrs["source_domain_type"] = "component-collapse"
    target.attrs["collapsed_source_mixtures"] = np.asarray(members, dtype="S")
    target.attrs["collapsed_source_count"] = len(members)


def _write_component_datasets(
    target,
    member_groups,
    member_flux: np.ndarray,
    class_flux: np.ndarray,
    ngroups: int,
) -> None:
    for name in VECTOR_XS:
        if not all(name in group for group in member_groups):
            continue
        values = np.stack([np.asarray(group[name][:], dtype=float) for group in member_groups])
        if values.shape != (len(member_groups), ngroups):
            raise ValueError(f"{name} must have one vector per source mixture")
        collapsed = np.sum(values * member_flux, axis=0) / class_flux
        target.create_dataset(name, data=collapsed)
        std_name = f"{name}_std_dev"
        if all(std_name in group for group in member_groups):
            std_values = np.stack(
                [np.asarray(group[std_name][:], dtype=float) for group in member_groups]
            )
            if std_values.shape != values.shape:
                raise ValueError(f"{std_name} must match the source {name} vectors")
            collapsed_std = np.sum(np.abs(std_values * member_flux), axis=0) / class_flux
            _write_component_uncertainty(target, std_name, collapsed_std)

    if all("scatter_matrix" in group for group in member_groups):
        scatter = np.stack(
            [np.asarray(group["scatter_matrix"][:], dtype=float) for group in member_groups]
        )
        if scatter.ndim != 4 or scatter.shape[2:] != (ngroups, ngroups):
            raise ValueError("scatter_matrix must have shape (moment, from, to)")
        weights = member_flux[:, np.newaxis, :, np.newaxis]
        collapsed_scatter = np.sum(scatter * weights, axis=0) / class_flux[
            np.newaxis, :, np.newaxis
        ]
        dataset = target.create_dataset("scatter_matrix", data=collapsed_scatter)
        for key, value in member_groups[0]["scatter_matrix"].attrs.items():
            dataset.attrs[key] = value
        if all("scatter_matrix_std_dev" in group for group in member_groups):
            scatter_std = np.stack(
                [
                    np.asarray(group["scatter_matrix_std_dev"][:], dtype=float)
                    for group in member_groups
                ]
            )
            if scatter_std.shape != scatter.shape:
                raise ValueError(
                    "scatter_matrix_std_dev must match source scatter_matrix"
                )
            collapsed_scatter_std = np.sum(
                np.abs(scatter_std * weights), axis=0
            ) / class_flux[np.newaxis, :, np.newaxis]
            _write_component_uncertainty(
                target,
                "scatter_matrix_std_dev",
                collapsed_scatter_std,
            )

    if all("chi" in group for group in member_groups):
        chi = np.stack([np.asarray(group["chi"][:], dtype=float) for group in member_groups])
        if all("nu_fission" in group for group in member_groups):
            nusigf = np.stack(
                [np.asarray(group["nu_fission"][:], dtype=float) for group in member_groups]
            )
            source_weights = np.sum(nusigf * member_flux, axis=1)
        else:
            source_weights = np.sum(member_flux, axis=1)
        if float(np.sum(source_weights)) > 0.0:
            chi_numerator = np.sum(chi * source_weights[:, np.newaxis], axis=0)
            chi_normalization = float(np.sum(chi_numerator))
            collapsed_chi = chi_numerator / chi_normalization
        else:
            collapsed_chi = np.zeros(ngroups, dtype=float)
        target.create_dataset("chi", data=collapsed_chi)
        if all("chi_std_dev" in group for group in member_groups):
            chi_std = np.stack(
                [np.asarray(group["chi_std_dev"][:], dtype=float) for group in member_groups]
            )
            if chi_std.shape != chi.shape:
                raise ValueError("chi_std_dev must match the source chi vectors")
            if float(np.sum(source_weights)) > 0.0:
                numerator_std = np.sum(
                    np.abs(chi_std * source_weights[:, np.newaxis]), axis=0
                )
                normalization_std = float(np.sum(numerator_std))
                collapsed_chi_std = (
                    numerator_std / chi_normalization
                    + np.abs(chi_numerator)
                    * normalization_std
                    / chi_normalization**2
                )
            else:
                collapsed_chi_std = np.zeros(ngroups, dtype=float)
            _write_component_uncertainty(
                target,
                "chi_std_dev",
                collapsed_chi_std,
            )


def _write_component_uncertainty(target, name: str, values: np.ndarray) -> None:
    dataset = target.create_dataset(name, data=values)
    dataset.attrs["component_uncertainty_method"] = (
        "conservative-l1-source-xs-bound-no-covariance"
    )


def _copy_flux_attrs(source, target, names: tuple[str, ...]) -> None:
    for key, value in source.attrs.items():
        if key == "mixture_names":
            continue
        target.attrs[key] = value
    target.attrs["mixture_names"] = np.asarray(names, dtype="S")


def _validate_group_declaration(groups: tuple[tuple[str, tuple[str, ...]], ...]) -> None:
    if not groups:
        raise ValueError("at least one component group is required")
    output_names = [name for name, _members in groups]
    if any(not name for name in output_names) or len(set(output_names)) != len(output_names):
        raise ValueError("component names must be non-empty and unique")
    if any(not members for _name, members in groups):
        raise ValueError("every component must contain at least one source mixture")


def _validate_group_coverage(
    groups: tuple[tuple[str, tuple[str, ...]], ...],
    source_names: tuple[str, ...],
) -> None:
    declared = [member for _name, members in groups for member in members]
    duplicates = sorted({name for name in declared if declared.count(name) > 1})
    missing = sorted(set(source_names) - set(declared))
    unknown = sorted(set(declared) - set(source_names))
    if duplicates or missing or unknown:
        raise ValueError(
            "component groups must cover every source mixture exactly once: "
            f"duplicates={duplicates}, missing={missing}, unknown={unknown}"
        )


def _parse_group(value: str) -> tuple[str, tuple[str, ...]]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("group must use COMPONENT=MIX1,MIX2 syntax")
    name, raw_members = value.split("=", 1)
    members = tuple(item.strip() for item in raw_members.split(",") if item.strip())
    if not name.strip() or not members:
        raise argparse.ArgumentTypeError("group must use COMPONENT=MIX1,MIX2 syntax")
    return name.strip(), members


def print_mixture_collapse_result(report: dict[str, object]) -> None:
    """Render the mixture-collapse report as the CLI JSON result."""

    print(json.dumps(report, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_h5", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--group", action="append", type=_parse_group, required=True)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    report = collapse_components(
        args.input_h5,
        args.output,
        groups=args.group,
        force=args.force,
        summary_json=args.summary_json,
    )
    print_mixture_collapse_result(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

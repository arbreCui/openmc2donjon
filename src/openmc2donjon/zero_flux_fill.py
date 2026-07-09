"""Fill zero-flux-group XS in a converter MGXS handoff from an OpenMC MG macrolib.

Fast-spectrum cores carry literally zero Monte Carlo flux in the thermal
groups of fine fast meshes (e.g. ECCO-33), so flux-weighted MGXS tallies are
0/0 -> 0 there at any statistics. For those groups this module substitutes
the exact material cross sections from the OpenMC MG macrolib that the
transport run consumed (track-length tallies already reproduce the macrolib
to machine precision wherever flux is nonzero, so the substitution is
consistent by construction).

For each mixture and each group g with total == 0, or transport_total <= 0
when that dataset is present:

- total, absorption, fission, nu_fission        <- macrolib material data
- scatter_matrix[:, g, :] (all shared orders)    <- macrolib scatter rows
- transport_total = total - sum_g' P1(g -> g')   (out-scatter correction)
- matching *_std_dev entries                     <- 0 (exact library value)

Filled group indices are recorded per mixture in the
``zero_flux_filled_groups`` attribute (converter order, index 0 = highest
energy group) together with the ``zero_flux_fill_source`` provenance path.

Mixtures are matched to macrolib materials through a label attribute on the
mixture group (default ``irena_mixture_label``); pass ``label_attr`` to use
another attribute name.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np


SCHEMA = "openmc2donjon.zero-flux-fill.v1"
DEFAULT_LABEL_ATTR = "irena_mixture_label"


@dataclass(frozen=True)
class ZeroFluxFillReport:
    input_h5: Path
    macrolib: Path
    output_h5: Path
    label_attr: str
    mixture_count: int
    filled_per_mixture: tuple[tuple[str, int], ...]
    total_filled_bins: int


def print_report(report: ZeroFluxFillReport) -> None:
    """Print the user-facing zero-flux fill report."""

    print("OpenMC-to-DONJON zero-flux fill")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  macrolib: {report.macrolib}")
    print(f"  output: {report.output_h5}")
    print(f"  label attribute: {report.label_attr}")
    print(f"  mixtures: {report.mixture_count}")
    print(f"  mixtures filled: {len(report.filled_per_mixture)}")
    print(f"  filled (mixture, group) bins: {report.total_filled_bins}")
    for name, count in report.filled_per_mixture:
        print(f"    {name}: {count}")
    print("")
    print("Zero-flux fill decision")
    print("  openmc2donjon_zero_flux_fill_passed")


def write_summary(path: Path, report: ZeroFluxFillReport) -> None:
    """Write a machine-readable zero-flux fill summary."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary_payload(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def summary_payload(report: ZeroFluxFillReport) -> dict[str, Any]:
    """Return the JSON-serializable zero-flux fill payload."""

    return {
        "schema": SCHEMA,
        "decision": "openmc2donjon_zero_flux_fill_passed",
        "input_h5": str(report.input_h5),
        "macrolib": str(report.macrolib),
        "output_h5": str(report.output_h5),
        "label_attr": report.label_attr,
        "mixtures": report.mixture_count,
        "filled_per_mixture": {name: count for name, count in report.filled_per_mixture},
        "total_filled_bins": report.total_filled_bins,
    }


def fill_zero_flux_groups(
    input_h5: Path,
    *,
    macrolib: Path,
    output_h5: Path | None = None,
    in_place: bool = False,
    label_attr: str = DEFAULT_LABEL_ATTR,
    force: bool = False,
) -> ZeroFluxFillReport:
    """Substitute macrolib XS into zero-flux (mixture, group) bins.

    By default the input file is copied to ``output_h5`` and the copy is
    edited; pass ``in_place=True`` (and no ``output_h5``) to edit the input
    file directly.
    """

    import h5py

    input_h5 = Path(input_h5)
    macrolib = Path(macrolib)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if not macrolib.exists():
        raise FileNotFoundError(f"macrolib does not exist: {macrolib}")
    if in_place:
        if output_h5 is not None:
            raise ValueError("--in-place cannot be combined with an output path")
        target_h5 = input_h5
    else:
        if output_h5 is None:
            raise ValueError("an output path is required unless in_place is set")
        target_h5 = Path(output_h5)
        if target_h5.resolve() == input_h5.resolve():
            raise ValueError("output HDF5 must be different from input HDF5; use in_place instead")
        if target_h5.exists() and not force:
            raise FileExistsError(f"output already exists; use --force to overwrite: {target_h5}")

    library = _load_macrolib(macrolib)
    by_name = {xsdata.name: xsdata for xsdata in library.xsdatas}

    if not in_place:
        target_h5.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_h5, target_h5)

    mixture_count = 0
    filled_per_mixture: list[tuple[str, int]] = []
    with h5py.File(target_h5, "r+") as h5:
        for name, group in h5["mixtures"].items():
            mixture_count += 1
            label = _mixture_label(group, name, label_attr)
            if label not in by_name:
                raise ValueError(
                    f"{name}: macrolib {macrolib} has no material named {label!r} "
                    f"(from mixture attribute {label_attr!r})"
                )
            xsdata = by_name[label]
            if len(xsdata.temperatures) != 1:
                raise ValueError(f"{label}: expected a single-temperature macrolib")
            temp_idx = 0

            total = group["total"][:]
            fill_mask = total == 0.0
            if "transport_total" in group:
                # Micro-flux groups can tally a few counts (total > 0) while
                # the P1-corrected transport value is still zero or negative
                # noise; substitute those bins from the macrolib as well.
                fill_mask |= group["transport_total"][:] <= 0.0
            fill = np.where(fill_mask)[0]
            if not len(fill):
                continue

            mac_total = _group_vector(xsdata.total[temp_idx])
            mac_absorption = _group_vector(xsdata.absorption[temp_idx])
            scatter = _dense_scatter(xsdata, temp_idx)
            n_orders_mac = scatter.shape[0]

            _fill_dataset(group, fill, "total", mac_total)
            _fill_dataset(group, fill, "absorption", mac_absorption)
            if xsdata.fissionable and "fission" in group:
                _fill_dataset(group, fill, "fission", _group_vector(xsdata.fission[temp_idx]))
                _fill_dataset(group, fill, "nu_fission", _group_vector(xsdata.nu_fission[temp_idx]))

            matrix = group["scatter_matrix"][:]
            for order in range(min(matrix.shape[0], n_orders_mac)):
                matrix[order][fill, :] = scatter[order][fill, :]
            group["scatter_matrix"][...] = matrix
            if "scatter_matrix_std_dev" in group:
                std = group["scatter_matrix_std_dev"][:]
                std[:, fill, :] = 0.0
                group["scatter_matrix_std_dev"][...] = std

            if "transport_total" in group:
                if n_orders_mac > 1:
                    correction = scatter[1].sum(axis=1)
                else:
                    correction = np.zeros_like(mac_total)
                _fill_dataset(group, fill, "transport_total", mac_total - correction)

            group.attrs["zero_flux_filled_groups"] = fill.astype(np.int64)
            group.attrs["zero_flux_fill_source"] = str(macrolib)
            filled_per_mixture.append((name, len(fill)))

    return ZeroFluxFillReport(
        input_h5=input_h5,
        macrolib=macrolib,
        output_h5=target_h5,
        label_attr=label_attr,
        mixture_count=mixture_count,
        filled_per_mixture=tuple(filled_per_mixture),
        total_filled_bins=sum(count for _name, count in filled_per_mixture),
    )


def _load_macrolib(macrolib: Path) -> Any:
    import openmc  # type: ignore[import-not-found]

    return openmc.MGXSLibrary.from_hdf5(str(macrolib))


def _mixture_label(group: Any, name: str, label_attr: str) -> str:
    if label_attr not in group.attrs:
        raise ValueError(f"{name}: mixture is missing the label attribute {label_attr!r}")
    label = group.attrs[label_attr]
    return label.decode() if isinstance(label, bytes) else str(label)


def _dense_scatter(xsdata: Any, temp_idx: int) -> np.ndarray:
    """Return dense (order, g_in, g_out) scatter matrix in converter order
    (index 0 = highest energy; macrolib storage is ascending energy)."""
    matrix = np.transpose(np.asarray(xsdata.scatter_matrix[temp_idx]), (2, 0, 1))
    return matrix[:, ::-1, ::-1]


def _group_vector(values: Any) -> np.ndarray:
    """Reverse an ascending-energy macrolib vector into converter order."""
    return np.asarray(values, dtype=float)[::-1]


def _fill_dataset(group: Any, fill: np.ndarray, key: str, values: np.ndarray) -> None:
    data = group[key][:]
    data[fill] = values[fill]
    group[key][...] = data
    std_key = f"{key}_std_dev"
    if std_key in group:
        std = group[std_key][:]
        std[fill] = 0.0
        group[std_key][...] = std

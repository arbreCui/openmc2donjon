#!/usr/bin/env python3
"""Fill zero-flux-group XS in the IRENA ZREFL export from the MG macrolib.

The IRENA-30 core is a fast reactor: the thermal groups of the 33-group
structure carry literally zero Monte Carlo flux, so flux-weighted MGXS
tallies are 0/0 -> 0 there at any statistics. For those groups this script
substitutes the exact material cross sections from the OpenMC MG macrolib
that the transport run consumed (track-length tallies already reproduce the
macrolib to machine precision wherever flux is nonzero, so the substitution
is consistent by construction).

For each mixture and each group g with total == 0:

- total, absorption, fission, nu_fission        <- macrolib material data
- scatter_matrix[:, g, :] (all Legendre orders)  <- macrolib scatter rows
- transport_total = total - sum_g' P1(g -> g')   (out-scatter correction)
- matching *_std_dev entries                     <- 0 (exact library value)

Filled group indices are recorded per mixture in the
``zero_flux_filled_groups`` attribute (converter order, index 0 = highest
energy group).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np
import openmc


def dense_scatter(xsdata, temp_idx: int) -> np.ndarray:
    """Return dense (order, g_in, g_out) scatter matrix in converter order
    (index 0 = highest energy; macrolib storage is ascending energy)."""
    matrix = np.transpose(np.asarray(xsdata.scatter_matrix[temp_idx]), (2, 0, 1))
    return matrix[:, ::-1, ::-1]


def group_vector(values) -> np.ndarray:
    """Reverse an ascending-energy macrolib vector into converter order."""
    return np.asarray(values, dtype=float)[::-1]


def fill_dataset(group, fill: np.ndarray, key: str, values: np.ndarray) -> None:
    data = group[key][:]
    data[fill] = values[fill]
    group[key][...] = data
    std_key = f"{key}_std_dev"
    if std_key in group:
        std = group[std_key][:]
        std[fill] = 0.0
        group[std_key][...] = std


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgxs", type=Path, required=True,
                        help="converted mgxs_library.h5 (edited in place)")
    parser.add_argument("--macrolib", type=Path, required=True, help="OpenMC MG macrolib the run consumed")
    args = parser.parse_args()

    library = openmc.MGXSLibrary.from_hdf5(str(args.macrolib))
    by_name = {xsdata.name: xsdata for xsdata in library.xsdatas}

    total_filled = 0
    with h5py.File(args.mgxs, "r+") as h5:
        for name, group in h5["mixtures"].items():
            label = group.attrs.get("irena_mixture_label")
            label = label.decode() if isinstance(label, bytes) else str(label)
            if label not in by_name:
                raise SystemExit(f"{name}: unknown IRENA mixture label {label!r}")
            xsdata = by_name[label]
            if len(xsdata.temperatures) != 1:
                raise SystemExit(f"{label}: expected a single-temperature macrolib")
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

            mac_total = group_vector(xsdata.total[temp_idx])
            mac_absorption = group_vector(xsdata.absorption[temp_idx])
            scatter = dense_scatter(xsdata, temp_idx)
            n_orders_mac = scatter.shape[0]

            fill_dataset(group, fill, "total", mac_total)
            fill_dataset(group, fill, "absorption", mac_absorption)
            if xsdata.fissionable and "fission" in group:
                fill_dataset(group, fill, "fission", group_vector(xsdata.fission[temp_idx]))
                fill_dataset(group, fill, "nu_fission", group_vector(xsdata.nu_fission[temp_idx]))

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
                fill_dataset(group, fill, "transport_total", mac_total - correction)

            group.attrs["zero_flux_filled_groups"] = fill.astype(np.int64)
            group.attrs["zero_flux_fill_source"] = str(args.macrolib)
            total_filled += len(fill)

    print(f"filled {total_filled} zero-flux (mixture, group) bins from {args.macrolib}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

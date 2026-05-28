"""Build deterministic inputs for the OpenMC-side SPH update-table example."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


ENERGY_BOUNDS = np.array([1.0e-5, 1.0, 1.0e7], dtype=float)
MIXTURE_NAMES = ("ASM_LEFT", "ASM_RIGHT")
PREVIOUS_SPH = np.array([[1.0, 1.1], [0.9, 1.0]], dtype=float)
REFERENCE_FLUX = np.array([[1.20, 0.80], [0.90, 1.10]], dtype=float)
LOW_ORDER_FLUX = np.array([[1.00, 1.00], [1.00, 1.00]], dtype=float)
EXPECTED_SPH = PREVIOUS_SPH * (LOW_ORDER_FLUX / REFERENCE_FLUX)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write deterministic OpenMC-side SPH update-table inputs.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory where example input files will be written",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    mgxs = output_dir / "mgxs_library.h5"
    previous = output_dir / "previous_sph.csv"
    reference = output_dir / "reference_flux.csv"
    low_order = output_dir / "low_order_flux.h5"
    expected = output_dir / "reference_expected.h5"

    _write_mgxs(mgxs)
    _write_table(previous, "sph", PREVIOUS_SPH)
    _write_table(reference, "reference_flux", REFERENCE_FLUX)
    _write_low_order_flux(low_order)
    _write_reference(expected)

    print("OpenMC-side SPH update-table inputs")
    print(f"  mgxs: {mgxs}")
    print(f"  previous_sph: {previous}")
    print(f"  reference_flux: {reference}")
    print(f"  low_order_flux: {low_order}")
    print(f"  reference: {expected}")
    return 0


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.attrs["domain_mode"] = "openmc_sph_update_table_example"
        h5.attrs["spatial_mapping"] = "one OpenMC MG macro region -> one DONJON mixture"
        h5.create_dataset("energy_bounds", data=ENERGY_BOUNDS)
        mixtures = h5.create_group("mixtures")
        _write_mixture(
            mixtures,
            "ASM_LEFT",
            fissionable=True,
            total=np.array([0.50, 0.70]),
            absorption=np.array([0.05, 0.10]),
            scatter=np.array([[[0.40, 0.05], [0.02, 0.58]]]),
            transport=np.array([0.45, 0.63]),
        )
        _write_mixture(
            mixtures,
            "ASM_RIGHT",
            fissionable=False,
            total=np.array([0.30, 0.60]),
            absorption=np.array([0.02, 0.04]),
            scatter=np.array([[[0.27, 0.01], [0.03, 0.53]]]),
            transport=np.array([0.29, 0.57]),
        )


def _write_mixture(
    mixtures,
    name: str,
    *,
    fissionable: bool,
    total: np.ndarray,
    absorption: np.ndarray,
    scatter: np.ndarray,
    transport: np.ndarray,
) -> None:
    group = mixtures.create_group(name)
    group.attrs["fissionable"] = bool(fissionable)
    group.attrs["scatter_axes"] = "moment,from,to"
    group.attrs["volume"] = 64.0
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset("fission", data=np.zeros(2))
    group.create_dataset("nu_fission", data=np.zeros(2))
    group.create_dataset("chi", data=np.array([1.0, 0.0]) if fissionable else np.zeros(2))
    group.create_dataset("scatter_matrix", data=scatter)
    group.create_dataset("transport_total", data=transport)


def _write_table(path: Path, value_column: str, values: np.ndarray) -> None:
    lines = ["mixture,group," + value_column]
    for mixture_index, mixture in enumerate(MIXTURE_NAMES):
        for group_index, value in enumerate(values[mixture_index], start=1):
            lines.append(f"{mixture},{group_index},{value:.12g}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_low_order_flux(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset("volume_flux", data=LOW_ORDER_FLUX)
        dataset.attrs["mixture_names"] = np.asarray(MIXTURE_NAMES, dtype="S")
        dataset.attrs["group_order"] = "mgxs_donjon"
        dataset.attrs["source_group_order"] = "example_mgxs_order"
        h5.create_dataset("mixture_names", data=np.asarray(MIXTURE_NAMES, dtype="S"))


def _write_reference(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.openmc-sph-update-table-reference.v1"
        h5.create_dataset("expected_sph", data=EXPECTED_SPH)
        h5.create_dataset("mixture_names", data=np.asarray(MIXTURE_NAMES, dtype="S"))


if __name__ == "__main__":
    raise SystemExit(main())

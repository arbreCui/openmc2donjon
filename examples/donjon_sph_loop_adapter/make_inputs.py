"""Build deterministic inputs for the generic DONJON SPH loop adapter example."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


ENERGY_BOUNDS = np.array([1.0e-5, 1.0, 1.0e7], dtype=float)
MIXTURE_NAMES = ("ASM_LEFT", "ASM_RIGHT")
SCALAR_FLUX_IDS = np.array([2, 4], dtype=int)
REFERENCE_FLUX = np.array([[80.0, 800.0], [120.0, 600.0]], dtype=float)
EXPECTED_SPH = np.full((2, 2), np.sqrt(0.5), dtype=float)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write deterministic inputs for the DONJON SPH loop adapter."
    )
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
    reference = output_dir / "reference_flux.h5"
    flux_map = output_dir / "flux_map.h5"
    expected = output_dir / "reference_expected.h5"

    _write_mgxs(mgxs)
    _write_reference_flux(reference)
    _write_flux_map(flux_map)
    _write_reference(expected)

    print("DONJON SPH loop adapter inputs")
    print(f"  mgxs: {mgxs}")
    print(f"  reference_flux: {reference}")
    print(f"  flux_map: {flux_map}")
    print(f"  reference: {expected}")
    return 0


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.attrs["domain_mode"] = "donjon_sph_loop_adapter"
        h5.attrs["spatial_mapping"] = (
            "one low-order scalar flux unknown -> one DONJON mixture"
        )
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
            volume=100.0,
        )
        _write_mixture(
            mixtures,
            "ASM_RIGHT",
            fissionable=False,
            total=np.array([0.30, 0.60]),
            absorption=np.array([0.02, 0.04]),
            scatter=np.array([[[0.27, 0.01], [0.03, 0.53]]]),
            transport=np.array([0.29, 0.57]),
            volume=120.0,
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
    volume: float,
) -> None:
    group = mixtures.create_group(name)
    group.attrs["fissionable"] = bool(fissionable)
    group.attrs["scatter_axes"] = "moment,from,to"
    group.attrs["volume"] = float(volume)
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset("fission", data=np.array([0.01, 0.03]) if fissionable else np.zeros(2))
    group.create_dataset(
        "nu_fission",
        data=np.array([0.025, 0.075]) if fissionable else np.zeros(2),
    )
    group.create_dataset("chi", data=np.array([1.0, 0.0]) if fissionable else np.zeros(2))
    group.create_dataset("scatter_matrix", data=scatter)
    group.create_dataset("transport_total", data=transport)


def _write_reference_flux(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.reference-flux.v1"
        dataset = h5.create_dataset("openmc_volume_flux", data=REFERENCE_FLUX)
        names = np.asarray(MIXTURE_NAMES, dtype="S")
        dataset.attrs["mixture_names"] = names
        h5.create_dataset("mixture_names", data=names)


def _write_flux_map(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.donjon-flux-map.v1"
        dataset = h5.create_dataset("scalar_flux_ids", data=SCALAR_FLUX_IDS)
        names = np.asarray(MIXTURE_NAMES, dtype="S")
        dataset.attrs["mixture_names"] = names
        h5.create_dataset("mixture_names", data=names)


def _write_reference(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.donjon-sph-loop-adapter-reference.v1"
        h5.create_dataset("expected_sph", data=EXPECTED_SPH)
        h5.create_dataset("mixture_names", data=np.asarray(MIXTURE_NAMES, dtype="S"))
        h5.create_dataset("scalar_flux_ids", data=SCALAR_FLUX_IDS)


if __name__ == "__main__":
    raise SystemExit(main())

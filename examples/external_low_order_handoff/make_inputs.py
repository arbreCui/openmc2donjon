"""Build deterministic inputs for the external low-order handoff example."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


ENERGY_BOUNDS = np.array([1.0e-5, 1.0, 1.0e7], dtype=float)
MIXTURE_NAMES = ("ASM_LEFT", "ASM_RIGHT")
RAW_MIXTURE_NAMES = ("ASM_RIGHT", "ASM_LEFT")
FACES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
RAW_FACES = ("FD_YMAX", "FD_XMAX", "FD_YMIN", "FD_XMIN")
FACE_WIDTHS = np.ones(len(FACES), dtype=float)

TRANSPORT_TOTAL = np.array(
    [
        [0.45, 0.63],
        [0.29, 0.57],
    ],
    dtype=float,
)
VOLUME_FLUX = np.array(
    [
        [1.00, 0.80],
        [0.92, 1.10],
    ],
    dtype=float,
)
NET_CURRENT_OUTWARD = np.array(
    [
        [
            [-0.020, 0.010],
            [0.010, -0.020],
            [0.015, 0.005],
            [-0.005, 0.015],
        ],
        [
            [0.012, -0.008],
            [-0.018, 0.010],
            [0.006, 0.012],
            [-0.010, -0.006],
        ],
    ],
    dtype=float,
)
TARGET_ADF = np.array(
    [
        [
            [1.020, 0.980],
            [0.990, 1.030],
            [1.010, 1.000],
            [0.970, 1.040],
        ],
        [
            [1.015, 0.985],
            [0.995, 1.025],
            [1.005, 1.010],
            [0.975, 1.035],
        ],
    ],
    dtype=float,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write deterministic MGXS, external low-order, and face-flux inputs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory where example input HDF5 files will be written",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    mgxs = output_dir / "mgxs_library.h5"
    raw_driver = output_dir / "external_solver_raw_driver.h5"
    surface_flux = output_dir / "openmc_surface_flux.h5"
    reference = output_dir / "reference_expected.h5"

    homogeneous = _homogeneous_face_flux()
    surface = homogeneous * TARGET_ADF

    _write_mgxs(mgxs)
    _write_raw_driver(raw_driver)
    _write_surface_flux(surface_flux, surface)
    _write_reference(reference, homogeneous, TARGET_ADF)

    print("external low-order handoff inputs")
    print(f"  mgxs: {mgxs}")
    print(f"  raw_driver: {raw_driver}")
    print(f"  surface_flux: {surface_flux}::detector/surface_phi")
    print(f"  reference: {reference}")
    return 0


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.attrs["domain_mode"] = "external_low_order_example"
        h5.attrs["spatial_mapping"] = "one external low-order node -> one DONJON mixture"
        h5.create_dataset("energy_bounds", data=ENERGY_BOUNDS)
        mixtures = h5.create_group("mixtures")
        _write_mixture(
            mixtures,
            "ASM_LEFT",
            fissionable=True,
            volume=64.0,
            total=np.array([0.50, 0.70]),
            absorption=np.array([0.05, 0.10]),
            fission=np.array([0.010, 0.020]),
            nu_fission=np.array([0.025, 0.050]),
            chi=np.array([1.0, 0.0]),
            scatter=np.array([[[0.40, 0.05], [0.02, 0.58]]]),
            transport=TRANSPORT_TOTAL[0],
        )
        _write_mixture(
            mixtures,
            "ASM_RIGHT",
            fissionable=False,
            volume=64.0,
            total=np.array([0.30, 0.60]),
            absorption=np.array([0.02, 0.04]),
            fission=np.array([0.0, 0.0]),
            nu_fission=np.array([0.0, 0.0]),
            chi=np.array([0.0, 0.0]),
            scatter=np.array([[[0.27, 0.01], [0.03, 0.53]]]),
            transport=TRANSPORT_TOTAL[1],
        )


def _write_mixture(
    mixtures,
    name: str,
    *,
    fissionable: bool,
    volume: float,
    total: np.ndarray,
    absorption: np.ndarray,
    fission: np.ndarray,
    nu_fission: np.ndarray,
    chi: np.ndarray,
    scatter: np.ndarray,
    transport: np.ndarray,
) -> None:
    group = mixtures.create_group(name)
    group.attrs["fissionable"] = bool(fissionable)
    group.attrs["scatter_axes"] = "moment,from,to"
    group.attrs["volume"] = float(volume)
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset("fission", data=fission)
    group.create_dataset("nu_fission", data=nu_fission)
    group.create_dataset("chi", data=chi)
    group.create_dataset("scatter_matrix", data=scatter)
    group.create_dataset("transport_total", data=transport)


def _write_raw_driver(path: Path) -> None:
    raw_mixture_indices = [MIXTURE_NAMES.index(name) for name in RAW_MIXTURE_NAMES]
    raw_face_indices = [FACES.index(name) for name in RAW_FACES]
    raw_volume = VOLUME_FLUX[raw_mixture_indices]
    raw_current_positive_inward = -NET_CURRENT_OUTWARD[np.ix_(raw_mixture_indices, raw_face_indices)]

    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.low-order-driver-raw.v1"
        h5.attrs["source"] = "example external nodal solve with case-specific paths"
        h5.attrs["volume_flux_dataset"] = "solver/scalar_flux"
        h5.attrs["net_current_dataset"] = "solver/boundary_current_density"
        solver = h5.create_group("solver")
        volume = solver.create_dataset("scalar_flux", data=raw_volume)
        current = solver.create_dataset("boundary_current_density", data=raw_current_positive_inward)
        volume.attrs["mixture_names"] = np.asarray(RAW_MIXTURE_NAMES, dtype="S")
        current.attrs["mixture_names"] = np.asarray(RAW_MIXTURE_NAMES, dtype="S")
        current.attrs["face_names"] = np.asarray(RAW_FACES, dtype="S")
        current.attrs["sign_convention"] = "positive inward"


def _write_surface_flux(path: Path, values: np.ndarray) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "external-openmc-surface-flux-example.v1"
        detector = h5.create_group("detector")
        dataset = detector.create_dataset("surface_phi", data=values)
        dataset.attrs["mixture_names"] = np.asarray(MIXTURE_NAMES, dtype="S")
        dataset.attrs["face_names"] = np.asarray(FACES, dtype="S")


def _write_reference(path: Path, homogeneous: np.ndarray, adf: np.ndarray) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.external-low-order-reference.v1"
        h5.create_dataset("canonical_volume_flux", data=VOLUME_FLUX)
        h5.create_dataset("canonical_net_current_density", data=NET_CURRENT_OUTWARD)
        h5.create_dataset("homogeneous_face_flux", data=homogeneous)
        h5.create_dataset("adf", data=adf)
        h5.create_dataset("mixture_names", data=np.asarray(MIXTURE_NAMES, dtype="S"))
        h5.create_dataset("face_names", data=np.asarray(FACES, dtype="S"))


def _homogeneous_face_flux() -> np.ndarray:
    diffusion = 1.0 / (3.0 * TRANSPORT_TOTAL)
    return VOLUME_FLUX[:, np.newaxis, :] - (
        NET_CURRENT_OUTWARD
        * FACE_WIDTHS[np.newaxis, :, np.newaxis]
        / (2.0 * diffusion[:, np.newaxis, :])
    )


if __name__ == "__main__":
    raise SystemExit(main())

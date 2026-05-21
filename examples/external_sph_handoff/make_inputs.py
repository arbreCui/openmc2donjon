"""Build deterministic inputs for the external SPH handoff example."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


ENERGY_BOUNDS = np.array([1.0e-5, 1.0, 1.0e7], dtype=float)
MIXTURE_NAMES = ("ASM_LEFT", "ASM_RIGHT")
SPH = np.array(
    [
        [1.10, 0.90],
        [0.95, 1.05],
    ],
    dtype=float,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write deterministic MGXS and external SPH table inputs."
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
    table = output_dir / "external_solver_sph.csv"
    reference = output_dir / "reference_expected.h5"

    _write_mgxs(mgxs)
    _write_sph_table(table)
    _write_reference(reference)

    print("external SPH handoff inputs")
    print(f"  mgxs: {mgxs}")
    print(f"  sph_table: {table}")
    print(f"  reference: {reference}")
    return 0


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.attrs["domain_mode"] = "external_sph_example"
        h5.attrs["spatial_mapping"] = "one external SPH node -> one DONJON mixture"
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
            transport=np.array([0.45, 0.63]),
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
            transport=np.array([0.29, 0.57]),
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


def _write_sph_table(path: Path) -> None:
    lines = ["mixture,group,sph"]
    for mix_index, mixture in enumerate(MIXTURE_NAMES):
        for group_index, value in enumerate(SPH[mix_index], start=1):
            lines.append(f"{mixture},{group_index},{value:.12g}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_reference(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.external-sph-reference.v1"
        h5.create_dataset("sph", data=SPH)
        h5.create_dataset("mixture_names", data=np.asarray(MIXTURE_NAMES, dtype="S"))


if __name__ == "__main__":
    raise SystemExit(main())

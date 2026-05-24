"""Create deterministic inputs for the minimal SPH loop user case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import h5py
import numpy as np


ENERGY_BOUNDS = np.array([1.0e-5, 1.0, 1.0e7], dtype=float)
MIXTURE_NAMES = ("FUEL_ASM", "REFL_ASM")
SCALAR_FLUX_IDS = np.array([2, 4], dtype=int)
REFERENCE_FLUX = np.array([[80.0, 800.0], [120.0, 600.0]], dtype=float)
EXPECTED_SPH = np.full((2, 2), np.sqrt(0.5), dtype=float)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write inputs for the SPH loop minicase."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="case directory where inputs and optional config will be written",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="optional concrete run-sph-loop config to write",
    )
    parser.add_argument(
        "--driver",
        type=Path,
        default=Path(__file__).with_name("fake_low_order_solver.py"),
        help="low-order solver stub or production runner path",
    )
    parser.add_argument("--python-bin", default=sys.executable)
    args = parser.parse_args(argv)

    case_dir = args.output_dir
    input_dir = case_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)

    mgxs = input_dir / "mgxs_library.h5"
    reference = input_dir / "reference_flux.h5"
    flux_map = input_dir / "flux_map.h5"
    expected = case_dir / "expected_sph.h5"

    _write_mgxs(mgxs)
    _write_reference_flux(reference)
    _write_flux_map(flux_map)
    _write_expected(expected)
    if args.config is not None:
        _write_config(
            args.config,
            driver=args.driver,
            python_bin=args.python_bin,
        )

    print("SPH loop minicase inputs")
    print(f"  mgxs: {mgxs}")
    print(f"  reference_flux: {reference}")
    print(f"  flux_map: {flux_map}")
    print(f"  expected_sph: {expected}")
    if args.config is not None:
        print(f"  config: {args.config}")
    return 0


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.attrs["domain_mode"] = "assembly-wise"
        h5.attrs["spatial_mapping"] = (
            "one OpenMC homogenized domain -> one DONJON mixture"
        )
        h5.create_dataset("energy_bounds", data=ENERGY_BOUNDS)
        h5.create_dataset("mixture_names", data=np.asarray(MIXTURE_NAMES, dtype="S"))
        mixtures = h5.create_group("mixtures")
        _write_mixture(
            mixtures,
            "FUEL_ASM",
            source_domain_index=1,
            source_domain_id=101,
            fissionable=True,
            total=np.array([0.50, 0.70]),
            absorption=np.array([0.05, 0.10]),
            scatter=np.array([[[0.40, 0.05], [0.02, 0.58]]]),
            transport=np.array([0.45, 0.63]),
            volume=100.0,
        )
        _write_mixture(
            mixtures,
            "REFL_ASM",
            source_domain_index=2,
            source_domain_id=102,
            fissionable=False,
            total=np.array([0.30, 0.60]),
            absorption=np.array([0.02, 0.04]),
            scatter=np.array([[[0.27, 0.01], [0.03, 0.53]]]),
            transport=np.array([0.29, 0.57]),
            volume=120.0,
        )


def _write_mixture(
    mixtures: h5py.Group,
    name: str,
    *,
    source_domain_index: int,
    source_domain_id: int,
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
    group.attrs["source_domain_index"] = int(source_domain_index)
    group.attrs["source_domain_id"] = int(source_domain_id)
    group.attrs["source_domain_type"] = "assembly"
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset(
        "fission",
        data=np.array([0.01, 0.03]) if fissionable else np.zeros(2),
    )
    group.create_dataset(
        "nu_fission",
        data=np.array([0.025, 0.075]) if fissionable else np.zeros(2),
    )
    if fissionable:
        group.create_dataset("kappa_fission", data=np.array([3.2e-12, 3.1e-12]))
    group.create_dataset(
        "chi",
        data=np.array([1.0, 0.0]) if fissionable else np.zeros(2),
    )
    group.create_dataset("scatter_matrix", data=scatter)
    group.create_dataset("transport_total", data=transport)


def _write_reference_flux(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.reference-flux.v1"
        dataset = h5.create_dataset("openmc_volume_flux", data=REFERENCE_FLUX)
        names = np.asarray(MIXTURE_NAMES, dtype="S")
        dataset.attrs["mixture_names"] = names
        dataset.attrs["group_order"] = "mgxs_donjon"
        h5.create_dataset("mixture_names", data=names)


def _write_flux_map(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.low-order-flux-map.v1"
        dataset = h5.create_dataset("scalar_flux_ids", data=SCALAR_FLUX_IDS)
        names = np.asarray(MIXTURE_NAMES, dtype="S")
        dataset.attrs["mixture_names"] = names
        h5.create_dataset("mixture_names", data=names)


def _write_expected(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.sph-loop-minicase-reference.v1"
        h5.create_dataset("expected_sph", data=EXPECTED_SPH)
        h5.create_dataset("mixture_names", data=np.asarray(MIXTURE_NAMES, dtype="S"))
        h5.create_dataset("scalar_flux_ids", data=SCALAR_FLUX_IDS)


def _write_config(path: Path, *, driver: Path, python_bin: str) -> None:
    payload = {
        "schema": "openmc2donjon.sph-loop-config.v1",
        "input_h5": "inputs/mgxs_library.h5",
        "output_dir": "sph_loop",
        "reference_flux": "inputs/reference_flux.h5::openmc_volume_flux",
        "map_h5": "inputs/flux_map.h5",
        "iterations": 2,
        "format": "macrolib",
        "final_solve": True,
        "damping": 0.5,
        "clip_min": 0.5,
        "clip_max": 2.0,
        "sph_kind": "sph-loop-minicase",
        "sph_real": False,
        "sph_applied": False,
        "source_label": "SPH loop minicase low-order flux",
        "convergence": {
            "sph_change_tolerance": 1.0e-12,
            "flux_ratio_tolerance": 1.0e-12,
            "min_iterations": 2,
            "fail_on_nonconvergence": True,
        },
        "acceptance": {
            "preset": "production",
        },
        "solver": {
            "command": [
                python_bin,
                str(driver.resolve()),
                "solve",
                "--macrolib",
                "{ascii_input}",
                "--result",
                "{result}",
                "--iteration",
                "{iteration}",
            ],
            "result": "low_order_flux.result",
        },
        "postprocess": {
            "command": [
                python_bin,
                str(driver.resolve()),
                "apply",
                "--input",
                "{workflow_ascii}",
                "--output",
                "{output}",
                "--sph",
                "{sph_sidecar}",
                "--iteration",
                "{iteration1}",
            ],
            "output": "corrected.macrolib.txt",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())

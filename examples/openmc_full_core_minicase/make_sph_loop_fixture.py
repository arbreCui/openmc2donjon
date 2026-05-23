"""Build a concrete SPH-loop fixture from the full-core OpenMC minicase MGXS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from openmc2donjon.hdf5_names import read_mixture_names


EXPECTED_SPH_VALUE = 2.0
ASCII_ROUNDTRIP_TOLERANCE = 1.0e-8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write full-core SPH loop inputs for run-sph-loop."
    )
    parser.add_argument("--mgxs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--driver",
        type=Path,
        default=Path(__file__).with_name("fake_full_core_low_order_solver.py"),
    )
    parser.add_argument("--python-bin", default=sys.executable)
    args = parser.parse_args(argv)

    mixture_names, energy_groups, reference_flux = _read_mgxs(args.mgxs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    flux_map = args.output_dir / "flux_map.h5"
    expected = args.output_dir / "expected_sph.h5"
    _write_flux_map(flux_map, mixture_names=mixture_names)
    _write_expected(expected, mixture_names=mixture_names, energy_groups=energy_groups)
    _write_config(
        args.config,
        mgxs=args.mgxs,
        flux_map=flux_map,
        driver=args.driver,
        python_bin=args.python_bin,
    )

    print("Full-core SPH loop fixture")
    print(f"  mgxs: {args.mgxs}")
    print(f"  reference_flux: {args.mgxs}::openmc_volume_flux")
    print(f"  flux_map: {flux_map}")
    print(f"  expected_sph: {expected}")
    print(f"  config: {args.config}")
    print(
        "  dimensions: "
        f"mixtures={len(mixture_names)} groups={energy_groups} "
        f"flux_min={float(np.min(reference_flux)):.6g} "
        f"flux_max={float(np.max(reference_flux)):.6g}"
    )
    return 0


def _read_mgxs(path: Path) -> tuple[tuple[str, ...], int, np.ndarray]:
    if not path.exists():
        raise SystemExit(f"missing MGXS HDF5: {path}")
    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise SystemExit(f"{path}: missing /mixtures")
        if "openmc_volume_flux" not in h5:
            raise SystemExit(f"{path}: missing /openmc_volume_flux")
        mixture_names = read_mixture_names(h5)
        for index, name in enumerate(mixture_names, start=1):
            group = h5["mixtures"][name]
            if int(group.attrs.get("source_domain_index", -1)) != index:
                raise SystemExit(
                    f"{path}: mixture {name} source_domain_index does not "
                    "match /mixture_names order"
                )
        reference_flux = np.asarray(h5["openmc_volume_flux"][:], dtype=float)
        energy_groups = int(h5.attrs.get("energy_groups", reference_flux.shape[-1]))
    if reference_flux.shape != (len(mixture_names), energy_groups):
        raise SystemExit(
            f"{path}: /openmc_volume_flux shape {reference_flux.shape} does not "
            f"match mixtures={len(mixture_names)} groups={energy_groups}"
        )
    if not np.all(np.isfinite(reference_flux)) or np.any(reference_flux <= 0.0):
        raise SystemExit(f"{path}: /openmc_volume_flux must be positive finite")
    return mixture_names, energy_groups, reference_flux


def _write_flux_map(path: Path, *, mixture_names: tuple[str, ...]) -> None:
    names = np.asarray(mixture_names, dtype="S")
    scalar_flux_ids = np.arange(1, len(mixture_names) + 1, dtype=int)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.low-order-flux-map.v1"
        dataset = h5.create_dataset("scalar_flux_ids", data=scalar_flux_ids)
        dataset.attrs["mixture_names"] = names
        dataset.attrs["index_order"] = "mixture_names"
        dataset.attrs["id_base"] = 1
        dataset.attrs["id_kind"] = "donjon_scalar_flux_unknown"
        h5.create_dataset("mixture_names", data=names)


def _write_expected(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.full-core-sph-fixture.v1"
        h5.attrs["expected_sph_value"] = EXPECTED_SPH_VALUE
        h5.create_dataset(
            "expected_sph",
            data=np.full(
                (len(mixture_names), energy_groups),
                EXPECTED_SPH_VALUE,
                dtype=float,
            ),
        )
        h5.create_dataset("mixture_names", data=np.asarray(mixture_names, dtype="S"))


def _write_config(
    path: Path,
    *,
    mgxs: Path,
    flux_map: Path,
    driver: Path,
    python_bin: str,
) -> None:
    payload = {
        "schema": "openmc2donjon.sph-loop-config.v1",
        "input_h5": str(mgxs.resolve()),
        "output_dir": str((path.parent / "sph_loop").resolve()),
        "reference_flux": f"{mgxs.resolve()}::openmc_volume_flux",
        "map_h5": str(flux_map.resolve()),
        "iterations": 2,
        "format": "macrolib",
        "final_solve": True,
        "damping": 1.0,
        "clip_min": 0.25,
        "clip_max": 4.0,
        "sph_kind": "full-core-assembly-sph-loop",
        "sph_real": False,
        "sph_applied": False,
        "source_label": "OpenMC full-core assembly-wise SPH loop smoke",
        "convergence": {
            "sph_change_tolerance": ASCII_ROUNDTRIP_TOLERANCE,
            "flux_ratio_tolerance": ASCII_ROUNDTRIP_TOLERANCE,
            "min_iterations": 2,
            "fail_on_nonconvergence": True,
        },
        "acceptance": {
            "min_completed_iterations": 2,
            "require_converged": True,
            "require_final_solve": True,
            "max_sph_rel_change": ASCII_ROUNDTRIP_TOLERANCE,
            "max_flux_ratio_residual": ASCII_ROUNDTRIP_TOLERANCE,
            "sph_minimum_floor": EXPECTED_SPH_VALUE - ASCII_ROUNDTRIP_TOLERANCE,
            "sph_maximum_ceiling": EXPECTED_SPH_VALUE + ASCII_ROUNDTRIP_TOLERANCE,
            "max_final_to_initial_flux_residual_ratio": ASCII_ROUNDTRIP_TOLERANCE,
            "max_final_clipped_count": 0,
            "require_artifact_metadata_alignment": True,
            "require_production_audit": True,
            "require_mgxs_explicit_volumes": True,
            "fail_on_violation": True,
        },
        "solver": {
            "command": [
                python_bin,
                str(driver.resolve()),
                "solve",
                "--input-h5",
                "{input_h5}",
                "--macrolib",
                "{ascii_input}",
                "--result",
                "{result}",
                "--iteration",
                "{iteration}",
                "--previous-sph",
                "{previous_sph}",
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

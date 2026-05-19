#!/usr/bin/env python3
"""Build a C5G7 assembly-wise ADF candidate from OpenMC face tallies.

The output is primarily diagnostic. If the input current file contains
``/surface_flux`` from a mu-binned OpenMC mesh-surface tally, that
heterogeneous surface-flux reconstruction is used. Otherwise, the script falls
back to the P1 partial-current proxy. It compares that heterogeneous face flux
against a diffusion-consistent homogeneous face flux estimated from the same
assembly volume flux and net current:

    phi_face_hom = phi_avg - J_out * h / (2D)

This is not a substitute for a full homogeneous nodal solve, but it is useful
for finding the size, sign, and stability of the discontinuity-factor problem
before wiring ADFs back into MULTICOMPO.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import h5py
import numpy as np


PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH
FACE_AREA = ASSEMBLY_PITCH
FACE_NAMES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
PARTIAL_FACE_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7))
DEFAULT_MGXS = Path(
    "/Users/wen/openmc-workspace/c5g7_converter_test/mgxs_library_assembly_p1.h5"
)
DEFAULT_CURRENTS = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_boundary_currents_full.h5"
)
DEFAULT_OUT = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_adf_candidate.h5"
)
DEFAULT_DONJON_FLUX_DUMP = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/c5g7ap1_flux_dump.result"
)
DEFAULT_DONJON_TRACK_DUMP = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/c5g7ap1_track_dump.result"
)
DEFAULT_HOMOGENEOUS_FACE_FLUX = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_homogeneous_face_flux_donjon.h5"
)


def main() -> int:
    args = _parse_args()
    mgxs = _read_mgxs(args.mgxs)
    currents = _read_currents(args.currents)
    candidate = _build_candidate(
        mgxs,
        currents,
        homogeneous_source=args.homogeneous_source,
        homogeneous_face_flux_path=args.homogeneous_face_flux,
        donjon_flux_dump=args.donjon_flux_dump,
        donjon_track_dump=args.donjon_track_dump,
    )
    _write_diagnostic(args.output, mgxs, currents, candidate)
    _print_summary(candidate)
    if args.output_mgxs is not None:
        adf = _adf_for_write(
            candidate["adf_candidate"],
            candidate["valid_adf_mask"],
            args.clip_min,
            args.clip_max,
            args.invalid_fill,
        )
        _write_mgxs_with_adf(args.mgxs, args.output_mgxs, mgxs, candidate, adf, args)
        print(f"Wrote MGXS with ADF datasets: {args.output_mgxs}")
    print(f"Wrote diagnostic: {args.output}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--currents", type=Path, default=DEFAULT_CURRENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--output-mgxs",
        type=Path,
        default=None,
        help=(
            "optional HDF5 copy of --mgxs with /mixtures/*/adf datasets added; "
            "requires --clip-min/--clip-max if any raw candidate value is invalid"
        ),
    )
    parser.add_argument(
        "--clip-min",
        type=float,
        default=None,
        help="optional minimum ADF value to use when writing --output-mgxs",
    )
    parser.add_argument(
        "--clip-max",
        type=float,
        default=None,
        help="optional maximum ADF value to use when writing --output-mgxs",
    )
    parser.add_argument(
        "--invalid-fill",
        type=float,
        default=None,
        help=(
            "value used for invalid raw ADF bins when writing --output-mgxs; "
            "if omitted, invalid bins are an error"
        ),
    )
    parser.add_argument(
        "--production-adf",
        action="store_true",
        help=(
            "mark --output-mgxs ADF data as the project production definition: "
            "OpenMC mu-surface flux over DONJON mixed-dual current face-flux "
            "reconstruction"
        ),
    )
    parser.add_argument(
        "--homogeneous-source",
        choices=("openmc-current", "donjon-flux"),
        default="openmc-current",
        help=(
            "source for the homogeneous face flux denominator. "
            "'openmc-current' uses the original local diffusion estimate; "
            "'donjon-flux' uses a DONJON mixed-dual current face-flux "
            "reconstruction and normalizes it to OpenMC volume flux"
        ),
    )
    parser.add_argument("--donjon-flux-dump", type=Path, default=DEFAULT_DONJON_FLUX_DUMP)
    parser.add_argument("--donjon-track-dump", type=Path, default=DEFAULT_DONJON_TRACK_DUMP)
    parser.add_argument(
        "--homogeneous-face-flux",
        type=Path,
        default=DEFAULT_HOMOGENEOUS_FACE_FLUX,
        help=(
            "HDF5 file produced by extract_c5g7_donjon_face_flux.py; used by "
            "--homogeneous-source donjon-flux when available"
        ),
    )
    args = parser.parse_args()
    if (args.clip_min is None) ^ (args.clip_max is None):
        parser.error("--clip-min and --clip-max must be supplied together")
    if args.clip_min is not None and args.clip_min <= 0.0:
        parser.error("--clip-min must be positive")
    if (
        args.clip_min is not None
        and args.clip_max is not None
        and args.clip_min > args.clip_max
    ):
        parser.error("--clip-min must be <= --clip-max")
    if args.invalid_fill is not None and args.invalid_fill <= 0.0:
        parser.error("--invalid-fill must be positive")
    return args


def _read_mgxs(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as h5:
        energy_bounds = h5["energy_bounds"][:]
        names = list(h5["mixtures"])
        mesh_dim = int(h5.attrs.get("mesh_dimension", round(len(names) ** 0.5)))
        ngroups = int(h5.attrs.get("energy_groups", len(energy_bounds) - 1))
        diffusion = np.zeros((mesh_dim, mesh_dim, ngroups), dtype=float)
        mixture_names = np.empty((mesh_dim, mesh_dim), dtype=object)
        for name in names:
            group = h5["mixtures"][name]
            mesh_index = np.asarray(group.attrs["mesh_index"], dtype=int)
            x_index = int(mesh_index[0]) - 1
            y_index = int(mesh_index[1]) - 1
            if "transport_total" in group:
                transport_total = np.asarray(group["transport_total"][:], dtype=float)
            else:
                transport_total = np.asarray(group["total"][:], dtype=float)
            if np.any(transport_total <= 0.0):
                raise ValueError(f"{name}: transport_total must be positive")
            diffusion[y_index, x_index] = 1.0 / (3.0 * transport_total)
            mixture_names[y_index, x_index] = str(name)
        if any(value is None for value in mixture_names.reshape(-1)):
            raise ValueError("MGXS mixture mesh is incomplete")
        return {
            "path": str(path),
            "energy_bounds": energy_bounds,
            "mesh_dim": mesh_dim,
            "ngroups": ngroups,
            "diffusion": diffusion,
            "mixture_names": mixture_names,
        }


def _read_currents(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as h5:
        current = h5["boundary_currents/mean"][:]
        current_std_dev = h5["boundary_currents/std_dev"][:]
        volume_flux = h5["volume_flux/average"][:]
        energy_bounds = h5["energy_bounds"][:]
        if current.ndim != 4 or current.shape[-1] != 8:
            raise ValueError("expected current shape [mesh_y, mesh_x, group, 8]")
        if volume_flux.shape != current.shape[:3]:
            raise ValueError("volume flux shape does not match current bins")
        surface_flux = h5["surface_flux/mean"][:] if "surface_flux" in h5 else None
        surface_flux_std_dev = (
            h5["surface_flux/std_dev"][:] if "surface_flux" in h5 else None
        )
        if surface_flux is not None and surface_flux.shape != current.shape[:3] + (4,):
            raise ValueError("surface_flux shape does not match current bins")
        return {
            "path": str(path),
            "energy_bounds": energy_bounds,
            "current": current,
            "current_std_dev": current_std_dev,
            "volume_flux": volume_flux,
            "surface_flux": surface_flux,
            "surface_flux_std_dev": surface_flux_std_dev,
        }


def _build_candidate(
    mgxs: dict[str, object],
    currents: dict[str, object],
    *,
    homogeneous_source: str,
    homogeneous_face_flux_path: Path,
    donjon_flux_dump: Path,
    donjon_track_dump: Path,
) -> dict[str, np.ndarray]:
    if not np.allclose(mgxs["energy_bounds"], currents["energy_bounds"]):
        raise ValueError("MGXS and current files have different energy_bounds")
    diffusion = np.asarray(mgxs["diffusion"], dtype=float)
    current = np.asarray(currents["current"], dtype=float)
    current_std_dev = np.asarray(currents["current_std_dev"], dtype=float)
    volume_flux = np.asarray(currents["volume_flux"], dtype=float)
    measured_surface_flux = currents.get("surface_flux")
    measured_surface_flux_std_dev = currents.get("surface_flux_std_dev")
    if diffusion.shape != volume_flux.shape:
        raise ValueError("MGXS diffusion shape does not match volume flux shape")

    surface_flux = np.zeros(volume_flux.shape + (4,), dtype=float)
    surface_flux_std_dev = np.zeros_like(surface_flux)
    net_current_density = np.zeros_like(surface_flux)
    homogeneous_face_flux = np.zeros_like(surface_flux)

    for face, (out_idx, in_idx) in enumerate(PARTIAL_FACE_PAIRS):
        outgoing = current[..., out_idx]
        incoming = current[..., in_idx]
        outgoing_std = current_std_dev[..., out_idx]
        incoming_std = current_std_dev[..., in_idx]
        surface_flux[..., face] = 2.0 * (outgoing + incoming) / FACE_AREA
        surface_flux_std_dev[..., face] = (
            2.0 * np.sqrt(outgoing_std**2 + incoming_std**2) / FACE_AREA
        )
        net_current_density[..., face] = (outgoing - incoming) / FACE_AREA
        homogeneous_face_flux[..., face] = volume_flux - (
            net_current_density[..., face] * ASSEMBLY_PITCH / (2.0 * diffusion)
        )
    homogeneous_face_source = "OpenMC volume flux plus OpenMC net-current diffusion estimate"
    if homogeneous_source == "donjon-flux":
        if homogeneous_face_flux_path.exists():
            homogeneous_face_flux_values, homogeneous_face_source = (
                _read_homogeneous_face_flux_file(homogeneous_face_flux_path, mgxs, currents)
            )
            homogeneous_face_flux = homogeneous_face_flux_values
        else:
            homogeneous_face_flux = _donjon_homogeneous_face_flux(
                mgxs,
                currents,
                donjon_flux_dump,
                donjon_track_dump,
            )
            homogeneous_face_source = (
                "DONJON mixed-dual current face-flux reconstruction normalized to OpenMC volume flux"
            )
    elif homogeneous_source != "openmc-current":
        raise ValueError(f"unsupported homogeneous_source {homogeneous_source!r}")

    surface_flux_source = "P1 partial-current proxy"
    if measured_surface_flux is not None:
        surface_flux = np.asarray(measured_surface_flux, dtype=float)
        surface_flux_source = "OpenMC mu-binned mesh-surface flux reconstruction"
        if measured_surface_flux_std_dev is not None:
            surface_flux_std_dev = np.asarray(measured_surface_flux_std_dev, dtype=float)

    adf_candidate = np.divide(
        surface_flux,
        homogeneous_face_flux,
        out=np.full_like(surface_flux, np.nan),
        where=homogeneous_face_flux != 0.0,
    )
    valid_homogeneous_flux = homogeneous_face_flux > 0.0
    valid_adf_mask = (
        valid_homogeneous_flux & np.isfinite(adf_candidate) & (adf_candidate > 0.0)
    )
    return {
        "diffusion": diffusion,
        "volume_flux": volume_flux,
        "surface_flux_proxy": surface_flux,
        "surface_flux_proxy_std_dev": surface_flux_std_dev,
        "surface_flux_source": surface_flux_source,
        "net_current_density": net_current_density,
        "homogeneous_face_flux": homogeneous_face_flux,
        "homogeneous_face_source": homogeneous_face_source,
        "valid_homogeneous_flux": valid_homogeneous_flux,
        "adf_candidate": adf_candidate,
        "valid_adf_mask": valid_adf_mask,
        "interior_face_mask": _interior_face_mask(volume_flux.shape[:2]),
    }


def _interior_face_mask(mesh_shape: tuple[int, int]) -> np.ndarray:
    mesh_y, mesh_x = mesh_shape
    mask = np.zeros((mesh_y, mesh_x, 4), dtype=np.bool_)
    for y_index in range(mesh_y):
        for x_index in range(mesh_x):
            mask[y_index, x_index, 0] = x_index > 0
            mask[y_index, x_index, 1] = x_index < mesh_x - 1
            mask[y_index, x_index, 2] = y_index > 0
            mask[y_index, x_index, 3] = y_index < mesh_y - 1
    return mask


def _write_diagnostic(
    path: Path,
    mgxs: dict[str, object],
    currents: dict[str, object],
    candidate: dict[str, np.ndarray],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["source"] = "C5G7 diffusion-consistent ADF candidate"
        h5.attrs["mgxs"] = mgxs["path"]
        h5.attrs["currents"] = currents["path"]
        h5.attrs["formula"] = "ADF = phi_surface_proxy / (phi_avg - J_out*h/(2D))"
        h5.attrs["surface_flux_source"] = str(candidate["surface_flux_source"])
        h5.attrs["homogeneous_face_source"] = str(candidate["homogeneous_face_source"])
        h5.attrs["warning"] = (
            "Diagnostic only. Invalid or extreme bins indicate that this linear "
            "homogeneous-face estimate is not sufficient as a production ADF."
        )
        h5.attrs["face_area_cm2_unit_height"] = FACE_AREA
        h5.create_dataset("energy_bounds", data=mgxs["energy_bounds"])
        h5.create_dataset("face_names", data=np.asarray(FACE_NAMES, dtype="S"))
        h5.create_dataset(
            "mixture_names",
            data=np.asarray(mgxs["mixture_names"], dtype="S"),
        )
        for name, values in candidate.items():
            if name in {"surface_flux_source", "homogeneous_face_source"}:
                continue
            h5.create_dataset(name, data=values)


def _adf_for_write(
    adf: np.ndarray,
    valid_mask: np.ndarray,
    clip_min: float | None,
    clip_max: float | None,
    invalid_fill: float | None,
) -> np.ndarray:
    if not np.all(valid_mask) and invalid_fill is None:
        invalid = int(valid_mask.size - np.count_nonzero(valid_mask))
        raise ValueError(
            f"raw ADF candidate has {invalid} invalid bins; either inspect "
            "the diagnostic file or pass --invalid-fill for an explicit fill policy"
        )
    safe = np.array(adf, dtype=float, copy=True)
    if invalid_fill is not None:
        safe[~valid_mask] = invalid_fill
        safe = np.nan_to_num(
            safe,
            nan=invalid_fill,
            posinf=invalid_fill,
            neginf=invalid_fill,
        )
    if clip_min is not None and clip_max is not None:
        safe = np.clip(safe, clip_min, clip_max)
    return safe


def _write_mgxs_with_adf(
    input_mgxs: Path,
    output_mgxs: Path,
    mgxs: dict[str, object],
    candidate: dict[str, np.ndarray],
    adf: np.ndarray,
    args: argparse.Namespace,
) -> None:
    output_mgxs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_mgxs, output_mgxs)
    mixture_names = np.asarray(mgxs["mixture_names"], dtype=object)
    valid_mask = np.asarray(candidate["valid_adf_mask"], dtype=bool)
    interior_mask = np.broadcast_to(
        candidate["interior_face_mask"][:, :, np.newaxis, :],
        valid_mask.shape,
    )
    with h5py.File(output_mgxs, "a") as h5:
        if args.production_adf:
            h5.attrs["adf_source"] = (
                "OpenMC mu-surface flux over DONJON mixed-dual current "
                "face-flux reconstruction"
            )
            h5.attrs["adf_kind"] = "production"
            h5.attrs["adf_real"] = "true"
        else:
            h5.attrs["adf_source"] = "build_c5g7_adf_candidate.py"
            h5.attrs["adf_kind"] = "diagnostic"
            h5.attrs["adf_real"] = "false"
        h5.attrs["adf_method"] = (
            "openmc_mu_surface_over_donjon_mixed_dual_face_flux"
        )
        h5.attrs["adf_generator"] = "build_c5g7_adf_candidate.py"
        h5.attrs["adf_surface_flux_source"] = str(candidate["surface_flux_source"])
        h5.attrs["adf_homogeneous_face_source"] = str(
            candidate["homogeneous_face_source"]
        )
        h5.attrs["adf_invalid_policy"] = (
            f"fill={args.invalid_fill}" if args.invalid_fill is not None else "none"
        )
        h5.attrs["adf_invalid_count"] = int(valid_mask.size - np.count_nonzero(valid_mask))
        h5.attrs["adf_invalid_interior_count"] = int(
            np.count_nonzero((~valid_mask) & interior_mask)
        )
        if args.clip_min is not None and args.clip_max is not None:
            h5.attrs["adf_clip_min"] = float(args.clip_min)
            h5.attrs["adf_clip_max"] = float(args.clip_max)
            h5.attrs["adf_clip_policy"] = "clip_after_invalid_fill"
        h5.attrs["adf_raw_valid_count"] = int(np.count_nonzero(valid_mask))
        h5.attrs["adf_raw_total_count"] = int(valid_mask.size)
        for y_index in range(adf.shape[0]):
            for x_index in range(adf.shape[1]):
                name = str(mixture_names[y_index, x_index])
                group = h5["mixtures"][name]
                if "adf" in group:
                    del group["adf"]
                values = np.moveaxis(adf[y_index, x_index], -1, 0)
                dataset = group.create_dataset("adf", data=values)
                dataset.attrs["face_names"] = np.asarray(FACE_NAMES, dtype="S")


def _print_summary(candidate: dict[str, np.ndarray]) -> None:
    adf = candidate["adf_candidate"]
    valid = candidate["valid_adf_mask"]
    interior = np.broadcast_to(
        candidate["interior_face_mask"][:, :, np.newaxis, :], adf.shape
    )
    valid_values = adf[valid]
    interior_values = adf[valid & interior]
    invalid_count = int(valid.size - np.count_nonzero(valid))
    invalid_interior = int(np.count_nonzero((~valid) & interior))
    print(
        "Raw diffusion-consistent ADF candidate: "
        f"valid={np.count_nonzero(valid)}/{valid.size}, invalid={invalid_count}"
    )
    print(f"  surface flux source: {candidate['surface_flux_source']}")
    print(f"  homogeneous face source: {candidate['homogeneous_face_source']}")
    print(
        "  valid all faces: "
        f"min={np.min(valid_values):.6g}, "
        f"median={np.median(valid_values):.6g}, "
        f"max={np.max(valid_values):.6g}"
    )
    print(
        "  valid interior faces: "
        f"min={np.min(interior_values):.6g}, "
        f"median={np.median(interior_values):.6g}, "
        f"max={np.max(interior_values):.6g}, "
        f"invalid={invalid_interior}"
    )


def _donjon_homogeneous_face_flux(
    mgxs: dict[str, object],
    currents: dict[str, object],
    flux_dump: Path,
    track_dump: Path,
) -> np.ndarray:
    vectors = _read_donjon_flux_vectors(flux_dump)
    kn = _read_donjon_kn(track_dump)
    diffusion = np.asarray(mgxs["diffusion"], dtype=float)
    volume_flux = np.asarray(currents["volume_flux"], dtype=float)
    mesh_dim = int(mgxs["mesh_dim"])
    ngroups = int(mgxs["ngroups"])
    if vectors.shape[0] < ngroups:
        raise ValueError(
            f"DONJON flux dump has {vectors.shape[0]} groups, expected {ngroups}"
        )
    vectors = vectors[:ngroups]
    if kn.shape != (mesh_dim * mesh_dim, 7):
        raise ValueError(
            f"DONJON KN shape {kn.shape} is not compatible with {mesh_dim}x{mesh_dim}"
        )

    homogeneous = np.zeros((mesh_dim, mesh_dim, ngroups, 4), dtype=float)
    donjon_volume_flux = np.zeros((mesh_dim, mesh_dim, ngroups), dtype=float)
    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            element = y_index * mesh_dim + x_index
            ids = kn[element]
            flux_id = int(ids[0])
            if flux_id <= 0:
                raise ValueError(f"DONJON KN element {element + 1} has no flux id")
            for group in range(ngroups):
                phi = float(vectors[group, flux_id - 1])
                donjon_volume_flux[y_index, x_index, group] = phi
                coeff = ASSEMBLY_PITCH / (2.0 * diffusion[y_index, x_index, group])
                currents_out = (
                    0.0 if ids[1] == 0 else -float(vectors[group, ids[1] - 1]),
                    0.0 if ids[2] == 0 else float(vectors[group, ids[2] - 1]),
                    0.0 if ids[3] == 0 else -float(vectors[group, ids[3] - 1]),
                    0.0 if ids[4] == 0 else float(vectors[group, ids[4] - 1]),
                )
                for face, current in enumerate(currents_out):
                    homogeneous[y_index, x_index, group, face] = phi - current * coeff

    scale = np.divide(
        volume_flux,
        donjon_volume_flux,
        out=np.ones_like(volume_flux),
        where=donjon_volume_flux != 0.0,
    )
    return homogeneous * scale[:, :, :, np.newaxis]


def _read_homogeneous_face_flux_file(
    path: Path,
    mgxs: dict[str, object],
    currents: dict[str, object],
) -> tuple[np.ndarray, str]:
    with h5py.File(path, "r") as h5:
        values = np.asarray(h5["homogeneous_face_flux"][:], dtype=float)
        if "energy_bounds" in h5 and not np.allclose(h5["energy_bounds"][:], mgxs["energy_bounds"]):
            raise ValueError(f"{path}: energy_bounds do not match MGXS")
        source = _attr_text(
            h5.attrs.get(
                "source",
                "DONJON mixed-dual current face-flux reconstruction HDF5",
            )
        )
    expected = np.asarray(currents["volume_flux"]).shape + (4,)
    if values.shape != expected:
        raise ValueError(f"{path}: homogeneous_face_flux shape {values.shape} != {expected}")
    return values, f"{source} ({path})"


def _read_donjon_flux_vectors(path: Path) -> np.ndarray:
    text = path.read_text(errors="replace").splitlines()
    vectors: list[list[float]] = []
    header = re.compile(r"^->\s+2\s+0\s+2\s+(\d+)\s+<-\s+\d+")
    for index, line in enumerate(text):
        match = header.match(line)
        if not match:
            continue
        count = int(match.group(1))
        values: list[float] = []
        cursor = index + 1
        while len(values) < count and cursor < len(text):
            try:
                values.extend(float(token) for token in text[cursor].split())
            except ValueError:
                break
            cursor += 1
        if len(values) == count:
            vectors.append(values)
    if not vectors:
        raise ValueError(f"no unnamed FLUX vectors found in {path}")
    widths = {len(vector) for vector in vectors}
    if len(widths) != 1:
        raise ValueError(f"inconsistent DONJON FLUX vector lengths in {path}: {widths}")
    return np.asarray(vectors, dtype=float)


def _read_donjon_kn(path: Path) -> np.ndarray:
    text = path.read_text(errors="replace").splitlines()
    header = re.compile(r"^->\s+1\s+12\s+1\s+(\d+)\s+<-")
    for index, line in enumerate(text):
        match = header.match(line)
        if not match:
            continue
        if index + 1 >= len(text) or text[index + 1].strip() != "KN":
            continue
        count = int(match.group(1))
        values: list[int] = []
        cursor = index + 2
        while len(values) < count and cursor < len(text):
            try:
                values.extend(int(token) for token in text[cursor].split())
            except ValueError:
                break
            cursor += 1
        if len(values) != count:
            raise ValueError(f"incomplete DONJON KN payload in {path}")
        if count % 7 != 0:
            raise ValueError(f"DONJON KN length {count} is not divisible by 7")
        return np.asarray(values, dtype=int).reshape(count // 7, 7)
    raise ValueError(f"no DONJON KN block found in {path}")


def _attr_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.bytes_):
        return value.decode()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())

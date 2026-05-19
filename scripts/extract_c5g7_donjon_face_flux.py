#!/usr/bin/env python3
"""Extract a C5G7 DONJON homogeneous face-flux diagnostic.

The input is a pair of UTL ASCII dumps:

* an ``L_FLUX`` dump from the assembly-wise DONJON solve
* the matching ``L_TRACK`` dump from ``TRIVAT:``

For the current C5G7 assembly benchmark, ``DUAL 1 1`` gives one scalar flux
unknown and four face-current unknowns per Cartesian cell. DONJON does not dump
a separate scalar face flux in the ``L_FLUX`` object, so this script
reconstructs a Fick-consistent face-flux estimate from the mixed-dual current
unknowns, normalizes the DONJON nodal cell flux to the OpenMC assembly-average
flux, and writes a compact HDF5 file that can be compared with OpenMC
heterogeneous surface fluxes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np

from openmc2donjon import lcm_ascii as lcm


DEFAULT_MGXS = Path(
    "/Users/wen/openmc-workspace/c5g7_converter_test/mgxs_library_assembly_p1.h5"
)
DEFAULT_CURRENTS = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_boundary_currents_mu_full.h5"
)
DEFAULT_FLUX_DUMP = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/c5g7ap1_flux_dump.result"
)
DEFAULT_TRACK_DUMP = Path(
    "/Users/wen/dragon-5.1/Donjon/Darwin_arm64/c5g7ap1_track_dump.result"
)
DEFAULT_OUT = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_homogeneous_face_flux_donjon.h5"
)

PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH
FACE_NAMES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")


def main() -> int:
    args = _parse_args()
    mgxs = _read_mgxs(args.mgxs)
    currents = _read_currents(args.currents)
    flux_vectors = _read_flux_vectors(args.flux_dump, mgxs["ngroups"])
    track = _read_track(args.track_dump, mgxs["mesh_dim"])
    face_flux = _reconstruct_face_flux(mgxs, currents, flux_vectors, track["kn"])
    checks = _checks(face_flux["homogeneous_face_flux"], prefix="normalized")
    checks.update(_checks(face_flux["homogeneous_face_flux_raw"], prefix="raw"))
    checks.update(_current_sanity(mgxs, flux_vectors, track["kn"]))
    _write_output(args.output, args, mgxs, currents, flux_vectors, track, face_flux, checks)
    _print_summary(args.output, face_flux, checks)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgxs", type=Path, default=DEFAULT_MGXS)
    parser.add_argument("--currents", type=Path, default=DEFAULT_CURRENTS)
    parser.add_argument("--flux-dump", type=Path, default=DEFAULT_FLUX_DUMP)
    parser.add_argument("--track-dump", type=Path, default=DEFAULT_TRACK_DUMP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def _read_mgxs(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as h5:
        energy_bounds = h5["energy_bounds"][:]
        mesh_dim = int(h5.attrs.get("mesh_dimension", round(len(h5["mixtures"]) ** 0.5)))
        ngroups = int(h5.attrs.get("energy_groups", len(energy_bounds) - 1))
        diffusion = np.zeros((mesh_dim, mesh_dim, ngroups), dtype=float)
        mixture_names = np.empty((mesh_dim, mesh_dim), dtype=object)
        for name in h5["mixtures"]:
            group = h5["mixtures"][name]
            mesh_index = np.asarray(group.attrs["mesh_index"], dtype=int)
            x_index = int(mesh_index[0]) - 1
            y_index = int(mesh_index[1]) - 1
            transport_total = np.asarray(group["transport_total"][:], dtype=float)
            diffusion[y_index, x_index] = 1.0 / (3.0 * transport_total)
            mixture_names[y_index, x_index] = str(name)
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
        volume_flux = np.asarray(h5["volume_flux/average"][:], dtype=float)
        surface_flux = (
            np.asarray(h5["surface_flux/mean"][:], dtype=float)
            if "surface_flux" in h5
            else None
        )
    return {
        "path": str(path),
        "volume_flux": volume_flux,
        "surface_flux": surface_flux,
    }


def _read_flux_vectors(path: Path, ngroups: int) -> np.ndarray:
    blocks = lcm.read_lcm_ascii(path)
    vectors = [
        np.asarray(block.data, dtype=float)
        for block in blocks
        if block.name is None
        and block.data is not None
        and block.type_code == 2
        and block.trailing
    ]
    if len(vectors) < ngroups:
        raise ValueError(f"{path}: found {len(vectors)} FLUX vectors, expected {ngroups}")
    lengths = {vector.size for vector in vectors[:ngroups]}
    if len(lengths) != 1:
        raise ValueError(f"{path}: inconsistent FLUX vector lengths {lengths}")
    return np.stack(vectors[:ngroups])


def _read_track(path: Path, mesh_dim: int) -> dict[str, object]:
    blocks = lcm.read_lcm_ascii(path)
    track: dict[str, object] = {"path": str(path)}
    for block in blocks:
        if block.name == "STATE-VECTOR" and block.type_code == 1:
            track["state_vector"] = np.asarray(block.data, dtype=int)
        elif block.name == "QFR" and block.type_code == 2:
            track["qfr"] = np.asarray(block.data, dtype=float)
        elif block.name == "R" and block.type_code == 2:
            values = np.asarray(block.data, dtype=float)
            if values.size == 4:
                track["bivcol_r"] = values.reshape(2, 2)
            else:
                track["bivcol_r"] = values
        elif block.name == "V" and block.type_code == 2:
            track["bivcol_v"] = np.asarray(block.data, dtype=float)
        elif block.name == "KN" and block.type_code == 1:
            values = np.asarray(block.data, dtype=int)
            if values.size != mesh_dim * mesh_dim * 7:
                raise ValueError(
                    f"{path}: KN has {values.size} entries, expected "
                    f"{mesh_dim * mesh_dim * 7}"
                )
            track["kn"] = values.reshape(mesh_dim * mesh_dim, 7)
    if "kn" not in track:
        raise ValueError(f"{path}: no KN block found")
    return track


def _reconstruct_face_flux(
    mgxs: dict[str, object],
    currents: dict[str, object],
    flux_vectors: np.ndarray,
    kn: np.ndarray,
) -> dict[str, np.ndarray]:
    mesh_dim = int(mgxs["mesh_dim"])
    ngroups = int(mgxs["ngroups"])
    diffusion = np.asarray(mgxs["diffusion"], dtype=float)
    openmc_volume_flux = np.asarray(currents["volume_flux"], dtype=float)

    donjon_volume_flux = np.zeros((mesh_dim, mesh_dim, ngroups), dtype=float)
    net_current = np.zeros((mesh_dim, mesh_dim, ngroups, 4), dtype=float)
    homogeneous = np.zeros_like(net_current)

    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            element = y_index * mesh_dim + x_index
            ids = kn[element]
            flux_id = int(ids[0])
            if flux_id <= 0:
                raise ValueError(f"KN element {element + 1} has no flux id")
            for group in range(ngroups):
                phi = float(flux_vectors[group, flux_id - 1])
                donjon_volume_flux[y_index, x_index, group] = phi
                currents_out = (
                    0.0 if ids[1] == 0 else -float(flux_vectors[group, ids[1] - 1]),
                    0.0 if ids[2] == 0 else float(flux_vectors[group, ids[2] - 1]),
                    0.0 if ids[3] == 0 else -float(flux_vectors[group, ids[3] - 1]),
                    0.0 if ids[4] == 0 else float(flux_vectors[group, ids[4] - 1]),
                )
                coeff = ASSEMBLY_PITCH / (2.0 * diffusion[y_index, x_index, group])
                for face, current in enumerate(currents_out):
                    net_current[y_index, x_index, group, face] = current
                    homogeneous[y_index, x_index, group, face] = phi - current * coeff

    scale = np.divide(
        openmc_volume_flux,
        donjon_volume_flux,
        out=np.ones_like(openmc_volume_flux),
        where=donjon_volume_flux != 0.0,
    )
    return {
        "donjon_volume_flux": donjon_volume_flux,
        "openmc_volume_flux": openmc_volume_flux,
        "normalization": scale,
        "net_current": net_current,
        "homogeneous_face_flux_raw": homogeneous,
        "homogeneous_face_flux": homogeneous * scale[:, :, :, np.newaxis],
    }


def _current_sanity(
    mgxs: dict[str, object],
    flux_vectors: np.ndarray,
    kn: np.ndarray,
) -> dict[str, float]:
    """Compare mixed-dual current unknowns with a simple two-point gradient."""

    mesh_dim = int(mgxs["mesh_dim"])
    diffusion = np.asarray(mgxs["diffusion"], dtype=float)
    ngroups = int(mgxs["ngroups"])
    donjon_volume_flux = np.zeros((mesh_dim, mesh_dim, ngroups), dtype=float)
    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            flux_id = int(kn[y_index * mesh_dim + x_index, 0])
            if flux_id <= 0:
                continue
            donjon_volume_flux[y_index, x_index] = flux_vectors[:ngroups, flux_id - 1]

    def collect(axis: str) -> tuple[np.ndarray, np.ndarray]:
        stored: list[float] = []
        finite_difference: list[float] = []
        if axis == "x":
            for y_index in range(mesh_dim):
                for x_index in range(mesh_dim - 1):
                    ids = kn[y_index * mesh_dim + x_index]
                    current_id = int(ids[2])
                    if current_id <= 0:
                        continue
                    left = donjon_volume_flux[y_index, x_index]
                    right = donjon_volume_flux[y_index, x_index + 1]
                    diff = 0.5 * (
                        diffusion[y_index, x_index] + diffusion[y_index, x_index + 1]
                    )
                    stored.extend(flux_vectors[:ngroups, current_id - 1])
                    finite_difference.extend(-diff * (right - left) / ASSEMBLY_PITCH)
        elif axis == "y":
            for y_index in range(mesh_dim - 1):
                for x_index in range(mesh_dim):
                    ids = kn[y_index * mesh_dim + x_index]
                    current_id = int(ids[4])
                    if current_id <= 0:
                        continue
                    lower = donjon_volume_flux[y_index, x_index]
                    upper = donjon_volume_flux[y_index + 1, x_index]
                    diff = 0.5 * (
                        diffusion[y_index, x_index] + diffusion[y_index + 1, x_index]
                    )
                    stored.extend(flux_vectors[:ngroups, current_id - 1])
                    finite_difference.extend(-diff * (upper - lower) / ASSEMBLY_PITCH)
        else:
            raise ValueError(f"unsupported axis {axis!r}")
        return np.asarray(stored, dtype=float), np.asarray(finite_difference, dtype=float)

    diagnostics: dict[str, float] = {}
    for axis in ("x", "y"):
        stored, finite_difference = collect(axis)
        nonzero = np.abs(finite_difference) > 0.0
        ratio = np.divide(
            stored,
            finite_difference,
            out=np.full_like(stored, np.nan),
            where=nonzero,
        )
        finite_ratio = ratio[np.isfinite(ratio)]
        sign = np.sign(stored) == np.sign(finite_difference)
        diagnostics[f"current_{axis}_sign_agreement"] = float(np.mean(sign))
        if finite_ratio.size:
            diagnostics[f"current_{axis}_ratio_median"] = float(np.median(finite_ratio))
            diagnostics[f"current_{axis}_ratio_min"] = float(np.min(finite_ratio))
            diagnostics[f"current_{axis}_ratio_max"] = float(np.max(finite_ratio))
        diagnostics[f"current_{axis}_stored_min"] = float(np.min(stored))
        diagnostics[f"current_{axis}_stored_max"] = float(np.max(stored))
        diagnostics[f"current_{axis}_fd_min"] = float(np.min(finite_difference))
        diagnostics[f"current_{axis}_fd_max"] = float(np.max(finite_difference))
    return diagnostics


def _checks(face_flux: np.ndarray, *, prefix: str) -> dict[str, float | int]:
    mismatches = [
        face_flux[:, :-1, :, 1] - face_flux[:, 1:, :, 0],
        face_flux[:-1, :, :, 3] - face_flux[1:, :, :, 2],
    ]
    all_mismatch = np.concatenate([item.reshape(-1) for item in mismatches])
    interior = np.zeros(face_flux.shape[:2] + (4,), dtype=bool)
    for y_index in range(face_flux.shape[0]):
        for x_index in range(face_flux.shape[1]):
            interior[y_index, x_index] = [
                x_index > 0,
                x_index < face_flux.shape[1] - 1,
                y_index > 0,
                y_index < face_flux.shape[0] - 1,
            ]
    interior_mask = np.broadcast_to(interior[:, :, np.newaxis, :], face_flux.shape)
    return {
        f"{prefix}_nonpositive": int(np.count_nonzero(face_flux <= 0.0)),
        f"{prefix}_interior_nonpositive": int(
            np.count_nonzero((face_flux <= 0.0) & interior_mask)
        ),
        f"{prefix}_shared_max_abs_mismatch": float(np.max(np.abs(all_mismatch))),
        f"{prefix}_shared_rms_mismatch": float(np.sqrt(np.mean(all_mismatch**2))),
    }


def _write_output(
    path: Path,
    args: argparse.Namespace,
    mgxs: dict[str, object],
    currents: dict[str, object],
    flux_vectors: np.ndarray,
    track: dict[str, object],
    face_flux: dict[str, np.ndarray],
    checks: dict[str, float | int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["source"] = "DONJON mixed-dual current face-flux reconstruction"
        h5.attrs["mgxs"] = mgxs["path"]
        h5.attrs["currents"] = currents["path"]
        h5.attrs["flux_dump"] = str(args.flux_dump)
        h5.attrs["track_dump"] = str(args.track_dump)
        h5.attrs["formula"] = (
            "phi_face = phi_cell - J_out*h/(2D); J_out from TRIDKN mixed-dual "
            "face-current unknowns; normalized to OpenMC volume flux"
        )
        h5.attrs["reconstruction_method"] = (
            "finite_difference_half_cell_from_mixed_dual_current"
        )
        h5.attrs["face_current_convention"] = (
            "KN faces are X-/X+/Y-/Y+/Z-/Z+; X/Y currents are oriented +x/+y; "
            "J_out changes sign on minus faces"
        )
        h5.attrs["face_area_cm2_unit_height"] = ASSEMBLY_PITCH
        for key, value in checks.items():
            h5.attrs[key] = value
        h5.create_dataset("energy_bounds", data=mgxs["energy_bounds"])
        h5.create_dataset("face_names", data=np.asarray(FACE_NAMES, dtype="S"))
        h5.create_dataset("mixture_names", data=np.asarray(mgxs["mixture_names"], dtype="S"))
        h5.create_dataset("kn", data=track["kn"])
        if "state_vector" in track:
            h5.create_dataset("track_state_vector", data=track["state_vector"])
        if "qfr" in track:
            h5.create_dataset("qfr", data=track["qfr"])
        if "bivcol_r" in track:
            h5.create_dataset("bivcol_r", data=track["bivcol_r"])
        if "bivcol_v" in track:
            h5.create_dataset("bivcol_v", data=track["bivcol_v"])
        h5.create_dataset("flux_vectors", data=flux_vectors)
        for name, values in face_flux.items():
            h5.create_dataset(name, data=values)
        if currents["surface_flux"] is not None:
            surface = np.asarray(currents["surface_flux"], dtype=float)
            h5.create_dataset("openmc_surface_flux", data=surface)
            adf = np.divide(
                surface,
                face_flux["homogeneous_face_flux"],
                out=np.full_like(surface, np.nan),
                where=face_flux["homogeneous_face_flux"] != 0.0,
            )
            h5.create_dataset("adf_candidate", data=adf)


def _print_summary(
    output: Path,
    face_flux: dict[str, np.ndarray],
    checks: dict[str, float | int],
) -> None:
    flux = face_flux["homogeneous_face_flux"]
    print(f"Wrote {output}")
    print(f"homogeneous_face_flux shape: {flux.shape} [mesh_y, mesh_x, group, face]")
    print(
        "face flux diagnostics: "
        f"normalized_nonpositive={checks['normalized_nonpositive']}, "
        f"normalized_interior_nonpositive={checks['normalized_interior_nonpositive']}, "
        "raw_shared_max_abs_mismatch="
        f"{checks['raw_shared_max_abs_mismatch']:.6e}, "
        "normalized_shared_max_abs_mismatch="
        f"{checks['normalized_shared_max_abs_mismatch']:.6e}"
    )
    print(
        "mixed-dual current sanity: "
        f"x_sign={checks['current_x_sign_agreement']:.3f}, "
        f"x_ratio_median={checks['current_x_ratio_median']:.3f}, "
        f"y_sign={checks['current_y_sign_agreement']:.3f}, "
        f"y_ratio_median={checks['current_y_ratio_median']:.3f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())

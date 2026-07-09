"""Build a 2-group C5G7 assembly-wise MGXS file for NSSF/ANM smoke tests.

The production C5G7 payload remains the 7-group assembly-wise HDF5/MCO.  This
utility creates a flux-weighted 2-group derivative only to exercise DONJON's
ADF-aware NSSF path, whose current ANM implementation aborts on two of the
7-group assembly-wise nodal relation matrices.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


ROOT = Path("/Users/wen/dragon-5.1")
DEFAULT_INPUT = ROOT / "Donjon/data/openmc2donjon/c5g7_assembly_p1_adf_production.h5"
DEFAULT_CURRENTS = ROOT / "Donjon/data/openmc2donjon/c5g7_boundary_currents_mu_full.h5"
DEFAULT_OUTPUT = ROOT / "Donjon/data/openmc2donjon/c5g7_validation/c5g7pa_2g_nssf_smoke.h5"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--currents", type=Path, default=DEFAULT_CURRENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--split-index",
        type=int,
        default=4,
        help=(
            "first fine-group index assigned to the low-energy coarse group; "
            "default 4 gives coarse bins [0:4] and [4:7]"
        ),
    )
    args = parser.parse_args()

    condense(args.input, args.currents, args.output, args.split_index)
    return 0


def condense(input_path: Path, currents_path: Path, output_path: Path, split_index: int) -> None:
    with h5py.File(input_path, "r") as src, h5py.File(currents_path, "r") as cur:
        energy_bounds = np.asarray(src["energy_bounds"][:], dtype=float)
        ngroups = int(src.attrs["energy_groups"])
        if not 0 < split_index < ngroups:
            raise ValueError(f"split-index must be between 1 and {ngroups - 1}")
        groups = (np.arange(0, split_index), np.arange(split_index, ngroups))
        volume_flux = np.asarray(cur["volume_flux/average"][:], dtype=float)
        if volume_flux.shape[-1] != ngroups:
            raise ValueError("current-file volume flux group count does not match MGXS")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(output_path, "w") as out:
            _copy_attrs(src, out)
            out.attrs["energy_groups"] = 2
            out.attrs["legendre_order"] = int(src.attrs.get("legendre_order", 0))
            out.attrs["scatter_axes"] = "moment,G_in,G_out"
            out.attrs["condensation"] = "flux_weighted_for_nssf_anm_smoke"
            out.attrs["condensation_source"] = str(input_path)
            out.attrs["condensation_flux_source"] = str(currents_path)
            out.attrs["condensation_split_index"] = split_index
            out.attrs["condensation_groups"] = "[0:%d],[%d:%d]" % (
                split_index,
                split_index,
                ngroups,
            )
            out.create_dataset(
                "energy_bounds",
                data=np.asarray(
                    [energy_bounds[0], energy_bounds[ngroups - split_index], energy_bounds[-1]],
                    dtype=float,
                ),
            )

            src_mixtures = src["mixtures"]
            dst_mixtures = out.create_group("mixtures")
            mesh_dim = int(src.attrs.get("mesh_dimension", round(len(src_mixtures) ** 0.5)))
            diagnostics = []
            for mix_index, name in enumerate(src_mixtures):
                y_index = mix_index // mesh_dim
                x_index = mix_index % mesh_dim
                weights = np.asarray(volume_flux[y_index, x_index, :], dtype=float)
                dst = dst_mixtures.create_group(name)
                _copy_attrs(src_mixtures[name], dst)

                diag = _condense_mixture(src_mixtures[name], dst, groups, weights)
                diagnostics.append((name, *diag))

            diag_dtype = np.dtype(
                [
                    ("name", "S32"),
                    ("max_row_balance_abs", "f8"),
                    ("max_anm_eig_imag", "f8"),
                ]
            )
            out.create_dataset(
                "nssf_smoke_diagnostics",
                data=np.asarray(
                    [
                        (name.encode(), row_balance, eig_imag)
                        for name, row_balance, eig_imag in diagnostics
                    ],
                    dtype=diag_dtype,
                ),
            )

    print(f"wrote {output_path}")
    for name, row_balance, eig_imag in diagnostics:
        print(
            f"{name}: max_row_balance_abs={row_balance:.3e} "
            f"max_anm_eig_imag={eig_imag:.3e}"
        )


def _condense_mixture(
    src, dst, groups: tuple[np.ndarray, np.ndarray], weights: np.ndarray
) -> tuple[float, float]:
    total = np.asarray(src["total"][:], dtype=float)
    absorption = np.asarray(src["absorption"][:], dtype=float)
    fission = np.asarray(src["fission"][:], dtype=float)
    nu_fission = np.asarray(src["nu_fission"][:], dtype=float)
    chi = np.asarray(src["chi"][:], dtype=float)
    scatter = np.asarray(src["scatter_matrix"][:], dtype=float)
    transport_total = np.asarray(src["transport_total"][:], dtype=float)

    coarse_total = _condense_vector(total, groups, weights)
    coarse_absorption = _condense_vector(absorption, groups, weights)
    coarse_fission = _condense_vector(fission, groups, weights)
    coarse_nu_fission = _condense_vector(nu_fission, groups, weights)
    coarse_transport_total = _condense_vector(transport_total, groups, weights)
    coarse_scatter = _condense_scatter(scatter, groups, weights)
    coarse_chi = np.asarray([np.sum(chi[group]) for group in groups], dtype=float)
    if np.sum(coarse_chi) > 0.0:
        coarse_chi /= np.sum(coarse_chi)

    dst.create_dataset("total", data=coarse_total)
    dst.create_dataset("absorption", data=coarse_absorption)
    dst.create_dataset("fission", data=coarse_fission)
    dst.create_dataset("nu_fission", data=coarse_nu_fission)
    dst.create_dataset("chi", data=coarse_chi)
    dst.create_dataset("transport_total", data=coarse_transport_total)
    dst.create_dataset("scatter_matrix", data=coarse_scatter)

    if "adf" in src:
        adf = np.asarray(src["adf"][:], dtype=float)
        coarse_adf = np.vstack([_condense_vector(row, groups, weights) for row in adf])
        adf_ds = dst.create_dataset("adf", data=coarse_adf)
        for key, value in src["adf"].attrs.items():
            adf_ds.attrs[key] = value

    row_balance = coarse_total - coarse_absorption - coarse_scatter[0].sum(axis=1)
    eig_imag = _max_anm_eig_imag(
        coarse_total,
        coarse_transport_total,
        coarse_scatter[0],
        coarse_chi,
        coarse_nu_fission,
    )
    return float(np.max(np.abs(row_balance))), eig_imag


def _condense_vector(
    values: np.ndarray, groups: tuple[np.ndarray, np.ndarray], weights: np.ndarray
) -> np.ndarray:
    out = []
    for group in groups:
        denom = float(np.sum(weights[group]))
        if denom <= 0.0:
            raise ValueError(f"non-positive flux weight for fine groups {group}")
        out.append(float(np.sum(weights[group] * values[group]) / denom))
    return np.asarray(out, dtype=float)


def _condense_scatter(
    scatter: np.ndarray, groups: tuple[np.ndarray, np.ndarray], weights: np.ndarray
) -> np.ndarray:
    moments = []
    for moment in scatter:
        coarse = np.zeros((2, 2), dtype=float)
        for from_coarse, from_group in enumerate(groups):
            denom = float(np.sum(weights[from_group]))
            if denom <= 0.0:
                raise ValueError(f"non-positive flux weight for fine groups {from_group}")
            for to_coarse, to_group in enumerate(groups):
                block = moment[np.ix_(from_group, to_group)]
                coarse[from_coarse, to_coarse] = float(
                    np.sum(weights[from_group, np.newaxis] * block) / denom
                )
        moments.append(coarse)
    return np.stack(moments)


def _max_anm_eig_imag(
    total: np.ndarray,
    transport_total: np.ndarray,
    scatter_from_to: np.ndarray,
    chi: np.ndarray,
    nu_fission: np.ndarray,
) -> float:
    keff = 1.2080752850
    diff = 1.0 / (3.0 * transport_total)
    scatter_to_from = scatter_from_to.T
    removal = total - np.diag(scatter_to_from)
    matrix = np.empty((2, 2), dtype=float)
    for ig in range(2):
        for jg in range(2):
            if ig == jg:
                value = chi[ig] * nu_fission[ig] / keff - removal[ig]
            else:
                value = chi[ig] * nu_fission[jg] / keff + scatter_to_from[ig, jg]
            matrix[ig, jg] = value / diff[ig]
    return float(np.max(np.abs(np.linalg.eigvals(matrix).imag)))


def _copy_attrs(src, dst) -> None:
    for key, value in src.attrs.items():
        dst.attrs[key] = value


if __name__ == "__main__":
    raise SystemExit(main())

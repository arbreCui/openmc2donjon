"""Build minimal DRAGON/DONJON L_MULTICOMPO objects from OpenMC MGXS data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from . import lcm_ascii as lcm
from .scatter import dense_moments_to_triplets


DEFAULT_ROOT_NAME = "CPO"


@dataclass
class MixtureXS:
    name: str
    total: np.ndarray
    absorption: np.ndarray
    fission: np.ndarray
    nu_fission: np.ndarray
    chi: np.ndarray
    scatter_matrix: np.ndarray
    fissionable: bool = False
    volume: float = 1.0
    temperature: float = 0.0
    inverse_velocity: np.ndarray | None = None
    transport_total: np.ndarray | None = None
    flux_weight: np.ndarray | None = None
    h_factor: np.ndarray | None = None
    adf: dict[str, np.ndarray] | None = None

    @property
    def ngroups(self) -> int:
        return int(self.total.size)

    @property
    def nmoments(self) -> int:
        return int(self.scatter_matrix.shape[0])


def convert_mgxs_hdf5(
    input_h5: str | Path,
    output_path: str | Path,
    *,
    root_name: str = DEFAULT_ROOT_NAME,
    comment: str | None = None,
    burnup: float | None = None,
    h_factor_default: float | None = None,
    mixture_names: Sequence[str] | None = None,
) -> None:
    """Read an OpenMC MGXS HDF5 dump and write a L_MULTICOMPO ASCII file."""

    mixtures, energy_bounds = read_mgxs_hdf5(
        input_h5,
        h_factor_default=h_factor_default,
    )
    mixtures = _select_mixtures(mixtures, mixture_names)
    if comment is None:
        comment = f"OpenMC MGXS conversion from {Path(input_h5).name}"
    write_multicompo(
        mixtures,
        energy_bounds,
        output_path,
        root_name=root_name,
        comment=comment,
        burnup=burnup,
    )


def _select_mixtures(
    mixtures: list[MixtureXS],
    names: Sequence[str] | None,
) -> list[MixtureXS]:
    if not names:
        return mixtures
    by_name = {mix.name: mix for mix in mixtures}
    missing = [name for name in names if name not in by_name]
    if missing:
        available = ", ".join(mix.name for mix in mixtures)
        raise ValueError(
            f"unknown mixture name(s): {', '.join(missing)}; available: {available}"
        )
    return [by_name[name] for name in names]


def read_mgxs_hdf5(
    input_h5: str | Path,
    *,
    h_factor_default: float | None = None,
) -> tuple[list[MixtureXS], np.ndarray]:
    """Read the converter-facing OpenMC MGXS HDF5 schema."""

    import h5py

    with h5py.File(input_h5, "r") as h5:
        energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
        ngroups = int(h5.attrs.get("energy_groups", len(energy_bounds) - 1))
        legendre_order = h5.attrs.get("legendre_order")
        expected_moments = None if legendre_order is None else int(legendre_order) + 1
        if len(energy_bounds) != ngroups + 1:
            raise ValueError("energy_bounds length must be energy_groups + 1")

        mixtures: list[MixtureXS] = []
        mix_group = h5["mixtures"]
        for name in mix_group:
            g = mix_group[name]
            scatter = _scatter_matrix_from_hdf5(
                g,
                ngroups,
                str(name),
                expected_moments=expected_moments,
            )

            total = _vector(g["total"][:], ngroups, name, "total")
            transport_total = _transport_total_from_hdf5(g, scatter, total, ngroups, str(name))
            absorption = _optional_vector(g, "absorption", ngroups)
            fission = _optional_vector(g, "fission", ngroups)
            nu_fission = _optional_vector(g, "nu_fission", ngroups)
            chi = _optional_vector(g, "chi", ngroups)
            inverse_velocity = _inverse_velocity_from_hdf5(g, ngroups, str(name))
            fission_attr = bool(g.attrs.get("fissionable", True))
            has_fission_source = (
                np.sum(np.abs(nu_fission)) > 1e-12 and np.sum(np.abs(chi)) > 1e-12
            )
            fissionable = fission_attr and has_fission_source
            if not fissionable:
                fission = np.zeros(ngroups, dtype=float)
                nu_fission = np.zeros(ngroups, dtype=float)
                chi = np.zeros(ngroups, dtype=float)

            mixtures.append(
                MixtureXS(
                    name=str(name),
                    total=total,
                    absorption=absorption,
                    fission=fission,
                    nu_fission=nu_fission,
                    chi=chi,
                    scatter_matrix=scatter,
                    fissionable=fissionable,
                    volume=float(g.attrs.get("volume", 1.0)),
                    inverse_velocity=inverse_velocity,
                    transport_total=transport_total,
                    h_factor=_h_factor_from_hdf5(
                        g,
                        ngroups,
                        str(name),
                        default=h_factor_default,
                    ),
                    adf=_adf_from_hdf5(g, ngroups, str(name)),
                )
            )

    if not mixtures:
        raise ValueError("MGXS HDF5 contains no mixtures")
    return mixtures, energy_bounds


def write_multicompo(
    mixtures: Iterable[MixtureXS],
    energy_bounds: np.ndarray | list[float],
    output_path: str | Path,
    *,
    root_name: str = DEFAULT_ROOT_NAME,
    comment: str = "OpenMC MGXS conversion",
    burnup: float | None = None,
) -> None:
    """Write a minimal single-state L_MULTICOMPO ASCII object."""

    mix_list = list(mixtures)
    if not mix_list:
        raise ValueError("at least one mixture is required")
    energy = np.asarray(energy_bounds, dtype=float)
    ngroups = mix_list[0].ngroups
    if energy.shape != (ngroups + 1,):
        raise ValueError("energy_bounds length must be ngroups + 1")
    for mix in mix_list:
        _validate_mixture(mix, ngroups)
    _validate_adf_layout(mix_list)

    blocks = build_multicompo_blocks(
        mix_list,
        energy,
        root_name=root_name,
        comment=comment,
        burnup=burnup,
    )
    lcm.write_lcm_ascii(blocks, output_path)


def build_multicompo_blocks(
    mixtures: list[MixtureXS],
    energy_bounds: np.ndarray,
    *,
    root_name: str,
    comment: str,
    burnup: float | None = None,
) -> list[lcm.LcmBlock]:
    ngroups = mixtures[0].ngroups
    for mix in mixtures:
        _validate_mixture(mix, ngroups)
    _validate_adf_layout(mixtures)
    maxcal = 1
    energy_desc = np.asarray(energy_bounds, dtype=float)[::-1]

    npar = 1 if burnup is not None else 0
    blocks: list[lcm.LcmBlock] = [
        lcm.string_block(1, "SIGNATURE", "L_MULTICOMPO", width=12),
        lcm.block(1, root_name[:72], 0, count=-1),
        lcm.string_block(2, "COMMENT", comment, width=80),
        lcm.block(2, "GLOBAL", 0, count=-1),
        *_global_parameter_blocks(3, burnup),
        lcm.control(-3),
        lcm.block(
            2,
            "STATE-VECTOR",
            1,
            _multicompo_state_vector(
                len(mixtures),
                ngroups,
                maxcal,
                _multicompo_adf_type(mixtures),
                npar=npar,
            ),
        ),
        lcm.block(2, "MIXTURES", 10, count=len(mixtures)),
    ]

    for mix_index, mix in enumerate(mixtures, start=1):
        blocks.extend(_mixture_blocks(mix_index, mix, energy_desc, maxcal))

    blocks.extend([lcm.control(-2), lcm.control(-1)])
    return blocks


def _global_parameter_blocks(level: int, burnup: float | None) -> list[lcm.LcmBlock]:
    if burnup is None:
        return [
            lcm.block(level, "PARCAD", 1, [1]),
            lcm.block(level, "PARPAD", 1, [1]),
        ]

    parkey, parkey_count = lcm.pack_fixed_strings(["BURN"], width=12)
    partyp, partyp_count = lcm.pack_fixed_strings(["VALU"], width=4)
    parfmt, parfmt_count = lcm.pack_fixed_strings(["REAL"], width=8)
    return [
        lcm.block(level, "PARKEY", 3, parkey, count=parkey_count),
        lcm.block(level, "PARTYP", 3, partyp, count=partyp_count),
        lcm.block(level, "PARFMT", 3, parfmt, count=parfmt_count),
        lcm.block(level, "PARCAD", 1, [1, 1]),
        lcm.block(level, "PARPAD", 1, [1, 1]),
        lcm.block(level, "pval00000001", 2, [float(burnup)]),
        lcm.block(level, "NVALUE", 1, [1]),
    ]


def _mixture_blocks(
    mix_index: int, mix: MixtureXS, energy_desc: np.ndarray, maxcal: int
) -> list[lcm.LcmBlock]:
    blocks: list[lcm.LcmBlock] = [
        lcm.list_item(3, mix_index),
        lcm.block(4, "CALCULATIONS", 10, count=maxcal),
        lcm.list_item(5, 1),
        lcm.block(6, "ISOTOPESLIST", 10, count=1),
        lcm.list_item(7, 1),
    ]
    blocks.extend(_isotope_blocks(8, mix))
    blocks.extend(
        [
            lcm.control(-8),
            *_macrolib_blocks(6, mix),
            *_library_blocks(6, mix, energy_desc),
            lcm.control(-6),
            lcm.block(4, "TREE", 0, count=-1),
            lcm.block(5, "NVP", 1, [1, 20]),
            lcm.block(5, "NCALS", 1, [1]),
            lcm.block(5, "DEBARB", 1, [2, 1]),
            lcm.block(5, "ARBVAL", 1, [0]),
            lcm.block(5, "ORIGIN", 1, [0]),
            lcm.control(-5),
            lcm.control(-4),
        ]
    )
    return blocks


def _isotope_blocks(level: int, mix: MixtureXS) -> list[lcm.LcmBlock]:
    ngroups = mix.ngroups
    inverse_velocity = (
        np.zeros(ngroups, dtype=float)
        if mix.inverse_velocity is None
        else np.asarray(mix.inverse_velocity, dtype=float)
    )
    transport_total = (
        np.asarray(mix.total, dtype=float)
        if mix.transport_total is None
        else np.asarray(mix.transport_total, dtype=float)
    )
    flux_weight = (
        np.ones(ngroups, dtype=float)
        if mix.flux_weight is None
        else np.asarray(mix.flux_weight, dtype=float)
    )

    blocks: list[lcm.LcmBlock] = [
        lcm.block(level, "NWT0", 2, flux_weight),
        lcm.block(level, "NTOT0", 2, mix.total),
        lcm.block(level, "OVERV", 2, inverse_velocity),
        lcm.block(level, "STRD", 2, transport_total),
    ]

    if mix.fissionable:
        blocks.extend(
            [
                lcm.block(level, "NUSIGF", 2, mix.nu_fission),
                lcm.block(level, "NFTOT", 2, mix.fission),
                lcm.block(level, "CHI", 2, mix.chi),
            ]
        )

    if mix.h_factor is not None:
        blocks.append(lcm.block(level, "H-FACTOR", 2, mix.h_factor))

    for ell, triplet in enumerate(dense_moments_to_triplets(mix.scatter_matrix)):
        tag = f"{ell:02d}"
        sigs = np.asarray(mix.scatter_matrix[ell], dtype=float).sum(axis=1)
        blocks.extend(
            [
                lcm.block(level, f"SIGS{tag}", 2, sigs),
                lcm.block(level, f"NJJS{tag}", 1, triplet.njjs),
                lcm.block(level, f"IJJS{tag}", 1, triplet.ijjs),
                lcm.block(level, f"SCAT{tag}", 2, triplet.scat),
            ]
        )

    blocks.extend(
        [
            lcm.block(level, "SCAT-SAVED", 1, [1] * mix.nmoments),
            lcm.string_block(level, "ALIAS", "*MAC*RES", width=12),
        ]
    )
    return blocks


def _macrolib_blocks(level: int, mix: MixtureXS) -> list[lcm.LcmBlock]:
    if not mix.adf:
        return []

    names = tuple(mix.adf)
    packed_names, name_count = lcm.pack_fixed_strings(names, width=8)
    blocks: list[lcm.LcmBlock] = [
        lcm.block(level, "MACROLIB", 0, count=-1),
        lcm.block(level + 1, "ADF", 0, count=-1),
        lcm.block(level + 2, "NTYPE", 1, [len(names)]),
        lcm.block(level + 2, "HADF", 3, packed_names, count=name_count),
    ]
    for name in names:
        blocks.append(lcm.block(level + 2, name, 2, mix.adf[name]))
    blocks.extend([lcm.control(-(level + 2)), lcm.control(-(level + 1))])
    return blocks


def _library_blocks(level: int, mix: MixtureXS, energy_desc: np.ndarray) -> list[lcm.LcmBlock]:
    deltau = np.log(energy_desc[:-1] / energy_desc[1:])
    return [
        lcm.string_block(level, "SIGNATURE", "L_LIBRARY", width=12),
        lcm.block(
            level,
            "STATE-VECTOR",
            1,
            _library_state_vector(mix.ngroups, mix.nmoments, _mixture_adf_type(mix)),
        ),
        lcm.block(level, "ISOTOPESMIX", 1, [1]),
        lcm.string_block(level, "ISOTOPESUSED", "*MAC*RES", width=12),
        lcm.string_block(level, "ISOTOPERNAME", "*MAC*RES", width=12),
        lcm.block(level, "ISOTOPESDENS", 2, [1.0]),
        lcm.block(level, "ISOTOPESTYPE", 1, [1]),
        lcm.block(level, "ISOTOPESTODO", 1, [1]),
        lcm.block(level, "ISOTOPESVOL", 2, [mix.volume]),
        lcm.block(level, "ISOTOPESTEMP", 2, [mix.temperature]),
        lcm.block(level, "MIXTURESVOL", 2, [mix.volume]),
        lcm.block(level, "K-EFFECTIVE", 2, [1.0]),
        lcm.block(level, "K-INFINITY", 2, [1.0]),
        lcm.block(level, "ENERGY", 2, energy_desc),
        lcm.block(level, "DELTAU", 2, deltau),
    ]


def _multicompo_state_vector(
    nmix: int, ngroups: int, maxcal: int, adf_type: int = 0, npar: int = 0
) -> list[int]:
    state = [0] * 40
    state[0] = int(nmix)
    state[1] = int(ngroups)
    state[2] = 1
    state[3] = int(maxcal)
    state[4] = int(npar)
    state[9] = 1
    state[11] = 2006
    state[15] = int(adf_type)
    return state


def _library_state_vector(ngroups: int, nmoments: int, adf_type: int = 0) -> list[int]:
    state = [0] * 40
    state[0] = 1
    state[1] = 1
    state[2] = int(ngroups)
    state[3] = int(nmoments)
    state[13] = 1
    state[23] = int(adf_type)
    return state


def _multicompo_adf_type(mixtures: list[MixtureXS]) -> int:
    return 3 if any(_mixture_adf_type(mix) == 3 for mix in mixtures) else 0


def _mixture_adf_type(mix: MixtureXS) -> int:
    return 3 if mix.adf else 0


def _optional_vector(group, name: str, ngroups: int) -> np.ndarray:
    if name not in group:
        return np.zeros(ngroups, dtype=float)
    return _vector(group[name][:], ngroups, group.name, name)


def _inverse_velocity_from_hdf5(group, ngroups: int, mix_name: str) -> np.ndarray | None:
    for name in ("inverse_velocity", "inverse-velocity", "OVERV", "overv"):
        if name in group:
            return _vector(group[name][:], ngroups, mix_name, name)
    return None


def _transport_total_from_hdf5(
    group,
    scatter: np.ndarray,
    total: np.ndarray,
    ngroups: int,
    mix_name: str,
) -> np.ndarray | None:
    if "transport_total" in group:
        transport_total = _vector(group["transport_total"][:], ngroups, mix_name, "transport_total")
    elif scatter.shape[0] > 1:
        transport_total = total - scatter[1].sum(axis=1)
    else:
        return None

    if np.any(transport_total <= 0.0):
        raise ValueError(
            f"mixture {mix_name}: transport_total must be positive in every group"
        )
    return np.asarray(transport_total, dtype=float)


def _adf_from_hdf5(group, ngroups: int, mix_name: str) -> dict[str, np.ndarray] | None:
    for name in ("adf", "ADF", "discontinuity_factors"):
        if name not in group:
            continue
        obj = group[name]
        if hasattr(obj, "keys"):
            out: dict[str, np.ndarray] = {}
            for face_name in obj:
                out[_adf_name(str(face_name), mix_name)] = _vector(
                    obj[face_name][:], ngroups, mix_name, f"{name}/{face_name}"
                )
            return out or None

        values = np.asarray(obj[:], dtype=float)
        names = _adf_names_from_attrs(obj, values)
        if values.ndim == 1:
            return {names[0]: _vector(values, ngroups, mix_name, name)}
        if values.ndim == 2:
            if values.shape[1] != ngroups:
                raise ValueError(
                    f"mixture {mix_name}: {name} must have shape (N, {ngroups})"
                )
            if len(names) != values.shape[0]:
                raise ValueError(
                    f"mixture {mix_name}: {name} has {values.shape[0]} ADF rows "
                    f"but {len(names)} names"
                )
            return {
                _adf_name(face_name, mix_name): _vector(
                    values[i], ngroups, mix_name, f"{name}/{face_name}"
                )
                for i, face_name in enumerate(names)
            }
        raise ValueError(f"mixture {mix_name}: {name} must be 1D, 2D, or a group")
    return None


def _h_factor_from_hdf5(
    group,
    ngroups: int,
    mix_name: str,
    *,
    default: float | None,
) -> np.ndarray | None:
    for name in (
        "h_factor",
        "H-FACTOR",
        "H_FACTOR",
        "kappa_fission",
        "kappa_fission_xs",
        "kappa_fission_cross_section",
    ):
        if name in group:
            return _vector(group[name][:], ngroups, mix_name, name)
    if default is None:
        return None
    return np.full(ngroups, float(default), dtype=float)


def _adf_names_from_attrs(dataset, values: np.ndarray) -> list[str]:
    for key in ("names", "face_names", "adf_names"):
        if key in dataset.attrs:
            raw = dataset.attrs[key]
            if isinstance(raw, (bytes, str)):
                return [_attr_text(raw) or ""]
            return [_attr_text(value) or "" for value in raw]
    if values.ndim == 1:
        return ["FD_B"]
    return [f"FD_{i + 1:05d}" for i in range(values.shape[0])]


def _adf_name(name: str, mix_name: str) -> str:
    if not name:
        raise ValueError(f"mixture {mix_name}: ADF name must not be empty")
    if len(name) > 8:
        raise ValueError(
            f"mixture {mix_name}: ADF name {name!r} is longer than 8 characters"
        )
    return name


def _validate_adf_layout(mixtures: list[MixtureXS]) -> None:
    adf_names = [tuple(mix.adf or {}) for mix in mixtures]
    first = adf_names[0]
    if not first:
        if any(adf_names):
            raise ValueError("ADF data must be present for either all mixtures or none")
        return
    if any(not names for names in adf_names):
        raise ValueError("ADF data must be present for either all mixtures or none")
    for mix, names in zip(mixtures, adf_names, strict=True):
        if names != first:
            raise ValueError(
                f"mixture {mix.name}: ADF names {names!r} do not match "
                f"the first mixture ADF names {first!r}"
            )


def _scatter_matrix_from_hdf5(
    group,
    ngroups: int,
    mix_name: str,
    *,
    expected_moments: int | None,
) -> np.ndarray:
    raw = np.asarray(group["scatter_matrix"][:], dtype=float)
    if raw.ndim == 2:
        scatter = raw[np.newaxis, :, :]
    elif raw.ndim == 3:
        scatter = _normalise_scatter_axes(
            raw,
            ngroups,
            mix_name,
            expected_moments=expected_moments,
            axes=_attr_text(group.attrs.get("scatter_axes"))
            or _attr_text(group.attrs.get("axes")),
        )
    else:
        raise ValueError(f"mixture {mix_name}: scatter_matrix must be 2D or 3D")

    if scatter.shape[1:] != (ngroups, ngroups):
        raise ValueError(
            f"mixture {mix_name}: scatter_matrix shape {scatter.shape} "
            f"is not compatible with {ngroups} groups"
        )
    if expected_moments is not None and scatter.shape[0] != expected_moments:
        raise ValueError(
            f"mixture {mix_name}: scatter_matrix has {scatter.shape[0]} moments, "
            f"expected {expected_moments} from legendre_order"
        )
    return np.ascontiguousarray(scatter, dtype=float)


def _normalise_scatter_axes(
    raw: np.ndarray,
    ngroups: int,
    mix_name: str,
    *,
    expected_moments: int | None,
    axes: str | None,
) -> np.ndarray:
    if axes is not None:
        normalized = axes.lower().replace(" ", "").replace("_", "")
        moment_first = {
            "moment,from,to",
            "moment,in,out",
            "moment,gin,gout",
            "legendre,from,to",
            "legendre,gin,gout",
        }
        moment_last = {
            "from,to,moment",
            "in,out,moment",
            "gin,gout,moment",
            "from,to,legendre",
            "gin,gout,legendre",
        }
        if normalized in moment_first:
            return raw
        if normalized in moment_last:
            return np.moveaxis(raw, -1, 0)
        raise ValueError(
            f"mixture {mix_name}: unsupported scatter_axes={axes!r}; "
            "expected 'moment,from,to' or 'from,to,moment'"
        )

    moment_first_shape = raw.shape[1:] == (ngroups, ngroups)
    moment_last_shape = raw.shape[:2] == (ngroups, ngroups)

    if expected_moments is not None:
        first_matches = moment_first_shape and raw.shape[0] == expected_moments
        last_matches = moment_last_shape and raw.shape[2] == expected_moments
        if first_matches and not last_matches:
            return raw
        if last_matches and not first_matches:
            return np.moveaxis(raw, -1, 0)
        if first_matches and last_matches:
            raise ValueError(
                f"mixture {mix_name}: ambiguous scatter_matrix shape {raw.shape}; "
                "set scatter_axes='moment,from,to' or 'from,to,moment'"
            )

    if moment_first_shape and not moment_last_shape:
        return raw
    if moment_last_shape and not moment_first_shape:
        return np.moveaxis(raw, -1, 0)

    raise ValueError(
        f"mixture {mix_name}: scatter_matrix shape {raw.shape} is not compatible "
        f"with {ngroups} groups"
    )


def _attr_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _vector(values: np.ndarray, ngroups: int, mix_name: str, dataset: str) -> np.ndarray:
    out = np.asarray(values, dtype=float).reshape(-1)
    if out.shape != (ngroups,):
        raise ValueError(f"{mix_name}: {dataset} must have shape ({ngroups},)")
    return out


def _validate_mixture(mix: MixtureXS, ngroups: int) -> None:
    for field in ("total", "absorption", "fission", "nu_fission", "chi"):
        values = np.asarray(getattr(mix, field), dtype=float).reshape(-1)
        if values.shape != (ngroups,):
            raise ValueError(f"mixture {mix.name}: {field} must have {ngroups} values")
    scatter = np.asarray(mix.scatter_matrix, dtype=float)
    if scatter.ndim != 3 or scatter.shape[1:] != (ngroups, ngroups):
        raise ValueError(
            f"mixture {mix.name}: scatter_matrix must have shape "
            f"[moment, {ngroups}, {ngroups}]"
        )
    if mix.adf:
        for name, values in mix.adf.items():
            _adf_name(name, mix.name)
            values = np.asarray(values, dtype=float).reshape(-1)
            if values.shape != (ngroups,):
                raise ValueError(
                    f"mixture {mix.name}: ADF {name!r} must have {ngroups} values"
                )
    if mix.h_factor is not None:
        values = np.asarray(mix.h_factor, dtype=float).reshape(-1)
        if values.shape != (ngroups,):
            raise ValueError(
                f"mixture {mix.name}: h_factor must have {ngroups} values"
            )

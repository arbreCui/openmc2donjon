"""Build minimal DRAGON/DONJON L_MULTICOMPO objects from OpenMC MGXS data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from . import lcm_ascii as lcm
from .constants import (
    DONJON_ADF_NAME_WIDTH,
    DONJON_COMMENT_WIDTH,
    DONJON_MACRO_NAME_WIDTH,
    DONJON_OBJECT_NAME_WIDTH,
    DONJON_PARAMETER_FORMAT_WIDTH,
    DONJON_PARAMETER_KEY_WIDTH,
    DONJON_PARAMETER_TYPE_WIDTH,
    DONJON_SIGNATURE_WIDTH,
)
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
    sph: np.ndarray | None = None

    @property
    def ngroups(self) -> int:
        return int(self.total.size)

    @property
    def nmoments(self) -> int:
        return int(self.scatter_matrix.shape[0])


@dataclass
class MixtureHistory:
    name: str
    calculations: list[MixtureXS]

    @property
    def nstates(self) -> int:
        return len(self.calculations)


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

    histories, energy_bounds, burnup_values = read_mgxs_hdf5_histories(
        input_h5,
        h_factor_default=h_factor_default,
    )
    histories = _select_mixture_histories(histories, mixture_names)
    if comment is None:
        comment = f"OpenMC MGXS conversion from {Path(input_h5).name}"
    if any(history.nstates > 1 for history in histories):
        if burnup is not None:
            raise ValueError("--burnup cannot override a multi-state HDF5 burnup axis")
        write_multicompo_histories(
            histories,
            energy_bounds,
            output_path,
            root_name=root_name,
            comment=comment,
            burnup_values=burnup_values,
        )
    else:
        write_multicompo(
            [history.calculations[0] for history in histories],
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


def _select_mixture_histories(
    histories: list[MixtureHistory],
    names: Sequence[str] | None,
) -> list[MixtureHistory]:
    if not names:
        return histories
    by_name = {history.name: history for history in histories}
    missing = [name for name in names if name not in by_name]
    if missing:
        available = ", ".join(history.name for history in histories)
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

    histories, energy_bounds, _burnup_values = read_mgxs_hdf5_histories(
        input_h5,
        h_factor_default=h_factor_default,
    )
    if any(history.nstates != 1 for history in histories):
        raise ValueError("MGXS HDF5 contains multiple state points")
    return [history.calculations[0] for history in histories], energy_bounds


def read_mgxs_hdf5_histories(
    input_h5: str | Path,
    *,
    h_factor_default: float | None = None,
) -> tuple[list[MixtureHistory], np.ndarray, np.ndarray | None]:
    """Read one-state or burnup-axis MGXS HDF5 data."""

    import h5py

    with h5py.File(input_h5, "r") as h5:
        energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
        ngroups = int(h5.attrs.get("energy_groups", len(energy_bounds) - 1))
        legendre_order = h5.attrs.get("legendre_order")
        expected_moments = None if legendre_order is None else int(legendre_order) + 1
        if len(energy_bounds) != ngroups + 1:
            raise ValueError("energy_bounds length must be energy_groups + 1")

        burnup_values = _burnup_values_from_hdf5(h5)
        histories: list[MixtureHistory] = []
        mix_group = h5["mixtures"]
        for name in mix_group:
            g = mix_group[name]
            if "states" in g:
                states_group = g["states"]
                states = [
                    _mixture_from_hdf5_group(
                        states_group[state_name],
                        ngroups,
                        str(name),
                        expected_moments=expected_moments,
                        h_factor_default=h_factor_default,
                        parent_attrs=g.attrs,
                    )
                    for state_name in _sorted_state_names(states_group)
                ]
            else:
                states = [
                    _mixture_from_hdf5_group(
                        g,
                        ngroups,
                        str(name),
                        expected_moments=expected_moments,
                        h_factor_default=h_factor_default,
                        parent_attrs=None,
                    )
                ]
            histories.append(MixtureHistory(name=str(name), calculations=states))

    if not histories:
        raise ValueError("MGXS HDF5 contains no mixtures")
    _validate_histories(histories, burnup_values)
    return histories, energy_bounds, burnup_values


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
    _validate_sph_layout(mix_list)

    blocks = build_multicompo_blocks(
        mix_list,
        energy,
        root_name=root_name,
        comment=comment,
        burnup=burnup,
    )
    lcm.write_lcm_ascii(blocks, output_path)


def write_multicompo_histories(
    histories: Iterable[MixtureHistory],
    energy_bounds: np.ndarray | list[float],
    output_path: str | Path,
    *,
    root_name: str = DEFAULT_ROOT_NAME,
    comment: str = "OpenMC MGXS conversion",
    burnup_values: Sequence[float] | np.ndarray | None = None,
) -> None:
    """Write a MULTICOMPO object with multiple calculations per mixture."""

    history_list = list(histories)
    if not history_list:
        raise ValueError("at least one mixture history is required")
    burnup_axis = None if burnup_values is None else np.asarray(burnup_values, dtype=float)
    _validate_histories(history_list, burnup_axis)
    energy = np.asarray(energy_bounds, dtype=float)
    ngroups = history_list[0].calculations[0].ngroups
    if energy.shape != (ngroups + 1,):
        raise ValueError("energy_bounds length must be ngroups + 1")

    blocks = build_multicompo_history_blocks(
        history_list,
        energy,
        root_name=root_name,
        comment=comment,
        burnup_values=burnup_values,
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
    histories = [MixtureHistory(name=mix.name, calculations=[mix]) for mix in mixtures]
    burnup_values = None if burnup is None else [float(burnup)]
    return build_multicompo_history_blocks(
        histories,
        energy_bounds,
        root_name=root_name,
        comment=comment,
        burnup_values=burnup_values,
    )


def build_multicompo_history_blocks(
    histories: list[MixtureHistory],
    energy_bounds: np.ndarray,
    *,
    root_name: str,
    comment: str,
    burnup_values: Sequence[float] | np.ndarray | None = None,
) -> list[lcm.LcmBlock]:
    if not histories:
        raise ValueError("at least one mixture history is required")
    if not histories[0].calculations:
        raise ValueError("mixture histories must contain at least one calculation")
    mixtures = [history.calculations[0] for history in histories]
    ngroups = mixtures[0].ngroups
    all_calculations = [
        mix for history in histories for mix in history.calculations
    ]
    for mix in all_calculations:
        _validate_mixture(mix, ngroups)
    _validate_adf_layout(all_calculations)
    _validate_sph_layout(all_calculations)
    _validate_histories(histories, None if burnup_values is None else np.asarray(burnup_values))
    nstates = histories[0].nstates
    maxcal = nstates
    energy_desc = np.asarray(energy_bounds, dtype=float)[::-1]

    burnup_axis = None if burnup_values is None else np.asarray(burnup_values, dtype=float)
    npar = 1 if burnup_axis is not None else 0
    validated_root_name = _validate_root_name(root_name)
    blocks: list[lcm.LcmBlock] = [
        lcm.string_block(
            1,
            "SIGNATURE",
            "L_MULTICOMPO",
            width=DONJON_SIGNATURE_WIDTH,
        ),
        lcm.block(1, validated_root_name, 0, count=-1),
        lcm.string_block(
            2,
            "COMMENT",
            comment,
            width=DONJON_COMMENT_WIDTH,
            truncate=True,
        ),
        lcm.block(2, "GLOBAL", 0, count=-1),
        *_global_parameter_blocks(3, burnup_axis),
        lcm.control(-3),
        lcm.block(
            2,
            "STATE-VECTOR",
            1,
            _multicompo_state_vector(
                len(histories),
                ngroups,
                maxcal,
                _multicompo_adf_type(all_calculations),
                npar=npar,
            ),
        ),
        lcm.block(2, "MIXTURES", 10, count=len(histories)),
    ]

    for mix_index, history in enumerate(histories, start=1):
        blocks.extend(
            _mixture_blocks(
                mix_index,
                history.calculations,
                energy_desc,
                maxcal,
                burnup_axis=burnup_axis,
            )
        )

    blocks.extend([lcm.control(-2), lcm.control(-1)])
    return blocks


def _global_parameter_blocks(
    level: int,
    burnup_values: np.ndarray | None,
) -> list[lcm.LcmBlock]:
    if burnup_values is None:
        return [
            lcm.block(level, "PARCAD", 1, [1]),
            lcm.block(level, "PARPAD", 1, [1]),
        ]

    values = np.asarray(burnup_values, dtype=float).reshape(-1)
    parkey, parkey_count = lcm.pack_fixed_strings(
        ["BURN"],
        width=DONJON_PARAMETER_KEY_WIDTH,
    )
    partyp, partyp_count = lcm.pack_fixed_strings(
        ["VALU"],
        width=DONJON_PARAMETER_TYPE_WIDTH,
    )
    parfmt, parfmt_count = lcm.pack_fixed_strings(
        ["REAL"],
        width=DONJON_PARAMETER_FORMAT_WIDTH,
    )
    return [
        lcm.block(level, "PARKEY", 3, parkey, count=parkey_count),
        lcm.block(level, "PARTYP", 3, partyp, count=partyp_count),
        lcm.block(level, "PARFMT", 3, parfmt, count=parfmt_count),
        lcm.block(level, "PARCAD", 1, [1, 1]),
        lcm.block(level, "PARPAD", 1, [1, 1]),
        lcm.block(level, "pval00000001", 2, values),
        lcm.block(level, "NVALUE", 1, [len(values)]),
    ]


def _mixture_blocks(
    mix_index: int,
    calculations: list[MixtureXS],
    energy_desc: np.ndarray,
    maxcal: int,
    *,
    burnup_axis: np.ndarray | None,
) -> list[lcm.LcmBlock]:
    blocks: list[lcm.LcmBlock] = [
        lcm.list_item(3, mix_index),
        lcm.block(4, "CALCULATIONS", 10, count=maxcal),
    ]
    for calc_index, mix in enumerate(calculations, start=1):
        blocks.extend(
            [
                lcm.list_item(5, calc_index),
                lcm.block(6, "ISOTOPESLIST", 10, count=1),
                lcm.list_item(7, 1),
            ]
        )
        blocks.extend(_isotope_blocks(8, mix))
        blocks.extend(
            [
                lcm.control(-8),
                *_macrolib_blocks(6, mix),
                *_library_blocks(6, mix, energy_desc),
                lcm.control(-6),
            ]
        )

    tree = _parameter_tree_blocks(4, len(calculations), burnup_axis=burnup_axis)
    blocks.extend([*tree, lcm.control(-4)])
    return blocks


def _parameter_tree_blocks(
    level: int,
    ncal: int,
    *,
    burnup_axis: np.ndarray | None,
) -> list[lcm.LcmBlock]:
    if burnup_axis is None:
        return [
            lcm.block(level, "TREE", 0, count=-1),
            lcm.block(level + 1, "NVP", 1, [1, 20]),
            lcm.block(level + 1, "NCALS", 1, [ncal]),
            lcm.block(level + 1, "DEBARB", 1, [2, 1]),
            lcm.block(level + 1, "ARBVAL", 1, [0]),
            lcm.block(level + 1, "ORIGIN", 1, [0] * ncal),
            lcm.control(-(level + 1)),
        ]

    if len(burnup_axis) != ncal:
        raise ValueError("burnup_values length must match number of calculations")
    nvp = ncal + 1
    debarb = [2, ncal + 2, *range(1, ncal + 1)]
    arbval = [0, *range(1, ncal + 1)]
    return [
        lcm.block(level, "TREE", 0, count=-1),
        lcm.block(level + 1, "NVP", 1, [nvp, max(20, nvp)]),
        lcm.block(level + 1, "NCALS", 1, [ncal]),
        lcm.block(level + 1, "DEBARB", 1, debarb),
        lcm.block(level + 1, "ARBVAL", 1, arbval),
        lcm.block(level + 1, "ORIGIN", 1, [0] * ncal),
        lcm.control(-(level + 1)),
    ]


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

    if mix.sph is not None:
        blocks.append(lcm.block(level, "NSPH", 2, mix.sph))

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
            lcm.string_block(
                level,
                "ALIAS",
                "*MAC*RES",
                width=DONJON_MACRO_NAME_WIDTH,
            ),
        ]
    )
    return blocks


def _macrolib_blocks(level: int, mix: MixtureXS) -> list[lcm.LcmBlock]:
    if not mix.adf:
        return []

    names = tuple(mix.adf)
    packed_names, name_count = lcm.pack_fixed_strings(
        names,
        width=DONJON_ADF_NAME_WIDTH,
    )
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
        lcm.string_block(
            level,
            "SIGNATURE",
            "L_LIBRARY",
            width=DONJON_SIGNATURE_WIDTH,
        ),
        lcm.block(
            level,
            "STATE-VECTOR",
            1,
            _library_state_vector(mix.ngroups, mix.nmoments, _mixture_adf_type(mix)),
        ),
        lcm.block(level, "ISOTOPESMIX", 1, [1]),
        lcm.string_block(
            level,
            "ISOTOPESUSED",
            "*MAC*RES",
            width=DONJON_MACRO_NAME_WIDTH,
        ),
        lcm.string_block(
            level,
            "ISOTOPERNAME",
            "*MAC*RES",
            width=DONJON_MACRO_NAME_WIDTH,
        ),
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
    state[2] = int(maxcal)
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


def _mixture_from_hdf5_group(
    group,
    ngroups: int,
    mix_name: str,
    *,
    expected_moments: int | None,
    h_factor_default: float | None,
    parent_attrs,
) -> MixtureXS:
    scatter = _scatter_matrix_from_hdf5(
        group,
        ngroups,
        mix_name,
        expected_moments=expected_moments,
        parent_attrs=parent_attrs,
    )

    total = _vector(group["total"][:], ngroups, mix_name, "total")
    transport_total = _transport_total_from_hdf5(group, scatter, total, ngroups, mix_name)
    absorption = _optional_vector(group, "absorption", ngroups)
    fission = _optional_vector(group, "fission", ngroups)
    nu_fission = _optional_vector(group, "nu_fission", ngroups)
    chi = _optional_vector(group, "chi", ngroups)
    inverse_velocity = _inverse_velocity_from_hdf5(group, ngroups, mix_name)
    fission_attr = bool(_attr_with_parent(group.attrs, parent_attrs, "fissionable", True))
    has_fission_source = (
        np.sum(np.abs(nu_fission)) > 1e-12 and np.sum(np.abs(chi)) > 1e-12
    )
    fissionable = fission_attr and has_fission_source
    if not fissionable:
        fission = np.zeros(ngroups, dtype=float)
        nu_fission = np.zeros(ngroups, dtype=float)
        chi = np.zeros(ngroups, dtype=float)

    return MixtureXS(
        name=mix_name,
        total=total,
        absorption=absorption,
        fission=fission,
        nu_fission=nu_fission,
        chi=chi,
        scatter_matrix=scatter,
        fissionable=fissionable,
        volume=float(_attr_with_parent(group.attrs, parent_attrs, "volume", 1.0)),
        inverse_velocity=inverse_velocity,
        transport_total=transport_total,
        h_factor=_h_factor_from_hdf5(
            group,
            ngroups,
            mix_name,
            default=h_factor_default,
        ),
        adf=_adf_from_hdf5(group, ngroups, mix_name),
        sph=_sph_from_hdf5(group, ngroups, mix_name),
    )


def _attr_with_parent(attrs, parent_attrs, name: str, default):
    if name in attrs:
        return attrs[name]
    if parent_attrs is not None and name in parent_attrs:
        return parent_attrs[name]
    return default


def _burnup_values_from_hdf5(h5) -> np.ndarray | None:
    paths: list[str] = []
    if "state_points" in h5:
        state_points = h5["state_points"]
        if not hasattr(state_points, "keys"):
            raise ValueError("/state_points must be an HDF5 group")
        unsupported = [
            str(name)
            for name in state_points
            if str(name).lower() not in {"burn", "burnup"}
        ]
        if unsupported:
            raise ValueError(
                "unsupported state_points axis/axes: "
                f"{', '.join(unsupported)}; only BURN is supported"
            )
        paths.extend(
            f"state_points/{name}"
            for name in state_points
            if str(name).lower() in {"burn", "burnup"}
        )
    paths.extend(path for path in ("burnup_values", "burnup") if path in h5)

    attrs = [attr for attr in ("burnup_values", "burnup") if attr in h5.attrs]
    if len(paths) + len(attrs) > 1:
        labels = [f"/{path}" for path in paths] + [f"/attrs/{attr}" for attr in attrs]
        raise ValueError(f"multiple BURN axis definitions found: {', '.join(labels)}")
    if paths:
        return np.asarray(h5[paths[0]][:], dtype=float).reshape(-1)
    if attrs:
        return np.asarray(h5.attrs[attrs[0]], dtype=float).reshape(-1)
    return None


def _sorted_state_names(states_group) -> list[str]:
    def key(name: str) -> tuple[int, int | str]:
        try:
            return (0, int(name))
        except ValueError:
            return (1, name)

    return sorted(states_group.keys(), key=key)


def _validate_histories(
    histories: list[MixtureHistory],
    burnup_values: np.ndarray | None,
) -> None:
    if not histories:
        raise ValueError("at least one mixture history is required")
    nstates = histories[0].nstates
    if nstates <= 0:
        raise ValueError("mixture histories must contain at least one calculation")
    for history in histories:
        if history.nstates != nstates:
            raise ValueError("all mixture histories must contain the same number of states")
        if not history.name:
            raise ValueError("mixture history name must not be empty")
    if nstates > 1:
        if burnup_values is None:
            raise ValueError("multi-state HDF5 requires a BURN axis")
        if len(burnup_values) != nstates:
            raise ValueError("BURN axis length must match number of states")


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


def _sph_from_hdf5(group, ngroups: int, mix_name: str) -> np.ndarray | None:
    for name in ("sph", "SPH", "NSPH"):
        if name in group:
            return _vector(group[name][:], ngroups, mix_name, name)
    return None


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
    if len(name) > DONJON_ADF_NAME_WIDTH:
        raise ValueError(
            f"mixture {mix_name}: ADF name {name!r} is longer than "
            f"{DONJON_ADF_NAME_WIDTH} characters"
        )
    return name


def _validate_root_name(name: str) -> str:
    if not name:
        raise ValueError("root_name must not be empty")
    if len(name) > DONJON_OBJECT_NAME_WIDTH:
        raise ValueError(
            f"root_name {name!r} is longer than "
            f"{DONJON_OBJECT_NAME_WIDTH} characters"
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


def _validate_sph_layout(mixtures: list[MixtureXS]) -> None:
    has_sph = [mix.sph is not None for mix in mixtures]
    if any(has_sph) and not all(has_sph):
        raise ValueError("SPH data must be present for either all mixtures or none")


def _scatter_matrix_from_hdf5(
    group,
    ngroups: int,
    mix_name: str,
    *,
    expected_moments: int | None,
    parent_attrs=None,
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
            axes=_attr_text(
                _attr_with_parent(group.attrs, parent_attrs, "scatter_axes", None)
            )
            or _attr_text(_attr_with_parent(group.attrs, parent_attrs, "axes", None)),
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
    if mix.sph is not None:
        values = np.asarray(mix.sph, dtype=float).reshape(-1)
        if values.shape != (ngroups,):
            raise ValueError(f"mixture {mix.name}: sph must have {ngroups} values")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"mixture {mix.name}: sph must be finite")
        if np.any(values <= 0.0):
            raise ValueError(f"mixture {mix.name}: sph must be positive")

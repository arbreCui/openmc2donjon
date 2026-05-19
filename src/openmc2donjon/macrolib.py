"""Helpers for reading and writing DONJON ``L_MACROLIB`` ASCII dumps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from . import lcm_ascii as lcm
from .scatter import dense_moments_to_triplets


@dataclass
class Macrolib:
    state_vector: tuple[int, ...]
    energy: np.ndarray
    volume: np.ndarray
    ntot0: np.ndarray
    diff: np.ndarray
    sigs: dict[int, np.ndarray]
    scatter: dict[int, np.ndarray]
    nusigf: np.ndarray
    chi: np.ndarray
    h_factor: np.ndarray | None
    adf: dict[str, np.ndarray]

    @property
    def ngroups(self) -> int:
        return int(self.state_vector[0])

    @property
    def nmixtures(self) -> int:
        return int(self.state_vector[1])


def read_macrolib_ascii(path: str | Path) -> Macrolib:
    """Read the first ``L_MACROLIB`` object found in an ASCII listing."""

    return parse_macrolib_blocks(lcm.read_lcm_ascii(path))


def convert_mgxs_hdf5_to_macrolib(
    input_h5: str | Path,
    output_path: str | Path,
    *,
    h_factor_default: float | None = None,
    mixture_names: Sequence[str] | None = None,
) -> None:
    """Read an OpenMC MGXS HDF5 dump and write a root ``L_MACROLIB`` object."""

    from .multicompo import _select_mixtures, read_mgxs_hdf5

    mixtures, energy_bounds = read_mgxs_hdf5(
        input_h5,
        h_factor_default=h_factor_default,
    )
    write_macrolib(
        _select_mixtures(mixtures, mixture_names),
        energy_bounds,
        output_path,
    )


def write_macrolib(
    mixtures: Iterable["MixtureXS"],
    energy_bounds: np.ndarray | list[float],
    output_path: str | Path,
) -> None:
    """Write a root ``L_MACROLIB`` ASCII object."""

    blocks = build_macrolib_blocks(
        list(mixtures),
        np.asarray(energy_bounds, dtype=float),
    )
    lcm.write_lcm_ascii(blocks, output_path)


def build_macrolib_blocks(
    mixtures: list["MixtureXS"],
    energy_bounds: np.ndarray,
) -> list[lcm.LcmBlock]:
    """Build root ``L_MACROLIB`` records from converter-facing MGXS mixtures."""

    from .multicompo import _validate_adf_layout, _validate_mixture

    if not mixtures:
        raise ValueError("at least one mixture is required")
    ngroups = mixtures[0].ngroups
    if energy_bounds.shape != (ngroups + 1,):
        raise ValueError("energy_bounds length must be ngroups + 1")
    for mix in mixtures:
        _validate_mixture(mix, ngroups)
        _validate_macrolib_vectors(mix, ngroups)
    _validate_adf_layout(mixtures)

    nmoments = max(mix.nmoments for mix in mixtures)
    if any(mix.nmoments != nmoments for mix in mixtures):
        raise ValueError("all mixtures must use the same number of Legendre moments")

    blocks: list[lcm.LcmBlock] = [
        lcm.string_block(1, "SIGNATURE", "L_MACROLIB", width=12),
        lcm.block(1, "STATE-VECTOR", 1, _macrolib_state_vector(mixtures)),
        lcm.block(1, "ENERGY", 2, np.asarray(energy_bounds, dtype=float)[::-1]),
        lcm.block(1, "VOLUME", 2, [mix.volume for mix in mixtures]),
        lcm.block(1, "GROUP", 10, count=ngroups),
    ]

    triplets = [dense_moments_to_triplets(mix.scatter_matrix) for mix in mixtures]
    starts = [
        [np.concatenate(([0], np.cumsum(moment.njjs[:-1]))) for moment in mix_triplets]
        for mix_triplets in triplets
    ]

    for group_index in range(ngroups):
        blocks.extend(
            _macrolib_group_blocks(
                group_index,
                mixtures,
                triplets,
                starts,
                nmoments,
            )
        )

    blocks.extend(_macrolib_adf_blocks(mixtures))
    blocks.extend(
        [
            lcm.block(1, "K-INFINITY", 2, [1.0]),
            lcm.block(1, "K-EFFECTIVE", 2, [1.0]),
            lcm.control(-1),
        ]
    )
    return blocks


def _macrolib_group_blocks(
    group_index: int,
    mixtures: list["MixtureXS"],
    triplets,
    starts,
    nmoments: int,
) -> list[lcm.LcmBlock]:
    blocks: list[lcm.LcmBlock] = [lcm.list_item(2, group_index + 1)]
    blocks.extend(
        [
            lcm.block(3, "FLUX-INTG", 2, _group_flux_integral(mixtures, group_index)),
            lcm.block(3, "NTOT0", 2, [mix.total[group_index] for mix in mixtures]),
            lcm.block(
                3,
                "OVERV",
                2,
                _group_optional_vector(
                    mixtures,
                    "inverse_velocity",
                    group_index,
                    0.0,
                ),
            ),
            lcm.block(
                3,
                "DIFF",
                2,
                _group_diffusion_coefficients(mixtures, group_index),
            ),
        ]
    )

    if any(mix.h_factor is not None for mix in mixtures):
        blocks.append(
            lcm.block(
                3,
                "H-FACTOR",
                2,
                _group_optional_vector(mixtures, "h_factor", group_index, 0.0),
            )
        )

    for ell in range(nmoments):
        tag = f"{ell:02d}"
        blocks.append(
            lcm.block(
                3,
                f"SIGS{tag}",
                2,
                [
                    np.asarray(mix.scatter_matrix[ell], dtype=float).sum(axis=1)[
                        group_index
                    ]
                    for mix in mixtures
                ],
            )
        )

    if any(mix.fissionable for mix in mixtures):
        blocks.extend(
            [
                lcm.block(
                    3,
                    "NUSIGF",
                    2,
                    [mix.nu_fission[group_index] for mix in mixtures],
                ),
                lcm.block(3, "CHI", 2, [mix.chi[group_index] for mix in mixtures]),
            ]
        )

    for ell in range(nmoments):
        tag = f"{ell:02d}"
        scat, njjs, ijjs, ipos = _group_scatter_triplets(
            group_index,
            ell,
            mixtures,
            triplets,
            starts,
        )
        blocks.extend(
            [
                lcm.block(3, f"SCAT{tag}", 2, scat),
                lcm.block(3, f"NJJS{tag}", 1, njjs),
                lcm.block(3, f"IJJS{tag}", 1, ijjs),
                lcm.block(3, f"IPOS{tag}", 1, ipos),
                lcm.block(
                    3,
                    f"SIGW{tag}",
                    2,
                    [
                        mix.scatter_matrix[ell, group_index, group_index]
                        for mix in mixtures
                    ],
                ),
            ]
        )

    blocks.append(lcm.control(-3))
    return blocks


def _group_scatter_triplets(
    group_index: int,
    moment: int,
    mixtures: list["MixtureXS"],
    triplets,
    starts,
) -> tuple[list[float], list[int], list[int], list[int]]:
    flat: list[float] = []
    njjs: list[int] = []
    ijjs: list[int] = []
    ipos: list[int] = []
    cursor = 1

    for mix_index, _mix in enumerate(mixtures):
        triplet = triplets[mix_index][moment]
        span = int(triplet.njjs[group_index])
        start = int(starts[mix_index][moment][group_index])
        ipos.append(cursor)
        njjs.append(span)
        ijjs.append(int(triplet.ijjs[group_index]))
        flat.extend(float(x) for x in triplet.scat[start : start + span])
        cursor += span

    return flat, njjs, ijjs, ipos


def _group_flux_integral(mixtures: list["MixtureXS"], group_index: int) -> list[float]:
    values: list[float] = []
    for mix in mixtures:
        if mix.flux_weight is None:
            values.append(float(mix.volume))
        else:
            values.append(
                float(
                    np.asarray(mix.flux_weight, dtype=float)[group_index] * mix.volume
                )
            )
    return values


def _group_optional_vector(
    mixtures: list["MixtureXS"],
    field: str,
    group_index: int,
    default: float,
) -> list[float]:
    values: list[float] = []
    for mix in mixtures:
        vector = getattr(mix, field)
        values.append(
            float(
                default
                if vector is None
                else np.asarray(vector, dtype=float)[group_index]
            )
        )
    return values


def _group_diffusion_coefficients(
    mixtures: list["MixtureXS"], group_index: int
) -> list[float]:
    values: list[float] = []
    for mix in mixtures:
        transport_total = (
            np.asarray(mix.total, dtype=float)
            if mix.transport_total is None
            else np.asarray(mix.transport_total, dtype=float)
        )
        values.append(float(1.0 / (3.0 * transport_total[group_index])))
    return values


def _macrolib_state_vector(mixtures: list["MixtureXS"]) -> list[int]:
    state = [0] * 40
    state[0] = mixtures[0].ngroups
    state[1] = len(mixtures)
    state[2] = mixtures[0].nmoments
    state[3] = 1 if any(mix.fissionable for mix in mixtures) else 0
    state[8] = 1
    state[11] = 3 if any(mix.adf for mix in mixtures) else 0
    return state


def _macrolib_adf_blocks(mixtures: list["MixtureXS"]) -> list[lcm.LcmBlock]:
    if not mixtures[0].adf:
        return []

    names = tuple(mixtures[0].adf)
    packed_names, name_count = lcm.pack_fixed_strings(names, width=8)
    blocks: list[lcm.LcmBlock] = [
        lcm.block(1, "ADF", 0, count=-1),
        lcm.block(2, "NTYPE", 1, [len(names)]),
        lcm.block(2, "HADF", 3, packed_names, count=name_count),
    ]
    for name in names:
        matrix = np.stack([np.asarray(mix.adf[name], dtype=float) for mix in mixtures])
        blocks.append(lcm.block(2, name, 2, matrix.T.reshape(-1)))
    blocks.append(lcm.control(-2))
    return blocks


def _validate_macrolib_vectors(mix: "MixtureXS", ngroups: int) -> None:
    for field in ("inverse_velocity", "transport_total", "flux_weight", "h_factor"):
        vector = getattr(mix, field)
        if vector is None:
            continue
        values = np.asarray(vector, dtype=float).reshape(-1)
        if values.shape != (ngroups,):
            raise ValueError(f"mixture {mix.name}: {field} must have {ngroups} values")
        if field == "transport_total" and np.any(values <= 0.0):
            raise ValueError(
                f"mixture {mix.name}: transport_total must be positive in every group"
            )


def parse_macrolib_blocks(blocks: list[lcm.LcmBlock]) -> Macrolib:
    """Parse a ``L_MACROLIB`` block sequence from ``lcm_ascii`` records."""

    start, base_level, starts_with_group = _find_macrolib_object(blocks)
    object_blocks = _object_blocks(
        blocks[start:],
        base_level,
        stop_on_base_control=starts_with_group,
    )

    state = _find_named(object_blocks, "STATE-VECTOR", level=base_level).data
    if not isinstance(state, tuple):
        raise ValueError("L_MACROLIB STATE-VECTOR is missing integer data")
    ngroups = int(state[0])
    nmixtures = int(state[1])

    energy = _real_vector(
        _find_named(object_blocks, "ENERGY", level=base_level), ngroups + 1
    )
    volume_block = _find_named(object_blocks, "VOLUME", level=base_level, required=False)
    volume = (
        np.ones(nmixtures, dtype=float)
        if volume_block is None
        else _real_vector(volume_block, nmixtures)
    )

    groups = _group_payloads(object_blocks, ngroups, base_level)
    ntot0 = _group_matrix(groups, "NTOT0", nmixtures, ngroups)
    diff = _group_matrix(groups, "DIFF", nmixtures, ngroups)
    nusigf = _group_matrix(groups, "NUSIGF", nmixtures, ngroups, default=0.0)
    chi = _group_matrix(groups, "CHI", nmixtures, ngroups, default=0.0)
    h_factor = _optional_group_matrix(groups, "H-FACTOR", nmixtures, ngroups)
    adf = _adf_payload(object_blocks, nmixtures, ngroups, base_level)

    moments = _scatter_moments(groups)
    sigs = {
        moment: _group_matrix(groups, f"SIGS{moment:02d}", nmixtures, ngroups)
        for moment in moments
    }
    scatter = {
        moment: _scatter_matrix(groups, moment, nmixtures, ngroups)
        for moment in moments
    }

    return Macrolib(
        state_vector=state,
        energy=energy,
        volume=volume,
        ntot0=ntot0,
        diff=diff,
        sigs=sigs,
        scatter=scatter,
        nusigf=nusigf,
        chi=chi,
        h_factor=h_factor,
        adf=adf,
    )


def _find_macrolib_object(blocks: list[lcm.LcmBlock]) -> tuple[int, int, bool]:
    for index, block in enumerate(blocks):
        if block.name == "SIGNATURE" and isinstance(block.data, str):
            if block.data.strip() == "L_MACROLIB":
                start = _macrolib_object_start(blocks, index)
                return start, block.level, start != index
    raise ValueError("no L_MACROLIB SIGNATURE found")


def _macrolib_object_start(blocks: list[lcm.LcmBlock], signature_index: int) -> int:
    base_level = blocks[signature_index].level
    for index in range(signature_index - 1, -1, -1):
        block = blocks[index]
        if block.is_control:
            continue
        if block.level < base_level:
            break
        if block.level == base_level and block.name == "GROUP":
            return index
    return signature_index


def _object_blocks(
    blocks: list[lcm.LcmBlock],
    base_level: int,
    *,
    stop_on_base_control: bool,
) -> list[lcm.LcmBlock]:
    out: list[lcm.LcmBlock] = []
    for index, block in enumerate(blocks):
        if (
            not stop_on_base_control
            and index > 0
            and block.name == "SIGNATURE"
            and block.level <= base_level
        ):
            break
        out.append(block)
        if stop_on_base_control and block.is_control and block.level == -base_level:
            break
    return out


def _find_named(
    blocks: list[lcm.LcmBlock],
    name: str,
    *,
    level: int | None = None,
    required: bool = True,
) -> lcm.LcmBlock | None:
    for block in blocks:
        if block.name == name and (level is None or block.level == level):
            return block
    if required:
        raise ValueError(f"missing L_MACROLIB block {name!r}")
    return None


def _group_payloads(
    blocks: list[lcm.LcmBlock], ngroups: int, base_level: int
) -> list[dict[str, lcm.LcmBlock]]:
    groups: list[dict[str, lcm.LcmBlock]] = [{} for _ in range(ngroups)]
    current: int | None = None

    for block in blocks:
        if block.is_control:
            if (
                block.level == base_level + 1
                and block.count == -1
                and block.trailing
            ):
                current = int(block.trailing) - 1
                if not 0 <= current < ngroups:
                    raise ValueError(f"group list item {current + 1} is out of range")
            elif block.level == -(base_level + 2):
                current = None
            continue

        if (
            current is not None
            and block.level == base_level + 2
            and block.name is not None
        ):
            groups[current][block.name] = block

    missing = [index + 1 for index, payload in enumerate(groups) if not payload]
    if missing:
        raise ValueError(f"missing GROUP payloads: {missing}")
    return groups


def _adf_payload(
    blocks: list[lcm.LcmBlock], nmixtures: int, ngroups: int, base_level: int
) -> dict[str, np.ndarray]:
    adf_index = _find_named_index(blocks, "ADF", level=base_level)
    if adf_index is None:
        return {}

    adf_blocks: list[lcm.LcmBlock] = []
    for block in blocks[adf_index + 1 :]:
        if block.is_control and block.level == -(base_level + 1):
            break
        adf_blocks.append(block)

    ntype_block = _find_named(adf_blocks, "NTYPE", level=base_level + 1)
    ntype = int(_int_vector(ntype_block, 1)[0])
    hadf_block = _find_named(adf_blocks, "HADF", level=base_level + 1)
    if not isinstance(hadf_block.data, str):
        raise ValueError("L_MACROLIB ADF/HADF is missing string data")
    names = [name.strip() for name in lcm.unpack_fixed_strings(hadf_block.data, 8)]
    names = names[:ntype]
    if len(names) != ntype or any(not name for name in names):
        raise ValueError("L_MACROLIB ADF/HADF has invalid face names")

    adf: dict[str, np.ndarray] = {}
    for name in names:
        block = _find_named(adf_blocks, name, level=base_level + 1)
        values = _real_vector(block, nmixtures * ngroups)
        adf[name] = values.reshape((ngroups, nmixtures)).T
    return adf


def _find_named_index(
    blocks: list[lcm.LcmBlock], name: str, *, level: int | None = None
) -> int | None:
    for index, block in enumerate(blocks):
        if block.name == name and (level is None or block.level == level):
            return index
    return None


def _group_matrix(
    groups: list[dict[str, lcm.LcmBlock]],
    name: str,
    nmixtures: int,
    ngroups: int,
    *,
    default: float | None = None,
) -> np.ndarray:
    out = np.zeros((nmixtures, ngroups), dtype=float)
    for group_index, payload in enumerate(groups):
        block = payload.get(name)
        if block is None:
            if default is None:
                raise ValueError(f"missing GROUP/{group_index + 1}/{name}")
            out[:, group_index] = default
            continue
        out[:, group_index] = _real_vector(block, nmixtures)
    return out


def _optional_group_matrix(
    groups: list[dict[str, lcm.LcmBlock]],
    name: str,
    nmixtures: int,
    ngroups: int,
) -> np.ndarray | None:
    if all(name not in payload for payload in groups):
        return None
    return _group_matrix(groups, name, nmixtures, ngroups)


def _scatter_moments(groups: list[dict[str, lcm.LcmBlock]]) -> list[int]:
    moments: set[int] = set()
    for payload in groups:
        for name in payload:
            if name.startswith("SCAT") and len(name) == 6 and name[4:].isdigit():
                moments.add(int(name[4:]))
    return sorted(moments)


def _scatter_matrix(
    groups: list[dict[str, lcm.LcmBlock]],
    moment: int,
    nmixtures: int,
    ngroups: int,
) -> np.ndarray:
    tag = f"{moment:02d}"
    dense = np.zeros((nmixtures, ngroups, ngroups), dtype=float)
    for to_group, payload in enumerate(groups):
        scat = _real_vector(payload[f"SCAT{tag}"], expected=None)
        njjs = _int_vector(payload[f"NJJS{tag}"], nmixtures)
        ijjs = _int_vector(payload[f"IJJS{tag}"], nmixtures)
        ipos = _int_vector(payload[f"IPOS{tag}"], nmixtures)

        for mix_index in range(nmixtures):
            start = int(ipos[mix_index]) - 1
            count = int(njjs[mix_index])
            from_start = int(ijjs[mix_index]) - 1
            for offset in range(count):
                from_group = from_start - offset
                dense[mix_index, from_group, to_group] = scat[start + offset]
    return dense


def _real_vector(block: lcm.LcmBlock, expected: int | None) -> np.ndarray:
    if not isinstance(block.data, tuple):
        raise ValueError(f"block {block.name!r} has no real payload")
    values = np.asarray(block.data, dtype=float)
    if expected is not None and values.shape != (expected,):
        raise ValueError(
            f"block {block.name!r} has shape {values.shape}, expected ({expected},)"
        )
    return values


def _int_vector(block: lcm.LcmBlock, expected: int) -> np.ndarray:
    if not isinstance(block.data, tuple):
        raise ValueError(f"block {block.name!r} has no integer payload")
    values = np.asarray(block.data, dtype=int)
    if values.shape != (expected,):
        raise ValueError(
            f"block {block.name!r} has shape {values.shape}, expected ({expected},)"
        )
    return values

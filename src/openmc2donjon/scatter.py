"""DRAGON/DONJON scattering triplet conversion.

OpenMC MGXS data arrives as dense matrices indexed ``dense[from, to]``.
DRAGON stores each Legendre moment by outgoing group as a contiguous incoming
group span.  Zeros inside the span are significant and are therefore preserved.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ScatterTriplet:
    njjs: np.ndarray
    ijjs: np.ndarray
    scat: np.ndarray


def dense_to_triplet(matrix: np.ndarray, *, atol: float = 0.0) -> ScatterTriplet:
    """Convert a dense ``[from, to]`` scattering matrix to DRAGON triplets."""

    dense = np.asarray(matrix, dtype=float)
    if dense.ndim != 2 or dense.shape[0] != dense.shape[1]:
        raise ValueError("scatter matrix must be square with shape [from, to]")

    ngroups = dense.shape[0]
    njjs = np.zeros(ngroups, dtype=np.int64)
    ijjs = np.zeros(ngroups, dtype=np.int64)
    flat: list[float] = []

    for to_idx in range(ngroups):
        column = dense[:, to_idx]
        if atol == 0.0:
            nonzero = np.flatnonzero(column != 0.0)
        else:
            nonzero = np.flatnonzero(np.abs(column) > atol)
        if nonzero.size == 0:
            njjs[to_idx] = 1
            ijjs[to_idx] = to_idx + 1
            flat.append(0.0)
            continue

        first = int(nonzero.min())
        last = int(nonzero.max())
        njjs[to_idx] = last - first + 1
        ijjs[to_idx] = last + 1
        flat.extend(
            float(dense[from_idx, to_idx])
            for from_idx in range(last, first - 1, -1)
        )

    return ScatterTriplet(njjs=njjs, ijjs=ijjs, scat=np.asarray(flat, dtype=float))


def triplet_to_dense(
    njjs: np.ndarray | list[int] | tuple[int, ...],
    ijjs: np.ndarray | list[int] | tuple[int, ...],
    scat: np.ndarray | list[float] | tuple[float, ...],
    ngroups: int | None = None,
) -> np.ndarray:
    """Reconstruct dense ``[from, to]`` scattering from DRAGON triplets."""

    n = np.asarray(njjs, dtype=np.int64)
    i = np.asarray(ijjs, dtype=np.int64)
    s = np.asarray(scat, dtype=float)
    if n.shape != i.shape:
        raise ValueError("NJJS and IJJS must have the same shape")
    if ngroups is None:
        ngroups = int(n.size)
    if n.size != ngroups:
        raise ValueError("NJJS length must equal ngroups")

    dense = np.zeros((ngroups, ngroups), dtype=float)
    cursor = 0
    for to_idx in range(ngroups):
        span = int(n[to_idx])
        if span == 0:
            continue
        last = int(i[to_idx]) - 1
        first = last - span + 1
        if first < 0 or last >= ngroups:
            raise ValueError(
                f"invalid scattering span for to group {to_idx + 1}: "
                f"first={first + 1}, last={last + 1}"
            )
        for from_idx in range(last, first - 1, -1):
            if cursor >= s.size:
                raise ValueError("SCAT payload ended before triplets were consumed")
            dense[from_idx, to_idx] = s[cursor]
            cursor += 1

    if cursor != s.size:
        raise ValueError(f"SCAT payload has {s.size - cursor} unused values")
    return dense


def dense_moments_to_triplets(
    dense: np.ndarray, *, atol: float = 0.0
) -> list[ScatterTriplet]:
    """Convert ``[moment, from, to]`` dense scattering to triplets."""

    moments = np.asarray(dense, dtype=float)
    if moments.ndim != 3:
        raise ValueError("dense moments must have shape [moment, from, to]")
    return [
        dense_to_triplet(moments[ell], atol=atol)
        for ell in range(moments.shape[0])
    ]


def triplets_to_dense_moments(triplets: list[ScatterTriplet], ngroups: int) -> np.ndarray:
    """Convert a list of triplets to ``[moment, from, to]`` dense scattering."""

    if not triplets:
        raise ValueError("at least one scattering moment is required")
    return np.stack(
        [triplet_to_dense(t.njjs, t.ijjs, t.scat, ngroups) for t in triplets],
        axis=0,
    )

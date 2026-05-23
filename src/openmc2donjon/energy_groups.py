"""Energy-group identity helpers for MGXS handoff files."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

import numpy as np

MESH_RELATIVE_TOLERANCE = 1.0e-6
MESH_ABSOLUTE_TOLERANCE = 1.0e-12


@dataclass(frozen=True)
class EnergyMesh:
    mesh_id: str
    name: str
    short: str
    description: str
    purpose: str
    n_groups: int
    boundaries_descending: np.ndarray


def energy_bounds_sha256(bounds: np.ndarray | list[float]) -> str:
    """Return a stable SHA-256 digest for a group-boundary vector."""

    values = np.asarray(bounds, dtype="<f8").reshape(-1)
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def load_energy_bounds_text(path: str | Path) -> np.ndarray:
    """Load an expected one-dimensional energy-boundary vector from text."""

    values = np.loadtxt(Path(path), dtype=float)
    return np.asarray(values, dtype=float).reshape(-1)


def validate_energy_bounds_internal(
    bounds: np.ndarray | list[float],
    *,
    expected_groups: int | None = None,
    expected_order: str = "ascending",
) -> list[str]:
    """Return internal consistency issues for a group-boundary vector."""

    issues: list[str] = []
    try:
        values = np.asarray(bounds, dtype=float)
    except (TypeError, ValueError):
        return ["energy_bounds must be a numeric vector"]
    if values.ndim != 1:
        issues.append("energy_bounds must be a one-dimensional vector")
        return issues
    if values.size < 2:
        issues.append("energy_bounds must contain at least two boundary values")
        return issues
    if expected_groups is not None and values.shape != (int(expected_groups) + 1,):
        issues.append(
            "energy_bounds length must be energy_groups + 1: "
            f"{values.shape[0]} != {int(expected_groups) + 1}"
        )
    if not np.all(np.isfinite(values)):
        issues.append("energy_bounds contains non-finite values")
    if np.any(values <= 0.0):
        issues.append("energy_bounds must contain positive eV values")

    order = energy_bounds_order(values)
    if expected_order == "ascending" and order != "ascending":
        issues.append("energy_bounds must be strictly ascending")
    elif expected_order == "descending" and order != "descending":
        issues.append("energy_bounds must be strictly descending")
    elif expected_order == "either" and order not in {"ascending", "descending"}:
        issues.append("energy_bounds must be strictly monotonic")
    elif expected_order not in {"ascending", "descending", "either"}:
        raise ValueError("expected_order must be 'ascending', 'descending', or 'either'")
    return issues


def energy_bounds_order(bounds: np.ndarray | list[float]) -> str:
    """Return ``ascending``, ``descending``, or ``unordered``."""

    values = np.asarray(bounds, dtype=float).reshape(-1)
    if values.size < 2:
        return "unordered"
    delta = np.diff(values)
    if np.all(delta > 0.0):
        return "ascending"
    if np.all(delta < 0.0):
        return "descending"
    return "unordered"


def identify_mesh(
    bounds: np.ndarray | list[float],
    *,
    rtol: float = MESH_RELATIVE_TOLERANCE,
    atol: float = MESH_ABSOLUTE_TOLERANCE,
) -> EnergyMesh | None:
    """Identify a known energy mesh from ascending or descending boundaries."""

    try:
        candidate = _ascending_bounds(bounds)
    except ValueError:
        return None
    for mesh in energy_mesh_catalog():
        reference = mesh.boundaries_descending[::-1]
        if reference.shape != candidate.shape:
            continue
        if np.allclose(candidate, reference, rtol=float(rtol), atol=float(atol)):
            return mesh
    return None


def load_energy_mesh(mesh_id: str) -> EnergyMesh:
    """Load one bundled energy mesh by id."""

    by_id = {mesh.mesh_id: mesh for mesh in energy_mesh_catalog()}
    try:
        return by_id[mesh_id]
    except KeyError as exc:
        raise ValueError(f"unknown energy mesh id {mesh_id!r}") from exc


@lru_cache(maxsize=1)
def energy_mesh_catalog() -> tuple[EnergyMesh, ...]:
    """Return bundled energy meshes from the package data catalog."""

    root = resources.files("openmc2donjon").joinpath("data").joinpath("energy_meshes")
    index = json.loads(root.joinpath("meshes.json").read_text(encoding="utf-8"))
    meshes: list[EnergyMesh] = []
    for item in index["meshes"]:
        mesh_id = str(item["id"])
        payload = json.loads(root.joinpath(f"{mesh_id}.json").read_text(encoding="utf-8"))
        boundaries = np.asarray(payload["boundaries"], dtype=float).reshape(-1)
        issues = validate_energy_bounds_internal(
            boundaries,
            expected_groups=int(payload["n_groups"]),
            expected_order="descending",
        )
        if issues:
            continue
        meshes.append(
            EnergyMesh(
                mesh_id=mesh_id,
                name=str(payload.get("name", item.get("name", mesh_id))),
                short=str(payload.get("short", item.get("short", mesh_id))),
                description=str(
                    payload.get("description", item.get("description", ""))
                ),
                purpose=str(payload.get("purpose", item.get("purpose", ""))),
                n_groups=int(payload["n_groups"]),
                boundaries_descending=boundaries,
            )
        )
    return tuple(meshes)


def _ascending_bounds(bounds: np.ndarray | list[float]) -> np.ndarray:
    values = np.asarray(bounds, dtype=float).reshape(-1)
    order = energy_bounds_order(values)
    if order == "ascending":
        return values
    if order == "descending":
        return values[::-1]
    raise ValueError("energy bounds must be strictly monotonic")

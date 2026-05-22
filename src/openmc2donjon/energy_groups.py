"""Energy-group identity helpers for MGXS handoff files."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def energy_bounds_sha256(bounds: np.ndarray | list[float]) -> str:
    """Return a stable SHA-256 digest for a group-boundary vector."""

    values = np.asarray(bounds, dtype="<f8").reshape(-1)
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def load_energy_bounds_text(path: str | Path) -> np.ndarray:
    """Load an expected one-dimensional energy-boundary vector from text."""

    values = np.loadtxt(Path(path), dtype=float)
    return np.asarray(values, dtype=float).reshape(-1)

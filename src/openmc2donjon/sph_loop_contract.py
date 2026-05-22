"""Artifact contract checks for the fixed-OpenMC SPH loop."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import lcm_ascii as lcm
from .macrolib import read_macrolib_ascii


def require_existing_file(path: Path, *, label: str) -> int:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{label} is not a regular file: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"{label} is empty: {path}")
    return int(size)


def validate_solver_result(
    path: Path,
    *,
    iteration: int,
    energy_groups: int,
    list_offset: int,
) -> tuple[int, int, int]:
    try:
        size = require_existing_file(
            path,
            label=f"solver result for iteration {iteration}",
        )
        blocks = lcm.read_lcm_ascii(path)
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"solver result contract failed for iteration {iteration}: {exc}"
        ) from exc

    vectors = [
        np.asarray(block.data, dtype=float)
        for block in blocks
        if block.name is None
        and block.data is not None
        and block.type_code == 2
        and block.trailing
    ]
    needed = int(list_offset) + int(energy_groups)
    if len(vectors) < needed:
        raise ValueError(
            f"solver result contract failed for iteration {iteration}: {path} "
            f"contains {len(vectors)} unnamed real flux vector(s), need {needed} "
            f"for list_offset={list_offset} and {energy_groups} group(s)"
        )
    selected = vectors[int(list_offset) : needed]
    lengths = {int(vector.size) for vector in selected}
    if len(lengths) != 1:
        raise ValueError(
            f"solver result contract failed for iteration {iteration}: "
            f"inconsistent flux vector lengths {sorted(lengths)}"
        )
    flux_unknown_count = lengths.pop()
    if flux_unknown_count <= 0:
        raise ValueError(
            f"solver result contract failed for iteration {iteration}: "
            "flux vectors contain no unknowns"
        )
    return size, len(vectors), flux_unknown_count


def validate_postprocess_output(
    path: Path,
    *,
    output_format: str,
    iteration: int,
) -> tuple[int, int]:
    try:
        size = require_existing_file(
            path,
            label=f"postprocess output for iteration {iteration}",
        )
        blocks = lcm.read_lcm_ascii(path)
        if not blocks:
            raise ValueError("no LCM ASCII blocks found")
        if output_format == "macrolib":
            read_macrolib_ascii(path)
        elif not _has_signature(blocks, "L_MULTICOMPO"):
            raise ValueError("missing L_MULTICOMPO SIGNATURE")
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"postprocess output contract failed for iteration {iteration}: {exc}"
        ) from exc
    return size, len(blocks)


def _has_signature(blocks: list[lcm.LcmBlock], value: str) -> bool:
    return any(
        block.name == "SIGNATURE"
        and isinstance(block.data, str)
        and block.data.strip() == value
        for block in blocks
    )

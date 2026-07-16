"""Optional PyGan-backed LCM ASCII writer.

The default writer remains :mod:`openmc2donjon.lcm_ascii`.  This module is a
thin alternate backend for users who already have PyGan installed and want the
DRAGON/DONJON Python bindings to perform the final LCM serialization step.

The important design constraint is that PyGan does *not* rebuild the physics
payload.  We first use the same block builders as the default ASCII writer, then
load that ordered block stream into a PyGan LCM tree and export it.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Iterable, Sequence

import numpy as np

from . import lcm_ascii
from .macrolib import (
    _limit_scatter_order,
    build_macrolib_blocks,
    derive_reference_kinf,
    read_reference_eigenvalues_hdf5,
)
from .multicompo import (
    DEFAULT_ROOT_NAME,
    _select_mixture_histories,
    _select_mixtures,
    build_multicompo_blocks,
    build_multicompo_history_blocks,
    read_mgxs_hdf5,
    read_mgxs_hdf5_histories,
)
from .pygan_backend import (
    pygan_process_guard,
    pygan_working_directory,
    require_pygan,
)


PYGAN_EXPORT_OBJECT_NAME = "openmc2donjon_export"


def convert_mgxs_hdf5_with_pygan(
    input_h5: str | Path,
    output_path: str | Path,
    *,
    output_format: str = "multicompo",
    root_name: str = DEFAULT_ROOT_NAME,
    comment: str | None = None,
    burnup: float | None = None,
    h_factor_default: float | None = None,
    mixture_names: Sequence[str] | None = None,
    max_scatter_order: int | None = None,
) -> None:
    """Read an OpenMC MGXS HDF5 dump and write ASCII through PyGan.

    ``output_format`` accepts the same values as the CLI ``--format`` option:
    ``"multicompo"`` and ``"macrolib"``.
    """

    with pygan_process_guard():
        source = Path(input_h5).expanduser().resolve()
        output = Path(output_path).expanduser().resolve()
        if output_format == "macrolib":
            mixtures, energy_bounds = read_mgxs_hdf5(
                source,
                h_factor_default=h_factor_default,
            )
            reference_keff, reference_kinf = read_reference_eigenvalues_hdf5(source)
            selected = _select_mixtures(mixtures, mixture_names)
            selected_is_complete_model = len(selected) == len(mixtures) and {
                mixture.name for mixture in selected
            } == {mixture.name for mixture in mixtures}
            if not selected_is_complete_model:
                reference_keff = None
            if reference_kinf is None:
                reference_kinf = derive_reference_kinf(selected)
            blocks = build_macrolib_blocks(
                _limit_scatter_order(
                    selected,
                    max_scatter_order,
                ),
                np.asarray(energy_bounds, dtype=float),
                reference_keff=reference_keff,
                reference_kinf=reference_kinf,
            )
        elif output_format == "multicompo":
            if max_scatter_order is not None:
                raise ValueError("max_scatter_order currently requires output_format='macrolib'")
            histories, energy_bounds, burnup_values = read_mgxs_hdf5_histories(
                source,
                h_factor_default=h_factor_default,
            )
            histories = _select_mixture_histories(histories, mixture_names)
            if comment is None:
                comment = f"OpenMC MGXS conversion from {source.name}"
            if any(history.nstates > 1 for history in histories):
                if burnup is not None:
                    raise ValueError("--burnup cannot override a multi-state HDF5 burnup axis")
                blocks = build_multicompo_history_blocks(
                    histories,
                    np.asarray(energy_bounds, dtype=float),
                    root_name=root_name,
                    comment=comment,
                    burnup_values=burnup_values,
                )
            else:
                blocks = build_multicompo_blocks(
                    [history.calculations[0] for history in histories],
                    np.asarray(energy_bounds, dtype=float),
                    root_name=root_name,
                    comment=comment,
                    burnup=burnup,
                )
        else:
            raise ValueError("output_format must be 'multicompo' or 'macrolib'")

        write_lcm_blocks_with_pygan(blocks, output)


def write_lcm_blocks_with_pygan(
    blocks: Iterable[lcm_ascii.LcmBlock],
    output_path: str | Path,
    *,
    object_name: str = PYGAN_EXPORT_OBJECT_NAME,
) -> None:
    """Write ordered LCM blocks using PyGan's ASCII exporter."""

    with pygan_process_guard():
        output = Path(output_path).expanduser().resolve()
        lcm, _, _ = require_pygan()
        _validate_pygan_object_name(object_name)
        obj = _blocks_to_pygan_object(lcm, list(blocks), object_name=object_name)

        # PyGan exports an in-memory object named ``NAME`` as a file named
        # ``_NAME`` in the current directory. Stage that side effect in a
        # temporary directory, then atomically replace the requested output.
        with tempfile.TemporaryDirectory(dir=output.parent) as tmpdir:
            tmp = Path(tmpdir).resolve()
            with pygan_working_directory(tmp):
                lcm.new("ASCII", pyobj=obj)
            staged = tmp / f"_{object_name}"
            if not staged.is_file():
                raise RuntimeError(f"PyGan did not produce expected ASCII file {staged}")
            staged.replace(output)


def _blocks_to_pygan_object(
    lcm_module: Any,
    blocks: list[lcm_ascii.LcmBlock],
    *,
    object_name: str,
) -> Any:
    obj = lcm_module.new("LCM", object_name)
    stack: list[tuple[int, Any, bool]] = [(0, obj, False)]
    for block in blocks:
        if _is_list_item(block):
            _pop_to_parent_level(stack, block.level)
            parent = stack[-1][1]
            if not stack[-1][2]:
                raise ValueError(
                    f"list item {block.trailing!r} at level {block.level} is not inside a list"
                )
            child = parent.rep(_list_item_index(block))
            stack.append((block.level, child, False))
            continue
        if block.is_control:
            continue
        if block.name is None:
            raise ValueError("PyGan writer does not support unnamed payload records")

        _pop_to_parent_level(stack, block.level)
        parent = stack[-1][1]
        if block.type_code == 0:
            child = parent.rep(block.name)
            stack.append((block.level, child, False))
        elif block.type_code == 10:
            child = parent.lis(block.name, block.count)
            stack.append((block.level, child, True))
        else:
            parent[block.name] = _pygan_payload(block)
    return obj


def _pygan_payload(block: lcm_ascii.LcmBlock) -> np.ndarray | str:
    if block.type_code == 1:
        if not isinstance(block.data, tuple):
            raise TypeError(f"integer block {block.name!r} has non-tuple data")
        return np.asarray(block.data, dtype=np.int32)
    if block.type_code == 2:
        if not isinstance(block.data, tuple):
            raise TypeError(f"real block {block.name!r} has non-tuple data")
        # PyGan maps numpy.float32 to LCM type 2.  The existing
        # openmc2donjon ASCII writer emits all real payloads as type 2, so this
        # preserves the block type expected by downstream DRAGON/DONJON cards.
        return np.asarray(block.data, dtype=np.float32)
    if block.type_code == 3:
        if not isinstance(block.data, str):
            raise TypeError(f"string block {block.name!r} has non-string data")
        return block.data
    raise ValueError(f"unsupported LCM type_code={block.type_code}")


def _is_list_item(block: lcm_ascii.LcmBlock) -> bool:
    return block.name is None and block.data is None and block.count == -1 and bool(block.trailing)


def _list_item_index(block: lcm_ascii.LcmBlock) -> int:
    try:
        index = int(block.trailing)
    except ValueError as exc:
        raise ValueError(f"invalid list item tag {block.trailing!r}") from exc
    if index <= 0:
        raise ValueError(f"LCM list item tags are 1-based; got {block.trailing!r}")
    return index - 1


def _pop_to_parent_level(stack: list[tuple[int, Any, bool]], block_level: int) -> None:
    while len(stack) > 1 and stack[-1][0] >= block_level:
        stack.pop()


def _validate_pygan_object_name(name: str) -> None:
    if not name:
        raise ValueError("PyGan object name must be non-empty")
    if len(name) > 71:
        raise ValueError("PyGan object name must be at most 71 characters")

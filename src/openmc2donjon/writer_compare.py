"""Compare built-in ASCII and optional PyGan writer outputs semantically."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable, Sequence

import numpy as np

from . import lcm_ascii
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .pygan_backend import pygan_process_guard
from .pygan_writer import convert_mgxs_hdf5_with_pygan


WRITER_COMPARISON_SCHEMA = "openmc2donjon.writer-comparison.v1"


@dataclass(frozen=True, slots=True)
class WriterComparisonIssue:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


@dataclass(frozen=True, slots=True)
class WriterComparisonReport:
    input_h5: str
    output_format: str
    ok: bool
    rtol: float
    atol: float
    compared_payloads: int
    compared_real_payloads: int
    max_abs_diff: float
    max_rel_diff: float
    issues: tuple[WriterComparisonIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": WRITER_COMPARISON_SCHEMA,
            "input_h5": self.input_h5,
            "format": self.output_format,
            "ok": self.ok,
            "rtol": self.rtol,
            "atol": self.atol,
            "compared_payloads": self.compared_payloads,
            "compared_real_payloads": self.compared_real_payloads,
            "max_abs_diff": self.max_abs_diff,
            "max_rel_diff": self.max_rel_diff,
            "issue_count": len(self.issues),
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(slots=True)
class _TableNode:
    entries: dict[str, Any]


@dataclass(slots=True)
class _ListNode:
    count: int
    items: dict[int, Any]


@dataclass(frozen=True, slots=True)
class _Payload:
    type_code: int
    data: tuple[int, ...] | tuple[float, ...] | str


@dataclass(slots=True)
class _CompareState:
    issues: list[WriterComparisonIssue]
    compared_payloads: int = 0
    compared_real_payloads: int = 0
    max_abs_diff: float = 0.0
    max_rel_diff: float = 0.0

    def add_issue(self, path: str, message: str) -> None:
        self.issues.append(WriterComparisonIssue(path=path, message=message))


def compare_writer_backends(
    input_h5: str | Path,
    *,
    output_format: str = "multicompo",
    root_name: str = DEFAULT_ROOT_NAME,
    comment: str | None = None,
    burnup: float | None = None,
    h_factor_default: float | None = None,
    mixture_names: Sequence[str] | None = None,
    rtol: float = 1.0e-6,
    atol: float = 1.0e-8,
    summary_json: str | Path | None = None,
    keep_dir: str | Path | None = None,
) -> WriterComparisonReport:
    """Write with both backends and compare the resulting LCM trees."""

    with pygan_process_guard():
        source = Path(input_h5).expanduser().resolve()
        summary_path = (
            Path(summary_json).expanduser().resolve()
            if summary_json is not None
            else None
        )
        keep_path = (
            Path(keep_dir).expanduser().resolve()
            if keep_dir is not None
            else None
        )
        if output_format not in {"multicompo", "macrolib"}:
            raise ValueError("output_format must be 'multicompo' or 'macrolib'")
        suffix = ".macrolib.txt" if output_format == "macrolib" else ".mcompo.txt"
        if keep_path is None:
            with tempfile.TemporaryDirectory() as tmpdir:
                report = _compare_in_dir(
                    source,
                    Path(tmpdir).resolve(),
                    output_format=output_format,
                    suffix=suffix,
                    root_name=root_name,
                    comment=comment,
                    burnup=burnup,
                    h_factor_default=h_factor_default,
                    mixture_names=mixture_names,
                    rtol=rtol,
                    atol=atol,
                )
        else:
            keep_path.mkdir(parents=True, exist_ok=True)
            report = _compare_in_dir(
                source,
                keep_path,
                output_format=output_format,
                suffix=suffix,
                root_name=root_name,
                comment=comment,
                burnup=burnup,
                h_factor_default=h_factor_default,
                mixture_names=mixture_names,
                rtol=rtol,
                atol=atol,
            )
        if summary_path is not None:
            summary_path.write_text(
                json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report


def print_writer_comparison_report(report: WriterComparisonReport, *, max_issues: int = 20) -> None:
    state = "PASS" if report.ok else "FAIL"
    print("openmc2donjon writer backend comparison")
    print(f"  schema: {WRITER_COMPARISON_SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  format: {report.output_format}")
    print(f"  decision: {state}")
    print(
        "  payloads: "
        f"{report.compared_payloads} compared, "
        f"{report.compared_real_payloads} real payloads"
    )
    print(
        "  tolerance: "
        f"rtol={report.rtol:g} atol={report.atol:g} "
        f"max_abs={report.max_abs_diff:.6e} max_rel={report.max_rel_diff:.6e}"
    )
    if not report.issues:
        print("  issues: none")
        return
    print(f"  issues: {len(report.issues)}")
    for issue in report.issues[:max_issues]:
        print(f"    - {issue.path}: {issue.message}")
    remaining = len(report.issues) - max_issues
    if remaining > 0:
        print(f"    ... {remaining} more")


def _compare_in_dir(
    input_h5: Path,
    work_dir: Path,
    *,
    output_format: str,
    suffix: str,
    root_name: str,
    comment: str | None,
    burnup: float | None,
    h_factor_default: float | None,
    mixture_names: Sequence[str] | None,
    rtol: float,
    atol: float,
) -> WriterComparisonReport:
    ascii_path = work_dir / f"ascii{suffix}"
    pygan_path = work_dir / f"pygan{suffix}"
    if output_format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            input_h5,
            ascii_path,
            h_factor_default=h_factor_default,
            mixture_names=mixture_names,
        )
    else:
        convert_mgxs_hdf5(
            input_h5,
            ascii_path,
            root_name=root_name,
            comment=comment,
            burnup=burnup,
            h_factor_default=h_factor_default,
            mixture_names=mixture_names,
        )
    convert_mgxs_hdf5_with_pygan(
        input_h5,
        pygan_path,
        output_format=output_format,
        root_name=root_name,
        comment=comment,
        burnup=burnup,
        h_factor_default=h_factor_default,
        mixture_names=mixture_names,
    )
    state = _CompareState(issues=[])
    _compare_nodes(
        _blocks_to_tree(lcm_ascii.read_lcm_ascii(ascii_path)),
        _blocks_to_tree(lcm_ascii.read_lcm_ascii(pygan_path)),
        path="/",
        state=state,
        rtol=rtol,
        atol=atol,
    )
    return WriterComparisonReport(
        input_h5=str(input_h5),
        output_format=output_format,
        ok=not state.issues,
        rtol=rtol,
        atol=atol,
        compared_payloads=state.compared_payloads,
        compared_real_payloads=state.compared_real_payloads,
        max_abs_diff=state.max_abs_diff,
        max_rel_diff=state.max_rel_diff,
        issues=tuple(state.issues),
    )


def _blocks_to_tree(blocks: Iterable[lcm_ascii.LcmBlock]) -> _TableNode:
    root = _TableNode(entries={})
    stack: list[tuple[int, _TableNode | _ListNode]] = [(0, root)]
    for block in blocks:
        if _is_list_item(block):
            _pop_to_parent_level(stack, block.level)
            parent = stack[-1][1]
            if not isinstance(parent, _ListNode):
                raise ValueError(f"list item {block.trailing!r} at level {block.level} is not inside a list")
            item = _TableNode(entries={})
            parent.items[_list_item_index(block)] = item
            stack.append((block.level, item))
            continue
        if block.is_control:
            continue
        if block.name is None:
            raise ValueError("unnamed payload records cannot be compared as a semantic tree")
        _pop_to_parent_level(stack, block.level)
        parent = stack[-1][1]
        if not isinstance(parent, _TableNode):
            raise ValueError(f"named block {block.name!r} at level {block.level} is not inside a table")
        if block.type_code == 0:
            node = _TableNode(entries={})
            parent.entries[block.name] = node
            stack.append((block.level, node))
        elif block.type_code == 10:
            node = _ListNode(count=block.count, items={})
            parent.entries[block.name] = node
            stack.append((block.level, node))
        elif block.type_code in (1, 2, 3):
            if not isinstance(block.data, (tuple, str)):
                raise TypeError(f"block {block.name!r} has no payload")
            parent.entries[block.name] = _Payload(block.type_code, block.data)
        else:
            raise ValueError(f"unsupported LCM type_code={block.type_code}")
    return root


def _compare_nodes(
    ascii_node: Any,
    pygan_node: Any,
    *,
    path: str,
    state: _CompareState,
    rtol: float,
    atol: float,
) -> None:
    if type(ascii_node) is not type(pygan_node):
        state.add_issue(
            path,
            "kind mismatch: "
            f"ascii={type(ascii_node).__name__} pygan={type(pygan_node).__name__}",
        )
        return
    if isinstance(ascii_node, _TableNode):
        _compare_key_sets(path, ascii_node.entries, pygan_node.entries, state)
        for key in sorted(set(ascii_node.entries).intersection(pygan_node.entries)):
            _compare_nodes(
                ascii_node.entries[key],
                pygan_node.entries[key],
                path=f"{path.rstrip('/')}/{key}",
                state=state,
                rtol=rtol,
                atol=atol,
            )
    elif isinstance(ascii_node, _ListNode):
        if ascii_node.count != pygan_node.count:
            state.add_issue(path, f"list count mismatch: ascii={ascii_node.count} pygan={pygan_node.count}")
        _compare_key_sets(path, ascii_node.items, pygan_node.items, state)
        for index in sorted(set(ascii_node.items).intersection(pygan_node.items)):
            _compare_nodes(
                ascii_node.items[index],
                pygan_node.items[index],
                path=f"{path.rstrip('/')}[{index + 1}]",
                state=state,
                rtol=rtol,
                atol=atol,
            )
    elif isinstance(ascii_node, _Payload):
        _compare_payload(ascii_node, pygan_node, path=path, state=state, rtol=rtol, atol=atol)
    else:
        state.add_issue(path, f"unsupported comparison node {type(ascii_node).__name__}")


def _compare_payload(
    ascii_payload: _Payload,
    pygan_payload: _Payload,
    *,
    path: str,
    state: _CompareState,
    rtol: float,
    atol: float,
) -> None:
    state.compared_payloads += 1
    if ascii_payload.type_code != pygan_payload.type_code:
        state.add_issue(
            path,
            f"type mismatch: ascii={ascii_payload.type_code} pygan={pygan_payload.type_code}",
        )
        return
    if ascii_payload.type_code == 2:
        state.compared_real_payloads += 1
        left = np.asarray(ascii_payload.data, dtype=float)
        right = np.asarray(pygan_payload.data, dtype=float)
        if left.shape != right.shape:
            state.add_issue(path, f"real shape mismatch: ascii={left.shape} pygan={right.shape}")
            return
        diff = np.abs(left - right)
        if diff.size:
            max_abs = float(np.max(diff))
            denom = np.maximum(np.abs(left), atol)
            max_rel = float(np.max(diff / denom))
            state.max_abs_diff = max(state.max_abs_diff, max_abs)
            state.max_rel_diff = max(state.max_rel_diff, max_rel)
        if not np.allclose(left, right, rtol=rtol, atol=atol):
            state.add_issue(path, f"real payload differs beyond rtol={rtol:g}, atol={atol:g}")
    elif ascii_payload.data != pygan_payload.data:
        state.add_issue(path, "payload differs")


def _compare_key_sets(
    path: str,
    ascii_entries: dict[Any, Any],
    pygan_entries: dict[Any, Any],
    state: _CompareState,
) -> None:
    ascii_keys = set(ascii_entries)
    pygan_keys = set(pygan_entries)
    for key in sorted(ascii_keys - pygan_keys):
        state.add_issue(path, f"missing from PyGan output: {key!r}")
    for key in sorted(pygan_keys - ascii_keys):
        state.add_issue(path, f"extra in PyGan output: {key!r}")


def _is_list_item(block: lcm_ascii.LcmBlock) -> bool:
    return block.name is None and block.data is None and block.count == -1 and bool(block.trailing)


def _list_item_index(block: lcm_ascii.LcmBlock) -> int:
    index = int(block.trailing)
    if index <= 0:
        raise ValueError(f"LCM list item tags are 1-based; got {block.trailing!r}")
    return index - 1


def _pop_to_parent_level(stack: list[tuple[int, _TableNode | _ListNode]], block_level: int) -> None:
    while len(stack) > 1 and stack[-1][0] >= block_level:
        stack.pop()

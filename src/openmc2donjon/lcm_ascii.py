"""Reader and writer for GANLIB/LCM ASCII objects.

The format is used by DRAGON/DONJON LCMASC for objects such as
``L_MULTICOMPO``.  This module intentionally stays close to the wire format:
control records are represented explicitly and string payload padding is
preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Sequence

from .constants import (
    LCM_BLOCK_NAME_WIDTH,
    LCM_CHAR_CHUNK_WIDTH,
    LCM_DEFAULT_FLAGS,
    LCM_INT_FIELD_WIDTH,
    LCM_INTS_PER_LINE,
    LCM_LIST_TAG_WIDTH,
    LCM_REAL_FIELD_WIDTH,
    LCM_REAL_PRECISION,
    LCM_REALS_PER_LINE,
    LCM_TEXT_LINE_WIDTH,
)


HEADER_RE = re.compile(
    r"^->\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+<-\s*(.*?)\s*$"
)


@dataclass(frozen=True)
class LcmBlock:
    """One LCM ASCII record.

    ``name`` is ``None`` for control records and for unnamed list payload
    records emitted by some UTL dumps. String data is stored exactly as
    ``count * LCM_CHAR_CHUNK_WIDTH`` characters, including trailing blanks.
    """

    level: int
    flags: int
    type_code: int
    count: int
    name: str | None = None
    data: tuple[int, ...] | tuple[float, ...] | str | None = None
    trailing: str = ""
    line_no: int = 0

    @property
    def is_control(self) -> bool:
        return self.name is None and self.data is None

    def semantic_tuple(self) -> tuple:
        """Return a stable representation for round-trip semantic checks."""

        return (
            self.level,
            self.flags,
            self.type_code,
            self.count,
            self.name,
            self.data,
            self.trailing,
        )


def string_chunks(text: str) -> tuple[str, int]:
    """Pad ``text`` to a 4-character boundary and return (text, chunk_count)."""

    pad = (-len(text)) % LCM_CHAR_CHUNK_WIDTH
    padded = text + (" " * pad)
    return padded, len(padded) // LCM_CHAR_CHUNK_WIDTH


def pack_fixed_strings(values: Sequence[str], width: int) -> tuple[str, int]:
    """Pack fixed-width character data for an LCM type-3 block."""

    if width % LCM_CHAR_CHUNK_WIDTH != 0:
        raise ValueError("LCM character width must be a multiple of 4")
    for value in values:
        if len(value) > width:
            raise ValueError(
                f"fixed string {value!r} is longer than {width} characters"
            )
    text = "".join(value.ljust(width) for value in values)
    return text, len(text) // LCM_CHAR_CHUNK_WIDTH


def unpack_fixed_strings(text: str, width: int) -> list[str]:
    if width % LCM_CHAR_CHUNK_WIDTH != 0:
        raise ValueError("LCM character width must be a multiple of 4")
    return [text[i : i + width] for i in range(0, len(text), width)]


def read_lcm_ascii(path: str | Path) -> list[LcmBlock]:
    """Read a LCM ASCII file into an ordered block list."""

    lines = Path(path).read_text(errors="replace").splitlines()
    return parse_lcm_ascii_lines(lines)


def parse_lcm_ascii_text(text: str) -> list[LcmBlock]:
    return parse_lcm_ascii_lines(text.splitlines())


def parse_lcm_ascii_lines(lines: Sequence[str]) -> list[LcmBlock]:
    blocks: list[LcmBlock] = []
    i = 0
    while i < len(lines):
        match = HEADER_RE.match(lines[i])
        if match is None:
            i += 1
            continue

        level, flags, type_code, count = (
            int(match.group(k)) for k in range(1, 5)
        )
        trailing = match.group(5).strip()
        line_no = i + 1
        i += 1

        if level < 0 or (flags == 0 and type_code == 0) or type_code == 99:
            blocks.append(
                LcmBlock(
                    level,
                    flags,
                    type_code,
                    count,
                    trailing=trailing,
                    line_no=line_no,
                )
            )
            continue

        name = None
        if flags != 0:
            if i >= len(lines):
                raise ValueError(f"missing block name after header at line {line_no}")
            name = lines[i].rstrip()
            i += 1

        if type_code in (0, 10):
            data = None
        elif type_code == 1:
            data, i = _read_ints(lines, i, count)
        elif type_code == 2:
            data, i = _read_reals(lines, i, count)
        elif type_code == 3:
            data, i = _read_string(lines, i, count)
        else:
            raise ValueError(
                f"unsupported LCM type_code={type_code} at line {line_no}"
            )

        blocks.append(
            LcmBlock(
                level,
                flags,
                type_code,
                count,
                name=name,
                data=data,
                trailing=trailing,
                line_no=line_no,
            )
        )

    return blocks


def write_lcm_ascii(blocks: Iterable[LcmBlock], path: str | Path) -> None:
    Path(path).write_text(format_lcm_ascii(blocks))


def format_lcm_ascii(blocks: Iterable[LcmBlock]) -> str:
    lines: list[str] = []
    for block in blocks:
        lines.append(_format_header(block))
        if block.is_control:
            continue
        if block.name is not None:
            lines.append(f"{block.name:<{LCM_BLOCK_NAME_WIDTH}}")
        if block.type_code == 1:
            lines.extend(
                _format_ints(_coerce_ints(block.data), per_line=LCM_INTS_PER_LINE)
            )
        elif block.type_code == 2:
            lines.extend(
                _format_reals(_coerce_reals(block.data), per_line=LCM_REALS_PER_LINE)
            )
        elif block.type_code == 3:
            if not isinstance(block.data, str):
                raise TypeError(f"string block {block.name!r} has non-string data")
            expected = block.count * LCM_CHAR_CHUNK_WIDTH
            if len(block.data) != expected:
                raise ValueError(
                    f"string block {block.name!r} has {len(block.data)} chars, "
                    f"expected {expected}"
                )
            lines.extend(
                _format_ints(
                    (LCM_CHAR_CHUNK_WIDTH,) * block.count,
                    per_line=LCM_INTS_PER_LINE,
                )
            )
            lines.extend(_wrap_text(block.data, width=LCM_TEXT_LINE_WIDTH))
        elif block.type_code in (0, 10):
            pass
        else:
            raise ValueError(f"unsupported LCM type_code={block.type_code}")
    return "\n".join(lines) + "\n"


def block(
    level: int,
    name: str,
    type_code: int,
    data: Sequence[int] | Sequence[float] | str | None = None,
    *,
    count: int | None = None,
    flags: int = LCM_DEFAULT_FLAGS,
) -> LcmBlock:
    """Create a named LCM block with a computed count when possible."""

    if type_code in (0, 10):
        if count is None:
            count = -1
        payload = None
    elif type_code == 1:
        payload = tuple(int(x) for x in _require_sequence(data, name))
        count = len(payload) if count is None else count
    elif type_code == 2:
        payload = tuple(float(x) for x in _require_sequence(data, name))
        count = len(payload) if count is None else count
    elif type_code == 3:
        if not isinstance(data, str):
            raise TypeError(f"string block {name!r} requires str data")
        payload = data
        count = len(payload) // LCM_CHAR_CHUNK_WIDTH if count is None else count
        if len(payload) != count * LCM_CHAR_CHUNK_WIDTH:
            raise ValueError(
                f"string block {name!r} length must equal count*{LCM_CHAR_CHUNK_WIDTH}"
            )
    else:
        raise ValueError(f"unsupported LCM type_code={type_code}")
    return LcmBlock(level, flags, type_code, count, name=name, data=payload)


def string_block(level: int, name: str, text: str, *, width: int | None = None) -> LcmBlock:
    """Create a type-3 block from text."""

    if width is not None:
        if width % LCM_CHAR_CHUNK_WIDTH != 0:
            raise ValueError("LCM character width must be a multiple of 4")
        text = text[:width].ljust(width)
    text, count = string_chunks(text)
    return block(level, name, 3, text, count=count)


def control(level: int, *, trailing: int | str | None = None) -> LcmBlock:
    tag = "" if trailing is None else _format_trailing(trailing)
    return LcmBlock(level, 0, 0, 0, trailing=tag)


def list_item(level: int, index: int) -> LcmBlock:
    return LcmBlock(level, 0, 0, -1, trailing=f"{index:0{LCM_LIST_TAG_WIDTH}d}")


def list_placeholder(level: int, index: int) -> LcmBlock:
    return LcmBlock(level, 0, 99, 0, trailing=f"{index:0{LCM_LIST_TAG_WIDTH}d}")


def _read_ints(lines: Sequence[str], i: int, count: int) -> tuple[tuple[int, ...], int]:
    values: list[int] = []
    while len(values) < count:
        if i >= len(lines):
            raise ValueError("unexpected EOF while reading integer payload")
        values.extend(int(token) for token in lines[i].split())
        i += 1
    return tuple(values[:count]), i


def _read_reals(
    lines: Sequence[str], i: int, count: int
) -> tuple[tuple[float, ...], int]:
    values: list[float] = []
    while len(values) < count:
        if i >= len(lines):
            raise ValueError("unexpected EOF while reading real payload")
        values.extend(float(token.replace("D", "E")) for token in lines[i].split())
        i += 1
    return tuple(values[:count]), i


def _read_string(lines: Sequence[str], i: int, count: int) -> tuple[str, int]:
    ndecl = 0
    while ndecl < count:
        if i >= len(lines):
            raise ValueError("unexpected EOF while reading string declarations")
        for token in lines[i].split():
            if int(token) != LCM_CHAR_CHUNK_WIDTH:
                raise ValueError(f"unsupported string chunk width {token!r}")
            ndecl += 1
            if ndecl >= count:
                break
        i += 1

    nchars = count * LCM_CHAR_CHUNK_WIDTH
    text = ""
    while len(text) < nchars:
        if i >= len(lines):
            raise ValueError("unexpected EOF while reading string payload")
        take = min(nchars - len(text), len(lines[i]))
        text += lines[i][:take]
        i += 1
    return text, i


def _format_header(block: LcmBlock) -> str:
    line = (
        f"-> {block.level:7d}{block.flags:8d}{block.type_code:8d}"
        f"{block.count:8d}                                 <-"
    )
    if block.trailing:
        line += f"   {block.trailing}"
    else:
        line += "   "
    return line


def _format_ints(values: Sequence[int], *, per_line: int) -> list[str]:
    return [
        "".join(
            f"{int(value):{LCM_INT_FIELD_WIDTH}d}"
            for value in values[i : i + per_line]
        )
        for i in range(0, len(values), per_line)
    ]


def _format_reals(values: Sequence[float], *, per_line: int) -> list[str]:
    return [
        "".join(
            f"{float(value):{LCM_REAL_FIELD_WIDTH}.{LCM_REAL_PRECISION}E}"
            for value in values[i : i + per_line]
        )
        for i in range(0, len(values), per_line)
    ]


def _wrap_text(text: str, *, width: int) -> list[str]:
    if not text:
        return []
    return [text[i : i + width] for i in range(0, len(text), width)]


def _format_trailing(value: int | str) -> str:
    if isinstance(value, int):
        return f"{value:0{LCM_LIST_TAG_WIDTH}d}"
    return value.strip()


def _require_sequence(data: object, name: str) -> Sequence:
    if data is None or isinstance(data, str):
        raise TypeError(f"numeric block {name!r} requires a sequence payload")
    return data  # type: ignore[return-value]


def _coerce_ints(data: object) -> tuple[int, ...]:
    if not isinstance(data, tuple):
        raise TypeError("integer block payload must be a tuple")
    return tuple(int(x) for x in data)


def _coerce_reals(data: object) -> tuple[float, ...]:
    if not isinstance(data, tuple):
        raise TypeError("real block payload must be a tuple")
    return tuple(float(x) for x in data)

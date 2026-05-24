"""Bounded text-artifact preview endpoints for the localhost web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any


TEXT_PREVIEW_SCHEMA = "openmc2donjon.text-preview.v1"

_DEFAULT_BYTES = 32_768
_DEFAULT_LINES = 220
_LIMIT_BYTES = 262_144
_LIMIT_LINES = 2_000


def register_text_preview_routes(app: Any, *, mock_mode: bool) -> None:
    """Register ``GET /api/text-preview`` on a FastAPI app."""

    from fastapi import HTTPException, Query

    @app.get("/api/text-preview")
    def api_text_preview(
        path: str = Query(..., min_length=1),
        max_bytes: int = Query(_DEFAULT_BYTES, ge=1, le=_LIMIT_BYTES),
        max_lines: int = Query(_DEFAULT_LINES, ge=1, le=_LIMIT_LINES),
    ) -> dict[str, Any]:
        if mock_mode:
            return _mock_text_preview(path, max_bytes=max_bytes, max_lines=max_lines)
        real_path = _validate_text_preview_path(path, HTTPException)
        try:
            return _read_text_preview(real_path, max_bytes=max_bytes, max_lines=max_lines)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=403, detail=f"cannot read text preview: {exc}"
            ) from exc


def _validate_text_preview_path(raw: str, http_exception: Any) -> Path:
    """Resolve a user-supplied path and confirm it is a regular file."""

    real = Path(raw).expanduser().resolve()
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    return real


def _read_text_preview(
    real_path: Path,
    *,
    max_bytes: int,
    max_lines: int,
) -> dict[str, Any]:
    """Read a bounded UTF-8 preview of a generated text artifact."""

    file_size = real_path.stat().st_size
    with real_path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if b"\x00" in raw:
        raise ValueError(f"file looks binary, not text: {real_path}")
    return _text_preview_payload(
        str(real_path),
        raw,
        file_size=file_size,
        max_bytes=max_bytes,
        max_lines=max_lines,
    )


def _mock_text_preview(
    raw_path: str,
    *,
    max_bytes: int,
    max_lines: int,
) -> dict[str, Any]:
    text = _mock_ascii_preview_text(raw_path)
    return _text_preview_payload(
        raw_path,
        text.encode("utf-8"),
        file_size=len(text.encode("utf-8")),
        max_bytes=max_bytes,
        max_lines=max_lines,
    )


def _text_preview_payload(
    path: str,
    raw: bytes,
    *,
    file_size: int,
    max_bytes: int,
    max_lines: int,
) -> dict[str, Any]:
    byte_truncated = len(raw) > max_bytes
    preview_raw = raw[:max_bytes]
    text = preview_raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    line_truncated = len(lines) > max_lines
    visible_lines = lines[:max_lines]
    truncated_by: list[str] = []
    if byte_truncated:
        truncated_by.append("bytes")
    if line_truncated:
        truncated_by.append("lines")
    return {
        "schema": TEXT_PREVIEW_SCHEMA,
        "path": path,
        "file_size": file_size,
        "preview_bytes": len(preview_raw),
        "max_bytes": max_bytes,
        "displayed_lines": len(visible_lines),
        "decoded_lines": len(lines),
        "max_lines": max_lines,
        "truncated": bool(truncated_by),
        "truncated_by": truncated_by,
        "text": "\n".join(visible_lines),
    }


def _mock_ascii_preview_text(path: str) -> str:
    object_name = "L_MACROLIB" if path.endswith(".macrolib.txt") else "L_MULTICOMPO"
    return "\n".join(
        [
            "->  1 12  3  1 <-",
            "SIGNATURE",
            object_name,
            "->  1 12  0  0 <-",
            "GLOBAL",
            "->  2 12  1 40 <-",
            "STATE-VECTOR",
            "         9         7         9         1         0         0         0         0",
            "         0         1         0      2006         0         0         0         0",
            "->  2 12 10  9 <-",
            "MIXTURES",
            "->  3  0  0 -1 <-       1",
            "->  4 12  2  7 <-",
            "NTOT0",
            "  1.8923400000E+00  1.2857300000E+00  7.3012000000E-01  3.1184000000E-01  1.2820000000E-01",
            "  9.1080000000E-02  4.3120000000E-02",
            "->  4 12  2  7 <-",
            "NUSIGF",
            "  7.1080000000E-03  1.6210000000E-02  3.0170000000E-02  4.8020000000E-02  6.1990000000E-02",
            "  7.2140000000E-02  8.0030000000E-02",
            "->  4 12  1  7 <-",
            "NJJS00",
            "         1         2         2         3         3         3         4",
            "->  4 12  1  7 <-",
            "IJJS00",
            "         1         2         3         4         5         6         7",
            "->  4 12  2 18 <-",
            "SCAT00",
            "  1.2500000000E+00  6.8000000000E-02  9.7300000000E-01  1.4300000000E-02  6.2110000000E-01",
            "  9.8200000000E-03  3.1420000000E-01  2.1100000000E-03  1.2310000000E-01",
            "-> -4  0  0  0 <-",
        ]
    )

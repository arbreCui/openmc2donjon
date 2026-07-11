"""Bounded text-artifact preview endpoints for the localhost web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .filesystem import FilesystemScope


TEXT_PREVIEW_SCHEMA = "openmc2donjon.text-preview.v1"

_DEFAULT_BYTES = 32_768
_DEFAULT_LINES = 220
_LIMIT_BYTES = 262_144
_LIMIT_LINES = 2_000


def register_text_preview_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope | None = None,
) -> None:
    """Register ``GET /api/text-preview`` on a FastAPI app."""

    from fastapi import HTTPException, Query

    scope = filesystem_scope or FilesystemScope()

    @app.get("/api/text-preview")
    def api_text_preview(
        path: str = Query(..., min_length=1),
        max_bytes: int = Query(_DEFAULT_BYTES, ge=1, le=_LIMIT_BYTES),
        max_lines: int = Query(_DEFAULT_LINES, ge=1, le=_LIMIT_LINES),
    ) -> dict[str, Any]:
        if mock_mode:
            return _mock_text_preview(path, max_bytes=max_bytes, max_lines=max_lines)
        real_path = _validate_text_preview_path(path, HTTPException, scope)
        try:
            return _read_text_preview(real_path, max_bytes=max_bytes, max_lines=max_lines)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=403, detail=f"cannot read text preview: {exc}"
            ) from exc


def _validate_text_preview_path(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> Path:
    """Resolve a user-supplied path and confirm it is a regular file."""

    real = filesystem_scope.resolve(raw, http_exception)
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


def _is_mock_openmc_sph_path(path: str) -> bool:
    """True for paths that belong to the bundled OpenMC-side SPH minicase."""

    return "openmc-sph-minicase" in path or "mgxs_with_openmc_sph" in path


def _mock_ascii_preview_text(path: str) -> str:
    """Synthesize a complete-but-small DONJON ASCII artifact for mock mode.

    The block roster mirrors the real writers (``multicompo.py`` /
    ``macrolib.py``) so the frontend anatomy scan agrees with the mock
    convert preflight: the C5G7 story previews as 9 mixtures / 7 groups
    with ADF + NSPH records carried, and the OpenMC-side SPH minicase
    previews as 2 mixtures / 33 groups with one GROUP/*/NSPH block per
    group (matching the physics-summary fixture's
    ``macrolib_ascii_nsp_block_count``) and no ADF (its preflight
    reports ``adf_mixtures = 0``). ``*_uncorrected*`` paths drop the
    NSPH records. The text is deterministic per path so the sizes the
    mock convert/file endpoints report can stay in lockstep with it.
    """

    if _is_mock_openmc_sph_path(path):
        mixtures, groups, calculations, moments, adf = 2, 33, 2, 4, False
    else:
        mixtures, groups, calculations, moments, adf = 9, 7, 9, 2, True
    sph = "uncorrected" not in path
    if path.endswith(".macrolib.txt"):
        return _mock_macrolib_text(mixtures, groups, moments, adf=adf, sph=sph)
    return _mock_multicompo_text(
        mixtures, groups, calculations, moments, adf=adf, sph=sph
    )


def _mock_multicompo_text(
    mixtures: int,
    groups: int,
    calculations: int,
    moments: int,
    *,
    adf: bool,
    sph: bool,
) -> str:
    state = [0] * 40
    state[0] = mixtures
    state[1] = groups
    state[2] = calculations
    state[3] = calculations
    state[9] = 1
    state[11] = 2006
    state[15] = 3 if adf else 0
    library_state = [0] * 40
    library_state[0] = 1
    library_state[1] = 1
    library_state[2] = groups
    library_state[3] = moments
    library_state[13] = 1

    njjs = [min(index + 1, 2) for index in range(groups)]
    ijjs = [index + 1 for index in range(groups)]
    scat = _mock_xs(sum(njjs), 0.5, -0.4 / (sum(njjs) + 1))

    lines = [
        *_mock_block(1, 3, 1, "SIGNATURE"),
        "L_MULTICOMPO",
        *_mock_block(1, 0, 0, "GLOBAL"),
        *_mock_block(2, 1, 40, "STATE-VECTOR"),
        *_mock_int_lines(state),
        *_mock_block(2, 10, mixtures, "MIXTURES"),
        _mock_list_item(1),
        *_mock_block(2, 10, calculations, "CALCULATIONS"),
        _mock_list_item(1),
        *_mock_block(4, 3, 2, "ISOTOPESLIST"),
        "MACR",
        *_mock_block(4, 0, -1, "TREE"),
        *_mock_block(4, 2, groups, "NTOT0"),
        *_mock_float_lines(_mock_xs(groups, 0.19, 0.28)),
        *_mock_block(4, 2, groups, "NUSIGF"),
        *_mock_float_lines(_mock_xs(groups, 0.007, 0.011)),
        *_mock_block(4, 2, groups, "STRD"),
        *_mock_float_lines(_mock_xs(groups, 0.17, 0.25)),
        *_mock_block(4, 2, groups, "H-FACTOR"),
        *_mock_float_lines(_mock_xs(groups, 3.2e-12, 1.1e-13)),
    ]
    if sph:
        lines += [
            *_mock_block(4, 2, groups, "NSPH"),
            *_mock_float_lines(_mock_sph_factors(groups)),
        ]
    lines += [
        *_mock_block(4, 1, groups, "NJJS00"),
        *_mock_int_lines(njjs),
        *_mock_block(4, 1, groups, "IJJS00"),
        *_mock_int_lines(ijjs),
        *_mock_block(4, 2, len(scat), "SCAT00"),
        *_mock_float_lines(scat),
    ]
    # One NSPH record per calculation, like the real writer, so the
    # preview's NSPH count matches the preflight's sph_calculations.
    for calculation in range(2, calculations + 1):
        lines.append(_mock_list_item(calculation))
        if sph:
            lines += [
                *_mock_block(4, 2, groups, "NSPH"),
                *_mock_float_lines(_mock_sph_factors(groups)),
            ]
    if adf:
        lines += [
            *_mock_block(2, 0, -1, "ADF"),
            *_mock_block(3, 3, 4, "HADF"),
            "XMIN    XMAX    YMIN    YMAX",
        ]
    lines += [
        *_mock_block(2, 3, 1, "SIGNATURE"),
        "L_LIBRARY",
        *_mock_block(3, 1, 40, "STATE-VECTOR"),
        *_mock_int_lines(library_state),
        *_mock_block(3, 2, groups + 1, "ENERGY"),
        *_mock_float_lines(_mock_energy_bounds(groups)),
        "-> -4  0  0  0 <-",
    ]
    return "\n".join(lines)


def _mock_macrolib_text(
    mixtures: int,
    groups: int,
    moments: int,
    *,
    adf: bool,
    sph: bool,
) -> str:
    state = [0] * 40
    state[0] = groups
    state[1] = mixtures
    state[2] = moments
    state[3] = 1
    state[8] = 1
    state[11] = 3 if adf else 0
    state[13] = 1 if sph else 0

    lines = [
        *_mock_block(1, 3, 1, "SIGNATURE"),
        "L_MACROLIB",
        *_mock_block(1, 1, 40, "STATE-VECTOR"),
        *_mock_int_lines(state),
        *_mock_block(1, 2, groups + 1, "ENERGY"),
        *_mock_float_lines(_mock_energy_bounds(groups)),
        *_mock_block(1, 2, mixtures, "VOLUME"),
        *_mock_float_lines(_mock_xs(mixtures, 9.6, 0.4)),
        *_mock_block(1, 10, groups, "GROUP"),
        _mock_list_item(1),
        *_mock_block(3, 2, mixtures, "FLUX-INTG"),
        *_mock_float_lines(_mock_xs(mixtures, 1.0, -0.05)),
        *_mock_block(3, 2, mixtures, "NTOT0"),
        *_mock_float_lines(_mock_xs(mixtures, 0.19, 0.03)),
        *_mock_block(3, 2, mixtures, "DIFF"),
        *_mock_float_lines(_mock_xs(mixtures, 1.4, -0.02)),
        *_mock_block(3, 2, mixtures, "H-FACTOR"),
        *_mock_float_lines(_mock_xs(mixtures, 3.2e-12, 1.1e-13)),
    ]
    if sph:
        lines += [
            *_mock_block(3, 2, mixtures, "NSPH"),
            *_mock_float_lines(_mock_sph_factors(mixtures)),
        ]
    lines += [
        *_mock_block(3, 2, mixtures, "SIGS00"),
        *_mock_float_lines(_mock_xs(mixtures, 0.16, 0.02)),
        *_mock_block(3, 2, mixtures, "SCAT00"),
        *_mock_float_lines(_mock_xs(mixtures, 0.15, 0.02)),
        *_mock_block(3, 1, mixtures, "NJJS00"),
        *_mock_int_lines([1] * mixtures),
        *_mock_block(3, 1, mixtures, "IJJS00"),
        *_mock_int_lines([1] * mixtures),
    ]
    # One GROUP/*/NSPH block per remaining group so the preview carries
    # the full DSPH-consumable NSPH set (kept compact to stay inside
    # the default preview line budget).
    for group in range(2, groups + 1):
        lines.append(_mock_list_item(group))
        if sph:
            lines += [
                *_mock_block(3, 2, mixtures, "NSPH"),
                *_mock_float_lines(_mock_sph_factors(mixtures)),
            ]
    if adf:
        lines += [
            *_mock_block(1, 0, -1, "ADF"),
            *_mock_block(2, 1, 1, "NTYPE"),
            *_mock_int_lines([4]),
            *_mock_block(2, 3, 4, "HADF"),
            "XMIN    XMAX    YMIN    YMAX",
        ]
    lines.append("-> -4  0  0  0 <-")
    return "\n".join(lines)


def _mock_block(level: int, type_code: int, count: int, name: str) -> list[str]:
    return [f"-> {level:2d} 12 {type_code:2d} {count:2d} <-", name]


def _mock_list_item(index: int) -> str:
    return f"->  3  0  0 -1 <-       {index}"


def _mock_float_lines(values: list[float]) -> list[str]:
    return [
        "".join(f"  {value:.10E}" for value in values[index : index + 5])
        for index in range(0, len(values), 5)
    ]


def _mock_int_lines(values: list[int]) -> list[str]:
    return [
        "".join(f"{value:10d}" for value in values[index : index + 8])
        for index in range(0, len(values), 8)
    ]


def _mock_xs(count: int, base: float, step: float) -> list[float]:
    return [base + step * index for index in range(count)]


def _mock_energy_bounds(groups: int) -> list[float]:
    # Descending 10 MeV -> 1e-4 eV mock grid.
    return [1.0e7 * (1.0e-11 ** (index / groups)) for index in range(groups + 1)]


def _mock_sph_factors(count: int) -> list[float]:
    # Alternate around unity like a real SPH factor vector.
    return [
        1.0 + 0.05 * ((-1.0) ** index) * ((index % 4) + 1) / 4.0
        for index in range(count)
    ]

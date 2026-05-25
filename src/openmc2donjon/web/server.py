"""FastAPI application factory for the openmc2donjon web UI.

Endpoints (M1 scope):

- ``GET /api/health`` - backend liveness + mock flag + package version.
- ``GET /api/commands`` - web/CLI command catalog used by the command
  workspace page.
- ``GET /api/inspect?path=...`` - file-level summary of an MGXS HDF5
  handoff, plus standard energy-mesh ID match when present.
- ``GET /api/inspect/mixture?path=...&mixture=...&moment=0`` - per-mixture
  cross sections and one scatter moment.
- ``GET /api/audit?path=...`` - returns the JSON payload written by
  ``run-sph-loop`` (schema ``openmc2donjon.sph-loop.v1``). The
  response is the raw parsed JSON; the frontend chooses what to
  surface.
- ``GET /api/text-preview?path=...`` - bounded UTF-8/ASCII preview for
  generated text artifacts such as ``.mcompo.txt`` and ``.macrolib.txt``.
- ``GET /api/file-status?path=...`` - single-path existence / kind /
  size probe used by localhost workflow cards.
- ``GET /api/bundle/inspect?manifest=...`` - read-only bundle manifest
  validation summary used by converter delivery cards.

The ``create_app`` factory keeps the mock flag out of module globals so
the CLI ``serve`` command can pass it in explicitly. Mock mode returns
bundled fixture JSONs from ``src/openmc2donjon/web/fixtures/`` so the
frontend can be exercised without a real HDF5 on disk.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np

from .. import __version__
from .._logging import get_logger
from ..energy_groups import identify_mesh
from ..mgxs_inspect import _report_payload, inspect_file
from ..mgxs_physics_checks import scatter_moment_matrix
from .bundle import register_bundle_routes
from .commands import register_command_routes
from .convert import register_convert_routes
from .openmc_workflow import register_openmc_workflow_routes
from .text_preview import (
    TEXT_PREVIEW_SCHEMA as TEXT_PREVIEW_SCHEMA,
    register_text_preview_routes,
)


logger = get_logger("web.server")

DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

INSPECT_SCHEMA = "openmc2donjon.mgxs-inspect.v1"
MIXTURE_SCHEMA = "openmc2donjon.mgxs-mixture.v1"
FILES_SCHEMA = "openmc2donjon.files.v1"
FILE_STATUS_SCHEMA = "openmc2donjon.file-status.v1"
AUDIT_SCHEMA = "openmc2donjon.sph-loop.v1"
_MOCK_REFERENCE_STD_DEV_DATASET = "openmc_volume_flux_std_dev"
_MOCK_REFERENCE_STD_DEV_MAX_REL = 1.8e-2
_MOCK_REFERENCE_STD_DEV_LIMIT = 5.0e-2
_MOCK_REFERENCE_STD_DEV_WORST = (
    "mixture=ASM_Y02_X03 group=2 mean=9.201245e-04 "
    "std_dev=1.656224e-05 rel=1.800000e-02"
)
_MOCK_AUDIT_STD_DEV_PATH_MARKERS = (
    "ref_stddev",
    "reference_std_dev",
    "reference-std-dev",
    "with_reference_std_dev",
    "with-reference-std-dev",
)

# Hard caps on the ``/api/inspect`` peek panel so a pathological HDF5
# (hundreds of root attrs, thousands of top-level datasets) can't blow
# up the response payload or the frontend layout. The totals stay
# accurate so the UI can honestly say "showing 200 of 1432 entries".
_PEEK_MAX_ROOT_ATTRS = 50
_PEEK_MAX_TOP_LEVEL_KEYS = 200

# Synthetic directory tree returned by the file browser when running in
# ``--mock``. Three levels deep, mimicking the typical ``$HOME/openmc-runs``
# layout users will navigate in production.
_MOCK_HOME = "/mock/home"
_MOCK_TREE: dict[str, list[tuple[str, str, int | None]]] = {
    _MOCK_HOME: [
        ("openmc-runs", "dir", None),
        ("scratch", "dir", None),
        ("notes.txt", "file", 1024),
    ],
    f"{_MOCK_HOME}/openmc-runs": [
        ("c5g7", "dir", None),
        ("full-core-sph", "dir", None),
        ("u238_33g", "dir", None),
    ],
    f"{_MOCK_HOME}/openmc-runs/c5g7": [
        ("handoff.h5", "file", 832_000),
        ("handoff_aug.h5", "file", 856_000),
        ("bundle", "dir", None),
        ("README.md", "file", 1_024),
    ],
    f"{_MOCK_HOME}/openmc-runs/c5g7/bundle": [
        ("manifest.json", "file", 2_048),
        ("handoff.h5", "file", 832_000),
        ("out.mcompo.txt", "file", 184_320),
        ("convert_summary.json", "file", 8_192),
    ],
    f"{_MOCK_HOME}/openmc-runs/full-core-sph": [
        # ``sph_loop_summary.json`` is what ``/api/audit`` consumes;
        # the fixture is a sanitized real 10-iteration DONJON-backed
        # full-core minicase, so the audit page exercises a realistic
        # convergence history rather than a perfect two-step toy loop.
        ("sph_loop_summary.json", "file", 143_282),
        # Same loop history, but with reference-flux std_dev metadata
        # and the corresponding production acceptance gates marked
        # pass. This gives the audit UI a positive demo case for the
        # newer OpenMC reference-flux uncertainty workflow without
        # duplicating the large JSON fixture.
        ("sph_loop_summary_ref_stddev.json", "file", 143_840),
    ],
    f"{_MOCK_HOME}/openmc-runs/u238_33g": [
        ("mgxs.h5", "file", 1_240_000),
        ("mgxs_with_sph.h5", "file", 1_250_000),
    ],
    f"{_MOCK_HOME}/scratch": [
        ("tmp_run.h5", "file", 256_000),
    ],
}

# Cross sections to extract when reading per-mixture detail. ``chi`` is
# included so the frontend can show source spectrum alongside reaction
# rates; it lives on a different axis than the absorption / fission
# group so the plot UI should treat it separately.
_MIXTURE_XS_DATASETS: tuple[str, ...] = (
    "total",
    "absorption",
    "fission",
    "nu_fission",
    "chi",
)


def create_app(
    *,
    mock_mode: bool = False,
    extra_origins: tuple[str, ...] = (),
) -> Any:
    """Build a configured FastAPI application instance.

    The CORS allow-list always includes ``DEFAULT_CORS_ORIGINS`` (the
    Next.js dev server). Any ``extra_origins`` are appended and the
    resulting list is order-preserving deduplicated, so callers can
    grow the list without losing the defaults.

    Importing FastAPI lazily lets the package work without the ``web``
    extra installed for users who only need the CLI.
    """

    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - exercised via CLI handler
        raise RuntimeError(
            "openmc2donjon web extras are not installed. "
            'Install with: pip install -e ".[web]"',
        ) from exc

    app = FastAPI(
        title="openmc2donjon",
        description="Web interface for the OpenMC -> DRAGON/DONJON handoff pipeline.",
        version=__version__,
    )

    allow_origins = list(dict.fromkeys((*DEFAULT_CORS_ORIGINS, *extra_origins)))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mock_mode": mock_mode,
            "version": __version__,
        }

    register_command_routes(app)
    register_openmc_workflow_routes(app, mock_mode=mock_mode)

    @app.get("/api/inspect")
    def api_inspect(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _load_fixture("inspect_handoff.json")
        real_path = _validate_hdf5_path(path, HTTPException)
        try:
            report = inspect_file(real_path)
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=422, detail=f"inspect failed: {exc}"
            ) from exc
        payload = _report_payload(report)
        payload["schema"] = INSPECT_SCHEMA
        bounds, mesh_match = _read_bounds_and_mesh(real_path)
        payload["energy_bounds"] = bounds
        payload["mesh_match"] = mesh_match
        # Generic HDF5 peek (root attrs + top-level entries) makes the
        # response useful even for files that don't match the MGXS
        # contract (boundary currents, ADF sidecars, etc.): the user
        # at least sees what KIND of HDF5 they pointed at instead of
        # a bare "0 mixtures, FAIL".
        peek = _read_top_level_peek(real_path)
        payload.update(peek)
        return payload

    @app.get("/api/files")
    def api_files(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _mock_list_dir(path, HTTPException)
        return _list_dir(path, HTTPException)

    @app.get("/api/file-status")
    def api_file_status(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _mock_file_status(path)
        return _file_status(path)

    register_text_preview_routes(app, mock_mode=mock_mode)

    register_convert_routes(app, mock_mode=mock_mode)
    register_bundle_routes(app, mock_mode=mock_mode)

    @app.get("/api/inspect/mixture")
    def api_inspect_mixture(
        path: str = Query(..., min_length=1),
        mixture: str = Query(..., min_length=1),
        moment: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        if mock_mode:
            return _mock_mixture(mixture, moment, HTTPException)
        real_path = _validate_hdf5_path(path, HTTPException)
        try:
            return _read_mixture_detail(real_path, mixture, moment, HTTPException)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"mixture read failed: {exc}"
            ) from exc

    @app.get("/api/audit")
    def api_audit(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        # Returns the raw ``run-sph-loop`` summary JSON. The frontend
        # decides which sections to surface, but the backend still
        # validates the fields M6-A dereferences so an arbitrary JSON
        # object can't crash the page at render time.
        if mock_mode:
            payload = _mock_audit_summary(path)
            _validate_audit_summary_payload(payload, HTTPException)
            return payload
        real_path = _validate_audit_path(path, HTTPException)
        try:
            payload = json.loads(real_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=422, detail=f"audit read failed: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=422,
                detail="audit file is not a JSON object",
            )
        _validate_audit_summary_payload(payload, HTTPException)
        return payload

    if mock_mode:
        logger.info("openmc2donjon web server starting in MOCK mode")
    else:
        logger.info("openmc2donjon web server starting in LIVE mode")

    return app


def _validate_hdf5_path(raw: str, http_exception: Any) -> Path:
    """Resolve a user-supplied path and confirm it is a readable HDF5 file."""

    import h5py

    real = Path(raw).expanduser().resolve()
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    try:
        is_hdf5 = h5py.is_hdf5(str(real))
    except OSError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read path: {exc}"
        ) from exc
    if not is_hdf5:
        raise http_exception(status_code=400, detail=f"not an HDF5 file: {raw}")
    return real


def _validate_audit_path(raw: str, http_exception: Any) -> Path:
    """Resolve a user-supplied path and confirm it is a regular file.

    Schema-level validation happens after parsing so users get a
    precise 422 when the file is JSON but not a SPH loop summary.
    """

    real = Path(raw).expanduser().resolve()
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    return real


def _validate_audit_summary_payload(payload: dict[str, Any], http_exception: Any) -> None:
    """Validate the SPH-loop summary fields consumed by the M6-A page."""

    errors: list[str] = []
    _require_type(payload, "schema", str, errors)
    if payload.get("schema") != AUDIT_SCHEMA:
        errors.append(f"schema must be {AUDIT_SCHEMA!r}")
    for key in ("decision", "package_version", "stop_reason"):
        _require_type(payload, key, str, errors)
    for key in ("iterations", "completed_iterations"):
        _require_type(payload, key, int, errors)
    for key in ("converged", "convergence_enabled"):
        _require_type(payload, key, bool, errors)
    for key in ("sph_change_tolerance", "flux_ratio_tolerance"):
        _require_number_or_none(payload, key, errors)
    if "min_iterations" in payload:
        _require_int_or_none(payload, "min_iterations", errors)
    if "fail_on_nonconvergence" in payload:
        _require_bool_or_none(payload, "fail_on_nonconvergence", errors)
    _validate_audit_convergence(payload.get("convergence"), errors)
    _validate_audit_quality(payload.get("quality"), errors)
    _validate_audit_rows(payload.get("audit_rows"), errors)
    _validate_audit_solves(payload.get("solves"), errors)

    acceptance = payload.get("acceptance")
    if not isinstance(acceptance, dict):
        errors.append("acceptance must be an object")
    else:
        _validate_audit_gate("acceptance", acceptance, require_errors=False, errors=errors)

    production_audit = payload.get("production_audit")
    if not isinstance(production_audit, dict):
        errors.append("production_audit must be an object")
    else:
        _validate_audit_gate(
            "production_audit",
            production_audit,
            require_errors=True,
            errors=errors,
        )

    if errors:
        raise http_exception(
            status_code=422,
            detail="invalid SPH loop summary: " + "; ".join(errors),
        )


def _validate_audit_gate(
    name: str,
    payload: dict[str, Any],
    *,
    require_errors: bool,
    errors: list[str],
) -> None:
    _require_type(payload, "passed", bool, errors, prefix=name)
    if name == "acceptance":
        _require_type(payload, "enabled", bool, errors, prefix=name)
    checks = payload.get("checks")
    if not isinstance(checks, list):
        errors.append(f"{name}.checks must be a list")
    else:
        for index, item in enumerate(checks):
            if not isinstance(item, dict):
                errors.append(f"{name}.checks[{index}] must be an object")
                continue
            _require_type(item, "passed", bool, errors, prefix=f"{name}.checks[{index}]")
    if require_errors:
        gate_errors = payload.get("errors")
        if not isinstance(gate_errors, list) or not all(
            isinstance(item, str) for item in gate_errors
        ):
            errors.append(f"{name}.errors must be a list of strings")


def _validate_audit_convergence(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("convergence must be a list")
        return
    for index, item in enumerate(value):
        prefix = f"convergence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _require_type(item, "iteration", int, errors, prefix=prefix)
        _require_type(item, "converged", bool, errors, prefix=prefix)
        _require_type(item, "clipped_count", int, errors, prefix=prefix)
        _require_number_or_none(item, "clipped_fraction", errors, prefix=prefix)
        for key in (
            "sph_max_abs_change",
            "sph_max_rel_change",
            "flux_ratio_max_residual",
        ):
            _require_number_or_none(item, key, errors, prefix=prefix)
        for key in ("worst_residual_bins", "clipped_bins"):
            if not isinstance(item.get(key), list):
                errors.append(f"{prefix}.{key} must be a list")


def _validate_audit_quality(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("quality must be an object")
        return
    for key in (
        "initial_flux_ratio_max_residual",
        "final_flux_ratio_max_residual",
        "final_to_initial_flux_residual_ratio",
        "final_clipped_fraction",
        "maximum_clipped_fraction",
        "final_sph_minimum",
        "final_sph_maximum",
    ):
        _require_number_or_none(value, key, errors, prefix="quality")
    for key in ("final_clipped_count", "maximum_clipped_count"):
        _require_int_or_none(value, key, errors, prefix="quality")
    for key in ("flux_residual_improved", "clipping_observed"):
        _require_bool_or_none(value, key, errors, prefix="quality")
    for key in ("initial_worst_residual_bin", "final_worst_residual_bin"):
        _validate_optional_residual_bin(value.get(key), errors, prefix=f"quality.{key}")
    for key in ("final_worst_residual_bins", "final_clipped_bins"):
        _validate_residual_bin_list(value.get(key), errors, prefix=f"quality.{key}")


def _validate_residual_bin_list(value: Any, errors: list[str], *, prefix: str) -> None:
    if not isinstance(value, list):
        errors.append(f"{prefix} must be a list")
        return
    for index, item in enumerate(value):
        _validate_optional_residual_bin(item, errors, prefix=f"{prefix}[{index}]")


def _validate_optional_residual_bin(
    value: Any,
    errors: list[str],
    *,
    prefix: str,
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object or null")
        return
    _require_string_or_none(value, "mixture", errors, prefix=prefix)
    _require_int_or_none(value, "group", errors, prefix=prefix)
    for key in (
        "residual",
        "signed_residual",
        "raw_update",
        "sph",
        "previous_sph",
        "unclipped_sph",
        "reference_flux",
        "low_order_flux",
    ):
        if key in value:
            _require_number_or_none(value, key, errors, prefix=prefix)
    if "clipped" in value:
        _require_bool_or_none(value, "clipped", errors, prefix=prefix)


def _validate_audit_rows(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("audit_rows must be a list")
        return
    for index, item in enumerate(value):
        prefix = f"audit_rows[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _require_type(item, "stage", str, errors, prefix=prefix)
        _require_type(item, "iteration", int, errors, prefix=prefix)
        for key in (
            "keff",
            "sph_minimum",
            "sph_maximum",
            "sph_max_abs_change",
            "sph_max_rel_change",
            "flux_ratio_max_residual",
            "worst_residual_raw_update",
            "worst_residual",
        ):
            _require_number_or_none(item, key, errors, prefix=prefix)
        _require_string_or_none(item, "worst_residual_mixture", errors, prefix=prefix)
        _require_int_or_none(item, "worst_residual_group", errors, prefix=prefix)
        _require_bool_or_none(item, "converged", errors, prefix=prefix)
        for key in ("solve_result", "ascii_output", "postprocess_output"):
            _require_string_or_none(item, key, errors, prefix=prefix)


def _validate_audit_solves(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("solves must be a list")
        return
    for index, item in enumerate(value):
        prefix = f"solves[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _require_type(item, "iteration", int, errors, prefix=prefix)
        _require_string_list(item, "command", errors, prefix=prefix)
        for key in ("cwd", "ascii_input", "result", "stdout", "stderr"):
            _require_type(item, key, str, errors, prefix=prefix)
        for key in ("returncode", "result_bytes", "flux_vector_count", "flux_unknown_count"):
            _require_type(item, key, int, errors, prefix=prefix)
        _require_number_or_none(item, "keff", errors, prefix=prefix)


def _require_type(
    payload: dict[str, Any],
    key: str,
    expected: type,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    value = payload.get(key)
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        qualified = key if prefix is None else f"{prefix}.{key}"
        errors.append(f"{qualified} must be {expected.__name__}")


def _require_string_list(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    qualified = key if prefix is None else f"{prefix}.{key}"
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{qualified} must be a list of strings")


def _require_string_or_none(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    qualified = key if prefix is None else f"{prefix}.{key}"
    if key not in payload:
        errors.append(f"{qualified} must be string or null")
        return
    value = payload[key]
    if value is not None and not isinstance(value, str):
        errors.append(f"{qualified} must be string or null")


def _require_int_or_none(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    qualified = key if prefix is None else f"{prefix}.{key}"
    if key not in payload:
        errors.append(f"{qualified} must be int or null")
        return
    value = payload[key]
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        errors.append(f"{qualified} must be int or null")


def _require_bool_or_none(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    qualified = key if prefix is None else f"{prefix}.{key}"
    if key not in payload:
        errors.append(f"{qualified} must be bool or null")
        return
    value = payload[key]
    if value is not None and not isinstance(value, bool):
        errors.append(f"{qualified} must be bool or null")


def _require_number_or_none(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    qualified = key if prefix is None else f"{prefix}.{key}"
    if key not in payload:
        errors.append(f"{qualified} must be number or null")
        return
    value = payload[key]
    if value is None:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{qualified} must be number or null")


def _read_top_level_peek(real_path: Path) -> dict[str, Any]:
    """Read root attrs and one-level group/dataset names for a peek panel.

    Returns a dict with five keys:

    - ``root_attrs``: list of ``{name, value}`` (scalar / short-vector
      attrs only; unsupported dtypes are silently dropped).
    - ``top_level_keys``: list of ``{name, kind, shape, dtype}`` for
      the immediate children of the HDF5 root.
    - ``root_attrs_total``: total attribute count in the file (before
      cap / drop).
    - ``top_level_keys_total``: total root-level entry count in the
      file (before cap).
    - ``peek_truncated``: convenience flag — true when either list is
      shorter than its total. Frontend renders a "showing X of Y" hint
      so a 1432-entry file doesn't silently hide most of itself.

    Returns empty lists / zero totals if the file can't be opened.
    """

    import h5py

    empty = {
        "root_attrs": [],
        "top_level_keys": [],
        "root_attrs_total": 0,
        "top_level_keys_total": 0,
        "peek_truncated": False,
    }
    try:
        with h5py.File(real_path, "r") as h5:
            attr_names = list(h5.attrs.keys())
            root_attrs: list[dict[str, Any]] = []
            for name in attr_names:
                if len(root_attrs) >= _PEEK_MAX_ROOT_ATTRS:
                    break
                value = _attr_to_jsonable(h5.attrs[name])
                if value is None:
                    continue
                root_attrs.append({"name": str(name), "value": value})

            all_top_names = sorted(h5)
            top_level_keys: list[dict[str, Any]] = []
            for name in all_top_names[:_PEEK_MAX_TOP_LEVEL_KEYS]:
                node = h5[name]
                if isinstance(node, h5py.Group):
                    top_level_keys.append(
                        {
                            "name": str(name),
                            "kind": "group",
                            "shape": None,
                            "dtype": None,
                        }
                    )
                else:
                    dataset = node
                    try:
                        shape = list(dataset.shape)
                        dtype = str(dataset.dtype)
                    except (AttributeError, OSError):
                        shape = None
                        dtype = None
                    top_level_keys.append(
                        {
                            "name": str(name),
                            "kind": "dataset",
                            "shape": shape,
                            "dtype": dtype,
                        }
                    )
            root_attrs_total = len(attr_names)
            top_level_keys_total = len(all_top_names)
    except (OSError, ValueError, KeyError):
        return empty
    return {
        "root_attrs": root_attrs,
        "top_level_keys": top_level_keys,
        "root_attrs_total": root_attrs_total,
        "top_level_keys_total": top_level_keys_total,
        "peek_truncated": (
            len(root_attrs) < root_attrs_total
            or len(top_level_keys) < top_level_keys_total
        ),
    }


def _attr_to_jsonable(value: Any) -> Any:
    """Convert an HDF5 attribute value to a JSON-friendly scalar.

    Returns ``None`` for blobs we don't want to ship (large arrays,
    unsupported dtypes), the caller will skip them. Bytes / numpy
    strings are decoded; numpy scalars are unwrapped via ``.item()``.
    """

    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        return value
    if hasattr(value, "item") and not hasattr(value, "shape"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            return None
    if hasattr(value, "shape"):
        shape = value.shape
        if shape == ():
            try:
                return _attr_to_jsonable(value.item())
            except (AttributeError, ValueError):
                return None
        if len(shape) == 1 and shape[0] <= 8:
            # Short 1D vectors render nicely as a list (energy bounds,
            # small enumerations, etc.); anything bigger gets dropped
            # to keep the peek payload bounded.
            try:
                return [_attr_to_jsonable(v) for v in value.tolist()]
            except (AttributeError, ValueError):
                return None
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple)) and len(value) <= 8:
        return [_attr_to_jsonable(v) for v in value]
    return None


def _read_bounds_and_mesh(
    real_path: Path,
) -> tuple[list[float] | None, dict[str, Any] | None]:
    """Read ``/energy_bounds`` once and reuse it for mesh ID detection.

    Returns ``(bounds_list, mesh_dict)``. Either side can be ``None``: no
    ``energy_bounds`` dataset means no bounds and no mesh match; bounds
    present but no catalog hit means bounds list with ``mesh_dict=None``.
    """

    import h5py

    try:
        with h5py.File(real_path, "r") as h5:
            if "energy_bounds" not in h5:
                return None, None
            bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
    except (OSError, KeyError, ValueError):
        return None, None
    bounds_list = bounds.tolist()
    mesh = identify_mesh(bounds)
    if mesh is None:
        return bounds_list, None
    return bounds_list, {
        "id": mesh.mesh_id,
        "name": mesh.name,
        "short": mesh.short,
        "n_groups": mesh.n_groups,
        "purpose": mesh.purpose,
        "description": mesh.description,
    }


def _read_mixture_detail(
    real_path: Path,
    mixture_name: str,
    moment: int,
    http_exception: Any,
) -> dict[str, Any]:
    """Pull per-mixture cross sections and one scatter moment out of HDF5."""

    import h5py

    with h5py.File(real_path, "r") as h5:
        mixtures = h5.get("mixtures")
        if mixtures is None:
            raise http_exception(
                status_code=422, detail="HDF5 has no /mixtures group"
            )
        mix_group = mixtures.get(mixture_name)
        if mix_group is None:
            raise http_exception(
                status_code=404,
                detail=f"mixture not found: {mixture_name}",
            )

        ngroups_attr = h5.attrs.get("energy_groups")
        try:
            ngroups = int(ngroups_attr) if ngroups_attr is not None else None
        except (TypeError, ValueError):
            ngroups = None

        legendre_attr = h5.attrs.get("legendre_order")
        try:
            legendre_order = int(legendre_attr) if legendre_attr is not None else None
        except (TypeError, ValueError):
            legendre_order = None

        cross_sections: dict[str, list[float] | None] = {}
        for name in _MIXTURE_XS_DATASETS:
            if name in mix_group:
                cross_sections[name] = np.asarray(
                    mix_group[name][:], dtype=float
                ).reshape(-1).tolist()
            else:
                cross_sections[name] = None

        volume = _float_attr(mix_group.attrs, "volume")
        temperature = _float_attr(mix_group.attrs, "temperature")

        scatter_payload = _scatter_moment_payload(
            mix_group, ngroups=ngroups, legendre_order=legendre_order, moment=moment
        )
        if scatter_payload is not None and not scatter_payload.get("values"):
            # Requested moment out of range; surface it as a 404 so the
            # frontend can fall back to moment=0 rather than render an
            # empty heatmap.
            raise http_exception(
                status_code=404,
                detail=(
                    f"scatter moment {moment} not available for "
                    f"mixture {mixture_name}"
                ),
            )

        return {
            "schema": MIXTURE_SCHEMA,
            "path": str(real_path),
            "mixture": mixture_name,
            "energy_groups": ngroups,
            "legendre_order": legendre_order,
            "volume": volume,
            "temperature": temperature,
            "cross_sections": cross_sections,
            "scatter": scatter_payload,
        }


def _scatter_moment_payload(
    mix_group: Any,
    *,
    ngroups: int | None,
    legendre_order: int | None,
    moment: int,
) -> dict[str, Any] | None:
    """Return ``{axes, shape, moment_index, values}`` for one scatter moment.

    Returns ``None`` if the mixture has no scatter dataset at all so the
    endpoint can tell the difference between "no scatter" (None) and
    "moment out of range" (dict with empty ``values``, surfaced as 404).
    """

    if "scatter_matrix" not in mix_group:
        return None
    dataset = mix_group["scatter_matrix"]
    axes_raw = dataset.attrs.get("axes")
    axes = (
        axes_raw.decode("utf-8")
        if isinstance(axes_raw, (bytes, bytearray))
        else axes_raw
        if isinstance(axes_raw, str)
        else None
    )
    arr = np.asarray(dataset[:], dtype=float)
    shape = list(arr.shape)
    if ngroups is None:
        # Best-effort fall back to whichever symmetric dimension matches.
        candidates = [s for s in shape if s > 0]
        ngroups = candidates[0] if candidates else 0
    matrix = scatter_moment_matrix(
        arr,
        axes,
        ngroups,
        legendre_order if legendre_order is not None else max(0, shape[0] - 1),
        moment=moment,
    )
    return {
        "axes": axes,
        "shape": shape,
        "moment_index": moment,
        "values": matrix.tolist() if matrix is not None else [],
    }


def _float_attr(attrs: Any, name: str) -> float | None:
    if name not in attrs:
        return None
    try:
        return float(attrs[name])
    except (TypeError, ValueError):
        return None


def _list_dir(raw: str, http_exception: Any) -> dict[str, Any]:
    """Real-filesystem implementation of ``/api/files`` (live mode)."""

    real = Path(raw).expanduser().resolve()
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_dir():
        raise http_exception(
            status_code=400, detail=f"path is not a directory: {raw}"
        )
    try:
        children = sorted(real.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read directory: {exc}"
        ) from exc
    except OSError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read directory: {exc}"
        ) from exc

    entries: list[dict[str, Any]] = []
    for child in children:
        try:
            is_dir = child.is_dir()
            size: int | None = None
            if not is_dir:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = None
        except OSError:
            # Broken symlink or vanished mid-listing; skip it rather
            # than fail the whole request.
            continue
        entries.append(
            {
                "name": child.name,
                "kind": "dir" if is_dir else "file",
                "size": size,
            }
        )
    parent = None if real.parent == real else str(real.parent)
    return _files_payload(str(real), parent, entries)


def _file_status(raw: str) -> dict[str, Any]:
    """Single-path status probe for live-mode workflow hints.

    Missing paths are a normal status, not an HTTP error: the frontend
    uses this to tell users which smoke artifacts still need to be
    generated. Permission / OS errors are surfaced in the payload so a
    card can show "unreadable" without breaking the whole page.
    """

    real = Path(raw).expanduser().resolve()
    try:
        if not real.exists():
            return _file_status_payload(
                path=str(real),
                exists=False,
                kind="missing",
                size=None,
                detail="path not found",
            )
        if real.is_dir():
            return _file_status_payload(
                path=str(real),
                exists=True,
                kind="dir",
                size=None,
                detail=None,
            )
        if real.is_file():
            try:
                size = real.stat().st_size
            except OSError:
                size = None
            return _file_status_payload(
                path=str(real),
                exists=True,
                kind="file",
                size=size,
                detail=None,
            )
        return _file_status_payload(
            path=str(real),
            exists=True,
            kind="other",
            size=None,
            detail="path exists but is not a regular file or directory",
        )
    except OSError as exc:
        return _file_status_payload(
            path=str(real),
            exists=False,
            kind="unknown",
            size=None,
            detail=f"cannot stat path: {exc}",
        )


def _mock_list_dir(raw: str, http_exception: Any) -> dict[str, Any]:
    """Mock-mode implementation of ``/api/files`` (returns the bundled tree)."""

    resolved = _resolve_mock_path(raw)

    if resolved not in _MOCK_TREE:
        raise http_exception(
            status_code=404, detail=f"path not found: {raw}"
        )
    entries = [
        {"name": name, "kind": kind, "size": size}
        for name, kind, size in _MOCK_TREE[resolved]
    ]
    # Parent navigation is honest about the mock universe: only walk
    # up if the would-be parent is itself a node in the tree. That
    # way ``/mock/home`` ends up with ``parent = None`` (disables the
    # frontend "up" button) instead of pointing at ``/mock`` which
    # would 404 on the next request.
    parent_candidate = resolved.rsplit("/", 1)[0]
    parent = parent_candidate if parent_candidate in _MOCK_TREE else None
    return _files_payload(resolved, parent, entries)


def _mock_file_status(raw: str) -> dict[str, Any]:
    """Mock-mode single-path status probe using ``_MOCK_TREE``."""

    resolved = _resolve_mock_path(raw)
    if resolved in _MOCK_TREE:
        return _file_status_payload(
            path=resolved,
            exists=True,
            kind="dir",
            size=None,
            detail=None,
        )
    parent, _, name = resolved.rpartition("/")
    for entry_name, kind, size in _MOCK_TREE.get(parent, []):
        if entry_name == name:
            return _file_status_payload(
                path=resolved,
                exists=True,
                kind=kind,
                size=size,
                detail=None,
            )
    return _file_status_payload(
        path=resolved,
        exists=False,
        kind="missing",
        size=None,
        detail="path not found",
    )


def _resolve_mock_path(raw: str) -> str:
    if raw in ("~", "~/"):
        resolved = _MOCK_HOME
    elif raw.startswith("~/"):
        resolved = f"{_MOCK_HOME}/{raw[2:]}"
    else:
        resolved = raw
    return resolved.rstrip("/") or "/"


def _files_payload(
    path: str, parent: str | None, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema": FILES_SCHEMA,
        "path": path,
        "parent": parent,
        "entries": entries,
    }


def _file_status_payload(
    *,
    path: str,
    exists: bool,
    kind: str,
    size: int | None,
    detail: str | None,
) -> dict[str, Any]:
    return {
        "schema": FILE_STATUS_SCHEMA,
        "path": path,
        "exists": exists,
        "kind": kind,
        "size": size,
        "detail": detail,
    }


def _load_fixture(filename: str) -> dict[str, Any]:
    """Read a bundled fixture JSON from ``openmc2donjon.web.fixtures``."""

    text = resources.files("openmc2donjon.web.fixtures").joinpath(filename).read_text(
        encoding="utf-8"
    )
    return json.loads(text)


def _mock_audit_summary(raw_path: str) -> dict[str, Any]:
    """Return a bundled audit fixture, with optional demo variants.

    Mock mode intentionally uses the same 10-iteration SPH loop history
    for every audit request. When the requested mock path contains one
    of ``_MOCK_AUDIT_STD_DEV_PATH_MARKERS`` (for example the file
    browser's ``sph_loop_summary_ref_stddev.json``), derive a second
    view that carries reference-flux std_dev metadata and passing
    uncertainty gates. That keeps the fixture physically coherent while
    giving the UI both "missing" and "gate pass" demo states.
    """

    payload = _load_fixture("audit_sph_loop.json")
    if not _mock_audit_path_requests_std_dev(raw_path):
        return payload
    return _with_mock_reference_flux_std_dev(payload)


def _mock_audit_path_requests_std_dev(raw_path: str) -> bool:
    lowered = raw_path.lower()
    return any(marker in lowered for marker in _MOCK_AUDIT_STD_DEV_PATH_MARKERS)


def _with_mock_reference_flux_std_dev(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("artifact_metadata")
    if isinstance(metadata, dict):
        reference = metadata.get("reference_flux")
        if isinstance(reference, dict):
            _apply_reference_flux_std_dev_metadata(reference, include_shape=True)

    production_audit = payload.get("production_audit")
    if isinstance(production_audit, dict):
        reference = production_audit.get("reference")
        if isinstance(reference, dict):
            _apply_reference_flux_std_dev_metadata(reference, include_shape=False)

    acceptance = payload.get("acceptance")
    if isinstance(acceptance, dict):
        checks = acceptance.get("checks")
        if isinstance(checks, list):
            _upsert_acceptance_check(
                checks,
                {
                    "name": "require_reference_flux_std_dev",
                    "actual": True,
                    "limit": True,
                    "message": "reference flux std_dev present",
                    "passed": True,
                    "units": "boolean",
                },
            )
            _upsert_acceptance_check(
                checks,
                {
                    "name": "max_reference_flux_std_dev_rel",
                    "actual": _MOCK_REFERENCE_STD_DEV_MAX_REL,
                    "limit": _MOCK_REFERENCE_STD_DEV_LIMIT,
                    "message": (
                        "actual 1.800000e-02 <= limit 5.000000e-02 "
                        "relative std_dev/mean"
                    ),
                    "passed": True,
                    "units": "relative",
                },
            )
    return payload


def _apply_reference_flux_std_dev_metadata(
    reference: dict[str, Any],
    *,
    include_shape: bool,
) -> None:
    source = str(reference.get("source") or "")
    shape = reference.get("shape")
    reference["std_dev_dataset"] = _MOCK_REFERENCE_STD_DEV_DATASET
    reference["std_dev_source"] = _std_dev_source(source)
    reference["std_dev_max_rel"] = _MOCK_REFERENCE_STD_DEV_MAX_REL
    reference["std_dev_worst"] = _MOCK_REFERENCE_STD_DEV_WORST
    if include_shape:
        reference["std_dev_shape"] = shape if isinstance(shape, list) else [9, 2]


def _std_dev_source(source: str) -> str:
    if "::" not in source:
        return f"{source}::{_MOCK_REFERENCE_STD_DEV_DATASET}" if source else ""
    path, _dataset = source.rsplit("::", maxsplit=1)
    return f"{path}::{_MOCK_REFERENCE_STD_DEV_DATASET}"


def _upsert_acceptance_check(
    checks: list[Any],
    replacement: dict[str, Any],
) -> None:
    name = replacement["name"]
    for index, item in enumerate(checks):
        if isinstance(item, dict) and item.get("name") == name:
            checks[index] = replacement
            return
    checks.append(replacement)


@lru_cache(maxsize=1)
def _mock_mixture_names() -> frozenset[str]:
    """Cached set of mixture names from the bundled handoff fixture.

    The fixture is read once per process; ``frozenset`` keeps the
    cached value immutable so callers can't accidentally mutate the
    shared object.
    """

    handoff = _load_fixture("inspect_handoff.json")
    return frozenset(mix["name"] for mix in handoff.get("mixtures", []))


@lru_cache(maxsize=1)
def _mock_non_fissionable_mixtures() -> frozenset[str]:
    """Cached set of non-fissionable mixture names from the handoff fixture."""

    handoff = _load_fixture("inspect_handoff.json")
    return frozenset(
        mix["name"]
        for mix in handoff.get("mixtures", [])
        if mix.get("fissionable") is False
    )


def _mock_mixture(mixture: str, moment: int, http_exception: Any) -> dict[str, Any]:
    """Serve the bundled per-mixture fixture for any mixture in the handoff.

    Mock mode previously ignored ``mixture`` / ``moment``. That made it
    impossible to develop the frontend selectors against the mock, and
    let regressions like "moment slider does nothing" slip through. The
    handoff fixture declares 9 mixtures and P1 scattering, so we accept
    those mixture names and moments 0 and 1, and synthesize a plausible
    P1 by scaling the bundled P0 values by 0.1 - enough non-zero
    structure for the frontend selectors and plot wiring to be exercised
    without us needing to ship a second hand-crafted fixture per moment.
    """

    if mixture not in _mock_mixture_names():
        raise http_exception(
            status_code=404, detail=f"mixture not found: {mixture}"
        )
    if moment >= 2:
        raise http_exception(
            status_code=404,
            detail=f"scatter moment {moment} not available for mixture {mixture}",
        )

    payload = _load_fixture("inspect_mixture.json")
    payload = dict(payload)
    payload["mixture"] = mixture
    if mixture in _mock_non_fissionable_mixtures():
        # Strip the fission family so the frontend exercises the
        # null-series guards in both the spectrum and the (M2-A)
        # heatmap. ``total`` / ``absorption`` / ``scatter`` stay
        # present - moderator / guide-tube mixtures absolutely still
        # have those.
        xs = dict(payload["cross_sections"])
        xs["fission"] = None
        xs["nu_fission"] = None
        xs["chi"] = None
        payload["cross_sections"] = xs
    if moment != 0:
        scatter = dict(payload["scatter"])
        scaled = [[float(v) * 0.1 for v in row] for row in scatter["values"]]
        scatter["values"] = scaled
        scatter["moment_index"] = moment
        payload["scatter"] = scatter
    return payload

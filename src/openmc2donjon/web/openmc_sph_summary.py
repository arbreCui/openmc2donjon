"""Read-only web endpoint for OpenMC CE/MG SPH physics summaries."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA = (
    "openmc2donjon.openmc-ce-mg-33g-sph-physics-summary.v1"
)


def register_openmc_sph_summary_routes(app: Any, *, mock_mode: bool) -> None:
    """Register ``/api/openmc-sph-summary`` on a FastAPI app."""

    from fastapi import HTTPException, Query

    @app.get("/api/openmc-sph-summary")
    def api_openmc_sph_summary(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            payload = _load_fixture_summary()
            payload = dict(payload)
            payload["requested_path"] = path
            _validate_summary_payload(payload, HTTPException)
            return payload

        real_path = _validate_json_path(path, HTTPException)
        try:
            payload = json.loads(real_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"OpenMC SPH physics summary read failed: {exc}",
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=422,
                detail="OpenMC SPH physics summary is not a JSON object",
            )
        payload["requested_path"] = str(real_path)
        _validate_summary_payload(payload, HTTPException)
        return payload


def _validate_json_path(raw: str, http_exception: Any) -> Path:
    real = Path(raw).expanduser().resolve()
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    if real.suffix.lower() != ".json":
        raise http_exception(status_code=400, detail=f"not a JSON summary file: {raw}")
    return real


def _load_fixture_summary() -> dict[str, Any]:
    text = (
        resources.files("openmc2donjon.web.fixtures")
        .joinpath("openmc_sph_physics_summary.json")
        .read_text(encoding="utf-8")
    )
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("mock OpenMC SPH physics summary fixture is not an object")
    return payload


def _validate_summary_payload(payload: dict[str, Any], http_exception: Any) -> None:
    errors: list[str] = []
    _require_type(payload, "schema", str, errors)
    if payload.get("schema") != OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA:
        errors.append(f"schema must be {OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA!r}")
    _require_type(payload, "route", str, errors)
    for key in ("mixture_count", "energy_groups", "legendre_order"):
        _require_type(payload, key, int, errors)
    _require_string_list(payload, "mixture_names", errors)
    for key in ("decisions", "normalization", "flux_uncertainty", "sph", "handoff"):
        _require_type(payload, key, dict, errors)
    per_mixture = payload.get("per_mixture")
    if not isinstance(per_mixture, list):
        errors.append("per_mixture must be a list")
    else:
        for index, row in enumerate(per_mixture):
            if not isinstance(row, dict):
                errors.append(f"per_mixture[{index}] must be an object")
                continue
            _require_type(row, "mixture", str, errors, prefix=f"per_mixture[{index}]")
            for key in (
                "sph_min",
                "sph_max",
                "sph_mean",
                "max_abs_sph_minus_1",
                "ce_flux_min",
                "ce_flux_max",
                "mg_flux_min",
                "mg_flux_max",
            ):
                _require_number(row, key, errors, prefix=f"per_mixture[{index}]")

    if isinstance(payload.get("sph"), dict):
        sph = payload["sph"]
        for key in ("minimum", "maximum", "mean", "max_abs_delta_from_unity"):
            _require_number(sph, key, errors, prefix="sph")
        _require_type(sph, "applied_to_xs", bool, errors, prefix="sph")
        _require_type(sph, "real", bool, errors, prefix="sph")
    if isinstance(payload.get("flux_uncertainty"), dict):
        flux = payload["flux_uncertainty"]
        _require_number(flux, "ce_max_relative_std_dev", errors, prefix="flux_uncertainty")
        _require_number(flux, "mg_max_relative_std_dev", errors, prefix="flux_uncertainty")
    if isinstance(payload.get("handoff"), dict):
        handoff = payload["handoff"]
        _require_type(handoff, "augmented_hdf5_has_sph", bool, errors, prefix="handoff")
        _require_type(handoff, "ascii_nsp_block_count", int, errors, prefix="handoff")

    if errors:
        raise http_exception(
            status_code=422,
            detail="invalid OpenMC SPH physics summary: " + "; ".join(errors),
        )


def _require_type(
    payload: dict[str, Any],
    key: str,
    expected: type,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    value = payload.get(key)
    qualified = key if prefix is None else f"{prefix}.{key}"
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        errors.append(f"{qualified} must be {expected.__name__}")


def _require_number(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    value = payload.get(key)
    qualified = key if prefix is None else f"{prefix}.{key}"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{qualified} must be number")


def _require_string_list(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{key} must be a list of strings")

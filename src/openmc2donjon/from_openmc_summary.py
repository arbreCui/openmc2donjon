"""Validation helpers for one-step OpenMC conversion summaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


FROM_OPENMC_SUMMARY_SCHEMA_V1 = "openmc2donjon.from-openmc-summary.v1"
FROM_OPENMC_SUMMARY_SCHEMA = "openmc2donjon.from-openmc-summary.v2"

FROM_OPENMC_SUMMARY_V1_KEYS = frozenset(
    {
        "burnup_axis",
        "energy_groups",
        "format",
        "h_factor_default",
        "hdf5",
        "hdf5_kept",
        "legendre_order",
        "loaded_statepoint",
        "mixture_count",
        "mixture_names",
        "output",
        "package_version",
        "recipe",
        "root_name",
        "schema",
        "selected_mixtures",
        "single_point_burnup",
        "state_points",
        "statepoint",
    }
)

FROM_OPENMC_SUMMARY_V2_KEYS = FROM_OPENMC_SUMMARY_V1_KEYS | frozenset(
    {
        "check_passed",
        "check_summary_json",
        "checked",
    }
)


def validate_from_openmc_summary(payload: Mapping[str, Any]) -> list[str]:
    """Return schema validation errors for any supported from-OpenMC summary."""

    schema = payload.get("schema")
    if schema == FROM_OPENMC_SUMMARY_SCHEMA_V1:
        return validate_from_openmc_summary_v1(payload)
    return validate_from_openmc_summary_v2(payload)


def validate_from_openmc_summary_v1(payload: Mapping[str, Any]) -> list[str]:
    """Return schema validation errors for a from-OpenMC summary payload."""

    return _validate_from_openmc_summary(
        payload,
        schema=FROM_OPENMC_SUMMARY_SCHEMA_V1,
        keys=FROM_OPENMC_SUMMARY_V1_KEYS,
        validate_check_fields=False,
    )


def validate_from_openmc_summary_v2(payload: Mapping[str, Any]) -> list[str]:
    """Return schema validation errors for a v2 from-OpenMC summary payload."""

    return _validate_from_openmc_summary(
        payload,
        schema=FROM_OPENMC_SUMMARY_SCHEMA,
        keys=FROM_OPENMC_SUMMARY_V2_KEYS,
        validate_check_fields=True,
    )


def _validate_from_openmc_summary(
    payload: Mapping[str, Any],
    *,
    schema: str,
    keys: frozenset[str],
    validate_check_fields: bool,
) -> list[str]:
    """Return schema validation errors for a from-OpenMC summary payload."""

    errors: list[str] = []
    payload_keys = set(payload)
    missing = sorted(keys - payload_keys)
    extra = sorted(payload_keys - keys)
    if missing:
        errors.append(f"missing keys: {', '.join(missing)}")
    if extra:
        errors.append(f"unexpected keys: {', '.join(extra)}")

    _require_literal(errors, payload, "schema", schema)
    _require_nonempty_string(errors, payload, "package_version")
    _require_nonempty_string(errors, payload, "recipe")
    _require_optional_string(errors, payload, "statepoint")
    _require_bool(errors, payload, "loaded_statepoint")
    _require_nonempty_string(errors, payload, "hdf5")
    _require_bool(errors, payload, "hdf5_kept")
    _require_nonempty_string(errors, payload, "output")
    _require_choice(errors, payload, "format", {"multicompo", "macrolib"})
    _require_int_at_least(errors, payload, "energy_groups", 1)
    _require_int_at_least(errors, payload, "legendre_order", 0)
    _require_int_at_least(errors, payload, "mixture_count", 0)
    _require_string_list(errors, payload, "mixture_names")
    _require_int_at_least(errors, payload, "state_points", 0)
    _require_optional_string_list(errors, payload, "selected_mixtures")
    _require_optional_number(errors, payload, "single_point_burnup")
    _require_optional_number(errors, payload, "h_factor_default")
    _validate_root_name(errors, payload)
    _validate_statepoint_link(errors, payload)
    _validate_mixture_count(errors, payload)
    _validate_burnup_axis(errors, payload.get("burnup_axis"))
    if validate_check_fields:
        _require_bool(errors, payload, "checked")
        _require_optional_bool(errors, payload, "check_passed")
        _require_optional_string(errors, payload, "check_summary_json")
        _validate_check_fields(errors, payload)
    return errors


def _require_literal(
    errors: list[str],
    payload: Mapping[str, Any],
    key: str,
    expected: object,
) -> None:
    if key not in payload:
        return
    if payload[key] != expected:
        errors.append(f"{key}: expected {expected!r}, got {payload[key]!r}")


def _require_nonempty_string(errors: list[str], payload: Mapping[str, Any], key: str) -> None:
    if key not in payload:
        return
    value = payload[key]
    if not isinstance(value, str) or not value:
        errors.append(f"{key}: expected non-empty string")


def _require_optional_string(errors: list[str], payload: Mapping[str, Any], key: str) -> None:
    if key not in payload:
        return
    value = payload[key]
    if value is not None and not isinstance(value, str):
        errors.append(f"{key}: expected string or null")


def _require_bool(errors: list[str], payload: Mapping[str, Any], key: str) -> None:
    if key not in payload:
        return
    if not isinstance(payload[key], bool):
        errors.append(f"{key}: expected boolean")


def _require_optional_bool(errors: list[str], payload: Mapping[str, Any], key: str) -> None:
    if key not in payload:
        return
    if payload[key] is not None and not isinstance(payload[key], bool):
        errors.append(f"{key}: expected boolean or null")


def _require_choice(
    errors: list[str],
    payload: Mapping[str, Any],
    key: str,
    choices: set[str],
) -> None:
    if key not in payload:
        return
    if payload[key] not in choices:
        rendered = ", ".join(sorted(choices))
        errors.append(f"{key}: expected one of {rendered}")


def _require_int_at_least(
    errors: list[str],
    payload: Mapping[str, Any],
    key: str,
    minimum: int,
) -> None:
    if key not in payload:
        return
    value = payload[key]
    if not _is_int(value) or value < minimum:
        errors.append(f"{key}: expected integer >= {minimum}")


def _require_string_list(errors: list[str], payload: Mapping[str, Any], key: str) -> None:
    if key not in payload:
        return
    value = payload[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{key}: expected list of strings")


def _require_optional_string_list(
    errors: list[str],
    payload: Mapping[str, Any],
    key: str,
) -> None:
    if key not in payload:
        return
    value = payload[key]
    if value is not None and (
        not isinstance(value, list) or not all(isinstance(item, str) for item in value)
    ):
        errors.append(f"{key}: expected list of strings or null")


def _require_optional_number(errors: list[str], payload: Mapping[str, Any], key: str) -> None:
    if key not in payload:
        return
    if payload[key] is not None and not _is_number(payload[key]):
        errors.append(f"{key}: expected number or null")


def _validate_root_name(errors: list[str], payload: Mapping[str, Any]) -> None:
    if "root_name" not in payload:
        return
    root_name = payload["root_name"]
    output_format = payload.get("format")
    if output_format == "multicompo":
        if not isinstance(root_name, str) or not root_name:
            errors.append("root_name: expected non-empty string for multicompo output")
    elif output_format == "macrolib":
        if root_name is not None:
            errors.append("root_name: expected null for macrolib output")
    elif root_name is not None and not isinstance(root_name, str):
        errors.append("root_name: expected string or null")


def _validate_statepoint_link(errors: list[str], payload: Mapping[str, Any]) -> None:
    if payload.get("loaded_statepoint") is True and payload.get("statepoint") is None:
        errors.append("statepoint: expected path when loaded_statepoint is true")


def _validate_check_fields(errors: list[str], payload: Mapping[str, Any]) -> None:
    checked = payload.get("checked")
    check_passed = payload.get("check_passed")
    check_summary_json = payload.get("check_summary_json")
    if checked is True:
        if check_passed is not True:
            errors.append("check_passed: expected true when checked is true")
    elif checked is False:
        if check_passed is not None:
            errors.append("check_passed: expected null when checked is false")
        if check_summary_json is not None:
            errors.append("check_summary_json: expected null when checked is false")


def _validate_mixture_count(errors: list[str], payload: Mapping[str, Any]) -> None:
    mixture_count = payload.get("mixture_count")
    mixture_names = payload.get("mixture_names")
    if _is_int(mixture_count) and isinstance(mixture_names, list):
        if mixture_count != len(mixture_names):
            errors.append("mixture_count: expected len(mixture_names)")


def _validate_burnup_axis(errors: list[str], value: object) -> None:
    if not isinstance(value, Mapping):
        errors.append("burnup_axis: expected object")
        return
    present = value.get("present")
    if not isinstance(present, bool):
        errors.append("burnup_axis.present: expected boolean")
        return
    keys = set(value)
    if present:
        if keys != {"count", "present", "values"}:
            errors.append("burnup_axis: expected count, present, values keys")
            return
        count = value["count"]
        values = value["values"]
        if not _is_int(count) or count < 0:
            errors.append("burnup_axis.count: expected integer >= 0")
        if not isinstance(values, list) or not all(_is_number(item) for item in values):
            errors.append("burnup_axis.values: expected list of numbers")
        elif _is_int(count) and count != len(values):
            errors.append("burnup_axis.count: expected len(values)")
    elif keys != {"present"}:
        errors.append("burnup_axis: expected only present=false")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

"""Recipe-based OpenMC statepoint export helpers.

This module keeps OpenMC as an optional runtime dependency.  A user recipe
builds the OpenMC ``mgxs.Library`` for a case, while this runner loads a
statepoint and writes the compact openmc2donjon HDF5 handoff contract.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from .export_openmc_mgxs import (
    MGXS_TYPE_ALIASES,
    NU_SCATTER_MGXS_TYPES,
    ExportSummary,
    _domain_name,
    _domain_volume,
    _energy_bounds_from_library,
    _export_specs_from_library,
    _mapped_domain_name,
    _safe_hdf5_name,
    export_openmc_mgxs_library,
)


class StatepointLoadError(RuntimeError):
    """Raised when an OpenMC statepoint cannot satisfy the recipe MGXS library."""


@dataclass(frozen=True)
class RecipeExportSummary:
    """Summary for a recipe-driven OpenMC statepoint export."""

    recipe_path: Path
    statepoint_path: Path | None
    statepoint_loaded: bool
    output: ExportSummary


@dataclass(frozen=True)
class RecipeTalliesExportSummary:
    """Summary for a recipe-driven OpenMC tallies XML export."""

    recipe_path: Path
    output_path: Path
    tally_count: int | None
    extra_tally_count: int
    merged: bool


@dataclass(frozen=True)
class RecipeDryRunDomain:
    """One domain or subdomain that would become a DONJON mixture."""

    name: str
    source_label: str
    source_id: Any
    source_type: str
    volume: float | None
    volume_source: str
    xs_kwargs: Mapping[str, Any] | None
    attr_keys: tuple[str, ...]


@dataclass(frozen=True)
class RecipeProductionCheck:
    """One production-readiness check for a recipe dry-run."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class RecipeDryRunSummary:
    """Dry-run summary for a recipe-driven OpenMC export."""

    recipe_path: Path
    statepoint_path: Path | None
    statepoint_loaded: bool
    output_path: Path | None
    energy_groups: int
    legendre_order: int
    domain_type: str | None
    mgxs_types: tuple[str, ...]
    scatter_mgxs_type: str | None
    domains: tuple[RecipeDryRunDomain, ...]
    root_attr_keys: tuple[str, ...]
    production_checks: tuple[RecipeProductionCheck, ...]
    warnings: tuple[str, ...]


def export_openmc_statepoint_recipe(
    recipe_path: str | Path,
    output_path: str | Path,
    *,
    statepoint_path: str | Path | None = None,
    load_statepoint: bool = True,
    scatter_mgxs_type: str | None = None,
    overwrite: bool = True,
) -> RecipeExportSummary:
    """Export an OpenMC MGXS recipe and statepoint to the HDF5 contract.

    The recipe is a Python file with a required ``build_library`` function and
    optional ``domain_specs``, ``domain_names``, ``root_attrs``,
    ``scatter_mgxs_type``, ``load_statepoint``, and ``postprocess_hdf5``
    functions.  Optional recipe functions may declare any subset of these
    keyword arguments:
    ``library``, ``recipe_path``, ``statepoint_path``, ``output_path``, and
    ``summary``.
    """

    recipe = load_recipe_module(recipe_path)
    recipe_file = Path(recipe_path).resolve()
    output_file = Path(output_path).resolve()
    statepoint_file = Path(statepoint_path).resolve() if statepoint_path else None

    library = _call_required(
        recipe,
        ("build_library", "get_library"),
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=output_file,
    )

    statepoint_loaded = False
    if load_statepoint:
        if statepoint_file is None:
            raise ValueError("recipe exports require a statepoint path unless loading is disabled")
        _load_statepoint(recipe, library, statepoint_file, recipe_file)
        statepoint_loaded = True

    domain_specs = _call_optional(
        recipe,
        ("domain_specs", "get_domain_specs"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=output_file,
    )
    domain_names = _call_optional(
        recipe,
        ("domain_names", "get_domain_names"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=output_file,
    )
    root_attrs = _call_optional(
        recipe,
        ("root_attrs", "get_root_attrs"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=output_file,
    )
    recipe_scatter_mgxs_type = _call_optional(
        recipe,
        ("scatter_mgxs_type", "get_scatter_mgxs_type"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=output_file,
    )
    selected_scatter_mgxs_type = (
        scatter_mgxs_type
        if scatter_mgxs_type is not None
        else recipe_scatter_mgxs_type
    )

    summary = export_openmc_mgxs_library(
        library,
        output_file,
        domain_specs=domain_specs,
        domain_names=domain_names,
        root_attrs=root_attrs,
        scatter_mgxs_type=selected_scatter_mgxs_type,
        overwrite=overwrite,
    )

    _call_optional(
        recipe,
        ("postprocess_hdf5", "finalize_hdf5"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=output_file,
        summary=summary,
    )

    return RecipeExportSummary(
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        statepoint_loaded=statepoint_loaded,
        output=summary,
    )


def export_openmc_tallies_recipe(
    recipe_path: str | Path,
    output_path: str | Path,
    *,
    merge: bool = True,
    overwrite: bool = True,
) -> RecipeTalliesExportSummary:
    """Write an OpenMC ``tallies.xml`` file from a recipe MGXS library.

    The recipe must define ``build_library`` or ``get_library``.  The exported
    tallies include the MGXS tallies required by the library.  A recipe can add
    case-specific tallies, such as surface-current tallies for ADF generation,
    by defining ``extra_tallies(...)`` or ``get_extra_tallies(...)``.
    """

    recipe = load_recipe_module(recipe_path)
    recipe_file = Path(recipe_path).resolve()
    output_file = Path(output_path).resolve()
    if output_file.exists() and not overwrite:
        raise FileExistsError(output_file)

    library = _call_required(
        recipe,
        ("build_library", "get_library"),
        recipe_path=recipe_file,
        output_path=output_file,
    )
    try:
        import openmc  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on user environment
        raise RuntimeError(
            "OpenMC is required to write tallies.xml from a recipe; install OpenMC "
            "in this environment or generate tallies from the recipe inside your "
            "OpenMC runtime."
        ) from exc

    tallies = openmc.Tallies()
    _add_library_to_tallies(library, tallies, merge=merge)
    extras = _call_optional(
        recipe,
        ("extra_tallies", "get_extra_tallies"),
        library=library,
        tallies=tallies,
        recipe_path=recipe_file,
        output_path=output_file,
    )
    extra_count = _append_extra_tallies(tallies, extras)
    replacement = _call_optional(
        recipe,
        ("postprocess_tallies", "finalize_tallies"),
        library=library,
        tallies=tallies,
        recipe_path=recipe_file,
        output_path=output_file,
    )
    if replacement is not None:
        tallies = replacement

    output_file.parent.mkdir(parents=True, exist_ok=True)
    _export_tallies_xml(tallies, output_file)
    return RecipeTalliesExportSummary(
        recipe_path=recipe_file,
        output_path=output_file,
        tally_count=_safe_len(tallies),
        extra_tally_count=extra_count,
        merged=merge,
    )


def dry_run_openmc_statepoint_recipe(
    recipe_path: str | Path,
    *,
    statepoint_path: str | Path | None = None,
    load_statepoint: bool = False,
    output_path: str | Path | None = None,
    scatter_mgxs_type: str | None = None,
) -> RecipeDryRunSummary:
    """Inspect a recipe without writing the HDF5 handoff or reading MGXS values."""

    recipe = load_recipe_module(recipe_path)
    recipe_file = Path(recipe_path).resolve()
    output_file = Path(output_path).resolve() if output_path else None
    statepoint_file = Path(statepoint_path).resolve() if statepoint_path else None
    hook_output = output_file or recipe_file.with_name("openmc2donjon_dry_run.h5")

    library = _call_required(
        recipe,
        ("build_library", "get_library"),
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=hook_output,
    )

    statepoint_loaded = False
    if load_statepoint:
        if statepoint_file is None:
            raise ValueError("dry-run statepoint loading requires a statepoint path")
        _load_statepoint(recipe, library, statepoint_file, recipe_file)
        statepoint_loaded = True

    domain_specs = _call_optional(
        recipe,
        ("domain_specs", "get_domain_specs"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=hook_output,
    )
    domain_names = _call_optional(
        recipe,
        ("domain_names", "get_domain_names"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=hook_output,
    )
    root_attrs = _call_optional(
        recipe,
        ("root_attrs", "get_root_attrs"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=hook_output,
    )
    recipe_scatter_mgxs_type = _call_optional(
        recipe,
        ("scatter_mgxs_type", "get_scatter_mgxs_type"),
        library=library,
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        output_path=hook_output,
    )
    selected_scatter_mgxs_type = (
        scatter_mgxs_type
        if scatter_mgxs_type is not None
        else recipe_scatter_mgxs_type
    )

    energy_bounds = _energy_bounds_from_library(library)
    specs = _export_specs_from_library(library, domain_specs)
    if not specs:
        raise ValueError("recipe selected no MGXS domains")

    used_names: set[str] = set()
    domains: list[RecipeDryRunDomain] = []
    warnings: list[str] = []
    for index, spec in enumerate(specs, start=1):
        raw_name = _raw_domain_name(spec.domain, index, domain_names, spec.name)
        safe_name = _safe_hdf5_name(str(raw_name))
        if not safe_name:
            safe_name = f"domain_{index}"
        name = _domain_name(spec.domain, index, domain_names, used_names, spec.name)
        if name != safe_name:
            warnings.append(f"domain {index}: duplicate name {safe_name!r} written as {name!r}")
        elif str(raw_name) != safe_name:
            warnings.append(f"domain {index}: name {raw_name!r} written as {safe_name!r}")
        volume, volume_source = _dry_run_volume(spec.domain, spec.volume)
        domains.append(
            RecipeDryRunDomain(
                name=name,
                source_label=_source_label(spec.domain),
                source_id=getattr(spec.domain, "id", None),
                source_type=type(spec.domain).__name__,
                volume=volume,
                volume_source=volume_source,
                xs_kwargs=spec.xs_kwargs,
                attr_keys=tuple(sorted((spec.attrs or {}).keys())),
            )
        )

    mgxs_types = _library_mgxs_types(library)
    warnings.extend(_mgxs_type_warnings(mgxs_types, selected_scatter_mgxs_type))
    root_attr_keys = tuple(sorted((root_attrs or {}).keys()))
    domain_type = _optional_string_attr(library, "domain_type")
    legendre_order = _library_legendre_order(library)
    production_checks = _production_checks(
        energy_groups=len(energy_bounds) - 1,
        legendre_order=legendre_order,
        domain_type=domain_type,
        mgxs_types=mgxs_types,
        scatter_mgxs_type=selected_scatter_mgxs_type,
        domains=tuple(domains),
        root_attr_keys=root_attr_keys,
    )
    return RecipeDryRunSummary(
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        statepoint_loaded=statepoint_loaded,
        output_path=output_file,
        energy_groups=len(energy_bounds) - 1,
        legendre_order=legendre_order,
        domain_type=domain_type,
        mgxs_types=mgxs_types,
        scatter_mgxs_type=(
            None if selected_scatter_mgxs_type is None else str(selected_scatter_mgxs_type)
        ),
        domains=tuple(domains),
        root_attr_keys=root_attr_keys,
        production_checks=production_checks,
        warnings=tuple(warnings),
    )


def load_recipe_module(recipe_path: str | Path) -> ModuleType:
    """Load a Python export recipe from disk."""

    path = Path(recipe_path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    module_name = f"_openmc2donjon_recipe_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import recipe {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _raw_domain_name(
    domain: Any,
    index: int,
    domain_names: Mapping[Any, str] | None,
    preferred_name: str | None,
) -> str:
    raw = preferred_name or _mapped_domain_name(domain, domain_names)
    if raw is None:
        raw = getattr(domain, "name", None) or getattr(domain, "id", None) or f"domain_{index}"
    return str(raw)


def _source_label(domain: Any) -> str:
    return str(getattr(domain, "name", None) or getattr(domain, "id", None) or domain)


def _library_legendre_order(library: Any) -> int:
    value = getattr(library, "legendre_order", 0)
    try:
        order = int(value)
    except (TypeError, ValueError):
        return 0
    return max(order, 0)


def _library_mgxs_types(library: Any) -> tuple[str, ...]:
    values = getattr(library, "mgxs_types", ()) or ()
    return tuple(str(value) for value in values)


def _production_checks(
    *,
    energy_groups: int,
    legendre_order: int,
    domain_type: str | None,
    mgxs_types: tuple[str, ...],
    scatter_mgxs_type: str | None,
    domains: tuple[RecipeDryRunDomain, ...],
    root_attr_keys: tuple[str, ...],
) -> tuple[RecipeProductionCheck, ...]:
    checks: list[RecipeProductionCheck] = []
    checks.append(
        RecipeProductionCheck(
            "energy-groups",
            "PASS" if energy_groups > 0 else "FAIL",
            f"{energy_groups} group(s) from recipe energy bounds",
        )
    )
    checks.append(_mgxs_required_check(mgxs_types, scatter_mgxs_type))
    checks.append(_mgxs_transport_check(mgxs_types))
    checks.append(_fission_source_check(mgxs_types))
    checks.append(
        RecipeProductionCheck(
            "legendre-order",
            "PASS" if legendre_order >= 1 else "WARN",
            (
                f"P{legendre_order}; P1+ supports anisotropic scattering checks"
                if legendre_order >= 1
                else "P0 only; diffusion may work, but SPN/transport studies usually need P1+"
            ),
        )
    )
    mapping_status = "PASS" if domain_type else "WARN"
    mapping_type = domain_type or "unknown"
    checks.append(
        RecipeProductionCheck(
            "domain-mapping",
            mapping_status,
            f"{len(domains)} {mapping_type} domain(s) -> {len(domains)} DONJON mixture(s)",
        )
    )
    checks.append(_volume_check(domains))
    checks.append(
        RecipeProductionCheck(
            "domain-mode",
            "PASS" if "domain_mode" in root_attr_keys else "WARN",
            (
                "root_attrs include domain_mode"
                if "domain_mode" in root_attr_keys
                else "root_attrs should include domain_mode, e.g. assembly/cell/material"
            ),
        )
    )
    return tuple(checks)


def _mgxs_required_check(
    mgxs_types: tuple[str, ...],
    scatter_mgxs_type: str | None,
) -> RecipeProductionCheck:
    if not mgxs_types:
        return RecipeProductionCheck(
            "mgxs-required",
            "WARN",
            "library has no mgxs_types list; required XS availability cannot be checked early",
        )
    missing: list[str] = []
    for required in ("total", "absorption"):
        if not _has_mgxs_alias(mgxs_types, required):
            missing.append("/".join(MGXS_TYPE_ALIASES[required]))
    if scatter_mgxs_type is None:
        if not _has_mgxs_alias(mgxs_types, "scatter_matrix"):
            missing.append("/".join(MGXS_TYPE_ALIASES["scatter_matrix"]))
        if _has_any_mgxs_type(mgxs_types, NU_SCATTER_MGXS_TYPES):
            return RecipeProductionCheck(
                "mgxs-required",
                "FAIL",
                "ordinary scatter matrix is missing or not selected; nu-scatter MGXS "
                "is not used as DONJON scattering unless scatter_mgxs_type is explicit",
            )
    elif not _has_any_mgxs_type(mgxs_types, (str(scatter_mgxs_type),)):
        missing.append(str(scatter_mgxs_type))
    if missing:
        return RecipeProductionCheck(
            "mgxs-required",
            "FAIL",
            "missing required MGXS type(s): " + ", ".join(missing),
        )
    return RecipeProductionCheck(
        "mgxs-required",
        "PASS",
        (
            "total, absorption, and scatter matrix MGXS are declared"
            if scatter_mgxs_type is None
            else f"total, absorption, and explicit scatter MGXS {scatter_mgxs_type!r} are declared"
        ),
    )


def _mgxs_transport_check(mgxs_types: tuple[str, ...]) -> RecipeProductionCheck:
    if _has_mgxs_alias(mgxs_types, "transport_total"):
        return RecipeProductionCheck(
            "transport",
            "PASS",
            "transport MGXS declared; STRD can be written explicitly",
        )
    return RecipeProductionCheck(
        "transport",
        "WARN",
        "transport MGXS not declared; STRD may fall back to total",
    )


def _fission_source_check(mgxs_types: tuple[str, ...]) -> RecipeProductionCheck:
    if not mgxs_types:
        return RecipeProductionCheck(
            "fission-source",
            "WARN",
            "fission, nu-fission, and chi availability cannot be checked early",
        )
    missing = [
        label
        for label, key in (
            ("fission", "fission"),
            ("nu-fission", "nu_fission"),
            ("chi", "chi"),
        )
        if not _has_mgxs_alias(mgxs_types, key)
    ]
    if not missing:
        return RecipeProductionCheck(
            "fission-source",
            "PASS",
            "fission, nu-fission, and chi MGXS are declared",
        )
    return RecipeProductionCheck(
        "fission-source",
        "WARN",
        "missing " + ", ".join(missing) + "; acceptable only for non-fissile/fixed-source cases",
    )


def _volume_check(domains: tuple[RecipeDryRunDomain, ...]) -> RecipeProductionCheck:
    missing = [domain.name for domain in domains if domain.volume is None]
    if missing:
        rendered = ", ".join(missing[:8])
        if len(missing) > 8:
            rendered += f", ... ({len(missing)} total)"
        return RecipeProductionCheck(
            "volumes",
            "WARN",
            (
                f"{len(missing)} domain(s) are missing volume: {rendered}; "
                "exported HDF5 will omit volume and strict preflight will fail"
            ),
        )
    non_positive = [
        domain.name
        for domain in domains
        if domain.volume is not None and domain.volume <= 0.0
    ]
    if non_positive:
        rendered = ", ".join(non_positive[:8])
        if len(non_positive) > 8:
            rendered += f", ... ({len(non_positive)} total)"
        return RecipeProductionCheck(
            "volumes",
            "FAIL",
            f"non-positive domain volume(s): {rendered}",
        )
    defaulted = [domain.name for domain in domains if domain.volume_source == "default"]
    if defaulted:
        rendered = ", ".join(defaulted[:8])
        if len(defaulted) > 8:
            rendered += f", ... ({len(defaulted)} total)"
        return RecipeProductionCheck(
            "volumes",
            "WARN",
            f"{len(defaulted)} domain(s) use default volume=1.0: {rendered}",
        )
    return RecipeProductionCheck(
        "volumes",
        "PASS",
        "all selected domains have positive explicit volumes",
    )


def _has_mgxs_alias(mgxs_types: tuple[str, ...], key: str) -> bool:
    normalized = {_normalize_mgxs_type(value) for value in mgxs_types}
    aliases = {_normalize_mgxs_type(value) for value in MGXS_TYPE_ALIASES[key]}
    return not normalized.isdisjoint(aliases)


def _has_any_mgxs_type(mgxs_types: tuple[str, ...], candidates: tuple[str, ...]) -> bool:
    normalized = {_normalize_mgxs_type(value) for value in mgxs_types}
    candidate_set = {_normalize_mgxs_type(value) for value in candidates}
    return not normalized.isdisjoint(candidate_set)


def _normalize_mgxs_type(value: str) -> str:
    return str(value).lower().replace("_", "-")


def _dry_run_volume(domain: Any, explicit_volume: float | None) -> tuple[float | None, str]:
    if explicit_volume is not None:
        return float(explicit_volume), "spec"
    for attr in ("volume", "vol"):
        if hasattr(domain, attr):
            value = getattr(domain, attr)
            if callable(value):
                value = value()
            try:
                return float(value), "domain"
            except (TypeError, ValueError):
                continue
    return _domain_volume(domain), "missing"


def _optional_string_attr(obj: Any, name: str) -> str | None:
    if not hasattr(obj, name):
        return None
    value = getattr(obj, name)
    if value is None:
        return None
    return str(value)


def _mgxs_type_warnings(
    mgxs_types: tuple[str, ...],
    scatter_mgxs_type: str | None,
) -> list[str]:
    if not mgxs_types:
        return ["library has no mgxs_types list; required MGXS availability is unchecked"]

    normalized = {value.lower().replace("_", "-") for value in mgxs_types}
    warnings: list[str] = []
    for required in ("total", "absorption"):
        aliases = {alias.lower().replace("_", "-") for alias in MGXS_TYPE_ALIASES[required]}
        if normalized.isdisjoint(aliases):
            rendered = "/".join(MGXS_TYPE_ALIASES[required])
            warnings.append(f"mgxs_types missing required {rendered}")
    scatter_candidates = (
        (str(scatter_mgxs_type),)
        if scatter_mgxs_type is not None
        else MGXS_TYPE_ALIASES["scatter_matrix"]
    )
    scatter_aliases = {alias.lower().replace("_", "-") for alias in scatter_candidates}
    if normalized.isdisjoint(scatter_aliases):
        rendered = "/".join(scatter_candidates)
        warnings.append(f"mgxs_types missing required {rendered}")
    if scatter_mgxs_type is None:
        nu_aliases = {alias.lower().replace("_", "-") for alias in NU_SCATTER_MGXS_TYPES}
        if not normalized.isdisjoint(nu_aliases):
            warnings.append(
                "mgxs_types declares nu-scatter, but default export requires ordinary scatter matrix"
            )
    transport_aliases = {
        alias.lower().replace("_", "-")
        for alias in MGXS_TYPE_ALIASES["transport_total"]
    }
    if normalized.isdisjoint(transport_aliases):
        warnings.append("mgxs_types missing transport; STRD will fall back during conversion")
    return warnings


def _load_statepoint(
    recipe: ModuleType,
    library: Any,
    statepoint_path: Path,
    recipe_path: Path,
) -> None:
    custom_loader = getattr(recipe, "load_statepoint", None)
    if custom_loader is not None:
        if not callable(custom_loader):
            raise TypeError("recipe load_statepoint must be callable")
        _call_with_supported_kwargs(
            custom_loader,
            library=library,
            statepoint_path=statepoint_path,
            recipe_path=recipe_path,
        )
        return

    if not hasattr(library, "load_from_statepoint"):
        raise TypeError(
            "recipe library has no load_from_statepoint method; "
            "define recipe load_statepoint(library, statepoint_path) for custom loading"
        )

    try:
        import openmc  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on user environment
        raise RuntimeError(
            "OpenMC is required for default statepoint loading; install OpenMC or "
            "define recipe load_statepoint(library, statepoint_path)"
        ) from exc

    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        try:
            library.load_from_statepoint(statepoint)
        except LookupError as exc:
            if "Unable to get Tally" in str(exc):
                raise StatepointLoadError(
                    f"statepoint {statepoint_path} does not contain one or more "
                    f"MGXS tallies required by recipe {recipe_path}; rerun OpenMC "
                    "with the tallies generated by that recipe/library, or use the "
                    f"matching statepoint. OpenMC reported: {exc}"
                ) from exc
            raise


def _add_library_to_tallies(library: Any, tallies: Any, *, merge: bool) -> None:
    if hasattr(library, "add_to_tallies"):
        try:
            library.add_to_tallies(tallies, merge=merge)
        except TypeError:
            library.add_to_tallies(tallies)
        return
    if hasattr(library, "add_to_tallies_file"):
        try:
            library.add_to_tallies_file(tallies, merge=merge)
        except TypeError:
            library.add_to_tallies_file(tallies)
        return
    raise TypeError(
        "recipe library has no add_to_tallies/add_to_tallies_file method; "
        "build an OpenMC mgxs.Library in the recipe before writing tallies.xml"
    )


def _append_extra_tallies(tallies: Any, extras: Any) -> int:
    if extras is None:
        return 0
    if _looks_like_single_tally(extras):
        _append_one_tally(tallies, extras)
        return 1
    if _looks_like_tallies_collection(extras):
        count = 0
        for tally in extras:
            _append_one_tally(tallies, tally)
            count += 1
        return count
    try:
        iterator = iter(extras)
    except TypeError as exc:
        raise TypeError(
            "recipe extra_tallies must return a Tally, Tallies, iterable of tallies, or None"
        ) from exc
    count = 0
    for tally in iterator:
        _append_one_tally(tallies, tally)
        count += 1
    return count


def _looks_like_single_tally(value: Any) -> bool:
    return hasattr(value, "scores") or value.__class__.__name__ == "Tally"


def _looks_like_tallies_collection(value: Any) -> bool:
    if isinstance(value, (str, bytes, bytearray)):
        return False
    return hasattr(value, "__iter__") and value.__class__.__name__ == "Tallies"


def _append_one_tally(tallies: Any, tally: Any) -> None:
    if hasattr(tallies, "append"):
        tallies.append(tally)
        return
    if hasattr(tallies, "extend"):
        tallies.extend([tally])
        return
    raise TypeError("OpenMC Tallies object does not support append/extend")


def _export_tallies_xml(tallies: Any, output_path: Path) -> None:
    try:
        tallies.export_to_xml(str(output_path))
    except TypeError:
        tallies.export_to_xml(path=str(output_path))


def _safe_len(value: Any) -> int | None:
    try:
        return len(value)
    except TypeError:
        return None


def _call_required(module: ModuleType, names: tuple[str, ...], **available: Any) -> Any:
    result = _call_optional(module, names, **available)
    if result is None:
        expected = " or ".join(names)
        raise AttributeError(f"recipe must define {expected}")
    return result


def _call_optional(module: ModuleType, names: tuple[str, ...], **available: Any) -> Any:
    for name in names:
        func = getattr(module, name, None)
        if func is None:
            continue
        if not callable(func):
            raise TypeError(f"recipe {name} must be callable")
        return _call_with_supported_kwargs(func, **available)
    return None


def _call_with_supported_kwargs(func: Any, **available: Any) -> Any:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func()

    if any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        kwargs = available
    else:
        kwargs = {
            name: value
            for name, value in available.items()
            if name in signature.parameters
            and signature.parameters[name].kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }

    missing = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and name not in kwargs
    ]
    if missing:
        raise TypeError(
            f"recipe function {getattr(func, '__name__', func)!r} has unsupported "
            f"required argument(s): {', '.join(missing)}"
        )
    return func(**kwargs)

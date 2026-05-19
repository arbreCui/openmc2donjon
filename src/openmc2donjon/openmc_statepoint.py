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
    ExportSummary,
    _domain_name,
    _domain_volume,
    _energy_bounds_from_library,
    _export_specs_from_library,
    _mapped_domain_name,
    _safe_hdf5_name,
    export_openmc_mgxs_library,
)


@dataclass(frozen=True)
class RecipeExportSummary:
    """Summary for a recipe-driven OpenMC statepoint export."""

    recipe_path: Path
    statepoint_path: Path | None
    statepoint_loaded: bool
    output: ExportSummary


@dataclass(frozen=True)
class RecipeDryRunDomain:
    """One domain or subdomain that would become a DONJON mixture."""

    name: str
    source_label: str
    source_id: Any
    source_type: str
    volume: float
    xs_kwargs: Mapping[str, Any] | None
    attr_keys: tuple[str, ...]


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
    domains: tuple[RecipeDryRunDomain, ...]
    root_attr_keys: tuple[str, ...]
    warnings: tuple[str, ...]


def export_openmc_statepoint_recipe(
    recipe_path: str | Path,
    output_path: str | Path,
    *,
    statepoint_path: str | Path | None = None,
    load_statepoint: bool = True,
    overwrite: bool = True,
) -> RecipeExportSummary:
    """Export an OpenMC MGXS recipe and statepoint to the HDF5 contract.

    The recipe is a Python file with a required ``build_library`` function and
    optional ``domain_specs``, ``domain_names``, ``root_attrs``,
    ``load_statepoint``, and ``postprocess_hdf5`` functions.  Optional recipe
    functions may declare any subset of these keyword arguments:
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

    summary = export_openmc_mgxs_library(
        library,
        output_file,
        domain_specs=domain_specs,
        domain_names=domain_names,
        root_attrs=root_attrs,
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


def dry_run_openmc_statepoint_recipe(
    recipe_path: str | Path,
    *,
    statepoint_path: str | Path | None = None,
    load_statepoint: bool = False,
    output_path: str | Path | None = None,
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
        domains.append(
            RecipeDryRunDomain(
                name=name,
                source_label=_source_label(spec.domain),
                source_id=getattr(spec.domain, "id", None),
                source_type=type(spec.domain).__name__,
                volume=float(spec.volume if spec.volume is not None else _domain_volume(spec.domain)),
                xs_kwargs=spec.xs_kwargs,
                attr_keys=tuple(sorted((spec.attrs or {}).keys())),
            )
        )

    mgxs_types = _library_mgxs_types(library)
    warnings.extend(_mgxs_type_warnings(mgxs_types))
    root_attr_keys = tuple(sorted((root_attrs or {}).keys()))
    return RecipeDryRunSummary(
        recipe_path=recipe_file,
        statepoint_path=statepoint_file,
        statepoint_loaded=statepoint_loaded,
        output_path=output_file,
        energy_groups=len(energy_bounds) - 1,
        legendre_order=_library_legendre_order(library),
        domain_type=_optional_string_attr(library, "domain_type"),
        mgxs_types=mgxs_types,
        domains=tuple(domains),
        root_attr_keys=root_attr_keys,
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


def _optional_string_attr(obj: Any, name: str) -> str | None:
    if not hasattr(obj, name):
        return None
    value = getattr(obj, name)
    if value is None:
        return None
    return str(value)


def _mgxs_type_warnings(mgxs_types: tuple[str, ...]) -> list[str]:
    if not mgxs_types:
        return ["library has no mgxs_types list; required MGXS availability is unchecked"]

    normalized = {value.lower().replace("_", "-") for value in mgxs_types}
    warnings: list[str] = []
    for required in ("total", "absorption", "scatter_matrix"):
        aliases = {alias.lower().replace("_", "-") for alias in MGXS_TYPE_ALIASES[required]}
        if normalized.isdisjoint(aliases):
            rendered = "/".join(MGXS_TYPE_ALIASES[required])
            warnings.append(f"mgxs_types missing required {rendered}")
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
        library.load_from_statepoint(statepoint)


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

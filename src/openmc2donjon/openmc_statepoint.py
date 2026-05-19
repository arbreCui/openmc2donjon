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
from typing import Any

from .export_openmc_mgxs import ExportSummary, export_openmc_mgxs_library


@dataclass(frozen=True)
class RecipeExportSummary:
    """Summary for a recipe-driven OpenMC statepoint export."""

    recipe_path: Path
    statepoint_path: Path | None
    statepoint_loaded: bool
    output: ExportSummary


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

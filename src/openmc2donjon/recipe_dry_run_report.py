"""Human-readable reporting for recipe dry-runs."""

from __future__ import annotations

from .openmc_statepoint import RecipeDryRunSummary


def print_recipe_dry_run_summary(summary: RecipeDryRunSummary) -> None:
    """Print the recipe inspection shared by exporter and one-step CLIs."""

    print("recipe dry-run OK")
    print(f"  recipe: {summary.recipe_path}")
    if summary.statepoint_path is None:
        print("  statepoint: none")
    else:
        loaded = "loaded" if summary.statepoint_loaded else "not loaded"
        print(f"  statepoint: {summary.statepoint_path} ({loaded})")
    if summary.output_path is None:
        print("  output: dry run; no HDF5 written")
    else:
        print(f"  output: {summary.output_path} (not written)")
    print(f"  energy_groups: {summary.energy_groups}")
    print(f"  legendre_order: {summary.legendre_order}")
    print(f"  domain_type: {summary.domain_type or 'unknown'}")
    print(f"  mgxs_types: {_render_list(summary.mgxs_types)}")
    print(f"  mixtures: {len(summary.domains)}")
    print(f"  root_attrs: {_render_list(summary.root_attr_keys)}")
    print("  production_checklist:")
    for check in summary.production_checks:
        print(f"    {check.status:<4} {check.name}: {check.detail}")
    if summary.warnings:
        print("  warnings:")
        for warning in summary.warnings:
            print(f"    - {warning}")
    print("  first_mixtures:")
    for index, domain in enumerate(summary.domains[:20], start=1):
        details = [
            f"source={domain.source_label}",
            f"type={domain.source_type}",
            f"volume={domain.volume:g}",
            f"volume_source={domain.volume_source}",
        ]
        if domain.xs_kwargs:
            details.append(f"xs_kwargs={dict(domain.xs_kwargs)}")
        if domain.attr_keys:
            details.append(f"attrs={list(domain.attr_keys)}")
        print(f"    {index:4d} {domain.name} ({', '.join(details)})")
    remaining = len(summary.domains) - 20
    if remaining > 0:
        print(f"    ... {remaining} more mixtures")


def _render_list(values: tuple[str, ...]) -> str:
    if not values:
        return "none"
    return ", ".join(values)

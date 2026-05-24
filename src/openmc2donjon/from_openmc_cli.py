"""One-step OpenMC recipe/statepoint to DONJON ASCII CLI."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from . import __version__
from ._logging import configure_cli_logging_from_args, get_logger
from .from_openmc_adf import (
    AdfConfig,
    build_flux_ratio_adf,
    flux_ratio_adf_managed_paths,
    inject_adf,
    print_dry_run_adf,
    validate_flux_ratio_adf_config,
)
from .from_openmc_parser import build_parser
from .from_openmc_run_dir import (
    GeneratedArtifacts,
    RunDirConfig,
    apply_run_dir_defaults,
    effective_adf_source,
    finalize_run_dir,
    output_path,
    prepare_run_dir,
    print_dry_run_artifacts,
    print_dry_run_run_dir,
    validate_run_dir_config,
)
from .from_openmc_sph import (
    SphConfig,
    apply_sph_workflow,
    print_dry_run_sph,
    sph_managed_paths,
    validate_sph_config,
)
from .from_openmc_summary import FROM_OPENMC_SUMMARY_SCHEMA
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import production_preflight_defaults, run_preflight
from .multicompo import convert_mgxs_hdf5, read_mgxs_hdf5_histories
from .openmc_statepoint import (
    RecipeExportSummary,
    StatepointLoadError,
    dry_run_openmc_statepoint_recipe,
    export_openmc_statepoint_recipe,
)
from .recipe_dry_run_report import (
    print_recipe_dry_run_summary,
    print_strict_dry_run_decision,
)


logger = get_logger("from_openmc_cli")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_cli_logging_from_args(args)
    _normalize_args(args)
    _validate_args(args, parser)
    try:
        if args.dry_run:
            return 0 if _run_dry_run(args) else 1
        if args.statepoint is None and not args.no_load_statepoint:
            parser.error("--statepoint is required unless --no-load-statepoint is set")

        final_output = output_path(args.output, args.format)
        try:
            prepare_run_dir(
                _run_dir_config(args),
                final_output,
                extra_managed_paths=_workflow_managed_paths(args),
            )
        except ValueError as exc:
            parser.error(str(exc))
        if args.keep_hdf5 is not None:
            return 0 if _run_pipeline(args, args.keep_hdf5, final_output, hdf5_kept=True) else 1
        else:
            with tempfile.TemporaryDirectory(prefix="openmc2donjon_") as tmpdir:
                ok = _run_pipeline(
                    args,
                    Path(tmpdir) / "mgxs_library.h5",
                    final_output,
                    hdf5_kept=False,
                )
                return 0 if ok else 1
    except StatepointLoadError as exc:
        logger.error("%s: error: %s", parser.prog, exc)
        return 1


def _normalize_args(args: argparse.Namespace) -> None:
    if args.production:
        args.check = True
    if args.build_flux_ratio_adf:
        args.check = True
        args.require_adf = True
    if args.sph_source is not None or args.sph_macrolib is not None:
        args.check = True
        args.require_sph = True
    _apply_run_dir_config(args, apply_run_dir_defaults(_run_dir_config(args)))


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        validate_run_dir_config(_run_dir_config(args))
    except ValueError as exc:
        parser.error(str(exc))
    if args.expected_adf_faces is None and args.adf_faces is not None:
        args.expected_adf_faces = args.adf_faces
    try:
        validate_flux_ratio_adf_config(_adf_config(args))
    except ValueError as exc:
        parser.error(str(exc))
    try:
        validate_sph_config(_sph_config(args))
    except ValueError as exc:
        parser.error(str(exc))
    if args.strict_dry_run and not args.dry_run:
        parser.error("--strict-dry-run requires --dry-run")


def _run_dir_config(args: argparse.Namespace) -> RunDirConfig:
    return RunDirConfig(
        run_dir=args.run_dir,
        keep_hdf5=args.keep_hdf5,
        output=args.output,
        output_format=args.format,
        summary_json=args.summary_json,
        check=args.check,
        check_summary_json=args.check_summary_json,
        adf_source=args.adf_source,
        build_flux_ratio_adf=args.build_flux_ratio_adf,
        adf_summary_json=args.adf_summary_json,
        sph_source=args.sph_source,
        sph_macrolib=args.sph_macrolib,
        sph_summary_json=args.sph_summary_json,
        no_validate_bundle=args.no_validate_bundle,
        bundle_validation_summary_json=args.bundle_validation_summary_json,
        no_handoff_summary=args.no_handoff_summary,
        handoff_summary_json=args.handoff_summary_json,
        extra_artifact=tuple(args.extra_artifact),
        force_run_dir=args.force_run_dir,
        recipe=args.recipe,
    )


def _apply_run_dir_config(args: argparse.Namespace, config: RunDirConfig) -> None:
    args.keep_hdf5 = config.keep_hdf5
    args.output = config.output
    args.summary_json = config.summary_json
    args.check_summary_json = config.check_summary_json
    args.adf_summary_json = config.adf_summary_json
    args.sph_summary_json = config.sph_summary_json
    args.bundle_validation_summary_json = config.bundle_validation_summary_json
    args.handoff_summary_json = config.handoff_summary_json


def _sph_config(args: argparse.Namespace) -> SphConfig:
    return SphConfig(
        run_dir=args.run_dir,
        sph_source=args.sph_source,
        sph_macrolib=args.sph_macrolib,
        sph_summary_json=args.sph_summary_json,
        sph_kind=args.sph_kind,
        sph_real=args.sph_real,
        sph_applied=args.sph_applied,
        sph_source_label=args.sph_source_label,
    )


def _adf_config(args: argparse.Namespace) -> AdfConfig:
    return AdfConfig(
        run_dir=args.run_dir,
        statepoint=args.statepoint,
        dry_run=args.dry_run,
        adf_source=args.adf_source,
        adf_faces=args.adf_faces,
        adf_summary_json=args.adf_summary_json,
        adf_kind=args.adf_kind,
        adf_real=args.adf_real,
        adf_source_label=args.adf_source_label,
        build_flux_ratio_adf=args.build_flux_ratio_adf,
        adf_surface_flux=args.adf_surface_flux,
        export_surface_flux=args.export_surface_flux,
        surface_flux_tally_name=args.surface_flux_tally_name,
        surface_flux_mesh_shape=args.surface_flux_mesh_shape,
        surface_flux_mu_edges=args.surface_flux_mu_edges,
        surface_flux_face_area=args.surface_flux_face_area,
        homogeneous_face_flux=args.homogeneous_face_flux,
        low_order_raw_driver=args.low_order_raw_driver,
        low_order_volume_flux=args.low_order_volume_flux,
        low_order_net_current=args.low_order_net_current,
        low_order_net_current_sign_convention=args.low_order_net_current_sign_convention,
        low_order_source_label=args.low_order_source_label,
        adf_face_widths=args.adf_face_widths,
        adf_invalid_fill=args.adf_invalid_fill,
        adf_clip_min=args.adf_clip_min,
        adf_clip_max=args.adf_clip_max,
    )


def _workflow_managed_paths(args: argparse.Namespace) -> list[Path | None]:
    paths = sph_managed_paths(_sph_config(args))
    if args.build_flux_ratio_adf:
        paths.extend(flux_ratio_adf_managed_paths(_adf_config(args)))
    return paths


def _run_dry_run(args: argparse.Namespace) -> bool:
    final_output = output_path(args.output, args.format)
    hdf5_path = args.keep_hdf5
    summary = dry_run_openmc_statepoint_recipe(
        args.recipe,
        statepoint_path=args.statepoint,
        load_statepoint=args.statepoint is not None and not args.no_load_statepoint,
        output_path=hdf5_path,
        scatter_mgxs_type=args.scatter_mgxs_type,
    )
    print_recipe_dry_run_summary(summary)
    print("one-step conversion dry-run OK")
    _print_dry_run_output(args, final_output, hdf5_path)
    print_dry_run_adf(_adf_config(args))
    print_dry_run_sph(_sph_config(args))
    print_dry_run_artifacts(_run_dir_config(args))
    _print_dry_run_checks(args)
    print_dry_run_run_dir(_run_dir_config(args))
    if args.strict_dry_run:
        return print_strict_dry_run_decision(summary)
    return True


def _print_dry_run_output(
    args: argparse.Namespace,
    output_path: Path,
    hdf5_path: Path | None,
) -> None:
    print(f"  format: {args.format}")
    print(f"  ascii_output: {output_path} (not written)")
    if hdf5_path is None:
        print("  hdf5: temporary handoff (not written)")
    else:
        print(f"  hdf5: {hdf5_path} (not written)")
    if args.format == "multicompo":
        print(f"  root_name: {args.root_name}")
    else:
        print("  root_name: n/a")
    print(f"  selected_mixtures: {_render_optional_list(args.mixture)}")
    print(f"  single_point_burnup: {_render_optional_value(args.burnup)}")
    print(f"  h_factor_default: {_render_optional_value(args.h_factor_default)}")
    print(f"  scatter_mgxs_type: {args.scatter_mgxs_type or 'scatter matrix'}")


def _print_dry_run_checks(args: argparse.Namespace) -> None:
    if args.check:
        settings = production_preflight_defaults(
            production=args.production,
            require_mixture_order=False,
            require_domain_mode=args.require_domain_mode,
            require_source_domain_metadata=args.require_source_domain_metadata,
            require_openmc_volume_flux=args.require_openmc_volume_flux,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            require_h_factor=args.require_h_factor,
            scatter_row_balance_warn=args.scatter_row_balance_warn,
            scatter_row_balance_fail=args.scatter_row_balance_fail,
            require_energy_bounds_consistency=getattr(
                args,
                "require_energy_bounds_consistency",
                False,
            ),
            chi_sum_tolerance=getattr(args, "chi_sum_tolerance", None),
            require_adf_face_consistency=getattr(
                args,
                "require_adf_face_consistency",
                False,
            ),
            transport_p1_fail=getattr(args, "transport_p1_fail", None),
            uncertainty_warn=None if args.no_uncertainty_check else args.uncertainty_warn,
            uncertainty_production_fail=(
                None if args.no_uncertainty_check else args.uncertainty_production_fail
            ),
            require_std_dev_coverage=(
                False if args.no_uncertainty_check else args.require_std_dev_coverage
            ),
        )
        print("  check: enabled after HDF5 export")
        print(f"    production: {_yes_no(args.production)}")
        print(f"    require_volume: {_yes_no(settings['require_volume'])}")
        print(f"    require_h_factor: {_yes_no(settings['require_h_factor'])}")
        print(
            "    require_mixture_order: "
            f"{_yes_no(settings['require_mixture_order'])}"
        )
        print(f"    require_domain_mode: {_yes_no(settings['require_domain_mode'])}")
        print(
            "    require_source_domain_metadata: "
            f"{_yes_no(settings['require_source_domain_metadata'])}"
        )
        print(
            "    require_openmc_volume_flux: "
            f"{_yes_no(settings['require_openmc_volume_flux'])}"
        )
        print(
            "    require_transport_dataset: "
            f"{_yes_no(settings['require_transport_dataset'])}"
        )
        print(
            "    expected_energy_group_structure: "
            f"{_render_optional_value(args.expected_energy_group_structure)}"
        )
        print(
            "    expected_energy_bounds: "
            f"{_render_optional_value(args.expected_energy_bounds)}"
        )
        print(
            "    expected_energy_bounds_sha256: "
            f"{_render_optional_value(args.expected_energy_bounds_sha256)}"
        )
        print(f"    require_adf: {_yes_no(args.require_adf)}")
        print(f"    require_sph: {_yes_no(args.require_sph)}")
        print(f"    expected_adf_faces: {_render_optional_value(args.expected_adf_faces)}")
        print(
            "    scatter_row_balance_warn: "
            f"{_render_optional_value(settings['scatter_row_balance_warn'])}"
        )
        print(
            "    scatter_row_balance_fail: "
            f"{_render_optional_value(settings['scatter_row_balance_fail'])}"
        )
        print(
            "    require_energy_bounds_consistency: "
            f"{_yes_no(settings['require_energy_bounds_consistency'])}"
        )
        print(
            "    chi_sum_tolerance: "
            f"{_render_optional_value(settings['chi_sum_tolerance'])}"
        )
        print(
            "    require_adf_face_consistency: "
            f"{_yes_no(settings['require_adf_face_consistency'])}"
        )
        print(
            "    transport_p1_fail: "
            f"{_render_optional_value(settings['transport_p1_fail'])}"
        )
        if args.no_uncertainty_check:
            print("    uncertainty_check: disabled")
        else:
            print(
                "    uncertainty_warn: "
                f"{_render_optional_value(args.uncertainty_warn)}"
            )
            print(
                "    uncertainty_fail: "
                f"{_render_optional_value(args.uncertainty_fail)}"
            )
            print(
                "    uncertainty_production_fail: "
                f"{_render_optional_value(settings['uncertainty_production_fail'])}"
            )
            print(
                "    uncertainty_mean_abs_floor: "
                f"{_render_optional_value(args.uncertainty_mean_abs_floor)}"
            )
            print(
                "    require_std_dev_coverage: "
                f"{_yes_no(settings['require_std_dev_coverage'])}"
            )
        if args.check_summary_json is None:
            print("    check_summary_json: none")
        else:
            print(f"    check_summary_json: {args.check_summary_json} (not written)")
    else:
        print("  check: disabled")


def _run_pipeline(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
    *,
    hdf5_kept: bool,
) -> bool:
    generated = GeneratedArtifacts()
    recipe_summary = _export_pipeline_hdf5(args, hdf5_path)
    export_summary = recipe_summary.output

    _apply_pipeline_corrections(args, hdf5_path, recipe_summary, generated)
    if not _run_pipeline_preflight(args, hdf5_path, output_path, hdf5_kept=hdf5_kept):
        return False

    histories, _energy_bounds, burnup_values = read_mgxs_hdf5_histories(
        hdf5_path,
        h_factor_default=args.h_factor_default,
    )
    nstates = histories[0].nstates if histories else 0
    _print_pipeline_readiness(histories, nstates, burnup_values)
    _convert_pipeline_hdf5(args, hdf5_path, output_path)
    summary = _write_pipeline_summary(
        args,
        recipe_path=recipe_summary.recipe_path,
        statepoint_path=recipe_summary.statepoint_path,
        hdf5_path=hdf5_path,
        hdf5_kept=hdf5_kept,
        output_path=output_path,
        mixture_names=[history.name for history in histories],
        nstates=nstates,
        burnup_values=burnup_values,
        energy_groups=export_summary.energy_groups,
        legendre_order=export_summary.legendre_order,
        std_dev_dataset_count=export_summary.std_dev_dataset_count,
        std_dev_expected_dataset_count=export_summary.std_dev_expected_dataset_count,
    )
    return finalize_run_dir(
        _run_dir_config(args),
        hdf5_path=hdf5_path,
        output_path=output_path,
        recipe_path=recipe_summary.recipe_path,
        statepoint_path=recipe_summary.statepoint_path,
        summary=summary,
        generated=generated,
    )


def _export_pipeline_hdf5(
    args: argparse.Namespace,
    hdf5_path: Path,
) -> RecipeExportSummary:
    recipe_summary = export_openmc_statepoint_recipe(
        args.recipe,
        hdf5_path,
        statepoint_path=args.statepoint,
        load_statepoint=not args.no_load_statepoint,
        scatter_mgxs_type=args.scatter_mgxs_type,
        overwrite=not args.no_overwrite_hdf5,
    )
    export_summary = recipe_summary.output
    print(
        f"exported {len(export_summary.domains)} domains, "
        f"{export_summary.energy_groups} groups, P{export_summary.legendre_order} "
        f"from recipe {recipe_summary.recipe_path} "
        f"(std_dev {export_summary.std_dev_dataset_count}/"
        f"{export_summary.std_dev_expected_dataset_count})"
    )
    return recipe_summary


def _apply_pipeline_corrections(
    args: argparse.Namespace,
    hdf5_path: Path,
    recipe_summary: RecipeExportSummary,
    generated: GeneratedArtifacts,
) -> None:
    if args.build_flux_ratio_adf:
        generated.adf_source, generated.adf_artifacts = build_flux_ratio_adf(
            _adf_config(args),
            hdf5_path,
            statepoint_path=recipe_summary.statepoint_path,
        )

    adf_source = effective_adf_source(_run_dir_config(args), generated)
    if adf_source is not None:
        inject_adf(_adf_config(args), hdf5_path, adf_source=adf_source)

    generated.sph_source, generated.sph_artifacts = apply_sph_workflow(
        _sph_config(args),
        hdf5_path,
    )


def _run_pipeline_preflight(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
    *,
    hdf5_kept: bool,
) -> bool:
    if not args.check:
        return True
    ok = run_preflight(
        [hdf5_path],
        output_format=args.format,
        output_path=output_path,
        production=args.production,
        require_adf=args.require_adf,
        require_sph=args.require_sph,
        expected_adf_faces=args.expected_adf_faces,
        require_domain_mode=args.require_domain_mode,
        require_source_domain_metadata=args.require_source_domain_metadata,
        require_openmc_volume_flux=args.require_openmc_volume_flux,
        require_transport_dataset=args.require_transport_dataset,
        require_volume=args.require_volume,
        require_h_factor=args.require_h_factor,
        expected_energy_group_structure=args.expected_energy_group_structure,
        expected_energy_bounds=args.expected_energy_bounds,
        expected_energy_bounds_sha256=args.expected_energy_bounds_sha256,
        scatter_row_balance_warn=args.scatter_row_balance_warn,
        scatter_row_balance_fail=args.scatter_row_balance_fail,
        require_energy_bounds_consistency=args.require_energy_bounds_consistency,
        chi_sum_tolerance=args.chi_sum_tolerance,
        require_adf_face_consistency=args.require_adf_face_consistency,
        transport_p1_fail=args.transport_p1_fail,
        uncertainty_warn=None if args.no_uncertainty_check else args.uncertainty_warn,
        uncertainty_fail=None if args.no_uncertainty_check else args.uncertainty_fail,
        uncertainty_production_fail=(
            None if args.no_uncertainty_check else args.uncertainty_production_fail
        ),
        uncertainty_mean_abs_floor=args.uncertainty_mean_abs_floor,
        require_std_dev_coverage=(
            False if args.no_uncertainty_check else args.require_std_dev_coverage
        ),
        summary_json=args.check_summary_json,
    )
    if not ok and hdf5_kept:
        print(f"kept HDF5: {hdf5_path}")
    return ok


def _print_pipeline_readiness(histories, nstates: int, burnup_values) -> None:
    burnup_detail = "none" if burnup_values is None else str(len(burnup_values))
    print(
        f"preflight OK: mixtures={len(histories)} "
        f"state_points={nstates} burnup_axis={burnup_detail}"
    )


def _convert_pipeline_hdf5(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
) -> None:
    if args.format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            hdf5_path,
            output_path,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    else:
        convert_mgxs_hdf5(
            hdf5_path,
            output_path,
            root_name=args.root_name,
            comment=args.comment,
            burnup=args.burnup,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    if args.keep_hdf5 is not None:
        print(f"kept HDF5: {hdf5_path}")
    print(f"wrote {args.format}: {output_path}")


def _write_pipeline_summary(
    args: argparse.Namespace,
    *,
    recipe_path: Path,
    statepoint_path: Path | None,
    hdf5_path: Path,
    hdf5_kept: bool,
    output_path: Path,
    mixture_names: list[str],
    nstates: int,
    burnup_values,
    energy_groups: int,
    legendre_order: int,
    std_dev_dataset_count: int,
    std_dev_expected_dataset_count: int,
) -> dict[str, object]:
    summary = _summary_payload(
        args,
        recipe_path=recipe_path,
        statepoint_path=statepoint_path,
        hdf5_path=hdf5_path,
        hdf5_kept=hdf5_kept,
        output_path=output_path,
        mixture_names=mixture_names,
        nstates=nstates,
        burnup_values=burnup_values,
        energy_groups=energy_groups,
        legendre_order=legendre_order,
        std_dev_dataset_count=std_dev_dataset_count,
        std_dev_expected_dataset_count=std_dev_expected_dataset_count,
    )
    if args.summary_json is not None:
        _write_json(args.summary_json, summary)
        print(f"wrote summary: {args.summary_json}")
    return summary


def _render_optional_list(values: list[str] | None) -> str:
    if not values:
        return "all"
    return ", ".join(values)


def _render_optional_value(value: object) -> str:
    if value is None:
        return "none"
    return str(value)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _summary_payload(
    args: argparse.Namespace,
    *,
    recipe_path: Path,
    statepoint_path: Path | None,
    hdf5_path: Path,
    hdf5_kept: bool,
    output_path: Path,
    mixture_names: list[str],
    nstates: int,
    burnup_values,
    energy_groups: int,
    legendre_order: int,
    std_dev_dataset_count: int,
    std_dev_expected_dataset_count: int,
) -> dict[str, object]:
    burnup_summary: dict[str, object] = {"present": burnup_values is not None}
    if burnup_values is not None:
        values = [float(value) for value in burnup_values]
        burnup_summary.update(
            {
                "count": len(values),
                "values": values,
            }
        )

    return {
        "schema": FROM_OPENMC_SUMMARY_SCHEMA,
        "package_version": __version__,
        "recipe": str(recipe_path),
        "statepoint": None if statepoint_path is None else str(statepoint_path),
        "loaded_statepoint": not args.no_load_statepoint,
        "hdf5": str(hdf5_path),
        "hdf5_kept": hdf5_kept,
        "output": str(output_path),
        "format": args.format,
        "energy_groups": energy_groups,
        "legendre_order": legendre_order,
        "std_dev_dataset_count": std_dev_dataset_count,
        "std_dev_expected_dataset_count": std_dev_expected_dataset_count,
        "mixture_count": len(mixture_names),
        "mixture_names": mixture_names,
        "state_points": nstates,
        "burnup_axis": burnup_summary,
        "checked": bool(args.check),
        "check_passed": True if args.check else None,
        "check_summary_json": (
            str(args.check_summary_json)
            if args.check and args.check_summary_json is not None
            else None
        ),
        "selected_mixtures": args.mixture or None,
        "root_name": args.root_name if args.format == "multicompo" else None,
        "single_point_burnup": args.burnup,
        "h_factor_default": args.h_factor_default,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

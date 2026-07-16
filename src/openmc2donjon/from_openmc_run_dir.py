"""Run-directory packaging for the one-step OpenMC CLI."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .bundle import (
    ArtifactSpec,
    bundle_artifacts,
    parse_extra_artifact,
    validate_bundle,
)
from .handoff_summary import write_handoff_summary
from .openmc_provenance import file_sha256


_MAX_AUTO_BUNDLED_SOURCE_BYTES = 64 * 1024 * 1024
_AUTO_BUNDLED_SOURCE_SUFFIXES = {
    ".json",
    ".py",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True, slots=True)
class RunDirConfig:
    run_dir: Path | None
    keep_hdf5: Path | None
    output: str | None
    output_format: str
    summary_json: Path | None
    check: bool
    check_summary_json: Path | None
    adf_source: Path | None
    build_flux_ratio_adf: bool
    adf_summary_json: Path | None
    sph_source: Path | None
    sph_macrolib: Path | None
    sph_summary_json: Path | None
    no_validate_bundle: bool
    bundle_validation_summary_json: Path | None
    no_handoff_summary: bool
    handoff_summary_json: Path | None
    extra_artifact: tuple[str, ...]
    force_run_dir: bool
    recipe: Path


@dataclass(slots=True)
class GeneratedArtifacts:
    adf_source: Path | None = None
    adf_artifacts: list[ArtifactSpec] = field(default_factory=list)
    sph_source: Path | None = None
    sph_artifacts: list[ArtifactSpec] = field(default_factory=list)


def apply_run_dir_defaults(config: RunDirConfig) -> RunDirConfig:
    if config.run_dir is None:
        return config
    run_dir = config.run_dir
    updates: dict[str, object] = {}
    if config.keep_hdf5 is None:
        updates["keep_hdf5"] = run_dir / "mgxs_library.h5"
    if config.output is None:
        updates["output"] = str(run_dir / default_output_name(config.output_format))
    if config.summary_json is None:
        updates["summary_json"] = run_dir / "run_summary.json"
    if config.check and config.check_summary_json is None:
        updates["check_summary_json"] = run_dir / "check_summary.json"
    if (config.adf_source is not None or config.build_flux_ratio_adf) and config.adf_summary_json is None:
        updates["adf_summary_json"] = run_dir / "adf_summary.json"
    if (config.sph_source is not None or config.sph_macrolib is not None) and config.sph_summary_json is None:
        updates["sph_summary_json"] = run_dir / "sph_summary.json"
    if not config.no_validate_bundle and config.bundle_validation_summary_json is None:
        updates["bundle_validation_summary_json"] = run_dir / "bundle_validation_summary.json"
    if not config.no_handoff_summary and config.handoff_summary_json is None:
        updates["handoff_summary_json"] = run_dir / "handoff_summary.json"
    return replace(config, **updates)


def validate_run_dir_config(config: RunDirConfig) -> None:
    if config.bundle_validation_summary_json is not None and config.run_dir is None:
        raise ValueError("--bundle-validation-summary-json requires --run-dir")
    if config.handoff_summary_json is not None and config.run_dir is None:
        raise ValueError("--handoff-summary-json requires --run-dir")
    if config.extra_artifact and config.run_dir is None:
        raise ValueError("--extra-artifact requires --run-dir")
    if config.no_validate_bundle and config.bundle_validation_summary_json is not None:
        raise ValueError("--bundle-validation-summary-json cannot be used with --no-validate-bundle")
    if config.no_handoff_summary and config.handoff_summary_json is not None:
        raise ValueError("--handoff-summary-json cannot be used with --no-handoff-summary")
    extra_artifacts_from_config(config)


def print_dry_run_artifacts(config: RunDirConfig) -> None:
    if config.extra_artifact:
        print("  extra_artifacts:")
        for artifact in extra_artifacts_from_config(config):
            print(f"    {artifact.label}: {artifact.source} (not copied)")
    else:
        print("  extra_artifacts: none")
    if config.summary_json is None:
        print("  summary_json: none")
    else:
        print(f"  summary_json: {config.summary_json} (not written)")


def print_dry_run_run_dir(config: RunDirConfig) -> None:
    if config.run_dir is not None:
        if config.no_validate_bundle:
            print("  bundle_validation_summary_json: disabled")
        else:
            print(
                "  bundle_validation_summary_json: "
                f"{config.bundle_validation_summary_json} (not written)"
            )
        if config.no_handoff_summary:
            print("  handoff_summary_json: disabled")
        else:
            print(f"  handoff_summary_json: {config.handoff_summary_json} (not written)")


def prepare_run_dir(
    config: RunDirConfig,
    output_path: Path,
    *,
    extra_managed_paths: list[Path | None],
) -> None:
    if config.run_dir is None:
        return
    managed_paths = _managed_run_dir_paths(config, output_path)
    managed_paths.extend(extra_managed_paths)
    existing = [path for path in managed_paths if path is not None and path.exists()]
    if existing and not config.force_run_dir:
        rendered = ", ".join(str(path) for path in existing)
        raise ValueError(f"--run-dir managed artifacts already exist; use --force-run-dir: {rendered}")
    config.run_dir.mkdir(parents=True, exist_ok=True)


def finalize_run_dir(
    config: RunDirConfig,
    *,
    hdf5_path: Path,
    output_path: Path,
    recipe_path: Path,
    statepoint_path: Path | None,
    summary: dict[str, object],
    generated: GeneratedArtifacts,
) -> bool:
    if config.run_dir is None:
        return True

    provenance_path = config.run_dir / "openmc_provenance.json"
    provenance = summary.get("openmc_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("run summary is missing OpenMC provenance")
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = config.run_dir / "manifest.json"
    _write_run_dir_manifest(
        config,
        hdf5_path,
        output_path,
        recipe_path,
        summary=summary,
        provenance_path=provenance_path,
        generated=generated,
    )
    report = None
    if not config.no_validate_bundle:
        report = validate_bundle(
            manifest_path,
            summary_json=config.bundle_validation_summary_json,
        )
    if not config.no_handoff_summary:
        write_handoff_summary(
            config.handoff_summary_json,
            package_version=__version__,
            run_dir=config.run_dir,
            summary=summary,
            recipe_path=recipe_path,
            statepoint_path=statepoint_path,
            hdf5_path=hdf5_path,
            output_path=output_path,
            output_format=config.output_format,
            run_summary_json=config.summary_json,
            check_summary_json=config.check_summary_json if config.check else None,
            manifest_path=manifest_path,
            bundle_validation_summary_json=(
                config.bundle_validation_summary_json
                if not config.no_validate_bundle
                else None
            ),
            bundle_validation_passed=None if report is None else report.ok,
            bundle_validation_decision=None if report is None else report.decision,
            adf_enabled=effective_adf_source(config, generated) is not None,
            sph_enabled=effective_sph_source(config, generated) is not None,
        )
        print(f"wrote handoff summary: {config.handoff_summary_json}")
    return report is None or report.ok


def output_path(raw_output: str | None, output_format: str) -> Path:
    if raw_output:
        return Path(raw_output)
    return Path(default_output_name(output_format))


def default_output_name(output_format: str) -> str:
    if output_format == "macrolib":
        return "out.macrolib.txt"
    return "out.mcompo.txt"


def effective_adf_source(
    config: RunDirConfig,
    generated: GeneratedArtifacts | None = None,
) -> Path | None:
    if generated is not None and generated.adf_source is not None:
        return generated.adf_source
    return config.adf_source


def effective_sph_source(
    config: RunDirConfig,
    generated: GeneratedArtifacts | None = None,
) -> Path | None:
    if generated is not None and generated.sph_source is not None:
        return generated.sph_source
    return config.sph_source


def extra_artifacts_from_config(config: RunDirConfig) -> list[ArtifactSpec]:
    artifacts: list[ArtifactSpec] = []
    for raw in config.extra_artifact:
        try:
            artifacts.append(parse_extra_artifact(raw))
        except ValueError as exc:
            raise ValueError(f"--extra-artifact {raw!r}: {exc}") from exc
    return artifacts


def _managed_run_dir_paths(
    config: RunDirConfig,
    output_path: Path,
) -> list[Path | None]:
    run_dir = config.run_dir
    managed_paths = [
        config.keep_hdf5,
        output_path,
        config.summary_json,
        run_dir / "openmc_provenance.json",
        run_dir / "manifest.json",
    ]
    if not config.no_validate_bundle:
        managed_paths.append(config.bundle_validation_summary_json)
    if not config.no_handoff_summary:
        managed_paths.append(config.handoff_summary_json)
    _append_run_dir_copy(managed_paths, run_dir, config.recipe)
    if config.check:
        managed_paths.append(config.check_summary_json)
    if config.adf_source is not None:
        managed_paths.append(config.adf_summary_json)
        _append_run_dir_copy(managed_paths, run_dir, config.adf_source)
    for artifact in extra_artifacts_from_config(config):
        _append_run_dir_copy(managed_paths, run_dir, artifact.source)
    return managed_paths


def _write_run_dir_manifest(
    config: RunDirConfig,
    hdf5_path: Path,
    output_path: Path,
    recipe_path: Path,
    *,
    summary: Mapping[str, object],
    provenance_path: Path,
    generated: GeneratedArtifacts,
) -> None:
    artifacts = [ArtifactSpec(label="mgxs", source=hdf5_path)]
    if config.output_format == "macrolib":
        artifacts.append(ArtifactSpec(label="macrolib", source=output_path))
    else:
        artifacts.append(ArtifactSpec(label="mcompo", source=output_path))
    if config.summary_json is not None:
        artifacts.append(ArtifactSpec(label="run-summary", source=config.summary_json))
    if config.check and config.check_summary_json is not None:
        artifacts.append(ArtifactSpec(label="check-summary", source=config.check_summary_json))
    adf_source = effective_adf_source(config, generated)
    if adf_source is not None:
        artifacts.append(ArtifactSpec(label="adf-source", source=adf_source))
        if config.adf_summary_json is not None:
            artifacts.append(ArtifactSpec(label="adf-summary", source=config.adf_summary_json))
    artifacts.extend(generated.adf_artifacts)
    sph_source = effective_sph_source(config, generated)
    if sph_source is not None:
        artifacts.append(ArtifactSpec(label="sph-source", source=sph_source))
        if config.sph_summary_json is not None:
            artifacts.append(ArtifactSpec(label="sph-summary", source=config.sph_summary_json))
    artifacts.extend(generated.sph_artifacts)
    artifacts.extend(extra_artifacts_from_config(config))
    artifacts.append(ArtifactSpec(label="recipe", source=recipe_path))
    artifacts.append(
        ArtifactSpec(label="openmc-provenance", source=provenance_path)
    )
    artifacts.extend(
        _portable_provenance_artifacts(summary, existing=artifacts)
    )
    bundle_artifacts(
        output_dir=config.run_dir,
        artifacts=artifacts,
        force=True,
    )


def _portable_provenance_artifacts(
    summary: Mapping[str, object],
    *,
    existing: list[ArtifactSpec],
) -> list[ArtifactSpec]:
    """Return small source-definition files that make a run bundle replayable.

    Statepoints and nuclear-data libraries are hash-bound but deliberately not
    copied by default because they can be many gigabytes. The model XML,
    imported source files declared by the recipe, and cross_sections.xml are
    portable and belong in the standard research bundle.
    """

    provenance = summary.get("openmc_provenance")
    if not isinstance(provenance, Mapping):
        return []
    seen = {_resolved(spec.source) for spec in existing}
    candidates: list[tuple[str, Any, Any, Any]] = []
    raw_artifacts = provenance.get("artifacts")
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts:
            if not isinstance(item, Mapping):
                continue
            role = str(item.get("role") or "source")
            if role in {"recipe", "statepoint"}:
                continue
            candidates.append(
                (
                    role,
                    item.get("path"),
                    item.get("sha256"),
                    item.get("size_bytes"),
                )
            )
    nuclear_data = provenance.get("nuclear_data")
    if isinstance(nuclear_data, Mapping):
        cross_sections = nuclear_data.get("cross_sections")
        if isinstance(cross_sections, Mapping):
            candidates.append(
                (
                    "cross-sections",
                    cross_sections.get("path"),
                    cross_sections.get("sha256"),
                    cross_sections.get("size_bytes"),
                )
            )

    result: list[ArtifactSpec] = []
    used_labels = {spec.label for spec in existing}
    for role, raw_path, expected_sha256, expected_size in candidates:
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path)
        resolved = _resolved(path)
        if resolved in seen or not path.is_file():
            continue
        if (
            path.suffix.lower() not in _AUTO_BUNDLED_SOURCE_SUFFIXES
            or path.stat().st_size > _MAX_AUTO_BUNDLED_SOURCE_BYTES
        ):
            continue
        actual_size = path.stat().st_size
        actual_sha256 = file_sha256(path)
        if expected_size != actual_size or expected_sha256 != actual_sha256:
            raise ValueError(
                f"OpenMC provenance source changed after collection: {path}"
            )
        label_base = "openmc-" + role.lower().replace("_", "-").replace(" ", "-")
        label = label_base
        suffix = 2
        while label in used_labels:
            label = f"{label_base}-{suffix}"
            suffix += 1
        result.append(ArtifactSpec(label=label, source=path))
        used_labels.add(label)
        seen.add(resolved)
    return result


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _append_run_dir_copy(
    paths: list[Path | None],
    run_dir: Path,
    source: Path,
) -> None:
    destination = run_dir / source.name
    if not _same_path(source, destination):
        paths.append(destination)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()

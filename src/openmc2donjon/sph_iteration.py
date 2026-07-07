"""Build SPH update tables from reference and low-order fluxes."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
from typing import Any

import numpy as np

from . import __version__
from .constants import MGXS_DONJON_GROUP_ORDER
from .hdf5_names import read_mixture_names
from .sph_augment import load_sph_source


SCHEMA = "openmc2donjon.sph-iteration-table.v1"
PASS_DECISION = "openmc2donjon_sph_iteration_table_passed"
FLUX_NORMALIZATIONS = ("none", "total", "power", "auto")
ZERO_FLUX_POLICIES = ("reject", "identity")
H_FACTOR_DATASETS = (
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
)
FLUX_DATASETS = (
    "volume_flux",
    "flux",
    "scalar_flux",
    "reference_flux",
    "low_order_flux",
    "phi",
)
DIAGNOSTIC_BIN_LIMIT = 10


@dataclass(frozen=True)
class LoadedMatrix:
    values: np.ndarray
    path: Path
    dataset_path: str | None = None
    std_dev: np.ndarray | None = None
    std_dev_dataset_path: str | None = None
    max_relative_std_dev: float | None = None


@dataclass(frozen=True)
class SphUpdateBinDiagnostic:
    mixture: str
    group: int
    reference_flux: float
    low_order_flux: float
    raw_update: float
    signed_residual: float
    residual: float
    previous_sph: float
    unclipped_sph: float
    sph: float
    clipped: bool


@dataclass(frozen=True)
class SphUpdateTableReport:
    input_h5: Path
    output_table: Path
    reference_flux_source: Path
    reference_flux_dataset: str | None
    low_order_flux_source: Path
    low_order_flux_dataset: str | None
    reference_flux_std_dev_dataset: str | None
    reference_flux_max_relative_std_dev: float | None
    low_order_flux_std_dev_dataset: str | None
    low_order_flux_max_relative_std_dev: float | None
    previous_sph_source: Path | None
    previous_sph_dataset: str | None
    mixture_names: tuple[str, ...]
    energy_groups: int
    damping: float
    clip_min: float | None
    clip_max: float | None
    flux_normalization: str
    normalization_factor: float
    reference_normalization_integral: float | None
    low_order_normalization_integral: float | None
    normalization_weight_source: str | None
    reference_flux_minimum: float
    reference_flux_maximum: float
    low_order_flux_minimum: float
    low_order_flux_maximum: float
    normalized_low_order_flux_minimum: float
    normalized_low_order_flux_maximum: float
    raw_update_minimum: float
    raw_update_maximum: float
    previous_sph_minimum: float
    previous_sph_maximum: float
    sph_minimum: float
    sph_maximum: float
    clipped_count: int
    zero_flux_policy: str
    identity_bin_count: int
    flux_floor_rel: float | None
    floored_bin_count: int
    freeze_groups: tuple[int, ...] | None
    frozen_group_bin_count: int
    worst_residual_bins: tuple[SphUpdateBinDiagnostic, ...]
    clipped_bins: tuple[SphUpdateBinDiagnostic, ...]
    source_label: str


def create_sph_update_table(
    input_h5: Path,
    output_table: Path,
    *,
    reference_flux: str | Path,
    low_order_flux: str | Path,
    previous_sph: str | Path | None = None,
    damping: float = 1.0,
    clip_min: float | None = None,
    clip_max: float | None = None,
    flux_normalization: str = "none",
    zero_flux_policy: str = "reject",
    flux_floor_rel: float | None = None,
    freeze_groups: tuple[int, ...] | None = None,
    require_reference_flux_std_dev: bool = False,
    max_reference_flux_std_dev_rel: float | None = None,
    require_low_order_flux_std_dev: bool = False,
    max_low_order_flux_std_dev_rel: float | None = None,
    source_label: str = "external low-order SPH iteration",
    force: bool = False,
    summary_json: Path | None = None,
) -> SphUpdateTableReport:
    """Write the next SPH factors as a CSV table.

    The update is multiplicative and damped.  If ``flux_normalization`` is not
    ``"none"``, the low-order flux is first scaled to the reference flux's
    global normalization:

    ``next_sph = previous_sph * (reference_flux / normalized_low_order_flux) ** damping``.

    DONJON's ``DSPH``/``MAC`` path treats ``NSPH`` as a divisor on the
    macroscopic data.  A low-order flux that is too high must therefore produce
    an SPH factor below unity so the corrected cross sections increase.

    If no previous SPH source is supplied, unity factors are used.
    """

    input_h5 = Path(input_h5)
    output_table = Path(output_table)
    if not input_h5.exists():
        raise FileNotFoundError(f"input HDF5 does not exist: {input_h5}")
    if output_table.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_table}")
    flux_normalization = _normalize_flux_normalization(flux_normalization)
    if zero_flux_policy not in ZERO_FLUX_POLICIES:
        allowed = ", ".join(ZERO_FLUX_POLICIES)
        raise ValueError(f"--zero-flux-policy must be one of: {allowed}")
    _validate_update_options(
        damping=damping,
        clip_min=clip_min,
        clip_max=clip_max,
        flux_floor_rel=flux_floor_rel,
    )

    mixture_names, energy_groups = _read_mgxs_metadata(input_h5)
    freeze_groups = _normalize_freeze_groups(freeze_groups, energy_groups=energy_groups)
    reference = _load_matrix_source(
        reference_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=("reference_flux", "flux", "phi", "value"),
        label="reference flux",
    )
    low_order = _load_matrix_source(
        low_order_flux,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=("low_order_flux", "flux", "phi", "value"),
        label="low-order flux",
    )
    previous = _load_previous_sph(
        previous_sph,
        input_h5=input_h5,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
    )

    floored_mask = _floored_flux_mask(reference.values, flux_floor_rel=flux_floor_rel)
    frozen_groups_mask = _freeze_groups_mask(
        freeze_groups,
        mixture_count=len(mixture_names),
        energy_groups=energy_groups,
    )
    exempt_mask = _union_masks(floored_mask, frozen_groups_mask)
    identity_mask = _identity_zero_flux_mask(
        reference.values,
        low_order.values,
        mixture_names=mixture_names,
        zero_flux_policy=zero_flux_policy,
        exempt_mask=exempt_mask,
    )
    # Frozen bins (identity zeros, below-floor bins, frozen groups) pass
    # raw_update 1.0 through the update and are exempt from positivity and
    # std-dev gates.
    frozen_mask = _union_masks(identity_mask, exempt_mask)
    if frozen_mask is not None:
        reference = replace(
            reference,
            max_relative_std_dev=_max_relative_std_dev(
                reference.values, reference.std_dev, exclude_mask=frozen_mask
            ),
        )
        low_order = replace(
            low_order,
            max_relative_std_dev=_max_relative_std_dev(
                low_order.values, low_order.std_dev, exclude_mask=frozen_mask
            ),
        )
    _validate_flux(reference.values, "reference flux", zero_mask=frozen_mask)
    _validate_flux(low_order.values, "low-order flux", zero_mask=frozen_mask)
    _validate_flux_std_dev_gate(
        reference,
        "reference flux",
        required=require_reference_flux_std_dev,
        max_relative=max_reference_flux_std_dev_rel,
    )
    _validate_flux_std_dev_gate(
        low_order,
        "low-order flux",
        required=require_low_order_flux_std_dev,
        max_relative=max_low_order_flux_std_dev_rel,
    )
    _validate_sph(previous.values, "previous SPH")

    normalized_low_order, normalization = _normalized_low_order_flux(
        input_h5,
        reference_flux=reference.values,
        low_order_flux=low_order.values,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        flux_normalization=flux_normalization,
        zero_mask=frozen_mask,
    )
    resolved_flux_normalization = str(normalization["flux_normalization"])
    # The ratio must be reference/low-order: NSPH divides the macroscopic
    # data, which scales the next MG flux by the applied SPH factor, so this
    # orientation makes the iteration contract (log-error factor 1-damping);
    # the inverse orientation amplifies it (factor 1+damping) and diverges.
    if frozen_mask is None:
        raw_update = reference.values / normalized_low_order
    else:
        # Frozen bins force raw_update to 1.0 so the updated SPH keeps the
        # previous value there.
        raw_update = np.divide(
            reference.values,
            normalized_low_order,
            out=np.ones_like(reference.values),
            where=~frozen_mask,
        )
    # Disjoint attribution: identity zeros first, then the explicit group
    # list, then the floor, so the three counters sum to the frozen total.
    identity_bin_count = 0 if identity_mask is None else int(np.count_nonzero(identity_mask))
    frozen_group_bin_count = _masked_count(frozen_groups_mask, exclude=identity_mask)
    floored_bin_count = _masked_count(
        floored_mask,
        exclude=_union_masks(identity_mask, frozen_groups_mask),
    )
    unclipped = previous.values * np.power(raw_update, float(damping))
    updated = unclipped.copy()
    clipped_mask = np.zeros_like(updated, dtype=bool)
    if clip_min is not None or clip_max is not None:
        lower = -np.inf if clip_min is None else float(clip_min)
        upper = np.inf if clip_max is None else float(clip_max)
        updated = np.clip(updated, lower, upper)
        clipped_mask = unclipped != updated
    clipped_count = int(np.count_nonzero(clipped_mask))
    _validate_sph(updated, "updated SPH")
    worst_residual_bins = _top_residual_bins(
        mixture_names=mixture_names,
        reference_flux=reference.values,
        low_order_flux=normalized_low_order,
        raw_update=raw_update,
        previous_sph=previous.values,
        unclipped_sph=unclipped,
        sph=updated,
        clipped_mask=clipped_mask,
    )
    clipped_bins = _top_clipped_bins(
        mixture_names=mixture_names,
        reference_flux=reference.values,
        low_order_flux=normalized_low_order,
        raw_update=raw_update,
        previous_sph=previous.values,
        unclipped_sph=unclipped,
        sph=updated,
        clipped_mask=clipped_mask,
    )

    _write_sph_table(output_table, mixture_names=mixture_names, values=updated)
    report = SphUpdateTableReport(
        input_h5=input_h5,
        output_table=output_table,
        reference_flux_source=reference.path,
        reference_flux_dataset=reference.dataset_path,
        low_order_flux_source=low_order.path,
        low_order_flux_dataset=low_order.dataset_path,
        reference_flux_std_dev_dataset=reference.std_dev_dataset_path,
        reference_flux_max_relative_std_dev=reference.max_relative_std_dev,
        low_order_flux_std_dev_dataset=low_order.std_dev_dataset_path,
        low_order_flux_max_relative_std_dev=low_order.max_relative_std_dev,
        previous_sph_source=None if previous_sph is None else previous.path,
        previous_sph_dataset=None if previous_sph is None else previous.dataset_path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        damping=float(damping),
        clip_min=None if clip_min is None else float(clip_min),
        clip_max=None if clip_max is None else float(clip_max),
        flux_normalization=resolved_flux_normalization,
        normalization_factor=normalization["factor"],
        reference_normalization_integral=normalization["reference_integral"],
        low_order_normalization_integral=normalization["low_order_integral"],
        normalization_weight_source=normalization["weight_source"],
        reference_flux_minimum=float(np.min(reference.values)),
        reference_flux_maximum=float(np.max(reference.values)),
        low_order_flux_minimum=float(np.min(low_order.values)),
        low_order_flux_maximum=float(np.max(low_order.values)),
        normalized_low_order_flux_minimum=float(np.min(normalized_low_order)),
        normalized_low_order_flux_maximum=float(np.max(normalized_low_order)),
        raw_update_minimum=float(np.min(raw_update)),
        raw_update_maximum=float(np.max(raw_update)),
        previous_sph_minimum=float(np.min(previous.values)),
        previous_sph_maximum=float(np.max(previous.values)),
        sph_minimum=float(np.min(updated)),
        sph_maximum=float(np.max(updated)),
        clipped_count=clipped_count,
        zero_flux_policy=zero_flux_policy,
        identity_bin_count=identity_bin_count,
        flux_floor_rel=None if flux_floor_rel is None else float(flux_floor_rel),
        floored_bin_count=floored_bin_count,
        freeze_groups=freeze_groups,
        frozen_group_bin_count=frozen_group_bin_count,
        worst_residual_bins=worst_residual_bins,
        clipped_bins=clipped_bins,
        source_label=source_label,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: SphUpdateTableReport) -> None:
    print("OpenMC-to-DONJON SPH update table")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_table}")
    print(f"  reference_flux: {report.reference_flux_source}")
    if report.reference_flux_dataset is not None:
        print(f"  reference_flux_dataset: {report.reference_flux_dataset}")
    if report.reference_flux_std_dev_dataset is not None:
        print(
            "  reference_flux_std_dev: "
            f"{report.reference_flux_std_dev_dataset} "
            f"max_rel={report.reference_flux_max_relative_std_dev:g}"
        )
    print(f"  low_order_flux: {report.low_order_flux_source}")
    if report.low_order_flux_dataset is not None:
        print(f"  low_order_flux_dataset: {report.low_order_flux_dataset}")
    if report.low_order_flux_std_dev_dataset is not None:
        print(
            "  low_order_flux_std_dev: "
            f"{report.low_order_flux_std_dev_dataset} "
            f"max_rel={report.low_order_flux_max_relative_std_dev:g}"
        )
    if report.previous_sph_source is not None:
        print(f"  previous_sph: {report.previous_sph_source}")
        if report.previous_sph_dataset is not None:
            print(f"  previous_sph_dataset: {report.previous_sph_dataset}")
    print(
        f"  mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"damping={report.damping:g} clipped={report.clipped_count}"
    )
    if report.zero_flux_policy != "reject":
        print(
            f"  zero_flux_policy: {report.zero_flux_policy} "
            f"identity_bins={report.identity_bin_count}"
        )
    if report.flux_floor_rel is not None:
        print(
            f"  flux_floor_rel: {report.flux_floor_rel:g} "
            f"floored_bins={report.floored_bin_count}"
        )
    if report.freeze_groups is not None:
        rendered = ",".join(str(group) for group in report.freeze_groups)
        print(
            f"  freeze_groups: {rendered} "
            f"frozen_group_bins={report.frozen_group_bin_count}"
        )
    if report.flux_normalization != "none":
        print(
            "  flux_normalization: "
            f"{report.flux_normalization} factor={report.normalization_factor:g} "
            f"weights={report.normalization_weight_source}"
        )
    print(
        "  update range: "
        f"{report.raw_update_minimum:g}..{report.raw_update_maximum:g} "
        f"SPH range: {report.sph_minimum:g}..{report.sph_maximum:g}"
    )
    if report.worst_residual_bins:
        worst = report.worst_residual_bins[0]
        print(
            "  worst update bin: "
            f"{worst.mixture} g{worst.group} raw={worst.raw_update:g} "
            f"residual={worst.residual:g}"
        )
    print()
    print("SPH update table decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: SphUpdateTableReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "input": str(report.input_h5),
        "output_table": str(report.output_table),
        "reference_flux": str(report.reference_flux_source),
        "reference_flux_dataset": report.reference_flux_dataset,
        "low_order_flux": str(report.low_order_flux_source),
        "low_order_flux_dataset": report.low_order_flux_dataset,
        "reference_flux_std_dev_dataset": report.reference_flux_std_dev_dataset,
        "reference_flux_max_relative_std_dev": report.reference_flux_max_relative_std_dev,
        "low_order_flux_std_dev_dataset": report.low_order_flux_std_dev_dataset,
        "low_order_flux_max_relative_std_dev": report.low_order_flux_max_relative_std_dev,
        "previous_sph": None
        if report.previous_sph_source is None
        else str(report.previous_sph_source),
        "previous_sph_dataset": report.previous_sph_dataset,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "energy_groups": report.energy_groups,
        "damping": report.damping,
        "clip_min": report.clip_min,
        "clip_max": report.clip_max,
        "flux_normalization": report.flux_normalization,
        "normalization_factor": report.normalization_factor,
        "reference_normalization_integral": report.reference_normalization_integral,
        "low_order_normalization_integral": report.low_order_normalization_integral,
        "normalization_weight_source": report.normalization_weight_source,
        "reference_flux_minimum": report.reference_flux_minimum,
        "reference_flux_maximum": report.reference_flux_maximum,
        "low_order_flux_minimum": report.low_order_flux_minimum,
        "low_order_flux_maximum": report.low_order_flux_maximum,
        "normalized_low_order_flux_minimum": report.normalized_low_order_flux_minimum,
        "normalized_low_order_flux_maximum": report.normalized_low_order_flux_maximum,
        "raw_update_minimum": report.raw_update_minimum,
        "raw_update_maximum": report.raw_update_maximum,
        "previous_sph_minimum": report.previous_sph_minimum,
        "previous_sph_maximum": report.previous_sph_maximum,
        "sph_minimum": report.sph_minimum,
        "sph_maximum": report.sph_maximum,
        "clipped_count": report.clipped_count,
        "zero_flux_policy": report.zero_flux_policy,
        "identity_bin_count": report.identity_bin_count,
        "flux_floor_rel": report.flux_floor_rel,
        "floored_bin_count": report.floored_bin_count,
        "freeze_groups": None if report.freeze_groups is None else list(report.freeze_groups),
        "frozen_group_bin_count": report.frozen_group_bin_count,
        "diagnostic_bin_limit": DIAGNOSTIC_BIN_LIMIT,
        "worst_residual_bins": [
            _bin_diagnostic_payload(item) for item in report.worst_residual_bins
        ],
        "clipped_bins": [
            _bin_diagnostic_payload(item) for item in report.clipped_bins
        ],
        "source_label": report.source_label,
        "formula": (
            "next_sph = previous_sph * "
            "(reference_flux / normalized_low_order_flux) ** damping"
        ),
    }
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _top_residual_bins(
    *,
    mixture_names: tuple[str, ...],
    reference_flux: np.ndarray,
    low_order_flux: np.ndarray,
    raw_update: np.ndarray,
    previous_sph: np.ndarray,
    unclipped_sph: np.ndarray,
    sph: np.ndarray,
    clipped_mask: np.ndarray,
    limit: int = DIAGNOSTIC_BIN_LIMIT,
) -> tuple[SphUpdateBinDiagnostic, ...]:
    residual = np.abs(raw_update - 1.0)
    flat_order = np.argsort(residual.ravel(), kind="stable")[::-1]
    diagnostics: list[SphUpdateBinDiagnostic] = []
    for flat_index in flat_order[:limit]:
        mixture_index, group_index = np.unravel_index(int(flat_index), raw_update.shape)
        diagnostics.append(
            _build_bin_diagnostic(
                mixture_index,
                group_index,
                mixture_names=mixture_names,
                reference_flux=reference_flux,
                low_order_flux=low_order_flux,
                raw_update=raw_update,
                previous_sph=previous_sph,
                unclipped_sph=unclipped_sph,
                sph=sph,
                clipped_mask=clipped_mask,
            )
        )
    return tuple(diagnostics)


def _top_clipped_bins(
    *,
    mixture_names: tuple[str, ...],
    reference_flux: np.ndarray,
    low_order_flux: np.ndarray,
    raw_update: np.ndarray,
    previous_sph: np.ndarray,
    unclipped_sph: np.ndarray,
    sph: np.ndarray,
    clipped_mask: np.ndarray,
    limit: int = DIAGNOSTIC_BIN_LIMIT,
) -> tuple[SphUpdateBinDiagnostic, ...]:
    clipped_indices = np.argwhere(clipped_mask)
    if clipped_indices.size == 0:
        return ()
    clipped_delta = np.abs(unclipped_sph[clipped_mask] - sph[clipped_mask])
    order = np.argsort(clipped_delta, kind="stable")[::-1]
    diagnostics: list[SphUpdateBinDiagnostic] = []
    for clipped_position in order[:limit]:
        mixture_index, group_index = clipped_indices[int(clipped_position)]
        diagnostics.append(
            _build_bin_diagnostic(
                int(mixture_index),
                int(group_index),
                mixture_names=mixture_names,
                reference_flux=reference_flux,
                low_order_flux=low_order_flux,
                raw_update=raw_update,
                previous_sph=previous_sph,
                unclipped_sph=unclipped_sph,
                sph=sph,
                clipped_mask=clipped_mask,
            )
        )
    return tuple(diagnostics)


def _build_bin_diagnostic(
    mixture_index: int,
    group_index: int,
    *,
    mixture_names: tuple[str, ...],
    reference_flux: np.ndarray,
    low_order_flux: np.ndarray,
    raw_update: np.ndarray,
    previous_sph: np.ndarray,
    unclipped_sph: np.ndarray,
    sph: np.ndarray,
    clipped_mask: np.ndarray,
) -> SphUpdateBinDiagnostic:
    raw = float(raw_update[mixture_index, group_index])
    signed_residual = raw - 1.0
    return SphUpdateBinDiagnostic(
        mixture=mixture_names[mixture_index],
        group=int(group_index) + 1,
        reference_flux=float(reference_flux[mixture_index, group_index]),
        low_order_flux=float(low_order_flux[mixture_index, group_index]),
        raw_update=raw,
        signed_residual=signed_residual,
        residual=abs(signed_residual),
        previous_sph=float(previous_sph[mixture_index, group_index]),
        unclipped_sph=float(unclipped_sph[mixture_index, group_index]),
        sph=float(sph[mixture_index, group_index]),
        clipped=bool(clipped_mask[mixture_index, group_index]),
    )


def _bin_diagnostic_payload(item: SphUpdateBinDiagnostic) -> dict[str, bool | float | int | str]:
    return {
        "mixture": item.mixture,
        "group": item.group,
        "reference_flux": item.reference_flux,
        "low_order_flux": item.low_order_flux,
        "raw_update": item.raw_update,
        "signed_residual": item.signed_residual,
        "residual": item.residual,
        "previous_sph": item.previous_sph,
        "unclipped_sph": item.unclipped_sph,
        "sph": item.sph,
        "clipped": item.clipped,
    }


def _normalize_flux_normalization(value: str) -> str:
    normalized = str(value).strip().lower().replace("_", "-")
    aliases = {
        "automatic": "auto",
        "off": "none",
        "false": "none",
        "no": "none",
        "unity": "none",
        "global": "total",
        "total-flux": "total",
        "sum": "total",
        "kappa-fission": "power",
        "h-factor": "power",
        "hfactor": "power",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in FLUX_NORMALIZATIONS:
        allowed = ", ".join(FLUX_NORMALIZATIONS)
        raise ValueError(f"--flux-normalization must be one of: {allowed}")
    return normalized


def _normalized_low_order_flux(
    input_h5: Path,
    *,
    reference_flux: np.ndarray,
    low_order_flux: np.ndarray,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    flux_normalization: str,
    zero_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, float | str | None]]:
    if flux_normalization == "none":
        return low_order_flux, {
            "flux_normalization": "none",
            "factor": 1.0,
            "reference_integral": None,
            "low_order_integral": None,
            "weight_source": None,
        }
    if flux_normalization == "total":
        weights = np.ones_like(reference_flux, dtype=float)
        weight_source = "unit"
    elif flux_normalization == "power":
        weights = _read_h_factor_matrix(
            input_h5,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
        )
        weight_source = "H-FACTOR/kappa_fission"
    elif flux_normalization == "auto":
        try:
            weights = _read_h_factor_matrix(
                input_h5,
                mixture_names=mixture_names,
                energy_groups=energy_groups,
            )
        except ValueError as exc:
            raise ValueError(
                "auto flux normalization requires group-wise "
                "H-FACTOR/kappa_fission for power normalization; pass "
                "--flux-normalization total or --flux-normalization none only "
                "if you intentionally want to bypass power normalization"
            ) from exc
        flux_normalization = "power"
        weight_source = "H-FACTOR/kappa_fission (auto)"
    else:
        raise AssertionError(f"unhandled flux normalization: {flux_normalization}")

    _validate_normalization_weights(weights, flux_normalization)
    reference_integral = float(np.sum(reference_flux * weights))
    low_order_integral = float(np.sum(low_order_flux * weights))
    if not np.isfinite(reference_integral) or reference_integral <= 0.0:
        raise ValueError(
            f"{flux_normalization} normalization reference integral must be positive"
        )
    if not np.isfinite(low_order_integral) or low_order_integral <= 0.0:
        raise ValueError(
            f"{flux_normalization} normalization low-order integral must be positive"
        )
    factor = reference_integral / low_order_integral
    # Zero bins contribute zero to both normalization integrals and stay zero
    # after scaling, so the frozen-bin mask remains valid for the ratio.
    normalized = low_order_flux * factor
    _validate_flux(normalized, "normalized low-order flux", zero_mask=zero_mask)
    return normalized, {
        "flux_normalization": flux_normalization,
        "factor": float(factor),
        "reference_integral": reference_integral,
        "low_order_integral": low_order_integral,
        "weight_source": weight_source,
    }


def _read_h_factor_matrix(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> np.ndarray:
    import h5py

    values = np.zeros((len(mixture_names), energy_groups), dtype=float)
    missing: list[str] = []
    with h5py.File(path, "r") as h5:
        for mixture_index, mixture in enumerate(mixture_names):
            group = h5.get(f"mixtures/{mixture}")
            if group is None:
                raise ValueError(f"input HDF5 is missing mixture {mixture!r}")
            dataset_name = next((name for name in H_FACTOR_DATASETS if name in group), None)
            if dataset_name is None:
                if bool(group.attrs.get("fissionable", False)):
                    missing.append(mixture)
                continue
            data = np.asarray(group[dataset_name][:], dtype=float).reshape(-1)
            if data.size != energy_groups:
                raise ValueError(
                    f"mixture {mixture}: {dataset_name} must have "
                    f"{energy_groups} value(s), got {data.size}"
                )
            values[mixture_index, :] = data
    if missing:
        raise ValueError(
            "power flux normalization requires group-wise H-FACTOR/kappa_fission "
            "for every fissionable mixture; missing: "
            + ", ".join(missing)
        )
    return values


def _validate_normalization_weights(values: np.ndarray, flux_normalization: str) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{flux_normalization} normalization weights must be finite")
    if np.any(values < 0.0):
        raise ValueError(f"{flux_normalization} normalization weights must be non-negative")
    if not np.any(values > 0.0):
        raise ValueError(f"{flux_normalization} normalization weights must include a positive value")


def _read_mgxs_metadata(path: Path) -> tuple[tuple[str, ...], int]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError("input HDF5 is missing /mixtures")
        mixture_names = read_mixture_names(h5)
        if "energy_groups" in h5.attrs:
            energy_groups = int(h5.attrs["energy_groups"])
        elif "energy_bounds" in h5:
            energy_groups = int(np.asarray(h5["energy_bounds"][:]).size - 1)
        else:
            raise ValueError("input HDF5 is missing energy_groups metadata")
    if not mixture_names:
        raise ValueError("input HDF5 has no mixtures")
    if energy_groups <= 0:
        raise ValueError("input HDF5 energy group count must be positive")
    return mixture_names, energy_groups


def _load_matrix_source(
    source: str | Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    value_columns: tuple[str, ...],
    label: str,
) -> LoadedMatrix:
    path, dataset = _split_dataset_reference(source)
    if not path.exists():
        raise FileNotFoundError(f"{label} source does not exist: {path}")
    if _looks_like_hdf5(path) or dataset is not None:
        values, dataset_path, std_dev, std_dev_dataset_path = _load_hdf5_matrix(
            path,
            dataset=dataset,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            label=label,
        )
        return LoadedMatrix(
            values=values,
            path=path,
            dataset_path=dataset_path,
            std_dev=std_dev,
            std_dev_dataset_path=std_dev_dataset_path,
            max_relative_std_dev=_max_relative_std_dev(values, std_dev),
        )
    values = _load_csv_matrix(
        path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=value_columns,
        label=label,
    )
    return LoadedMatrix(values=values, path=path, dataset_path=None)


def _load_previous_sph(
    source: str | Path | None,
    *,
    input_h5: Path,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> LoadedMatrix:
    if source is None:
        return LoadedMatrix(
            values=np.ones((len(mixture_names), energy_groups), dtype=float),
            path=Path("unity"),
            dataset_path=None,
        )
    path, dataset = _split_dataset_reference(source)
    if not path.exists():
        raise FileNotFoundError(f"previous SPH source does not exist: {path}")
    if _looks_like_hdf5(path) or dataset is not None:
        if dataset is None:
            loaded = load_sph_source(
                path,
                mixture_names=mixture_names,
                energy_groups=energy_groups,
            )
            values = np.stack([loaded.sph[name] for name in mixture_names])
            return LoadedMatrix(values=values, path=path, dataset_path="sph")
        values, dataset_path, _std_dev, _std_dev_dataset_path = _load_hdf5_matrix(
            path,
            dataset=dataset,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            label="previous SPH",
        )
        return LoadedMatrix(values=values, path=path, dataset_path=dataset_path)
    values = _load_csv_matrix(
        path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        value_columns=("sph", "nsph", "value"),
        label="previous SPH",
    )
    return LoadedMatrix(values=values, path=path, dataset_path=None)


def _load_hdf5_matrix(
    path: Path,
    *,
    dataset: str | None,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    label: str,
) -> tuple[np.ndarray, str, np.ndarray | None, str | None]:
    import h5py

    with h5py.File(path, "r") as h5:
        dataset_path = dataset
        if dataset_path is None:
            for candidate in FLUX_DATASETS:
                if candidate in h5 and not hasattr(h5[candidate], "keys"):
                    dataset_path = candidate
                    break
        if dataset_path is None:
            rendered = ", ".join(f"/{name}" for name in FLUX_DATASETS)
            raise ValueError(f"{label} HDF5 must contain one of: {rendered}")
        if dataset_path not in h5:
            raise ValueError(f"{label} dataset not found: /{dataset_path}")
        obj = h5[dataset_path]
        if hasattr(obj, "keys"):
            raise ValueError(f"{label} path is a group, not a dataset: /{dataset_path}")
        _validate_hdf5_flux_group_order(obj, h5, label)
        values = np.asarray(obj[:], dtype=float)
        declared = _names_from_hdf5(obj, h5, ("mixture_names", "mixtures", "domain_names"))
        _validate_hdf5_flux_mixture_names(declared, label)
        normalized = _normalize_matrix(
            values,
            declared,
            mixture_names,
            energy_groups,
            label,
        )
        std_dev_dataset_path = _find_std_dev_dataset_path(h5, dataset_path)
        if std_dev_dataset_path is None:
            std_dev = None
        else:
            std_obj = h5[std_dev_dataset_path]
            if hasattr(std_obj, "keys"):
                raise ValueError(
                    f"{label} std_dev path is a group, not a dataset: "
                    f"/{std_dev_dataset_path}"
                )
            _validate_hdf5_flux_group_order(std_obj, h5, f"{label} std_dev")
            std_declared = _names_from_hdf5(
                std_obj,
                h5,
                ("mixture_names", "mixtures", "domain_names"),
            )
            if std_declared is None:
                std_declared = declared
            _validate_hdf5_flux_mixture_names(std_declared, f"{label} std_dev")
            std_values = np.asarray(std_obj[:], dtype=float)
            std_dev = _normalize_matrix(
                std_values,
                std_declared,
                mixture_names,
                energy_groups,
                f"{label} std_dev",
            )
            _validate_std_dev(std_dev, f"{label} std_dev")
    return normalized, dataset_path, std_dev, std_dev_dataset_path


def _find_std_dev_dataset_path(root: Any, dataset_path: str) -> str | None:
    candidates = (
        f"{dataset_path}_std_dev",
        f"{dataset_path}_stddev",
        f"{dataset_path}_sigma",
        f"{Path(dataset_path).name}_std_dev",
    )
    for candidate in candidates:
        if candidate in root:
            return candidate
    target = dataset_path.strip("/")
    for name, obj in root.items():
        if hasattr(obj, "keys") or not name.endswith(("_std_dev", "_stddev", "_sigma")):
            continue
        raw = obj.attrs.get("std_dev_of")
        if raw is None:
            continue
        if isinstance(raw, bytes):
            raw_text = raw.decode("utf-8")
        else:
            raw_text = str(raw)
        if raw_text.strip("/") == target:
            return str(name)
    return None


def _validate_hdf5_flux_group_order(obj: Any, root: Any, label: str) -> None:
    if "flux" not in label.lower():
        return
    group_order = _hdf5_text_attr(obj, root, "group_order")
    if group_order is None:
        raise ValueError(
            f"{label}: group_order must be {MGXS_DONJON_GROUP_ORDER!r}; "
            "HDF5 flux sources must declare their energy-group order"
        )
    if group_order != MGXS_DONJON_GROUP_ORDER:
        raise ValueError(
            f"{label}: group_order must be {MGXS_DONJON_GROUP_ORDER!r}, "
            f"got {group_order!r}"
        )


def _validate_hdf5_flux_mixture_names(declared_mixtures: Any, label: str) -> None:
    if "flux" not in label.lower():
        return
    if declared_mixtures is None or not _flatten_names(declared_mixtures):
        raise ValueError(
            f"{label}: HDF5 flux sources must declare mixture_names, "
            "mixtures, or domain_names"
        )


def _load_csv_matrix(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    value_columns: tuple[str, ...],
    label: str,
) -> np.ndarray:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{label} CSV must have a header row")
        fieldnames = [str(name).strip() for name in reader.fieldnames]
        rows = [
            {str(key).strip(): value for key, value in row.items()}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    if not rows:
        raise ValueError(f"{label} CSV contains no data rows")

    mixture_column = _find_column(fieldnames, ("mixture", "mixture_name", "name"))
    if mixture_column is None:
        raise ValueError(f"{label} CSV must define a mixture, mixture_name, or name column")
    group_column = _find_column(fieldnames, ("group", "energy_group", "g"))
    value_column = _find_column(fieldnames, value_columns)
    if group_column is not None and value_column is not None:
        return _load_long_csv(
            rows,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            mixture_column=mixture_column,
            group_column=group_column,
            value_column=value_column,
            label=label,
        )

    group_columns = _group_columns(fieldnames, mixture_column)
    group_indices = [index for index, _column in group_columns]
    if len(set(group_indices)) != len(group_indices):
        raise ValueError(f"{label} wide CSV contains duplicate group columns")
    if group_indices and group_indices != list(range(energy_groups)):
        raise ValueError(
            f"{label} wide CSV must define contiguous group columns 1..{energy_groups}"
        )
    if len(group_columns) == energy_groups:
        return _load_wide_csv(
            rows,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            mixture_column=mixture_column,
            group_columns=group_columns,
            label=label,
        )
    raise ValueError(
        f"{label} CSV must be long form (mixture,group,value) or wide form "
        f"(mixture plus {energy_groups} group columns)"
    )


def _load_long_csv(
    rows: list[dict[str, str]],
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    mixture_column: str,
    group_column: str,
    value_column: str,
    label: str,
) -> np.ndarray:
    values = {name: np.full(energy_groups, np.nan, dtype=float) for name in mixture_names}
    seen: set[tuple[str, int]] = set()
    valid = set(mixture_names)
    for row_index, row in enumerate(rows, start=2):
        mixture = str(row.get(mixture_column, "")).strip()
        if mixture not in valid:
            raise ValueError(f"{label} row {row_index}: unknown mixture {mixture!r}")
        group = _parse_group_index(str(row.get(group_column, "")).strip(), energy_groups, row_index, label)
        key = (mixture, group)
        if key in seen:
            raise ValueError(f"{label} row {row_index}: duplicate {mixture} group {group + 1}")
        seen.add(key)
        values[mixture][group] = _parse_float(row.get(value_column, ""), row_index, value_column, label)
    _require_complete(values, label)
    return np.stack([values[name] for name in mixture_names])


def _load_wide_csv(
    rows: list[dict[str, str]],
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    mixture_column: str,
    group_columns: list[tuple[int, str]],
    label: str,
) -> np.ndarray:
    values: dict[str, np.ndarray] = {}
    valid = set(mixture_names)
    for row_index, row in enumerate(rows, start=2):
        mixture = str(row.get(mixture_column, "")).strip()
        if mixture not in valid:
            raise ValueError(f"{label} row {row_index}: unknown mixture {mixture!r}")
        if mixture in values:
            raise ValueError(f"{label} row {row_index}: duplicate mixture {mixture!r}")
        vector = np.empty(energy_groups, dtype=float)
        for group_index, column in group_columns:
            vector[group_index] = _parse_float(row.get(column, ""), row_index, column, label)
        values[mixture] = vector
    missing = [name for name in mixture_names if name not in values]
    if missing:
        raise ValueError(f"{label} CSV is missing mixture(s): {', '.join(missing)}")
    return np.stack([values[name] for name in mixture_names])


def _write_sph_table(
    path: Path,
    *,
    mixture_names: tuple[str, ...],
    values: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mixture", "group", "sph"))
        for mixture_index, mixture in enumerate(mixture_names):
            for group_index, value in enumerate(values[mixture_index], start=1):
                writer.writerow((mixture, group_index, f"{float(value):.12g}"))


def _normalize_matrix(
    values: np.ndarray,
    declared_mixtures: Any,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    label: str,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    expected_shape = (len(mixture_names), energy_groups)
    if values.shape == expected_shape:
        if declared_mixtures is None:
            return values
        declared = tuple(_flatten_names(declared_mixtures))
        if not declared:
            return values
        if set(declared) != set(mixture_names):
            raise ValueError(
                f"{label}: declared mixture names {declared!r} do not match "
                f"{mixture_names!r}"
            )
        order = [declared.index(name) for name in mixture_names]
        return values[order, :]

    if values.ndim >= 3 and values.shape[-1] == energy_groups:
        return _mesh_values_to_mixture_order(
            values,
            declared_mixtures,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            label=label,
        )

    raise ValueError(
        f"{label}: shape {values.shape} is not compatible with "
        f"({len(mixture_names)}, {energy_groups}) or mesh-shaped "
        f"(..., {energy_groups})"
    )


def _mesh_values_to_mixture_order(
    values: np.ndarray,
    declared_mixtures: Any,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    label: str,
) -> np.ndarray:
    if declared_mixtures is None:
        raise ValueError(
            f"{label}: mesh-shaped HDF5 datasets must declare mixture_names, "
            "mixtures, or domain_names"
        )
    declared = _decode_name_array(declared_mixtures)
    spatial_shape = values.shape[:-1]
    if declared.shape != spatial_shape:
        if declared.size != int(np.prod(spatial_shape)):
            raise ValueError(
                f"{label}: declared mixture name shape {declared.shape} does not "
                f"match mesh shape {spatial_shape}"
            )
        declared = declared.reshape(spatial_shape)

    flat_names = declared.reshape(-1)
    flat_values = values.reshape((-1, energy_groups))
    ordered = np.empty((len(mixture_names), energy_groups), dtype=float)
    for mixture_index, mixture in enumerate(mixture_names):
        matches = np.flatnonzero(flat_names == mixture)
        if matches.size == 0:
            raise ValueError(f"{label}: mesh is missing mixture {mixture!r}")
        if matches.size > 1:
            raise ValueError(
                f"{label}: mesh contains mixture {mixture!r} more than once; "
                "SPH update tables require one flux vector per mixture"
            )
        ordered[mixture_index, :] = flat_values[int(matches[0]), :]
    return ordered


def _validate_update_options(
    *,
    damping: float,
    clip_min: float | None,
    clip_max: float | None,
    flux_floor_rel: float | None = None,
) -> None:
    if not np.isfinite(damping) or damping < 0.0 or damping > 1.0:
        raise ValueError("--damping must be finite and within 0..1")
    if flux_floor_rel is not None and (
        not np.isfinite(flux_floor_rel)
        or flux_floor_rel <= 0.0
        or flux_floor_rel >= 1.0
    ):
        raise ValueError("--flux-floor-rel must be strictly between 0 and 1")
    if clip_min is not None and (not np.isfinite(clip_min) or clip_min <= 0.0):
        raise ValueError("--clip-min must be positive and finite")
    if clip_max is not None and (not np.isfinite(clip_max) or clip_max <= 0.0):
        raise ValueError("--clip-max must be positive and finite")
    if clip_min is not None and clip_max is not None and clip_min > clip_max:
        raise ValueError("--clip-min must be less than or equal to --clip-max")


def _validate_flux(
    values: np.ndarray,
    label: str,
    *,
    zero_mask: np.ndarray | None = None,
) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} values must be finite")
    allowed = values > 0.0
    if zero_mask is not None:
        allowed |= zero_mask & (values == 0.0)
    if not np.all(allowed):
        raise ValueError(f"{label} values must be positive")


def _floored_flux_mask(
    reference_flux: np.ndarray,
    *,
    flux_floor_rel: float | None,
) -> np.ndarray | None:
    if flux_floor_rel is None:
        return None
    floors = float(flux_floor_rel) * np.max(reference_flux, axis=1, keepdims=True)
    return reference_flux < floors


def _normalize_freeze_groups(
    freeze_groups: tuple[int, ...] | None,
    *,
    energy_groups: int,
) -> tuple[int, ...] | None:
    if freeze_groups is None:
        return None
    groups = tuple(int(group) for group in freeze_groups)
    if not groups:
        return None
    for group in groups:
        if group < 1 or group > energy_groups:
            raise ValueError(f"--freeze-groups group {group} outside 1..{energy_groups}")
    if len(set(groups)) != len(groups):
        raise ValueError("--freeze-groups must not contain duplicate groups")
    return groups


def _freeze_groups_mask(
    freeze_groups: tuple[int, ...] | None,
    *,
    mixture_count: int,
    energy_groups: int,
) -> np.ndarray | None:
    if freeze_groups is None:
        return None
    mask = np.zeros((mixture_count, energy_groups), dtype=bool)
    mask[:, [group - 1 for group in freeze_groups]] = True
    return mask


def _union_masks(*masks: np.ndarray | None) -> np.ndarray | None:
    combined: np.ndarray | None = None
    for mask in masks:
        if mask is None:
            continue
        combined = mask if combined is None else combined | mask
    return combined


def _masked_count(mask: np.ndarray | None, *, exclude: np.ndarray | None) -> int:
    if mask is None:
        return 0
    if exclude is not None:
        mask = mask & ~exclude
    return int(np.count_nonzero(mask))


def _identity_zero_flux_mask(
    reference_flux: np.ndarray,
    low_order_flux: np.ndarray,
    *,
    mixture_names: tuple[str, ...],
    zero_flux_policy: str,
    exempt_mask: np.ndarray | None = None,
) -> np.ndarray | None:
    if zero_flux_policy != "identity":
        return None
    reference_zero = reference_flux == 0.0
    low_order_zero = low_order_flux == 0.0
    one_sided = reference_zero ^ low_order_zero
    if exempt_mask is not None:
        # Below-floor and explicitly frozen bins are passed through anyway; a
        # one-sided zero there is noise, not a CE/MG inconsistency.
        one_sided &= ~exempt_mask
    if np.any(one_sided):
        rendered: list[str] = []
        for mixture_index, group_index in np.argwhere(one_sided)[:DIAGNOSTIC_BIN_LIMIT]:
            side = (
                "reference flux"
                if reference_zero[mixture_index, group_index]
                else "low-order flux"
            )
            rendered.append(
                f"{mixture_names[int(mixture_index)]} g{int(group_index) + 1} "
                f"(zero {side})"
            )
        raise ValueError(
            "zero-flux policy 'identity' requires zero bins to match in the "
            "reference and low-order fluxes; one-sided zero flux indicates a "
            "CE/MG inconsistency: " + "; ".join(rendered)
        )
    return reference_zero & low_order_zero


def _validate_std_dev(values: np.ndarray, label: str) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} values must be finite")
    if np.any(values < 0.0):
        raise ValueError(f"{label} values must be non-negative")


def _max_relative_std_dev(
    values: np.ndarray,
    std_dev: np.ndarray | None,
    *,
    exclude_mask: np.ndarray | None = None,
) -> float | None:
    if std_dev is None:
        return None
    # Zero-mean bins (identity zero-flux policy) carry zero Monte Carlo
    # std_dev; exclude them so the relative gate stays finite.  Frozen bins
    # (exclude_mask) are passed through the update and bypass the gate.
    include = values != 0.0
    if exclude_mask is not None:
        include &= ~exclude_mask
    rel = np.zeros_like(std_dev, dtype=float)
    np.divide(std_dev, np.abs(values), out=rel, where=include)
    return float(np.max(rel))


def _validate_flux_std_dev_gate(
    matrix: LoadedMatrix,
    label: str,
    *,
    required: bool,
    max_relative: float | None,
) -> None:
    if max_relative is not None and (not np.isfinite(max_relative) or max_relative < 0.0):
        raise ValueError(f"{label} std_dev threshold must be finite and non-negative")
    if matrix.std_dev is None:
        if required:
            raise ValueError(f"{label} HDF5 source is missing a matching std_dev dataset")
        return
    max_rel = matrix.max_relative_std_dev
    if max_relative is not None and max_rel is not None and max_rel > max_relative:
        raise ValueError(
            f"{label} max relative std_dev {max_rel:.6g} exceeds "
            f"threshold {max_relative:.6g}"
        )


def _validate_sph(values: np.ndarray, label: str) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} values must be finite")
    if np.any(values <= 0.0):
        raise ValueError(f"{label} values must be positive")


def _split_dataset_reference(reference: str | Path) -> tuple[Path, str | None]:
    raw = str(reference)
    if "::" not in raw:
        return Path(raw), None
    path, dataset = raw.split("::", 1)
    dataset = dataset.strip("/")
    if not dataset:
        raise ValueError(f"empty dataset reference in {raw!r}")
    return Path(path), dataset


def _looks_like_hdf5(path: Path) -> bool:
    return path.suffix.lower() in {".h5", ".hdf5", ".hdf"}


def _names_from_hdf5(obj: Any, root: Any, candidates: tuple[str, ...]) -> Any:
    for candidate in candidates:
        if candidate in obj.attrs:
            return obj.attrs[candidate]
    for candidate in candidates:
        if candidate in root.attrs:
            return root.attrs[candidate]
    for candidate in candidates:
        if candidate in root and not hasattr(root[candidate], "keys"):
            return root[candidate][:]
    return None


def _hdf5_text_attr(obj: Any, root: Any, name: str) -> str | None:
    for source in (obj.attrs, root.attrs):
        if name in source:
            value = source[name]
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value)
    return None


def _flatten_names(raw: Any) -> tuple[str, ...]:
    arr = np.asarray(raw)
    out: list[str] = []
    for item in arr.reshape(-1):
        if isinstance(item, bytes):
            out.append(item.decode("utf-8"))
        else:
            out.append(str(item))
    return tuple(out)


def _decode_name_array(raw: Any) -> np.ndarray:
    arr = np.asarray(raw)
    out = np.empty(arr.shape, dtype=object)
    for index, item in np.ndenumerate(arr):
        if isinstance(item, bytes):
            out[index] = item.decode("utf-8")
        else:
            out[index] = str(item)
    return out


def _find_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {_normalize_column(name): name for name in fieldnames}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _group_columns(fieldnames: list[str], mixture_column: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for name in fieldnames:
        if name == mixture_column:
            continue
        match = re.fullmatch(r"(?:sph|nsph|flux|phi|group|g)?_?(\d+)", _normalize_column(name))
        if match is None:
            continue
        out.append((int(match.group(1)) - 1, name))
    out.sort(key=lambda item: item[0])
    return out


def _normalize_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _parse_group_index(raw: str, energy_groups: int, row_index: int, label: str) -> int:
    try:
        group = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label} row {row_index}: group must be an integer") from exc
    if group < 1 or group > energy_groups:
        raise ValueError(f"{label} row {row_index}: group {group} outside 1..{energy_groups}")
    return group - 1


def _parse_float(raw: Any, row_index: int, column: str, label: str) -> float:
    text = str(raw or "").strip()
    if not text:
        raise ValueError(f"{label} row {row_index}: missing value in {column}")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"{label} row {row_index}: {column} must be a floating-point value"
        ) from exc


def _require_complete(values: dict[str, np.ndarray], label: str) -> None:
    missing: list[str] = []
    for mixture, vector in values.items():
        missing_groups = np.flatnonzero(~np.isfinite(vector)) + 1
        if missing_groups.size:
            rendered = ",".join(str(int(group)) for group in missing_groups[:8])
            if missing_groups.size > 8:
                rendered += ",..."
            missing.append(f"{mixture}: groups {rendered}")
    if missing:
        raise ValueError(f"{label} CSV is incomplete: " + "; ".join(missing))

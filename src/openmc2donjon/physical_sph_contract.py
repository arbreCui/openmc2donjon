"""Strict physical provenance gates for production SPH handoffs.

The base contract is geometry-agnostic: one assembly, an assembly containing
many homogenization domains, an arbitrary colorset, and a full-core coarse
mesh are all valid shapes.  Benchmark/template topology belongs in a thin
specialization, never in the physical SPH contract itself.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .hdf5_names import read_mixture_names


PHYSICAL_SPH_MAX_UPDATE_RESIDUAL = 0.02
EXPECTED_COLORSET_DOMAINS = 7


def physical_sph_issues(
    path: str | Path,
    *,
    max_update_residual: float = PHYSICAL_SPH_MAX_UPDATE_RESIDUAL,
) -> list[str]:
    """Return every reason an applied SPH handoff is not production-ready.

    This contract deliberately rejects empirical/global calibration provenance.
    The accepted route is a matched OpenMC CE/MG, rate-preserving fixed point
    that has already been applied to the declared homogenized domains.  It
    intentionally imposes no component count, domain count, lattice, or core
    topology.
    """

    import h5py

    issues: list[str] = []
    with h5py.File(Path(path), "r") as h5:
        try:
            mixture_names = read_mixture_names(h5)
        except ValueError as exc:
            issues.append(str(exc))
            mixture_names = ()

        if "mixture_names" not in h5:
            issues.append("/mixture_names must declare the SPH domain order")
        if not mixture_names:
            issues.append("physical SPH requires at least one declared domain")
        filled_bins = sum(
            _attribute_item_count(
                h5["mixtures"][name].attrs.get("zero_flux_filled_groups")
            )
            for name in mixture_names
            if "mixtures" in h5 and name in h5["mixtures"]
        )

        applied = bool(h5.attrs.get("sph_applied", False))
        source = _text_attr(h5.attrs.get("sph_applied_source"))
        operator = _text_attr(h5.attrs.get("sph_apply_operator"))
        kind = _text_attr(h5.attrs.get("sph_kind")).lower()
        derivation = _text_attr(h5.attrs.get("sph_derivation"))
        target = _text_attr(h5.attrs.get("sph_target"))
        normalization = _text_attr(h5.attrs.get("sph_flux_normalization"))
        zero_flux_policy = _text_attr(h5.attrs.get("sph_zero_flux_policy"))
        identity_bin_count = _integer_attr(h5.attrs.get("sph_identity_bin_count"))
        floored_bin_count = _integer_attr(h5.attrs.get("sph_floored_bin_count"))
        frozen_bin_count = _integer_attr(h5.attrs.get("sph_frozen_group_bin_count"))
        clipped_count = _integer_attr(h5.attrs.get("sph_clipped_count"))
        is_real = bool(h5.attrs.get("sph_real", False))
        residual = h5.attrs.get("sph_max_update_residual")

    if not applied:
        issues.append("sph_applied=true is required; run apply-sph before Converter")
    if not source:
        issues.append("sph_applied_source must record the physical SPH sidecar")
    if operator != "divide-xs-by-nsph":
        issues.append("sph_apply_operator must be divide-xs-by-nsph")
    if not is_real or not kind.startswith("openmc-ce-mg"):
        issues.append("SPH must be derived from a real matched OpenMC CE/MG calculation")
    if any(token in kind for token in ("global", "optical", "calibrat", "empirical")):
        issues.append("empirical, global, optical, or calibrated SPH provenance is forbidden")
    if derivation != "rate-preserving-ce-mg-fixed-point" or target != "rate":
        issues.append("SPH must use the rate-preserving CE/MG fixed-point derivation")
    if normalization != "power":
        issues.append("SPH must use H-FACTOR/kappa-fission power normalization")
    if zero_flux_policy != "reject":
        issues.append("SPH zero-flux policy must be reject; identity is forbidden")
    if identity_bin_count != 0:
        issues.append("SPH provenance must report zero identity-substituted bins")
    if floored_bin_count != 0:
        issues.append("SPH provenance must report zero flux-floored bins")
    if frozen_bin_count != 0:
        issues.append("SPH provenance must report zero frozen-group bins")
    if clipped_count != 0:
        issues.append("SPH provenance must report zero clipped update bins")
    if filled_bins != 0:
        issues.append(
            "physical SPH handoff must contain zero macrolib-filled XS bins; "
            f"found {filled_bins}"
        )
    try:
        numeric_residual = float(residual)
    except (TypeError, ValueError):
        numeric_residual = math.inf
    if not math.isfinite(numeric_residual) or numeric_residual > max_update_residual:
        issues.append(
            "SPH fixed point is not converged: max update residual "
            f"{numeric_residual:.6g} exceeds {max_update_residual:.6g}"
        )
    return issues


def physical_colorset_sph_issues(
    path: str | Path,
    *,
    expected_domains: int = EXPECTED_COLORSET_DOMAINS,
    max_update_residual: float = PHYSICAL_SPH_MAX_UPDATE_RESIDUAL,
) -> list[str]:
    """Add the IRENA-style center-plus-six-neighbors colorset topology gate.

    This is a template contract, not the general definition of physical SPH.
    It remains available for existing IRENA manifests and other projects that
    explicitly choose the same seven-domain topology.
    """

    import h5py

    issues = physical_sph_issues(
        path,
        max_update_residual=max_update_residual,
    )
    with h5py.File(Path(path), "r") as h5:
        try:
            mixture_names = read_mixture_names(h5)
        except ValueError:
            mixture_names = ()
        if len(mixture_names) != expected_domains:
            issues.append(
                f"colorset must contain exactly {expected_domains} domains "
                f"(center target + six neighbors), found {len(mixture_names)}"
            )
        if mixture_names:
            first = h5["mixtures"][mixture_names[0]]
            try:
                first_index = int(first.attrs.get("source_domain_index", 0))
            except (TypeError, ValueError):
                first_index = 0
            if first_index != 1:
                issues.append(
                    "the center target must be the first declared domain "
                    "with source_domain_index=1"
                )
    return issues


def _text_attr(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return "" if value is None else str(value).strip()


def _integer_attr(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _attribute_item_count(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value.size)
    except (AttributeError, TypeError, ValueError):
        pass
    if isinstance(value, (str, bytes)):
        return 1 if value else 0
    try:
        return len(value)
    except TypeError:
        return 1

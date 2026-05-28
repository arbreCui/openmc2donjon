import type { OpenmcSphPhysicsSummary } from "./api";

export function summaryStatus(summary: OpenmcSphPhysicsSummary): {
  label: string;
  tone: "pass" | "warn";
  detail: string;
} {
  const hasNsp = summary.handoff.ascii_nsp_block_count > 0;
  const hasSph = summary.handoff.augmented_hdf5_has_sph;
  if (hasNsp && hasSph) {
    if (summary.quality?.decision === "openmc_ce_mg_sph_statistical_review_required") {
      return {
        label: "statistics need review",
        tone: "warn",
        detail:
          "SPH factors are present, but CE/MG flux uncertainty is above the demonstration threshold. Increase OpenMC particles/batches before treating this as production evidence.",
      };
    }
    if (summary.quality?.decision === "openmc_ce_mg_sph_demonstration_quality") {
      return {
        label: "demo-quality NSPH",
        tone: "warn",
        detail:
          "SPH factors are present and the workflow is structurally complete, but flux uncertainty is above the production threshold.",
      };
    }
    const route =
      summary.handoff.accepted_sph_consumption_format === "macrolib"
        ? "MACROLIB NSPH"
        : "ASCII NSPH";
    return {
      label: "handoff carries NSPH",
      tone: "pass",
      detail: `SPH factors are present in the augmented HDF5 and exported ${route}.`,
    };
  }
  return {
    label: "review handoff",
    tone: "warn",
    detail: "The summary did not confirm both HDF5 SPH datasets and ASCII NSPH blocks.",
  };
}

export function formatPhysicsNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1.0e4 || abs < 1.0e-3) return value.toExponential(3);
  return value.toPrecision(4).replace(/\.?0+$/, "");
}

export function formatScatterTreatment(
  summary: OpenmcSphPhysicsSummary,
): string {
  const handoff = summary.handoff_scatter;
  const mgMacro = summary.mg_macro_scatter;
  const handoffLabel =
    handoff?.format === "legendre" || handoff?.scatter_format === "legendre"
      ? `P${handoff.legendre_order ?? summary.legendre_order} handoff`
      : `P${summary.legendre_order} handoff`;
  const macroFormat = mgMacro?.scatter_format ?? mgMacro?.format;
  const macroLabel =
    macroFormat === "histogram"
      ? `H${mgMacro?.histogram_bins ?? "?"} MG macro`
      : macroFormat === "legendre"
        ? `P${mgMacro?.legendre_order ?? "?"} MG macro`
        : "MG macro";
  return `${handoffLabel} · ${macroLabel}`;
}

export function topSphDeviationRows(
  summary: OpenmcSphPhysicsSummary,
  limit = 3,
) {
  return [...summary.per_mixture]
    .sort((a, b) => b.max_abs_sph_minus_1 - a.max_abs_sph_minus_1)
    .slice(0, limit);
}

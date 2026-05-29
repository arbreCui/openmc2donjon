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

export function reactionRatePreservationRows(summary: OpenmcSphPhysicsSummary): {
  id: "current" | "frozen";
  label: string;
  detail: string;
  maxResidual: number;
  meanResidual: number | null;
  validBins: number | null;
}[] {
  const preservation = summary.reaction_rate_preservation;
  if (!preservation) return [];
  const rows = [
    {
      id: "current" as const,
      label: "Current OpenMC MG solve",
      detail: "Before applying the newly generated SPH factors.",
      source: preservation.current_solve,
    },
    {
      id: "frozen" as const,
      label: "After SPH update, frozen MG flux",
      detail: "Diagnostic using CE MGXS / NSPH with the latest MG flux.",
      source: preservation.after_sph_update_frozen_flux,
    },
  ];
  return rows
    .filter((row) => row.source && Number.isFinite(row.source.max_relative_residual))
    .map((row) => ({
      id: row.id,
      label: row.label,
      detail: row.detail,
      maxResidual: row.source!.max_relative_residual,
      meanResidual:
        row.source!.mean_relative_residual != null
          ? row.source!.mean_relative_residual
          : null,
      validBins: row.source!.valid_bins != null ? row.source!.valid_bins : null,
    }));
}

export function productionEvidenceRows(summary: OpenmcSphPhysicsSummary): {
  id: "flux" | "sph" | "rates" | "handoff" | "donjon" | "donjon-solve";
  label: string;
  value: string;
  detail: string;
}[] {
  const threshold = summary.quality?.production_flux_relative_std_dev_threshold;
  const current = summary.reaction_rate_preservation?.current_solve;
  const frozen = summary.reaction_rate_preservation?.after_sph_update_frozen_flux;
  const acceptedFormat = summary.handoff.accepted_sph_consumption_format ?? "ASCII";
  const nspBlocks =
    summary.handoff.macrolib_ascii_nsp_block_count ??
    summary.handoff.ascii_nsp_block_count;
  const donjon = summary.donjon_consumption;
  const solve = summary.donjon_solve_diagnostic;

  const rows: {
    id: "flux" | "sph" | "rates" | "handoff" | "donjon" | "donjon-solve";
    label: string;
    value: string;
    detail: string;
  }[] = [
    {
      id: "flux",
      label: "OpenMC flux uncertainty",
      value: `${formatPhysicsNumber(summary.flux_uncertainty.ce_max_relative_std_dev)} / ${formatPhysicsNumber(
        summary.flux_uncertainty.mg_max_relative_std_dev,
      )}`,
      detail:
        threshold == null
          ? "CE/MG max relative standard deviations."
          : `CE/MG max relative standard deviations; production target <= ${formatPhysicsNumber(
              threshold,
            )}.`,
    },
    {
      id: "sph",
      label: "SPH correction size",
      value: `${formatPhysicsNumber(summary.sph.minimum)} .. ${formatPhysicsNumber(
        summary.sph.maximum,
      )}`,
      detail: `${summary.sph.clipped_count} clipped bin(s); max |SPH-1| = ${formatPhysicsNumber(
        summary.sph.max_abs_delta_from_unity,
      )}.`,
    },
    {
      id: "rates",
      label: "Reaction-rate preservation",
      value:
        frozen == null
          ? "n/a"
          : formatPhysicsNumber(frozen.max_relative_residual),
      detail:
        current == null
          ? "Frozen-flux diagnostic after the proposed SPH update."
          : `Frozen-flux residual after SPH update; current MG solve was ${formatPhysicsNumber(
              current.max_relative_residual,
            )}.`,
    },
    {
      id: "handoff",
      label: "DONJON handoff",
      value: `${nspBlocks} NSPH block(s)`,
      detail: `Accepted SPH consumption route: ${acceptedFormat.toUpperCase()} GROUP/*/NSPH.`,
    },
  ];
  if (donjon) {
    const status = donjon.status ?? "not run";
    const pn = formatPhysicsNumber(donjon.pn_ntot0_ratio);
    const sn = formatPhysicsNumber(donjon.sn_ntot0_ratio);
    rows.push({
      id: "donjon",
      label: "DONJON consume smoke",
      value: status,
      detail: `DSPH/MAC checked exported NSPH; PN NTOT0 ratio ${pn}, SN NTOT0 ratio ${sn}.`,
    });
  }
  const spn3 = solve?.modes?.spn3;
  if (solve && spn3) {
    const k = formatPhysicsNumber(spn3.k_effective);
    const mean = formatPhysicsNumber(
      spn3.vs_openmc_ce?.flux_shape_mean_relative_residual,
    );
    const max = formatPhysicsNumber(
      spn3.vs_openmc_ce?.flux_shape_max_relative_residual,
    );
    rows.push({
      id: "donjon-solve",
      label: "DONJON solve diagnostic",
      value: `SPN3 k=${k}`,
      detail: `Low-order solve recorded; CE flux-shape residual mean ${mean}, max ${max}.`,
    });
  }
  return rows;
}

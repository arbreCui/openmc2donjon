import type { OpenmcSphPhysicsSummary } from "./api";

export function summaryStatus(summary: OpenmcSphPhysicsSummary): {
  label: string;
  tone: "pass" | "warn";
  detail: string;
} {
  const hasNsp = summary.handoff.ascii_nsp_block_count > 0;
  const hasSph = summary.handoff.augmented_hdf5_has_sph;
  if (hasNsp && hasSph) {
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

export function topSphDeviationRows(
  summary: OpenmcSphPhysicsSummary,
  limit = 3,
) {
  return [...summary.per_mixture]
    .sort((a, b) => b.max_abs_sph_minus_1 - a.max_abs_sph_minus_1)
    .slice(0, limit);
}

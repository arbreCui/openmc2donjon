import { describe, expect, it } from "vitest";
import type { OpenmcSphPhysicsSummary } from "./api";
import {
  formatScatterTreatment,
  formatPhysicsNumber,
  reactionRatePreservationRows,
  summaryStatus,
  topSphDeviationRows,
} from "./openmcSphSummary";

const SUMMARY: OpenmcSphPhysicsSummary = {
  schema: "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
  route: "OpenMC CE reference + OpenMC MG same geometry -> OpenMC-side SPH",
  handoff_dir: "/mock",
  mixture_count: 2,
  energy_groups: 33,
  legendre_order: 3,
  handoff_scatter: {
    format: "legendre",
    legendre_order: 3,
  },
  mg_macro_scatter: {
    scatter_format: "histogram",
    histogram_bins: 16,
    legendre_order: null,
  },
  mixture_names: ["A", "B"],
  decisions: {
    openmc_sph: "openmc2donjon_openmc_sph_sidecar_passed",
    sph_augment: "openmc2donjon_sph_augment_passed",
  },
  normalization: {
    method: "power",
    factor: 1.0,
    formula: "sph = mg / ce",
  },
  flux_uncertainty: {
    ce_max_relative_std_dev: 0.01,
    mg_max_relative_std_dev: 0.02,
    ce_dataset: "openmc_volume_flux",
    mg_dataset: "openmc_mg_flux",
  },
  quality: {
    decision: "openmc_ce_mg_sph_production_quality",
    structural_passed: true,
    production_ready: true,
    demonstration_quality: true,
    max_flux_relative_std_dev: 0.02,
    production_flux_relative_std_dev_threshold: 0.05,
    demonstration_flux_relative_std_dev_threshold: 0.3,
    notes: ["ok"],
  },
  sph: {
    kind: "openmc-ce-mg",
    real: true,
    applied_to_xs: false,
    minimum: 0.8,
    maximum: 1.2,
    mean: 1.0,
    max_abs_delta_from_unity: 0.2,
    clipped_count: 0,
  },
  reaction_rate_preservation: {
    reference: "CE-tallied MGXS * CE volume flux",
    current_solve: {
      max_relative_residual: 0.24,
      mean_relative_residual: 0.03,
      valid_bins: 165,
    },
    after_sph_update_frozen_flux: {
      max_relative_residual: 5.0e-12,
      mean_relative_residual: 1.5e-12,
      valid_bins: 165,
    },
  },
  handoff: {
    augmented_hdf5_has_sph: true,
    ascii_nsp_block_count: 2,
    ascii_path: "/mock/out.mcompo.txt",
    augmented_hdf5_path: "/mock/mgxs_with_sph.h5",
  },
  per_mixture: [
    {
      mixture: "A",
      ce_flux_min: 1,
      ce_flux_max: 2,
      mg_flux_min: 1,
      mg_flux_max: 2,
      normalized_mg_over_ce_min: 0.9,
      normalized_mg_over_ce_max: 1.1,
      sph_min: 0.9,
      sph_max: 1.1,
      sph_mean: 1,
      max_abs_sph_minus_1: 0.1,
    },
    {
      mixture: "B",
      ce_flux_min: 1,
      ce_flux_max: 2,
      mg_flux_min: 1,
      mg_flux_max: 2,
      normalized_mg_over_ce_min: 0.7,
      normalized_mg_over_ce_max: 1.3,
      sph_min: 0.7,
      sph_max: 1.3,
      sph_mean: 1,
      max_abs_sph_minus_1: 0.3,
    },
  ],
};

describe("openmcSphSummary", () => {
  it("marks summaries with HDF5 SPH and ASCII NSPH as pass", () => {
    expect(summaryStatus(SUMMARY)).toMatchObject({
      tone: "pass",
      label: "handoff carries NSPH",
    });
  });

  it("warns when SPH is present but only demonstration-quality", () => {
    expect(
      summaryStatus({
        ...SUMMARY,
        quality: {
          ...SUMMARY.quality!,
          decision: "openmc_ce_mg_sph_demonstration_quality",
          production_ready: false,
          max_flux_relative_std_dev: 0.2,
        },
      }),
    ).toMatchObject({
      tone: "warn",
      label: "demo-quality NSPH",
    });
  });

  it("warns when SPH is present but flux statistics need review", () => {
    expect(
      summaryStatus({
        ...SUMMARY,
        quality: {
          ...SUMMARY.quality!,
          decision: "openmc_ce_mg_sph_statistical_review_required",
          production_ready: false,
          demonstration_quality: false,
          max_flux_relative_std_dev: 0.6,
        },
      }),
    ).toMatchObject({
      tone: "warn",
      label: "statistics need review",
    });
  });

  it("sorts mixtures by largest SPH deviation", () => {
    expect(topSphDeviationRows(SUMMARY).map((row) => row.mixture)).toEqual([
      "B",
      "A",
    ]);
  });

  it("formats compact physics numbers", () => {
    expect(formatPhysicsNumber(0)).toBe("0");
    expect(formatPhysicsNumber(0.000000123)).toBe("1.230e-7");
    expect(formatPhysicsNumber(1.2300)).toBe("1.23");
  });

  it("describes the Pn handoff and Hn MG macro treatments separately", () => {
    expect(formatScatterTreatment(SUMMARY)).toBe("P3 handoff · H16 MG macro");
  });

  it("extracts current and frozen-flux reaction-rate preservation diagnostics", () => {
    const rows = reactionRatePreservationRows(SUMMARY);

    expect(rows.map((row) => row.id)).toEqual(["current", "frozen"]);
    expect(rows[0]).toMatchObject({
      label: "Current OpenMC MG solve",
      maxResidual: 0.24,
      validBins: 165,
    });
    expect(rows[1].maxResidual).toBe(5.0e-12);
  });
});

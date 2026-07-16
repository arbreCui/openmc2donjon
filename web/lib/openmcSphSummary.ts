import type { OpenmcSphPhysicsSummary } from "./api";

export const NATIVE_DRAGON_SPH_SUMMARY_SCHEMA =
  "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1";

export function isNativeDragonSphSummary(
  summary: OpenmcSphPhysicsSummary,
): boolean {
  return summary.schema === NATIVE_DRAGON_SPH_SUMMARY_SCHEMA;
}

/**
 * One strict, fail-closed verdict for native DRAGON SPH acceptance.
 *
 * The validator's audit verdict is necessary but is not trusted on its own:
 * older summaries can still carry `physics_acceptance: "passed"` while
 * omitting newer raw convergence records.  A green native verdict therefore
 * requires the live audit, every validator acceptance flag, and the matching
 * raw solver evidence to agree.
 */
export function nativeDragonSphAcceptancePassed(
  summary: OpenmcSphPhysicsSummary,
): boolean {
  if (!isNativeDragonSphSummary(summary)) return false;

  const audit = summary.evidence_audit;
  const checks = summary.acceptance_checks;
  const native = summary.native_sph;
  const quality = summary.quality;
  if (!audit || !checks || !native || !quality) return false;

  const positiveChecks = [
    checks.donjon_normal_end,
    checks.native_sph_converged,
    checks.native_sph_factors_unmodified,
    checks.native_sph_not_stopped_by_oscillation,
    checks.one_speed_convergence_provable,
    checks.final_flux_solve_converged,
    checks.energy_coverage_passed,
    checks.leakage_balance_available_when_required,
    checks.reference_physical_balance_within_openmc_uncertainty,
    checks.donjon_keff_within_openmc_uncertainty,
  ];

  return (
    audit.origin === "live_file" &&
    audit.summary_file_present === true &&
    audit.all_referenced_handoff_artifacts_present === true &&
    audit.all_referenced_handoff_artifacts_hash_verified === true &&
    audit.evidence_integrity?.verified === true &&
    audit.physics_acceptance === "passed" &&
    quality.structural_passed === true &&
    quality.production_ready === true &&
    positiveChecks.every((value) => value === true) &&
    checks.empirical_eigenvalue_multiplier_used === false &&
    checks.adf_used === false &&
    native.normal_end === true &&
    native.converged === true &&
    native.one_speed_convergence_provable === true &&
    native.final_flux_solve_converged === true &&
    native.factors_unmodified === true &&
    native.flux_nonconvergence_count === 0 &&
    native.negative_factor_correction_count === 0 &&
    (native.oscillation_stop_count ?? 0) === 0 &&
    summary.sph.clipped_count === 0
  );
}

export function evidenceAuditPresentation(
  summary: OpenmcSphPhysicsSummary,
): { label: string; detail: string; passed: boolean } {
  const audit = summary.evidence_audit;
  if (!audit) {
    return {
      label: "physics acceptance not evaluated",
      detail: "No evidence audit accompanies this summary.",
      passed: false,
    };
  }

  if (isNativeDragonSphSummary(summary)) {
    if (nativeDragonSphAcceptancePassed(summary)) {
      return {
        label: "physics acceptance passed",
        detail:
          "The native validator's declared artifacts are available, and the audit, acceptance checks, and raw solver records agree that every physical/statistical gate passes. Full-core acceptance remains separate.",
        passed: true,
      };
    }
    if (audit.origin !== "live_file") {
      return {
        label: "physics acceptance not evaluated",
        detail:
          "Fixture values are useful for UI and workflow review. They are not a substitute for preserved source artifacts and rerunnable calculations.",
        passed: false,
      };
    }
    if (audit.all_referenced_handoff_artifacts_present !== true) {
      return {
        label: "physics acceptance blocked",
        detail:
          "The summary is readable, but its declared handoff artifacts are incomplete; rerun or restore them before review.",
        passed: false,
      };
    }
    if (
      audit.all_referenced_handoff_artifacts_hash_verified !== true ||
      audit.evidence_integrity?.verified !== true
    ) {
      return {
        label: "physics acceptance blocked",
        detail:
          "The files exist, but their live hashes, Converter receipt, OpenMC provenance, execution deck, or forbidden-correction audit is incomplete or contradictory.",
        passed: false,
      };
    }
    if (audit.physics_acceptance === "failed") {
      return {
        label: "physics acceptance failed",
        detail:
          "The native validator rejected at least one required physical, statistical, or solver-convergence gate.",
        passed: false,
      };
    }
    if (audit.physics_acceptance === "passed") {
      return {
        label: "physics acceptance blocked",
        detail:
          "The stored audit says passed, but the current strict contract is missing or contradicts a required acceptance check or raw solver record. Revalidate this summary before use.",
        passed: false,
      };
    }
    return {
      label: "physics acceptance not evaluated",
      detail:
        "The summary and its declared artifacts are available, but no strict native physics acceptance was established.",
      passed: false,
    };
  }

  return {
    label:
      audit.physics_acceptance === "failed"
        ? "physics acceptance failed"
        : "physics acceptance not evaluated",
    detail:
      audit.origin === "live_file"
        ? "The summary and its declared handoff artifacts establish reproducible handoff evidence only; OpenMC-side NSPH is not native DRAGON/DONJON physics acceptance."
        : "Fixture values are useful for UI and workflow review. They are not a substitute for preserved source artifacts and rerunnable calculations.",
    passed: false,
  };
}

export function summaryStatus(summary: OpenmcSphPhysicsSummary): {
  label: string;
  tone: "pass" | "warn";
  detail: string;
} {
  const audit = summary.evidence_audit;
  if (audit?.origin === "mock_fixture" || audit?.origin === "recorded_fixture") {
    return {
      label: "recorded fixture — review only",
      tone: "warn",
      detail:
        "This JSON is fixture-backed recorded data. Use it to inspect the workflow and report shape, not as a live or reproducible physics acceptance result.",
    };
  }
  if (audit?.all_referenced_handoff_artifacts_present === false) {
    return {
      label: "referenced artifacts missing",
      tone: "warn",
      detail:
        "The summary file is readable, but one or more referenced HDF5 or ASCII handoff artifacts are missing or outside the configured workspace.",
    };
  }
  if (
    isNativeDragonSphSummary(summary) &&
    audit?.origin === "live_file" &&
    (audit.all_referenced_handoff_artifacts_hash_verified !== true ||
      audit.evidence_integrity?.verified !== true)
  ) {
    return {
      label: "native evidence integrity blocked",
      tone: "warn",
      detail:
        "The evidence files are present, but live SHA-256, Converter receipt, OpenMC provenance, execution-deck reproduction, or forbidden-correction checks did not verify.",
    };
  }
  if (isNativeDragonSphSummary(summary)) {
    if (nativeDragonSphAcceptancePassed(summary)) {
      return {
        label: "native SPH physics pass",
        tone: "pass",
        detail:
          "DRAGON native SPH, every one-speed inner solve, and the final transport solve have proved convergence without factor reset; all referenced artifacts are present, and the physical-balance and DONJON eigenvalue gates pass within the OpenMC uncertainty.",
      };
    }
    return {
      label: "native SPH review required",
      tone: "warn",
      detail:
        "The native DRAGON SPH summary is present, but its one-speed convergence proof, final convergence, artifact, energy-coverage, or eigenvalue acceptance is incomplete.",
    };
  }
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
      label: "SPH handoff present — validation required",
      tone: "warn",
      detail: `SPH factors are present in the augmented HDF5 and exported ${route}, but this OpenMC-side record is not a native DRAGON/DONJON physics acceptance.`,
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
  if (isNativeDragonSphSummary(summary)) {
    const solver = summary.native_sph?.solver_family?.toUpperCase() ?? "SN/SPN";
    return `P${summary.legendre_order} Converter data · DONJON ${solver}`;
  }
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

export function openmcSphConvertHref(
  summary: OpenmcSphPhysicsSummary,
): string | null {
  // Native DRAGON SPH happens after Converter. Sending the reference HDF5
  // back to Converter would reverse the physical workflow and discard the
  // corrected MACROLIB produced by SPH:.
  if (isNativeDragonSphSummary(summary)) return null;
  const input = summary.handoff.augmented_hdf5_path?.trim();
  const output = openmcSphOutputPath(summary)?.trim();
  if (!input || !output) return null;

  const format = openmcSphOutputFormat(summary);
  const params = new URLSearchParams({
    intent: "openmc-sph",
    input,
    output,
    format,
    writer_backend: "ascii",
    check: "1",
    production: "1",
    require_known_mesh: "0",
    comment: "OpenMC-side SPH-augmented handoff",
  });
  return `/convert?${params.toString()}`;
}

export function nativeSphValidatorHref(
  summary: OpenmcSphPhysicsSummary,
): string | null {
  if (!isNativeDragonSphSummary(summary)) return null;
  const handoff = summary.handoff;
  const required = {
    reference_h5: handoff.augmented_hdf5_path,
    reference_macrolib: handoff.reference_macrolib_path,
    sph_macrolib: handoff.macrolib_ascii_path ?? handoff.ascii_path,
    verify_macrolib: handoff.verification_macrolib_path,
    result_listing: handoff.result_listing_path,
    execution_deck: handoff.execution_deck_path,
    energy_coverage: handoff.energy_coverage_path,
    converter_receipt: handoff.converter_receipt_path,
    summary_json: summary.requested_path,
  };
  if (Object.values(required).some((value) => !value?.trim())) return null;
  const params = new URLSearchParams({ command: "validate-native-sph" });
  for (const [key, value] of Object.entries(required)) {
    params.set(key, value!);
  }
  return `/builder?${params.toString()}`;
}

export type FailClosedCheckState = "pass" | "fail" | "unknown";

export function forbiddenCorrectionAbsenceState(
  used: boolean | null | undefined,
): FailClosedCheckState {
  if (used === false) return "pass";
  if (used === true) return "fail";
  return "unknown";
}

/**
 * A native-SPH summary declaration is not proof that a forbidden correction
 * was absent.  The green state requires the live deck/listing audit to verify
 * absence as well; missing or contradictory audit evidence stays fail-closed.
 */
export function verifiedForbiddenCorrectionAbsenceState(
  used: boolean | null | undefined,
  evidenceStatus: string | null | undefined,
): FailClosedCheckState {
  if (used === true || evidenceStatus === "observed") return "fail";
  if (used === false && evidenceStatus === "verified_absent") return "pass";
  return "unknown";
}

function openmcSphOutputPath(summary: OpenmcSphPhysicsSummary): string | null {
  const accepted = normalizedAcceptedFormat(summary);
  if (accepted === "macrolib") {
    return summary.handoff.macrolib_ascii_path ?? summary.handoff.ascii_path;
  }
  if (accepted === "multicompo") {
    return summary.handoff.multicompo_ascii_path ?? summary.handoff.ascii_path;
  }
  return summary.handoff.ascii_path;
}

function openmcSphOutputFormat(summary: OpenmcSphPhysicsSummary) {
  const accepted = normalizedAcceptedFormat(summary);
  if (accepted === "macrolib" || accepted === "multicompo") return accepted;
  const output = summary.handoff.ascii_path ?? "";
  return output.includes(".macrolib.") ? "macrolib" : "multicompo";
}

function normalizedAcceptedFormat(
  summary: OpenmcSphPhysicsSummary,
): string | null {
  return summary.handoff.accepted_sph_consumption_format?.toLowerCase() ?? null;
}

export function sphUpdatePolicyRows(summary: OpenmcSphPhysicsSummary): {
  id: "target" | "zero-flux" | "flux-floor" | "freeze-groups";
  label: string;
  value: string;
  detail: string;
}[] {
  const rows: {
    id: "target" | "zero-flux" | "flux-floor" | "freeze-groups";
    label: string;
    value: string;
    detail: string;
  }[] = [];
  if (isNativeDragonSphSummary(summary)) {
    const negativeResets =
      summary.native_sph?.negative_factor_correction_count ?? null;
    const factorsUnmodified = summary.native_sph?.factors_unmodified === true;
    const correctionAudit =
      summary.evidence_audit?.evidence_integrity?.forbidden_corrections;
    const forbiddenCorrectionObserved =
      correctionAudit?.status === "forbidden_correction_observed" ||
      summary.native_sph?.factors_unmodified === false ||
      (negativeResets ?? 0) > 0;
    const forbiddenCorrectionsVerifiedAbsent =
      correctionAudit?.status === "verified_absent" &&
      factorsUnmodified &&
      negativeResets === 0;
    rows.push({
      id: "target",
      label: "SPH method",
      value: "DRAGON native STD",
      detail:
        "DRAGON solves the SPH fixed point on the declared coarse geometry using Converter reference rates and flux integrals.",
    });
    rows.push({
      id: "zero-flux",
      label: "Forbidden numerical fallback",
      value: forbiddenCorrectionObserved
        ? "forbidden correction observed"
        : forbiddenCorrectionsVerifiedAbsent
          ? "verified absent"
          : "not established",
      detail:
        "Acceptance forbids zero-bin substitution, flux floors, frozen groups, clipping or factor reset, ADF, and empirical eigenvalue factors. Absence must be proved from the live execution deck and result listing.",
    });
    return rows;
  }
  if (summary.sph_target != null) {
    rows.push({
      id: "target",
      label: "SPH target",
      value: summary.sph_target,
      detail:
        summary.sph_target === "rate"
          ? "Rate-preserving fixed point: MG flux matches SPH times the CE reference."
          : "Flux-matching fixed point: corrected MG flux matches the CE reference.",
    });
  }
  if (summary.zero_flux_policy != null) {
    rows.push({
      id: "zero-flux",
      label: "Zero-flux policy",
      value: summary.zero_flux_policy,
      detail:
        summary.zero_flux_policy === "identity"
          ? `${summary.identity_bin_count ?? 0} bin(s) with zero CE and MG flux kept the previous SPH.`
          : "Bins where CE and MG flux are both exactly zero fail the update.",
    });
  }
  if (summary.flux_floor_rel != null) {
    rows.push({
      id: "flux-floor",
      label: "Flux floor",
      value: formatPhysicsNumber(summary.flux_floor_rel),
      detail: `${summary.floored_bin_count ?? 0} bin(s) below the per-mixture floor were frozen at the previous SPH.`,
    });
  }
  if (summary.freeze_groups != null && summary.freeze_groups.length > 0) {
    rows.push({
      id: "freeze-groups",
      label: "Frozen groups",
      value: summary.freeze_groups.join(", "),
      detail: `${summary.frozen_group_bin_count ?? 0} bin(s) frozen at the previous SPH across all mixtures.`,
    });
  }
  return rows;
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
  if (isNativeDragonSphSummary(summary)) {
    const native = summary.native_sph;
    const eigenvalue = summary.eigenvalue_validation;
    const balance = summary.component_balance;
    return [
      {
        id: "flux",
        label: "OpenMC reference uncertainty",
        value: formatPhysicsNumber(
          summary.flux_uncertainty.ce_max_relative_std_dev,
        ),
        detail: `Maximum retained-bin relative standard deviation; declared production threshold ${formatPhysicsNumber(
          summary.quality?.production_flux_relative_std_dev_threshold,
        )}.`,
      },
      {
        id: "sph",
        label: "Native DRAGON SPH",
        value: native?.converged ? `${native.iterations} iterations` : "not converged",
        detail: `Final RMS factor update ${formatPhysicsNumber(
          native?.final_rms_factor_update,
        )}; criterion ${formatPhysicsNumber(native?.epsilon)}.`,
      },
      {
        id: "rates",
        label: "Global reaction-rate balance",
        value: formatPhysicsNumber(balance?.net_loss_relative_residual),
        detail: `Physical flux RMS residual ${formatPhysicsNumber(
          balance?.flux_rms_relative_residual,
        )}. Fitted eigenvalue factors are forbidden; their absence is accepted only by the live deck/listing audit.`,
      },
      {
        id: "handoff",
        label: "DONJON vs OpenMC",
        value:
          eigenvalue == null
            ? "n/a"
            : `${eigenvalue.donjon_delta_pcm.toFixed(1)} pcm`,
        detail:
          eigenvalue == null
            ? "No eigenvalue comparison was recorded."
            : `DONJON k=${formatPhysicsNumber(eigenvalue.donjon_keff)}; ${formatPhysicsNumber(
                eigenvalue.donjon_z,
              )}σ against OpenMC k=${formatPhysicsNumber(eigenvalue.openmc_keff)}.`,
      },
    ];
  }
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
      detail: `Declared SPH consumption route: ${acceptedFormat.toUpperCase()} GROUP/*/NSPH.`,
    },
  ];
  if (donjon) {
    const status = donjon.status ?? "not run";
    const pn = formatPhysicsNumber(donjon.pn_ntot0_ratio);
    const sn = formatPhysicsNumber(donjon.sn_ntot0_ratio);
    const expected =
      donjon.expected_g1 ?? donjon.expected_mix3_g1 ?? null;
    const target =
      donjon.target_mix != null && expected != null
        ? `target mix ${donjon.target_mix} group 1 NSPH ${formatPhysicsNumber(
            expected,
          )}; `
        : "";
    rows.push({
      id: "donjon",
      label: "DONJON consume smoke",
      value: status,
      detail: `${target}DSPH/MAC checked exported NSPH; PN NTOT0 ratio ${pn}, SN NTOT0 ratio ${sn}.`,
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

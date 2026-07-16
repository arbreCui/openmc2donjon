import type {
  ConvertPreflightInput,
  ConvertResponse,
  ExecutionJob,
  OpenmcSphPhysicsSummary,
  WriterComparisonResponse,
} from "./api";
import {
  isNativeDragonSphSummary,
  nativeDragonSphAcceptancePassed,
} from "./openmcSphSummary";

export type EvidenceStageId =
  | "handoff-contract"
  | "writer-validation"
  | "donjon-ingest"
  | "physics-equivalence"
  | "reactor-validation";

export type EvidenceStageStatus =
  | "passed"
  | "failed"
  | "pending"
  | "evidence-present"
  | "not-evaluated";

export interface EvidenceStage {
  id: EvidenceStageId;
  label: string;
  status: EvidenceStageStatus;
  summary: string;
}

const LABELS: Record<EvidenceStageId, string> = {
  "handoff-contract": "Handoff contract",
  "writer-validation": "Writer validation",
  "donjon-ingest": "DONJON ingest",
  "physics-equivalence": "Physics equivalence",
  "reactor-validation": "Reactor validation",
};

export function evidenceStatusLabel(status: EvidenceStageStatus): string {
  if (status === "passed") return "PASS";
  if (status === "failed") return "FAIL";
  if (status === "pending") return "PENDING";
  if (status === "evidence-present") return "EVIDENCE PRESENT";
  return "NOT EVALUATED";
}

export function converterEvidenceLadder(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): readonly EvidenceStage[] {
  const hasPreflight = data.preflight !== null;
  const contractStatus: EvidenceStageStatus = hasPreflight
    ? data.preflight_ok && data.ok
      ? "passed"
      : "failed"
    : "not-evaluated";

  let writerStatus: EvidenceStageStatus = "not-evaluated";
  let writerSummary =
    "No output writer was exercised. A dry run does not serialize an artifact.";
  if (!data.dry_run) {
    if (!data.converted || !data.output_exists) {
      writerStatus = "failed";
      writerSummary = "The requested output artifact was not confirmed.";
    } else if (data.writer_backend === "pygan") {
      writerStatus = "evidence-present";
      writerSummary =
        "PyGan serialized the artifact, but the ASCII-versus-PyGan semantic comparison is a separate required evidence step.";
    } else if (data.output_sha256) {
      writerStatus = "passed";
      writerSummary =
        "Built-in ASCII serialization completed and the output hash was recorded. This is not a physics verdict.";
    } else {
      writerStatus = "evidence-present";
      writerSummary =
        "The ASCII artifact exists, but this response did not record an output hash.";
    }
  }

  let physicsStatus: EvidenceStageStatus = "not-evaluated";
  let physicsSummary =
    "No project-declared physics-equivalence result is attached to this Converter response.";
  const hasSphEvidence =
    input?.sph_applied === true || (input?.sph_calculations ?? 0) > 0;
  if (data.physical_sph_required && !hasSphEvidence) {
    physicsStatus = "failed";
    physicsSummary =
      "Physical SPH was required, but the required applied-SPH provenance was not found.";
  } else if (hasSphEvidence) {
    physicsStatus = "evidence-present";
    physicsSummary = input?.sph_applied
      ? "Applied-SPH provenance is present. Converter does not establish convergence or reaction-rate acceptance without the physics summary."
      : "SPH records are present. Converter does not establish convergence or reaction-rate acceptance from those records alone.";
  }

  return [
    stage(
      "handoff-contract",
      contractStatus,
      hasPreflight
        ? data.preflight_ok && data.ok
          ? "The declared HDF5 and output handoff contract passed. This does not accept SPH or reactor physics."
          : "The Converter handoff contract failed; no downstream acceptance can be inferred."
        : "No Converter contract preflight was recorded for this action.",
    ),
    stage("writer-validation", writerStatus, writerSummary),
    stage(
      "donjon-ingest",
      "not-evaluated",
      "Converter did not run a DONJON ingest deck. Use the DONJON page to record this evidence.",
    ),
    stage("physics-equivalence", physicsStatus, physicsSummary),
    stage(
      "reactor-validation",
      "not-evaluated",
      "No component or full-core benchmark comparison is part of this Converter result.",
    ),
  ];
}

export function writerComparisonEvidenceLadder(
  data: WriterComparisonResponse,
): readonly EvidenceStage[] {
  const live = !data.mock_mode;
  const writerStatus: EvidenceStageStatus = data.ok
    ? live
      ? "passed"
      : "evidence-present"
    : "failed";
  return [
    stage(
      "handoff-contract",
      "not-evaluated",
      "Writer comparison does not record a production Converter contract decision.",
    ),
    stage(
      "writer-validation",
      writerStatus,
      data.ok
        ? live
          ? `${data.compared_payloads} LCM payloads matched within the declared tolerances.`
          : "The fixture comparison completed, but mock evidence is not a live PyGan acceptance result."
        : `${data.issue_count} semantic writer difference${data.issue_count === 1 ? "" : "s"} were reported.`,
    ),
    stage(
      "donjon-ingest",
      "not-evaluated",
      "The comparison parses LCM trees; it does not run a DONJON ingest deck.",
    ),
    stage(
      "physics-equivalence",
      "not-evaluated",
      "Writer equality does not test CE/MG reaction-rate or SPH equivalence.",
    ),
    stage(
      "reactor-validation",
      "not-evaluated",
      "Writer equality does not validate a component or full-core calculation.",
    ),
  ];
}

export function openmcSphEvidenceLadder(
  summary: OpenmcSphPhysicsSummary,
): readonly EvidenceStage[] {
  const audit = summary.evidence_audit;
  const fixture =
    audit?.origin === "mock_fixture" || audit?.origin === "recorded_fixture";
  const native = isNativeDragonSphSummary(summary);
  if (native) {
    const artifactsPresent = audit?.all_referenced_handoff_artifacts_present;
    const strictAcceptancePassed = nativeDragonSphAcceptancePassed(summary);
    const normalEnd =
      summary.acceptance_checks?.donjon_normal_end === true &&
      summary.native_sph?.normal_end === true;
    const sphConverged =
      summary.acceptance_checks?.native_sph_converged === true &&
      summary.native_sph?.converged === true;
    const oneSpeedConvergenceProved =
      summary.acceptance_checks?.one_speed_convergence_provable === true &&
      summary.native_sph?.one_speed_convergence_provable === true;
    const finalTransportConverged =
      summary.acceptance_checks?.final_flux_solve_converged === true &&
      summary.native_sph?.final_flux_solve_converged === true;
    const factorsUnmodified =
      summary.acceptance_checks?.native_sph_factors_unmodified === true &&
      summary.native_sph?.factors_unmodified === true &&
      summary.native_sph?.negative_factor_correction_count === 0;
    const noOscillation =
      summary.acceptance_checks?.native_sph_not_stopped_by_oscillation === true &&
      (summary.native_sph?.oscillation_stop_count ?? 0) === 0;
    const noFluxNonconvergence =
      summary.native_sph?.flux_nonconvergence_count === 0;
    const deterministicSolvePassed =
      normalEnd &&
      sphConverged &&
      oneSpeedConvergenceProved &&
      finalTransportConverged &&
      factorsUnmodified &&
      noOscillation &&
      noFluxNonconvergence;
    const balanceKind =
      summary.eigenvalue_validation?.reference_physical_balance_kind;
    const balanceLabel =
      balanceKind === "finite-domain-keff"
        ? "finite-domain physical balance"
        : balanceKind === "collision-balance-kinf"
          ? "closed-domain collision balance"
          : "explicit physical balance";
    return [
      stage(
        "handoff-contract",
        artifactsPresent === false
          ? "failed"
          : strictAcceptancePassed
            ? "passed"
            : "evidence-present",
        artifactsPresent === true
          ? strictAcceptancePassed
            ? "The Converter reference HDF5, reference MACROLIB, SPH MACROLIB, verification MACROLIB, and DONJON result are all present."
            : "The declared handoff artifacts are present, but this summary is blocked by the strict native acceptance contract."
          : "One or more artifacts required to reproduce the native SPH handoff are missing or not yet audited.",
      ),
      stage(
        "writer-validation",
        "not-evaluated",
        "This physics summary does not compare the built-in ASCII and PyGan writer trees.",
      ),
      stage(
        "donjon-ingest",
        strictAcceptancePassed
          ? "passed"
          : deterministicSolvePassed
            ? "evidence-present"
            : "failed",
        deterministicSolvePassed
          ? strictAcceptancePassed
            ? "The DRAGON SPH fixed point, every one-speed inner solve, and the final DONJON transport solve have proved convergence without any negative-factor reset."
            : "The deterministic solver records are present, but no PASS is issued while the strict native audit or a required physics gate remains blocked."
          : "A normal end alone is insufficient: proof of every one-speed inner solve, the final transport solve, unmodified SPH factors, or one of these records is missing.",
      ),
      stage(
        "physics-equivalence",
        strictAcceptancePassed ? "passed" : "failed",
        strictAcceptancePassed
          ? `Native SPH converged and the energy-coverage, ${balanceLabel}, and DONJON eigenvalue gates pass within the declared OpenMC uncertainty.`
          : audit?.physics_acceptance === "passed"
            ? "The stored audit says passed, but the current strict acceptance contract is missing or contradicts required raw solver or validator evidence."
            : "At least one declared native-SPH physics gate did not pass.",
      ),
      stage(
        "reactor-validation",
        "not-evaluated",
        "This is a declared coarse-model/component closure. It does not by itself accept a separate full-core loading calculation.",
      ),
    ];
  }
  const handoffComplete =
    summary.handoff.augmented_hdf5_has_sph &&
    summary.handoff.ascii_nsp_block_count > 0;
  const artifactsPresent = audit?.all_referenced_handoff_artifacts_present;
  const handoffStatus: EvidenceStageStatus = fixture
    ? "evidence-present"
    : handoffComplete && artifactsPresent !== false
      ? "passed"
      : handoffComplete
        ? "evidence-present"
        : "failed";
  const donjonStatus: EvidenceStageStatus =
    summary.donjon_consumption?.status === "passed"
      ? fixture
        ? "evidence-present"
        : "passed"
      : summary.donjon_consumption?.status === "failed"
        ? "failed"
        : "not-evaluated";

  return [
    stage(
      "handoff-contract",
      handoffStatus,
      fixture
        ? "This is fixture-backed recorded evidence. It can demonstrate the report shape but is not a currently reproducible live handoff."
        : artifactsPresent === false
          ? "The summary records an SPH handoff, but one or more referenced handoff artifacts are missing or outside the configured workspace."
          : handoffComplete
            ? "The summary records SPH datasets and exported NSPH blocks; referenced handoff artifacts are available."
            : "The summary does not confirm both augmented HDF5 SPH data and exported NSPH blocks.",
    ),
    stage(
      "writer-validation",
      "not-evaluated",
      "The SPH summary does not compare built-in ASCII and PyGan writer semantics.",
    ),
    stage(
      "donjon-ingest",
      donjonStatus,
      summary.donjon_consumption?.status === "passed"
        ? fixture
          ? "The recorded fixture says the DONJON consume smoke passed; load live artifacts to reproduce it."
          : "The attached DONJON consume smoke passed for this recorded handoff."
        : "No passing DONJON consume result is attached to this summary.",
    ),
    stage(
      "physics-equivalence",
      "evidence-present",
      fixture
        ? "Recorded CE/MG flux, uncertainty, and SPH values are present, but their source files are not live evidence in this session."
        : "CE/MG flux, uncertainty, and SPH diagnostics are present. A declared equivalence target and acceptance tolerance are still required for PASS.",
    ),
    stage(
      "reactor-validation",
      "not-evaluated",
      "This summary does not contain an accepted component or full-core benchmark comparison. A k-effective diagnostic alone is not acceptance.",
    ),
  ];
}

export function donjonEvidenceLadder(
  label: string,
  job: ExecutionJob,
): readonly EvidenceStage[] {
  const ingestStatus: EvidenceStageStatus =
    job.status === "completed"
      ? "passed"
      : job.status === "failed"
        ? "failed"
        : "pending";
  const ingestOnly = label.toLowerCase().includes("ingest");
  const hasKeff = job.k_effective !== null;

  return [
    stage(
      "handoff-contract",
      "not-evaluated",
      "This DONJON job does not rerun or accept the Converter production contract.",
    ),
    stage(
      "writer-validation",
      "not-evaluated",
      "This DONJON job consumes the selected artifact but does not compare writer backends.",
    ),
    stage(
      "donjon-ingest",
      ingestStatus,
      job.status === "completed"
        ? "The submitted DONJON deck completed and read the selected object."
        : job.status === "failed"
          ? "The DONJON deck failed; inspect the result log before continuing."
          : "The DONJON job has not completed yet.",
    ),
    stage(
      "physics-equivalence",
      "not-evaluated",
      "Deck completion does not compare reaction rates, flux fields, or converged SPH evidence against a reference.",
    ),
    stage(
      "reactor-validation",
      "not-evaluated",
      ingestOnly
        ? "This is an ingest-only deck; no reactor solve or benchmark acceptance was requested."
        : hasKeff
          ? `A k-effective value (${job.k_effective?.toFixed(6)}) was computed, but no declared reference, uncertainty, or acceptance tolerance was applied.`
          : "The diagnostic run has no benchmark-backed reactor acceptance decision.",
    ),
  ];
}

function stage(
  id: EvidenceStageId,
  status: EvidenceStageStatus,
  summary: string,
): EvidenceStage {
  return { id, label: LABELS[id], status, summary };
}

import type { JsonValue, SphLoopAcceptanceCheck } from "./api";

export type ReferenceFluxUncertaintyStatus =
  | "present"
  | "missing"
  | "not-recorded";

export interface ReferenceFluxUncertaintySummary {
  status: ReferenceFluxUncertaintyStatus;
  tone: "pass" | "warn" | "fail" | "neutral";
  badge: string;
  datasetLabel: string;
  maxRelLabel: string;
  worstLabel: string;
  detail: string;
  gateLabel: string;
}

export function summarizeReferenceFluxUncertainty(
  reference: Record<string, JsonValue> | null | undefined,
  acceptanceChecks: SphLoopAcceptanceCheck[] = [],
): ReferenceFluxUncertaintySummary {
  if (reference == null) {
    return {
      status: "not-recorded",
      tone: "neutral",
      badge: "not recorded",
      datasetLabel: "—",
      maxRelLabel: "—",
      worstLabel: "—",
      gateLabel: gateSummary(acceptanceChecks),
      detail:
        "This summary predates reference-flux uncertainty metadata, so the SPH reference flux was not audited.",
    };
  }

  const dataset = stringValue(reference.std_dev_dataset);
  const maxRel = numberValue(reference.std_dev_max_rel);
  const worst = stringValue(reference.std_dev_worst);
  const relevantChecks = referenceFluxChecks(acceptanceChecks);
  const failedGate = relevantChecks.find((check) => !check.passed);

  if (failedGate != null) {
    return {
      status: dataset == null ? "missing" : "present",
      tone: "fail",
      badge: "gate fail",
      datasetLabel: dataset ?? "missing",
      maxRelLabel: formatOptionalNumber(maxRel),
      worstLabel: worst ?? "—",
      gateLabel: gateSummary(acceptanceChecks),
      detail: failedGate.message ?? `${failedGate.name} failed for the OpenMC reference flux.`,
    };
  }

  if (dataset == null) {
    return {
      status: "missing",
      tone: "warn",
      badge: "missing",
      datasetLabel: "missing",
      maxRelLabel: "—",
      worstLabel: "—",
      gateLabel: gateSummary(acceptanceChecks),
      detail:
        "No reference-flux std_dev dataset is recorded. Enable require_reference_flux_std_dev when the SPH audit must prove OpenMC reference-flux uncertainty coverage.",
    };
  }

  return {
    status: "present",
    tone: "pass",
    badge: relevantChecks.length > 0 ? "gate pass" : "present",
    datasetLabel: dataset,
    maxRelLabel: formatOptionalNumber(maxRel),
    worstLabel: worst ?? "—",
    gateLabel: gateSummary(acceptanceChecks),
    detail:
      "The OpenMC reference flux carries a matching standard-deviation dataset for the SPH audit.",
  };
}

function referenceFluxChecks(
  checks: SphLoopAcceptanceCheck[],
): SphLoopAcceptanceCheck[] {
  return checks.filter((check) =>
    check.name === "require_reference_flux_std_dev" ||
    check.name === "max_reference_flux_std_dev_rel"
  );
}

function gateSummary(checks: SphLoopAcceptanceCheck[]): string {
  const relevant = referenceFluxChecks(checks);
  if (relevant.length === 0) return "not required";
  const failed = relevant.filter((check) => !check.passed).length;
  if (failed === 0) return `${relevant.length}/${relevant.length} pass`;
  return `${failed}/${relevant.length} fail`;
}

function stringValue(value: JsonValue | undefined): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: JsonValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatOptionalNumber(value: number | null): string {
  if (value == null) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1.0e-3 && abs < 1.0e4) return value.toPrecision(4);
  return value.toExponential(3);
}

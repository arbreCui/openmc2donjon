import type { OpenmcExportExecutionResponse } from "./api";

/**
 * Decide whether a real OpenMC export may cross into Converter.
 *
 * A successful planner response is intentionally irrelevant here. The gate
 * requires a non-mock write plus embedded, integrity-checked provenance. The
 * production variant also requires complete, transport-reproducible closure.
 */
export function openmcExportProvenanceVerified(
  data: OpenmcExportExecutionResponse,
  production: boolean,
): boolean {
  if (data.mock_mode || !data.ok) return false;
  const provenance = data.openmc_provenance;
  if (provenance.integrity?.ok !== true) return false;
  if (!provenance.capabilities.reference_bound) return false;
  if (production) {
    return (
      provenance.status === "complete" &&
      provenance.capabilities.transport_reproducible
    );
  }
  return true;
}

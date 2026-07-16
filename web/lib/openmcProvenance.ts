import type { OpenmcProvenance, OpenmcProvenanceArtifact } from "@/lib/api";

export type ProvenanceTone = "pass" | "warn" | "fail";

export interface OpenmcProvenanceView {
  label: string;
  tone: ProvenanceTone;
  summary: string;
  integrityOk: boolean;
  referenceBound: boolean;
  exportReplayable: boolean;
  transportReproducible: boolean;
}

export function openmcProvenanceView(
  provenance: OpenmcProvenance,
): OpenmcProvenanceView {
  const integrityOk = provenance.integrity?.ok === true;
  // No capability survives a failed content-binding check.  This prevents a
  // tampered record from showing a green replay claim beside an UNBOUND label.
  const referenceBound =
    integrityOk && Boolean(provenance.capabilities.reference_bound);
  const exportReplayable =
    integrityOk && Boolean(provenance.capabilities.export_replayable);
  const transportReproducible = Boolean(
    integrityOk && provenance.capabilities.transport_reproducible,
  );
  if (!integrityOk || provenance.status === "legacy") {
    return {
      label: "UNBOUND",
      tone: "fail",
      summary: "The file has no verified OpenMC fine-reference identity.",
      integrityOk,
      referenceBound,
      exportReplayable,
      transportReproducible,
    };
  }
  if (transportReproducible) {
    return {
      label: "COMPLETE",
      tone: "pass",
      summary:
        "The frozen reference and its OpenMC transport inputs are content-hash bound.",
      integrityOk,
      referenceBound,
      exportReplayable,
      transportReproducible,
    };
  }
  if (referenceBound) {
    return {
      label: "REFERENCE BOUND",
      tone: "warn",
      summary:
        "Native DRAGON SPH may consume this frozen MGXS reference; some inputs needed to replay the OpenMC transport are still missing.",
      integrityOk,
      referenceBound,
      exportReplayable,
      transportReproducible,
    };
  }
  return {
    label: "INCOMPLETE",
    tone: "fail",
    summary:
      "Recipe/statepoint identity is incomplete, so this is not yet a frozen academic reference.",
    integrityOk,
    referenceBound,
    exportReplayable,
    transportReproducible,
  };
}

export function provenanceArtifact(
  provenance: OpenmcProvenance,
  role: string,
): OpenmcProvenanceArtifact | null {
  return provenance.artifacts.find((artifact) => artifact.role === role) ?? null;
}

export function shortDigest(value: string | null | undefined): string {
  return value ? value.slice(0, 12) : "not recorded";
}

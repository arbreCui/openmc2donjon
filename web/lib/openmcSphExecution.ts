export const OPENMC_SPH_UPDATE_GATE = 0.02;

export const OPENMC_SPH_FIXED_POLICY = [
  ["Target", "Reaction-rate preserving"],
  ["Normalization", "H-factor / kappa-fission power (auto)"],
  ["Zero-flux bins", "Reject"],
  ["Numerical exemptions", "None: no clipping, floors, or frozen groups"],
] as const;

export type DampingParseResult =
  | { ok: true; value: number }
  | { ok: false; message: string };

export function parseOpenmcSphDamping(value: string): DampingParseResult {
  const trimmed = value.trim();
  if (!trimmed) {
    return { ok: false, message: "Damping is required." };
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
    return {
      ok: false,
      message: "Damping must be a finite number within 0..1.",
    };
  }
  return { ok: true, value: parsed };
}

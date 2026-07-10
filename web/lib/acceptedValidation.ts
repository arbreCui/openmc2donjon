export interface AcceptedValidationEntry {
  id: "c5g7-cartesian" | "irena30-hex" | "openmc-sph-equivalence";
  label: string;
  title: string;
  body: string;
  result: string;
}

export const ACCEPTED_VALIDATION_ENTRIES: readonly AcceptedValidationEntry[] = [
  {
    id: "c5g7-cartesian",
    label: "C5G7",
    title: "Assembly-wise Cartesian benchmark",
    body:
      "DONJON consumes the converted handoff at diffusion k 1.1896194 and SPN3 k 1.1912802 against the OpenMC reference k 1.18798.",
    result: "OpenMC k 1.18798",
  },
  {
    id: "irena30-hex",
    label: "IRENA-30",
    title: "ZREFL 91-hex core",
    body:
      "DONJON SN8 lands within Monte Carlo statistics of the paired OpenMC reference (-9 pcm at 21 pcm sigma; +29 pcm with a different seed), with per-assembly fission-source shape 1.27% worst / 0.47% RMS.",
    result: "SN8 -9 pcm",
  },
  {
    id: "openmc-sph-equivalence",
    label: "SPH",
    title: "OpenMC-side CE/MG equivalence",
    body:
      "OpenMC-side CE/MG SPH with the rate-preserving target is validated to core level on the IRENA Pb-reflector line (prescription: rate target, freeze groups {1, 31}, 2-3 iterations).",
    result: "core-level validated",
  },
] as const;

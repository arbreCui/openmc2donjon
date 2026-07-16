export interface AcceptedValidationEntry {
  id: "c5g7-cartesian" | "irena30-hex";
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
    title: "ZREFL 91-hex transport baseline",
    body:
      "A separate direct-handoff geometry baseline put DONJON SN within Monte Carlo statistics of its paired OpenMC case (-9 pcm at 21 pcm sigma; +29 pcm with a different seed), with 1.27% worst / 0.47% RMS source-shape error. It validates geometry and solver plumbing, not the new colorset-SPH production result.",
    result: "geometry baseline",
  },
] as const;

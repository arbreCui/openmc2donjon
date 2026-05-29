export interface TaskEntrypoint {
  id: "direct-convert" | "openmc-sph" | "inspect";
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  cta: string;
}

export const TASK_ENTRYPOINTS: readonly TaskEntrypoint[] = [
  {
    id: "direct-convert",
    eyebrow: "I already have HDF5",
    title: "Convert MGXS HDF5",
    body:
      "Check the OpenMC handoff, write L_MULTICOMPO or L_MACROLIB ASCII, then preview the output.",
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    cta: "Open converter",
  },
  {
    id: "openmc-sph",
    eyebrow: "Need SPH first",
    title: "Prepare CE/MG SPH",
    body:
      "Use OpenMC CE as the reference, run OpenMC MG on the same geometry/output regions, then inject NSPH before conversion.",
    href: "/openmc?workflow=two-step&equivalence=sph&format=macrolib&production=1",
    cta: "Open SPH workflow",
  },
  {
    id: "inspect",
    eyebrow: "Need to understand a file",
    title: "Inspect HDF5 or output",
    body:
      "Look at mixtures, energy groups, ADF/SPH metadata, spectra, and generated ASCII previews.",
    href: "/inspect",
    cta: "Open inspector",
  },
] as const;

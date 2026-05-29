import {
  C5G7_PRODUCTION_DEMO,
  convertDemoHref,
  convertDemoInspectHref,
} from "./convertDemo";
import { MOCK_OPENMC_SPH_DEMO } from "./openmcSphDemo";

export interface DemoShortcut {
  id: "convert-c5g7" | "inspect-c5g7" | "openmc-sph-minicase";
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  cta: string;
}

export const HOME_DEMO_SHORTCUTS: readonly DemoShortcut[] = [
  {
    id: "convert-c5g7",
    eyebrow: "C5G7 direct conversion",
    title: "Run the converter demo",
    body:
      "Open the converter prefilled with the bundled C5G7 MGXS HDF5, production checks, and MULTICOMPO output.",
    href: convertDemoHref(C5G7_PRODUCTION_DEMO),
    cta: "Open converter demo",
  },
  {
    id: "inspect-c5g7",
    eyebrow: "HDF5 handoff",
    title: "Inspect the demo MGXS",
    body:
      "Jump straight to the HDF5 inspector for mixture roster, group structure, ADF/SPH coverage, and spectra.",
    href: convertDemoInspectHref(C5G7_PRODUCTION_DEMO),
    cta: "Inspect HDF5",
  },
  {
    id: "openmc-sph-minicase",
    eyebrow: "CE/MG SPH minicase",
    title: "Review OpenMC-side SPH",
    body:
      "Open the two-region CE reference + MG macro route, including the physics summary and corrected MACROLIB NSPH handoff.",
    href: `/openmc?workflow=two-step&equivalence=sph&format=macrolib&production=1&summary=${encodeURIComponent(
      MOCK_OPENMC_SPH_DEMO.physicsSummary,
    )}`,
    cta: "Open SPH minicase",
  },
] as const;

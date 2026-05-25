import {
  C5G7_PRODUCTION_DEMO,
  convertDemoHref,
  convertDemoInspectHref,
} from "./convertDemo";

export interface DemoShortcut {
  id: "convert-c5g7" | "inspect-c5g7" | "audit-sph";
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  cta: string;
}

export const MOCK_AUDIT_DEMO_PATH =
  "/mock/home/openmc-runs/full-core-sph/sph_loop_summary_ref_stddev.json";

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
    id: "audit-sph",
    eyebrow: "SPH loop audit",
    title: "Review a 10-iteration loop",
    body:
      "Load the bundled full-core SPH loop summary with production acceptance and convergence diagnostics.",
    href: `/audit?path=${encodeURIComponent(MOCK_AUDIT_DEMO_PATH)}`,
    cta: "Open audit demo",
  },
] as const;

import { C5G7_PRODUCTION_DEMO, convertDemoHref } from "./convertDemo";

export interface DemoShortcut {
  id: "convert-c5g7";
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  cta: string;
}

// The home Demo panel keeps only the primary converter shortcut; the
// landing pages (/inspect, /openmc) self-serve their own demos.
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
] as const;

import type { ConvertFormat } from "./api";

export interface ConvertDemoPreset {
  id: string;
  label: string;
  description: string;
  inputPath: string;
  outputPath: string;
  format: ConvertFormat;
  check: boolean;
  production: boolean;
  requireKnownMesh: boolean;
}

export const C5G7_PRODUCTION_DEMO: ConvertDemoPreset = {
  id: "c5g7-production",
  label: "C5G7 production demo",
  description:
    "Fill the mock C5G7 handoff, MULTICOMPO output, preflight, and production gates.",
  inputPath: "/mock/home/openmc-runs/c5g7/handoff.h5",
  outputPath: "/mock/home/openmc-runs/c5g7/out.mcompo.txt",
  format: "multicompo",
  check: true,
  production: true,
  requireKnownMesh: false,
};

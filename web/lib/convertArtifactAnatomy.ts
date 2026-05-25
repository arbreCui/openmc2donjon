import type { ConvertFormat, ConvertPreflightInput } from "./api";

export interface ConvertArtifactAnatomySection {
  id: string;
  title: string;
  body: string;
  blocks: string[];
}

export interface ConvertArtifactAnatomy {
  label: string;
  subtitle: string;
  countLine: string;
  sections: ConvertArtifactAnatomySection[];
}

export function convertArtifactAnatomy(
  format: ConvertFormat,
  input: ConvertPreflightInput | null,
): ConvertArtifactAnatomy {
  return format === "macrolib"
    ? macrolibAnatomy(input)
    : multicompoAnatomy(input);
}

function multicompoAnatomy(input: ConvertPreflightInput | null): ConvertArtifactAnatomy {
  return {
    label: "L_MULTICOMPO",
    subtitle:
      "Mapped domain-wise library: DONJON sees the exported OpenMC domains as mixture slots with calculation records.",
    countLine: countLine(input),
    sections: [
      {
        id: "header",
        title: "Object header",
        body:
          "Top-level identity, global parameter metadata, and the 40-integer state vector for groups, mixtures, calculations, and parameter axes.",
        blocks: ["SIGNATURE", "GLOBAL", "STATE-VECTOR"],
      },
      {
        id: "map",
        title: "Mixture map",
        body:
          "The MIXTURES list preserves exported domain order. Each mixture owns CALCULATIONS and a TREE so later state axes can be added without changing the handoff shape.",
        blocks: ["MIXTURES", "CALCULATIONS", "TREE"],
      },
      {
        id: "xs",
        title: "Macroscopic XS",
        body:
          "Each calculation stores one macro isotope record with total, transport, absorption/fission data, chi, and sparse Legendre scattering triplets.",
        blocks: ["ISOTOPESLIST", "NTOT0", "STRD", "SCATxx"],
      },
      {
        id: "equivalence",
        title: "Equivalence metadata",
        body: equivalenceBody(input),
        blocks: ["L_LIBRARY", "ENERGY", "ADF/HADF", "NSPH"],
      },
    ],
  };
}

function macrolibAnatomy(input: ConvertPreflightInput | null): ConvertArtifactAnatomy {
  return {
    label: "L_MACROLIB",
    subtitle:
      "Direct one-state macrolib: compact group-major cross sections for deterministic solver consumption.",
    countLine: countLine(input),
    sections: [
      {
        id: "header",
        title: "Object header",
        body:
          "A single MACROLIB signature, state vector, descending energy boundaries, and mixture volumes.",
        blocks: ["SIGNATURE", "STATE-VECTOR", "ENERGY", "VOLUME"],
      },
      {
        id: "groups",
        title: "Group-major payload",
        body:
          "The GROUP list stores vectors over mixtures for each energy group: flux integral, total cross section, inverse velocity, diffusion coefficient, and fission data when present.",
        blocks: ["GROUP", "FLUX-INTG", "NTOT0", "DIFF"],
      },
      {
        id: "scatter",
        title: "Scattering layout",
        body:
          "For each Legendre moment, scatter is written as DRAGON sparse triplets by destination group with NJJS/IJJS/IPOS bookkeeping.",
        blocks: ["SIGSxx", "SCATxx", "NJJSxx", "IJJSxx"],
      },
      {
        id: "equivalence",
        title: "Equivalence metadata",
        body: equivalenceBody(input),
        blocks: ["ADF/HADF", "NSPH", "H-FACTOR"],
      },
    ],
  };
}

function countLine(input: ConvertPreflightInput | null): string {
  if (!input) return "Counts come from preflight when available.";
  const groups = input.energy_groups == null ? "?" : String(input.energy_groups);
  const moments =
    input.legendre_order == null ? "?" : String(input.legendre_order + 1);
  const mixtures = input.mixtures == null ? "?" : String(input.mixtures);
  const states = input.state_points == null ? "?" : String(input.state_points);
  return `${mixtures} mixture(s), ${groups} group(s), ${moments} Legendre moment(s), ${states} state point(s).`;
}

function equivalenceBody(input: ConvertPreflightInput | null): string {
  if (!input) {
    return "ADF and SPH blocks are carried when present in the input HDF5; inspect the source to confirm coverage.";
  }
  const adfFaces = input.adf_faces?.length ?? 0;
  const adfMixtures = input.adf_mixtures ?? 0;
  const sph = input.sph_calculations ?? 0;
  if (adfFaces > 0 && sph > 0) {
    return `Carries ADF for ${adfMixtures} mixture(s) across ${adfFaces} face type(s), plus ${sph} SPH calculation record(s).`;
  }
  if (adfFaces > 0) {
    return `Carries ADF for ${adfMixtures} mixture(s) across ${adfFaces} face type(s); no SPH records were reported.`;
  }
  if (sph > 0) {
    return `Carries ${sph} SPH calculation record(s); no ADF face data was reported.`;
  }
  return "No ADF or SPH records were reported for this input.";
}

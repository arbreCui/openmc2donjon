import type { CommandCatalogEntry } from "./api";

export interface CommandWorkflowMapping {
  available: boolean;
  href: string | null;
  surface: string;
  title: string;
  summary: string;
  presets: string[];
  requiredInputs: string[];
}

export function commandWorkflowMapping(
  command: CommandCatalogEntry,
): CommandWorkflowMapping {
  if (!command.web_path) {
    return {
      available: false,
      href: null,
      surface: "CLI only",
      title: "No dedicated web workflow yet",
      summary:
        "This command is documented here and can be copied as CLI. A first-class web form has not been added yet.",
      presets: ["No web presets"],
      requiredInputs: ["Use the CLI form below"],
    };
  }

  const parsed = parseWebPath(command.web_path);
  if (parsed.pathname === "/convert") {
    const production = flag(parsed.searchParams.get("production"));
    const check = flag(parsed.searchParams.get("check"));
    const format = parsed.searchParams.get("format") ?? "multicompo";
    return {
      available: true,
      href: command.web_path,
      surface: "Convert page",
      title: "Direct converter workflow",
      summary:
        "Opens the converter page with the matching output object and check mode already selected.",
      presets: [
        `Output object: ${format === "macrolib" ? "MACROLIB" : "MULTICOMPO"}`,
        `Preflight: ${check ? "on" : "off"}`,
        `Production checks: ${production ? "on" : "off"}`,
      ],
      requiredInputs: [
        "Input MGXS HDF5 path",
        "Output ASCII directory or filename",
        "Optional mixture filter / metadata fields",
      ],
    };
  }

  if (parsed.pathname === "/openmc") {
    const workflow = parsed.searchParams.get("workflow") ?? "one-step";
    const equivalence = parsed.searchParams.get("equivalence") ?? "direct";
    const production = flag(parsed.searchParams.get("production"));
    return {
      available: true,
      href: command.web_path,
      surface: "OpenMC planner",
      title: "OpenMC production handoff planner",
      summary:
        "Opens the OpenMC workflow planner with the intended one-step or two-step path already selected.",
      presets: [
        `Workflow: ${workflow === "two-step" ? "two-step export then convert" : "one-step export + convert"}`,
        `Equivalence: ${equivalenceLabel(equivalence)}`,
        `Production checks: ${production ? "on" : "off"}`,
      ],
      requiredInputs: [
        "Recipe Python path",
        "Statepoint HDF5 path or no-load-statepoint mode",
        "Run directory / output artifact paths",
      ],
    };
  }

  if (parsed.pathname === "/inspect") {
    return {
      available: true,
      href: command.web_path,
      surface: "Inspect page",
      title: "MGXS handoff inspection",
      summary:
        "Opens the inspector for HDF5 metadata, mixture roster, mesh ID, spectra, and scatter views.",
      presets: ["Viewer mode: HDF5 inspect"],
      requiredInputs: ["Input MGXS HDF5 path"],
    };
  }

  if (parsed.pathname === "/audit") {
    return {
      available: true,
      href: command.web_path,
      surface: "Audit page",
      title: "SPH loop audit viewer",
      summary:
        "Opens the SPH-loop audit page for convergence, acceptance, production checks, and iteration traces.",
      presets: ["Viewer mode: SPH loop summary"],
      requiredInputs: ["SPH loop summary JSON path"],
    };
  }

  if (parsed.pathname === "/equivalence") {
    const kind = parsed.searchParams.get("kind") ?? "adf-sidecar";
    return {
      available: true,
      href: command.web_path,
      surface: "Equivalence page",
      title: "Sidecar command builder",
      summary:
        "Opens a non-mutating web form that builds the matching ADF/SPH sidecar or augmentation CLI command.",
      presets: [`Builder: ${equivalenceBuilderLabel(kind)}`],
      requiredInputs: equivalenceRequiredInputs(kind),
    };
  }

  if (parsed.pathname === "/builder") {
    const builderCommand = parsed.searchParams.get("command") ?? "unknown";
    return {
      available: true,
      href: command.web_path,
      surface: "Command builder",
      title: "Copyable CLI command builder",
      summary:
        "Opens a non-mutating form that assembles the selected CLI command with paths and key options.",
      presets: [`Builder: ${builderCommand}`],
      requiredInputs: ["Command-specific paths and options", "Terminal execution after copy"],
    };
  }

  return {
    available: true,
    href: command.web_path,
    surface: parsed.pathname,
    title: "Linked web surface",
    summary: "Opens the corresponding localhost web page for this command.",
    presets: queryPresetLabels(parsed.searchParams),
    requiredInputs: ["Fill the page-specific inputs"],
  };
}

function parseWebPath(webPath: string): URL {
  return new URL(webPath, "http://localhost");
}

function flag(value: string | null): boolean {
  if (value == null) return false;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function equivalenceLabel(value: string): string {
  if (value === "adf") return "ADF/DF sidecar";
  if (value === "sph") return "SPH sidecar";
  if (value === "flux-ratio-adf") return "flux-ratio ADF";
  return "direct";
}

function equivalenceBuilderLabel(value: string): string {
  if (value === "augment-adf") return "inject ADF/DF";
  if (value === "sph-sidecar") return "make SPH sidecar";
  if (value === "augment-sph") return "inject SPH";
  return "make ADF/DF sidecar";
}

function equivalenceRequiredInputs(value: string): string[] {
  if (value === "augment-adf") {
    return ["Input MGXS HDF5 path", "ADF sidecar HDF5 path", "Augmented HDF5 output path"];
  }
  if (value === "sph-sidecar") {
    return ["Input MGXS HDF5 path", "SPH source mode/options", "SPH sidecar output path"];
  }
  if (value === "augment-sph") {
    return ["Input MGXS HDF5 path", "SPH sidecar HDF5 path", "Augmented HDF5 output path"];
  }
  return ["Input MGXS HDF5 path", "ADF mode/options", "ADF sidecar output path"];
}

function queryPresetLabels(searchParams: URLSearchParams): string[] {
  const labels: string[] = [];
  for (const [key, value] of searchParams.entries()) {
    labels.push(`${key}: ${value}`);
  }
  return labels.length > 0 ? labels : ["No query presets"];
}

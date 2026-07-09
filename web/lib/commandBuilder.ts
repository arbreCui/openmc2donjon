export type BuilderFieldKind = "path" | "text" | "select" | "toggle";
export type BrowseMode = "file" | "directory";

export interface BuilderOption {
  value: string;
  label: string;
}

export interface BuilderField {
  name: string;
  label: string;
  kind: BuilderFieldKind;
  help: string;
  placeholder?: string;
  defaultValue?: string | boolean;
  flag?: string;
  positional?: number;
  required?: boolean;
  includeDefault?: boolean;
  repeatCsv?: boolean;
  options?: BuilderOption[];
  browse?: BrowseMode;
  extensions?: string[];
}

export interface CommandBuilderSpec {
  id: string;
  title: string;
  summary: string;
  base: string[];
  fields: BuilderField[];
  notes: string[];
}

export interface CommandBuilderStage {
  label: string;
  summary: string;
  reference: string;
}

export type BuilderValues = Record<string, string | boolean>;

export interface BuilderQueryParams {
  get(name: string): string | null;
}

const FACES = "FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX";

const FORMAT_OPTIONS = [
  { value: "macrolib", label: "MACROLIB" },
  { value: "multicompo", label: "MULTICOMPO" },
] as const;

const FLUX_NORMALIZATION_OPTIONS = [
  { value: "none", label: "none" },
  { value: "total", label: "total" },
  { value: "power", label: "power" },
  { value: "auto", label: "auto" },
] as const;

const SIGN_CONVENTION_OPTIONS = [
  { value: "", label: "default" },
  { value: "auto", label: "auto" },
  { value: "positive-outward", label: "positive outward" },
  { value: "positive-inward", label: "positive inward" },
] as const;

const H5 = [".h5", ".hdf5"];
const JSON = [".json"];

const SPH_APPLY_FORMAT_OPTIONS = [
  { value: "openmc-mgxs", label: "OpenMC native mgxs.h5" },
  { value: "converter", label: "converter HDF5" },
] as const;

export const COMMAND_BUILDER_SPECS: readonly CommandBuilderSpec[] = [
  {
    id: "diff",
    title: "Compare two MGXS HDF5 handoffs",
    summary:
      "Build the regression command that compares a reference and candidate HDF5 handoff.",
    base: ["openmc2donjon", "diff"],
    fields: [
      path("reference_h5", "Reference HDF5", "Baseline MGXS handoff.", "<reference.h5>", 0, H5),
      path("candidate_h5", "Candidate HDF5", "New MGXS handoff to compare.", "<candidate.h5>", 1, H5),
      text("rtol", "Relative tolerance", "Numeric relative tolerance; empty keeps CLI default.", "--rtol"),
      text("atol", "Absolute tolerance", "Numeric absolute tolerance; empty keeps CLI default.", "--atol"),
      toggle("ignore_attrs", "Ignore attrs", "Compare tree/datasets only.", "--ignore-attrs"),
      text(
        "ignore_attr",
        "Ignore attr names",
        "Comma-separated attribute names; each becomes one --ignore-attr flag.",
        "--ignore-attr",
        undefined,
        true,
      ),
      optionPath("summary_json", "Summary JSON", "Optional diff summary JSON.", "--summary-json", "diff.json", JSON),
      text("max_diffs", "Max printed diffs", "Optional --max-diffs override.", "--max-diffs"),
      toggle("no_fail", "No fail", "Always exit zero after printing the diff report.", "--no-fail"),
    ],
    notes: [
      "Use this before accepting a new exporter or converter change.",
      "The web page only assembles the command; the comparison still runs in your shell.",
    ],
  },
  {
    id: "compare-writers",
    title: "Compare ASCII and PyGan writers",
    summary:
      "Build the validation command that writes the same MGXS handoff with both backends and compares the LCM trees.",
    base: ["openmc2donjon", "compare-writers"],
    fields: [
      path("input_h5", "MGXS HDF5", "Input handoff to write with both backends.", "<mgxs_library.h5>", 0, H5),
      {
        ...select("format", "ASCII format", "Writer format to compare.", "--format", FORMAT_OPTIONS),
        defaultValue: "multicompo",
      },
      text("root_name", "LCM root name", "Optional LCM root name override.", "--root-name"),
      text("comment", "Comment", "Optional comment embedded in the generated handoff.", "--comment"),
      text("burnup", "Burnup", "Optional burnup value for one-state branch metadata.", "--burnup"),
      text("h_factor_default", "H-factor default", "Optional H-FACTOR fallback value.", "--h-factor-default"),
      text("mixture", "Mixture filter", "Comma-separated mixtures; each becomes one --mixture flag.", "--mixture", undefined, true),
      text("rtol", "Relative tolerance", "Semantic real-payload relative tolerance.", "--rtol"),
      text("atol", "Absolute tolerance", "Semantic real-payload absolute tolerance.", "--atol"),
      optionPath("summary_json", "Summary JSON", "Optional comparison summary JSON.", "--summary-json", "writer_compare.json", JSON),
      optionPath("keep_dir", "Keep generated files", "Optional directory for ascii.* and pygan.* outputs.", "--keep-dir", "writer_compare", undefined, false, "directory"),
      text("max_issues", "Max printed issues", "Optional --max-issues override.", "--max-issues"),
      toggle("no_fail", "No fail", "Always exit zero after printing the comparison report.", "--no-fail"),
    ],
    notes: [
      "Use this after installing PyGan to verify that the optional backend stays semantically aligned with the default ASCII writer.",
      "This is a validation command: it does not replace the default writer used by production conversion.",
    ],
  },
  {
    id: "export-surface-flux",
    title: "Export OpenMC surface flux",
    summary:
      "Build the command that extracts MeshSurfaceFilter + MuSurfaceFilter current tallies.",
    base: ["openmc2donjon", "export-surface-flux"],
    fields: [
      path("statepoint", "Statepoint", "OpenMC statepoint containing the surface tally.", "<statepoint.h5>", 0, H5),
      optionPath("output", "Surface flux HDF5", "Output HDF5 sidecar.", "-o", "face_flux.h5", H5, true),
      optionPath("mgxs", "MGXS handoff", "Optional MGXS file for energy bounds and mixture names.", "--mgxs", "mgxs_library.h5", H5),
      text("tally_name", "Tally name", "OpenMC tally name; empty keeps CLI default.", "--tally-name"),
      text("mesh_shape", "Mesh shape", "Y,X shape when mixture names are not enough.", "--mesh-shape"),
      text("mixture_names", "Mixture names", "Comma-separated row-major mixture names.", "--mixture-names"),
      text("energy_bounds", "Energy bounds", "Comma-separated ascending energy bounds in eV.", "--energy-bounds"),
      text("mu_edges", "Mu edges", "Required MuSurfaceFilter bin edges.", "--mu-edges", "-1,-0.5,0.5,1", false, true),
      text("face_area", "Face area", "Optional face area override.", "--face-area"),
      text("faces", "Faces", "Comma-separated output face names.", "--faces", FACES),
      optionPath("summary_json", "Summary JSON", "Optional export summary JSON.", "--summary-json", "surface_flux_summary.json", JSON),
      toggle("force", "Force overwrite", "Allow replacing an existing output file.", "--force"),
    ],
    notes: [
      "This is the OpenMC-side input for flux-ratio ADF.",
      "Mu edges must match the OpenMC MuSurfaceFilter bins used by the tally.",
    ],
  },
  {
    id: "export-volume-flux",
    title: "Export OpenMC volume flux",
    summary:
      "Build the command that extracts a region/group OpenMC flux tally for CE/MG SPH.",
    base: ["openmc2donjon", "export-volume-flux"],
    fields: [
      path("statepoint", "Statepoint", "OpenMC statepoint containing the flux tally.", "<statepoint.h5>", 0, H5),
      optionPath("output", "Flux HDF5", "Output HDF5 source for SPH.", "-o", "openmc_ce_flux.h5", H5, true),
      optionPath("mgxs", "MGXS handoff", "MGXS file for mixture names and group count.", "--mgxs", "mgxs_library.h5", H5),
      text("tally_name", "Tally name", "OpenMC tally name; empty keeps CLI default.", "--tally-name"),
      text("dataset_name", "Dataset name", "Output dataset name, e.g. openmc_volume_flux or openmc_mg_flux.", "--dataset-name"),
      text("std_dev_dataset_name", "Std-dev dataset", "Optional std_dev dataset name.", "--std-dev-dataset-name"),
      text("mixture_names", "Mixture names", "Comma-separated names when --mgxs is not supplied.", "--mixture-names"),
      text("energy_groups", "Energy groups", "Group count when --mgxs is not supplied.", "--energy-groups"),
      text("source_group_order", "Source group order", "Metadata label for raw tally order.", "--source-group-order"),
      toggle("allow_zero_flux", "Allow zero flux", "Accept exactly-zero flux bins, e.g. fast-spectrum thermal groups.", "--allow-zero-flux"),
      optionPath("summary_json", "Summary JSON", "Optional export summary JSON.", "--summary-json", "volume_flux_summary.json", JSON),
      toggle("force", "Force overwrite", "Allow replacing an existing output file.", "--force"),
    ],
    notes: [
      "Run once for the CE reference flux and once for the OpenMC MG macro flux.",
      "Use --dataset-name openmc_mg_flux for the MG macro side.",
    ],
  },
  {
    id: "check-face-flux",
    title: "Validate face-flux inputs",
    summary: "Build a QA command before constructing flux-ratio ADF sidecars.",
    base: ["openmc2donjon", "check-face-flux"],
    fields: [
      path("input_h5", "MGXS HDF5", "MGXS handoff used for metadata.", "<mgxs_library.h5>", 0, H5),
      optionPath("surface_flux", "Heterogeneous face flux", "HDF5 file or FILE::DATASET.", "--surface-flux", "face_flux.h5", H5, true),
      optionPath("homogeneous_face_flux", "Homogeneous face flux", "HDF5 file or FILE::DATASET.", "--homogeneous-face-flux", "homogeneous_face_flux.h5", H5, true),
      text("faces", "Faces", "Comma-separated expected face names.", "--faces", FACES),
      text("invalid_fill", "Invalid fill", "Optional fill value for invalid bins.", "--invalid-fill"),
      text("clip_min", "Clip min", "Optional lower clip bound.", "--clip-min"),
      text("clip_max", "Clip max", "Optional upper clip bound.", "--clip-max"),
      optionPath("summary_json", "Summary JSON", "Optional contract summary JSON.", "--summary-json", "face_flux_check.json", JSON),
      toggle("no_fail", "No fail", "Always exit zero after printing the report.", "--no-fail"),
    ],
    notes: ["Use this before make-adf-sidecar --mode flux-ratio."],
  },
  {
    id: "make-low-order-driver",
    title: "Canonicalize a low-order driver",
    summary:
      "Build the command that converts external low-order flux/current data into the canonical HDF5 layout.",
    base: ["openmc2donjon", "make-low-order-driver"],
    fields: [
      path("input_h5", "MGXS HDF5", "MGXS handoff used for metadata.", "<mgxs_library.h5>", 0, H5),
      optionPath("output", "Driver HDF5", "Canonical low-order driver output.", "-o", "driver.h5", H5, true),
      optionPath("raw_driver", "Raw driver bundle", "Optional raw driver HDF5 bundle.", "--raw-driver", "raw_driver.h5", H5),
      text("volume_flux", "Volume flux source", "HDF5 file or FILE::DATASET.", "--volume-flux"),
      text("net_current", "Net current source", "HDF5 file or FILE::DATASET.", "--net-current"),
      select("net_current_sign_convention", "Current sign", "Raw net-current sign convention.", "--net-current-sign-convention", SIGN_CONVENTION_OPTIONS),
      text("faces", "Faces", "Comma-separated face names.", "--faces", FACES),
      text("source_label", "Source label", "Provenance label stored in output HDF5.", "--source-label"),
      optionPath("summary_json", "Summary JSON", "Optional summary JSON.", "--summary-json", "driver_summary.json", JSON),
      toggle("force", "Force overwrite", "Allow replacing an existing output file.", "--force"),
    ],
    notes: ["The canonical driver feeds make-homogeneous-face-flux."],
  },
  {
    id: "check-low-order-driver",
    title: "Validate a low-order driver",
    summary: "Build the QA command for a canonical low-order driver HDF5.",
    base: ["openmc2donjon", "check-low-order-driver"],
    fields: [
      path("input_h5", "MGXS HDF5", "MGXS handoff used for metadata.", "<mgxs_library.h5>", 0, H5),
      path("driver_h5", "Driver HDF5", "Canonical low-order driver HDF5.", "<driver.h5>", 1, H5),
      text("faces", "Faces", "Optional expected face names.", "--faces"),
      text("face_widths", "Face widths", "Optional one width or comma-separated widths.", "--face-widths"),
      optionPath("summary_json", "Summary JSON", "Optional contract summary JSON.", "--summary-json", "driver_check.json", JSON),
      toggle("no_fail", "No fail", "Always exit zero after printing the report.", "--no-fail"),
    ],
    notes: ["Run this before reconstructing homogeneous face flux."],
  },
  {
    id: "make-homogeneous-face-flux",
    title: "Reconstruct homogeneous face flux",
    summary: "Build the homogeneous face-flux side of a flux-ratio ADF definition.",
    base: ["openmc2donjon", "make-homogeneous-face-flux"],
    fields: [
      path("input_h5", "MGXS HDF5", "MGXS handoff with transport_total.", "<mgxs_library.h5>", 0, H5),
      optionPath("output", "Homogeneous face flux", "Output HDF5.", "-o", "homogeneous_face_flux.h5", H5, true),
      text("volume_flux", "Volume flux source", "HDF5 file or FILE::DATASET.", "--volume-flux", "<volume_flux>", false, true),
      text("net_current", "Net current source", "HDF5 file or FILE::DATASET.", "--net-current", "<net_current>", false, true),
      select("net_current_sign_convention", "Current sign", "Raw net-current sign convention.", "--net-current-sign-convention", SIGN_CONVENTION_OPTIONS),
      text("faces", "Faces", "Comma-separated face names.", "--faces", FACES),
      text("face_widths", "Face widths", "One width or comma-separated widths.", "--face-widths"),
      optionPath("summary_json", "Summary JSON", "Optional summary JSON.", "--summary-json", "homogeneous_face_flux_summary.json", JSON),
      toggle("force", "Force overwrite", "Allow replacing an existing output file.", "--force"),
    ],
    notes: ["The output pairs with exported OpenMC surface flux in make-adf-sidecar."],
  },
  {
    id: "make-sph-update-table",
    title: "Compute OpenMC-side SPH table",
    summary:
      "Build the command that compares OpenMC CE reference flux and OpenMC MG macro flux, then writes an SPH CSV table.",
    base: ["openmc2donjon", "make-sph-update-table"],
    fields: [
      path("input_h5", "MGXS HDF5", "MGXS handoff used for metadata.", "<mgxs_library.h5>", 0, H5),
      optionPath("output", "SPH table CSV", "Output SPH CSV table.", "-o", "sph_update.csv", [".csv"], true),
      text("reference_flux", "OpenMC CE flux", "OpenMC CE reference flux CSV/HDF5 source.", "--reference-flux", "<openmc_ce_flux>", false, true),
      text("low_order_flux", "OpenMC MG flux", "OpenMC MG macro flux CSV/HDF5 source.", "--low-order-flux", "<openmc_mg_flux>", false, true),
      text("previous_sph", "Previous SPH", "Previous SPH CSV or HDF5 sidecar/source.", "--previous-sph"),
      text("damping", "Damping", "Optional multiplicative damping.", "--damping"),
      text("clip_min", "Clip min", "Optional minimum SPH value.", "--clip-min"),
      text("clip_max", "Clip max", "Optional maximum SPH value.", "--clip-max"),
      select("flux_normalization", "Flux normalization", "Scale low-order flux before ratio.", "--flux-normalization", FLUX_NORMALIZATION_OPTIONS),
      text("source_label", "Source label", "Provenance label recorded in the summary.", "--source-label"),
      optionPath("summary_json", "Summary JSON", "Optional iteration summary JSON.", "--summary-json", "sph_update_summary.json", JSON),
      toggle("force", "Force overwrite", "Allow replacing the CSV output.", "--force"),
    ],
    notes: ["Use this after the CE and MG OpenMC calculations share the same geometry and output regions."],
  },
  {
    id: "apply-sph",
    title: "Apply SPH to MGXS for the next MG run",
    summary:
      "Build the command that writes an SPH-corrected MGXS HDF5 copy for the next OpenMC MG macro iteration.",
    base: ["openmc2donjon", "apply-sph"],
    fields: [
      path("input_h5", "MGXS HDF5", "Input MGXS handoff to correct.", "mg_case/mgxs_unapplied.h5", 0, H5),
      select("input_format", "Input format", "HDF5 layout to correct.", "--input-format", SPH_APPLY_FORMAT_OPTIONS),
      optionPath("sph_source", "SPH sidecar", "HDF5 sidecar containing SPH/NSPH vectors.", "--sph-source", "openmc_sph.h5", H5, true),
      optionPath("output", "Corrected MGXS HDF5", "Output HDF5 copy with XS divided by NSPH.", "-o", "mg_case/mgxs.h5", H5, true),
      optionPath("summary_json", "Summary JSON", "Optional SPH application summary JSON.", "--summary-json", "sph_apply_summary.json", JSON),
      toggle("force", "Force overwrite", "Allow replacing the corrected HDF5 output.", "--force"),
    ],
    notes: [
      "This is the OpenMC-side iteration step: rerun OpenMC MG with the corrected XS, then recompute the SPH factors.",
      "The output removes active SPH datasets and stores applied_sph provenance so the same factors are not applied twice.",
    ],
  },
  {
    id: "bundle",
    title: "Bundle production artifacts",
    summary: "Build a manifest-backed delivery bundle command.",
    base: ["openmc2donjon", "bundle"],
    fields: [
      optionPath("output_dir", "Bundle directory", "Directory that receives artifacts and manifest.", "--output-dir", "bundle", undefined, true, "directory"),
      optionPath("mgxs", "MGXS HDF5", "MGXS handoff to include.", "--mgxs", "mgxs_library.h5", H5),
      optionPath("mcompo", "MULTICOMPO ASCII", "L_MULTICOMPO ASCII to include.", "--mcompo", "out.mcompo.txt", [".txt", ".mcompo.txt"]),
      optionPath("macrolib", "MACROLIB ASCII", "L_MACROLIB ASCII to include.", "--macrolib", "out.macrolib.txt", [".txt", ".macrolib.txt"]),
      optionPath("run_summary", "Run summary", "One-step conversion summary JSON.", "--run-summary", "run_summary.json", JSON),
      optionPath("check_summary", "Check summary", "Preflight summary JSON.", "--check-summary", "check_summary.json", JSON),
      optionPath("inspect_summary", "Inspect summary", "Inspect summary JSON.", "--inspect-summary", "inspect_summary.json", JSON),
      optionPath("doctor_summary", "Doctor summary", "Doctor summary JSON.", "--doctor-summary", "doctor_summary.json", JSON),
      optionPath("diff_summary", "Diff summary", "Diff summary JSON.", "--diff-summary", "diff_summary.json", JSON),
      text("extra", "Extra artifacts", "Comma-separated LABEL=PATH entries; each becomes one --extra flag.", "--extra", undefined, true),
      text("manifest_name", "Manifest name", "Optional manifest filename.", "--manifest-name"),
      toggle("force", "Force overwrite", "Overwrite bundled files and manifest.", "--force"),
    ],
    notes: ["Bundle before sending a run to another machine or collaborator."],
  },
  {
    id: "validate-bundle",
    title: "Validate a production bundle",
    summary: "Build the command that validates a manifest-backed bundle.",
    base: ["openmc2donjon", "validate-bundle"],
    fields: [
      path("manifest", "Manifest JSON", "Bundle manifest JSON.", "manifest.json", 0, JSON),
      optionPath("summary_json", "Summary JSON", "Optional validation summary JSON.", "--summary-json", "bundle_validation.json", JSON),
      toggle("no_fail", "No fail", "Always exit zero after printing the report.", "--no-fail"),
    ],
    notes: ["Run this after bundle, before sharing the delivery directory."],
  },
  {
    id: "doctor",
    title: "Check local runtime",
    summary: "Build a runtime diagnostics command for package, imports, and console scripts.",
    base: ["openmc2donjon", "doctor"],
    fields: [
      optionPath("recipe", "Recipe", "Optional OpenMC export recipe to dry-run.", "--recipe", "recipe.py", [".py"]),
      optionPath("statepoint", "Statepoint", "Optional OpenMC statepoint path.", "--statepoint", "statepoint.h5", H5),
      toggle("load_statepoint", "Load statepoint", "Load the statepoint during recipe dry-run.", "--load-statepoint"),
      optionPath("summary_json", "Summary JSON", "Optional doctor summary JSON.", "--summary-json", "doctor.json", JSON),
      toggle("no_fail", "No fail", "Always exit zero after printing the report.", "--no-fail"),
    ],
    notes: ["Use this when a collaborator reports that local commands fail to start."],
  },
  {
    id: "serve",
    title: "Start localhost web backend",
    summary: "Build the FastAPI backend command used by the Next.js web UI.",
    base: ["openmc2donjon", "serve"],
    fields: [
      text("host", "Host", "Bind address; empty keeps CLI default.", "--host"),
      text("port", "Port", "Bind port; empty keeps CLI default.", "--port"),
      toggle("mock", "Mock mode", "Serve fixture data instead of real files.", "--mock"),
      text("cors_origin", "Extra CORS origins", "Comma-separated origins; each becomes one --cors-origin flag.", "--cors-origin", undefined, true),
      select("log_level", "Log level", "Explicit diagnostic log level.", "--log-level", [
        { value: "", label: "default" },
        { value: "ERROR", label: "ERROR" },
        { value: "WARNING", label: "WARNING" },
        { value: "INFO", label: "INFO" },
        { value: "DEBUG", label: "DEBUG" },
      ]),
    ],
    notes: ["Keep this backend running while using the localhost web UI."],
  },
];

export function commandBuilderSpec(id: string): CommandBuilderSpec | null {
  return COMMAND_BUILDER_SPECS.find((spec) => spec.id === id) ?? null;
}

export function commandBuilderStage(id: string): CommandBuilderStage {
  if (id === "diff" || id === "compare-writers" || id === "doctor") {
    return {
      label: "Inspect and preflight",
      summary:
        "Diagnostic command: use it before accepting a handoff or when a local environment looks suspicious.",
      reference: "HDF5 / runtime QA",
    };
  }
  if (
    id === "export-volume-flux" ||
    id === "make-sph-update-table" ||
    id === "apply-sph"
  ) {
    return {
      label: "OpenMC-side SPH",
      summary:
        "OpenMC equivalence command: compare CE reference and MG macro flux, then write explicit SPH factors for each output region and energy group.",
      reference: "OpenMC CE reference plus OpenMC MG macro flux on the selected group structure",
    };
  }
  if (
    id === "export-surface-flux" ||
    id === "check-face-flux" ||
    id === "make-low-order-driver" ||
    id === "check-low-order-driver" ||
    id === "make-homogeneous-face-flux"
  ) {
    return {
      label: "ADF/DF equivalence",
      summary:
        "One-shot equivalence command: prepare face-flux or low-order inputs before ADF sidecar generation.",
      reference: "OpenMC reference plus low-order face data",
    };
  }
  if (id === "bundle" || id === "validate-bundle") {
    return {
      label: "Package and archive",
      summary:
        "Delivery command: collect or validate the artifacts that make a production handoff reproducible.",
      reference: "Run directory artifacts",
    };
  }
  if (id === "serve") {
    return {
      label: "Local web service",
      summary: "Operational command: start the localhost API backend used by the web UI.",
      reference: "FastAPI backend",
    };
  }
  return {
    label: "Command-line workflow",
    summary: "Generic command builder: copy the CLI and run it locally.",
    reference: "CLI",
  };
}

export function defaultBuilderValues(spec: CommandBuilderSpec): BuilderValues {
  const values: BuilderValues = {};
  for (const field of spec.fields) {
    values[field.name] =
      field.kind === "toggle" ? Boolean(field.defaultValue) : String(field.defaultValue ?? "");
  }
  return values;
}

export function builderValuesFromQuery(
  spec: CommandBuilderSpec,
  query: BuilderQueryParams,
): BuilderValues {
  const values = defaultBuilderValues(spec);
  for (const field of spec.fields) {
    const raw = query.get(field.name);
    if (raw == null) continue;
    values[field.name] = field.kind === "toggle" ? parseQueryBool(raw) : raw;
  }
  return values;
}

function parseQueryBool(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
}

export function buildCommandCli(spec: CommandBuilderSpec, values: BuilderValues): string {
  const tokens = [...spec.base];
  const positionals = spec.fields
    .filter((field) => field.positional != null)
    .sort((a, b) => Number(a.positional) - Number(b.positional));
  for (const field of positionals) {
    tokens.push(valueOrPlaceholder(field, values[field.name]));
  }
  for (const field of spec.fields) {
    if (!field.flag) continue;
    const raw = values[field.name];
    if (field.kind === "toggle") {
      if (raw === true) tokens.push(field.flag);
      continue;
    }
    const value = stringValue(raw);
    if (field.repeatCsv) {
      for (const item of splitCsv(value)) {
        tokens.push(field.flag, item);
      }
      continue;
    }
    const shouldEmit =
      field.required ||
      value !== "" ||
      (field.includeDefault && stringValue(field.defaultValue) !== "");
    if (!shouldEmit) continue;
    const emitted = value || stringValue(field.defaultValue) || field.placeholder || "";
    if (emitted !== "") tokens.push(field.flag, emitted);
  }
  return tokens.map(shellQuote).join(" ");
}

function path(
  name: string,
  label: string,
  help: string,
  placeholder: string,
  positional: number,
  extensions?: string[],
): BuilderField {
  return {
    name,
    label,
    kind: "path",
    help,
    placeholder,
    positional,
    required: true,
    browse: "file",
    extensions,
  };
}

function optionPath(
  name: string,
  label: string,
  help: string,
  flag: string,
  placeholder: string,
  extensions?: string[],
  required = false,
  browse: BrowseMode = "file",
): BuilderField {
  return {
    name,
    label,
    kind: "path",
    help,
    flag,
    placeholder,
    required,
    browse,
    extensions,
  };
}

function text(
  name: string,
  label: string,
  help: string,
  flag?: string,
  placeholder?: string,
  repeatCsv = false,
  required = false,
): BuilderField {
  return {
    name,
    label,
    kind: "text",
    help,
    flag,
    placeholder,
    repeatCsv,
    required,
  };
}

function toggle(name: string, label: string, help: string, flag: string): BuilderField {
  return {
    name,
    label,
    kind: "toggle",
    help,
    flag,
    defaultValue: false,
  };
}

function select(
  name: string,
  label: string,
  help: string,
  flag: string,
  options: readonly BuilderOption[],
): BuilderField {
  return {
    name,
    label,
    kind: "select",
    help,
    flag,
    options: [...options],
    defaultValue: options[0]?.value ?? "",
  };
}

function valueOrPlaceholder(field: BuilderField, value: string | boolean | undefined): string {
  const stringified = stringValue(value);
  return stringified || field.placeholder || `<${field.name}>`;
}

function stringValue(value: string | boolean | undefined): string {
  if (value == null) return "";
  if (typeof value === "boolean") return value ? "true" : "";
  return value.trim();
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_@%+=:,./<>-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}

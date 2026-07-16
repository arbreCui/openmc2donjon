import {
  COLORSET_DEFINITIONS,
  WITHDRAWN_COLORSET_DIAGNOSTIC,
  type ColorsetDefinition,
  type ColorsetId,
} from "./colorsetWorkflow";
import type {
  ProjectComponentStatus,
  ProjectConsumerStatus,
  ProjectManifest,
  ProjectStatus,
  JsonValue,
} from "./api";

export const PROJECT_TEMPLATE = "irena30-colorset-core";
export const PROJECT_ROOT_STORAGE_KEY = "openmc2donjon.project-root";

export type ProjectReadinessTone = "ready" | "hold" | "rejected" | "neutral";

export interface ProjectReadinessPresentation {
  handoffValue: string;
  handoffLabel: string;
  handoffTone: ProjectReadinessTone;
  physicsValue: string;
  physicsLabel: string;
  physicsTone: ProjectReadinessTone;
  consumerValue: string;
  consumerTone: ProjectReadinessTone;
  explanation: string | null;
}

export function projectReadinessPresentation(
  status: Pick<
    ProjectStatus,
    | "accepted_outputs"
    | "required_components"
    | "handoffs_ready"
    | "physics_accepted"
    | "ready_for_consumer"
    | "acceptance"
    | "consumer"
  >,
): ProjectReadinessPresentation {
  const acceptanceDeclared = status.acceptance.declared;
  const acceptanceState = status.acceptance.state;
  const acceptanceBasis = status.acceptance.basis ?? (
    acceptanceDeclared ? "project-declared" : "not-required"
  );
  const acceptanceNotRequired = acceptanceBasis === "not-required";
  const machineValidation = status.acceptance.machine_validation;
  const explanation = acceptanceState === "rejected"
    ? acceptanceBasis === "machine-verified"
      ? "Machine-verified acceptance is REJECTED. The bound validator did not pass every strict physics check, so archived handoffs cannot release the consumer."
      : "Project-declared acceptance is explicitly REJECTED. Archived handoffs remain available for diagnosis, but they cannot release the consumer."
    : status.handoffs_ready
    ? acceptanceNotRequired
      ? "This handoff-only project has no physics acceptance gate. The contract-validated handoffs may be delivered to the declared consumer; READY does not claim physics equivalence or reactor acceptance."
      : acceptanceDeclared && acceptanceState !== "accepted"
      ? acceptanceBasis === "machine-verified"
        ? `Required handoffs are ready, but the consumer remains on HOLD until both the project ledger and its machine validator pass${machineValidation?.state ? ` (validator: ${machineValidation.state})` : ""}.`
        : "Required handoffs are ready, but the consumer remains on HOLD until the project-declared decision file, evidence hashes, and criteria validate with status=accepted. This is external model acceptance, not a generic physics verdict from Converter."
      : acceptanceBasis === "machine-verified"
          ? "The project ledger and its file-backed machine validator both passed against the live hash-linked evidence."
          : "The model owner accepted the project-declared external criteria. This is not a machine-verified generic physics verdict from Converter."
    : acceptanceNotRequired
      ? "Physics acceptance is not required by this handoff-only project. Delivery remains on HOLD only until every required input, output, and receipt passes its handoff contract."
      : acceptanceBasis === "machine-verified"
        ? "The consumer remains on HOLD: first complete every required handoff contract, then pass the project ledger and its bound machine validator against the live physics evidence."
        : "The consumer remains on HOLD: first complete every required handoff contract, then satisfy the project-declared external acceptance decision and evidence hashes.";
  return {
    handoffValue: `${status.accepted_outputs}/${status.required_components || "–"}`,
    handoffLabel: status.handoffs_ready ? "handoffs ready" : "handoffs pending",
    handoffTone: status.handoffs_ready ? "ready" : "hold",
    physicsValue:
      acceptanceNotRequired
        ? "N/A"
        : acceptanceState === "accepted"
        ? "READY"
        : acceptanceState === "rejected"
          ? "REJECTED"
          : "HOLD",
    physicsLabel:
      acceptanceNotRequired
        ? "physics gate not required"
        : acceptanceBasis === "machine-verified"
        ? "machine-verified acceptance"
        : acceptanceBasis === "project-declared"
          ? "project-declared acceptance"
          : "acceptance",
    physicsTone:
      acceptanceNotRequired
        ? "neutral"
        : acceptanceState === "accepted"
        ? "ready"
        : acceptanceState === "rejected"
          ? "rejected"
          : "hold",
    consumerValue: status.ready_for_consumer ? "READY" : "HOLD",
    consumerTone: status.ready_for_consumer ? "ready" : "hold",
    explanation,
  };
}

export function isWithdrawnDiagnosticProject(
  project: Pick<ProjectStatus, "workflow" | "template">,
): boolean {
  return (
    project.workflow === "withdrawn-diagnostic" ||
    project.template === PROJECT_TEMPLATE
  );
}

export function canEditProjectManifest(
  project: Pick<ProjectStatus, "configured" | "workflow" | "template">,
): boolean {
  return project.configured && !isWithdrawnDiagnosticProject(project);
}

export function isPhysicalSphContract(
  contract: ProjectComponentStatus["contract"],
): boolean {
  return contract !== "converter-hdf5";
}

export function isNativeSphContract(
  contract: ProjectComponentStatus["contract"],
): boolean {
  return contract === "native-sph";
}

export function isIrenaColorsetSphContract(
  contract: ProjectComponentStatus["contract"],
): boolean {
  return (
    contract === "irena30-colorset-sph" ||
    contract === "physical-colorset-sph"
  );
}

export interface ColorsetProjectPaths {
  directory: string;
  mgxs: string;
  ceFlux: string;
  mgFlux: string;
  sphSidecar: string;
  sphApplied: string;
  cpo: string;
  cpoReceipt: string;
}

export function normalizeProjectRoot(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  if (trimmed === "/") return trimmed;
  return trimmed.replace(/\/+$/, "");
}

export type ProjectManifestDraftResult =
  | { ok: true; manifest: ProjectManifest }
  | { ok: false; message: string };

export function formatProjectManifest(manifest: ProjectManifest): string {
  return `${JSON.stringify(manifest, null, 2)}\n`;
}

export function parseProjectManifestDraft(
  draft: string,
): ProjectManifestDraftResult {
  if (!draft.trim()) {
    return { ok: false, message: "Project manifest JSON is empty." };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(draft);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown parse error";
    return { ok: false, message: `Invalid JSON: ${detail}` };
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {
      ok: false,
      message: "Project manifest must be a JSON object, not an array or scalar.",
    };
  }
  return { ok: true, manifest: parsed as ProjectManifest };
}

export interface ProjectComponentDraft {
  id: string;
  label: string;
  role: string;
  input: string;
  output: string;
  format: "multicompo" | "macrolib";
  contract: "converter-hdf5" | "physical-sph" | "native-sph";
  writerBackend: "ascii" | "pygan";
  required: boolean;
}

export type AddProjectComponentResult =
  | { ok: true; manifest: ProjectManifest }
  | { ok: false; message: string };

/** Add a normal Converter component without asking users to edit raw JSON. */
export function addProjectComponentToManifest(
  manifest: ProjectManifest,
  draft: ProjectComponentDraft,
): AddProjectComponentResult {
  const id = draft.id.trim();
  const label = draft.label.trim();
  const input = draft.input.trim();
  const output = draft.output.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(id)) {
    return {
      ok: false,
      message: "Component ID must use letters, numbers, dot, underscore, or dash.",
    };
  }
  if (!label) return { ok: false, message: "Component label is required." };
  for (const [field, value] of [["input", input], ["output", output]] as const) {
    if (!value || value.startsWith("/") || value.split("/").includes("..")) {
      return {
        ok: false,
        message: `Component ${field} must be a project-relative path.`,
      };
    }
  }
  const components = Array.isArray(manifest.components)
    ? manifest.components.filter(isJsonObject)
    : [];
  if (components.some((item) => item.id === id)) {
    return { ok: false, message: `Component ID ${id} already exists.` };
  }
  const outputDirectory = output.includes("/")
    ? output.slice(0, output.lastIndexOf("/") + 1)
    : "";
  const referenceMacrolib = `${outputDirectory}${id}.reference.macrolib.txt`;
  const nativeSphArtifacts =
    draft.contract === "native-sph"
      ? {
          receipt: `${referenceMacrolib}.convert.json`,
          physics_summary: `${outputDirectory}${id}.physics-summary.json`,
          evidence: [
            {
              id: "reference",
              label: "Converter reference MACROLIB",
              path: referenceMacrolib,
            },
          ],
        }
      : { receipt: `${output}.convert.json` };
  const component = {
    id,
    label,
    role: draft.role.trim() || "User-defined homogenized component or model region",
    required: draft.required,
    input,
    output,
    format: draft.format,
    contract: draft.contract,
    conversion: { writer_backend: draft.writerBackend },
    ...nativeSphArtifacts,
  };
  return {
    ok: true,
    manifest: {
      ...manifest,
      components: [...components, component] as ProjectManifest["components"],
    },
  };
}

export function addProjectEvidenceToManifest(
  manifest: ProjectManifest,
  projectRoot: string,
  componentId: string,
  evidencePath: string,
  label: string,
): AddProjectComponentResult {
  const root = normalizeProjectRoot(projectRoot);
  const absolute = evidencePath.trim();
  const relative = absolute.startsWith(`${root}/`)
    ? absolute.slice(root.length + 1)
    : absolute;
  if (
    !relative ||
    relative.startsWith("/") ||
    relative.split("/").includes("..")
  ) {
    return {
      ok: false,
      message: "Evidence must be a file inside the project root.",
    };
  }
  const clone = JSON.parse(JSON.stringify(manifest)) as ProjectManifest;
  if (!Array.isArray(clone.components)) {
    return { ok: false, message: "Project manifest has no component array." };
  }
  const component = clone.components.find(
    (item) =>
      item !== null &&
      typeof item === "object" &&
      !Array.isArray(item) &&
      item.id === componentId,
  );
  if (component === null || typeof component !== "object" || Array.isArray(component)) {
    return { ok: false, message: `Project component ${componentId} was not found.` };
  }
  const existing = Array.isArray(component.evidence) ? component.evidence : [];
  if (
    existing.some(
      (item) =>
        item !== null &&
        typeof item === "object" &&
        !Array.isArray(item) &&
        item.path === relative,
    )
  ) {
    return { ok: false, message: "This evidence path is already declared." };
  }
  const baseId = (label.trim() || "consumer-result")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "consumer-result";
  component.evidence = [
    ...existing,
    {
      id: `${baseId}-${existing.length + 1}`,
      label: label.trim() || "Consumer diagnostic result",
      path: relative,
    },
  ];
  return { ok: true, manifest: clone };
}

export function projectPath(root: string, ...parts: string[]): string {
  const normalized = normalizeProjectRoot(root);
  if (!normalized) return "";
  const suffix = parts.map((part) => part.replace(/^\/+|\/+$/g, "")).join("/");
  return normalized === "/" ? `/${suffix}` : `${normalized}/${suffix}`;
}

export function colorsetProjectPaths(
  root: string,
  colorset: ColorsetDefinition | ColorsetId,
): ColorsetProjectPaths {
  const definition =
    typeof colorset === "string"
      ? COLORSET_DEFINITIONS.find((item) => item.id === colorset) ?? COLORSET_DEFINITIONS[0]
      : colorset;
  const directory = projectPath(root, "colorsets", definition.id);
  const cpo = projectPath(root, "cpo", definition.outputName);
  return {
    directory,
    mgxs: projectPath(directory, "mgxs_library.h5"),
    ceFlux: projectPath(directory, "openmc_ce_flux.h5"),
    mgFlux: projectPath(directory, "openmc_mg_flux.h5"),
    sphSidecar: projectPath(directory, "openmc_sph.h5"),
    sphApplied: projectPath(directory, "mgxs_sph_applied.h5"),
    cpo,
    cpoReceipt: `${cpo}.convert.json`,
  };
}

export function projectRootFromSearchParams(
  searchParams: Pick<URLSearchParams, "get">,
): string {
  return normalizeProjectRoot(searchParams.get("project"));
}

export function withProjectContext(
  href: string,
  projectRoot: string,
  colorsetId?: ColorsetId,
): string {
  const root = normalizeProjectRoot(projectRoot);
  if (!root && !colorsetId) return href;
  const [beforeHash, hash] = href.split("#", 2);
  const [pathname, query = ""] = beforeHash.split("?", 2);
  const params = new URLSearchParams(query);
  if (root) params.set("project", root);
  if (colorsetId) {
    params.set("colorset", colorsetId);
    params.set("production", "0");
    params.set("diagnostic", WITHDRAWN_COLORSET_DIAGNOSTIC);
  }
  const next = `${pathname}${params.size ? `?${params.toString()}` : ""}`;
  return hash === undefined ? next : `${next}#${hash}`;
}

export interface ProjectComponentRouteContext {
  projectRoot: string;
  componentId?: string | null;
  contract?: ProjectComponentStatus["contract"] | string | null;
}

/**
 * Carry the manifest identity through a cross-page workflow link.  Artifact
 * paths can change while OpenMC is preparing a handoff, but project,
 * component, and contract identify which manifest row owns that artifact.
 */
export function withProjectComponentContext(
  href: string,
  { projectRoot, componentId, contract }: ProjectComponentRouteContext,
): string {
  const contextual = withProjectContext(href, projectRoot);
  if (!componentId && !contract) return contextual;
  const [beforeHash, hash] = contextual.split("#", 2);
  const [pathname, query = ""] = beforeHash.split("?", 2);
  const params = new URLSearchParams(query);
  if (componentId) params.set("component", componentId);
  if (contract) params.set("contract", contract);
  const next = `${pathname}${params.size ? `?${params.toString()}` : ""}`;
  return hash === undefined ? next : `${next}#${hash}`;
}

export function projectCoreHref(projectRoot: string): string {
  return withProjectContext("/donjon", projectRoot);
}

export function projectAcceptanceHref(projectRoot: string): string {
  return withProjectContext("/inspect?mode=acceptance", projectRoot);
}

export function projectComponentConvertHref(
  projectRoot: string,
  component: ProjectComponentStatus,
): string {
  const withdrawnColorset = isIrenaColorsetSphContract(component.contract);
  const output = projectComponentConverterOutputPath(component);
  const conversion = component.conversion;
  const params = new URLSearchParams({
    component: component.id,
    input: component.paths.input,
    output,
    format: component.format,
    check: "1",
    production:
      withdrawnColorset || conversion?.h_factor_default != null ? "0" : "1",
    contract: component.contract,
  });
  if (withdrawnColorset) {
    params.set("colorset", component.id);
    params.set("diagnostic", WITHDRAWN_COLORSET_DIAGNOSTIC);
  }
  if (component.identity) params.set("comment", component.identity);
  if (conversion) {
    params.set("writer_backend", conversion.writer_backend);
    if (conversion.root_name && conversion.root_name !== "CPO") {
      params.set("root_name", conversion.root_name);
    }
    if (conversion.comment) params.set("comment", conversion.comment);
    if (conversion.burnup != null) params.set("burnup", String(conversion.burnup));
    if (conversion.h_factor_default != null) {
      params.set("h_factor_default", String(conversion.h_factor_default));
    }
    for (const mixture of conversion.mixtures ?? []) params.append("mixture", mixture);
  }
  if (projectRoot) params.set("project", normalizeProjectRoot(projectRoot));
  return `/convert?${params.toString()}#convert-component`;
}

export function projectComponentPrepareHref(
  projectRoot: string,
  component: ProjectComponentStatus,
): string {
  // OpenMC is only an optional way to create a missing Converter input. Keep
  // this route on the direct, two-step MGXS export path: selecting a physical
  // SPH contract must not silently opt the user into OpenMC MG-side SPH.
  const withdrawnColorset = isIrenaColorsetSphContract(component.contract);
  const params = new URLSearchParams({
    workflow: "two-step",
    equivalence: "direct",
    format: component.format,
    production: withdrawnColorset ? "0" : "1",
    component: component.id,
    contract: component.contract,
    input: component.paths.input,
    output: projectComponentConverterOutputPath(component),
  });
  if (withdrawnColorset) {
    params.set("colorset", component.id);
    params.set("diagnostic", WITHDRAWN_COLORSET_DIAGNOSTIC);
  }
  if (projectRoot) params.set("project", normalizeProjectRoot(projectRoot));
  return `/openmc?${params.toString()}`;
}

export function projectComponentConverterOutputPath(
  component: ProjectComponentStatus,
): string {
  return isNativeSphContract(component.contract)
    ? nativeSphConverterReferencePath(component) ?? component.paths.output
    : component.paths.output;
}

export function nativeSphConverterReferencePath(
  component: ProjectComponentStatus,
): string | null {
  if (!isNativeSphContract(component.contract)) return null;
  const reference = component.paths.evidence.find((item) => {
    const id = item.id.trim().toLowerCase();
    const label = item.label.trim().toLowerCase();
    return id === "reference" || label.includes("converter reference");
  });
  return reference?.path ?? null;
}

export interface ProjectNativeSphValidationInputs {
  reference_h5: string;
  reference_macrolib: string;
  sph_macrolib: string;
  verify_macrolib: string;
  result_listing: string;
  energy_coverage: string;
  converter_receipt: string;
  summary_json: string;
}

/**
 * Bind the generic validator fields to manifest-owned component paths. Evidence
 * roles are declared by stable ids; labels are only a compatibility fallback.
 */
export function projectNativeSphValidationInputs(
  component: ProjectComponentStatus,
): ProjectNativeSphValidationInputs {
  return {
    reference_h5: component.paths.input ?? "",
    reference_macrolib: projectNativeSphEvidencePath(component, {
      ids: ["reference", "reference-macrolib", "converter-reference"],
      labelTerms: ["converter reference", "reference macrolib"],
    }),
    sph_macrolib: component.paths.output ?? "",
    verify_macrolib: projectNativeSphEvidencePath(component, {
      ids: ["verification", "verify-macrolib", "verification-macrolib"],
      labelTerms: ["verification macrolib"],
    }),
    result_listing: projectNativeSphEvidencePath(component, {
      ids: ["result", "result-listing", "native-sph-result"],
      labelTerms: ["result listing", "transport listing", "native sph and final"],
    }),
    energy_coverage: projectNativeSphEvidencePath(component, {
      ids: ["coverage", "energy-coverage"],
      labelTerms: ["energy coverage"],
    }),
    converter_receipt: component.paths.receipt ?? "",
    summary_json: component.paths.physics_summary ?? "",
  };
}

function projectNativeSphEvidencePath(
  component: ProjectComponentStatus,
  role: { ids: readonly string[]; labelTerms: readonly string[] },
): string {
  const ids = new Set(role.ids);
  const exact = component.paths.evidence.find((item) =>
    ids.has(item.id.trim().toLowerCase()),
  );
  if (exact) return exact.path;
  const compatible = component.paths.evidence.find((item) => {
    const label = item.label.trim().toLowerCase();
    return role.labelTerms.some((term) => label.includes(term));
  });
  return compatible?.path ?? "";
}

export function projectComponentEquivalenceHref(
  projectRoot: string,
  component: ProjectComponentStatus,
): string {
  if (!isPhysicalSphContract(component.contract)) {
    return projectComponentConvertHref(projectRoot, component);
  }
  const params = new URLSearchParams({
    component: component.id,
    contract: component.contract,
  });
  if (isNativeSphContract(component.contract)) {
    const validation = projectNativeSphValidationInputs(component);
    for (const [key, value] of Object.entries(validation)) {
      if (value.trim()) params.set(key, value);
    }
    if (component.native_sph) {
      params.set("deck", component.native_sph.deck_path);
      params.set("working_directory", component.native_sph.working_directory);
      params.set("native_sph_source", "project-manifest");
    }
  }
  if (!isNativeSphContract(component.contract)) {
    params.set("kind", "openmc-sph-sidecar");
  }
  if (isIrenaColorsetSphContract(component.contract)) {
    params.set("colorset", component.id);
    params.set("diagnostic", WITHDRAWN_COLORSET_DIAGNOSTIC);
  }
  if (projectRoot) params.set("project", normalizeProjectRoot(projectRoot));
  return `/equivalence?${params.toString()}`;
}

export function projectNativeSphEntryHrefs(
  projectRoot: string,
  components: readonly ProjectComponentStatus[],
  preferredComponentId = "fullcore",
): {
  component: ProjectComponentStatus | null;
  converterHref: string | null;
  equivalenceHref: string;
} {
  const component =
    components.find(
      (item) =>
        item.id === preferredComponentId && isNativeSphContract(item.contract),
    ) ?? components.find((item) => isNativeSphContract(item.contract)) ?? null;
  if (component) {
    return {
      component,
      converterHref: projectComponentConvertHref(projectRoot, component),
      equivalenceHref: projectComponentEquivalenceHref(projectRoot, component),
    };
  }

  const params = new URLSearchParams({ contract: "native-sph" });
  const root = normalizeProjectRoot(projectRoot);
  if (root) {
    params.set("project", root);
    params.set("component", preferredComponentId);
  }
  return {
    component: null,
    converterHref: null,
    equivalenceHref: `/equivalence?${params.toString()}`,
  };
}

export function projectEquivalenceActionLabel(
  contract: ProjectComponentStatus["contract"],
): "Native SPH" | "Physical SPH" {
  return isNativeSphContract(contract) ? "Native SPH" : "Physical SPH";
}

export function projectConsumerActionLabel(
  ready: boolean,
  consumerLabel: string,
): string {
  return ready ? `Open ${consumerLabel} →` : "Review HOLD consumer →";
}

export function projectConsumerHref(
  projectRoot: string,
  consumer: ProjectConsumerStatus,
  component?: ProjectComponentStatus | string | null,
): string {
  const href = consumer.href?.trim() || "/donjon";
  const componentId = typeof component === "string" ? component : component?.id;
  const contextual = withProjectComponentContext(href, {
    projectRoot,
    componentId,
  });
  if (!component || typeof component === "string") return contextual;
  const [beforeHash, hash] = contextual.split("#", 2);
  const [pathname, query = ""] = beforeHash.split("?", 2);
  const params = new URLSearchParams(query);
  params.set("ascii", component.paths.output);
  params.set("output", component.paths.output);
  params.set("format", component.format);
  params.set("receipt", component.paths.receipt);
  if (component.paths.physics_summary) {
    params.set("physics_summary", component.paths.physics_summary);
  }
  params.set("input_h5", component.paths.input);
  const conversion = component.conversion;
  if (conversion) {
    params.set("root_name", conversion.root_name || "CPO");
    if (conversion.comment) params.set("comment", conversion.comment);
    if (conversion.burnup != null) params.set("burnup", String(conversion.burnup));
    if (conversion.h_factor_default != null) {
      params.set("h_factor_default", String(conversion.h_factor_default));
    }
    for (const mixture of conversion.mixtures ?? []) params.append("mixture", mixture);
  }
  const next = `${pathname}?${params.toString()}`;
  return hash === undefined ? next : `${next}#${hash}`;
}

export interface ProjectPostConvertDestination {
  href: string;
  label: string;
  title: string;
  body: string;
}

/**
 * A project-owned conversion returns to the declared consumer.  If its
 * manifest is not available yet, returning to the project is safer than
 * silently switching to the standalone single-object DONJON guide.
 */
export function projectPostConvertDestination(
  projectRoot: string,
  componentId: string | null,
  project: (
    Pick<ProjectStatus, "configured" | "consumer" | "acceptance"> &
    Partial<
      Pick<
        ProjectStatus,
        "components" | "ready_for_consumer" | "handoffs_ready"
      >
    >
  ) | null,
): ProjectPostConvertDestination | null {
  const root = normalizeProjectRoot(projectRoot);
  if (!root) return null;
  if (project?.configured) {
    const components = project.components ?? [];
    const pending = components.find(
      (component) =>
        component.required &&
        (component.handoff.state !== "accepted" ||
          component.output.state !== "accepted"),
    );
    if (project.ready_for_consumer === false) {
      return {
        href: withProjectComponentContext("/projects", {
          projectRoot: root,
          componentId: pending?.id ?? componentId,
        }),
        label: pending ? `Continue ${pending.label}` : "Review Project HOLD",
        title: pending
          ? `Continue the next pending component: ${pending.label}`
          : "Return to the project gate",
        body: pending
          ? "This component conversion is complete, but the project still has a required handoff on HOLD. Finish the next manifest row before opening the downstream consumer."
          : project.handoffs_ready
            ? "All component handoffs are present, but the project physics-acceptance gate remains on HOLD. Review the project evidence before opening its consumer."
            : "The project is still on HOLD. Return to its component and evidence table before choosing a downstream consumer.",
      };
    }
    const handoffOnly = project.acceptance.basis === "not-required";
    const selected = components.find((item) => item.id === componentId);
    return {
      href: projectConsumerHref(root, project.consumer, selected ?? componentId),
      label: `Open ${project.consumer.label}`,
      title: `Continue to ${project.consumer.label}`,
      body: handoffOnly
        ? componentId
          ? `Return component ${componentId} to the consumer declared by this handoff-only project. Converter completion establishes delivery readiness, not physics acceptance.`
          : "Continue through the consumer declared by this handoff-only project. Converter completion establishes delivery readiness, not physics acceptance."
        : componentId
          ? `Return component ${componentId} to the consumer declared by this project manifest. Converter completion does not bypass the project physics-acceptance gate.`
          : "Continue through the consumer declared by this project manifest. Converter completion does not bypass the project physics-acceptance gate.",
    };
  }
  return {
    href: withProjectComponentContext("/projects", {
      projectRoot: root,
      componentId,
    }),
    label: "Return to Project",
    title: "Return this handoff to Project",
    body: "The project context is preserved, but its declared consumer is not loaded. Reopen the manifest before choosing a downstream model.",
  };
}

function isJsonObject(value: JsonValue): value is { [key: string]: JsonValue } {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

import { describe, expect, it } from "vitest";
import {
  addProjectComponentToManifest,
  addProjectEvidenceToManifest,
  canEditProjectManifest,
  colorsetProjectPaths,
  formatProjectManifest,
  isIrenaColorsetSphContract,
  isNativeSphContract,
  isPhysicalSphContract,
  isWithdrawnDiagnosticProject,
  normalizeProjectRoot,
  parseProjectManifestDraft,
  projectAcceptanceHref,
  projectComponentConvertHref,
  projectComponentEquivalenceHref,
  projectComponentPrepareHref,
  projectConsumerActionLabel,
  projectConsumerHref,
  projectCoreHref,
  projectEquivalenceActionLabel,
  projectNativeSphEntryHrefs,
  projectNativeSphValidationInputs,
  projectPath,
  projectPostConvertDestination,
  projectReadinessPresentation,
  withProjectComponentContext,
  withProjectContext,
} from "./projectWorkspace";
import type { ProjectComponentStatus, ProjectStatus } from "./api";

describe("projectWorkspace", () => {
  it("adds a structured component while keeping raw JSON optional", () => {
    const manifest = {
      schema: "openmc2donjon.project.v1",
      name: "General model",
      components: [
        { id: "fuel", label: "Fuel", input: "fuel.h5", output: "fuel.txt" },
      ],
    };
    const added = addProjectComponentToManifest(manifest, {
      id: "reflector",
      label: "Reflector",
      role: "Radial reflector",
      input: "components/reflector.h5",
      output: "outputs/reflector.macrolib.txt",
      format: "macrolib",
      contract: "converter-hdf5",
      writerBackend: "pygan",
      required: true,
    });
    expect(added.ok).toBe(true);
    if (added.ok) {
      expect(added.manifest.components).toHaveLength(2);
      expect(added.manifest.components).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            id: "reflector",
            conversion: { writer_backend: "pygan" },
          }),
        ]),
      );
    }
    expect(
      addProjectComponentToManifest(manifest, {
        id: "fuel",
        label: "Duplicate",
        role: "",
        input: "x.h5",
        output: "x.txt",
        format: "multicompo",
        contract: "converter-hdf5",
        writerBackend: "ascii",
        required: true,
      }),
    ).toMatchObject({ ok: false });
  });

  it("creates distinct Converter and native-SPH evidence paths", () => {
    const added = addProjectComponentToManifest(
      {
        schema: "openmc2donjon.project.v1",
        name: "Native SPH model",
        components: [],
      },
      {
        id: "assembly-a",
        label: "Assembly A",
        role: "Homogenized assembly",
        input: "components/assembly-a/reference.h5",
        output: "outputs/assembly-a.sph.macrolib.txt",
        format: "macrolib",
        contract: "native-sph",
        writerBackend: "ascii",
        required: true,
      },
    );

    expect(added.ok).toBe(true);
    if (added.ok) {
      expect(added.manifest.components).toEqual([
        expect.objectContaining({
          receipt: "outputs/assembly-a.reference.macrolib.txt.convert.json",
          physics_summary: "outputs/assembly-a.physics-summary.json",
          evidence: [
            {
              id: "reference",
              label: "Converter reference MACROLIB",
              path: "outputs/assembly-a.reference.macrolib.txt",
            },
          ],
        }),
      ]);
    }
  });

  it("adds only project-confined consumer evidence", () => {
    const manifest = {
      schema: "openmc2donjon.project.v1",
      name: "General model",
      components: [
        { id: "fuel", label: "Fuel", input: "fuel.h5", output: "fuel.txt" },
      ],
    };
    const added = addProjectEvidenceToManifest(
      manifest,
      "/runs/a",
      "fuel",
      "/runs/a/core/jobs/one/result.txt",
      "DONJON ingest result",
    );
    expect(added.ok).toBe(true);
    if (added.ok) {
      expect(added.manifest.components).toEqual([
        expect.objectContaining({
          evidence: [
            expect.objectContaining({ path: "core/jobs/one/result.txt" }),
          ],
        }),
      ]);
    }
    expect(
      addProjectEvidenceToManifest(
        manifest,
        "/runs/a",
        "fuel",
        "/outside/result.txt",
        "Outside",
      ),
    ).toMatchObject({ ok: false });
  });

  it("formats and parses a generic project manifest without model assumptions", () => {
    const manifest = {
      schema: "openmc2donjon.project.v1",
      name: "Two unrelated components",
      components: [
        { id: "fuel", label: "Fuel", input: "fuel.h5", output: "fuel.txt" },
        { id: "shield", label: "Shield", input: "shield.h5", output: "shield.txt" },
      ],
    };
    const formatted = formatProjectManifest(manifest);

    expect(formatted.endsWith("\n")).toBe(true);
    expect(formatted).toContain('\n  "components": [');
    expect(parseProjectManifestDraft(formatted)).toEqual({
      ok: true,
      manifest,
    });
  });

  it("reports local manifest JSON errors before a save request", () => {
    expect(parseProjectManifestDraft("  ")).toEqual({
      ok: false,
      message: "Project manifest JSON is empty.",
    });
    expect(parseProjectManifestDraft("[1, 2]")).toEqual({
      ok: false,
      message: "Project manifest must be a JSON object, not an array or scalar.",
    });
    const malformed = parseProjectManifestDraft('{"components": [}');
    expect(malformed.ok).toBe(false);
    if (!malformed.ok) expect(malformed.message).toContain("Invalid JSON:");
  });

  it("offers advanced manifest editing only for configured live projects", () => {
    expect(
      canEditProjectManifest({
        configured: true,
        workflow: "component-library",
        template: null,
      }),
    ).toBe(true);
    expect(
      canEditProjectManifest({
        configured: false,
        workflow: null,
        template: null,
      }),
    ).toBe(false);
    expect(
      canEditProjectManifest({
        configured: true,
        workflow: "withdrawn-diagnostic",
        template: null,
      }),
    ).toBe(false);
  });

  it("derives the stable colorset artifact layout", () => {
    expect(colorsetProjectPaths("/runs/irena/", "csd_int")).toEqual({
      directory: "/runs/irena/colorsets/csd_int",
      mgxs: "/runs/irena/colorsets/csd_int/mgxs_library.h5",
      ceFlux: "/runs/irena/colorsets/csd_int/openmc_ce_flux.h5",
      mgFlux: "/runs/irena/colorsets/csd_int/openmc_mg_flux.h5",
      sphSidecar: "/runs/irena/colorsets/csd_int/openmc_sph.h5",
      sphApplied: "/runs/irena/colorsets/csd_int/mgxs_sph_applied.h5",
      cpo: "/runs/irena/cpo/irena30_csd.mcompo.txt",
      cpoReceipt: "/runs/irena/cpo/irena30_csd.mcompo.txt.convert.json",
    });
  });

  it("normalizes roots without damaging the filesystem root", () => {
    expect(normalizeProjectRoot(" /runs/irena/// ")).toBe("/runs/irena");
    expect(normalizeProjectRoot("/")).toBe("/");
    expect(projectPath("/", "colorsets", "int_ext")).toBe("/colorsets/int_ext");
  });

  it("preserves hashes while adding shareable project context", () => {
    expect(withProjectContext("/convert?production=1#convert-component", "/runs/a", "pnl_ext"))
      .toBe("/convert?production=0&project=%2Fruns%2Fa&colorset=pnl_ext&diagnostic=withdrawn-five-colorset#convert-component");
    expect(projectCoreHref("/runs/a")).toContain("project=%2Fruns%2Fa");
    expect(projectAcceptanceHref("/runs/a")).toBe(
      "/inspect?mode=acceptance&project=%2Fruns%2Fa",
    );
    expect(
      withProjectComponentContext("/convert?check=1#convert-component", {
        projectRoot: "/runs/a",
        componentId: "assembly-a",
        contract: "native-sph",
      }),
    ).toBe(
      "/convert?check=1&project=%2Fruns%2Fa&component=assembly-a&contract=native-sph#convert-component",
    );
  });

  it("routes generic physical SPH without inventing a colorset topology", () => {
    const component = {
      id: "assembly-a",
      contract: "physical-sph",
      format: "macrolib",
      paths: {
        input: "/runs/a/components/assembly-a/mgxs.h5",
        output: "/runs/a/outputs/assembly-a.macrolib.txt",
        evidence: [],
      },
    } as unknown as ProjectComponentStatus;

    expect(isPhysicalSphContract(component.contract)).toBe(true);
    expect(isIrenaColorsetSphContract(component.contract)).toBe(false);
    expect(projectComponentPrepareHref("/runs/a", component)).toContain(
      "contract=physical-sph",
    );
    expect(projectComponentPrepareHref("/runs/a", component)).not.toContain(
      "colorset=",
    );
    expect(projectComponentPrepareHref("/runs/a", component)).toContain(
      "equivalence=direct",
    );
    expect(projectComponentPrepareHref("/runs/a", component)).not.toContain(
      "equivalence=sph",
    );
    expect(
      new URL(
        projectComponentPrepareHref("/runs/a", component),
        "http://localhost",
      ).searchParams.get("input"),
    ).toBe("/runs/a/components/assembly-a/mgxs.h5");
    expect(
      new URL(
        projectComponentPrepareHref("/runs/a", component),
        "http://localhost",
      ).searchParams.get("output"),
    ).toBe("/runs/a/outputs/assembly-a.macrolib.txt");
    expect(projectComponentEquivalenceHref("/runs/a", component)).not.toContain(
      "colorset=",
    );
    expect(projectComponentEquivalenceHref("/runs/a", component)).toContain(
      "kind=openmc-sph-sidecar",
    );
    expect(projectEquivalenceActionLabel(component.contract)).toBe("Physical SPH");
  });

  it("keeps the archived IRENA colorset project diagnostic-only", () => {
    const component = {
      id: "csd_int",
      contract: "irena30-colorset-sph",
      format: "multicompo",
      paths: {
        input: "/runs/irena/colorsets/csd_int/mgxs_sph_applied.h5",
        output: "/runs/irena/cpo/irena30_csd.mcompo.txt",
        evidence: [],
      },
    } as unknown as ProjectComponentStatus;

    for (const href of [
      projectComponentPrepareHref("/runs/irena", component),
      projectComponentConvertHref("/runs/irena", component),
    ]) {
      const url = new URL(href, "http://localhost");
      expect(url.searchParams.get("production")).toBe("0");
      expect(url.searchParams.get("colorset")).toBe("csd_int");
      expect(url.searchParams.get("diagnostic")).toBe(
        "withdrawn-five-colorset",
      );
      expect(href).not.toContain("production=1");
    }

    const equivalence = new URL(
      projectComponentEquivalenceHref("/runs/irena", component),
      "http://localhost",
    );
    expect(equivalence.searchParams.get("diagnostic")).toBe(
      "withdrawn-five-colorset",
    );
  });

  it("lets project-level withdrawal override a native-SPH component contract", () => {
    expect(
      isWithdrawnDiagnosticProject({
        workflow: "withdrawn-diagnostic",
        template: null,
      }),
    ).toBe(true);
    expect(
      isWithdrawnDiagnosticProject({
        workflow: "project",
        template: "irena30-colorset-core",
      }),
    ).toBe(true);
    expect(
      isWithdrawnDiagnosticProject({
        workflow: "native-sph",
        template: "irena30_fullcore",
      }),
    ).toBe(false);
  });

  it("routes native SPH through Converter before the separate physical-equivalence step", () => {
    const component = {
      id: "shield",
      contract: "native-sph",
      format: "macrolib",
      identity: "shield-1",
      paths: {
        input: "/runs/a/components/shield/mgxs.h5",
        output: "/runs/a/outputs/shield.sph.macrolib.txt",
        receipt: "/runs/a/outputs/shield.reference.macrolib.txt.convert.json",
        physics_summary: "/runs/a/outputs/shield.physics-summary.json",
        evidence: [
          {
            id: "reference",
            label: "Converter reference",
            path: "/runs/a/outputs/shield.reference.macrolib.txt",
          },
          {
            id: "verification",
            label: "Verification MACROLIB",
            path: "/runs/a/outputs/shield.verify.macrolib.txt",
          },
          {
            id: "result",
            label: "Native SPH result listing",
            path: "/runs/a/diagnostics/shield.result",
          },
          {
            id: "coverage",
            label: "Energy coverage",
            path: "/runs/a/diagnostics/energy-coverage.json",
          },
        ],
      },
      native_sph: {
        deck_path: "/runs/a/native-sph/shield/native_sph.x2m",
        working_directory: "/runs/a/native-sph/shield",
      },
    } as unknown as ProjectComponentStatus;

    expect(isNativeSphContract(component.contract)).toBe(true);
    const convert = new URL(projectComponentConvertHref("/runs/a", component), "http://localhost");
    expect(convert.pathname).toBe("/convert");
    expect(convert.searchParams.get("input")).toBe(
      "/runs/a/components/shield/mgxs.h5",
    );
    expect(convert.searchParams.get("output")).toBe(
      "/runs/a/outputs/shield.reference.macrolib.txt",
    );
    expect(convert.searchParams.get("contract")).toBe("native-sph");
    const equivalence = new URL(
      projectComponentEquivalenceHref("/runs/a", component),
      "http://localhost",
    );
    expect(equivalence.pathname).toBe("/equivalence");
    expect(equivalence.searchParams.get("project")).toBe("/runs/a");
    expect(equivalence.searchParams.get("component")).toBe("shield");
    expect(equivalence.searchParams.get("deck")).toBe(
      "/runs/a/native-sph/shield/native_sph.x2m",
    );
    expect(equivalence.searchParams.get("working_directory")).toBe(
      "/runs/a/native-sph/shield",
    );
    expect(equivalence.searchParams.get("reference_h5")).toBe(
      "/runs/a/components/shield/mgxs.h5",
    );
    expect(equivalence.searchParams.get("reference_macrolib")).toBe(
      "/runs/a/outputs/shield.reference.macrolib.txt",
    );
    expect(equivalence.searchParams.get("sph_macrolib")).toBe(
      "/runs/a/outputs/shield.sph.macrolib.txt",
    );
    expect(equivalence.searchParams.get("verify_macrolib")).toBe(
      "/runs/a/outputs/shield.verify.macrolib.txt",
    );
    expect(equivalence.searchParams.get("result_listing")).toBe(
      "/runs/a/diagnostics/shield.result",
    );
    expect(equivalence.searchParams.get("energy_coverage")).toBe(
      "/runs/a/diagnostics/energy-coverage.json",
    );
    expect(equivalence.searchParams.get("converter_receipt")).toBe(
      "/runs/a/outputs/shield.reference.macrolib.txt.convert.json",
    );
    expect(equivalence.searchParams.get("summary_json")).toBe(
      "/runs/a/outputs/shield.physics-summary.json",
    );
    expect(equivalence.searchParams.get("native_sph_source")).toBe(
      "project-manifest",
    );
    expect(projectNativeSphValidationInputs(component)).toEqual({
      reference_h5: "/runs/a/components/shield/mgxs.h5",
      reference_macrolib: "/runs/a/outputs/shield.reference.macrolib.txt",
      sph_macrolib: "/runs/a/outputs/shield.sph.macrolib.txt",
      verify_macrolib: "/runs/a/outputs/shield.verify.macrolib.txt",
      result_listing: "/runs/a/diagnostics/shield.result",
      energy_coverage: "/runs/a/diagnostics/energy-coverage.json",
      converter_receipt: "/runs/a/outputs/shield.reference.macrolib.txt.convert.json",
      summary_json: "/runs/a/outputs/shield.physics-summary.json",
    });
    expect(projectComponentPrepareHref("/runs/a", component)).not.toContain(
      "equivalence=sph",
    );
    const prepare = new URL(
      projectComponentPrepareHref("/runs/a", component),
      "http://localhost",
    );
    expect(prepare.searchParams.get("input")).toBe(
      "/runs/a/components/shield/mgxs.h5",
    );
    expect(prepare.searchParams.get("output")).toBe(
      "/runs/a/outputs/shield.reference.macrolib.txt",
    );
    expect(projectEquivalenceActionLabel(component.contract)).toBe("Native SPH");

    const entries = projectNativeSphEntryHrefs("/runs/a", [component]);
    const entryConvert = new URL(entries.converterHref!, "http://localhost");
    expect(entryConvert.searchParams.get("input")).toBe(
      "/runs/a/components/shield/mgxs.h5",
    );
    expect(entryConvert.searchParams.get("output")).toBe(
      "/runs/a/outputs/shield.reference.macrolib.txt",
    );
    expect(entryConvert.searchParams.get("format")).toBe("macrolib");
    expect(entryConvert.searchParams.get("check")).toBe("1");
    expect(entryConvert.searchParams.get("production")).toBe("1");
    expect(entryConvert.searchParams.get("contract")).toBe("native-sph");
    expect(entryConvert.searchParams.get("component")).toBe("shield");
    expect(entryConvert.searchParams.get("project")).toBe("/runs/a");
    expect(entries.equivalenceHref).toContain("contract=native-sph");
  });

  it("keeps strict native links fail-closed until a manifest component is loaded", () => {
    const entries = projectNativeSphEntryHrefs("/runs/irena", []);
    expect(entries.converterHref).toBeNull();
    expect(entries.equivalenceHref).toBe(
      "/equivalence?contract=native-sph&project=%2Fruns%2Firena&component=fullcore",
    );
    expect(projectConsumerActionLabel(false, "IRENA full core")).toBe(
      "Review HOLD consumer →",
    );
    expect(projectConsumerActionLabel(true, "IRENA full core")).toBe(
      "Open IRENA full core →",
    );
  });

  it("leaves deck and missing evidence editable for a generic native-SPH component", () => {
    const component = {
      id: "assembly",
      contract: "native-sph",
      format: "macrolib",
      native_sph: null,
      paths: {
        input: "/runs/generic/assembly/reference.h5",
        output: "/runs/generic/assembly/native.macrolib.txt",
        receipt: "/runs/generic/assembly/reference.macrolib.txt.convert.json",
        physics_summary: "/runs/generic/assembly/physics-summary.json",
        evidence: [],
      },
    } as unknown as ProjectComponentStatus;

    const route = new URL(
      projectComponentEquivalenceHref("/runs/generic", component),
      "http://localhost",
    );
    expect(route.searchParams.get("reference_h5")).toBe(
      "/runs/generic/assembly/reference.h5",
    );
    expect(route.searchParams.get("sph_macrolib")).toBe(
      "/runs/generic/assembly/native.macrolib.txt",
    );
    expect(route.searchParams.get("converter_receipt")).toBe(
      "/runs/generic/assembly/reference.macrolib.txt.convert.json",
    );
    expect(route.searchParams.get("summary_json")).toBe(
      "/runs/generic/assembly/physics-summary.json",
    );
    expect(route.searchParams.has("deck")).toBe(false);
    expect(route.searchParams.has("working_directory")).toBe(false);
    expect(route.searchParams.has("native_sph_source")).toBe(false);
  });

  it("routes a converted project component to its declared consumer", () => {
    const consumer = {
      kind: "declared-core",
      label: "Declared core",
      href: "/donjon?mode=declared-core",
      runs: [],
    };
    expect(projectConsumerHref("/runs/a", consumer, "assembly-a")).toBe(
      "/donjon?mode=declared-core&project=%2Fruns%2Fa&component=assembly-a",
    );
    expect(
      projectPostConvertDestination("/runs/a", "assembly-a", {
        configured: true,
        consumer,
        acceptance: {
          basis: "not-required",
        } as ProjectStatus["acceptance"],
      }),
    ).toMatchObject({
      href: "/donjon?mode=declared-core&project=%2Fruns%2Fa&component=assembly-a",
      label: "Open Declared core",
    });
    expect(projectPostConvertDestination("/runs/a", "assembly-a", null)?.href)
      .toBe("/projects?project=%2Fruns%2Fa&component=assembly-a");
  });

  it("carries component output, receipt, and writer policy into its consumer", () => {
    const component = {
      id: "fuel",
      format: "multicompo",
      contract: "converter-hdf5",
      paths: {
        input: "/runs/a/components/fuel.h5",
        output: "/runs/a/outputs/fuel.mcompo.txt",
        receipt: "/runs/a/outputs/fuel.mcompo.txt.convert.json",
        physics_summary: "",
        evidence: [],
      },
      conversion: {
        writer_backend: "pygan",
        root_name: "LIB",
        comment: "fuel state",
        burnup: 0,
        h_factor_default: 1.25,
        mixtures: ["M1", "M2"],
      },
    } as unknown as ProjectComponentStatus;
    const consumer = {
      kind: "external",
      label: "DONJON",
      href: "/donjon",
      runs: [],
    };
    const href = new URL(projectConsumerHref("/runs/a", consumer, component), "http://localhost");
    expect(href.searchParams.get("ascii")).toBe(component.paths.output);
    expect(href.searchParams.get("receipt")).toBe(component.paths.receipt);
    expect(href.searchParams.has("physics_summary")).toBe(false);
    expect(href.searchParams.get("input_h5")).toBe(component.paths.input);
    expect(href.searchParams.getAll("mixture")).toEqual(["M1", "M2"]);
    const convert = new URL(
      projectComponentConvertHref("/runs/a", component),
      "http://localhost",
    );
    expect(convert.searchParams.get("writer_backend")).toBe("pygan");
    expect(convert.searchParams.get("root_name")).toBe("LIB");
    expect(convert.searchParams.get("production")).toBe("0");
  });

  it("returns a converted component to the next pending project row", () => {
    const pending = {
      id: "reflector",
      label: "Reflector",
      required: true,
      handoff: { state: "missing", issues: ["missing input"] },
      output: { state: "missing", issues: ["missing output"] },
    } as unknown as ProjectComponentStatus;
    const destination = projectPostConvertDestination("/runs/a", "fuel", {
      configured: true,
      consumer: { kind: "external", label: "Core", href: "/donjon", runs: [] },
      acceptance: { basis: "not-required" } as ProjectStatus["acceptance"],
      components: [pending],
      handoffs_ready: false,
      ready_for_consumer: false,
    });
    expect(destination).toMatchObject({
      href: "/projects?project=%2Fruns%2Fa&component=reflector",
      label: "Continue Reflector",
    });
  });

  it("keeps a declared physics decision separate from ready handoffs", () => {
    const presentation = projectReadinessPresentation({
      accepted_outputs: 1,
      required_components: 1,
      handoffs_ready: true,
      physics_accepted: false,
      ready_for_consumer: false,
      acceptance: { declared: true },
      consumer: { kind: "irena30-donjon-fullcore" },
    } as unknown as ProjectStatus);

    expect(presentation.handoffValue).toBe("1/1");
    expect(presentation.handoffLabel).toBe("handoffs ready");
    expect(presentation.handoffTone).toBe("ready");
    expect(presentation.physicsValue).toBe("HOLD");
    expect(presentation.physicsTone).toBe("hold");
    expect(presentation.consumerValue).toBe("HOLD");
    expect(presentation.explanation).toContain("status=accepted");
  });

  it("allows a generic external consumer without inventing physics acceptance", () => {
    const presentation = projectReadinessPresentation({
      accepted_outputs: 1,
      required_components: 1,
      handoffs_ready: true,
      physics_accepted: false,
      ready_for_consumer: true,
      acceptance: {
        declared: false,
        state: "not-required",
        basis: "not-required",
      },
      consumer: { kind: "external" },
    } as ProjectStatus);

    expect(presentation.physicsValue).toBe("N/A");
    expect(presentation.physicsLabel).toBe("physics gate not required");
    expect(presentation.physicsTone).toBe("neutral");
    expect(presentation.consumerValue).toBe("READY");
    expect(presentation.explanation).toContain("does not claim physics equivalence");
  });

  it("labels handoff-only readiness without promoting it to physics acceptance", () => {
    const presentation = projectReadinessPresentation({
      accepted_outputs: 1,
      required_components: 1,
      handoffs_ready: true,
      physics_accepted: false,
      ready_for_consumer: true,
      acceptance: {
        declared: false,
        state: "not-required",
        basis: "not-required",
      },
      consumer: { kind: "declared-full-core" },
    } as ProjectStatus);

    expect(presentation.physicsValue).toBe("N/A");
    expect(presentation.consumerValue).toBe("READY");
    expect(presentation.explanation).toContain("READY does not claim");
  });

  it("renders the exact physics acceptance decision state", () => {
    const base = {
      accepted_outputs: 1,
      required_components: 1,
      handoffs_ready: true,
      ready_for_consumer: false,
      consumer: { kind: "declared-full-core" },
    } as ProjectStatus;
    const accepted = projectReadinessPresentation({
      ...base,
      physics_accepted: true,
      acceptance: { declared: true, state: "accepted" },
    } as ProjectStatus);
    const rejected = projectReadinessPresentation({
      ...base,
      physics_accepted: false,
      acceptance: { declared: true, state: "rejected" },
    } as ProjectStatus);
    const pending = projectReadinessPresentation({
      ...base,
      physics_accepted: false,
      acceptance: { declared: true, state: "pending" },
    } as ProjectStatus);

    expect([accepted.physicsValue, accepted.physicsTone]).toEqual([
      "READY",
      "ready",
    ]);
    expect(accepted.physicsLabel).toBe("project-declared acceptance");
    expect(accepted.explanation).toContain("not a machine-verified generic physics verdict");
    expect([rejected.physicsValue, rejected.physicsTone]).toEqual([
      "REJECTED",
      "rejected",
    ]);
    expect(rejected.explanation).toContain("explicitly REJECTED");
    expect([pending.physicsValue, pending.physicsTone]).toEqual([
      "HOLD",
      "hold",
    ]);
  });

  it("distinguishes a bound machine validator from project-declared acceptance", () => {
    const presentation = projectReadinessPresentation({
      accepted_outputs: 1,
      required_components: 1,
      handoffs_ready: true,
      physics_accepted: true,
      ready_for_consumer: true,
      acceptance: {
        declared: true,
        state: "accepted",
        basis: "machine-verified",
        machine_validation: { declared: true, state: "passed" },
      },
      consumer: { kind: "irena30-donjon-fullcore" },
    } as ProjectStatus);

    expect(presentation.physicsLabel).toBe("machine-verified acceptance");
    expect(presentation.physicsValue).toBe("READY");
    expect(presentation.explanation).toContain("file-backed machine validator");
  });

  it("does not imply handoff completion alone releases a physics-gated project", () => {
    const presentation = projectReadinessPresentation({
      accepted_outputs: 0,
      required_components: 1,
      handoffs_ready: false,
      physics_accepted: false,
      ready_for_consumer: false,
      acceptance: {
        declared: true,
        state: "pending",
        basis: "machine-verified",
        machine_validation: { declared: true, state: "pending" },
      },
      consumer: { kind: "irena30-donjon-fullcore" },
    } as unknown as ProjectStatus);

    expect(presentation.explanation).toContain("complete every required handoff");
    expect(presentation.explanation).toContain("bound machine validator");
  });
});

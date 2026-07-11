import { describe, expect, it } from "vitest";
import type { OpenmcWorkflowPlan } from "./api";
import {
  OPENMC_SPH_SIDECAR_FORM_HREF,
  isFailedOpenmcSphSidecarCheck,
  openmcBundleBuilderHref,
  openmcConvertHref,
  openmcInspectHref,
  openmcSphPrerequisiteCommands,
  openmcSphSidecarCheckFailed,
  openmcWalkthroughStatuses,
} from "./openmcWorkflowWalkthrough";

function plan(overrides: Partial<OpenmcWorkflowPlan> = {}): OpenmcWorkflowPlan {
  return {
    schema: "openmc2donjon.openmc-workflow-plan.v1",
    ok: true,
    mock_mode: true,
    workflow: "two-step",
    workflow_label: "Two-step export then convert",
    equivalence: "direct",
    steps: [],
    artifacts: [
      {
        label: "MGXS HDF5 handoff",
        path: "/runs/case/mgxs_library.h5",
        kind: "hdf5",
        will_write: true,
      },
      {
        label: "DONJON ASCII output",
        path: "/runs/case/out.mcompo.txt",
        kind: "ascii",
        will_write: true,
      },
      {
        label: "Pipeline summary",
        path: "/runs/case/openmc2donjon_from_openmc_summary.json",
        kind: "json",
        will_write: true,
      },
      {
        label: "Bundle manifest",
        path: "/runs/case/manifest.json",
        kind: "json",
        will_write: true,
      },
    ],
    checks: [],
    commands: [],
    primary_command_text: "",
    next_actions: [],
    ...overrides,
  };
}

describe("OpenMC workflow walkthrough", () => {
  it("requires a statepoint when load-statepoint mode is on", () => {
    expect(
      openmcWalkthroughStatuses({
        hasRecipe: true,
        hasStatepoint: false,
        loadStatepoint: true,
        hasRunDir: true,
        run: { kind: "idle" },
      }),
    ).toMatchObject({
      source: "needed",
      plan: "needed",
      bundle: "planned",
    });
  });

  it("allows no-load-statepoint plans once the recipe is selected", () => {
    expect(
      openmcWalkthroughStatuses({
        hasRecipe: true,
        hasStatepoint: false,
        loadStatepoint: false,
        hasRunDir: false,
        run: { kind: "idle" },
      }),
    ).toMatchObject({
      source: "ready",
      plan: "ready",
      bundle: "optional",
    });
  });

  it("marks a successful plan as ready to copy and run", () => {
    expect(
      openmcWalkthroughStatuses({
        hasRecipe: true,
        hasStatepoint: true,
        loadStatepoint: true,
        hasRunDir: true,
        run: { kind: "ok", ok: true },
      }),
    ).toMatchObject({
      plan: "planned",
      run: "ready",
      review: "planned",
      bundle: "planned",
    });
  });

  it("reports planning, not running, while the plan request is in flight", () => {
    expect(
      openmcWalkthroughStatuses({
        hasRecipe: true,
        hasStatepoint: true,
        loadStatepoint: true,
        hasRunDir: true,
        run: { kind: "loading" },
      }),
    ).toMatchObject({ plan: "planning" });
  });

  it("blocks downstream work on failed plans", () => {
    expect(
      openmcWalkthroughStatuses({
        hasRecipe: true,
        hasStatepoint: true,
        loadStatepoint: true,
        hasRunDir: true,
        run: { kind: "ok", ok: false },
      }),
    ).toMatchObject({
      plan: "blocked",
      run: "blocked",
      review: "blocked",
      bundle: "blocked",
    });
  });

  it("builds inspect, convert, and bundle links from planned artifacts", () => {
    const payload = plan();
    expect(openmcInspectHref(payload)).toBe(
      "/inspect?path=%2Fruns%2Fcase%2Fmgxs_library.h5",
    );
    expect(openmcConvertHref(payload, "multicompo", true)).toBe(
      "/convert?intent=direct-convert&input=%2Fruns%2Fcase%2Fmgxs_library.h5&output=%2Fruns%2Fcase%2Fout.mcompo.txt&format=multicompo&check=1&production=1&comment=Two-step+export+then+convert+web+handoff",
    );
    expect(openmcBundleBuilderHref(payload, "multicompo")).toBe(
      "/builder?command=bundle&output_dir=%2Fruns%2Fcase&mgxs=%2Fruns%2Fcase%2Fmgxs_library.h5&mcompo=%2Fruns%2Fcase%2Fout.mcompo.txt",
    );
  });

  it("uses the augmented HDF5 as the conversion input for two-step equivalence", () => {
    const payload = plan({
      equivalence: "sph",
      artifacts: [
        {
          label: "MGXS HDF5 handoff",
          path: "/runs/case/mgxs_library.h5",
          kind: "hdf5",
          will_write: true,
        },
        {
          label: "SPH-augmented HDF5 handoff",
          path: "/runs/case/mgxs_library_sph.h5",
          kind: "hdf5",
          will_write: true,
        },
        {
          label: "DONJON ASCII output",
          path: "/runs/case/out.macrolib.txt",
          kind: "ascii",
          will_write: true,
        },
      ],
    });

    expect(openmcInspectHref(payload)).toBe(
      "/inspect?path=%2Fruns%2Fcase%2Fmgxs_library_sph.h5",
    );
    expect(openmcConvertHref(payload, "macrolib", false)).toContain(
      "input=%2Fruns%2Fcase%2Fmgxs_library_sph.h5",
    );
  });

  it("flags SPH plans whose sidecar readiness check failed", () => {
    const failed = plan({
      ok: false,
      equivalence: "sph",
      checks: [
        {
          name: "SPH sidecar",
          status: "fail",
          message: "Required path is missing.",
        },
      ],
    });
    expect(openmcSphSidecarCheckFailed(failed)).toBe(true);
    expect(isFailedOpenmcSphSidecarCheck(failed.checks[0])).toBe(true);

    // A passing sidecar check, or a non-SPH route, must not splice.
    expect(
      openmcSphSidecarCheckFailed(
        plan({
          equivalence: "sph",
          checks: [{ name: "SPH sidecar", status: "pass", message: "Ready." }],
        }),
      ),
    ).toBe(false);
    expect(
      openmcSphSidecarCheckFailed(
        plan({
          equivalence: "direct",
          checks: [
            { name: "SPH sidecar", status: "fail", message: "Required path is missing." },
          ],
        }),
      ),
    ).toBe(false);
  });

  it("splices the three sidecar-building commands as plan prerequisites", () => {
    const commands = openmcSphPrerequisiteCommands();

    expect(commands.map((command) => command.id)).toEqual([
      "ce-flux",
      "mg-flux",
      "sph-sidecar",
    ]);
    for (const command of commands) {
      expect(command.cli).toMatch(/^openmc2donjon /);
      expect(command.title.length).toBeGreaterThan(0);
    }
    expect(commands[2].cli).toContain("make-openmc-sph-sidecar");
    expect(OPENMC_SPH_SIDECAR_FORM_HREF).toBe("/equivalence?kind=openmc-sph-sidecar");
  });
});

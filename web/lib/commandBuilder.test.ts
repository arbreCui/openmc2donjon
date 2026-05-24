import { describe, expect, it } from "vitest";
import {
  buildCommandCli,
  commandBuilderStage,
  commandBuilderSpec,
  defaultBuilderValues,
} from "./commandBuilder";

describe("commandBuilder", () => {
  it("builds repeated flags and numeric options for diff", () => {
    const spec = commandBuilderSpec("diff");
    expect(spec).not.toBeNull();
    const values = defaultBuilderValues(spec!);
    values.reference_h5 = "/runs/ref.h5";
    values.candidate_h5 = "/runs/candidate.h5";
    values.rtol = "1e-5";
    values.ignore_attr = "created_by, timestamp";
    values.no_fail = true;

    expect(buildCommandCli(spec!, values)).toBe(
      "openmc2donjon diff /runs/ref.h5 /runs/candidate.h5 --rtol 1e-5 " +
        "--ignore-attr created_by --ignore-attr timestamp --no-fail",
    );
  });

  it("keeps required placeholders visible for incomplete ADF driver commands", () => {
    const spec = commandBuilderSpec("make-homogeneous-face-flux");
    expect(spec).not.toBeNull();
    const cli = buildCommandCli(spec!, defaultBuilderValues(spec!));

    expect(cli).toContain("<mgxs_library.h5>");
    expect(cli).toContain("-o homogeneous_face_flux.h5");
    expect(cli).toContain("--volume-flux <volume_flux>");
    expect(cli).toContain("--net-current <net_current>");
  });

  it("builds serve command with mock mode and repeated CORS origins", () => {
    const spec = commandBuilderSpec("serve");
    expect(spec).not.toBeNull();
    const values = defaultBuilderValues(spec!);
    values.host = "0.0.0.0";
    values.port = "8015";
    values.mock = true;
    values.cors_origin = "http://localhost:3000,http://127.0.0.1:3000";
    values.log_level = "DEBUG";

    expect(buildCommandCli(spec!, values)).toBe(
      "openmc2donjon serve --host 0.0.0.0 --port 8015 --mock " +
        "--cors-origin http://localhost:3000 --cors-origin http://127.0.0.1:3000 " +
        "--log-level DEBUG",
    );
  });

  it("labels SPH builders with the fixed-OpenMC feedback-loop stage", () => {
    const stage = commandBuilderStage("make-sph-loop-scaffold");

    expect(stage.label).toBe("SPH feedback loop");
    expect(stage.summary).toContain("Fixed-OpenMC");
    expect(stage.reference).toContain("OpenMC");
  });
});

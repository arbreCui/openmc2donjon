import { describe, expect, it } from "vitest";
import {
  builderValuesFromQuery,
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

  it("builds PyGan writer comparison commands", () => {
    const spec = commandBuilderSpec("compare-writers");
    expect(spec).not.toBeNull();
    const values = defaultBuilderValues(spec!);
    expect(values.format).toBe("multicompo");
    values.input_h5 = "/runs/case/mgxs_library.h5";
    values.format = "multicompo";
    values.mixture = "ASM_01, ASM_02";
    values.summary_json = "/runs/case/writer_compare.json";
    values.keep_dir = "/runs/case/writer_compare_files";
    values.no_fail = true;

    expect(buildCommandCli(spec!, values)).toBe(
      "openmc2donjon compare-writers /runs/case/mgxs_library.h5 --format multicompo " +
        "--mixture ASM_01 --mixture ASM_02 --summary-json /runs/case/writer_compare.json " +
        "--keep-dir /runs/case/writer_compare_files --no-fail",
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

  it("prefills builder values from matching query parameters", () => {
    const spec = commandBuilderSpec("bundle");
    expect(spec).not.toBeNull();
    const values = builderValuesFromQuery(
      spec!,
      new URLSearchParams({
        mgxs: "/runs/case/mgxs_library.h5",
        mcompo: "/runs/case/out.mcompo.txt",
        output_dir: "/runs/case/bundle",
        force: "1",
        ignored: "nope",
      }),
    );

    expect(values.mgxs).toBe("/runs/case/mgxs_library.h5");
    expect(values.mcompo).toBe("/runs/case/out.mcompo.txt");
    expect(values.output_dir).toBe("/runs/case/bundle");
    expect(values.force).toBe(true);
    expect(buildCommandCli(spec!, values)).toContain(
      "--mgxs /runs/case/mgxs_library.h5 --mcompo /runs/case/out.mcompo.txt",
    );
  });

  it("labels SPH builders with the OpenMC-side equivalence stage", () => {
    const stage = commandBuilderStage("make-sph-update-table");

    expect(stage.label).toBe("OpenMC-side SPH");
    expect(stage.summary).toContain("CE reference");
    expect(stage.reference).toContain("OpenMC MG");
  });
});

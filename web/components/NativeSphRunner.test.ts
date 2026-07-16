import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ExecutionJob } from "@/lib/api";
import NativeSphJobStatus from "./NativeSphJobStatus";

describe("NativeSphJobStatus", () => {
  it("shows process evidence without turning completion into acceptance", () => {
    const html = renderToStaticMarkup(
      createElement(NativeSphJobStatus, {
        job: completedJob(),
      }),
    );

    expect(html).toContain("completed");
    expect(html).toContain(
      "/project/diagnostics/native-sph-runs/native-job-1/case.result",
    );
    expect(html).toContain("NORMAL END");
    expect(html).toContain("archived run native-job-1");
    expect(html).toContain("Declared working directory");
    expect(html).toContain("artifacts.json");
    expect(html).toContain("does not set Project physics acceptance");
  });
});

function completedJob(): ExecutionJob {
  return {
    schema: "openmc2donjon.web-donjon-job.v1",
    job_id: "native-job-1",
    run_id: "native-job-1",
    operation: "donjon",
    status: "completed",
    created_at: 1,
    started_at: 2,
    finished_at: 3,
    message: "DONJON ingest completed.",
    result_path: "/project/diagnostics/native-sph-runs/native-job-1/case.result",
    deck_path: "/project/diagnostics/native-sph-runs/native-job-1/case.x2m",
    k_effective: null,
    return_code: 0,
    log_tail: "NORMAL END",
    working_directory: "/project/native-deck",
    archive_root: "/project/diagnostics/native-sph-runs",
    run_directory: "/project/diagnostics/native-sph-runs/native-job-1",
    request_path:
      "/project/diagnostics/native-sph-runs/native-job-1/request.json",
    status_path:
      "/project/diagnostics/native-sph-runs/native-job-1/status.json",
    artifacts_path:
      "/project/diagnostics/native-sph-runs/native-job-1/artifacts.json",
    log_path: "/project/diagnostics/native-sph-runs/native-job-1/run.log",
    staged_manifest_path:
      "/project/diagnostics/native-sph-runs/native-job-1/staged-inputs.json",
    runtime_output_directory:
      "/project/diagnostics/native-sph-runs/native-job-1/runtime-output",
  };
}

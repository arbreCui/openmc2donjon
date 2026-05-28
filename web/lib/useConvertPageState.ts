"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { ConvertRunState } from "@/components/convert/ConvertReportState";
import { ApiError, api } from "@/lib/api";
import type {
  ConvertFormat,
  ConvertWriterBackend,
  PyGanBackendStatus,
} from "@/lib/api";
import { convertAdvancedPayload } from "@/lib/convertCommand";
import {
  C5G7_PRODUCTION_DEMO,
  PRODUCTION_MINICASE_DEMO,
  convertDemoRequest,
  isProductionMinicasePath,
} from "@/lib/convertDemo";
import { convertIntentCopy } from "@/lib/convertIntent";
import { defaultConvertOutputPath } from "@/lib/convertPaths";
import { useSettings } from "@/lib/settings";
import { parseConvertFormat, queryFlag } from "@/lib/workflowQuery";

const FALLBACK_INPUT = "/path/to/mgxs_library.h5";
const UNKNOWN_PYGAN_BACKEND: PyGanBackendStatus = {
  available: false,
  role: "optional PyGan writer backend",
  install_hint:
    "Restart `openmc2donjon serve` from the current checkout to expose PyGan backend status.",
  modules: [],
  missing_modules: [],
};

export type BackendMode = "checking" | "mock" | "live" | "unavailable";

export function useConvertPageState() {
  const searchParams = useSearchParams();
  const intent = convertIntentCopy(searchParams.get("intent"));
  const queryInput = searchParams.get("input");
  const queryOutput = searchParams.get("output");
  const queryFormat = parseConvertFormat(searchParams.get("format"));
  const queryWriterBackend: ConvertWriterBackend =
    searchParams.get("writer_backend") === "pygan" ? "pygan" : "ascii";
  const queryCheck = queryFlag(searchParams, "check", true);
  const queryProduction = queryFlag(searchParams, "production", false);
  const queryRequireKnownMesh = queryFlag(
    searchParams,
    "require_known_mesh",
    false,
  );
  const queryComment = searchParams.get("comment");
  const queryHasPrefill =
    queryInput !== null ||
    queryOutput !== null ||
    searchParams.get("format") !== null ||
    searchParams.get("writer_backend") !== null ||
    searchParams.get("check") !== null ||
    searchParams.get("production") !== null ||
    searchParams.get("require_known_mesh") !== null ||
    queryComment !== null;

  const [inputPath, setInputPath] = useState(queryInput ?? "");
  const [outputPath, setOutputPath] = useState(queryOutput ?? "");
  const [format, setFormat] = useState<ConvertFormat>(queryFormat);
  const [writerBackend, setWriterBackend] =
    useState<ConvertWriterBackend>(queryWriterBackend);
  const [check, setCheck] = useState(queryCheck);
  const [production, setProduction] = useState(queryProduction);
  const [requireKnownMesh, setRequireKnownMesh] = useState(queryRequireKnownMesh);
  const [overwrite, setOverwrite] = useState(false);
  const [rootName, setRootName] = useState("CPO");
  const [comment, setComment] = useState(queryComment ?? "");
  const [burnup, setBurnup] = useState("");
  const [hFactorDefault, setHFactorDefault] = useState("");
  const [mixturesText, setMixturesText] = useState("");
  const [outputTouched, setOutputTouched] = useState(queryOutput !== null);
  const [state, setState] = useState<ConvertRunState>({ kind: "idle" });
  const [backendMode, setBackendMode] = useState<BackendMode>("checking");
  const [pyganStatus, setPyganStatus] = useState<PyGanBackendStatus | null>(null);

  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const inputPlaceholder = savedPrefix || FALLBACK_INPUT;
  const derivedOutput = useMemo(
    () => defaultConvertOutputPath(inputPath, format),
    [inputPath, format],
  );
  const displayedOutput = outputTouched ? outputPath : derivedOutput;
  const canUseSavedPrefix =
    settingsHydrated &&
    savedPrefix !== "" &&
    !inputPath.startsWith(savedPrefix);
  const showMinicaseMissingHint =
    backendMode === "live" &&
    state.kind === "error" &&
    state.status === 404 &&
    (isProductionMinicasePath(inputPath) ||
      isProductionMinicasePath(displayedOutput));
  const preflightInput =
    state.kind === "ok" ? state.data.preflight?.inputs[0] ?? null : null;
  const c5g7DemoDryRunPassed = isC5g7DemoDryRunPassed(state);
  const c5g7DemoConverted = isC5g7DemoConverted(state);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((health) => {
        if (cancelled) return;
        setBackendMode(health.mock_mode ? "mock" : "live");
        const pyganBackend = health.pygan_backend ?? UNKNOWN_PYGAN_BACKEND;
        setPyganStatus(pyganBackend);
        if (!pyganBackend.available) {
          setWriterBackend("ascii");
        }
      })
      .catch(() => {
        if (cancelled) return;
        setBackendMode("unavailable");
        setPyganStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!queryHasPrefill) return;
    setFormat(queryFormat);
    setWriterBackend(queryWriterBackend);
    setCheck(queryCheck);
    setProduction(queryProduction);
    setRequireKnownMesh(queryRequireKnownMesh);
    if (queryInput !== null) {
      setInputPath(queryInput);
    }
    if (queryOutput !== null) {
      setOutputPath(queryOutput);
      setOutputTouched(true);
    } else if (queryInput !== null) {
      setOutputPath(defaultConvertOutputPath(queryInput, queryFormat));
      setOutputTouched(false);
    }
    if (queryComment !== null) {
      setComment(queryComment);
    }
    setState({ kind: "idle" });
  }, [
    queryCheck,
    queryComment,
    queryFormat,
    queryHasPrefill,
    queryInput,
    queryOutput,
    queryProduction,
    queryRequireKnownMesh,
    queryWriterBackend,
  ]);

  function updateInput(value: string) {
    setInputPath(value);
    if (!outputTouched) setOutputPath(defaultConvertOutputPath(value, format));
  }

  function updateFormat(value: ConvertFormat) {
    setFormat(value);
    if (!outputTouched) setOutputPath(defaultConvertOutputPath(inputPath, value));
  }

  function updateOutput(value: string) {
    setOutputTouched(true);
    setOutputPath(value);
  }

  function applyC5g7Demo() {
    applyDemoPreset(C5G7_PRODUCTION_DEMO, "C5G7 mock production demo");
    setState({ kind: "idle" });
  }

  function applyProductionMinicaseDemo() {
    applyDemoPreset(PRODUCTION_MINICASE_DEMO, "production minicase web repeat");
    setState({ kind: "idle" });
  }

  function applyDemoPreset(
    preset: typeof C5G7_PRODUCTION_DEMO,
    demoComment: string,
  ) {
    updateInput(preset.inputPath);
    setOutputPath(preset.outputPath);
    setOutputTouched(true);
    setFormat(preset.format);
    setWriterBackend("ascii");
    setCheck(preset.check);
    setProduction(preset.production);
    setRequireKnownMesh(preset.requireKnownMesh);
    setOverwrite(false);
    setRootName("CPO");
    setComment(demoComment);
    setBurnup("");
    setHFactorDefault("");
    setMixturesText("");
  }

  async function runC5g7DemoDryRun() {
    await runDemo({ dryRun: true });
  }

  async function runC5g7DemoConvert() {
    await runDemo({ dryRun: false });
  }

  async function runDemo({ dryRun }: { dryRun: boolean }) {
    const demoComment = "C5G7 mock production demo";
    applyDemoPreset(C5G7_PRODUCTION_DEMO, demoComment);
    setState({ kind: "loading", mode: dryRun ? "dry-run" : "convert" });
    try {
      const data = await api.convert(
        convertDemoRequest(C5G7_PRODUCTION_DEMO, {
          dryRun,
          comment: demoComment,
        }),
      );
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  async function run(mode: "dry-run" | "convert") {
    const trimmedInput = inputPath.trim();
    const trimmedOutput = displayedOutput.trim();
    if (!trimmedInput) {
      setState({ kind: "error", message: "Enter an input HDF5 path first." });
      return;
    }
    if (!trimmedOutput) {
      setState({ kind: "error", message: "Enter an output path first." });
      return;
    }
    const numberError =
      optionalNumberError("Burnup", burnup) ??
      optionalNumberError("H-FACTOR default", hFactorDefault);
    if (numberError) {
      setState({ kind: "error", message: numberError });
      return;
    }
    setState({ kind: "loading", mode });
    try {
      const data = await api.convert({
        input_path: trimmedInput,
        output_path: trimmedOutput,
        format,
        writer_backend: writerBackend,
        dry_run: mode === "dry-run",
        overwrite,
        check,
        production,
        warn_unknown_energy_mesh: true,
        require_known_energy_mesh: requireKnownMesh,
        ...convertAdvancedPayload({
          rootName,
          comment,
          burnup,
          hFactorDefault,
          mixturesText,
        }),
      });
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  return {
    intent,
    inputPath,
    inputPlaceholder,
    canUseSavedPrefix,
    savedPrefix,
    displayedOutput,
    format,
    writerBackend,
    pyganStatus,
    check,
    production,
    requireKnownMesh,
    overwrite,
    rootName,
    comment,
    burnup,
    hFactorDefault,
    mixturesText,
    state,
    backendMode,
    preflightInput,
    c5g7DemoDryRunPassed,
    c5g7DemoConverted,
    showMinicaseMissingHint,
    updateInput,
    updateFormat,
    updateOutput,
    setWriterBackend,
    setCheck,
    setProduction,
    setRequireKnownMesh,
    setOverwrite,
    setRootName,
    setComment,
    setBurnup,
    setHFactorDefault,
    setMixturesText,
    applyC5g7Demo,
    applyProductionMinicaseDemo,
    runC5g7DemoDryRun,
    runC5g7DemoConvert,
    run,
  };
}

function optionalNumberError(label: string, value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (Number.isFinite(Number(trimmed))) return null;
  return `${label} must be a number.`;
}

function isC5g7DemoDryRunPassed(state: ConvertRunState): boolean {
  return (
    state.kind === "ok" &&
    state.data.ok &&
    state.data.dry_run &&
    !state.data.converted &&
    state.data.input_path === C5G7_PRODUCTION_DEMO.inputPath &&
    state.data.output_path === C5G7_PRODUCTION_DEMO.outputPath
  );
}

function isC5g7DemoConverted(state: ConvertRunState): boolean {
  return (
    state.kind === "ok" &&
    state.data.ok &&
    state.data.converted &&
    state.data.output_exists &&
    state.data.input_path === C5G7_PRODUCTION_DEMO.inputPath &&
    state.data.output_path === C5G7_PRODUCTION_DEMO.outputPath
  );
}

function toErrorState(
  err: unknown,
): Extract<ConvertRunState, { kind: "error" }> {
  if (err instanceof ApiError) {
    return {
      kind: "error",
      status: err.status,
      message: err.detail ?? err.message,
    };
  }
  if (err instanceof Error) return { kind: "error", message: err.message };
  return { kind: "error", message: "Unknown error." };
}

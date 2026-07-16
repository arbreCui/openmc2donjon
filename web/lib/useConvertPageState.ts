"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { ConvertRunState } from "@/components/convert/ConvertReportState";
import { ApiError, api } from "@/lib/api";
import type {
  ConvertFormat,
  ConvertWriterBackend,
  ProjectStatus,
  PyGanBackendStatus,
} from "@/lib/api";
import { CONVERT_CHECKS_DEFAULTS } from "@/lib/convertChecks";
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
import {
  colorsetDefinition,
  isWithdrawnColorsetWorkflow,
} from "@/lib/colorsetWorkflow";
import {
  colorsetProjectPaths,
  isWithdrawnDiagnosticProject,
  projectComponentConverterOutputPath,
  projectPostConvertDestination,
  projectRootFromSearchParams,
} from "@/lib/projectWorkspace";

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

interface ProjectPolicyState {
  root: string;
  checking: boolean;
  unavailable: boolean;
  withdrawn: boolean;
  status: ProjectStatus | null;
}

export function useConvertPageState() {
  const searchParams = useSearchParams();
  const intent = convertIntentCopy(searchParams.get("intent"));
  const queryInput = searchParams.get("input");
  const queryOutput = searchParams.get("output");
  const queryFormat = parseConvertFormat(searchParams.get("format"));
  const queryWriterBackend: ConvertWriterBackend =
    searchParams.get("writer_backend") === "pygan" ? "pygan" : "ascii";
  const componentId = searchParams.get("component");
  const colorsetId = searchParams.get("colorset");
  const contractKind = searchParams.get("contract");
  const diagnosticKind = searchParams.get("diagnostic");
  const withdrawnColorsetQuery = isWithdrawnColorsetWorkflow(
    colorsetId,
    contractKind,
    diagnosticKind,
  );
  // Production is the formal handoff default. URL params can still select the
  // explicitly non-production engineering or diagnostic levels.
  const queryCheck = queryFlag(searchParams, "check", CONVERT_CHECKS_DEFAULTS.check);
  const queryProduction = withdrawnColorsetQuery
    ? false
    : queryFlag(
        searchParams,
        "production",
        CONVERT_CHECKS_DEFAULTS.production,
      );
  const queryRequireKnownMesh = withdrawnColorsetQuery
    ? false
    : queryFlag(searchParams, "require_known_mesh", false);
  const queryComment = searchParams.get("comment");
  const queryRootName = searchParams.get("root_name");
  const queryBurnup = searchParams.get("burnup");
  const queryHFactorDefault = searchParams.get("h_factor_default");
  const queryMixtures = searchParams.getAll("mixture");
  const queryMixturesText = queryMixtures.join(",");
  const activeColorset = colorsetId ? colorsetDefinition(colorsetId) : null;
  const projectRoot = projectRootFromSearchParams(searchParams);
  const projectPaths = activeColorset
    ? colorsetProjectPaths(projectRoot, activeColorset)
    : null;
  const [projectPolicy, setProjectPolicy] = useState<ProjectPolicyState>({
    root: projectRoot,
    checking: projectRoot !== "",
    unavailable: false,
    withdrawn: false,
    status: null,
  });
  const projectPolicyChecking =
    projectRoot !== "" &&
    (projectPolicy.root !== projectRoot || projectPolicy.checking);
  const projectPolicyUnavailable =
    projectPolicy.root === projectRoot && projectPolicy.unavailable;
  const withdrawnProject =
    projectPolicy.root === projectRoot && projectPolicy.withdrawn;
  const loadedProject =
    projectPolicy.root === projectRoot ? projectPolicy.status : null;
  const withdrawnIrenaColorsetWorkflow =
    withdrawnColorsetQuery || withdrawnProject;
  const requirePhysicalSph =
    !withdrawnIrenaColorsetWorkflow && contractKind === "physical-sph";
  const queryHasPrefill =
    queryInput !== null ||
    queryOutput !== null ||
    searchParams.get("format") !== null ||
    searchParams.get("writer_backend") !== null ||
    searchParams.get("check") !== null ||
    searchParams.get("production") !== null ||
    searchParams.get("require_known_mesh") !== null ||
    queryComment !== null ||
    queryRootName !== null ||
    queryBurnup !== null ||
    queryHFactorDefault !== null ||
    queryMixtures.length > 0 ||
    componentId !== null ||
    colorsetId !== null ||
    contractKind !== null ||
    diagnosticKind !== null ||
    projectRoot !== "";

  const [inputPath, setInputPath] = useState(queryInput ?? projectPaths?.sphApplied ?? "");
  const [outputPath, setOutputPath] = useState(queryOutput ?? projectPaths?.cpo ?? "");
  const [format, setFormat] = useState<ConvertFormat>(queryFormat);
  const [writerBackend, setWriterBackend] =
    useState<ConvertWriterBackend>(queryWriterBackend);
  const [check, setCheck] = useState(queryCheck);
  const [production, setProduction] = useState(queryProduction);
  const [requireKnownMesh, setRequireKnownMesh] = useState(queryRequireKnownMesh);
  const [overwrite, setOverwrite] = useState(false);
  const [rootName, setRootName] = useState(queryRootName ?? "CPO");
  const [comment, setComment] = useState(
    queryComment ?? (activeColorset ? colorsetConverterComment(activeColorset) : ""),
  );
  const [burnup, setBurnup] = useState(queryBurnup ?? "");
  const [hFactorDefault, setHFactorDefault] = useState(queryHFactorDefault ?? "");
  const [mixturesText, setMixturesText] = useState(queryMixturesText);
  const [outputTouched, setOutputTouched] = useState(
    queryOutput !== null || Boolean(projectPaths?.cpo),
  );
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
    if (!projectRoot) {
      setProjectPolicy({
        root: "",
        checking: false,
        unavailable: false,
        withdrawn: false,
        status: null,
      });
      return;
    }
    let cancelled = false;
    setProjectPolicy({
      root: projectRoot,
      checking: true,
      unavailable: false,
      withdrawn: false,
      status: null,
    });
    api
      .projectStatus(projectRoot)
      .then((project) => {
        if (cancelled) return;
        const declaredComponent = componentId
          ? project.components.find((item) => item.id === componentId) ?? null
          : null;
        if (declaredComponent) {
          if (queryInput === null) {
            setInputPath((current) =>
              current.trim() ? current : declaredComponent.paths.input,
            );
          }
          if (queryOutput === null) {
            setOutputPath((current) =>
              current.trim()
                ? current
                : projectComponentConverterOutputPath(declaredComponent),
            );
            setOutputTouched(true);
          }
        }
        setProjectPolicy({
          root: projectRoot,
          checking: false,
          unavailable: false,
          withdrawn: isWithdrawnDiagnosticProject(project),
          status: project,
        });
      })
      .catch(() => {
        if (cancelled) return;
        setProjectPolicy({
          root: projectRoot,
          checking: false,
          unavailable: true,
          withdrawn: false,
          status: null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [componentId, projectRoot, queryInput, queryOutput]);

  const projectDestination = projectPostConvertDestination(
    projectRoot,
    componentId,
    loadedProject,
  );

  useEffect(() => {
    if (!withdrawnIrenaColorsetWorkflow) return;
    setProduction(false);
    setRequireKnownMesh(false);
    setState({ kind: "idle" });
  }, [withdrawnIrenaColorsetWorkflow]);

  useEffect(() => {
    if (!queryHasPrefill) return;
    setFormat(queryFormat);
    setWriterBackend(queryWriterBackend);
    setCheck(queryCheck);
    setProduction(queryProduction);
    setRequireKnownMesh(queryRequireKnownMesh);
    if (queryInput !== null || projectPaths?.sphApplied) {
      setInputPath(queryInput ?? projectPaths?.sphApplied ?? "");
    }
    if (queryRootName !== null) setRootName(queryRootName);
    if (queryComment !== null) setComment(queryComment);
    if (queryBurnup !== null) setBurnup(queryBurnup);
    if (queryHFactorDefault !== null) setHFactorDefault(queryHFactorDefault);
    if (queryMixturesText) setMixturesText(queryMixturesText);
    if (queryOutput !== null || projectPaths?.cpo) {
      setOutputPath(queryOutput ?? projectPaths?.cpo ?? "");
      setOutputTouched(true);
    } else if (queryInput !== null) {
      setOutputPath(defaultConvertOutputPath(queryInput, queryFormat));
      setOutputTouched(false);
    }
    if (queryComment !== null) {
      setComment(queryComment);
    } else if (activeColorset) {
      setComment(colorsetConverterComment(activeColorset));
    }
    setState({ kind: "idle" });
  }, [
    queryCheck,
    queryComment,
    queryFormat,
    queryHasPrefill,
    queryInput,
    queryRootName,
    queryBurnup,
    queryHFactorDefault,
    queryMixturesText,
    queryOutput,
    queryProduction,
    queryRequireKnownMesh,
    queryWriterBackend,
    activeColorset,
    colorsetId,
    componentId,
    projectPaths?.cpo,
    projectPaths?.sphApplied,
    projectRoot,
  ]);

  function updateInput(value: string) {
    setInputPath(value);
    if (!outputTouched) setOutputPath(defaultConvertOutputPath(value, format));
    setState({ kind: "idle" });
  }

  function updateFormat(value: ConvertFormat) {
    setFormat(value);
    if (!outputTouched) setOutputPath(defaultConvertOutputPath(inputPath, value));
    setState({ kind: "idle" });
  }

  function updateOutput(value: string) {
    setOutputTouched(true);
    setOutputPath(value);
    setState({ kind: "idle" });
  }

  function updateWriterBackend(value: ConvertWriterBackend) {
    setWriterBackend(value);
    setState({ kind: "idle" });
  }

  function updateCheck(value: boolean) {
    setCheck(value);
    setState({ kind: "idle" });
  }

  function updateProduction(value: boolean) {
    setProduction(value);
    if (value) setHFactorDefault("");
    setState({ kind: "idle" });
  }

  function updateRequireKnownMesh(value: boolean) {
    setRequireKnownMesh(value);
    setState({ kind: "idle" });
  }

  function updateOverwrite(value: boolean) {
    setOverwrite(value);
    setState({ kind: "idle" });
  }

  function updateRootName(value: string) {
    setRootName(value);
    setState({ kind: "idle" });
  }

  function updateComment(value: string) {
    setComment(value);
    setState({ kind: "idle" });
  }

  function updateBurnup(value: string) {
    setBurnup(value);
    setState({ kind: "idle" });
  }

  function updateHFactorDefault(value: string) {
    setHFactorDefault(value);
    setState({ kind: "idle" });
  }

  function updateMixturesText(value: string) {
    setMixturesText(value);
    setState({ kind: "idle" });
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

  async function run(
    mode: "dry-run" | "convert",
    options: { overwrite?: boolean } = {},
  ) {
    if (projectPolicyChecking || projectPolicyUnavailable) {
      setState({
        kind: "error",
        message:
          "Converter is blocked until the project manifest policy can be inspected.",
      });
      return;
    }
    if (withdrawnIrenaColorsetWorkflow) {
      setState({
        kind: "error",
        message:
          "The historical IRENA five-colorset route is withdrawn and diagnostic only. Clear the colorset query or use a declared generic/native-SPH project before running Converter.",
      });
      return;
    }
    const trimmedInput = inputPath.trim();
    const trimmedOutput = displayedOutput.trim();
    if (!trimmedInput) {
      setState({ kind: "error", message: "Enter an MGXS HDF5 path first." });
      return;
    }
    if (!trimmedOutput) {
      setState({ kind: "error", message: "Enter an output path first." });
      return;
    }
    if (production && hFactorDefault.trim()) {
      setState({
        kind: "error",
        message:
          "Production forbids an H-FACTOR default. Export physical group-wise H-FACTOR / kappa-fission data in the HDF5.",
      });
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
        overwrite: options.overwrite ?? overwrite,
        check,
        production,
        require_physical_sph: requirePhysicalSph,
        warn_unknown_energy_mesh: true,
        require_known_energy_mesh: requireKnownMesh,
        project_root: projectRoot || null,
        component_id: componentId || null,
        ...convertAdvancedPayload({
          rootName,
          comment,
          burnup,
          hFactorDefault,
          mixturesText,
        }),
      });
      if (projectRoot && data.ok && !data.dry_run) {
        try {
          const refreshedProject = await api.projectStatus(projectRoot);
          setProjectPolicy({
            root: projectRoot,
            checking: false,
            unavailable: false,
            withdrawn: isWithdrawnDiagnosticProject(refreshedProject),
            status: refreshedProject,
          });
        } catch {
          setProjectPolicy((current) => ({
            ...current,
            root: projectRoot,
            checking: false,
            unavailable: true,
          }));
        }
      }
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  async function retryOverwrite() {
    setOverwrite(true);
    await run("convert", { overwrite: true });
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
    colorsetId,
    componentId,
    projectRoot,
    projectDestination,
    requirePhysicalSph,
    withdrawnIrenaColorsetWorkflow,
    projectPolicyChecking,
    projectPolicyUnavailable,
    c5g7DemoDryRunPassed,
    c5g7DemoConverted,
    showMinicaseMissingHint,
    updateInput,
    updateFormat,
    updateOutput,
    setWriterBackend: updateWriterBackend,
    setCheck: updateCheck,
    setProduction: updateProduction,
    setRequireKnownMesh: updateRequireKnownMesh,
    setOverwrite: updateOverwrite,
    setRootName: updateRootName,
    setComment: updateComment,
    setBurnup: updateBurnup,
    setHFactorDefault: updateHFactorDefault,
    setMixturesText: updateMixturesText,
    applyC5g7Demo,
    applyProductionMinicaseDemo,
    runC5g7DemoDryRun,
    runC5g7DemoConvert,
    run,
    retryOverwrite,
  };
}

function colorsetConverterComment(
  colorset: ReturnType<typeof colorsetDefinition>,
): string {
  return `WITHDRAWN DIAGNOSTIC ONLY: archived IRENA-30 ${colorset.id}; target ${colorset.target} center first; six ${colorset.neighbors} neighbors`;
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

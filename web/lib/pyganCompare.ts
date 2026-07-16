/**
 * Pure helpers for the /pygan writer-comparison form.
 *
 * Lives outside the page component so two behavioral rules can be
 * unit-tested: the web run and the "Same command" CLI preview must
 * agree on rtol/atol handling, and the file-browser start path must be
 * a directory the files API can list.
 */

import type { ConvertFormat } from "./api";

export interface PyGanWorkflowContext {
  projectRoot: string;
  componentId: string;
  inputH5: string;
  outputPath: string;
  receiptPath: string;
  format: ConvertFormat;
  rootName: string;
  comment: string;
  mixtures: string;
  burnup: string;
  hFactorDefault: string;
}

export function pyganWorkflowHrefs(context: PyGanWorkflowContext): {
  project: string | null;
  converter: string;
  bundle: string;
  donjon: string | null;
} {
  const common = new URLSearchParams({
    input: context.inputH5,
    format: context.format,
    writer_backend: "pygan",
    check: "1",
    production: context.hFactorDefault.trim() ? "0" : "1",
  });
  if (context.outputPath) common.set("output", context.outputPath);
  if (context.projectRoot) common.set("project", context.projectRoot);
  if (context.componentId) common.set("component", context.componentId);
  if (context.rootName) common.set("root_name", context.rootName);
  if (context.comment) common.set("comment", context.comment);
  if (context.burnup) common.set("burnup", context.burnup);
  if (context.hFactorDefault) common.set("h_factor_default", context.hFactorDefault);
  for (const mixture of parseMixtures(context.mixtures) ?? []) {
    common.append("mixture", mixture);
  }

  const bundle = new URLSearchParams({
    command: "bundle",
    output_dir: context.projectRoot && context.componentId
      ? `${context.projectRoot}/bundles/${context.componentId}`
      : siblingPath(context.outputPath || context.inputH5, "bundle"),
    mgxs: context.inputH5,
  });
  if (context.outputPath) {
    bundle.set(context.format === "macrolib" ? "macrolib" : "mcompo", context.outputPath);
  }
  if (context.receiptPath) bundle.set("run_summary", context.receiptPath);

  const donjon = context.outputPath
    ? new URLSearchParams({
        ascii: context.outputPath,
        format: context.format,
        ...(context.receiptPath ? { receipt: context.receiptPath } : {}),
        ...(context.projectRoot ? { project: context.projectRoot } : {}),
        ...(context.componentId ? { component: context.componentId } : {}),
      })
    : null;
  return {
    project: context.projectRoot
      ? `/projects?${new URLSearchParams({
          project: context.projectRoot,
          ...(context.componentId ? { component: context.componentId } : {}),
        }).toString()}`
      : null,
    converter: `/convert?${common.toString()}#convert-component`,
    bundle: `/builder?${bundle.toString()}`,
    donjon: donjon ? `/donjon?${donjon.toString()}` : null,
  };
}

export type PyGanBrowseTarget = "input" | "summary" | "keep";

export const PYGAN_RTOL_DEFAULT = 1e-6;
export const PYGAN_ATOL_DEFAULT = 1e-8;

export function parseMixtures(value: string): string[] | null {
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

/**
 * Validation shared by the web run and the CLI preview: a tolerance
 * field must be empty (use the default) or parse as a finite number.
 */
export function toleranceError(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return Number.isFinite(Number(trimmed))
    ? null
    : "Enter a number such as 1e-6, or leave empty for the default.";
}

/**
 * The numeric tolerance the web request sends. Empty means "use the
 * default" (``Number("")`` is 0, so a plain ``Number`` parse would
 * silently run at tolerance 0). Invalid text never reaches this in
 * practice — the form blocks the run — but falls back defensively.
 */
export function toleranceValue(value: string, fallback: number): number {
  const trimmed = value.trim();
  if (trimmed === "") return fallback;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function optionalNumberError(value: string, label: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  return Number.isFinite(Number(trimmed))
    ? null
    : `${label} must be a finite number or empty.`;
}

export function optionalNumberValue(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function buildCompareCli({
  inputH5,
  format,
  rootName,
  comment,
  mixtures,
  burnup,
  hFactorDefault,
  rtol,
  atol,
  summaryJson,
  keepDir,
}: {
  inputH5: string;
  format: ConvertFormat;
  rootName: string;
  comment: string;
  mixtures: string;
  burnup: string;
  hFactorDefault: string;
  rtol: string;
  atol: string;
  summaryJson: string;
  keepDir: string;
}): string {
  const tokens = ["openmc2donjon", "compare-writers", inputH5 || "<mgxs_library.h5>", "--format", format];
  if (rootName.trim() && rootName.trim() !== "CPO") tokens.push("--root-name", rootName.trim());
  if (comment.trim()) tokens.push("--comment", comment.trim());
  if (burnup.trim() && optionalNumberError(burnup, "Burnup") === null) {
    tokens.push("--burnup", burnup.trim());
  }
  if (
    hFactorDefault.trim() &&
    optionalNumberError(hFactorDefault, "H-FACTOR default") === null
  ) {
    tokens.push("--h-factor-default", hFactorDefault.trim());
  }
  for (const mixture of parseMixtures(mixtures) ?? []) tokens.push("--mixture", mixture);
  pushTolerance(tokens, "--rtol", rtol, PYGAN_RTOL_DEFAULT);
  pushTolerance(tokens, "--atol", atol, PYGAN_ATOL_DEFAULT);
  if (summaryJson.trim()) tokens.push("--summary-json", summaryJson.trim());
  if (keepDir.trim()) tokens.push("--keep-dir", keepDir.trim());
  return tokens.map(shellQuote).join(" ");
}

/**
 * Emit a tolerance flag only for a valid, non-default number, so the
 * copied command never embeds a broken string the web run would have
 * silently replaced (the numeric comparison also catches spellings
 * like ``1.0e-6`` that equal the default).
 */
function pushTolerance(
  tokens: string[],
  flag: string,
  value: string,
  defaultValue: number,
): void {
  const trimmed = value.trim();
  if (!trimmed) return;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed === defaultValue) return;
  tokens.push(flag, trimmed);
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:=,+@%-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}

/**
 * Where the file browser opens for a Browse click. The field values
 * hold file paths (or a to-be-created keep directory), so start from
 * the containing directory; with nothing to go on, fall back to ``~``,
 * which the files API resolves to the backend home / mock home.
 * Mirrors the equivalence page's ``browserStart``.
 */
export function browserInitialPath(
  target: PyGanBrowseTarget | null,
  input: string,
  summary: string,
  keep: string,
  savedPrefix: string,
): string {
  const value =
    target === "input"
      ? input
      : target === "summary"
        ? summary
        : target === "keep"
          ? keep
          : "";
  return browserStart(value || savedPrefix);
}

function browserStart(path: string): string {
  const trimmed = path.trim();
  if (trimmed === "") return "~";
  if (trimmed.endsWith("/")) return trimmed;
  const index = trimmed.lastIndexOf("/");
  if (index <= 0) return "~";
  return trimmed.slice(0, index);
}

function siblingPath(path: string, child: string): string {
  const trimmed = path.trim();
  const index = trimmed.lastIndexOf("/");
  return index > 0 ? `${trimmed.slice(0, index)}/${child}` : child;
}

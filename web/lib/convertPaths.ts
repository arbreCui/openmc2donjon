import type { ConvertFormat } from "./api";

export function defaultConvertOutputPath(
  input: string,
  format: ConvertFormat,
): string {
  const trimmed = input.trim();
  const extension = defaultConvertOutputExtension(format);
  if (!trimmed) return `out${extension}`;
  const slash = trimmed.lastIndexOf("/");
  const dirname = slash >= 0 ? trimmed.slice(0, slash + 1) : "";
  const basename = slash >= 0 ? trimmed.slice(slash + 1) : trimmed;
  const dot = basename.lastIndexOf(".");
  const stem = dot > 0 ? basename.slice(0, dot) : basename;
  return `${dirname}${stem}${extension}`;
}

export function pickConvertBrowserStart(path: string): string {
  const trimmed = path.trim();
  if (!trimmed) return "~";
  const lastSlash = trimmed.lastIndexOf("/");
  if (lastSlash >= 0 && lastSlash < trimmed.length - 1) {
    const tail = trimmed.slice(lastSlash + 1);
    if (tail.includes(".")) return trimmed.slice(0, lastSlash + 1);
  }
  return trimmed;
}

export function outputPathInDirectory({
  directory,
  currentOutput,
  inputPath,
  format,
}: {
  directory: string;
  currentOutput: string;
  inputPath: string;
  format: ConvertFormat;
}): string {
  const filename =
    basename(currentOutput) ||
    basename(defaultConvertOutputPath(inputPath, format)) ||
    defaultConvertOutputFilename(format);
  return joinDirectory(directory, filename);
}

export function defaultConvertOutputFilename(format: ConvertFormat): string {
  return `out${defaultConvertOutputExtension(format)}`;
}

function defaultConvertOutputExtension(format: ConvertFormat): string {
  return format === "macrolib" ? ".macrolib.txt" : ".mcompo.txt";
}

function basename(path: string): string {
  const trimmed = path.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  const slash = trimmed.lastIndexOf("/");
  return slash >= 0 ? trimmed.slice(slash + 1) : trimmed;
}

function joinDirectory(directory: string, filename: string): string {
  const raw = directory.trim();
  if (raw === "/") return `/${filename}`;
  const trimmed = raw.replace(/\/+$/, "");
  if (!trimmed) return filename;
  return `${trimmed}/${filename}`;
}

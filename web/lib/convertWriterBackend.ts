import type { ConvertWriterBackend, PyGanBackendStatus } from "./api";

export type ConvertWriterBackendTone =
  | "default"
  | "available"
  | "checking"
  | "disabled";

export interface ConvertWriterBackendOption {
  id: ConvertWriterBackend;
  label: string;
  badge: string;
  title: string;
  body: string;
  detail: string;
  disabled: boolean;
  tone: ConvertWriterBackendTone;
}

export function convertWriterBackendOptions(
  pyganStatus: PyGanBackendStatus | null,
): readonly ConvertWriterBackendOption[] {
  return [
    {
      id: "ascii",
      label: "ASCII",
      badge: "default",
      title: "Built-in ASCII writer",
      body:
        "The normal production route. openmc2donjon writes the LCM ASCII file " +
        "directly from the OpenMC MGXS HDF5.",
      detail:
        "No DRAGON/DONJON Python module is imported. Use this for regular " +
        ".mcompo.txt and .macrolib.txt outputs.",
      disabled: false,
      tone: "default",
    },
    {
      id: "pygan",
      label: "PyGan",
      badge: pyganBadge(pyganStatus),
      title: "Optional PyGan writer",
      body:
        "Writes the same converter LCM tree through DRAGON/DONJON PyGan " +
        "bindings instead of the built-in serializer.",
      detail: pyganDetail(pyganStatus),
      disabled: pyganStatus?.available !== true,
      tone:
        pyganStatus === null
          ? "checking"
          : pyganStatus.available
            ? "available"
            : "disabled",
    },
  ] as const;
}

export function convertWriterBackendShortLabel(
  backend: ConvertWriterBackend,
): string {
  return backend === "pygan" ? "PyGan writer" : "ASCII writer";
}

export function convertWriterBackendResultLabel(
  backend: ConvertWriterBackend,
): string {
  return backend === "pygan"
    ? "PyGan LCM exporter"
    : "built-in ASCII writer";
}

function pyganBadge(status: PyGanBackendStatus | null): string {
  if (status === null) return "checking";
  return status.available ? "optional" : "unavailable";
}

function pyganDetail(status: PyGanBackendStatus | null): string {
  if (status === null) {
    return "The backend is still checking whether PyGan can be imported.";
  }
  if (status.available) {
    return (
      "Use this when you want a local DRAGON/PyGan-backed export or a " +
      "writer comparison against the default ASCII output."
    );
  }
  const missing = status.missing_modules.join(", ") || "PyGan modules";
  return (
    `Unavailable in this backend environment (${missing}). ` +
    "Restart openmc2donjon serve from the Python environment where PyGan is installed."
  );
}

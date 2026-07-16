import type { PyGanBackendStatus } from "./api";

export const PYGAN_CONVERTER_HREF =
  "/convert?writer_backend=pygan&check=1&production=1#convert-component";

export interface PyGanCompareAvailability {
  canRun: boolean;
  hint: string;
}

export function pyganCompareAvailability(
  status: PyGanBackendStatus | null,
): PyGanCompareAvailability {
  if (status === null) {
    return {
      canRun: false,
      hint: "Checking whether the backend can import PyGan.",
    };
  }
  if (status.mock_mode) {
    return {
      canRun: true,
      hint:
        "Mock mode can run the fixture comparison even when local PyGan modules are not installed.",
    };
  }
  if (status.available) {
    return {
      canRun: true,
      hint: "PyGan is importable from the running backend; live writer comparison is enabled.",
    };
  }
  const missing = status.missing_modules.join(", ") || "PyGan modules";
  return {
    canRun: false,
    hint:
      `Live comparison needs ${missing}. Restart openmc2donjon serve from ` +
      "the Python environment where PyGan is installed.",
  };
}

export function pyganMissingModulesLabel(status: PyGanBackendStatus): string {
  if (status.available) return "none";
  return status.missing_modules.join(", ") || "PyGan modules";
}

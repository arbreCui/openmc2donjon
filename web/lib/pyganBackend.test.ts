import { describe, expect, it } from "vitest";
import type { PyGanBackendStatus } from "./api";
import {
  PYGAN_CONVERTER_HREF,
  pyganCompareAvailability,
  pyganMissingModulesLabel,
} from "./pyganBackend";

describe("pygan backend helpers", () => {
  it("opens Converter with the PyGan writer and production checks selected", () => {
    expect(PYGAN_CONVERTER_HREF).toBe(
      "/convert?writer_backend=pygan&check=1&production=1#convert-component",
    );
  });

  it("keeps live writer comparison disabled while status is loading", () => {
    expect(pyganCompareAvailability(null)).toMatchObject({
      canRun: false,
    });
  });

  it("allows mock comparison even without local PyGan modules", () => {
    expect(
      pyganCompareAvailability(status({ available: false, mock_mode: true })),
    ).toMatchObject({
      canRun: true,
    });
  });

  it("allows live comparison when PyGan is importable", () => {
    expect(
      pyganCompareAvailability(status({ available: true, mock_mode: false })),
    ).toMatchObject({
      canRun: true,
    });
  });

  it("explains missing modules for unavailable live PyGan", () => {
    const unavailable = status({
      available: false,
      mock_mode: false,
      missing_modules: ["lcm", "cle2000"],
    });

    expect(pyganCompareAvailability(unavailable)).toMatchObject({
      canRun: false,
    });
    expect(pyganCompareAvailability(unavailable).hint).toContain("lcm, cle2000");
    expect(pyganMissingModulesLabel(unavailable)).toBe("lcm, cle2000");
  });
});

function status(
  overrides: Partial<PyGanBackendStatus>,
): PyGanBackendStatus {
  return {
    available: true,
    role: "optional PyGan writer backend",
    install_hint: "install PyGan",
    modules: [],
    missing_modules: [],
    mock_mode: false,
    ...overrides,
  };
}

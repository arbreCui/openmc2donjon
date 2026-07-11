import { describe, expect, it } from "vitest";
import type { PyGanBackendStatus } from "./api";
import {
  convertWriterBackendOptions,
  convertWriterBackendResultLabel,
  convertWriterBackendShortLabel,
} from "./convertWriterBackend";

describe("convert writer backend helpers", () => {
  it("keeps the built-in ASCII writer as the enabled default option", () => {
    const [ascii, pygan] = convertWriterBackendOptions(null);

    expect(ascii.id).toBe("ascii");
    expect(ascii.badge).toBe("default");
    expect(ascii.disabled).toBe(false);
    expect(ascii.body).toContain("normal production route");
    expect(pygan.id).toBe("pygan");
    expect(pygan.disabled).toBe(true);
    expect(pygan.badge).toBe("checking");
  });

  it("enables PyGan only when the backend can import it", () => {
    const options = convertWriterBackendOptions(pyganStatus(true));
    const pygan = options.find((option) => option.id === "pygan");

    expect(pygan?.disabled).toBe(false);
    expect(pygan?.badge).toBe("optional");
    expect(pygan?.detail).toContain("writer comparison");
  });

  it("explains missing PyGan modules without disabling ASCII", () => {
    const options = convertWriterBackendOptions(pyganStatus(false));
    const ascii = options.find((option) => option.id === "ascii");
    const pygan = options.find((option) => option.id === "pygan");

    expect(ascii?.disabled).toBe(false);
    expect(pygan?.disabled).toBe(true);
    expect(pygan?.badge).toBe("unavailable");
    expect(pygan?.detail).toContain("lcm");
  });

  it("uses short and result labels consistently", () => {
    expect(convertWriterBackendShortLabel("ascii")).toBe("ASCII writer");
    expect(convertWriterBackendShortLabel("pygan")).toBe("PyGan writer");
    expect(convertWriterBackendResultLabel("ascii")).toBe(
      "built-in ASCII writer",
    );
    expect(convertWriterBackendResultLabel("pygan")).toBe("PyGan LCM exporter");
  });
});

function pyganStatus(available: boolean): PyGanBackendStatus {
  return {
    available,
    role: "optional PyGan writer backend",
    install_hint: "install PyGan",
    modules: [],
    missing_modules: available ? [] : ["lcm", "cle2000"],
  };
}

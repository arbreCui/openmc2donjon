import { afterEach, describe, expect, it, vi } from "vitest";
import { copyText } from "./copyText";

function stubDocument(execCommandResult: boolean) {
  const element = {
    value: "",
    setAttribute: vi.fn(),
    style: {} as Record<string, string>,
    select: vi.fn(),
  };
  vi.stubGlobal("document", {
    createElement: vi.fn(() => element),
    execCommand: vi.fn(() => execCommandResult),
    body: { appendChild: vi.fn(), removeChild: vi.fn() },
  });
  return element;
}

describe("copyText", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reports success when the async clipboard API resolves", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    await expect(copyText("openmc2donjon serve")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("openmc2donjon serve");
  });

  it("reports success when the textarea fallback copies", async () => {
    vi.stubGlobal("navigator", {});
    const element = stubDocument(true);

    await expect(copyText("openmc2donjon serve")).resolves.toBe(true);
    expect(element.value).toBe("openmc2donjon serve");
  });

  it("reports failure when both clipboard paths fail", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    stubDocument(false);

    await expect(copyText("openmc2donjon serve")).resolves.toBe(false);
  });
});

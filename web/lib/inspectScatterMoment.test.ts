import { describe, expect, it } from "vitest";
import { scatterMomentClickAction } from "./inspectScatterMoment";

describe("scatterMomentClickAction", () => {
  it("switches when a different moment is clicked", () => {
    expect(scatterMomentClickAction(1, 0, false)).toBe("switch");
    expect(scatterMomentClickAction(0, 1, true)).toBe("switch");
  });

  it("retries when the failed moment is re-clicked", () => {
    // Regression: after a failed P1 fetch the selector shows P1 while
    // the heatmap still draws P0; re-clicking P1 must re-fire the
    // request instead of bailing out on unchanged state.
    expect(scatterMomentClickAction(1, 1, true)).toBe("retry");
  });

  it("ignores re-clicks of a successfully loaded moment", () => {
    expect(scatterMomentClickAction(1, 1, false)).toBe("ignore");
  });
});

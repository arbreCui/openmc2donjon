import { describe, expect, it } from "vitest";
import { ACCEPTED_VALIDATION_ENTRIES } from "./acceptedValidation";

describe("accepted validation entries", () => {
  it("keeps the three validation credentials in stable order", () => {
    expect(ACCEPTED_VALIDATION_ENTRIES.map((entry) => entry.id)).toEqual([
      "c5g7-cartesian",
      "irena30-hex",
      "openmc-sph-equivalence",
    ]);
  });

  it("records the accepted benchmark numbers verbatim", () => {
    const [c5g7, irena, sph] = ACCEPTED_VALIDATION_ENTRIES;

    expect(c5g7.body).toContain("OpenMC reference k 1.18798");
    expect(c5g7.body).toContain("diffusion k 1.1896194");
    expect(c5g7.body).toContain("SPN3 k 1.1912802");

    expect(irena.body).toContain("-9 pcm at 21 pcm sigma");
    expect(irena.body).toContain("+29 pcm with a different seed");
    expect(irena.body).toContain("1.27% worst / 0.47% RMS");

    expect(sph.body).toContain("rate-preserving target");
    expect(sph.body).toContain("IRENA Pb-reflector line");
    expect(sph.body).toContain("freeze groups {1, 31}");
    expect(sph.body).toContain("2-3 iterations");
  });
});

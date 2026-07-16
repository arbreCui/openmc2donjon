import { describe, expect, it } from "vitest";
import {
  NATIVE_SPH_CONTRACT,
  OPENMC_SIDE_SPH_CONTRACT,
  equivalenceAppliedHandoffHref,
  equivalenceConverterReferenceHref,
  equivalenceOperationHref,
  equivalenceRouteHref,
  resolveEquivalenceContract,
  resolveEquivalenceRoute,
} from "./equivalenceRoutes";

describe("equivalence routes", () => {
  it("routes the default native DRAGON SPH reference through native-sph Converter", () => {
    const contract = resolveEquivalenceContract(null, false);
    const href = equivalenceConverterReferenceHref({ contract });

    expect(contract).toBe(NATIVE_SPH_CONTRACT);
    expect(href).toBe(
      "/convert?contract=native-sph&format=macrolib&check=1&production=1",
    );
    expect(href).not.toContain("physical-sph");
  });

  it("preserves an explicitly selected OpenMC MG-side physical-SPH contract", () => {
    expect(resolveEquivalenceContract("physical-sph", false)).toBe(
      "physical-sph",
    );
  });

  it("keeps project and component context on the Converter reference route", () => {
    expect(
      equivalenceConverterReferenceHref({
        contract: NATIVE_SPH_CONTRACT,
        projectRoot: "/runs/core candidate",
        componentId: "fullcore",
      }),
    ).toBe(
      "/convert?contract=native-sph&format=macrolib&check=1&production=1&project=%2Fruns%2Fcore+candidate&component=fullcore",
    );
  });

  it("separates the native and optional OpenMC-side routes at the top level", () => {
    expect(resolveEquivalenceRoute(null, false)).toBe("native");
    expect(resolveEquivalenceRoute(null, true)).toBe("openmc-side");
    expect(resolveEquivalenceRoute(null, false, "physical-sph")).toBe(
      "openmc-side",
    );
    expect(resolveEquivalenceContract("native-sph", false, "openmc-side")).toBe(
      OPENMC_SIDE_SPH_CONTRACT,
    );
  });

  it("keeps generic project and component context while switching routes", () => {
    expect(
      equivalenceRouteHref({
        route: "openmc-side",
        projectRoot: "/runs/model",
        componentId: "reflector-a",
      }),
    ).toBe(
      "/equivalence?route=openmc-side&contract=physical-sph&kind=openmc-sph-sidecar&project=%2Fruns%2Fmodel&component=reflector-a",
    );
    expect(
      equivalenceOperationHref({
        kind: "apply-sph",
        projectRoot: "/runs/model",
        componentId: "reflector-a",
      }),
    ).toBe(
      "/equivalence?route=openmc-side&kind=apply-sph&contract=physical-sph&project=%2Fruns%2Fmodel&component=reflector-a",
    );
    expect(
      equivalenceAppliedHandoffHref({
        inputH5: "/runs/model/applied.h5",
        projectRoot: "/runs/model",
        componentId: "reflector-a",
      }),
    ).toBe(
      "/convert?contract=physical-sph&check=1&production=1&input=%2Fruns%2Fmodel%2Fapplied.h5&project=%2Fruns%2Fmodel&component=reflector-a",
    );
  });
});

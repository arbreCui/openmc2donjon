import { WITHDRAWN_COLORSET_CONTRACT } from "./colorsetWorkflow";

export const NATIVE_SPH_CONTRACT = "native-sph";
export const OPENMC_SIDE_SPH_CONTRACT = "physical-sph";

export type EquivalenceRoute = "native" | "openmc-side";

export function resolveEquivalenceRoute(
  explicitRoute: string | null,
  operationSelected: boolean,
  explicitContract?: string | null,
): EquivalenceRoute {
  if (explicitRoute === "native" || explicitRoute === "openmc-side") {
    return explicitRoute;
  }
  return operationSelected || explicitContract === OPENMC_SIDE_SPH_CONTRACT
    ? "openmc-side"
    : "native";
}

export function resolveEquivalenceContract(
  explicitContract: string | null,
  withdrawnColorset: boolean,
  route?: EquivalenceRoute,
): string {
  if (route === "openmc-side" && !withdrawnColorset) {
    return OPENMC_SIDE_SPH_CONTRACT;
  }
  return (
    explicitContract ??
    (withdrawnColorset ? WITHDRAWN_COLORSET_CONTRACT : NATIVE_SPH_CONTRACT)
  );
}

export function equivalenceConverterReferenceHref({
  contract,
  projectRoot,
  componentId,
}: {
  contract: string;
  projectRoot?: string;
  componentId?: string | null;
}): string {
  const params = new URLSearchParams({
    contract,
    format: "macrolib",
    check: "1",
    production: "1",
  });
  if (projectRoot) params.set("project", projectRoot);
  if (componentId) params.set("component", componentId);
  return `/convert?${params.toString()}`;
}

export function equivalenceRouteHref({
  route,
  projectRoot,
  componentId,
  colorsetId,
}: {
  route: EquivalenceRoute;
  projectRoot?: string;
  componentId?: string | null;
  colorsetId?: string | null;
}): string {
  const params = new URLSearchParams({ route });
  params.set(
    "contract",
    route === "openmc-side" ? OPENMC_SIDE_SPH_CONTRACT : NATIVE_SPH_CONTRACT,
  );
  if (route === "openmc-side") params.set("kind", "openmc-sph-sidecar");
  if (projectRoot) params.set("project", projectRoot);
  if (componentId) params.set("component", componentId);
  if (colorsetId) params.set("colorset", colorsetId);
  return `/equivalence?${params.toString()}`;
}

export function equivalenceOperationHref({
  kind,
  projectRoot,
  componentId,
  colorsetId,
}: {
  kind: string;
  projectRoot?: string;
  componentId?: string | null;
  colorsetId?: string | null;
}): string {
  const params = new URLSearchParams({
    route: "openmc-side",
    kind,
    contract: OPENMC_SIDE_SPH_CONTRACT,
  });
  if (projectRoot) params.set("project", projectRoot);
  if (componentId) params.set("component", componentId);
  if (colorsetId) params.set("colorset", colorsetId);
  return `/equivalence?${params.toString()}`;
}

export function equivalenceAppliedHandoffHref({
  inputH5,
  projectRoot,
  componentId,
}: {
  inputH5: string;
  projectRoot?: string;
  componentId?: string | null;
}): string {
  const params = new URLSearchParams({
    contract: OPENMC_SIDE_SPH_CONTRACT,
    check: "1",
    production: "1",
    input: inputH5,
  });
  if (projectRoot) params.set("project", projectRoot);
  if (componentId) params.set("component", componentId);
  return `/convert?${params.toString()}`;
}

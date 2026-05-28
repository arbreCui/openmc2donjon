export interface NavItem {
  href: string;
  label: string;
  description?: string;
  match: readonly string[];
}

export const PRIMARY_NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/",
    label: "Home",
    match: ["/"],
  },
  {
    href: "/openmc?workflow=two-step&equivalence=sph&production=1",
    label: "OpenMC SPH",
    match: ["/openmc"],
  },
  {
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    label: "Convert",
    match: ["/convert"],
  },
  {
    href: "/inspect",
    label: "Inspect",
    match: ["/inspect"],
  },
  {
    href: "/commands",
    label: "Commands",
    match: ["/commands"],
  },
] as const;

export const SECONDARY_NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/equivalence?kind=adf-sidecar",
    label: "ADF/SPH sidecars",
    description: "Build sidecar commands and augmentation previews.",
    match: ["/equivalence"],
  },
  {
    href: "/builder?command=bundle",
    label: "Bundle handoff",
    description: "Package HDF5, ASCII, reports, and DONJON cards.",
    match: ["/builder"],
  },
  {
    href: "/donjon",
    label: "DONJON cards",
    description: "Review consumption paths and generated input cards.",
    match: ["/donjon"],
  },
  {
    href: "/pygan",
    label: "PyGan option",
    description: "Optional backend diagnostics; ASCII remains default.",
    match: ["/pygan"],
  },
  {
    href: "/settings",
    label: "Settings",
    description: "Local browser preferences and default paths.",
    match: ["/settings"],
  },
] as const;

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.match.some((prefix) => {
    if (prefix === "/") {
      return pathname === "/";
    }
    return pathname === prefix || pathname.startsWith(`${prefix}/`);
  });
}

export function isAnyNavItemActive(items: readonly NavItem[], pathname: string): boolean {
  return items.some((item) => isNavItemActive(item, pathname));
}

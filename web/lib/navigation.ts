export interface NavItem {
  href: string;
  label: string;
  description?: string;
  match: readonly string[];
}

export const PRIMARY_NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    label: "Convert",
    match: ["/convert"],
  },
  {
    href: "/openmc?workflow=two-step&equivalence=sph&production=1",
    label: "OpenMC prep",
    match: ["/openmc"],
  },
  {
    href: "/inspect",
    label: "Review HDF5",
    match: ["/inspect"],
  },
] as const;

export const SECONDARY_NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/commands",
    label: "Commands",
    description: "Advanced CLI reference and web command links.",
    match: ["/commands"],
  },
  {
    href: "/equivalence?kind=adf-sidecar",
    label: "ADF/SPH sidecars",
    description: "Build sidecar commands after the main path is chosen.",
    match: ["/equivalence"],
  },
  {
    href: "/builder?command=bundle",
    label: "Bundle",
    description: "Package HDF5, ASCII, reports, and DONJON cards.",
    match: ["/builder"],
  },
  {
    href: "/donjon",
    label: "DONJON",
    description: "Review consumption paths and input-card guidance.",
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

export interface NavItem {
  href: string;
  label: string;
  description?: string;
  match: readonly string[];
}

export const PRIMARY_NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/convert?intent=direct-convert&format=multicompo",
    label: "Convert",
    match: ["/convert"],
  },
  {
    href: "/openmc?workflow=two-step&production=1",
    label: "OpenMC prep",
    match: ["/openmc"],
  },
  {
    href: "/inspect",
    label: "Inspect HDF5",
    match: ["/inspect"],
  },
  {
    href: "/donjon",
    label: "DONJON",
    description: "Generate the DONJON deck that consumes your ASCII.",
    match: ["/donjon"],
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
    href: "/builder",
    label: "Command builder",
    description: "Fill inputs and copy the exact CLI for auxiliary commands.",
    match: ["/builder"],
  },
  {
    href: "/equivalence",
    label: "SPH/ADF sidecars",
    description: "Build SPH sidecar commands; ADF/DF rides along as converter data.",
    match: ["/equivalence"],
  },
  {
    href: "/pygan",
    label: "PyGan validation",
    description: "PyGan writer diagnostics and ASCII-vs-PyGan comparison.",
    match: ["/pygan"],
  },
  {
    href: "/settings",
    label: "Settings",
    description: "Default path prefix for path inputs and the file browser.",
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

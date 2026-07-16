export interface NavItem {
  href: string;
  label: string;
  step?: string;
  description?: string;
  match: readonly string[];
}

export const PRIMARY_NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/convert",
    label: "Converter",
    description: "Validate one MGXS handoff and write a traceable DONJON object.",
    match: ["/convert"],
  },
  {
    href: "/inspect",
    label: "Inspect",
    description: "Open an OpenMC HDF5 directly; visualize MGXS data or inspect any HDF5 structure read-only.",
    match: ["/inspect"],
  },
  {
    href: "/projects",
    label: "Projects",
    description: "Optionally coordinate repeated or multi-component Converter jobs.",
    match: ["/projects"],
  },
  {
    href: "/docs",
    label: "Documentation",
    description: "Read the product boundary, input contract, and verified workflow guides.",
    match: ["/docs"],
  },
] as const;

export const WORKFLOW_NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/openmc",
    label: "OpenMC MGXS",
    description: "Prepare or export an OpenMC MGXS HDF5 for your model.",
    match: ["/openmc"],
  },
  {
    href: "/equivalence",
    label: "SPH",
    description: "Close the fine-to-coarse model with native DRAGON SPH; OpenMC MG is optional.",
    match: ["/equivalence"],
  },
  {
    href: "/donjon",
    label: "DONJON",
    description: "Connect Converter outputs to a user-defined DRAGON/DONJON model.",
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
    href: "/pygan",
    label: "PyGan writer",
    description: "Optional PyGan/LCM writer diagnostics and ASCII-vs-PyGan comparison.",
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

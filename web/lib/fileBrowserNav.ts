import { pathCrumbs } from "./fileBrowserPath";

/**
 * Parent directory of a *requested* path, for recovering from a failed
 * listing: after a 404 there is no successful listing to supply a
 * backend-resolved ``parent``, so ↑ parent (and the breadcrumb) must
 * derive navigation targets from the path the user asked for or the
 * dialog is stuck on the error card. Returns ``null`` at a root
 * (nothing above it to climb to).
 */
export function requestedPathParent(path: string): string | null {
  const crumbs = pathCrumbs(path);
  return crumbs.length > 1 ? crumbs[crumbs.length - 2].path : null;
}

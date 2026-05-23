/**
 * Path helpers for the file-browser modal.
 *
 * Lives outside the component so the splitting rules (which include a
 * mock-mode special case) can be unit-tested without spinning up React.
 */

export interface Crumb {
  /** What to render in the breadcrumb button. */
  label: string;
  /** What to pass to ``setCurrentPath`` when this crumb is picked. */
  path: string;
}

/**
 * Split an absolute path into clickable breadcrumb segments.
 *
 * Mock-mode shortcut: ``/mock/home/...`` collapses the ``/mock/home``
 * prefix into a single ``home`` crumb so the breadcrumb doesn't lead
 * with the mock-tree scaffolding; the click target still navigates to
 * the real ``/mock/home`` path the backend expects.
 *
 * Inputs that aren't absolute paths (``~``, a relative slug) shouldn't
 * appear in practice - the backend resolves them before sending the
 * listing back - but we render them as a single crumb so the UI never
 * blows up if it ever does see one.
 */
export function pathCrumbs(path: string): Crumb[] {
  if (path === "/mock/home" || path.startsWith("/mock/home/")) {
    const crumbs: Crumb[] = [{ label: "home", path: "/mock/home" }];
    const tail =
      path === "/mock/home" ? "" : path.slice("/mock/home/".length);
    if (tail) {
      let cur = "/mock/home";
      for (const part of tail.split("/").filter(Boolean)) {
        cur = `${cur}/${part}`;
        crumbs.push({ label: part, path: cur });
      }
    }
    return crumbs;
  }
  if (path.startsWith("/")) {
    const crumbs: Crumb[] = [{ label: "/", path: "/" }];
    let cur = "";
    for (const part of path.split("/").filter(Boolean)) {
      cur = `${cur}/${part}`;
      crumbs.push({ label: part, path: cur });
    }
    return crumbs;
  }
  return [{ label: path || "/", path }];
}

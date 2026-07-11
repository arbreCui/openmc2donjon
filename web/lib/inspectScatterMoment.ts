export type ScatterMomentClickAction = "switch" | "retry" | "ignore";

/**
 * Decide what a click on a scatter-moment button does.
 *
 * The selector reflects the *requested* moment while the heatmap can
 * still be drawing the previously *loaded* one (the page keeps the last
 * good payload on screen during fetches and after failures). Clicking a
 * different moment always switches; re-clicking the already-requested
 * moment is a retry when that request failed — never a silent no-op
 * that strands the user on a stale heatmap.
 */
export function scatterMomentClickAction(
  clicked: number,
  requested: number,
  requestFailed: boolean,
): ScatterMomentClickAction {
  if (clicked !== requested) return "switch";
  return requestFailed ? "retry" : "ignore";
}

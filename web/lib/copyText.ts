/**
 * Copy text to the clipboard, reporting whether it actually landed.
 *
 * Tries the async clipboard API first, then falls back to a temporary
 * textarea + ``document.execCommand("copy")`` for browsers that deny
 * the API on a local/dev (plain-http) origin. Returns ``true`` only
 * when one of the two paths reported success, so callers can show a
 * real failure state instead of a false "Copied".
 */
export async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // Fall back to a temporary textarea when the browser denies the
      // async clipboard API on a local/dev origin.
    }
  }
  const element = document.createElement("textarea");
  element.value = value;
  element.setAttribute("readonly", "true");
  element.style.position = "fixed";
  element.style.opacity = "0";
  document.body.appendChild(element);
  element.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(element);
  return copied;
}

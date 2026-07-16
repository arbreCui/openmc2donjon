export function converterQuickStartHref(
  inputPath: string,
): string {
  const params = new URLSearchParams({
    check: "1",
    production: "1",
  });
  const input = inputPath.trim();
  if (input) params.set("input", input);
  return `/convert?${params.toString()}#convert-component`;
}

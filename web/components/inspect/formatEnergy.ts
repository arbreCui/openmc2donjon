/**
 * Format a neutron energy in eV with a unit prefix that matches the
 * usual reactor-physics conventions. Used in summary detail rows and,
 * once S3 lands, in spectrum-plot hover tooltips.
 */
export function formatEnergy(value: number): string {
  if (value === 0) return "0 eV";
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${(value / 1e6).toPrecision(3)} MeV`;
  if (abs >= 1e3) return `${(value / 1e3).toPrecision(3)} keV`;
  if (abs >= 1) return `${value.toPrecision(3)} eV`;
  return `${value.toExponential(2)} eV`;
}

import { MixtureSummary } from "@/lib/api";

export default function MixtureTable({
  mixtures,
}: {
  mixtures: MixtureSummary[];
}) {
  if (mixtures.length === 0) {
    return (
      <p className="text-sm text-[var(--fg-3)]">No mixtures in this file.</p>
    );
  }
  return (
    <div className="glass rounded-xl p-1 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-[12px] uppercase tracking-wider text-[var(--fg-3)]">
          <tr className="text-left">
            <Th>Mixture</Th>
            <Th>Fiss</Th>
            <Th align="right">Volume</Th>
            <Th align="right">Required</Th>
            <Th align="right">ADF faces</Th>
            <Th>SPH</Th>
            <Th>Scatter</Th>
          </tr>
        </thead>
        <tbody>
          {mixtures.map((m) => (
            <tr
              key={m.name}
              className="border-t border-[var(--edge)] hover:bg-white/[0.03]"
            >
              <Td>
                <span className="font-mono">{m.name}</span>
              </Td>
              <Td>
                {m.fissionable === null ? (
                  <span className="text-[var(--fg-3)]">—</span>
                ) : m.fissionable ? (
                  <span className="text-emerald-300">✓</span>
                ) : (
                  <span className="text-[var(--fg-3)]">·</span>
                )}
              </Td>
              <Td align="right" mono>
                {m.volume == null ? "—" : m.volume.toFixed(2)}
              </Td>
              <Td align="right" mono>
                {m.required_present}/{m.required_total}
              </Td>
              <Td align="right" mono>
                {m.adf_faces.length}
              </Td>
              <Td>
                {m.sph ? (
                  <span className="text-emerald-300">✓</span>
                ) : (
                  <span className="text-[var(--fg-3)]">·</span>
                )}
              </Td>
              <Td mono>
                {m.scatter_shape ? `[${m.scatter_shape.join(",")}]` : "—"}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={`px-3 py-2 ${align === "right" ? "text-right" : "text-left"}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  mono = false,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  mono?: boolean;
}) {
  return (
    <td
      className={
        "px-3 py-2 " +
        (align === "right" ? "text-right " : "") +
        (mono ? "font-mono " : "")
      }
    >
      {children}
    </td>
  );
}

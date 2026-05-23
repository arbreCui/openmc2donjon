import { HandoffInspection } from "@/lib/api";
import { formatEnergy } from "./formatEnergy";

export default function Summary({ data }: { data: HandoffInspection }) {
  return (
    <div className="glass rounded-xl p-5">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-[12px] uppercase tracking-wider text-[var(--fg-3)]">
            Path
          </div>
          <div className="font-mono text-sm break-all">{data.path}</div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <OkBadge ok={data.ok} />
          <MeshBadge match={data.mesh_match} />
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-4 tab-num text-sm">
        <Stat label="Mixtures" value={data.mixture_count} />
        <Stat label="Energy groups" value={data.energy_groups ?? "—"} />
        <Stat
          label="Legendre"
          value={
            data.legendre_order == null ? "—" : `P${data.legendre_order}`
          }
        />
        <Stat
          label="State points"
          value={data.state_points ?? data.calculation_count}
        />
        <Stat
          label="Fissionable"
          value={`${data.fissionable_mixtures} / ${data.mixture_count}`}
        />
        <Stat
          label="ADF mixtures"
          value={`${data.adf_mixtures} / ${data.mixture_count}`}
        />
        <Stat label="SPH calcs" value={data.sph_calculations} />
        <Stat
          label="H-factor"
          value={`${data.h_factor} / ${data.mixture_count}`}
        />
      </dl>

      <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4 text-[13px] tab-num">
        <DetailRow
          label="Energy range"
          value={
            data.energy_min != null && data.energy_max != null
              ? `${formatEnergy(data.energy_min)} — ${formatEnergy(
                  data.energy_max,
                )}`
              : "—"
          }
        />
        <DetailRow
          label="Bounds shape"
          value={
            data.energy_bounds_shape
              ? `[${data.energy_bounds_shape.join(", ")}]`
              : "—"
          }
        />
        <DetailRow
          label="ADF faces"
          value={data.adf_faces.length ? data.adf_faces.join(", ") : "—"}
        />
        <DetailRow
          label="Scatter axes"
          value={
            data.scatter_axes.length ? data.scatter_axes.join(", ") : "—"
          }
        />
      </div>

      {data.issues.length > 0 ? (
        <div className="mt-5 text-[13px]">
          <div className="text-amber-300 font-semibold mb-1">
            Issues ({data.issues.length})
          </div>
          <ul className="list-disc pl-5 space-y-0.5 text-[var(--fg-1)]">
            {data.issues.map((issue, index) => (
              <li key={index}>{issue}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function OkBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="text-emerald-300 font-semibold">OK</span>
  ) : (
    <span className="text-rose-300 font-semibold">FAIL</span>
  );
}

function MeshBadge({
  match,
}: {
  match: HandoffInspection["mesh_match"];
}) {
  if (!match) {
    return (
      <span className="px-2 py-0.5 rounded-md border border-[var(--edge)] bg-white/[0.03] text-[var(--fg-3)] text-[12px]">
        no mesh match
      </span>
    );
  }
  return (
    <span
      className="px-2 py-0.5 rounded-md border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-emerald-200 text-[12px]"
      title={match.description ?? undefined}
    >
      {match.short ?? match.name ?? match.id}
    </span>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-0.5 text-lg font-semibold">{value}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-[var(--edge)] pb-2">
      <span className="text-[var(--fg-3)]">{label}</span>
      <span className="font-mono text-right">{value}</span>
    </div>
  );
}

import type { OpenmcProvenance } from "@/lib/api";
import {
  openmcProvenanceView,
  provenanceArtifact,
  shortDigest,
} from "@/lib/openmcProvenance";

export default function OpenmcProvenanceCard({
  provenance,
  compact = false,
}: {
  provenance: OpenmcProvenance;
  compact?: boolean;
}) {
  const view = openmcProvenanceView(provenance);
  const recipe = provenanceArtifact(provenance, "recipe");
  const statepoint = provenanceArtifact(provenance, "statepoint");
  const settings = provenanceArtifact(provenance, "settings");
  const nuclear = provenance.nuclear_data;
  const issueList = [
    ...(provenance.integrity?.issues ?? []),
    ...provenance.issues,
  ].filter((value, index, values) => values.indexOf(value) === index);

  return (
    <section className={`rounded-xl border p-4 ${toneClass(view.tone)}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.15em] opacity-80">
            OpenMC source provenance
          </div>
          <h3 className="mt-1 text-sm font-semibold">{view.label}</h3>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 opacity-85">
            {view.summary}
          </p>
        </div>
        <code className="rounded border border-current/15 bg-black/10 px-2 py-1 text-[10px]">
          record {shortDigest(provenance.digest_sha256)}
        </code>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <Capability
          label="Frozen MGXS reference"
          value={view.referenceBound && view.integrityOk}
        />
        <Capability label="Export replay" value={view.exportReplayable} />
        <Capability
          label="Transport replay"
          value={view.transportReproducible}
        />
      </div>

      {!compact ? (
        <>
          <div className="mt-3 grid gap-2 text-[11px] sm:grid-cols-2 lg:grid-cols-5">
            <Datum label="OpenMC" value={provenance.openmc.version} />
            <Datum label="openmc2donjon" value={provenance.producer.version} />
            <Datum
              label="MGXS payload"
              value={shortDigest(provenance.handoff.payload_sha256)}
            />
            <Datum
              label="Run histories"
              value={runSize(provenance)}
            />
            <Datum
              label="Nuclear data"
              value={
                nuclear.libraries_manifest_sha256
                  ? `${nuclear.library_count} file(s) · ${shortDigest(
                      nuclear.libraries_manifest_sha256,
                    )}`
                  : "not content-bound"
              }
            />
          </div>

          <div className="mt-3 space-y-1.5 text-[11px]">
            <ArtifactRow label="Recipe" artifact={recipe} />
            <ArtifactRow label="Statepoint" artifact={statepoint} />
            <ArtifactRow label="Settings" artifact={settings} />
          </div>
        </>
      ) : null}

      {issueList.length > 0 ? (
        <div className="mt-3 rounded-md border border-current/15 bg-black/10 px-3 py-2 text-[11px] leading-5">
          <div className="font-semibold">Still missing or invalid</div>
          <ul className="mt-1 list-disc pl-4 opacity-85">
            {issueList.slice(0, 5).map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
          {issueList.length > 5 ? (
            <div className="mt-1 opacity-70">
              {issueList.length - 5} more item(s) are recorded in the provenance JSON.
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function Capability({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="rounded-md border border-current/15 bg-black/10 px-3 py-2 text-[11px]">
      <div className="opacity-70">{label}</div>
      <div className="mt-0.5 font-semibold">{value ? "PASS" : "NOT READY"}</div>
    </div>
  );
}

function Datum({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-md border border-current/10 bg-black/5 px-3 py-2">
      <div className="opacity-65">{label}</div>
      <div className="mt-0.5 break-words font-medium">{value ?? "not recorded"}</div>
    </div>
  );
}

function ArtifactRow({
  label,
  artifact,
}: {
  label: string;
  artifact: ReturnType<typeof provenanceArtifact>;
}) {
  return (
    <div className="grid gap-1 rounded-md border border-current/10 bg-black/5 px-3 py-2 sm:grid-cols-[90px_1fr_auto]">
      <span className="font-semibold">{label}</span>
      <code className="min-w-0 break-all opacity-80">
        {artifact?.path ?? "not recorded"}
      </code>
      <code className="opacity-70">{shortDigest(artifact?.sha256)}</code>
    </div>
  );
}

function runSize(provenance: OpenmcProvenance): string {
  const { particles, batches, inactive, seed } = provenance.simulation;
  if (particles == null && batches == null && seed == null) return "not recorded";
  return [
    particles == null ? null : `${particles} particles`,
    batches == null ? null : `${batches} batches`,
    inactive == null ? null : `${inactive} inactive`,
    seed == null ? null : `seed ${seed}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function toneClass(tone: "pass" | "warn" | "fail"): string {
  if (tone === "pass") {
    return "border-emerald-300/25 bg-emerald-300/[0.045] text-emerald-100";
  }
  if (tone === "warn") {
    return "border-amber-300/25 bg-amber-300/[0.045] text-amber-100";
  }
  return "border-rose-300/25 bg-rose-300/[0.045] text-rose-100";
}

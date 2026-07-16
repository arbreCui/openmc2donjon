"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import EvidenceLadder from "@/components/EvidenceLadder";
import { ApiError, OpenmcSphPhysicsSummary, api } from "@/lib/api";
import { openmcSphEvidenceLadder } from "@/lib/evidenceLadder";
import {
  evidenceAuditPresentation,
  formatScatterTreatment,
  formatPhysicsNumber,
  isNativeDragonSphSummary,
  nativeDragonSphAcceptancePassed,
  nativeSphValidatorHref,
  openmcSphConvertHref,
  productionEvidenceRows,
  reactionRatePreservationRows,
  sphUpdatePolicyRows,
  summaryStatus,
  topSphDeviationRows,
  verifiedForbiddenCorrectionAbsenceState,
} from "@/lib/openmcSphSummary";

type SummaryState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: OpenmcSphPhysicsSummary }
  | { kind: "error"; message: string; status?: number };

export default function OpenmcSphPhysicsSummaryCard({
  path,
  onPathChange,
  onBrowse,
  autoLoadPath = null,
}: {
  path: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
  autoLoadPath?: string | null;
}) {
  const [state, setState] = useState<SummaryState>({ kind: "idle" });

  useEffect(() => {
    // Deep links (?summary=...) promise the loaded evidence, so load it
    // without requiring a manual click on "Load summary".
    const trimmed = (autoLoadPath ?? "").trim();
    if (!trimmed) return;
    let cancelled = false;
    setState({ kind: "loading" });
    api
      .openmcSphSummary(trimmed)
      .then((data) => {
        if (!cancelled) setState({ kind: "ok", data });
      })
      .catch((err) => {
        if (!cancelled) setState(toErrorState(err));
      });
    return () => {
      cancelled = true;
    };
  }, [autoLoadPath]);

  async function load() {
    const trimmed = path.trim();
    if (!trimmed) {
      setState({
        kind: "error",
        message: "Choose a physics_summary.json file first.",
      });
      return;
    }
    setState({ kind: "loading" });
    try {
      const data = await api.openmcSphSummary(trimmed);
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  return (
    <section
      id="openmc-sph-summary"
      className="mt-4 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.04] p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-300">
            SPH physics summary
          </div>
          <h3 className="mt-1 text-sm font-semibold tracking-tight">
            Review physical equivalence and downstream evidence
          </h3>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            Load a `physics_summary.json` written by the preferred native
            DRAGON SPH validator or by the optional OpenMC CE/MG cross-check.
            The report identifies its route and never substitutes an empirical
            eigenvalue multiplier for physical closure.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto]">
        <input
          value={path}
          onChange={(event) => onPathChange(event.target.value)}
          aria-label="Physics summary JSON path"
          className="w-full min-w-0 rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-[12px] text-[var(--fg-0)]"
          placeholder="/path/to/handoff/physics_summary.json"
        />
        <button type="button" className="btn btn-secondary" onClick={onBrowse}>
          Browse
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={load}
          disabled={state.kind === "loading"}
        >
          {state.kind === "loading" ? "Loading…" : "Load summary"}
        </button>
      </div>

      <div className="mt-4">
        <SummaryBody state={state} />
      </div>
    </section>
  );
}

function SummaryBody({ state }: { state: SummaryState }) {
  if (state.kind === "idle") {
    return (
      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3 text-[12px] text-[var(--fg-2)]">
        After an SPH calculation, load its summary to review convergence,
        preserved rates, uncertainty, and the exact downstream artifacts.
      </div>
    );
  }
  if (state.kind === "loading") {
    return (
      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3 text-[12px] text-[var(--fg-2)]">
        Reading physics summary…
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="rounded-md border border-rose-400/25 bg-rose-400/[0.06] p-3">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Load failed"}
        </div>
        <div className="mt-1 text-[12px] text-[var(--fg-1)]">{state.message}</div>
      </div>
    );
  }

  const summary = state.data;
  const native = isNativeDragonSphSummary(summary);
  const status = summaryStatus(summary);
  const rows = topSphDeviationRows(summary);
  const policyRows = sphUpdatePolicyRows(summary);
  const reactionRows = reactionRatePreservationRows(summary);
  const evidenceRows = productionEvidenceRows(summary);
  const convertHref = openmcSphConvertHref(summary);
  const audit = summary.evidence_audit;
  const strictNativeAcceptance = nativeDragonSphAcceptancePassed(summary);
  const fixtureBacked =
    audit?.origin === "mock_fixture" || audit?.origin === "recorded_fixture";
  const handoffQualityPassed =
    native
      ? strictNativeAcceptance
      : status.tone === "pass" && summary.quality?.production_ready === true;
  const canOpenConverter =
    !native &&
    convertHref != null &&
    (audit == null ||
      audit.origin === "mock_fixture" ||
      audit.all_referenced_handoff_artifacts_present === true);
  const nativeMacrolib =
    summary.handoff.macrolib_ascii_path ?? summary.handoff.ascii_path;
  const nativeDonjonHref = nativeMacrolib
    ? `/donjon?ascii=${encodeURIComponent(nativeMacrolib)}&format=macrolib&nmix=${summary.mixture_count}&solver=spn`
    : null;
  const canUseNativeMacrolib =
    native &&
    nativeDonjonHref != null &&
    strictNativeAcceptance;
  const validatorHref = nativeSphValidatorHref(summary);
  const correctionAuditStatus =
    audit?.evidence_integrity?.forbidden_corrections?.status;
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {summary.route}
            </div>
            <div className="mt-1 text-sm font-semibold tracking-tight">
              {summary.mixture_count} mixtures · {summary.energy_groups} groups ·{" "}
              {formatScatterTreatment(summary)}
            </div>
          </div>
          <span
            className={
              "rounded border px-2 py-1 text-[10px] uppercase tracking-[0.14em] " +
              (status.tone === "pass"
                ? "border-emerald-300/30 text-emerald-300"
                : "border-amber-300/30 text-amber-300")
            }
          >
            {status.label}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-3xl text-[12px] text-[var(--fg-2)]">
            {status.detail}
          </p>
          {canUseNativeMacrolib && nativeDonjonHref ? (
            <div className="flex flex-wrap gap-2">
              <Link href={nativeDonjonHref} className="btn btn-primary text-[12px]">
                Use corrected MACROLIB in DONJON
              </Link>
              {validatorHref ? (
                <Link href={validatorHref} className="btn btn-secondary text-[12px]">
                  Rebuild validation command
                </Link>
              ) : null}
            </div>
          ) : native && validatorHref ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border border-amber-300/25 px-2 py-1 text-[11px] text-amber-200">
                Corrected MACROLIB is blocked until every physics gate passes
              </span>
              <Link href={validatorHref} className="btn btn-secondary text-[12px]">
                Rebuild validation command
              </Link>
            </div>
          ) : canOpenConverter && convertHref ? (
            <Link href={convertHref} className="btn btn-primary text-[12px]">
              {fixtureBacked
                ? "Preview fixture in Converter"
                : "Send SPH-augmented MGXS to Converter"}
            </Link>
          ) : (
            <span className="rounded border border-amber-300/25 px-2 py-1 text-[11px] text-amber-200">
              Referenced physics artifacts are not available
            </span>
          )}
        </div>
      </div>

      <EvidenceLadder
        title={native ? "Native DRAGON SPH evidence scope" : "OpenMC MG-side SPH evidence scope"}
        stages={openmcSphEvidenceLadder(summary)}
        compact
      />

      {audit ? <EvidenceSourceAudit summary={summary} /> : null}

      <div className="grid gap-2 md:grid-cols-4">
        <Stat label="SPH range" value={`${formatPhysicsNumber(summary.sph.minimum)} .. ${formatPhysicsNumber(summary.sph.maximum)}`} />
        <Stat label="max |SPH-1|" value={formatPhysicsNumber(summary.sph.max_abs_delta_from_unity)} />
        <Stat label="CE flux σ/μ max" value={formatPhysicsNumber(summary.flux_uncertainty.ce_max_relative_std_dev)} />
        <Stat
          label={native ? "native SPH iterations" : "MG flux σ/μ max"}
          value={
            native
              ? String(summary.native_sph?.iterations ?? "n/a")
              : formatPhysicsNumber(summary.flux_uncertainty.mg_max_relative_std_dev)
          }
        />
      </div>

      <div className="rounded-md border border-emerald-300/20 bg-emerald-300/[0.04] p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-emerald-300">
              SPH handoff evidence
            </div>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
              {native
                ? "These fields document the actual fine-to-coarse closure: OpenMC uncertainty, native DRAGON SPH convergence, conserved rates, and the final DONJON comparison. PASS is issued only by the declared statistical and physical gates."
                : "These fields document the optional OpenMC CE/MG-side SPH handoff: flux uncertainty, factor size, frozen-flux diagnostics, and exported NSPH. They do not create a physics-equivalence PASS by themselves."}
            </p>
          </div>
          <span
            className={
              "rounded border px-2 py-1 text-[10px] uppercase tracking-[0.14em] " +
              (handoffQualityPassed
                ? "border-emerald-300/30 text-emerald-300"
                : "border-amber-300/30 text-amber-300")
            }
          >
            {handoffQualityPassed ? "handoff quality pass" : "review required"}
          </span>
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-4">
          {evidenceRows.map((row) => (
            <div
              key={row.id}
              className="rounded border border-[var(--edge)] bg-black/15 p-2"
            >
              <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                {row.label}
              </div>
              <div className="mt-1 font-mono text-[13px] text-[var(--fg-0)]">
                {row.value}
              </div>
              <div className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
                {row.detail}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <EvidenceNote
            label="What it records"
            text={
              native
                ? "OpenMC fine-model reference rates and uncertainty, Converter MACROLIB, native DRAGON SPH convergence, corrected MACROLIB, and the verification solve."
                : "OpenMC CE reference flux, OpenMC MG macro flux on the same output regions, SPH(region, group), and the declared NSPH handoff."
            }
          />
          <EvidenceNote
            label="What it does not prove"
            text={
              native
                ? "A passing component or declared coarse-model closure is not automatically a full-core loading-map acceptance."
                : "This summary is not by itself a full-core benchmark or a DONJON k-effective validation; it is handoff evidence."
            }
          />
        </div>
      </div>

      {policyRows.length > 0 ? (
        <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
          <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            SPH update policy
          </div>
          <div className="grid gap-2 md:grid-cols-4">
            {policyRows.map((row) => (
              <div
                key={row.id}
                className="rounded border border-[var(--edge)] bg-white/[0.02] p-2"
              >
                <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                  {row.label}
                </div>
                <div className="mt-1 font-mono text-[13px] text-[var(--fg-0)]">
                  {row.value}
                </div>
                <div className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
                  {row.detail}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {reactionRows.length > 0 ? (
        <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
          <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            reaction-rate preservation
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {reactionRows.map((row) => (
              <div
                key={row.id}
                className="rounded border border-[var(--edge)] bg-white/[0.02] p-2"
              >
                <div className="text-[12px] font-semibold text-[var(--fg-1)]">
                  {row.label}
                </div>
                <div className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
                  {row.detail}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                  <span className="text-[var(--fg-3)]">max residual</span>
                  <span className="text-right font-mono text-[var(--fg-0)]">
                    {formatPhysicsNumber(row.maxResidual)}
                  </span>
                  <span className="text-[var(--fg-3)]">mean residual</span>
                  <span className="text-right font-mono text-[var(--fg-0)]">
                    {formatPhysicsNumber(row.meanResidual)}
                  </span>
                  <span className="text-[var(--fg-3)]">valid bins</span>
                  <span className="text-right font-mono text-[var(--fg-0)]">
                    {row.validBins ?? "n/a"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {native ? <NativeClosureDetails summary={summary} /> : null}

      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
        <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
          largest SPH corrections
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          {rows.map((row) => (
            <div key={row.mixture} className="rounded border border-[var(--edge)] bg-white/[0.02] p-2">
              <div className="font-mono text-[12px] text-[var(--fg-1)]">
                {row.mixture}
              </div>
              <div className="mt-1 text-[11px] text-[var(--fg-2)]">
                range {formatPhysicsNumber(row.sph_min)} .. {formatPhysicsNumber(row.sph_max)}
              </div>
              <div className="text-[11px] text-[var(--fg-3)]">
                max |SPH-1| = {formatPhysicsNumber(row.max_abs_sph_minus_1)}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3 text-[12px] text-[var(--fg-2)]">
        {native ? (
          <>
            Converter produced the uncorrected reference MACROLIB first. DRAGON
            then solved native `SPH:` on the declared coarse geometry and wrote
            the corrected `NSPH` MACROLIB.{" "}
            {correctionAuditStatus === "verified_absent"
              ? "The live execution-deck and result-listing audit verified that no ADF or global empirical coefficient was used."
              : correctionAuditStatus === "forbidden_correction_observed"
                ? "The live audit observed a forbidden ADF or empirical correction, so this result is rejected."
                : "The absence of ADF and empirical corrections is not proved by live deck/listing evidence, so this result remains blocked."}
          </>
        ) : (
          <>
            SPH is carried as DONJON `NSPH` equivalence factors. The report says
            `applied_to_xs = {String(summary.sph.applied_to_xs)}`, so the macro
            cross sections {summary.sph.applied_to_xs
              ? "in this HDF5 were already divided by the SPH factors (apply-sph route)."
              : "were not silently multiplied in the HDF5."}
          </>
        )}
      </div>
    </div>
  );
}

function EvidenceSourceAudit({
  summary,
}: {
  summary: OpenmcSphPhysicsSummary;
}) {
  const audit = summary.evidence_audit!;
  const presentation = evidenceAuditPresentation(summary);
  const integrity = audit.evidence_integrity;
  const integrityLabel =
    integrity?.verified === true
      ? "LIVE INTEGRITY VERIFIED"
      : integrity?.verified === false
        ? "LIVE INTEGRITY BLOCKED"
        : "INTEGRITY NOT EVALUATED";
  const origin =
    audit.origin === "live_file"
      ? "live summary file"
      : audit.origin === "mock_fixture"
        ? "mock fixture"
        : "recorded fixture snapshot";
  return (
    <div className="rounded-md border border-amber-300/20 bg-amber-300/[0.04] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-amber-200">
            evidence provenance
          </div>
          <div className="mt-1 text-[12px] text-[var(--fg-1)]">
            Source: <span className="font-mono">{origin}</span>
          </div>
        </div>
        <span className="rounded border border-amber-300/25 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-amber-100">
          {integrityLabel}
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {audit.referenced_handoff_artifacts.map((artifact) => (
          <div
            key={artifact.label}
            className="rounded border border-[var(--edge)] bg-black/15 p-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-[0.12em] text-[var(--fg-3)]">
                {artifact.label.replaceAll("_", " ")}
              </span>
              <span className="font-mono text-[10px] text-amber-100">
                {artifact.status.toUpperCase().replaceAll("_", " ")}
              </span>
            </div>
            <div className="mt-1 break-all font-mono text-[10px] text-[var(--fg-3)]">
              {artifact.path ?? "not declared"}
            </div>
            {artifact.manifest_key ? (
              <div className={
                "mt-1 text-[10px] " +
                (artifact.hash_matches === true
                  ? "text-emerald-200"
                  : artifact.hash_matches === false
                    ? "text-rose-200"
                    : "text-amber-200")
              }>
                SHA-256: {artifact.hash_matches === true
                  ? "MATCH"
                  : artifact.hash_matches === false
                    ? "MISMATCH / MISSING"
                    : "NOT VERIFIED"}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      {integrity?.issues?.length ? (
        <div className="mt-3 rounded border border-rose-300/25 bg-rose-300/[0.05] p-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-rose-200">
            Live evidence-integrity issues
          </div>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-[10px] leading-4 text-rose-100">
            {integrity.issues.map((issue) => <li key={issue}>{issue}</li>)}
          </ul>
        </div>
      ) : null}
      <p className="mt-2 text-[11px] leading-4 text-[var(--fg-2)]">
        <strong>{presentation.label}.</strong> {presentation.detail}
      </p>
    </div>
  );
}

function NativeClosureDetails({
  summary,
}: {
  summary: OpenmcSphPhysicsSummary;
}) {
  const eigenvalue = summary.eigenvalue_validation;
  const balance = summary.component_balance;
  const checks = summary.acceptance_checks;
  const correctionEvidence =
    summary.evidence_audit?.evidence_integrity?.forbidden_corrections;
  const physicalBalanceKind =
    eigenvalue?.reference_physical_balance_kind ?? "legacy-rate-balance";
  const physicalBalanceDelta =
    eigenvalue?.reference_physical_balance_delta_pcm ??
    eigenvalue?.reference_rate_balance_delta_pcm;
  const physicalBalanceLabel =
    physicalBalanceKind === "finite-domain-keff"
      ? "Converter finite-balance Δk"
      : physicalBalanceKind === "collision-balance-kinf"
        ? "Converter collision K∞ Δk"
        : "Converter legacy balance Δk";
  const checkRows: [string, "pass" | "fail" | "unknown"][] = checks
    ? [
        ["DONJON normal end", requiredTrueState(checks.donjon_normal_end)],
        ["native SPH converged", requiredTrueState(checks.native_sph_converged)],
        [
          "one-speed inner convergence proved",
          combinedRequiredTrueState(
            checks.one_speed_convergence_provable,
            summary.native_sph?.one_speed_convergence_provable,
          ),
        ],
        ["final transport converged", requiredTrueState(checks.final_flux_solve_converged)],
        ["SPH factors not reset", requiredTrueState(checks.native_sph_factors_unmodified)],
        [
          "SPH iteration not stopped by oscillation",
          requiredTrueState(checks.native_sph_not_stopped_by_oscillation),
        ],
        ["energy coverage", requiredTrueState(checks.energy_coverage_passed)],
        [
          "leakage balance available",
          requiredTrueState(checks.leakage_balance_available_when_required),
        ],
        [
          "reference physical balance",
          requiredTrueState(checks.reference_physical_balance_within_openmc_uncertainty),
        ],
        ["DONJON eigenvalue", requiredTrueState(checks.donjon_keff_within_openmc_uncertainty)],
        [
          "no empirical multiplier",
          verifiedForbiddenCorrectionAbsenceState(
            checks.empirical_eigenvalue_multiplier_used,
            correctionEvidence?.empirical_eigenvalue_multiplier?.evidence_status,
          ),
        ],
        [
          "no ADF",
          verifiedForbiddenCorrectionAbsenceState(
            checks.adf_used,
            correctionEvidence?.adf?.evidence_status,
          ),
        ],
      ]
    : [];
  return (
    <section className="rounded-md border border-cyan-300/20 bg-cyan-300/[0.04] p-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-cyan-200">
        native fine-to-coarse closure
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        <Stat
          label="OpenMC reference k"
          value={formatPhysicsNumber(eigenvalue?.openmc_keff)}
        />
        <Stat
          label={physicalBalanceLabel}
          value={
            physicalBalanceDelta != null
              ? `${physicalBalanceDelta.toFixed(1)} pcm`
              : "n/a"
          }
        />
        <Stat
          label="DONJON native-SPH Δk"
          value={eigenvalue ? `${eigenvalue.donjon_delta_pcm.toFixed(1)} pcm` : "n/a"}
        />
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-4">
        <EvidenceNote
          label="Energy coverage"
          text={`${summary.energy_coverage?.decision ?? "not recorded"}${
            summary.energy_coverage?.energy_mesh_id
              ? ` · ${summary.energy_coverage.energy_mesh_id}`
              : ""
          }`}
        />
        <EvidenceNote
          label="OpenMC leakage"
          text={formatPhysicsNumber(eigenvalue?.reference_leakage)}
        />
        <EvidenceNote
          label="Global net-loss residual"
          text={formatPhysicsNumber(balance?.net_loss_relative_residual)}
        />
        <EvidenceNote
          label="Physical flux residual"
          text={`RMS ${formatPhysicsNumber(
            balance?.flux_rms_relative_residual,
          )} · max ${formatPhysicsNumber(balance?.flux_max_relative_residual)}`}
        />
      </div>
      {checkRows.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {checkRows.map(([label, state]) => (
            <span
              key={label}
              className={
                "rounded border px-2 py-1 text-[10px] " +
                (state === "pass"
                  ? "border-emerald-300/25 text-emerald-200"
                  : state === "fail"
                    ? "border-rose-300/25 text-rose-200"
                    : "border-amber-300/25 text-amber-200")
              }
            >
              {state === "pass" ? "PASS" : state === "fail" ? "FAIL" : "UNKNOWN — BLOCKED"} · {label}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function requiredTrueState(
  value: boolean | null | undefined,
): "pass" | "fail" | "unknown" {
  if (value === true) return "pass";
  if (value === false) return "fail";
  return "unknown";
}

function combinedRequiredTrueState(
  ...values: (boolean | null | undefined)[]
): "pass" | "fail" | "unknown" {
  if (values.some((value) => value === false)) return "fail";
  if (values.every((value) => value === true)) return "pass";
  return "unknown";
}

function EvidenceNote({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded border border-[var(--edge)] bg-white/[0.02] p-2">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">{text}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-1 font-mono text-sm text-[var(--fg-0)]">{value}</div>
    </div>
  );
}

function toErrorState(err: unknown): SummaryState {
  if (err instanceof ApiError) {
    return {
      kind: "error",
      message: err.detail ?? err.message,
      status: err.status,
    };
  }
  if (err instanceof Error) return { kind: "error", message: err.message };
  return { kind: "error", message: "Unknown error" };
}

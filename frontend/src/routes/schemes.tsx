import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useProject } from "@/lib/iris/project-context";
import {
  BackendUnavailableError,
  irisApi,
  type SchemeApplicationStatus,
  type SchemeMatch,
} from "@/lib/iris/api-client";
import { PageHeader, PageShell, SectionHeading, EmptyState } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import type { DecisionTone } from "@/lib/iris/decision-states";
import { formatFactValue } from "@/lib/iris/facts";

export const Route = createFileRoute("/schemes")({
  head: () => ({
    meta: [
      { title: "Schemes — IRIS" },
      { name: "description", content: "Deterministic scheme matching against a verified catalogue." },
    ],
  }),
  component: SchemesPage,
});

const OUTCOME: Record<string, { label: string; tone: DecisionTone }> = {
  POTENTIALLY_ELIGIBLE: { label: "Potentially eligible", tone: "success" },
  NEEDS_INFORMATION: { label: "Needs information", tone: "warning" },
  NOT_ELIGIBLE: { label: "Not eligible", tone: "neutral" },
  CANNOT_EVALUATE: { label: "Cannot evaluate", tone: "danger" },
};

// Application status is a claim about the SCHEME (is it currently accepting
// applications?), entirely independent of eligibility (does this project's
// facts satisfy it?). Labels deliberately avoid implying availability the
// data doesn't assert — no "Available"/"Eligible now"/"Guaranteed"/"Approved".
const APPLICATION_STATUS_META: Record<SchemeApplicationStatus, { label: string; tone: DecisionTone }> = {
  VERIFIED_OPEN: { label: "Applications open", tone: "success" },
  VERIFIED_CLOSED: { label: "Applications closed", tone: "neutral" },
  VERIFIED_CONTINUING_BUT_NOT_OPEN_FOR_NEW_APPLICATIONS: {
    label: "Continuing scheme — not open for new applications",
    tone: "neutral",
  },
  VERIFIED_PERIODIC_CALL_FOR_PROPOSALS: { label: "Periodic call for proposals", tone: "info" },
  SELECTION_COMPLETED: { label: "Selection completed", tone: "neutral" },
  NO_CURRENT_WINDOW: { label: "No current application window", tone: "warning" },
  UNRESOLVED_CURRENT_STATUS: { label: "Current application status unresolved", tone: "warning" },
  DISCONTINUED: { label: "Scheme discontinued", tone: "neutral" },
  SUPERSEDED: { label: "Superseded by a newer scheme record", tone: "neutral" },
};

/** The only application_status the catalogue can assert that unambiguously
 * means "you can apply right now" — every other value keeps the
 * eligibility-vs-availability distinction visually prominent (§10). */
const CURRENTLY_OPEN: SchemeApplicationStatus = "VERIFIED_OPEN";

function ApplicationWindowDetail({ r }: { r: SchemeMatch }) {
  const w = r.application_window;
  if (!w) return null;
  const parts: string[] = [];
  if (w.closes) parts.push(`Closes ${w.closes}`);
  else if (w.opens) parts.push(`Opens ${w.opens}`);
  if (w.as_of_date) parts.push(`as verified on ${w.as_of_date}`);
  if (parts.length === 0) return null;
  return <p className="mt-0.5 text-[11.5px] text-muted-foreground">{parts.join(" · ")}</p>;
}

function SchemeRow({ r }: { r: SchemeMatch }) {
  const [open, setOpen] = useState(false);
  const meta = OUTCOME[r.outcome] ?? { label: r.outcome, tone: "neutral" as DecisionTone };
  const appMeta = r.application_status ? APPLICATION_STATUS_META[r.application_status] : null;
  // Prominent only when eligibility looks positive but the verified
  // application status says otherwise — generic and data-driven, never
  // naming a specific scheme. No claim is made when application_status is
  // unset (nothing verified either way).
  const showActionabilityWarning =
    r.outcome === "POTENTIALLY_ELIGIBLE" &&
    r.application_status !== null &&
    r.application_status !== CURRENTLY_OPEN;

  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[13px] font-medium">{r.name}</p>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            {r.administering_authority_name} · <span className="font-mono">{r.scheme_id}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!r.is_authoritative_catalogue_entry && <Tag tone="warning">Diagnostic — unverified catalogue record</Tag>}
          <button type="button" onClick={() => setOpen((v) => !v)} className="text-[12px] font-medium text-info hover:opacity-80">
            {open ? "Hide" : "Why?"}
          </button>
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap items-start gap-x-8 gap-y-2">
        <div>
          <p className="label-meta">Eligibility</p>
          <Tag tone={meta.tone}>{meta.label}</Tag>
        </div>
        <div>
          <p className="label-meta">Application status</p>
          {appMeta ? (
            <>
              <Tag tone={appMeta.tone}>{appMeta.label}</Tag>
              <ApplicationWindowDetail r={r} />
            </>
          ) : (
            <p className="text-[11.5px] text-muted-foreground">Not yet verified</p>
          )}
        </div>
      </div>

      {showActionabilityWarning && (
        <p className="mt-2 border-l-2 border-warning pl-3 text-[12px] leading-relaxed text-foreground/80">
          The project may fit the verified eligibility criteria, but new
          applications are not currently accepted under the verified window.
        </p>
      )}

      {open && (
        <div className="mt-2 space-y-2 border-l-2 border-border pl-3 text-[12px]">
          {r.not_in_force_reason && <p className="text-warning">{r.not_in_force_reason}</p>}
          {r.supersedes && (
            <p className="text-muted-foreground">
              Supersedes catalogue record <span className="font-mono">{r.supersedes}</span>
            </p>
          )}
          {r.superseded_by && (
            <p className="text-muted-foreground">
              Superseded by catalogue record <span className="font-mono">{r.superseded_by}</span>
            </p>
          )}
          {r.missing_facts.length > 0 && (
            <p className="text-warning">Missing: <span className="font-mono">{r.missing_facts.join(", ")}</span></p>
          )}
          <ul className="space-y-1">
            {r.why.map((w) => (
              <li key={w.scheme_condition_id}>
                <span className="font-mono">{w.fact_key} {w.operator} {formatFactValue(w.expected_value)}{w.unit ? ` ${w.unit}` : ""}</span>
                {" — project value "}
                <span className="tabular">{formatFactValue(w.project_value)}</span> → {w.result}
                {w.source_reference?.clause ? ` (cl. ${w.source_reference.clause})` : ""}
                {w.description && <span className="block text-[11.5px] text-muted-foreground">{w.description}</span>}
              </li>
            ))}
          </ul>
          {(r.composite_notes ?? []).some((c) => c.description) && (
            <div className="border-l-2 border-warning pl-3">
              <p className="label-meta">Stated limitations of this record</p>
              {(r.composite_notes ?? []).filter((c) => c.description).map((c) => (
                <p key={c.scheme_condition_id} className="mt-0.5 text-[11.5px] text-muted-foreground">{c.description}</p>
              ))}
            </div>
          )}
          {r.benefits_summary && (
            <p className="text-[11.5px] text-muted-foreground">
              <span className="label-meta">Benefit as published (no amount is computed)</span>
              <span className="block">{r.benefits_summary}</span>
            </p>
          )}
          {!r.is_authoritative_catalogue_entry && r.notes && (
            <p className="text-[11.5px] text-muted-foreground">
              <span className="label-meta">Record notes (draft)</span>
              <span className="block">{r.notes}</span>
            </p>
          )}
          {r.official_source?.url && (
            <p>
              Source:{" "}
              <a href={r.official_source.url} target="_blank" rel="noreferrer" className="text-info hover:underline">
                {r.official_source.document_title ?? r.official_source.url}
              </a>
              {r.last_verified?.date ? ` · last verified ${r.last_verified.date}` : ""}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function SchemesPage() {
  const { activeProject } = useProject();
  const [diagnostic, setDiagnostic] = useState(false);
  const q = useQuery({
    queryKey: ["schemes", activeProject.id, diagnostic],
    queryFn: () => irisApi.getProjectSchemes(activeProject.id, diagnostic ? "NON_PRODUCTION" : "PRODUCTION"),
  });
  const data = q.data;

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Oversight" }, { label: "Schemes" }]}
        title="Scheme Matching"
        description={`${activeProject.name} · deterministic matching against ${diagnostic ? "the diagnostic catalogue (includes unverified records)" : "the verified catalogue"}`}
      />

      <div role="group" aria-label="Catalogue mode" className="mt-4 inline-flex overflow-hidden rounded-sm border border-border text-[12px] font-medium">
        {([
          [false, "Verified catalogue"],
          [true, "Diagnostic catalogue"],
        ] as const).map(([isDiag, label]) => (
          <button
            key={label}
            type="button"
            aria-pressed={diagnostic === isDiag}
            onClick={() => setDiagnostic(isDiag)}
            className={`focus-ring px-3 py-[7px] transition-colors ${diagnostic === isDiag ? "bg-primary text-primary-foreground" : "bg-surface text-muted-foreground hover:bg-secondary"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {diagnostic && (
        <p className="mt-3 border border-warning/40 bg-warning-surface px-4 py-2.5 text-[12.5px] leading-relaxed">
          <span className="font-semibold uppercase tracking-[0.05em] text-warning">Diagnostic — non-authoritative.</span>{" "}
          This view also evaluates DRAFT / unverified catalogue records with the same deterministic matcher. They are not
          verified against archived official sources; eligibility and application status are separate claims.
        </p>
      )}

      {q.isLoading ? (
        <p className="mt-6 text-[12.5px] text-muted-foreground">Loading…</p>
      ) : q.isError || !data ? (
        <p className="mt-6 text-[12.5px] text-muted-foreground">
          {q.error instanceof BackendUnavailableError ? "The IRIS backend isn't reachable." : "Schemes could not be loaded."}
        </p>
      ) : data.catalogue_state === "INVALID" ? (
        <div className="mt-6">
          <EmptyState
            title="Scheme catalogue failed validation"
            description="No eligibility results are produced from an invalid catalogue. The catalogue maintainer needs to fix the reported errors."
          />
        </div>
      ) : data.catalogue_state === "AWAITING_VERIFIED_DATA" && !diagnostic ? (
        <div className="mt-6">
          <EmptyState
            title="Scheme catalogue awaiting verified data"
            description="IRIS matches schemes only against official, verified scheme records, and none are loaded yet. No eligibility is shown rather than an unverified guess. The matching framework is in place and will use the catalogue as soon as verified records are added."
          />
          {data.counts && data.counts.total > 0 && (
            <p className="mt-3 text-[12px] text-muted-foreground">
              {data.counts.total} draft record{data.counts.total === 1 ? "" : "s"} available in the Diagnostic catalogue.
            </p>
          )}
        </div>
      ) : (
        <section className="mt-6">
          <SectionHeading
            title={diagnostic ? "Diagnostic results (includes draft records)" : "Scheme results"}
            hint="Potentially eligible is never a final decision — the administering authority decides."
          />
          {data.results.length === 0 ? (
            <p className="mt-3 text-[12.5px] text-muted-foreground">No schemes to show.</p>
          ) : (
            <ul className="mt-3 divide-y divide-border border border-border bg-surface">
              {data.results.map((r) => <SchemeRow key={r.scheme_id} r={r} />)}
            </ul>
          )}
          {!diagnostic && data.counts && data.counts.total > data.counts.active_verified && (
            <p className="mt-3 text-[12px] text-muted-foreground">
              {data.counts.total - data.counts.active_verified} further record{data.counts.total - data.counts.active_verified === 1 ? " is" : "s are"} DRAFT / unverified and only shown in the Diagnostic catalogue.
            </p>
          )}
        </section>
      )}

      {data && (
        <ul className="mt-6 space-y-0.5 border-t border-border pt-4 text-[11px] text-muted-foreground">
          {data.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </PageShell>
  );
}

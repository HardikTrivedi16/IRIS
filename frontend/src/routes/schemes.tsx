import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useProject } from "@/lib/iris/project-context";
import { BackendUnavailableError, irisApi, type SchemeMatch } from "@/lib/iris/api-client";
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

function SchemeRow({ r }: { r: SchemeMatch }) {
  const [open, setOpen] = useState(false);
  const meta = OUTCOME[r.outcome] ?? { label: r.outcome, tone: "neutral" as DecisionTone };
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
          {!r.is_authoritative_catalogue_entry && <Tag tone="warning">Draft / unverified record</Tag>}
          <Tag tone={meta.tone}>{meta.label}</Tag>
          <button type="button" onClick={() => setOpen((v) => !v)} className="text-[12px] font-medium text-info hover:opacity-80">
            {open ? "Hide" : "Why?"}
          </button>
        </div>
      </div>
      {open && (
        <div className="mt-2 space-y-2 border-l-2 border-border pl-3 text-[12px]">
          {r.not_in_force_reason && <p className="text-warning">{r.not_in_force_reason}</p>}
          {r.missing_facts.length > 0 && (
            <p className="text-warning">Missing: <span className="font-mono">{r.missing_facts.join(", ")}</span></p>
          )}
          <ul className="space-y-0.5">
            {r.why.map((w) => (
              <li key={w.scheme_condition_id}>
                <span className="font-mono">{w.fact_key} {w.operator} {formatFactValue(w.expected_value)}{w.unit ? ` ${w.unit}` : ""}</span>
                {" — project value "}
                <span className="tabular">{formatFactValue(w.project_value)}</span> → {w.result}
                {w.source_reference?.clause ? ` (cl. ${w.source_reference.clause})` : ""}
              </li>
            ))}
          </ul>
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
        description={`${activeProject.name} · deterministic matching against a verified catalogue`}
      />

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
            <button type="button" onClick={() => setDiagnostic(true)} className="mt-3 text-[12px] font-medium text-info hover:opacity-80">
              View {data.counts.total} draft record{data.counts.total === 1 ? "" : "s"} in diagnostic mode →
            </button>
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
          {diagnostic && (
            <button type="button" onClick={() => setDiagnostic(false)} className="mt-3 text-[12px] text-muted-foreground hover:text-foreground">
              ← Back to verified results
            </button>
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

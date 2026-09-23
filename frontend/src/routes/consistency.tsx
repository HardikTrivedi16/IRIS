import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileSearch } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type ConsistencyResult,
  type ConsistencyStatus,
} from "@/lib/iris/api-client";
import { PageHeader, PageShell, DataField, EmptyState } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import {
  IssueCard,
  ManualEntry,
  ConsistencySafetyNote,
} from "@/components/iris/consistency-shared";
import { STATUS_META, STATUS_ORDER, type CheckSource } from "@/lib/iris/consistency";

export const Route = createFileRoute("/consistency")({
  head: () => ({
    meta: [
      { title: "Evidence Consistency — IRIS" },
      {
        name: "description",
        content:
          "Detect conflicting, missing, expired, or uncertain evidence before it affects regulatory decisions.",
      },
      { property: "og:title", content: "Evidence Consistency — IRIS" },
      {
        property: "og:description",
        content:
          "Objective, deterministic cross-document evidence comparison — not a compliance determination.",
      },
    ],
  }),
  component: EvidenceConsistency,
});

/** Prominent counts for the statuses that actually occurred, ordered by
 * urgency, CONSISTENT excluded (shown separately, de-emphasised). No score,
 * percentage or severity rating is computed — every number here is a plain
 * count straight from `result.summary`. */
function SummaryStrip({ summary }: { summary: Record<ConsistencyStatus, number> }) {
  const attention = STATUS_ORDER.filter((s) => s !== "CONSISTENT" && summary[s] > 0);
  const consistentCount = summary.CONSISTENT ?? 0;

  if (attention.length === 0) {
    return (
      <div className="flex items-center gap-2 border border-success/25 bg-success-surface px-4 py-3">
        <Tag tone="success">No findings</Tag>
        <p className="text-[12.5px] text-foreground">
          Every value compared agrees across its sources.
          {consistentCount > 0 &&
            ` (${consistentCount} consistent check${consistentCount === 1 ? "" : "s"}.)`}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border border-border bg-surface px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {attention.map((status) => {
          const meta = STATUS_META[status];
          return (
            <div key={status} className="flex items-baseline gap-1.5">
              <span className="tabular text-[20px] font-semibold leading-none">
                {summary[status]}
              </span>
              <span className="text-[11.5px] font-medium uppercase tracking-[0.04em] text-muted-foreground">
                {meta.label}
              </span>
            </div>
          );
        })}
      </div>
      {consistentCount > 0 && (
        <span className="ml-auto text-[11.5px] text-muted-foreground">
          {consistentCount} consistent check{consistentCount === 1 ? "" : "s"} not shown here
        </span>
      )}
    </div>
  );
}

function SourcesPanel({
  sources,
  onRemove,
  onAdd,
}: {
  sources: CheckSource[];
  onRemove: (id: string) => void;
  onAdd: (source: CheckSource) => void;
}) {
  return (
    <div className="border border-border bg-surface">
      <div className="border-b border-border px-5 py-3">
        <p className="label-meta">Evidence sources in this check ({sources.length})</p>
        <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          Your confirmed project record is always included automatically. Add
          another document's value here to compare it — the same values you
          extract and add to the pre-submission check on the Documents page
          also work here; nothing added on this page is saved.
        </p>
      </div>
      {sources.length > 0 && (
        <ul className="divide-y divide-border">
          {sources.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 px-5 py-2 text-[12.5px]">
              <span>
                {s.name}{" "}
                <span className="text-[11px] text-muted-foreground">
                  ·{" "}
                  {s.origin === "LEGACY_FIXTURE"
                    ? "legacy synthetic evidence observation"
                    : s.kind === "MANUAL"
                      ? "manual entry"
                      : "extracted"}{" "}
                  ·{" "}
                  {s.observations.map((o) => o.field.replace(/_/g, " ")).join(", ") || "no comparable fields"}
                </span>
              </span>
              <button
                type="button"
                onClick={() => onRemove(s.id)}
                className="text-[11.5px] text-muted-foreground hover:text-foreground"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <ManualEntry onAdd={onAdd} />
    </div>
  );
}

function EvidenceConsistency() {
  const { activeProject } = useProject();
  const [sources, setSources] = useState<CheckSource[]>([]);
  const [showConsistent, setShowConsistent] = useState(false);

  const run = useMutation({
    mutationFn: (currentSources: CheckSource[]) =>
      irisApi.runConsistencyCheck(activeProject.id, {
        observations: currentSources.flatMap((s) => s.observations),
      }),
  });

  // Demo-only: committed synthetic OBSERVATIONS for legacy evidence. The
  // engine — not this page — computes every status from them.
  const legacyQuery = useQuery({
    queryKey: ["consistency-legacy-observations", activeProject.id],
    queryFn: () => irisApi.getLegacyConsistencyObservations(activeProject.id),
    staleTime: 5 * 60_000,
  });
  const legacy = legacyQuery.data && legacyQuery.data.available ? legacyQuery.data : null;
  const legacyLoaded = sources.some((s) => s.origin === "LEGACY_FIXTURE");

  function compareLegacyEvidence() {
    if (!legacy || legacyLoaded) return;
    // One check source per document the observations name (honest provenance).
    const byDoc = new Map<string, CheckSource>();
    for (const o of legacy.observations) {
      const key = o.source.document_id ?? o.source.document_name ?? "legacy";
      const existing = byDoc.get(key) ?? {
        id: `legacy-${key}`,
        name: o.source.document_name ?? key,
        kind: "DOCUMENT" as const,
        origin: "LEGACY_FIXTURE" as const,
        observations: [],
      };
      existing.observations.push(o);
      byDoc.set(key, existing);
    }
    const next = [...sources, ...byDoc.values()];
    setSources(next);
    run.mutate(next);
  }

  // Runs once on load (project's confirmed record alone — include_project_record
  // defaults true server-side) and again whenever a source is added/removed.
  // Always deterministic and read-only: nothing is saved by running it.
  useEffect(() => {
    run.mutate([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject.id]);

  function addSource(source: CheckSource) {
    const next = [...sources, source];
    setSources(next);
    run.mutate(next);
  }

  function removeSource(id: string) {
    const next = sources.filter((s) => s.id !== id);
    setSources(next);
    run.mutate(next);
  }

  const result: ConsistencyResult | undefined = run.data;
  const hasRun = run.isSuccess && !!result;
  const isEmpty =
    hasRun &&
    sources.length === 0 &&
    result!.checks_performed === 0 &&
    result!.uncompared_fields.length === 0;

    const legacyPanel = legacy ? (
    <section className="mt-4 border border-border bg-surface px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div>
          <p className="text-[13px] font-medium">Legacy evidence — prior facility</p>
          <p className="mt-1 max-w-[80ch] text-[12px] leading-relaxed text-muted-foreground">
            Compare the committed synthetic legacy-evidence observations for this project's prior
            facility against its current project record. They are transcribed synthetic values, not
            live AI extractions, and carry no confidence score. Statuses are computed by the same
            deterministic engine. Nothing is saved.
          </p>
        </div>
        <button
          type="button"
          onClick={compareLegacyEvidence}
          disabled={legacyLoaded || run.isPending}
          className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {legacyLoaded ? "Legacy evidence loaded" : "Compare legacy evidence"}
        </button>
      </div>
    </section>
  ) : null;

  const issues = result?.checks.filter((c) => c.status !== "CONSISTENT") ?? [];
  const consistent = result?.checks.filter((c) => c.status === "CONSISTENT") ?? [];

  return (
    <PageShell wide>
      <PageHeader
        trail={[
          { label: "Regulatory intelligence" },
          { label: "Evidence Consistency" },
        ]}
        title="Evidence Consistency"
        description="Detect conflicting, missing, expired, or uncertain evidence before it affects regulatory decisions."
      />

      <section className="mt-6">
        <ConsistencySafetyNote />
      </section>

      <section className="mt-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border border-border bg-surface px-5 py-3.5">
        <DataField label="Current project" value={activeProject.name} />
        {hasRun && (
          <span className="text-[11.5px] text-muted-foreground">
            As of {result!.as_of_date} · {result!.checks_performed} check
            {result!.checks_performed === 1 ? "" : "s"} performed
          </span>
        )}
      </section>

      {legacyPanel}

      {run.isPending && !hasRun && (
        <p className="mt-4 px-1 text-[12.5px] text-muted-foreground">
          Comparing confirmed project evidence…
        </p>
      )}

      {run.isError && (
        <p className="mt-4 border border-destructive/30 bg-danger-surface px-5 py-3 text-[12.5px]">
          {run.error instanceof BackendUnavailableError
            ? "The IRIS backend isn't reachable right now."
            : run.error instanceof ApiError && run.error.status === 422
              ? "Some values were rejected — check the fields and units added below."
              : "The consistency check could not be run."}
        </p>
      )}

      {isEmpty && (
        <div className="mt-6">
          <EmptyState
            title="No evidence comparisons available yet"
            description="Extract and confirm document information on the Documents page to build an evidence set for cross-document checking — or add a value manually below to try it now."
            action={
              <Link
                to="/documents"
                className="focus-ring inline-flex items-center gap-1.5 rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                <FileSearch className="h-3.5 w-3.5" />
                Go to Documents
              </Link>
            }
          />
          <div className="mt-4">
            <SourcesPanel sources={sources} onRemove={removeSource} onAdd={addSource} />
          </div>
        </div>
      )}

      {hasRun && !isEmpty && (
        <>
          <section className="mt-6">
            <SummaryStrip summary={result!.summary} />
          </section>

          <section className="mt-4">
            <SourcesPanel sources={sources} onRemove={removeSource} onAdd={addSource} />
          </section>

          <section className="mt-6 border border-border bg-surface">
            {issues.length > 0 ? (
              <ul className="divide-y divide-border">
                {issues.map((c) => (
                  <IssueCard key={c.check_id} check={c} />
                ))}
              </ul>
            ) : (
              <p className="px-5 py-6 text-center text-[12.5px] text-muted-foreground">
                No issues among the values compared.
              </p>
            )}

            {consistent.length > 0 && (
              <div className="border-t border-border px-5 py-2.5">
                <button
                  type="button"
                  onClick={() => setShowConsistent((v) => !v)}
                  className="text-[12px] font-medium text-info hover:opacity-80"
                >
                  {showConsistent ? "Hide" : "Show"} {consistent.length} consistent check
                  {consistent.length === 1 ? "" : "s"}
                </button>
                {showConsistent && (
                  <ul className="mt-2 divide-y divide-border">
                    {consistent.map((c) => (
                      <IssueCard key={c.check_id} check={c} />
                    ))}
                  </ul>
                )}
              </div>
            )}

            {result!.uncompared_fields.length > 0 && (
              <div className="border-t border-border px-5 py-2.5 text-[11.5px] text-muted-foreground">
                Not compared:{" "}
                {result!.uncompared_fields.map((u) => u.field_label).join(", ")} — only one
                source states each.
              </div>
            )}
          </section>

          <p className="mt-4 text-[11px] leading-relaxed text-muted-foreground">
            {result!.policy.note} Legal significance not yet established from
            verified regulatory evidence.
          </p>
        </>
      )}
    </PageShell>
  );
}

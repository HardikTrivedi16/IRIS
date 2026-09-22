import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type ConsistencyResult,
} from "@/lib/iris/api-client";
import { IssueCard, ManualEntry } from "@/components/iris/consistency-shared";
import type { CheckSource } from "@/lib/iris/consistency";

// CheckSource / observationsFromExtraction moved to lib/iris/consistency.ts
// (shared with the standalone Evidence Consistency page); re-exported here
// so existing imports (routes/documents.tsx) keep working unchanged.
export type { CheckSource } from "@/lib/iris/consistency";
export { observationsFromExtraction } from "@/lib/iris/consistency";

/**
 * PRE-SUBMISSION CHECK — "What does not match before I file?"
 *
 * Compares values from the project's confirmed record and the documents
 * added in this session. The comparison is deterministic and server-side;
 * nothing is saved and no Project Fact is changed.
 *
 * This is the Documents-page embedded workflow tool. The standalone,
 * jury-facing view of the same engine is the Evidence Consistency page
 * (routes/consistency.tsx) — both call the same
 * POST /projects/{id}/consistency-check and share their presentation pieces
 * (components/iris/consistency-shared.tsx, lib/iris/consistency.ts).
 */
export function PreSubmissionCheck({
  projectId,
  sources,
  onRemoveSource,
  onAddSource,
}: {
  projectId: string;
  sources: CheckSource[];
  onRemoveSource: (id: string) => void;
  onAddSource: (source: CheckSource) => void;
}) {
  const [result, setResult] = useState<ConsistencyResult | null>(null);
  const [showConsistent, setShowConsistent] = useState(false);

  const run = useMutation({
    mutationFn: () =>
      irisApi.runConsistencyCheck(projectId, {
        observations: sources.flatMap((s) => s.observations),
      }),
    onSuccess: setResult,
  });

  const issues = result?.checks.filter((c) => c.status !== "CONSISTENT") ?? [];
  const consistent = result?.checks.filter((c) => c.status === "CONSISTENT") ?? [];

  return (
    <div className="border border-border bg-surface">
      <div className="border-b border-border px-5 py-3">
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          Compares the same fact across your confirmed project record and the
          documents you add here — names, addresses, identifiers, batches,
          quantities and validity dates. This is an objective data check, not
          a compliance decision. Sources added here are kept for this session
          only; nothing is saved and no Project Fact is changed.
        </p>
      </div>

      <div className="px-5 py-3">
        <p className="label-meta">Sources in this check ({sources.length})</p>
        {sources.length === 0 ? (
          <p className="mt-1 text-[12px] text-muted-foreground">
            Extract a document below and choose “Add to pre-submission check”,
            or add a value manually. The project's confirmed record is always included.
          </p>
        ) : (
          <ul className="mt-1.5 divide-y divide-border">
            {sources.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 py-1.5 text-[12.5px]">
                <span>
                  {s.name}{" "}
                  <span className="text-[11px] text-muted-foreground">
                    · {s.kind === "MANUAL" ? "manual entry" : "extracted"} ·{" "}
                    {s.observations.map((o) => o.field.replace(/_/g, " ")).join(", ") || "no comparable fields"}
                  </span>
                </span>
                <button type="button" onClick={() => onRemoveSource(s.id)}
                  className="text-[11.5px] text-muted-foreground hover:text-foreground">
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ManualEntry onAdd={onAddSource} />

      <div className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-3">
        <button type="button" onClick={() => run.mutate()} disabled={run.isPending}
          className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40">
          {run.isPending ? "Checking…" : "Run pre-submission check"}
        </button>
        {run.isError && (
          <span className="text-[11.5px] text-destructive">
            {run.error instanceof BackendUnavailableError
              ? "Backend unreachable."
              : run.error instanceof ApiError && run.error.status === 422
                ? "Some values were rejected — check fields and units."
                : "The check could not be run."}
          </span>
        )}
      </div>

      {result && (
        <div className="border-t border-border">
          <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2 px-5 py-3">
            <div>
              <span className="tabular text-[20px] font-semibold">{result.checks_performed}</span>{" "}
              <span className="text-[12px] text-muted-foreground">checks performed</span>
            </div>
            <div>
              <span className="tabular text-[20px] font-semibold">{result.issues_found}</span>{" "}
              <span className="text-[12px] text-muted-foreground">issues found</span>
            </div>
            <span className="text-[11px] text-muted-foreground">As of {result.as_of_date}</span>
          </div>

          {issues.length > 0 ? (
            <ul className="divide-y divide-border border-t border-border">
              {issues.map((c) => (
                <IssueCard key={c.check_id} check={c} />
              ))}
            </ul>
          ) : (
            <p className="border-t border-border px-5 py-3 text-[12.5px] text-muted-foreground">
              No issues among the values compared.
            </p>
          )}

          {consistent.length > 0 && (
            <div className="border-t border-border px-5 py-2.5">
              <button type="button" onClick={() => setShowConsistent((v) => !v)}
                className="text-[12px] font-medium text-info hover:opacity-80">
                {showConsistent ? "Hide" : "Show"} {consistent.length} consistent check{consistent.length === 1 ? "" : "s"}
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

          {result.uncompared_fields.length > 0 && (
            <div className="border-t border-border px-5 py-2.5 text-[11.5px] text-muted-foreground">
              Not compared:{" "}
              {result.uncompared_fields.map((u) => u.field_label).join(", ")} — only one source states each.
            </div>
          )}
          <p className="border-t border-border px-5 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
            {result.policy.note}
          </p>
        </div>
      )}
    </div>
  );
}

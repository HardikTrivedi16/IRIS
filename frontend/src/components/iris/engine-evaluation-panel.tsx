import { useMemo, useState } from "react";
import type { EvaluationMode } from "@/lib/iris/api-client";
import { Tag } from "@/components/iris/status";
import { RegulatoryItemList, type Lens } from "@/components/iris/regulatory-item-list";
import { useRegulatoryItems } from "@/lib/iris/use-regulatory-items";

export { useEngineEvaluation } from "@/lib/iris/use-engine-evaluation";

/**
 * Every dataset requirement evaluated by the deterministic Rule Engine from
 * this project's STORED Project Facts (no ad-hoc overrides, nothing
 * persisted). PRODUCTION (authoritative) is the default view: applicable and
 * needs-information results are shown first, not-applicable and the DRAFT-rule
 * diagnostic-only requirements collapse behind a one-line count so the first
 * viewport reads as counts, not paragraphs. The full non-authoritative
 * analysis of every requirement remains one click away.
 */
export function EngineEvaluationPanel({
  projectId,
  onOpenProof,
  authorityFilter,
  stageFilter,
}: {
  projectId: string;
  onOpenProof?: (requirementId: string, mode: EvaluationMode) => void;
  authorityFilter?: string;
  stageFilter?: string;
}) {
  const [lens, setLens] = useState<Lens>("PRODUCTION");
  const { items: all, isLoading, isError } = useRegulatoryItems(projectId);
  const items = all.filter(
    (i) =>
      (!authorityFilter || authorityFilter === "all" || i.authorityName === authorityFilter) &&
      (!stageFilter || stageFilter === "all" || i.lifecycleStageIds.includes(stageFilter)),
  );

  const counts = useMemo(() => {
    const authoritative = items.filter((i) => i.production.authoritative);
    return {
      applicable: authoritative.filter((i) => i.production.finalState === "APPLICABLE").length,
      notApplicable: authoritative.filter((i) => i.production.finalState === "NOT_APPLICABLE").length,
      needsInfo: authoritative.filter(
        (i) => i.production.finalState !== "APPLICABLE" && i.production.finalState !== "NOT_APPLICABLE",
      ).length,
      diagnosticOnly: items.length - authoritative.length,
    };
  }, [items]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border px-5 py-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="label-meta mr-1">Verified production</span>
          <Tag tone="success">{counts.applicable} Applicable</Tag>
          <Tag tone="neutral">{counts.notApplicable} Not applicable</Tag>
          <Tag tone="warning">{counts.needsInfo} Needs information</Tag>
        </div>
        {counts.diagnosticOnly > 0 && (
          <button
            type="button"
            onClick={() => setLens("DIAGNOSTIC")}
            className="text-[12px] font-medium text-info hover:opacity-80"
          >
            + {counts.diagnosticOnly} additional diagnostic {counts.diagnosticOnly === 1 ? "question" : "questions"}
          </button>
        )}
      </div>

      <div className="flex items-center justify-between border-b border-border px-5 py-2">
        <div className="flex overflow-hidden rounded-sm border border-border text-[11.5px]">
          {(["PRODUCTION", "DIAGNOSTIC"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setLens(m)}
              className={
                lens === m
                  ? "bg-primary px-2.5 py-[4px] font-medium text-primary-foreground"
                  : "px-2.5 py-[4px] text-muted-foreground hover:bg-secondary"
              }
            >
              {m === "DIAGNOSTIC" ? "Full diagnostic analysis" : "What applies now"}
            </button>
          ))}
        </div>
        {all.length > 0 && (
          <span className="text-[11px] text-muted-foreground">
            {items.length} of {all.length} requirements
          </span>
        )}
      </div>

      {lens === "DIAGNOSTIC" && (
        <p className="border-b border-border bg-info-surface px-5 py-2 text-[11.5px] leading-relaxed text-foreground/80">
          Diagnostic analysis uses additional regulatory knowledge not yet part of a verified Production
          determination — non-authoritative.
        </p>
      )}

      {isLoading ? (
        <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
          Evaluating against the regulatory engine…
        </p>
      ) : isError ? (
        <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
          The regulatory engine could not evaluate this project (or is not reachable right now).
        </p>
      ) : (
        <RegulatoryItemList items={items} lens={lens} onOpenProof={onOpenProof} />
      )}
      <p className="border-t border-border px-5 py-2 text-[10.5px] text-muted-foreground">
        Evaluated from this project's stored Project Facts. Viewing this does not store a decision.
      </p>
    </div>
  );
}

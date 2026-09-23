import { useState } from "react";
import type { EvaluationMode } from "@/lib/iris/api-client";
import { Tag } from "@/components/iris/status";
import { RegulatoryItemList, type Lens } from "@/components/iris/regulatory-item-list";
import { useRegulatoryItems } from "@/lib/iris/use-regulatory-items";
import { summarizeItems } from "@/lib/iris/regulatory-items";

export { useEngineEvaluation } from "@/lib/iris/use-engine-evaluation";

/**
 * Every dataset requirement evaluated by the deterministic Rule Engine from
 * this project's STORED Project Facts (no ad-hoc overrides, nothing
 * persisted). PRODUCTION (authoritative) is the default view; the adjacent
 * "View diagnostic analysis" lens shows how the deterministic logic evaluates
 * the project's facts over DRAFT rules, grouped by a presentation-only
 * relevance signal and clearly labelled non-authoritative.
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
  const summary = summarizeItems(all);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="label-meta">View</span>
          <div className="flex overflow-hidden rounded-sm border border-border text-[12px]">
            {(["PRODUCTION", "DIAGNOSTIC"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setLens(m)}
                className={
                  lens === m
                    ? "bg-primary px-2.5 py-[5px] font-medium text-primary-foreground"
                    : "px-2.5 py-[5px] text-muted-foreground hover:bg-secondary"
                }
              >
                {m === "DIAGNOSTIC" ? "View diagnostic analysis" : "Production (authoritative)"}
              </button>
            ))}
          </div>
        </div>
        {all.length > 0 && (
          <span className="text-[11.5px] text-muted-foreground">
            {items.length} of {all.length} requirements shown
          </span>
        )}
      </div>

      {all.length > 0 && (
        <div className="border-b border-border bg-warning-surface px-5 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Tag tone="warning">Production: {summary.authoritative} authoritative</Tag>
            <Tag tone="warning">{summary.awaitingVerifiedKnowledge} awaiting verified knowledge</Tag>
          </div>
          <p className="mt-1.5 max-w-[80ch] text-[11.5px] leading-relaxed text-foreground/80">
            Current regulatory knowledge is DRAFT, so IRIS is withholding authoritative determinations — it
            refuses to issue a production result from unverified rules.
            {lens === "PRODUCTION"
              ? " Use “View diagnostic analysis” to see how the deterministic logic evaluates this project's facts over those DRAFT rules (non-authoritative)."
              : " The analysis below is the deterministic evaluation of those DRAFT rules against this project's facts. It is diagnostic and non-authoritative."}
          </p>
        </div>
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
      <p className="border-t border-border px-5 py-2.5 text-[11px] text-muted-foreground">
        Evaluated from this project's stored Project Facts. Viewing this does not store a decision.
      </p>
    </div>
  );
}

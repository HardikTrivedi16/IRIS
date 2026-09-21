import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BackendUnavailableError,
  irisApi,
  type EngineDecision,
  type EvaluationMode,
} from "@/lib/iris/api-client";
import { Tag } from "@/components/iris/status";
import { finalStateMeta, isBlockedState } from "@/lib/iris/decision-states";
import { useDatasetRequirementTitles } from "@/lib/iris/facts";

export function useEngineEvaluation(projectId: string, mode: EvaluationMode) {
  return useQuery({
    queryKey: ["engine-evaluation", projectId, mode],
    queryFn: async () =>
      (await irisApi.evaluateAll({ projectId, evaluationMode: mode })).decisions,
    retry: (n, e) => !(e instanceof BackendUnavailableError) && n < 1,
    staleTime: 10_000,
  });
}

function DecisionRow({
  decision,
  title,
  onOpenProof,
}: {
  decision: EngineDecision;
  title: string;
  onOpenProof: ((requirementId: string) => void) | undefined;
}) {
  const meta = finalStateMeta(decision.final_state);
  const missing = decision.missing_project_fact_keys ?? [];
  return (
    <li className="px-5 py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <p className="text-[13px] font-medium leading-snug">{title}</p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            {decision.requirement_id} · {decision.rule_version_id ?? "no rule version"}
            {decision.rule_version_status ? ` (${decision.rule_version_status})` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {decision.is_non_production_result && <Tag tone="info">Diagnostic</Tag>}
          <Tag tone={meta.tone}>{meta.label}</Tag>
        </div>
      </div>

      {missing.length > 0 && (
        <div className="mt-2 border-l-2 border-warning pl-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-warning">
            Additional information required
          </p>
          <ul className="mt-0.5">
            {missing.map((k) => (
              <li key={k} className="font-mono text-[11px] text-muted-foreground">
                {k}
              </li>
            ))}
          </ul>
        </div>
      )}

      {onOpenProof && (
        <button
          type="button"
          onClick={() => onOpenProof(decision.requirement_id)}
          className="mt-2 text-[12px] font-medium text-info hover:opacity-80"
        >
          View decision proof →
        </button>
      )}
    </li>
  );
}

/**
 * Every dataset requirement evaluated by the deterministic Rule Engine from
 * this project's STORED Project Facts (no ad-hoc overrides, nothing
 * persisted). PRODUCTION is the default and, with an all-DRAFT dataset, is
 * honestly blocked; a labelled diagnostic mode shows how the logic behaves.
 */
export function EngineEvaluationPanel({
  projectId,
  onOpenProof,
}: {
  projectId: string;
  onOpenProof?: (requirementId: string, mode: EvaluationMode) => void;
}) {
  const [mode, setMode] = useState<EvaluationMode>("PRODUCTION");
  const evaluation = useEngineEvaluation(projectId, mode);
  const titles = useDatasetRequirementTitles();
  const decisions = evaluation.data ?? [];
  const allBlocked =
    decisions.length > 0 && decisions.every((d) => isBlockedState(d.final_state));
  const needInfo = decisions.filter(
    (d) => (d.missing_project_fact_keys ?? []).length > 0,
  ).length;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="label-meta">Mode</span>
          <div className="flex overflow-hidden rounded-sm border border-border text-[12px]">
            {(["PRODUCTION", "NON_PRODUCTION"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={
                  mode === m
                    ? "bg-primary px-2.5 py-[5px] font-medium text-primary-foreground"
                    : "px-2.5 py-[5px] text-muted-foreground hover:bg-secondary"
                }
              >
                {m === "PRODUCTION" ? "Production" : "Diagnostic"}
              </button>
            ))}
          </div>
        </div>
        {decisions.length > 0 && (
          <span className="text-[11.5px] text-muted-foreground">
            {decisions.length} requirements evaluated · {needInfo} need more information
          </span>
        )}
      </div>

      {evaluation.isLoading ? (
        <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
          Evaluating against the regulatory engine…
        </p>
      ) : evaluation.isError ? (
        <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
          {evaluation.error instanceof BackendUnavailableError
            ? "The regulatory engine backend isn't reachable right now."
            : "The engine could not evaluate this project."}
        </p>
      ) : (
        <>
          {mode === "PRODUCTION" && allBlocked && (
            <div className="border-b border-border bg-warning-surface px-5 py-3">
              <p className="text-[12.5px] font-medium">
                No authoritative result can be issued yet
              </p>
              <p className="mt-1 max-w-[80ch] text-[11.5px] leading-relaxed text-foreground/80">
                Every Rule Version in the regulatory dataset is still DRAFT, and
                IRIS refuses to issue a production determination from unverified
                rules. Switch to Diagnostic to see how the deterministic logic
                evaluates your facts — clearly labelled as non-authoritative.
              </p>
            </div>
          )}
          {mode === "NON_PRODUCTION" && (
            <div className="border-b border-border bg-info-surface px-5 py-2.5 text-[11.5px] text-foreground/80">
              Diagnostic evaluation — shows the deterministic logic over DRAFT
              rules. Not an authoritative regulatory determination.
            </div>
          )}
          <ul className="divide-y divide-border">
            {decisions.map((d) => (
              <DecisionRow
                key={d.requirement_id}
                decision={d}
                title={titles.data?.[d.requirement_id] ?? d.requirement_id}
                onOpenProof={onOpenProof ? (id) => onOpenProof(id, mode) : undefined}
              />
            ))}
          </ul>
        </>
      )}
      <p className="border-t border-border px-5 py-2.5 text-[11px] text-muted-foreground">
        Evaluated from this project's stored Project Facts. Viewing this does
        not store a decision.
      </p>
    </div>
  );
}

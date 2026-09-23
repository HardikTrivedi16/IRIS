import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useProject } from "@/lib/iris/project-context";
import { PageHeader, PageShell } from "@/components/iris/page";
import { EngineStatusStrip } from "@/components/iris/engine-status-strip";
import { EngineEvaluationPanel } from "@/components/iris/engine-evaluation-panel";
import {
  DecisionProofDrawer,
  type ProofTarget,
} from "@/components/iris/decision-proof-drawer";
import { useRegulatoryItems } from "@/lib/iris/use-regulatory-items";
import { stageLabel, summarizeItems } from "@/lib/iris/regulatory-items";

export const Route = createFileRoute("/requirements")({
  head: () => ({
    meta: [
      { title: "Requirements — IRIS" },
      {
        name: "description",
        content:
          "The regulatory requirements evaluated for this project by the deterministic rule engine, grouped by relevance, with authority and lifecycle stage.",
      },
      { property: "og:title", content: "Requirements — IRIS" },
      {
        property: "og:description",
        content:
          "Engine requirements grouped by relevance — diagnostic analysis is clearly separated from authoritative determinations.",
      },
    ],
  }),
  component: RequirementsPage,
});

function RequirementsPage() {
  const { activeProject } = useProject();
  const { items } = useRegulatoryItems(activeProject.id);
  const summary = useMemo(() => summarizeItems(items), [items]);
  const [authority, setAuthority] = useState("all");
  const [stage, setStage] = useState("all");
  const [proof, setProof] = useState<ProofTarget | null>(null);

  const authorities = useMemo(
    () => [...new Set(items.map((i) => i.authorityName).filter((a) => a !== "—"))].sort(),
    [items],
  );
  const stages = useMemo(
    () => [...new Set(items.flatMap((i) => i.lifecycleStageIds))].sort(),
    [items],
  );

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Regulatory intelligence" }, { label: "Requirements" }]}
        title="Requirements"
        description={`${activeProject.name} · evaluated by the deterministic rule engine`}
        actions={
          <Link
            to="/documents"
            className="rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors hover:bg-secondary"
          >
            Document register
          </Link>
        }
        meta={
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[12px] text-muted-foreground">
            <span>
              <span className="tabular font-semibold text-foreground">{summary.authoritative}</span>{" "}
              of {summary.total} authoritative
            </span>
            <span>
              <span className="tabular font-semibold text-foreground">{summary.diagnosticApplicable}</span>{" "}
              diagnostically applicable
            </span>
            <span>
              <span className="tabular font-semibold text-foreground">
                {summary.needsInformation + summary.needsReview}
              </span>{" "}
              need information or review
            </span>
            <span>
              <span className="tabular font-semibold text-foreground">{summary.unresolvedTriggers}</span>{" "}
              not yet evaluable
            </span>
          </div>
        }
      />

      <EngineStatusStrip />

      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-3 border border-border bg-surface px-4 py-3">
        <div className="flex items-center gap-2">
          <label className="label-meta" htmlFor="req-authority">
            Authority
          </label>
          <select
            id="req-authority"
            value={authority}
            onChange={(e) => setAuthority(e.target.value)}
            className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12.5px]"
          >
            <option value="all">All authorities</option>
            {authorities.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="label-meta" htmlFor="req-stage">
            Stage
          </label>
          <select
            id="req-stage"
            value={stage}
            onChange={(e) => setStage(e.target.value)}
            className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12.5px]"
          >
            <option value="all">All stages</option>
            {stages.map((s) => (
              <option key={s} value={s}>
                {stageLabel(s)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-5 border border-border bg-surface">
        <EngineEvaluationPanel
          projectId={activeProject.id}
          authorityFilter={authority}
          stageFilter={stage}
          onOpenProof={(requirementId, evaluationMode) =>
            setProof({ requirementId, evaluationMode })
          }
        />
      </div>

      <DecisionProofDrawer
        projectId={activeProject.id}
        target={proof}
        onClose={() => setProof(null)}
      />
    </PageShell>
  );
}

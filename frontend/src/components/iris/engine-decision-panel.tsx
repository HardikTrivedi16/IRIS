import { useState } from "react";
import { Tag } from "@/components/iris/status";
import { DataField } from "@/components/iris/page";
import { useEngineDecision } from "@/lib/iris/use-engine-decision";
import { BackendUnavailableError } from "@/lib/iris/api-client";
import type { Project } from "@/lib/iris/types";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

const FINAL_STATE_META: Record<string, { label: string; tone: Tone }> = {
  APPLICABLE: { label: "Applicable", tone: "success" },
  NOT_APPLICABLE: { label: "Not applicable", tone: "neutral" },
  REQUIRES_INFORMATION: { label: "Requires information", tone: "warning" },
  REQUIRES_REVIEW: { label: "Requires review", tone: "warning" },
  BLOCKED_DRAFT_NOT_PRODUCTION: {
    label: "Blocked — draft rule",
    tone: "danger",
  },
  BLOCKED_NO_RULE: { label: "Blocked — no rule defined", tone: "danger" },
  BLOCKED_UNKNOWN_REQUIREMENT: {
    label: "Blocked — unknown requirement",
    tone: "danger",
  },
  BLOCKED_UNKNOWN_RULE_VERSION_STATUS: {
    label: "Blocked — unrecognised rule version status",
    tone: "danger",
  },
};

function finalStateMeta(state: string) {
  return FINAL_STATE_META[state] ?? { label: state, tone: "neutral" as Tone };
}

/**
 * Renders the real Phase 9 engine Decision for a requirement that is
 * actually backed by the supplied regulatory dataset (see
 * engine-mapping.ts). Always evaluates PRODUCTION mode first — since every
 * Rule Version in the current dataset is DRAFT, that will correctly show
 * "Blocked — draft rule" rather than a fabricated production result. A
 * "View diagnostic evaluation" toggle re-queries in NON_PRODUCTION mode so
 * the underlying deterministic result can still be inspected, clearly
 * labelled as non-authoritative.
 */
export function EngineDecisionPanel({
  project,
  frontendRequirementId,
}: {
  project: Project;
  frontendRequirementId: string;
}) {
  const [showDiagnostic, setShowDiagnostic] = useState(false);
  const production = useEngineDecision(
    project,
    frontendRequirementId,
    "PRODUCTION",
  );
  const diagnostic = useEngineDecision(
    project,
    frontendRequirementId,
    "NON_PRODUCTION",
  );
  const active = showDiagnostic ? diagnostic : production;

  if (active.isLoading) {
    return (
      <p className="text-[12.5px] text-muted-foreground">
        Evaluating against the regulatory engine…
      </p>
    );
  }

  if (active.isError) {
    if (active.error instanceof BackendUnavailableError) {
      return (
        <div className="border-l-2 border-border-strong pl-3">
          <p className="text-[12.5px] text-muted-foreground">
            The regulatory engine backend isn't reachable right now, so a live
            decision can't be shown. The rest of this project's data is
            unaffected.
          </p>
        </div>
      );
    }
    return (
      <p className="text-[12.5px] text-destructive">
        The engine returned an error evaluating this requirement. Try again
        shortly.
      </p>
    );
  }

  const decision = active.data;
  if (!decision) return null;

  const meta = finalStateMeta(decision.final_state);
  const missing = decision.missing_project_fact_keys ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Tag tone={meta.tone}>{meta.label}</Tag>
        {decision.is_non_production_result && (
          <Tag tone="info">Non-production diagnostic</Tag>
        )}
        {decision.conflict_id && (
          <Tag tone="warning">Conflict {decision.conflict_id}</Tag>
        )}
      </div>

      <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
        <DataField
          label="Rule version"
          value={decision.rule_version_id ?? "—"}
        />
        <DataField
          label="Rule version status"
          value={decision.rule_version_status ?? "—"}
        />
        <DataField label="Engine version" value={decision.engine_version} />
        <DataField
          label="Decision ID"
          value={
            <span className="font-mono text-[11.5px] break-all">
              {decision.decision_id}
            </span>
          }
        />
      </div>

      {decision.explanation?.narrative && (
        <p className="border-l-2 border-info pl-3 text-[12.5px] leading-relaxed text-foreground">
          {decision.explanation.narrative}
        </p>
      )}

      {missing.length > 0 && (
        <div className="border-l-2 border-warning pl-3">
          <p className="text-[12.5px] font-medium text-warning">
            Missing facts needed for a decision
          </p>
          <ul className="mt-1 list-inside list-disc text-[12px] text-muted-foreground">
            {missing.map((key) => (
              <li key={key} className="font-mono">
                {key}
              </li>
            ))}
          </ul>
        </div>
      )}

      {decision.final_state === "BLOCKED_DRAFT_NOT_PRODUCTION" &&
        !showDiagnostic && (
          <button
            type="button"
            onClick={() => setShowDiagnostic(true)}
            className="text-[12px] font-medium text-info hover:opacity-80"
          >
            View non-production diagnostic evaluation →
          </button>
        )}
      {showDiagnostic && (
        <button
          type="button"
          onClick={() => setShowDiagnostic(false)}
          className="text-[12px] font-medium text-muted-foreground hover:opacity-80"
        >
          ← Back to production result
        </button>
      )}
    </div>
  );
}

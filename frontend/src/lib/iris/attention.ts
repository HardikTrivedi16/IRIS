/**
 * REGULATORY ATTENTION — pure aggregation of already-fetched, typed signals
 * into one deterministic, project-level "what needs attention" list.
 *
 * This is presentation organisation only, never a second rules engine and
 * never a risk/compliance score:
 *  - Engine signals come from POST /evaluate/all evaluated against the
 *    project's STORED Project Facts (irisApi.evaluateAll never takes ad-hoc
 *    fact overrides) — a Scenario Lab hypothetical result must never be
 *    passed into these functions.
 *  - Dependency signals come from GET /dependency-graph, which is itself
 *    only ever built from verified DEP-### edges (today: zero) — this
 *    module does not infer or fabricate a dependency relationship.
 *  - Nothing here reads or writes anything; every function is a pure
 *    mapping from typed API responses to AttentionItem[].
 *
 * Five distinct meanings are kept apart — see each builder's docstring.
 * None of them is "compliant"/"non-compliant"/a severity/a probability.
 */
import type {
  ApplicantApplication,
  DependencyGraphResponse,
  EngineDecision,
} from "./api-client";

export type AttentionCategory =
  | "NEEDS_INFORMATION"
  | "NEEDS_REVIEW"
  | "PROCESS_ATTENTION"
  | "DEPENDENCY_BLOCKED"
  | "UNVERIFIED_REGULATORY_KNOWLEDGE";

export interface AttentionAction {
  label: string;
  route: string;
}

export interface AttentionItem {
  /** Stable within one aggregation call — safe as a React list key. */
  id: string;
  source: "ENGINE" | "APPLICATION" | "DEPENDENCY";
  category: AttentionCategory;
  title: string;
  reason: string;
  requirementId?: string;
  missingFactKeys?: string[];
  action: AttentionAction;
}

export const ATTENTION_CATEGORY_LABEL: Record<AttentionCategory, string> = {
  NEEDS_INFORMATION: "Needs information",
  NEEDS_REVIEW: "Needs review",
  PROCESS_ATTENTION: "Process attention",
  DEPENDENCY_BLOCKED: "Dependency blocked",
  UNVERIFIED_REGULATORY_KNOWLEDGE: "Regulatory knowledge",
};

/** Presentation order only — not a risk ranking. */
const CATEGORY_ORDER: AttentionCategory[] = [
  "NEEDS_INFORMATION",
  "NEEDS_REVIEW",
  "PROCESS_ATTENTION",
  "DEPENDENCY_BLOCKED",
  "UNVERIFIED_REGULATORY_KNOWLEDGE",
];

/**
 * IRIS lacks project facts needed to determine a regulatory result
 * (REQUIRES_INFORMATION), or encountered ambiguity/conflict requiring human
 * review (REQUIRES_REVIEW), or is withholding an authoritative production
 * determination because the governing knowledge is still DRAFT
 * (BLOCKED_DRAFT_NOT_PRODUCTION — aggregated into ONE item, never one per
 * requirement). No requirement/rule id or count is hardcoded; everything
 * comes from the actual `decisions` the caller evaluated.
 */
export function attentionFromEngineDecisions(
  decisions: EngineDecision[],
  titleFor: (requirementId: string) => string,
): AttentionItem[] {
  const items: AttentionItem[] = [];
  const draftBlocked: EngineDecision[] = [];

  for (const d of decisions) {
    if (d.final_state === "REQUIRES_INFORMATION") {
      items.push({
        id: `needs-information-${d.requirement_id}`,
        source: "ENGINE",
        category: "NEEDS_INFORMATION",
        title: titleFor(d.requirement_id),
        reason:
          d.reason_text ??
          "IRIS cannot determine a regulatory result until the facts below are provided.",
        requirementId: d.requirement_id,
        missingFactKeys: d.missing_project_fact_keys,
        action: { label: "Provide project facts", route: "/evaluation" },
      });
    } else if (d.final_state === "REQUIRES_REVIEW") {
      items.push({
        id: `needs-review-${d.requirement_id}`,
        source: "ENGINE",
        category: "NEEDS_REVIEW",
        title: titleFor(d.requirement_id),
        reason:
          d.review_reason ??
          d.reason_text ??
          "IRIS flagged conflicting or ambiguous rule logic for this requirement.",
        requirementId: d.requirement_id,
        action: { label: "View evaluation", route: "/evaluation" },
      });
    } else if (d.final_state === "BLOCKED_DRAFT_NOT_PRODUCTION") {
      draftBlocked.push(d);
    }
  }

  if (draftBlocked.length > 0) {
    const n = draftBlocked.length;
    items.push({
      id: "unverified-regulatory-knowledge",
      source: "ENGINE",
      category: "UNVERIFIED_REGULATORY_KNOWLEDGE",
      title: "Regulatory knowledge awaiting verification",
      reason:
        `${n} requirement${n === 1 ? "" : "s"} currently rely on DRAFT Rule ` +
        `Version${n === 1 ? "" : "s"}. IRIS is withholding authoritative ` +
        "production determinations.",
      action: { label: "View evaluation", route: "/evaluation" },
    });
  }

  return items;
}

/**
 * An actual application/workflow needs attention — an OPERATIONAL state
 * (SLA timing, a department request, a rejection), never phrased as a
 * deterministic regulatory-engine conclusion. At most one item per
 * application (the most relevant condition), so one application cannot
 * flood the list.
 */
export function attentionFromApplications(
  applications: ApplicantApplication[],
): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const app of applications) {
    const title = app.title ?? app.application_id;
    let reason: string | null = null;
    if (app.sla.state === "BREACHED") {
      reason = "This application's processing SLA has been breached.";
    } else if (app.current_stage === "REJECTED") {
      reason = "This application was rejected by the department.";
    } else if (app.current_stage === "INFORMATION_REQUESTED") {
      reason = "The department has requested additional information for this application.";
    } else if (app.sla.state === "AT_RISK") {
      reason = "This application's processing SLA is at risk.";
    }
    if (!reason) continue;
    items.push({
      id: `process-attention-${app.id}`,
      source: "APPLICATION",
      category: "PROCESS_ATTENTION",
      title,
      reason,
      action: { label: "View your applications", route: "/grievances" },
    });
  }
  return items;
}

/**
 * A verified prerequisite prevents workflow readiness — sourced ONLY from
 * dependency_engine's own WorkflowStatus.BLOCKED, which itself only exists
 * when a verified DEP-### edge exists. With zero verified edges (the
 * current dataset), this naturally returns []. Never manufactured.
 */
export function attentionFromDependencyGraph(
  graph: DependencyGraphResponse | undefined,
): AttentionItem[] {
  if (!graph) return [];
  return graph.nodes
    .filter((n) => n.status === "BLOCKED")
    .map((n) => {
      const count = n.unmet_prerequisite_ids.length;
      return {
        id: `dependency-blocked-${n.requirement_id}`,
        source: "DEPENDENCY",
        category: "DEPENDENCY_BLOCKED",
        title: n.name,
        reason:
          count > 0
            ? `Blocked by ${count} unmet prerequisite requirement${count === 1 ? "" : "s"}.`
            : "Blocked by an unmet verified prerequisite.",
        requirementId: n.requirement_id,
        action: { label: "View regulatory map", route: "/regulatory-map" },
      } satisfies AttentionItem;
    });
}

/** Combines and orders every source's items: grouped by category in a fixed
 * order, stable title order within each group. Not a severity ranking. */
export function orderAttentionItems(items: AttentionItem[]): AttentionItem[] {
  return [...items].sort((a, b) => {
    const byCategory = CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category);
    if (byCategory !== 0) return byCategory;
    return a.title.localeCompare(b.title) || a.id.localeCompare(b.id);
  });
}

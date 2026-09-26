/**
 * ONE shared presentation model for the regulatory engine's output.
 *
 * Every Industry surface that shows regulatory intelligence (dashboard,
 * Requirements, Evaluation, Regulatory Map) consumes `RegulatoryItem[]` from
 * `buildRegulatoryItems` instead of the operational `project_requirements`
 * tracking table. This module is PURE: no fetching, no React, no I/O.
 *
 * Two concepts are kept explicitly apart and never merged:
 *   - `production`  — the authoritative determination. While the governing
 *     Rule Version is DRAFT the engine returns BLOCKED_DRAFT_NOT_PRODUCTION
 *     and that is what is reported here.
 *   - `diagnostic`  — a deterministic evaluation of the same (DRAFT) rule,
 *     useful for prototype analysis and ALWAYS non-authoritative.
 *
 * Nothing here decides regulatory applicability: states are copied verbatim
 * from engine decisions. `relevance` is only a presentation grouping.
 */
import type { EngineDecision, FactRegistryEntry } from "./api-client";
import type { GraphNode, Status } from "./types";

/** Dataset Requirement record as returned by GET /api/v1/requirements. */
export interface DatasetRequirement {
  requirement_id: string;
  title?: string;
  authority_id?: string;
  authority_name?: string | null;
  category?: string;
  lifecycle_stage_ids?: string[];
  latest_rule_version_id?: string | null;
  latest_rule_version_status?: string | null;
  /** Present on requirements superseded by a more precise successor (e.g. REQ-0004). */
  deprecation_note?: string | null;
}

/**
 * MATCHED            the engine had enough facts to decide (diagnostic
 *                    APPLICABLE / NOT_APPLICABLE)
 * NEEDS_INFORMATION  the engine needs facts for a rule family this project has
 *                    largely started to answer (a majority of its required
 *                    facts recorded, including one only this requirement
 *                    reads), or it flagged a review
 * OTHER              the engine cannot decide AND this project has recorded
 *                    no fact that is specific to this requirement's rule
 *                    family — an unresolved trigger, not a finding
 */
export type Relevance = "MATCHED" | "NEEDS_INFORMATION" | "OTHER";

export interface RegulatoryItem {
  requirementId: string;
  title: string;
  authorityId: string | null;
  authorityName: string;
  category: string | null;
  lifecycleStageIds: string[];
  ruleVersionId: string | null;
  ruleVersionStatus: string | null;
  production: {
    finalState: string;
    /** True only for a production result that is not a BLOCKED_* state. */
    authoritative: boolean;
    reasonText: string | null;
  };
  /** null until a diagnostic evaluation is available. */
  diagnostic: {
    finalState: string;
    missingFactKeys: string[];
    reviewReason: string | null;
    reasonText: string | null;
  } | null;
  /** Required fact keys of this requirement that have a stored value. */
  presentFactKeys: string[];
  relevance: Relevance;
  /** Historical/general requirement superseded by more precise ones; hidden from the default map. */
  deprecated: boolean;
}

export interface BuildInput {
  requirements: DatasetRequirement[];
  production: EngineDecision[];
  diagnostic: EngineDecision[] | undefined;
  registry: FactRegistryEntry[];
  /** The project's STORED Project Facts (never hypothetical). */
  facts: Record<string, unknown>;
}

const isBlocked = (s: string | null | undefined) => !!s && s.startsWith("BLOCKED_");
const hasValue = (v: unknown) => v !== null && v !== undefined;

export function buildRegulatoryItems(input: BuildInput): RegulatoryItem[] {
  const prodById = new Map(input.production.map((d) => [d.requirement_id, d]));
  const diagById = new Map((input.diagnostic ?? []).map((d) => [d.requirement_id, d]));

  // requirement_id -> fact keys its rules read; fact key -> #requirements that read it.
  // Both come from the Unified Project Fact Registry (derived from the dataset's
  // own Conditions) — no requirement or fact id is hardcoded here.
  const requiredKeys = new Map<string, string[]>();
  const consumers = new Map<string, number>();
  for (const entry of input.registry) {
    if (!entry.consumer_domains.includes("REGULATORY")) continue;
    consumers.set(entry.key, entry.requirement_ids.length);
    for (const rid of entry.requirement_ids) {
      requiredKeys.set(rid, [...(requiredKeys.get(rid) ?? []), entry.key]);
    }
  }

  return input.requirements
    .map<RegulatoryItem>((req) => {
      const id = req.requirement_id;
      const prod = prodById.get(id);
      const diag = diagById.get(id);
      const present = (requiredKeys.get(id) ?? []).filter((k) => hasValue(input.facts[k]));
      // "Specific" = a fact only this requirement's rules read. A fact shared by
      // several requirements (e.g. a location fact) says nothing about whether
      // THIS requirement's rule family is relevant to the project.
      const specificPresent = present.filter((k) => consumers.get(k) === 1);
      // ...and a majority of the requirement's rule-family facts must be recorded
      // before an information gap counts as this project's own gap.
      const required = requiredKeys.get(id) ?? [];
      const mostlyRecorded = required.length > 0 && present.length * 2 > required.length;

      let relevance: Relevance = "OTHER";
      if (diag) {
        if (diag.final_state === "APPLICABLE" || diag.final_state === "NOT_APPLICABLE") {
          relevance = "MATCHED";
        } else if (diag.final_state === "REQUIRES_REVIEW") {
          relevance = "NEEDS_INFORMATION";
        } else if (diag.final_state === "REQUIRES_INFORMATION") {
          relevance =
            specificPresent.length > 0 && mostlyRecorded ? "NEEDS_INFORMATION" : "OTHER";
        }
      }

      const prodState = prod?.final_state ?? "UNKNOWN";
      return {
        requirementId: id,
        title: req.title ?? id,
        authorityId: req.authority_id ?? null,
        authorityName: req.authority_name ?? req.authority_id ?? "—",
        category: req.category ?? null,
        lifecycleStageIds: req.lifecycle_stage_ids ?? [],
        ruleVersionId: prod?.rule_version_id ?? req.latest_rule_version_id ?? null,
        ruleVersionStatus: prod?.rule_version_status ?? req.latest_rule_version_status ?? null,
        production: {
          finalState: prodState,
          authoritative: !!prod && !isBlocked(prodState) && !prod.is_non_production_result,
          reasonText: prod?.reason_text ?? null,
        },
        diagnostic: diag
          ? {
              finalState: diag.final_state,
              missingFactKeys: diag.missing_project_fact_keys ?? [],
              reviewReason: diag.review_reason,
              reasonText: diag.reason_text,
            }
          : null,
        presentFactKeys: present,
        relevance,
        deprecated: !!req.deprecation_note,
      };
    })
    .sort((a, b) => a.requirementId.localeCompare(b.requirementId));
}

// ---------------------------------------------------------------------------
// Summaries — deterministic COUNTS, never a compliance percentage.
// ---------------------------------------------------------------------------

export interface RegulatorySummary {
  total: number;
  /** Production results that are authoritative (0 while everything is DRAFT). */
  authoritative: number;
  /** Production results withheld because the Rule Version is DRAFT/blocked. */
  awaitingVerifiedKnowledge: number;
  /** Diagnostic (non-authoritative) counts. */
  diagnosticApplicable: number;
  diagnosticNotApplicable: number;
  needsInformation: number;
  needsReview: number;
  unresolvedTriggers: number;
}

export function summarizeItems(items: RegulatoryItem[]): RegulatorySummary {
  const diagIs = (i: RegulatoryItem, s: string) => i.diagnostic?.finalState === s;
  return {
    total: items.length,
    authoritative: items.filter((i) => i.production.authoritative).length,
    awaitingVerifiedKnowledge: items.filter((i) => isBlocked(i.production.finalState)).length,
    diagnosticApplicable: items.filter((i) => diagIs(i, "APPLICABLE")).length,
    diagnosticNotApplicable: items.filter((i) => diagIs(i, "NOT_APPLICABLE")).length,
    needsInformation: items.filter(
      (i) => i.relevance === "NEEDS_INFORMATION" && !diagIs(i, "REQUIRES_REVIEW"),
    ).length,
    needsReview: items.filter((i) => diagIs(i, "REQUIRES_REVIEW")).length,
    unresolvedTriggers: items.filter((i) => i.relevance === "OTHER").length,
  };
}

export interface AuthorityRollup {
  authorityId: string | null;
  authorityName: string;
  total: number;
  diagnosticApplicable: number;
  needsInformation: number;
  authoritative: number;
}

/** Per-authority counts over the requirements this project is actually
 * matched to (diagnostic applicable or needing information). */
export function rollupByAuthority(items: RegulatoryItem[]): AuthorityRollup[] {
  const map = new Map<string, AuthorityRollup>();
  for (const i of items) {
    const applicable = i.diagnostic?.finalState === "APPLICABLE";
    const needs = i.relevance === "NEEDS_INFORMATION";
    if (!applicable && !needs) continue;
    const key = i.authorityId ?? i.authorityName;
    const row = map.get(key) ?? {
      authorityId: i.authorityId,
      authorityName: i.authorityName,
      total: 0,
      diagnosticApplicable: 0,
      needsInformation: 0,
      authoritative: 0,
    };
    row.total += 1;
    if (applicable) row.diagnosticApplicable += 1;
    if (needs) row.needsInformation += 1;
    if (i.production.authoritative) row.authoritative += 1;
    map.set(key, row);
  }
  return [...map.values()].sort(
    (a, b) => b.total - a.total || a.authorityName.localeCompare(b.authorityName),
  );
}

// ---------------------------------------------------------------------------
// Lifecycle stage labels (dataset ids -> display text; unknown ids pass through)
// ---------------------------------------------------------------------------

export function stageLabel(id: string): string {
  return id
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join("-");
}

// ---------------------------------------------------------------------------
// Regulatory Map nodes — DATA SOURCE ONLY. No edges are produced: the dataset
// has zero verified Requirement->Requirement dependencies and none is invented.
// `status` only drives the existing node colour; it is NOT a completion state.
// ---------------------------------------------------------------------------

export function toMapNodes(items: RegulatoryItem[]): GraphNode[] {
  return items.map<GraphNode>((i) => {
    const s = i.diagnostic?.finalState;
    const status: Status =
      s === "APPLICABLE"
        ? "attention"
        : s === "NOT_APPLICABLE"
          ? "not-applicable"
          : "not-ready";
    const node: GraphNode = {
      id: i.requirementId,
      label: i.title,
      type: "approval",
      status,
      authority: i.authorityName,
    };
    const description = i.diagnostic?.reasonText ?? i.production.reasonText;
    if (description) node.description = description;
    if (i.ruleVersionId) {
      node.source = `${i.ruleVersionId}${i.ruleVersionStatus ? ` (${i.ruleVersionStatus})` : ""}`;
    }
    return node;
  });
}

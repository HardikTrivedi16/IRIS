export type Status =
  "ready" | "attention" | "blocked" | "not-applicable" | "not-ready";

export type Industry =
  | "pharmaceutical"
  | "food"
  | "automobile-ev"
  | "electronics-esdm"
  | "chemicals"
  | "other";

/** Display labels for the closed Industry union (presentation only). */
export const INDUSTRY_LABELS: Record<Industry, string> = {
  pharmaceutical: "Pharmaceuticals",
  food: "Food",
  "automobile-ev": "Automobile / EV",
  "electronics-esdm": "Electronics / ESDM",
  chemicals: "Chemicals",
  other: "Other",
};

/** Maps a raw stored `industry` value (any case, `_` or `-` separators) onto
 * the closed Industry union. Presentation only — never used for regulatory
 * decisions (the engine reads Project Facts). */
export function normalizeIndustry(raw: unknown): Industry {
  const v = String(raw ?? "").trim().toLowerCase().replace(/[_\s]+/g, "-");
  if (["pharmaceutical", "pharmaceuticals", "pharma", "life-sciences", "lifesciences"].includes(v)) return "pharmaceutical";
  if (["food", "food-processing", "food-and-agro-processing", "agro-processing"].includes(v)) return "food";
  if (["automobile-ev", "auto-ev", "automobile", "automotive", "ev"].includes(v)) return "automobile-ev";
  if (["electronics-esdm", "electronics", "esdm"].includes(v)) return "electronics-esdm";
  if (["chemicals", "chemical", "specialty-chemicals"].includes(v)) return "chemicals";
  return "other";
}

export type ProjectStage =
  "pre-establishment" | "construction" | "commissioning" | "operations";

export type ProjectScale = "small" | "medium" | "large";

export interface ProjectCharacteristics {
  hazardousChemicals: boolean;
  hazardousWaste: boolean;
  wastewater: boolean;
  airEmissions: boolean;
  waterUse: boolean;
  chemicalStorage: boolean;
}

export interface Project {
  id: string;
  name: string;
  industry: Industry;
  activity: string;
  location: string;
  stage: ProjectStage;
  scale: ProjectScale;
  characteristics: ProjectCharacteristics;
  workers: number;
}

export interface DocumentItem {
  id: string;
  name: string;
  status: "extracted" | "missing-info" | "mismatch";
  uploadedAt: string;
  /** Explicit legacy (prior-facility) evidence — not evidence of the current facility. */
  legacy?: { label: string; priorFacility: string | null };
  extractedInformation?: {
    label: string;
    projectProfile: string;
    uploadedDocument: string;
  }[];
  issues?: string[];
}

export interface Requirement {
  id: string;
  name: string;
  authority: string;
  stage: string;
  status: Status;
  applicability: "applicable" | "not-applicable";
  documents: { total: number; complete: number };
  dependsOn: string[];
  blocks: string[];
  source: string;
  description: string;
  reason?: string;
  timeline: string;
}

export interface JourneyStage {
  id: string;
  label: string;
  status: Status;
}

export interface UpcomingAction {
  id: string;
  label: string;
  priority: "high" | "medium" | "low";
}

export interface RegulatorySource {
  id: string;
  name: string;
  fullName: string;
  sourceType: string;
  lastVerified: string;
  documentCount: string;
  description: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "project" | "approval" | "milestone";
  status: Status;
  authority?: string;
  description?: string;
  dependsOn?: string[];
  blocks?: string[];
  documents?: { total: number; complete: number };
  source?: string;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export interface ChatCitation {
  chunkId: string;
  sourceId: string;
  documentName: string | null;
  pageNumber: number | null;
  sectionReference: string | null;
  /** "iris_regulatory_dataset" | "iris_live_evaluation" | "iris_internal" —
   * always internal IRIS grounding for now, never an official source. */
  sourceType: string;
  /** Human-readable provenance disclaimer, e.g. "IRIS Regulatory Dataset —
   * ... (not an official government publication)". Always shown next to
   * the citation so it is never mistaken for an official document. */
  sourceLabel: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  source?: { name: string; type: string };
  /** Grounded citations returned by the real Ask IRIS backend, if any. */
  citations?: ChatCitation[];
  /** Advisory caveats surfaced alongside the answer (e.g. low grounding). */
  warnings?: string[];
  /** True when Phase 9/NetworkX data did not support a confident answer. */
  insufficientInformation?: boolean;
  /** True when the backend flagged this answer for human review (e.g. a
   * citation could not be validated, or verification disagreed). */
  requiresHumanReview?: boolean;
  /** The model's prose contradicted the Rule Engine and was replaced by
   * the engine's own result (backend engine_guard). */
  answerWithheld?: boolean;
  /** The question concerned a facility other than the active project. */
  outOfScope?: boolean;
  /** Ad-hoc/hypothetical facts used for THIS answer only (never persisted
   * as this project's stored Project Facts) — empty when the answer used
   * only stored facts. Kept distinct from any authoritative project data
   * so a hypothetical value is never displayed as if it were saved. */
  hypotheticalFacts?: Record<string, unknown>;
  /** True while the request to the backend is in flight. */
  pending?: boolean;
  /** True when the request failed (backend/AI unavailable, etc). */
  isError?: boolean;
}

// ChangeImpactResult (a hand-authored "requirements affected / new pathways /
// before-path / after-path / explanation" shape) was removed: it only ever
// described a hardcoded illustrative scenario on the Change Impact page.
// Change Impact is now a real, deterministic diff of two engine evaluations —
// see ChangeImpactResponse in lib/iris/api-client.ts, which mirrors the
// backend's POST /api/v1/projects/{id}/change-impact response.

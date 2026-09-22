/**
 * Shared vocabulary/helpers for the existing deterministic Consistency
 * Engine (backend/app/consistency.py via POST /projects/{id}/consistency-check).
 *
 * Nothing here compares anything — that stays entirely server-side, in plain
 * code, with no LLM in the loop. This module only holds the presentation
 * vocabulary (status labels/tones, the fixed set of comparable fields, how a
 * reference observation's basis is labelled) and the one bridge from the
 * existing AI extractor's output to a consistency observation. Both
 * `components/iris/pre-submission-check.tsx` (embedded in Documents) and
 * `routes/consistency.tsx` (the standalone Evidence Consistency page) import
 * from here so the status vocabulary and comparison formatting are defined
 * exactly once.
 */
import type {
  ConsistencyField,
  ConsistencyObservationInput,
  ConsistencyStatus,
  ExtractedDocumentFields,
} from "./api-client";
import type { DecisionTone } from "./decision-states";

/** A document (or manual entry) whose values were added to this session's
 * check set. Session-only: never persisted. */
export interface CheckSource {
  id: string;
  name: string;
  kind: "DOCUMENT" | "MANUAL";
  observations: ConsistencyObservationInput[];
}

/** Exactly the engine's own status vocabulary (app/consistency.py) — no
 * NON_COMPLIANT or other status is ever added here. */
export const STATUS_META: Record<ConsistencyStatus, { label: string; tone: DecisionTone }> = {
  CONFLICT: { label: "Conflict", tone: "danger" },
  EXPIRED: { label: "Expired", tone: "danger" },
  MISSING: { label: "Missing", tone: "warning" },
  REVIEW_REQUIRED: { label: "Review required", tone: "warning" },
  LOW_CONFIDENCE: { label: "Low confidence", tone: "warning" },
  NOT_COMPARABLE: { label: "Not comparable", tone: "neutral" },
  CONSISTENT: { label: "Consistent", tone: "success" },
};

/** Display order for a findings list: the statuses that need attention
 * first, CONSISTENT last (it must never dominate the screen). Mirrors the
 * backend's own `order` in `run_consistency_check`. */
export const STATUS_ORDER: ConsistencyStatus[] = [
  "CONFLICT",
  "EXPIRED",
  "MISSING",
  "REVIEW_REQUIRED",
  "LOW_CONFIDENCE",
  "NOT_COMPARABLE",
  "CONSISTENT",
];

export const FIELD_OPTIONS: { value: ConsistencyField; label: string; needsUnit?: boolean }[] = [
  { value: "entity_name", label: "Entity / business name" },
  { value: "address", label: "Premises address" },
  { value: "registration_number", label: "Registration / licence number" },
  { value: "batch_number", label: "Batch number" },
  { value: "net_quantity", label: "Net quantity / pack size", needsUnit: true },
  { value: "production_capacity", label: "Production capacity", needsUnit: true },
  { value: "valid_until", label: "Validity end date (YYYY-MM-DD)" },
];

export const BASIS_LABEL: Record<string, string> = {
  PROJECT_RECORD: "Project record",
  EXPLICIT_REFERENCE: "Reference document",
  FIRST_SUBMITTED: "First source",
};

export function fmt(v: unknown, unit?: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  return unit ? `${String(v)} ${unit}` : String(v);
}

/**
 * Maps the existing AI extractor's output onto consistency observations.
 * Only same-meaning fields are mapped; each keeps the extractor's own
 * confidence, evidence span and source page. The extractor does not produce
 * batch numbers or pack sizes — those can be entered manually.
 */
export function observationsFromExtraction(
  data: ExtractedDocumentFields,
  documentName: string,
  documentId: string,
): ConsistencyObservationInput[] {
  const map: [keyof ExtractedDocumentFields, ConsistencyField][] = [
    ["business_name", "entity_name"],
    ["location", "address"],
    ["registration_number", "registration_number"],
    ["valid_until", "valid_until"],
  ];
  const source = (key: string): ConsistencyObservationInput["source"] => {
    const s: ConsistencyObservationInput["source"] = {
      kind: "DOCUMENT",
      document_id: documentId,
      document_name: documentName,
    };
    const page = data.field_source_pages[key];
    const evidence = data.field_evidence[key];
    if (typeof page === "number" && page >= 1) s.page = page;
    if (evidence) s.evidence_text = evidence;
    return s;
  };
  const out: ConsistencyObservationInput[] = [];
  for (const [key, field] of map) {
    const value = data[key];
    if (typeof value !== "string" || !value.trim()) continue;
    const obs: ConsistencyObservationInput = { field, value, source: source(key) };
    const conf = data.field_confidence[key];
    if (typeof conf === "number") obs.confidence = conf;
    out.push(obs);
  }
  if (typeof data.capacity_value === "number" && data.capacity_unit) {
    const obs: ConsistencyObservationInput = {
      field: "production_capacity",
      value: data.capacity_value,
      unit: data.capacity_unit,
      source: source("capacity_value"),
    };
    const conf = data.field_confidence["capacity_value"];
    if (typeof conf === "number") obs.confidence = conf;
    out.push(obs);
  }
  return out;
}

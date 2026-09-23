/**
 * IRIS API client — Industry portal.
 *
 * Injects the Supabase JWT as Authorization: Bearer on all requests when
 * a session is active. When no session (demo mode), sends requests without
 * auth — the backend accepts them in demo mode.
 *
 * Data never flows to Supabase directly from here. All requests go to the
 * IRIS FastAPI backend.
 */

import type { Requirement } from "./types";

const API_BASE =
  (import.meta.env["VITE_API_URL"] as string) || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    /** The parsed `detail` field of the error body, when it is structured
     * rather than a plain string (e.g. the per-field 422 returned by
     * /change-impact). Kept separate from `message`, which must stay a
     * string for Error's own contract. */
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class BackendUnavailableError extends ApiError {
  constructor() {
    super(503, "Backend unavailable — is the IRIS API server running?");
    this.name = "BackendUnavailableError";
  }
}

/** Get the current auth token (if any) from session storage injected by AuthProvider. */
function getStoredToken(): string | null {
  // Auth token is injected by AuthContext into a module-level variable
  return _authToken;
}

/** Module-level token store — updated by AuthProvider via setAuthToken(). */
let _authToken: string | null = null;

/** Called by AuthProvider when the session changes. */
export function setAuthToken(token: string | null): void {
  _authToken = token;
}

/** Builds an ApiError from a non-OK response, preserving a structured
 * `detail` payload (e.g. the per-field 422 from /change-impact) instead of
 * stringifying it into "[object Object]". */
async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text().catch(() => "");
  let detail: unknown = text;
  try {
    detail = JSON.parse(text)?.detail ?? text;
  } catch {
    // Fall back to raw text if not JSON
  }
  const message =
    typeof detail === "string" ? detail : (text || response.statusText);
  return new ApiError(response.status, message, detail);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new BackendUnavailableError();
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** Like request(), but for multipart/form-data (file upload) bodies —
 * deliberately does NOT set Content-Type so the browser can add its own
 * multipart boundary. Only used by ocrExtract() today. */
async function requestFormData<T>(path: string, formData: FormData): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      body: formData,
      headers,
    });
  } catch {
    throw new BackendUnavailableError();
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Engine / regulatory API
// ---------------------------------------------------------------------------

interface Project {
  id: string;
  name: string;
  industry: string;
  stage?: string;
  facts?: Record<string, unknown>;
}

export type EvaluationMode = "PRODUCTION" | "NON_PRODUCTION";

/** Mirrors backend app/schemas.py::ProjectIn — the existing public.projects
 * columns only. Characteristics are an operational profile, NOT regulatory
 * facts; engine inputs are captured separately as Project Facts. */
export interface NewProjectPayload {
  name: string;
  industry: string;
  activity?: string;
  location?: string;
  stage?: string;
  scale?: string;
  workers?: number;
  characteristics?: Record<string, boolean>;
}

interface EvaluateParams {
  projectId: string;
  requirementId: string;
  evaluationMode?: EvaluationMode;
  facts?: Record<string, unknown>;
  persist?: boolean;
}

/** Mirrors the Phase 9 engine's Decision dict (backend/iris_engine/decision.py)
 * exactly as returned by POST /api/v1/evaluate — only the fields the
 * frontend actually reads are typed here; the engine may return more. */
export interface EngineDecision {
  project_id: string;
  requirement_id: string;
  rule_id: string | null;
  rule_version_id: string | null;
  rule_version_status: string | null;
  final_state: string;
  is_non_production_result: boolean;
  conflict_id: string | null;
  review_reason: string | null;
  reason_text: string | null;
  decision_id: string;
  engine_version: string;
  missing_project_fact_keys: string[];
  explanation?: { narrative?: string | null } | null;
}

/** One requirement node from GET /projects/{id}/dependency-graph
 * (backend/app/graph/service.py). `status` is dependency_engine's own
 * WorkflowStatus — whether this APPLICABLE requirement's verified
 * prerequisites are satisfied. It is workflow-sequencing readiness, not
 * regulatory applicability and not an application's operational stage. */
export interface DependencyGraphNode {
  requirement_id: string;
  requirement_code: string;
  name: string;
  status: "BLOCKED" | "AVAILABLE" | "INDEPENDENT";
  parallel_classification: string;
  parallel_constraint: string | null;
  duration: number | null;
  direct_prerequisite_ids: string[];
  unmet_prerequisite_ids: string[];
}

/** Mirrors GET /projects/{id}/dependency-graph. Only ever built from
 * verified DEP-### edges (today: zero) — never a fabricated dependency. */
export interface DependencyGraphResponse {
  nodes: DependencyGraphNode[];
  edges: unknown[];
  ignored_dependencies: unknown[];
  topological_order: string[];
  critical_path: string[];
  critical_path_duration: number | null;
  critical_path_available: boolean;
  excluded_requirements: { requirement_id: string; final_state: string }[];
  dependency_data_note: string;
}

/** Mirrors GET /api/v1/engine (backend/app/engine_service.py::engine_info). */
export interface EngineInfo {
  current_engine_version: string;
  engine_version_history: string[];
  evaluation_modes: string[];
  dataset_root: string;
  counts: {
    conditions: number;
    rules: number;
    rule_versions: number;
    requirements: number;
    rule_versions_by_status: Record<string, number>;
  };
  known_conflicts: unknown[];
  notes: string[];
}

// ---------------------------------------------------------------------------
// Ask IRIS
// ---------------------------------------------------------------------------

export interface AskCitation {
  chunk_id: string;
  source_id: string;
  document_name?: string | null;
  page_number?: number | null;
  section_reference?: string | null;
  /** "iris_regulatory_dataset" | "iris_live_evaluation" | "iris_internal" —
   * always an internal IRIS grounding kind for now. Never presented as an
   * official government source; distinguishes IRIS's own dataset/live
   * results from any real official document source added later. */
  source_type: string;
  /** Human-readable disclaimer for this citation's provenance, e.g. "IRIS
   * Regulatory Dataset — ... (not an official government publication)". */
  source_label: string;
}

export interface AskDecisionSummary {
  requirement_id: string;
  final_state: string | null;
  reason_text: string | null;
}

export interface AskDependencyStatus {
  requirement_id: string;
  status: string | null;
  unmet_prerequisite_ids: string[];
}

export interface AskFactContext {
  uses_hypothetical_facts: boolean;
  /** Keys from the request's ad-hoc `facts`, if any — NOT this project's
   * stored Project Facts. */
  hypothetical_fact_keys: string[];
  hypothetical_facts: Record<string, unknown>;
  note: string;
}

export interface AskIrisResponse {
  question: string;
  answer: string;
  insufficient_information: boolean;
  requires_human_review: boolean;
  citations_valid: boolean;
  citations: AskCitation[];
  warnings: string[];
  fact_context: AskFactContext;
  authoritative_context: {
    evaluation_mode: string;
    decisions: AskDecisionSummary[];
    dependency_status: AskDependencyStatus[];
  };
  /** Deterministic check of the answer against the engine's result. When a
   * contradiction is found the prose is withheld and `answer` carries the
   * engine's own result instead. */
  engine_consistency: {
    checked: boolean;
    contradictions: {
      requirement_id: string;
      sentence: string;
      claimed: string;
      engine_state: string | null;
    }[];
    answer_withheld: boolean;
    withheld_answer?: string | null;
  };
  scope: { out_of_scope: boolean; reason: string | null };
  ai_enabled: boolean;
}

interface AskIrisRequest {
  question: string;
  requirementId?: string;
  evaluationMode?: EvaluationMode;
  facts?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Project Fact schema + deterministic Change Impact
// ---------------------------------------------------------------------------

/** One supported project fact — the ONE Project Fact vocabulary shared by
 * regulatory evaluation and scheme eligibility, derived by the backend from
 * the regulatory dataset's own Conditions/Rule Versions AND the scheme
 * catalogue's own Scheme Conditions/Schemes (GET /api/v1/facts/registry).
 * Nothing here is authored in application code. A key referenced by both
 * domains is ONE entry with consumer_domains: ["REGULATORY", "SCHEME"]. */
export interface FactRegistryEntry {
  key: string;
  value_type: "boolean" | "number" | "string" | "mixed" | "unknown";
  typed_input_supported: boolean;
  predicate_types: string[];
  units: string[];
  /** True when this key is referenced with 2+ distinct, non-empty units
   * across its consumers — no conversion is performed, so typed input is
   * refused (typed_input_supported is also false in this case). */
  units_conflict: boolean;
  /** Which deterministic subsystem(s) reference this fact. */
  consumer_domains: ("REGULATORY" | "SCHEME")[];
  condition_ids: string[];
  scheme_condition_ids: string[];
  /** Comparison values the dataset's regulatory + scheme conditions
   * reference — NOT an exhaustive or legally authoritative list of
   * permitted values. */
  values_referenced_by_conditions: unknown[];
  /** Backward-compatible alias for values_referenced_by_conditions. */
  values_referenced_by_rules: unknown[];
  rule_version_ids: string[];
  requirement_ids: string[];
  scheme_ids: string[];
  values_note: string;
}

export type ChangeImpactCategory =
  | "UNCHANGED"
  | "NEWLY_APPLICABLE"
  | "NO_LONGER_APPLICABLE"
  | "REQUIRES_INFORMATION"
  | "REQUIRES_REVIEW"
  | "CHANGED";

export interface ChangeImpactSide {
  final_state: string;
  reason_text: string | null;
  missing_project_fact_keys: string[];
  rule_version_id: string | null;
  rule_version_status: string | null;
  decision_id: string;
  review_reason: string | null;
  conflict_id: string | null;
  is_non_production_result: boolean;
  /** The engine's own classification sub-group result, when the requirement
   * has one (REQ-0004's Central/State licensing tier). Null otherwise. This
   * can move while final_state stays the same. */
  classification: {
    combined_state: string | null;
    rule_results: Record<string, string>;
    conflict_id: string | null;
    review_reason: string | null;
  } | null;
}

export interface ChangeImpactRequirement {
  requirement_id: string;
  requirement_title: string;
  authority_id: string | null;
  category: ChangeImpactCategory;
  before: ChangeImpactSide;
  after: ChangeImpactSide;
  facts_this_requirement_uses: string[];
  changed_facts_used_by_this_requirement: string[];
}

export interface ProposedFactChange {
  key: string;
  previous_value: unknown;
  proposed_value: unknown;
  value_type: string | null;
  units: string[];
}

export interface ChangeImpactResponse {
  project_id: string;
  evaluation_mode: EvaluationMode;
  engine_version: string | null;
  /** True only when evaluated in PRODUCTION mode AND at least one
   * requirement was not blocked by the DRAFT rule-version lifecycle. */
  authoritative: boolean;
  proposed_changes: ProposedFactChange[];
  ignored_changes: ProposedFactChange[];
  summary: Record<ChangeImpactCategory, number>;
  requirements: ChangeImpactRequirement[];
  notes: string[];
  persistence_note: string;
}

// ---------------------------------------------------------------------------
// Decision Proof — a reshaping of the engine's own Decision (backend
// app/decision_proof.py). Nothing here is computed client-side.
// ---------------------------------------------------------------------------

/** One node of the engine's rendered condition evaluation tree
 * (iris_engine/condition_tree.py). */
export interface ConditionTreeNode {
  condition_id: string;
  predicate_type: string | null;
  operator: string | null;
  result: "TRUE" | "FALSE" | "UNKNOWN" | null;
  missing_fact_keys: string[];
  error: string | null;
  operands: string[];
  target_variable_key: string | null;
  expected_value: unknown;
  actual_project_value: unknown;
  children: ConditionTreeNode[];
}

export interface ProofCondition {
  rule_id: string;
  condition_id: string;
  fact_key: string | null;
  operator: string | null;
  expected_value: unknown;
  actual_value: unknown;
  result: string | null;
  error: string | null;
}

export interface DecisionProof {
  requirement: { requirement_id: string; title: string; authority_id: string | null };
  outcome: {
    final_state: string;
    reason_text: string | null;
    narrative: string | null;
    evaluation_mode: EvaluationMode;
    is_non_production_result: boolean;
    review_reason: string | null;
    conflict_id: string | null;
  };
  refuses_to_guess: boolean;
  refusal_reasons: string[];
  identity: {
    decision_id: string;
    evaluated_at: string;
    engine_version: string;
    rule_id: string | null;
    rule_version_id: string | null;
    rule_version_status: string | null;
    rule_version_ids: string[];
  };
  facts_used: { key: string; value: unknown; provided: boolean }[];
  declared_required_facts: string[];
  missing_facts: string[];
  matched_conditions: ProofCondition[];
  unmatched_conditions: ProofCondition[];
  condition_tree: ConditionTreeNode | null;
  rule_output_mapping: Record<string, string>;
  classification: {
    block: {
      combined_state: string | null;
      conflict_id: string | null;
      review_reason: string | null;
      rule_results: Record<string, string>;
    };
    condition_trees: Record<string, ConditionTreeNode | null> | null;
    output_mappings: Record<string, Record<string, string>> | null;
  } | null;
  provenance: {
    /** Whether the referenced Regulatory Fact / Evidence / Source records
     * exist in the dataset. This is NOT a statement that the source is
     * archived or that a human has verified anything — see `source_archival`
     * and `human_verification`. */
    status: "RESOLVED" | "PARTIAL" | "UNRESOLVED";
    instrument_id: string | null;
    authority_id: string | null;
    source_ids: string[];
    evidence_ids: string[];
    regulatory_fact_ids: string[];
    resolved_records: {
      authorities: Record<string, unknown>[];
      instruments: Record<string, unknown>[];
      regulatory_facts: Record<string, unknown>[];
      evidence: Record<string, unknown>[];
      sources: Record<string, unknown>[];
    } | null;
    rule_versions: {
      rule_version_id: string;
      status: string | null;
      confidence: string | null;
      effective_end_date: string | null;
    }[];
    source_archival: {
      state: "ALL_ARCHIVED" | "NOT_ALL_ARCHIVED" | "NO_SOURCES";
      archived: string[];
      not_archived: string[];
    };
    human_verification: {
      state: "HUMAN_VERIFIED" | "NOT_VERIFIED";
      verification_ids: string[];
    };
    /** Everything that is missing or unverified, stated plainly. */
    gaps: string[];
    note: string | null;
  };
  fact_basis: "STORED" | "HYPOTHETICAL";
  hypothetical_facts: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Pre-submission consistency check (backend app/consistency.py) — objective
// data comparison, decided deterministically server-side. Read-only.
// ---------------------------------------------------------------------------

export type ConsistencyField =
  | "entity_name"
  | "address"
  | "registration_number"
  | "batch_number"
  | "net_quantity"
  | "production_capacity"
  | "valid_until";

export type ConsistencyStatus =
  | "CONSISTENT"
  | "CONFLICT"
  | "REVIEW_REQUIRED"
  | "EXPIRED"
  | "MISSING"
  | "NOT_COMPARABLE"
  | "LOW_CONFIDENCE";

export interface ConsistencyObservationInput {
  field: ConsistencyField;
  value: string | number | null;
  unit?: string;
  confidence?: number;
  is_reference?: boolean;
  observation_id?: string;
  source: {
    kind: "DOCUMENT" | "MANUAL";
    document_id?: string;
    document_name?: string;
    page?: number;
    evidence_text?: string;
  };
}

export interface ConsistencyObservationView {
  observation_id: string;
  raw_value: unknown;
  unit: string | null;
  normalized_value: unknown;
  confidence: number | null;
  source: {
    kind: string;
    document_id?: string | null;
    document_name?: string | null;
    page?: number | null;
    evidence_text?: string | null;
    fact_key?: string;
  };
}

export interface ConsistencyCheck {
  check_id: string;
  field: ConsistencyField;
  field_label: string;
  status: ConsistencyStatus;
  message: string;
  human_review_required: boolean;
  reference: ConsistencyObservationView | null;
  candidate: ConsistencyObservationView | null;
  reference_basis: "EXPLICIT_REFERENCE" | "PROJECT_RECORD" | "FIRST_SUBMITTED" | null;
  comparison_rule: string;
  days_remaining?: number;
}

export interface ConsistencyResult {
  as_of_date: string;
  checks_performed: number;
  issues_found: number;
  human_review_required: boolean;
  summary: Record<ConsistencyStatus, number>;
  checks: ConsistencyCheck[];
  uncompared_fields: { field: string; field_label: string; reason: string }[];
  project_facts_modified: false;
  policy: { low_confidence_threshold: number; note: string };
}

// ---------------------------------------------------------------------------
// Upcoming compliance & renewals (backend app/renewals.py) — derived only from
// expiry dates on record; the action window is a labelled demo policy.
// ---------------------------------------------------------------------------

export type RenewalStatus =
  | "EXPIRED"
  | "ACTION_REQUIRED"
  | "UPCOMING"
  | "NO_EXPIRY_ON_RECORD"
  | "COMPLETED";

export interface RenewalItem {
  record_id: string;
  title: string;
  document_number: string | null;
  issuing_authority: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  days_remaining: number | null;
  status: RenewalStatus;
  source_kind: "CONFIRMED_DOCUMENT" | "STORED_METADATA" | "SYNTHETIC_DEMO";
  source_label: string;
  is_synthetic: boolean;
}

export interface RenewalRegister {
  as_of_date: string;
  action_window_days: number;
  action_window_is_policy: true;
  summary: Record<RenewalStatus, number>;
  items: RenewalItem[];
  notes: string[];
}

// ---------------------------------------------------------------------------
// Grievance preparation / tracking / hand-off (backend app/grievances.py).
// NOT a statutory grievance filing; does not replace MAITRI / NSWS.
// ---------------------------------------------------------------------------

export type GrievanceStatus = "OPEN" | "ASSIGNED" | "UNDER_REVIEW" | "RESOLVED" | "CLOSED";
export type GrievanceCategory =
  | "PROCESSING_DELAY"
  | "INFORMATION_REQUEST_UNCLEAR"
  | "DOCUMENT_HANDLING"
  | "OTHER";

export const GRIEVANCE_CATEGORY_LABEL: Record<GrievanceCategory, string> = {
  PROCESSING_DELAY: "Processing delay",
  INFORMATION_REQUEST_UNCLEAR: "Information request unclear",
  DOCUMENT_HANDLING: "Document handling",
  OTHER: "Other",
};

export interface ApplicantSla {
  state: string | null;
  due_at: string | null;
  warning_at: string | null;
  elapsed_pct: number | null;
}

/** An application as its applicant may see it — stage and SLA timing only. */
export interface ApplicantApplication {
  id: string;
  application_id: string;
  requirement_id: string;
  title: string | null;
  department_id: string;
  current_stage: string;
  created_at: string;
  completed_at: string | null;
  sla: ApplicantSla;
  data_classification: string | null;
}

export interface GrievanceHistoryEntry {
  id: string;
  from_status: GrievanceStatus | null;
  to_status: GrievanceStatus;
  actor_id: string;
  actor_name: string | null;
  actor_role: string;
  note: string | null;
  created_at: string;
}

export interface Grievance {
  id: string;
  grievance_number: string;
  project_id: string;
  application_id: string;
  department_id: string;
  category: GrievanceCategory;
  category_label: string;
  description: string;
  status: GrievanceStatus;
  context_snapshot: {
    captured_at: string;
    application_number: string | null;
    requirement_id: string | null;
    title: string | null;
    current_stage: string | null;
    current_stage_entered_at: string | null;
    application_created_at: string | null;
    sla: ApplicantSla;
    data_classification: string | null;
  };
  raised_by_name: string | null;
  assigned_officer_name: string | null;
  resolution_note: string | null;
  created_at: string;
  updated_at: string;
  history?: GrievanceHistoryEntry[];
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Scheme framework (backend app/schemes.py) — deterministic matching against a
// verified catalogue. The shipped catalogue is empty by design.
// ---------------------------------------------------------------------------

export interface SchemeMatch {
  scheme_id: string;
  name: string;
  administering_authority_name: string | null;
  outcome: "POTENTIALLY_ELIGIBLE" | "NEEDS_INFORMATION" | "NOT_ELIGIBLE" | "CANNOT_EVALUATE";
  missing_facts: string[];
  errors: string[];
  why: {
    scheme_condition_id: string;
    fact_key: string | null;
    operator: string | null;
    expected_value: unknown;
    unit: string | null;
    project_value: unknown;
    result: string;
    source_reference: { clause?: string; page_number?: number; document_title?: string } | null;
    description: string | null;
  }[];
  not_in_force_reason: string | null;
  official_source: { url?: string; document_title?: string } | null;
  benefits_summary: string | null;
  status: string;
  confidence: string;
  last_verified: { date?: string } | null;
  is_authoritative_catalogue_entry: boolean;
  /** Independent of `outcome` — whether the scheme is currently accepting
   * applications at all. Never derived from `outcome`, and never changes
   * it. See app/schemes.py's module docstring ("Two independent claims"). */
  application_status: SchemeApplicationStatus | null;
  application_window: SchemeApplicationWindow | null;
  supersedes: string | null;
  superseded_by: string | null;
}

export type SchemeApplicationStatus =
  | "VERIFIED_OPEN"
  | "VERIFIED_CLOSED"
  | "VERIFIED_CONTINUING_BUT_NOT_OPEN_FOR_NEW_APPLICATIONS"
  | "VERIFIED_PERIODIC_CALL_FOR_PROPOSALS"
  | "SELECTION_COMPLETED"
  | "NO_CURRENT_WINDOW"
  | "UNRESOLVED_CURRENT_STATUS"
  | "DISCONTINUED"
  | "SUPERSEDED";

export interface SchemeApplicationWindow {
  mode:
    | "CONTINUOUS"
    | "PERIODIC_EOI"
    | "FIXED_WINDOW"
    | "PROPOSAL_BASED"
    | "SELECTION_COMPLETED"
    | "CLOSED"
    | "UNKNOWN";
  opens: string | null;
  closes: string | null;
  as_of_date: string | null;
  source_reference: Record<string, unknown> | null;
}

export interface SchemeMatchResponse {
  catalogue_state: "READY" | "AWAITING_VERIFIED_DATA" | "INVALID";
  mode: EvaluationMode;
  as_of_date?: string;
  counts?: { total: number; active_verified: number };
  results: SchemeMatch[];
  catalogue_errors: string[];
  notes: string[];
}

// ---------------------------------------------------------------------------
// Document / OCR extraction (existing AI module, Phase 4-5 — read-only,
// never auto-persists Project Facts; see backend/app/routers/ai_documents.py)
// ---------------------------------------------------------------------------

export interface ExtractedDocumentFields {
  business_name: string | null;
  project_name: string | null;
  registration_number: string | null;
  location: string | null;
  state: string | null;
  district: string | null;
  capacity_value: number | null;
  capacity_unit: string | null;
  investment_crore_inr: number | null;
  worker_count: number | null;
  authorised_person: string | null;
  issue_date: string | null;
  valid_until: string | null;
  field_confidence: Record<string, number>;
  field_evidence: Record<string, string>;
  field_source_pages: Record<string, number>;
}

export interface DocumentExtractionResult {
  data: ExtractedDocumentFields;
  safety_valid: boolean;
  requires_human_review: boolean;
  warnings: string[];
}

export interface DocumentRecord {
  id: string;
  project_id: string;
  name: string;
  storage_path: string | null;
  status: "uploaded" | "extracted" | "missing-info" | "mismatch";
  linked_requirement_ids: string[];
  uploaded_at: string;
  /** Present only when the synthetic-demo metadata explicitly names this
   * document as evidence of a PRIOR facility (backend/demo-data). */
  legacy_evidence?: {
    label: string;
    prior_facility: string | null;
    current_facility: string | null;
    basis: string | null;
  } | null;
  /** Added in migration 0006 — display detail for the document register. */
  issues?: string[];
  extracted_information?: {
    label: string;
    projectProfile: string;
    uploadedDocument: string;
  }[];
}

/** One row of the project Overview activity timeline (activity_events table). */
export interface ActivityEvent {
  id: string;
  project_id: string;
  actor: string | null;
  event_type: string;
  message: string;
  created_at: string;
}

/** Mirrors GET /api/v1/ai/status (backend/app/ai_integration/service.py). */
export interface AiStatus {
  ai_enabled: boolean;
  ollama_reachable: boolean;
  generation_model: string;
  fallback_model: string;
  verifier_enabled: boolean;
  verifier_provider: string;
  /** Local Tesseract availability — independent of Ollama. */
  ocr_available: boolean;
}

/** Result of local Tesseract OCR — raw text only. Never a confidence score
 * (Tesseract doesn't give a meaningful one at this level) and never
 * persisted anywhere; the returned text is meant to be reviewed/edited and
 * then run through the existing extractDocument() step. */
export interface OcrResult {
  text: string;
  char_count: number;
  engine: string;
  warnings: string[];
  /** Present for PDFs: how each page's text was obtained. EMBEDDED_TEXT is
   * the PDF's own text layer (not OCR); OCR is Tesseract on a rendered page
   * that had no usable text. */
  source_format?: "pdf";
  page_count?: number;
  pages?: {
    page: number;
    method: "EMBEDDED_TEXT" | "OCR" | "OCR_UNAVAILABLE" | "NO_TEXT_FOUND";
    char_count: number;
    warnings: string[];
  }[];
}

export const irisApi = {
  getHealth: () => request<{ status: string }>("/health"),

  listProjects: () => request<Project[]>("/api/v1/projects"),

  /** POST /api/v1/projects — omit `id` so the backend generates one. The
   * backend stamps owner_id from the caller's session and rejects an
   * existing id with 409 (it never overwrites). */
  createProject: (payload: NewProjectPayload) =>
    request<Project>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getProject: (id: string) => request<Project>(`/api/v1/projects/${id}`),

  getProjectFacts: (projectId: string) =>
    request<{ facts: Record<string, unknown> }>(
      `/api/v1/projects/${projectId}/facts`,
    ),

  mergeProjectFacts: (projectId: string, facts: Record<string, unknown>) =>
    request<{ facts: Record<string, unknown> }>(
      `/api/v1/projects/${projectId}/facts`,
      {
        method: "POST",
        body: JSON.stringify({ facts }),
      },
    ),

  listRequirements: () => request<unknown[]>("/api/v1/requirements"),

  /** Per-project regulatory readiness checklist (real Supabase data —
   * migration 0006). Returns the frontend Requirement shape directly. */
  getProjectRequirements: (projectId: string) =>
    request<Requirement[]>(`/api/v1/projects/${projectId}/requirements`),

  /** Recent activity events for the project Overview timeline. */
  getProjectActivity: (projectId: string) =>
    request<ActivityEvent[]>(`/api/v1/projects/${projectId}/activity`),

  evaluate: (params: EvaluateParams) =>
    request<{ decision: EngineDecision }>("/api/v1/evaluate", {
      method: "POST",
      body: JSON.stringify({
        project_id: params.projectId,
        requirement_id: params.requirementId,
        evaluation_mode: params.evaluationMode ?? "PRODUCTION",
        facts: params.facts ?? {},
        persist: params.persist,
      }),
    }),

  /** Evaluates every dataset requirement for a project from its STORED
   * Project Facts only (no ad-hoc overrides). persist defaults to false here:
   * this backs read-only views, which must not write audit records. */
  evaluateAll: (params: {
    projectId: string;
    evaluationMode?: EvaluationMode;
    persist?: boolean;
  }) =>
    request<{ decisions: EngineDecision[] }>("/api/v1/evaluate/all", {
      method: "POST",
      body: JSON.stringify({
        project_id: params.projectId,
        evaluation_mode: params.evaluationMode ?? "PRODUCTION",
        facts: {},
        persist: params.persist ?? false,
      }),
    }),

  /** Decision Proof from the project's STORED facts, or — when
   * `hypotheticalFacts` is given — from a non-persisted copy with those
   * facts applied (labelled HYPOTHETICAL by the backend). */
  getDecisionProof: (params: {
    projectId: string;
    requirementId: string;
    evaluationMode: EvaluationMode;
    hypotheticalFacts?: Record<string, unknown>;
  }) => {
    const path = `/api/v1/projects/${params.projectId}/decision-proof/${params.requirementId}`;
    if (params.hypotheticalFacts && Object.keys(params.hypotheticalFacts).length) {
      return request<{ proof: DecisionProof }>(path, {
        method: "POST",
        body: JSON.stringify({
          evaluation_mode: params.evaluationMode,
          hypothetical_facts: params.hypotheticalFacts,
        }),
      });
    }
    return request<{ proof: DecisionProof }>(
      `${path}?evaluation_mode=${params.evaluationMode}`,
    );
  },

  /** Deterministic pre-submission check. Read-only: never writes facts. */
  runConsistencyCheck: (
    projectId: string,
    payload: {
      observations: ConsistencyObservationInput[];
      requiredFields?: ConsistencyField[];
      includeProjectRecord?: boolean;
    },
  ) =>
    request<ConsistencyResult>(`/api/v1/projects/${projectId}/consistency-check`, {
      method: "POST",
      body: JSON.stringify({
        observations: payload.observations,
        required_fields: payload.requiredFields ?? [],
        include_project_record: payload.includeProjectRecord ?? true,
      }),
    }),

  /** Committed synthetic observations (no results) for the demo project's
   * legacy evidence; `available:false` for every other project. */
  getLegacyConsistencyObservations: (projectId: string) =>
    request<
      | { available: false }
      | {
          available: true;
          description: string | null;
          basis: string | null;
          observations: ConsistencyObservationInput[];
        }
    >(`/api/v1/projects/${projectId}/consistency/legacy-observations`),

  getRenewals: (projectId: string, actionWindowDays?: number) =>
    request<RenewalRegister>(
      `/api/v1/projects/${projectId}/renewals${
        actionWindowDays ? `?action_window_days=${actionWindowDays}` : ""
      }`,
    ),

  /** The project's own applications (stage + SLA timing only). */
  listProjectApplications: (projectId: string) =>
    request<ApplicantApplication[]>(`/api/v1/projects/${projectId}/applications`),

  /** Real, engine-native dependency graph — built from the project's STORED
   * facts only. Read-only; never used to fabricate a dependency. */
  getDependencyGraph: (projectId: string, evaluationMode: EvaluationMode = "PRODUCTION") =>
    request<DependencyGraphResponse>(
      `/api/v1/projects/${projectId}/dependency-graph?evaluation_mode=${evaluationMode}`,
    ),

  listGrievances: (projectId: string) =>
    request<Grievance[]>(`/api/v1/projects/${projectId}/grievances`),

  getGrievance: (projectId: string, grievanceId: string) =>
    request<Grievance>(`/api/v1/projects/${projectId}/grievances/${grievanceId}`),

  /** Explicit applicant submission — never called automatically. */
  createGrievance: (
    projectId: string,
    body: {
      application_id: string;
      category: GrievanceCategory;
      description: string;
      acknowledge_not_statutory: boolean;
    },
  ) =>
    request<Grievance>(`/api/v1/projects/${projectId}/grievances`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getProjectSchemes: (projectId: string, mode: EvaluationMode = "PRODUCTION") =>
    request<SchemeMatchResponse>(`/api/v1/projects/${projectId}/schemes?mode=${mode}`),

  engineInfo: () => request<EngineInfo>("/api/v1/engine"),

  /** Supported project facts, derived from the regulatory dataset. */
  getFactRegistry: () =>
    request<{ facts: FactRegistryEntry[]; note: string }>(
      "/api/v1/facts/registry",
    ),

  /** Deterministic before/after diff for a proposed fact change. This is a
   * PREVIEW — the backend never persists the proposed facts. */
  analyseChangeImpact: (
    projectId: string,
    payload: {
      proposedFacts: Record<string, unknown>;
      evaluationMode?: EvaluationMode;
    },
  ) =>
    request<ChangeImpactResponse>(
      `/api/v1/projects/${projectId}/change-impact`,
      {
        method: "POST",
        body: JSON.stringify({
          proposed_facts: payload.proposedFacts,
          evaluation_mode: payload.evaluationMode ?? "PRODUCTION",
        }),
      },
    ),

  getAuthMe: () => request<unknown>("/api/v1/auth/me"),

  askIris: (projectId: string, payload: AskIrisRequest) =>
    request<AskIrisResponse>(`/api/v1/projects/${projectId}/ask`, {
      method: "POST",
      body: JSON.stringify({
        question: payload.question,
        requirement_id: payload.requirementId,
        evaluation_mode: payload.evaluationMode ?? "PRODUCTION",
        facts: payload.facts ?? {},
      }),
    }),

  // --- Documents / OCR extraction ------------------------------------------

  listDocuments: (projectId: string) =>
    request<DocumentRecord[]>(`/api/v1/projects/${projectId}/documents`),

  createDocument: (
    projectId: string,
    doc: {
      name: string;
      storage_path?: string;
      status?: DocumentRecord["status"];
      linked_requirement_ids?: string[];
    },
  ) =>
    request<DocumentRecord>(`/api/v1/projects/${projectId}/documents`, {
      method: "POST",
      body: JSON.stringify(doc),
    }),

  /** Extraction only — never mutates Project Facts. A human must review the
   * result and call mergeProjectFacts explicitly to persist anything. */
  extractDocument: (
    projectId: string,
    payload: {
      text: string;
      documentType?: string;
      provenance?: {
        source_id?: string;
        document_name?: string;
        page_number?: number;
        section_reference?: string;
      };
    },
  ) =>
    request<DocumentExtractionResult>(
      `/api/v1/projects/${projectId}/documents/extract`,
      {
        method: "POST",
        body: JSON.stringify({
          text: payload.text,
          document_type: payload.documentType,
          provenance: payload.provenance,
        }),
      },
    ),

  getAiStatus: () => request<AiStatus>("/api/v1/ai/status"),

  /** Local Tesseract OCR — image -> raw text only. Never mutates Project
   * Facts or Document records; the returned text still has to go through
   * extractDocument() (LLM extraction) and an explicit confirm step. */
  ocrExtract: (projectId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return requestFormData<OcrResult>(
      `/api/v1/projects/${projectId}/documents/ocr`,
      formData,
    );
  },
};

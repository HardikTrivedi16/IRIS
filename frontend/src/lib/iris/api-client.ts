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
    const text = await response.text().catch(() => "");
    let detail = text;
    try {
      detail = JSON.parse(text)?.detail ?? text;
    } catch {
      // Fall back to raw text if not JSON
    }
    throw new ApiError(response.status, detail);
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
    const text = await response.text().catch(() => "");
    let detail = text;
    try {
      detail = JSON.parse(text)?.detail ?? text;
    } catch {
      // Fall back to raw text if not JSON
    }
    throw new ApiError(response.status, detail);
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
  reason_text: string | null;
  decision_id: string;
  engine_version: string;
  missing_project_fact_keys: string[];
  explanation?: { narrative?: string | null } | null;
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
  ai_enabled: boolean;
}

interface AskIrisRequest {
  question: string;
  requirementId?: string;
  evaluationMode?: EvaluationMode;
  facts?: Record<string, unknown>;
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
}

export const irisApi = {
  getHealth: () => request<{ status: string }>("/health"),

  listProjects: () => request<Project[]>("/api/v1/projects"),
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

  engineInfo: () => request<EngineInfo>("/api/v1/engine"),

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

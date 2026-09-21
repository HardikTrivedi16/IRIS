/**
 * Department portal API client.
 *
 * All requests go to the IRIS FastAPI backend. Auth token injected via
 * the module-level token store shared with api-client.ts.
 * No direct Supabase data access. No service-role key.
 *
 * Government-only endpoints (SLA, Bottlenecks, User Management) are in
 * separate sections. They must NEVER be called from Industry portal pages.
 */

const API_BASE =
  (import.meta.env["VITE_API_URL"] as string) || "http://localhost:8000";

// Shared token store (set by AuthProvider via setAuthToken in api-client.ts)
import { setAuthToken } from "@/lib/iris/api-client";
export { setAuthToken };

// ---------------------------------------------------------------------------
// Types — Applications
// ---------------------------------------------------------------------------

export type ApplicationStage =
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "INFORMATION_REQUESTED"
  | "INSPECTION_SCHEDULED"
  | "INSPECTION_COMPLETED"
  | "RECOMMENDED"
  | "APPROVED"
  | "REJECTED";

export type SlaState = "WITHIN_SLA" | "AT_RISK" | "BREACHED" | "COMPLETED";

export interface SlaInfo {
  state: SlaState;
  due_at: string | null;
  warning_at: string | null;
  elapsed_pct: number;
}

export interface Application {
  id: string;
  application_id: string;
  project_id: string;
  requirement_id: string;
  department_id: string;
  title: string | null;
  applicant_name: string | null;
  current_stage: ApplicationStage;
  assigned_officer_id: string | null;
  assigned_officer_name: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  sla: SlaInfo;
}

export interface ApplicationDetail extends Application {
  stage_history: StageHistoryEntry[];
  assignment_history: AssignmentHistoryEntry[];
  operational_events: OperationalEvent[];
  sla_instance: Record<string, unknown> | null;
  engine_decision: Record<string, unknown> | null;
  project: Record<string, unknown> | null;
}

export interface StageHistoryEntry {
  id: string;
  application_id: string;
  previous_stage: string | null;
  new_stage: ApplicationStage;
  actor: string;
  reason: string | null;
  created_at: string;
}

export interface AssignmentHistoryEntry {
  id: string;
  application_id: string;
  officer_id: string;
  officer_name: string;
  assigned_by: string;
  reason: string | null;
  created_at: string;
}

export interface OperationalEvent {
  id: string;
  application_id: string;
  event_type: string;
  message: string;
  actor: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Types — SLA Intelligence (Government-only)
// ---------------------------------------------------------------------------

export interface SlaPolicy {
  id: string;
  name: string;
  requirement_type: string | null;
  duration_hours: number;
  warning_pct: number;
  description: string | null;
}

export interface SlaStageTarget {
  id: string;
  policy_id: string;
  stage: ApplicationStage;
  target_hours: number;
  warning_pct: number;
  description: string | null;
}

export interface SlaApplicationSummary {
  id: string;
  application_id: string;
  title: string | null;
  current_stage: string;
  department_id: string;
  requirement_id: string;
  assigned_officer_name: string | null;
  sla_state: SlaState;
  due_at: string | null;
  warning_at: string | null;
  elapsed_pct: number;
  age_hours: number;
  created_at: string;
  completed_at: string | null;
}

export interface SlaStagePerformance {
  stage: string;
  entry_count: number;
  completed_count: number;
  avg_duration_hours: number | null;
  median_duration_hours: number | null;
  min_duration_hours: number | null;
  max_duration_hours: number | null;
  target_hours: number | null;
  target_warning_pct: number | null;
  vs_target: "WITHIN" | "AT_RISK" | "EXCEEDED" | null;
}

export interface SlaDashboard {
  kpis: {
    total: number;
    active: number;
    completed: number;
    within_sla: number;
    at_risk: number;
    breached: number;
    aging_0_7d: number;
    aging_7_30d: number;
    aging_30_60d: number;
    aging_over_60d: number;
  };
  applications: SlaApplicationSummary[];
  stage_performance: SlaStagePerformance[];
  breach_by_stage: { stage: string; count: number }[];
}

// ---------------------------------------------------------------------------
// Types — Bottleneck Analytics (Government-only)
// ---------------------------------------------------------------------------

export interface StageBottleneck {
  stage: string;
  backlog: number;
  avg_duration_hours: number | null;
  median_duration_hours: number | null;
  min_duration_hours: number | null;
  max_duration_hours: number | null;
  entry_count: number;
  completed_count: number;
  at_risk_count: number;
  breached_count: number;
  sla_breach_pct: number;
  bottleneck_score: number;
  rank: number;
  aging_7d: number;
  aging_14d: number;
  aging_30d: number;
  throughput_7d: number;
  throughput_30d: number;
}

export interface OfficerWorkload {
  officer_id: string;
  officer_name: string;
  department_id: string | null;
  role: string;
  is_active: boolean;
  active_applications: number;
  completed_applications: number;
  total_applications: number;
  at_risk_count: number;
  breached_count: number;
}

export interface ProcessingTrend {
  date: string;
  stage: string;
  entered: number;
  exited: number;
}

export interface BottleneckReport {
  generated_at: string;
  total_active: number;
  total_applications: number;
  methodology: string;
  stages: StageBottleneck[];
  officers: OfficerWorkload[];
  top_bottleneck_stage: string | null;
  top_bottleneck_score: number | null;
}

// ---------------------------------------------------------------------------
// Types — Dashboard
// ---------------------------------------------------------------------------

export interface DashboardRecentApplication {
  id: string;
  application_id: string;
  project_id: string;
  requirement_id: string;
  title: string | null;
  current_stage: ApplicationStage;
  assigned_officer_name: string | null;
  sla_state: SlaState;
  created_at: string;
}

export interface DashboardData {
  kpis: {
    total: number;
    pending: number;
    in_progress: number;
    completed: number;
    sla_at_risk: number;
    sla_breached: number;
  };
  pipeline: { stage: string; count: number }[];
  recent_applications: DashboardRecentApplication[];
  attention_required: {
    id: string;
    application_id: string;
    title: string | null;
    current_stage: ApplicationStage;
    reasons: string[];
    sla_state: SlaState;
  }[];
}

// ---------------------------------------------------------------------------
// Types — User Management (Government-only)
// ---------------------------------------------------------------------------

export interface DepartmentUser {
  id: string;
  department_id: string;
  name: string;
  email: string | null;
  role: string;
  is_active: boolean;
  supabase_auth_uid: string | null;
  created_at: string;
  updated_at: string;
  department_name: string | null;
}

export interface UserProfile {
  id: string;
  supabase_auth_uid: string;
  email: string | null;
  full_name: string | null;
  iris_role: string;
  department_id: string | null;
  department_name: string | null;
  is_active: boolean;
  pending_government_link: boolean;
  provider: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export const STAGE_LABELS: Record<ApplicationStage, string> = {
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under Review",
  INFORMATION_REQUESTED: "Information Requested",
  INSPECTION_SCHEDULED: "Inspection Scheduled",
  INSPECTION_COMPLETED: "Inspection Completed",
  RECOMMENDED: "Recommended",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

export const STAGE_TONE: Record<
  ApplicationStage,
  "neutral" | "info" | "warning" | "success" | "danger"
> = {
  SUBMITTED: "neutral",
  UNDER_REVIEW: "info",
  INFORMATION_REQUESTED: "warning",
  INSPECTION_SCHEDULED: "info",
  INSPECTION_COMPLETED: "info",
  RECOMMENDED: "success",
  APPROVED: "success",
  REJECTED: "danger",
};

export const SLA_LABEL: Record<SlaState, string> = {
  WITHIN_SLA: "Within SLA",
  AT_RISK: "At Risk",
  BREACHED: "Breached",
  COMPLETED: "Completed",
};

export const SLA_TONE: Record<
  SlaState,
  "neutral" | "info" | "warning" | "success" | "danger"
> = {
  WITHIN_SLA: "success",
  AT_RISK: "warning",
  BREACHED: "danger",
  COMPLETED: "neutral",
};

export const ALLOWED_TRANSITIONS: Record<ApplicationStage, ApplicationStage[]> =
  {
    SUBMITTED: ["UNDER_REVIEW"],
    UNDER_REVIEW: [
      "INFORMATION_REQUESTED",
      "INSPECTION_SCHEDULED",
      "RECOMMENDED",
      "REJECTED",
    ],
    INFORMATION_REQUESTED: ["UNDER_REVIEW"],
    INSPECTION_SCHEDULED: ["INSPECTION_COMPLETED", "UNDER_REVIEW"],
    INSPECTION_COMPLETED: ["RECOMMENDED", "UNDER_REVIEW", "REJECTED"],
    RECOMMENDED: ["APPROVED", "REJECTED"],
    APPROVED: [],
    REJECTED: [],
  };

export function applicationAge(createdAt: string): string {
  const ms = Date.now() - new Date(createdAt).getTime();
  const days = Math.floor(ms / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export function formatHours(hours: number | null | undefined): string {
  if (hours == null) return "—";
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = hours / 24;
  return `${days.toFixed(1)}d`;
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

function getToken(): string | null {
  // Token is maintained by auth-context.tsx via setAuthToken
  // We import it lazily to avoid circular deps
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require("@/lib/iris/api-client");
    return (mod as { _getToken?: () => string | null })._getToken?.() ?? null;
  } catch {
    return null;
  }
}

// Standalone token variable updated by AuthProvider
let _deptToken: string | null = null;
export function setDeptAuthToken(token: string | null) {
  _deptToken = token;
}

async function deptRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (_deptToken) {
    headers["Authorization"] = `Bearer ${_deptToken}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new Error(
      "Department API unavailable — is the IRIS backend running?",
    );
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    let detail = text;
    try {
      detail = JSON.parse(text)?.detail ?? text;
    } catch {
      // Fall back to raw text if not JSON
    }
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Department API — Applications
// ---------------------------------------------------------------------------

export const departmentApi = {
  // Dashboard
  getDashboard: () =>
    deptRequest<DashboardData>("/api/v1/department/dashboard"),

  // Applications
  listApplications: (
    params: {
      search?: string;
      status?: ApplicationStage | "";
      sla_state?: SlaState | "";
      requirement_id?: string;
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.status) query.set("status", params.status);
    if (params.sla_state) query.set("sla_state", params.sla_state);
    if (params.requirement_id)
      query.set("requirement_id", params.requirement_id);
    if (params.limit) query.set("limit", String(params.limit));
    if (params.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return deptRequest<{ total: number; items: Application[] }>(
      `/api/v1/department/applications${qs ? `?${qs}` : ""}`,
    );
  },

  getApplication: (appId: string) =>
    deptRequest<ApplicationDetail>(`/api/v1/department/applications/${appId}`),

  createApplication: (data: {
    project_id: string;
    requirement_id: string;
    department_id: string;
    title?: string;
    applicant_name?: string;
  }) =>
    deptRequest<Application>("/api/v1/department/applications", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  assignOfficer: (
    appId: string,
    data: { officer_id: string; officer_name: string; reason?: string },
  ) =>
    deptRequest<ApplicationDetail>(
      `/api/v1/department/applications/${appId}/assign`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    ),

  transitionStage: (
    appId: string,
    data: { new_stage: ApplicationStage; reason?: string },
  ) =>
    deptRequest<ApplicationDetail>(
      `/api/v1/department/applications/${appId}/transition`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    ),

  getTimeline: (appId: string) =>
    deptRequest<OperationalEvent[]>(
      `/api/v1/department/applications/${appId}/timeline`,
    ),

  // SLA Policies
  listSLAPolicies: () =>
    deptRequest<SlaPolicy[]>("/api/v1/department/sla/policies"),

  createSLAPolicy: (data: {
    name: string;
    duration_hours: number;
    warning_pct?: number;
    description?: string;
  }) =>
    deptRequest<SlaPolicy>("/api/v1/department/sla/policies", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // SLA Intelligence (Government-only)
  getSlaDashboard: () =>
    deptRequest<SlaDashboard>("/api/v1/department/sla/dashboard"),

  getSlaApplications: (
    params: { sla_state?: SlaState; limit?: number; offset?: number } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.sla_state) q.set("sla_state", params.sla_state);
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return deptRequest<{ total: number; items: SlaApplicationSummary[] }>(
      `/api/v1/department/sla/applications${qs ? `?${qs}` : ""}`,
    );
  },

  getSlaStagePerformance: () =>
    deptRequest<SlaStagePerformance[]>(
      "/api/v1/department/sla/stage-performance",
    ),

  listSlaStageTargets: (policyId?: string) => {
    const q = policyId ? `?policy_id=${policyId}` : "";
    return deptRequest<SlaStageTarget[]>(
      `/api/v1/department/sla/stage-targets${q}`,
    );
  },

  // Bottleneck Analytics (Government-only)
  getBottleneckReport: () =>
    deptRequest<BottleneckReport>("/api/v1/department/bottlenecks/report"),

  getBottleneckStages: () =>
    deptRequest<StageBottleneck[]>("/api/v1/department/bottlenecks/stages"),

  getBottleneckOfficers: () =>
    deptRequest<OfficerWorkload[]>("/api/v1/department/bottlenecks/officers"),

  getBottleneckTrends: (days = 14) =>
    deptRequest<ProcessingTrend[]>(
      `/api/v1/department/bottlenecks/trends?days=${days}`,
    ),

  // User Management (Government Admin-only)
  listDepartmentUsers: (departmentId?: string) => {
    const q = departmentId ? `?department_id=${departmentId}` : "";
    return deptRequest<DepartmentUser[]>(`/api/v1/department/users${q}`);
  },

  createDepartmentUser: (data: {
    name: string;
    email?: string;
    role: string;
    department_id: string;
  }) =>
    deptRequest<DepartmentUser>("/api/v1/department/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getDepartmentUser: (userId: string) =>
    deptRequest<DepartmentUser>(`/api/v1/department/users/${userId}`),

  updateDepartmentUser: (
    userId: string,
    data: { role?: string; is_active?: boolean; department_id?: string },
  ) =>
    deptRequest<DepartmentUser>(`/api/v1/department/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  linkUserProfile: (data: {
    user_profile_id: string;
    department_id: string;
    role: string;
    name?: string;
  }) =>
    deptRequest<UserProfile>("/api/v1/department/users/link-profile", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listUserProfiles: (pendingOnly = false) =>
    deptRequest<UserProfile[]>(
      `/api/v1/department/user-profiles${pendingOnly ? "?pending_only=true" : ""}`,
    ),
};

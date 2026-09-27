import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Search } from "lucide-react";
import {
  departmentApi,
  STAGE_LABELS,
  SLA_LABEL,
  applicationAge,
} from "@/lib/iris/department-api";
import type { ApplicationStage, SlaState } from "@/lib/iris/department-api";
import { useAuth } from "@/lib/auth-context";
import { PageShell, PageHeader } from "@/components/iris/page";
import { cn } from "@/lib/utils";
import { BackendUnavailableError } from "@/lib/iris/api-client";

export const Route = createFileRoute("/department/applications")({
  head: () => ({
    meta: [
      { title: "Applications — IRIS Gov" },
      {
        name: "description",
        content: "Browse and filter all government department applications.",
      },
    ],
  }),
  component: ApplicationsPage,
});

const ALL_STAGES: ApplicationStage[] = [
  "SUBMITTED",
  "UNDER_REVIEW",
  "INFORMATION_REQUESTED",
  "INSPECTION_SCHEDULED",
  "INSPECTION_COMPLETED",
  "RECOMMENDED",
  "APPROVED",
  "REJECTED",
];

const SLA_STATES: SlaState[] = [
  "WITHIN_SLA",
  "AT_RISK",
  "BREACHED",
  "COMPLETED",
];

const STAGE_TONE_CLASSES: Record<ApplicationStage, string> = {
  SUBMITTED: "border-border bg-neutral-surface text-muted-foreground",
  UNDER_REVIEW: "border-info/25 bg-info-surface text-info",
  INFORMATION_REQUESTED: "border-warning/30 bg-warning-surface text-warning",
  INSPECTION_SCHEDULED: "border-info/25 bg-info-surface text-info",
  INSPECTION_COMPLETED: "border-info/25 bg-info-surface text-info",
  RECOMMENDED: "border-success/25 bg-success-surface text-success",
  APPROVED: "border-success/25 bg-success-surface text-success",
  REJECTED: "border-destructive/25 bg-danger-surface text-destructive",
};

const SLA_TONE_CLASSES: Record<SlaState, string> = {
  WITHIN_SLA: "border-success/25 bg-success-surface text-success",
  AT_RISK: "border-warning/30 bg-warning-surface text-warning",
  BREACHED: "border-destructive/25 bg-danger-surface text-destructive",
  COMPLETED: "border-border bg-neutral-surface text-muted-foreground",
};

/**
 * Creation modal for POST /api/v1/department/applications (departmentApi.
 * createApplication — already existed, was just never wired to any UI
 * control). department_id is locked to the signed-in officer's own
 * department rather than offered as a free choice: the backend is the
 * authoritative enforcer of department isolation, but the UI shouldn't
 * invite a cross-department attempt it knows will be refused.
 */
function NewApplicationModal({
  departmentId,
  departmentName,
  onClose,
}: {
  departmentId: string;
  departmentName: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [projectId, setProjectId] = useState("");
  const [requirementId, setRequirementId] = useState("");
  const [title, setTitle] = useState("");
  const [applicantName, setApplicantName] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      departmentApi.createApplication({
        project_id: projectId.trim(),
        requirement_id: requirementId.trim(),
        department_id: departmentId,
        ...(title.trim() ? { title: title.trim() } : {}),
        ...(applicantName.trim() ? { applicant_name: applicantName.trim() } : {}),
      }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({
        queryKey: ["department", "applications"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["department", "dashboard"],
      });
      void navigate({
        to: "/department/application/$appId",
        params: { appId: created.id },
      });
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
        <h3 className="text-[16px] font-semibold text-foreground">
          New Application
        </h3>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          Register an application for an existing applicant project and
          regulatory requirement.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
          className="mt-4 space-y-3 text-[13px]"
        >
          <div>
            <label className="mb-1 block text-[12px] font-medium">
              Project ID *
            </label>
            <input
              required
              type="text"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="e.g. 92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4"
              className="w-full rounded border border-border bg-background px-3 py-1.5"
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] font-medium">
              Requirement ID *
            </label>
            <input
              required
              type="text"
              value={requirementId}
              onChange={(e) => setRequirementId(e.target.value)}
              placeholder="e.g. REQ-0001"
              className="w-full rounded border border-border bg-background px-3 py-1.5"
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] font-medium">
              Department
            </label>
            <input
              disabled
              readOnly
              value={
                departmentName
                  ? `${departmentName} (${departmentId})`
                  : departmentId
              }
              className="w-full rounded border border-border bg-surface-sunken px-3 py-1.5 text-muted-foreground"
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] font-medium">
              Title (optional)
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. MPCB Consent to Establish — Water Act"
              className="w-full rounded border border-border bg-background px-3 py-1.5"
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] font-medium">
              Applicant Name (optional)
            </label>
            <input
              type="text"
              value={applicantName}
              onChange={(e) => setApplicantName(e.target.value)}
              placeholder="Applicant / company name"
              className="w-full rounded border border-border bg-background px-3 py-1.5"
            />
          </div>
          {mutation.error && (
            <p className="text-[12px] text-destructive">
              {mutation.error instanceof Error
                ? mutation.error.message
                : "Application creation failed."}
            </p>
          )}
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-border px-3 py-1.5 text-[12.5px] hover:bg-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={
                !projectId.trim() || !requirementId.trim() || mutation.isPending
              }
              className="rounded bg-primary px-3.5 py-1.5 text-[12.5px] font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {mutation.isPending ? "Creating…" : "Create Application"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ApplicationsPage() {
  const { irisUser, isDemoMode } = useAuth();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ApplicationStage | "">("");
  const [slaFilter, setSlaFilter] = useState<SlaState | "">("");
  const [reqFilter, setReqFilter] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  // The signed-in officer's own department — used to lock the create form.
  // Demo mode has no irisUser.department_id from a real profile, so it falls
  // back to the department the demo dashboard already operates on.
  const departmentId = irisUser?.department_id ?? (isDemoMode ? "dept-mpcb" : null);
  const departmentName = irisUser?.department_name ?? null;

  const { data, isLoading, error } = useQuery({
    queryKey: [
      "department",
      "applications",
      search,
      statusFilter,
      slaFilter,
      reqFilter,
    ],
    queryFn: () =>
      departmentApi.listApplications({
        ...(search ? { search } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(slaFilter ? { sla_state: slaFilter } : {}),
        ...(reqFilter ? { requirement_id: reqFilter } : {}),
        limit: 100,
      }),
  });

  return (
    <PageShell wide>
      <PageHeader
        trail={[
          { label: "Department", to: "/department" },
          { label: "Applications" },
        ]}
        title="Applications"
        description="All applications submitted to the department for processing."
        actions={
          <button
            type="button"
            disabled={!departmentId}
            title={
              departmentId
                ? undefined
                : "Your account has no department assigned yet."
            }
            onClick={() => setShowCreateModal(true)}
            className="focus-ring inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            New Application
          </button>
        }
      />

      {/* Filter bar */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            id="applications-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search applications…"
            className="h-8 w-[220px] rounded-md border border-border bg-surface pl-8 pr-3 text-[12.5px] placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <select
          id="applications-status-filter"
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(e.target.value as ApplicationStage | "")
          }
          className="h-8 rounded-md border border-border bg-surface px-2.5 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All Stages</option>
          {ALL_STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABELS[s]}
            </option>
          ))}
        </select>

        <select
          id="applications-sla-filter"
          value={slaFilter}
          onChange={(e) => setSlaFilter(e.target.value as SlaState | "")}
          className="h-8 rounded-md border border-border bg-surface px-2.5 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All SLA States</option>
          {SLA_STATES.map((s) => (
            <option key={s} value={s}>
              {SLA_LABEL[s]}
            </option>
          ))}
        </select>

        <input
          id="applications-req-filter"
          value={reqFilter}
          onChange={(e) => setReqFilter(e.target.value)}
          placeholder="Requirement (REQ-####)"
          className="h-8 w-[180px] rounded-md border border-border bg-surface px-2.5 text-[12.5px] placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />

        {(search || statusFilter || slaFilter || reqFilter) && (
          <button
            type="button"
            onClick={() => {
              setSearch("");
              setStatusFilter("");
              setSlaFilter("");
              setReqFilter("");
            }}
            className="h-8 rounded-md border border-border px-2.5 text-[12px] text-muted-foreground transition-colors hover:border-border-strong hover:bg-secondary"
          >
            Clear filters
          </button>
        )}

        {data && (
          <span className="ml-auto text-[12px] text-muted-foreground tabular">
            {data.total} result{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Table */}
      <div className="mt-4 border border-border bg-surface">
        {isLoading && (
          <div className="space-y-px">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="h-12 animate-pulse border-b border-border bg-surface-sunken"
              />
            ))}
          </div>
        )}

        {error && (
          <p className="px-5 py-6 text-[12.5px] text-destructive">
            {error instanceof BackendUnavailableError
              ? "Backend unavailable — start the IRIS backend to load applications."
              : `Error loading applications: ${error instanceof Error ? error.message : String(error)}`}
          </p>
        )}

        {data && data.items.length === 0 && (
          <p className="px-5 py-10 text-center text-[12.5px] text-muted-foreground">
            No applications match the current filters.
          </p>
        )}

        {data && data.items.length > 0 && (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border bg-surface-sunken">
                {[
                  "Applicant / Project",
                  "Requirement",
                  "Stage",
                  "Officer",
                  "Age",
                  "SLA",
                  "Status",
                ].map((h) => (
                  <th
                    key={h}
                    className="label-meta px-4 py-2.5 font-semibold whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.items.map((app) => (
                <tr key={app.id} className="row-hover hover:bg-surface-sunken">
                  <td className="max-w-[180px] px-4 py-3">
                    <Link
                      to="/department/application/$appId"
                      params={{ appId: app.id }}
                      className="block truncate text-[13px] font-medium text-foreground hover:text-info hover:underline"
                    >
                      {app.project_name ?? app.project_id}
                    </Link>
                    <div className="truncate text-[11px] text-muted-foreground">{app.title}</div>
                    <div className="font-mono text-[10.5px] text-muted-foreground">
                      {app.application_id}
                    </div>
                    {app.legacy_operational && (
                      <span className="mt-0.5 inline-flex items-center whitespace-nowrap rounded-sm border border-border px-1.5 py-[2px] text-[10px] font-medium text-muted-foreground">
                        {app.legacy_operational.label}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[12.5px] text-muted-foreground">
                    {app.requirement_id}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-[3px] text-[10.5px] font-medium",
                        STAGE_TONE_CLASSES[app.current_stage],
                      )}
                    >
                      {STAGE_LABELS[app.current_stage]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[12.5px]">
                    {app.assigned_officer_name ?? (
                      <span className="text-warning text-[11.5px]">
                        Unassigned
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 tabular text-[12px] text-muted-foreground">
                    {applicationAge(app.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          "inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-[3px] text-[10.5px] font-medium",
                          SLA_TONE_CLASSES[app.sla.state],
                        )}
                      >
                        {SLA_LABEL[app.sla.state]}
                      </span>
                      {app.sla.elapsed_pct > 0 && (
                        <div className="h-[3px] w-12 overflow-hidden rounded-full bg-border">
                          <div
                            className={cn(
                              "h-full",
                              app.sla.state === "BREACHED"
                                ? "bg-destructive"
                                : app.sla.state === "AT_RISK"
                                  ? "bg-warning"
                                  : "bg-success",
                            )}
                            style={{
                              width: `${Math.min(app.sla.elapsed_pct * 100, 100)}%`,
                            }}
                          />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to="/department/application/$appId"
                      params={{ appId: app.id }}
                      className="text-[12px] text-info hover:underline"
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreateModal && departmentId && (
        <NewApplicationModal
          departmentId={departmentId}
          departmentName={departmentName}
          onClose={() => setShowCreateModal(false)}
        />
      )}
    </PageShell>
  );
}

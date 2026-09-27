import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileText,
  User,
  Zap,
} from "lucide-react";
import {
  departmentApi,
  STAGE_LABELS,
  STAGE_TONE,
  SLA_LABEL,
  SLA_TONE,
  ALLOWED_TRANSITIONS,
  applicationAge,
} from "@/lib/iris/department-api";
import type { ApplicationStage, SlaState } from "@/lib/iris/department-api";
import {
  PageShell,
  PageHeader,
  SectionHeading,
  DataField,
  DrawerSection,
} from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import { cn } from "@/lib/utils";
import { BackendUnavailableError } from "@/lib/iris/api-client";

export const Route = createFileRoute("/department/application/$appId")({
  head: () => ({
    meta: [{ title: "Application Detail — IRIS Gov" }],
  }),
  component: ApplicationDetailPage,
});

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

function StageTransitionButton({
  appId,
  currentStage,
  onSuccess,
}: {
  appId: string;
  currentStage: ApplicationStage;
  onSuccess: () => void;
}) {
  const [reason, setReason] = useState("");
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: (stage: ApplicationStage) =>
      departmentApi.transitionStage(appId, {
        new_stage: stage,
        ...(reason ? { reason } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["department", "application", appId] });
      qc.invalidateQueries({ queryKey: ["department", "dashboard"] });
      setReason("");
      onSuccess();
    },
  });

  const allowed = ALLOWED_TRANSITIONS[currentStage];
  if (allowed.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground">
        This application has reached a terminal state (
        {STAGE_LABELS[currentStage]}).
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (optional)"
        className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <div className="flex flex-wrap gap-2">
        {allowed.map((stage) => (
          <button
            key={stage}
            type="button"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(stage)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md border px-3 py-[6px] text-[12px] font-medium transition-opacity hover:opacity-80 disabled:opacity-50",
              STAGE_TONE_CLASSES[stage],
            )}
          >
            <ChevronRight className="h-3.5 w-3.5" />
            {STAGE_LABELS[stage]}
          </button>
        ))}
      </div>
      {mutation.error && (
        <p className="text-[12px] text-destructive">
          {mutation.error instanceof Error
            ? mutation.error.message
            : "Transition failed"}
        </p>
      )}
    </div>
  );
}

function AssignOfficerPanel({
  appId,
  onSuccess,
}: {
  appId: string;
  onSuccess: () => void;
}) {
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [reason, setReason] = useState("");
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      departmentApi.assignOfficer(appId, {
        officer_id: id || `officer-${Date.now()}`,
        officer_name: name,
        ...(reason ? { reason } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["department", "application", appId] });
      setName("");
      setId("");
      setReason("");
      onSuccess();
    },
  });

  return (
    <div className="space-y-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Officer name *"
        className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <input
        value={id}
        onChange={(e) => setId(e.target.value)}
        placeholder="Officer ID (optional)"
        className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (optional)"
        className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <button
        type="button"
        disabled={!name || mutation.isPending}
        onClick={() => mutation.mutate()}
        className="w-full rounded-md bg-primary px-3 py-2 text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {mutation.isPending ? "Assigning…" : "Assign Officer"}
      </button>
      {mutation.error && (
        <p className="text-[12px] text-destructive">
          {mutation.error instanceof Error
            ? mutation.error.message
            : "Assignment failed"}
        </p>
      )}
    </div>
  );
}

function ApplicationDetailPage() {
  const { appId } = Route.useParams();
  const [actionsOpen, setActionsOpen] = useState(false);

  const {
    data: app,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["department", "application", appId],
    queryFn: () => departmentApi.getApplication(appId),
  });

  if (isLoading) {
    return (
      <PageShell>
        <div className="mt-8 space-y-4 animate-pulse">
          <div className="h-8 w-64 rounded bg-surface" />
          <div className="h-40 rounded bg-surface" />
        </div>
      </PageShell>
    );
  }

  if (error || !app) {
    return (
      <PageShell>
        <PageHeader
          title="Application not found"
          trail={[{ label: "Applications", to: "/department/applications" }]}
        />
        <div className="mt-6 border border-destructive/25 bg-danger-surface p-5">
          <p className="text-[13px] text-destructive">
            {error instanceof BackendUnavailableError
              ? "Backend unavailable."
              : `Application ${appId} not found.`}
          </p>
        </div>
      </PageShell>
    );
  }

  const canAct = !["APPROVED", "REJECTED"].includes(app.current_stage);

  return (
    <PageShell wide>
      <div className="mb-4">
        <Link
          to="/department/applications"
          className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Applications
        </Link>
      </div>

      <PageHeader
        title={app.project_name ?? app.project_id}
        description={`${app.title ?? app.requirement_id} · ${app.application_id} · Submitted ${applicationAge(app.created_at)} ago`}
        trail={[
          { label: "Department", to: "/department" },
          { label: "Applications", to: "/department/applications" },
          { label: app.application_id },
        ]}
        meta={
          <dl className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div className="flex items-baseline gap-2">
              <dt className="label-meta">Stage</dt>
              <dd>
                <span
                  className={cn(
                    "inline-flex items-center rounded-sm border px-2 py-[3px] text-[11px] font-medium",
                    STAGE_TONE_CLASSES[app.current_stage],
                  )}
                >
                  {STAGE_LABELS[app.current_stage]}
                </span>
              </dd>
            </div>
            <div className="flex items-baseline gap-2">
              <dt className="label-meta">Officer</dt>
              <dd className="text-[13px] font-medium">
                {app.assigned_officer_name ?? <span className="text-warning">Unassigned</span>}
              </dd>
            </div>
            <div className="flex items-baseline gap-2">
              <dt className="label-meta">SLA</dt>
              <dd>
                <span
                  className={cn(
                    "inline-flex items-center rounded-sm border px-2 py-[3px] text-[11px] font-medium",
                    SLA_TONE_CLASSES[app.sla.state],
                  )}
                >
                  {SLA_LABEL[app.sla.state]}
                </span>
              </dd>
            </div>
          </dl>
        }
        actions={
          canAct ? (
            <button
              type="button"
              onClick={() => setActionsOpen(!actionsOpen)}
              className={cn(
                "focus-ring rounded-md px-3 py-[7px] text-[12.5px] font-medium transition-colors",
                actionsOpen
                  ? "bg-secondary border border-border-strong"
                  : "bg-primary text-primary-foreground",
              )}
            >
              {actionsOpen ? "Close Actions" : "Workflow Actions"}
            </button>
          ) : null
        }
      />

      {/* Workflow Actions Panel */}
      {actionsOpen && canAct && (
        <div className="mt-5 grid gap-6 border border-border bg-surface p-5 md:grid-cols-2">
          <div>
            <div className="label-meta mb-3">Stage Transition</div>
            <StageTransitionButton
              appId={app.id}
              currentStage={app.current_stage}
              onSuccess={() => setActionsOpen(false)}
            />
          </div>
          <div>
            <div className="label-meta mb-3">
              {app.assigned_officer_name
                ? "Reassign Officer"
                : "Assign Officer"}
            </div>
            <AssignOfficerPanel
              appId={app.id}
              onSuccess={() => setActionsOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          {/* Application Info */}
          <section className="panel border border-border bg-surface">
            <div className="border-b border-border px-5 py-3.5">
              <div className="label-meta">Application</div>
            </div>
            <div className="grid gap-x-8 gap-y-4 px-5 py-4 sm:grid-cols-2 lg:grid-cols-3">
              <DataField label="Application ID" value={app.application_id} />
              <DataField label="Requirement" value={app.requirement_id} />
              <DataField label="Department" value={app.department_id} />
              {app.legacy_operational && (
                <DataField
                  label="Record status"
                  value={app.legacy_operational.label}
                />
              )}
              <DataField label="Applicant" value={app.applicant_name ?? "—"} />
              <DataField
                label="Project"
                value={
                  <Link to="/projects" className="text-info hover:underline">
                    {app.project_name ?? app.project_id}
                  </Link>
                }
              />
              {app.project && (
                <DataField
                  label="Industry"
                  value={
                    <span className="capitalize">
                      {(app.project as Record<string, string>)["industry"] ?? "—"}
                    </span>
                  }
                />
              )}
            </div>
          </section>

          {/* Current Stage & SLA */}
          <section className="panel border border-border bg-surface">
            <div className="border-b border-border px-5 py-3.5">
              <div className="label-meta">Status & SLA</div>
            </div>
            <div className="grid gap-x-8 gap-y-4 px-5 py-4 sm:grid-cols-2 lg:grid-cols-4">
              <DataField
                label="Current Stage"
                value={
                  <span
                    className={cn(
                      "inline-flex items-center rounded-sm border px-2 py-[3px] text-[11px] font-medium",
                      STAGE_TONE_CLASSES[app.current_stage],
                    )}
                  >
                    {STAGE_LABELS[app.current_stage]}
                  </span>
                }
              />
              <DataField
                label="SLA State"
                value={
                  <span
                    className={cn(
                      "inline-flex items-center rounded-sm border px-2 py-[3px] text-[11px] font-medium",
                      SLA_TONE_CLASSES[app.sla.state],
                    )}
                  >
                    {SLA_LABEL[app.sla.state]}
                  </span>
                }
              />
              <DataField
                label="Elapsed"
                value={
                  app.sla.elapsed_pct > 0 ? (
                    <span className="tabular">
                      {(app.sla.elapsed_pct * 100).toFixed(0)}%
                    </span>
                  ) : (
                    "—"
                  )
                }
              />
              <DataField
                label="Due"
                value={
                  app.sla.due_at
                    ? new Date(app.sla.due_at).toLocaleDateString()
                    : "—"
                }
              />
            </div>
            {app.sla.elapsed_pct > 0 && (
              <div className="px-5 pb-4">
                <div className="h-2 w-full overflow-hidden rounded-full bg-border">
                  <div
                    className={cn(
                      "h-full rounded-full transition-[width] duration-500",
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
              </div>
            )}
          </section>

          {/* Engine Decision */}
          {app.engine_decision && (
            <section className="panel border border-border bg-surface">
              <div className="border-b border-border px-5 py-3.5 flex items-center gap-2">
                <Zap className="h-3.5 w-3.5 text-info" />
                <div className="label-meta">Phase 9 Engine Decision</div>
                <span className="ml-auto rounded-sm border border-info/25 bg-info-surface px-1.5 py-[2px] text-[10px] font-medium text-info">
                  {(app.engine_decision as Record<string, string>)[
                    "evaluation_mode"
                  ] ?? "—"}
                </span>
              </div>
              <div className="grid gap-x-8 gap-y-4 px-5 py-4 sm:grid-cols-2 lg:grid-cols-3">
                <DataField
                  label="Final State"
                  value={
                    <span className="font-mono text-[12px]">
                      {(app.engine_decision as Record<string, string>)[
                        "final_state"
                      ] ?? "—"}
                    </span>
                  }
                />
                <DataField
                  label="Rule"
                  value={
                    (app.engine_decision as Record<string, string>)[
                      "rule_id"
                    ] ?? "—"
                  }
                />
                <DataField
                  label="Rule Version Status"
                  value={
                    (app.engine_decision as Record<string, string>)[
                      "rule_version_status"
                    ] ?? "—"
                  }
                />
              </div>
              <div className="border-t border-border bg-surface-sunken px-5 py-3">
                <p className="text-[11px] text-muted-foreground">
                  ⚠ This is a deterministic engine output — separate from the
                  operational workflow stage above. Engine decisions are
                  immutable and append-only.
                </p>
              </div>
            </section>
          )}

          {/* Operational Timeline */}
          <section>
            <SectionHeading title="Operational Timeline" />
            <ol className="mt-3 border-l border-border pl-4">
              {[...app.operational_events].reverse().map((ev) => (
                <li key={ev.id} className="relative pb-4 last:pb-0">
                  <span
                    className="absolute -left-[21px] top-[6px] h-[7px] w-[7px] rounded-full border border-border bg-surface"
                    aria-hidden
                  />
                  <p className="text-[12.5px] leading-relaxed font-medium">
                    {ev.message}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    <span className="tabular">
                      {new Date(ev.created_at).toLocaleString()}
                    </span>
                    {ev.actor && ` · ${ev.actor}`}
                    <span className="ml-2 rounded border border-border bg-neutral-surface px-1 py-[1px] text-[10px]">
                      {ev.event_type}
                    </span>
                  </p>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <div className="space-y-6">
          {/* Officer */}
          <section className="panel border border-border bg-surface">
            <div className="border-b border-border px-5 py-3.5 flex items-center gap-2">
              <User className="h-3.5 w-3.5 text-muted-foreground" />
              <div className="label-meta">Assigned Officer</div>
            </div>
            <div className="px-5 py-4">
              {app.assigned_officer_name ? (
                <>
                  <p className="text-[14px] font-medium">
                    {app.assigned_officer_name}
                  </p>
                  <p className="mt-1 text-[11.5px] text-muted-foreground">
                    ID: {app.assigned_officer_id ?? "—"}
                  </p>
                </>
              ) : (
                <div className="flex items-center gap-2 text-warning">
                  <AlertTriangle className="h-4 w-4" />
                  <span className="text-[12.5px] font-medium">Unassigned</span>
                </div>
              )}
            </div>
          </section>

          {/* Assignment History */}
          <section>
            <SectionHeading title="Assignment History" />
            {app.assignment_history.length === 0 ? (
              <p className="mt-2 text-[12px] text-muted-foreground">
                No assignments yet.
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-border border border-border bg-surface">
                {[...app.assignment_history].reverse().map((a) => (
                  <li key={a.id} className="px-4 py-3">
                    <p className="text-[13px] font-medium">{a.officer_name}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      By {a.assigned_by} ·{" "}
                      {new Date(a.created_at).toLocaleDateString()}
                    </p>
                    {a.reason && (
                      <p className="mt-1 text-[11.5px] text-muted-foreground italic">
                        {a.reason}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Stage History */}
          <section>
            <SectionHeading title="Stage History" />
            <ul className="mt-3 divide-y divide-border border border-border bg-surface">
              {[...app.stage_history].reverse().map((s) => (
                <li key={s.id} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {s.previous_stage && (
                      <>
                        <span
                          className={cn(
                            "rounded-sm border px-1.5 py-[2px] text-[10px] font-medium",
                            STAGE_TONE_CLASSES[s.previous_stage as ApplicationStage],
                          )}
                        >
                          {STAGE_LABELS[s.previous_stage as ApplicationStage]}
                        </span>
                        <ChevronRight className="h-3 w-3 text-muted-foreground" />
                      </>
                    )}
                    <span
                      className={cn(
                        "rounded-sm border px-1.5 py-[2px] text-[10px] font-medium",
                        STAGE_TONE_CLASSES[s.new_stage as ApplicationStage],
                      )}
                    >
                      {STAGE_LABELS[s.new_stage as ApplicationStage]}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {s.actor} · {new Date(s.created_at).toLocaleDateString()}
                    {s.reason && ` · "${s.reason}"`}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </PageShell>
  );
}

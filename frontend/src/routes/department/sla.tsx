import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  ExternalLink,
  Filter,
  Flame,
  Hourglass,
  Layers,
  ShieldAlert,
} from "lucide-react";
import {
  departmentApi,
  SLA_LABEL,
  STAGE_LABELS,
  formatHours,
  type SlaState,
  type ApplicationStage,
} from "@/lib/iris/department-api";
import { PageShell, PageHeader } from "@/components/iris/page";
import { cn } from "@/lib/utils";
import { BackendUnavailableError } from "@/lib/iris/api-client";

export const Route = createFileRoute("/department/sla")({
  head: () => ({
    meta: [
      { title: "SLA Intelligence — IRIS Gov" },
      {
        name: "description",
        content:
          "Department-wide SLA monitoring, at-risk detection, and stage-wise performance.",
      },
    ],
  }),
  component: SlaDashboardPage,
});

const SLA_BADGE_CLASSES: Record<SlaState, string> = {
  WITHIN_SLA: "border-success/30 bg-success-surface text-success",
  AT_RISK: "border-warning/30 bg-warning-surface text-warning font-medium",
  BREACHED:
    "border-destructive/30 bg-danger-surface text-destructive font-medium",
  COMPLETED: "border-border bg-neutral-surface text-muted-foreground",
};

const VS_TARGET_CLASSES = {
  WITHIN: "text-success bg-success-surface border-success/25",
  AT_RISK: "text-warning bg-warning-surface border-warning/25",
  EXCEEDED: "text-destructive bg-danger-surface border-destructive/25",
};

function SlaDashboardPage() {
  const [selectedState, setSelectedState] = useState<SlaState | "ALL">("ALL");
  const [activeTab, setActiveTab] = useState<
    "applications" | "stages" | "policies"
  >("applications");

  // Fetch full SLA dashboard from backend
  const {
    data: dashboard,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["department", "sla-dashboard"],
    queryFn: departmentApi.getSlaDashboard,
  });

  // Fetch policies
  const { data: policies } = useQuery({
    queryKey: ["department", "sla-policies"],
    queryFn: departmentApi.listSLAPolicies,
  });

  const kpis = dashboard?.kpis;
  const applications = dashboard?.applications ?? [];
  const stagePerf = dashboard?.stage_performance ?? [];

  const filteredApps = applications.filter((app) => {
    if (selectedState === "ALL") return true;
    return app.sla_state === selectedState;
  });

  if (isLoading) {
    return (
      <PageShell wide>
        <PageHeader
          trail={[
            { label: "Department", to: "/department" },
            { label: "SLA Intelligence" },
          ]}
          title="SLA Intelligence"
        />
        <div className="mt-6 grid animate-pulse grid-cols-2 gap-3 sm:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 rounded-lg border border-border bg-card" />
          ))}
        </div>
      </PageShell>
    );
  }

  if (error) {
    const isOffline = error instanceof BackendUnavailableError;
    return (
      <PageShell wide>
        <PageHeader
          trail={[
            { label: "Department", to: "/department" },
            { label: "SLA Intelligence" },
          ]}
          title="SLA Intelligence"
        />
        <div className="mt-6 border border-destructive/25 bg-danger-surface p-6">
          <p className="text-[13px] font-medium text-destructive">
            {isOffline
              ? "IRIS backend is not reachable"
              : "Failed to load SLA data"}
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {isOffline
              ? "Start the backend with: cd backend && uvicorn app.main:app"
              : String(error)}
          </p>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell wide>
      <PageHeader
        trail={[
          { label: "Department", to: "/department" },
          { label: "SLA Intelligence" },
        ]}
        title="SLA Intelligence"
        description="Authoritative operational tracking of application timelines, breach risk detection, and stage duration compliance."
      />

      {/* KPI Cards */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Total Monitored
            </span>
            <Layers className="h-4 w-4 text-muted-foreground/60" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight">
            {kpis?.total ?? "—"}
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            {kpis?.active ?? 0} currently active
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-success">
              Within SLA
            </span>
            <CheckCircle2 className="h-4 w-4 text-success" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight text-success">
            {kpis?.within_sla ?? "—"}
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            Healthy trajectory
          </div>
        </div>

        <div className="rounded-lg border border-warning/30 bg-warning-surface/30 p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-warning">
              At Risk
            </span>
            <AlertTriangle className="h-4 w-4 text-warning" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight text-warning">
            {kpis?.at_risk ?? "—"}
          </div>
          <div className="mt-1 text-[11.5px] text-warning/80">
            Crossed warning threshold
          </div>
        </div>

        <div className="rounded-lg border border-destructive/30 bg-danger-surface/30 p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-destructive">
              Breached
            </span>
            <Flame className="h-4 w-4 text-destructive" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight text-destructive">
            {kpis?.breached ?? "—"}
          </div>
          <div className="mt-1 text-[11.5px] text-destructive/80">
            Exceeded SLA window
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Completed
            </span>
            <Hourglass className="h-4 w-4 text-muted-foreground/60" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight">
            {kpis?.completed ?? "—"}
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            Decided & archived
          </div>
        </div>
      </div>

      {/* Aging Analysis Bar */}
      {kpis && (
        <div className="mt-4 rounded-lg border border-border bg-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-[13px] font-medium">
                Application Aging Distribution
              </span>
              <p className="text-[11.5px] text-muted-foreground">
                Calendar age of active applications since initial submission
              </p>
            </div>
            <div className="flex gap-4 text-[12px]">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                <span>
                  0–7 days: <strong>{kpis.aging_0_7d}</strong>
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-blue-500" />
                <span>
                  7–30 days: <strong>{kpis.aging_7_30d}</strong>
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-amber-500" />
                <span>
                  30–60 days: <strong>{kpis.aging_30_60d}</strong>
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-red-500" />
                <span>
                  &gt;60 days: <strong>{kpis.aging_over_60d}</strong>
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Tabs Navigation */}
      <div className="mt-6 flex border-b border-border">
        <button
          onClick={() => setActiveTab("applications")}
          className={cn(
            "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors",
            activeTab === "applications"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Application SLA Status ({applications.length})
        </button>
        <button
          onClick={() => setActiveTab("stages")}
          className={cn(
            "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors",
            activeTab === "stages"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Stage Performance vs Targets
        </button>
        <button
          onClick={() => setActiveTab("policies")}
          className={cn(
            "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors",
            activeTab === "policies"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Configurable Policies ({policies?.length ?? 0})
        </button>
      </div>

      {/* Tab 1: Application SLA Status Table */}
      {activeTab === "applications" && (
        <div className="mt-4">
          <div className="flex items-center justify-between pb-3">
            <div className="flex items-center gap-2">
              <Filter className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[12.5px] text-muted-foreground">
                Filter State:
              </span>
              <div className="flex gap-1">
                {(
                  [
                    "ALL",
                    "AT_RISK",
                    "BREACHED",
                    "WITHIN_SLA",
                    "COMPLETED",
                  ] as const
                ).map((st) => (
                  <button
                    key={st}
                    onClick={() => setSelectedState(st)}
                    className={cn(
                      "rounded px-2.5 py-1 text-[11.5px] font-medium transition-colors",
                      selectedState === st
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    {st === "ALL" ? "All" : SLA_LABEL[st]}
                  </button>
                ))}
              </div>
            </div>
            <span className="text-[12px] text-muted-foreground">
              Showing {filteredApps.length} applications
            </span>
          </div>

          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <thead className="border-b border-border bg-muted/40 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">Application</th>
                    <th className="px-4 py-3">Stage</th>
                    <th className="px-4 py-3">Assigned Officer</th>
                    <th className="px-4 py-3">SLA Status</th>
                    <th className="px-4 py-3">Timeline Progress</th>
                    <th className="px-4 py-3">Due Date</th>
                    <th className="px-4 py-3">Age</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border font-normal">
                  {filteredApps.map((app) => (
                    <tr
                      key={app.id}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <Link
                          to="/department/application/$appId"
                          params={{ appId: app.id }}
                          className="font-medium text-foreground hover:underline"
                        >
                          {app.application_id}
                        </Link>
                        <div className="text-[11.5px] text-muted-foreground truncate max-w-[200px]">
                          {app.title || app.requirement_id}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {STAGE_LABELS[app.current_stage as ApplicationStage] ??
                          app.current_stage}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {app.assigned_officer_name || (
                          <span className="italic text-muted-foreground/60">
                            Unassigned
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "inline-flex items-center rounded border px-2 py-0.5 text-[11px]",
                            SLA_BADGE_CLASSES[app.sla_state],
                          )}
                        >
                          {SLA_LABEL[app.sla_state]}
                        </span>
                      </td>
                      <td className="px-4 py-3 min-w-[140px]">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 rounded-full bg-secondary overflow-hidden">
                            <div
                              className={cn(
                                "h-full rounded-full transition-all",
                                app.sla_state === "BREACHED"
                                  ? "bg-destructive"
                                  : app.sla_state === "AT_RISK"
                                    ? "bg-warning"
                                    : "bg-primary",
                              )}
                              style={{
                                width: `${Math.min(app.elapsed_pct * 100, 100)}%`,
                              }}
                            />
                          </div>
                          <span className="text-[11px] tabular-nums text-muted-foreground">
                            {Math.round(app.elapsed_pct * 100)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-[12px]">
                        {app.due_at
                          ? new Date(app.due_at).toLocaleDateString()
                          : "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-[12px]">
                        {formatHours(app.age_hours)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          to="/department/application/$appId"
                          params={{ appId: app.id }}
                          className="inline-flex items-center gap-1 text-[12px] text-primary hover:underline"
                        >
                          View <ExternalLink className="h-3 w-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {filteredApps.length === 0 && (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-4 py-8 text-center text-[13px] text-muted-foreground"
                      >
                        No applications matching SLA filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Stage Performance vs Targets */}
      {activeTab === "stages" && (
        <div className="mt-4 space-y-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="text-[14px] font-semibold">
              Stage-Wise Processing Time vs Targets
            </h3>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">
              Evaluates actual average and median durations recorded in
              historical workflow transitions against configured stage targets.
            </p>
          </div>

          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-border bg-muted/40 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Workflow Stage</th>
                  <th className="px-4 py-3">Entered / Completed</th>
                  <th className="px-4 py-3">Avg Duration</th>
                  <th className="px-4 py-3">Median Duration</th>
                  <th className="px-4 py-3">Stage Target</th>
                  <th className="px-4 py-3">Target Compliance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {stagePerf.map((st) => (
                  <tr key={st.stage} className="hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">
                      {STAGE_LABELS[st.stage as ApplicationStage] ?? st.stage}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {st.entry_count} entries · {st.completed_count} completed
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">
                      {formatHours(st.avg_duration_hours)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatHours(st.median_duration_hours)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {st.target_hours
                        ? `${st.target_hours}h (${(st.target_hours / 24).toFixed(0)}d)`
                        : "Not configured"}
                    </td>
                    <td className="px-4 py-3">
                      {st.vs_target ? (
                        <span
                          className={cn(
                            "inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-medium",
                            VS_TARGET_CLASSES[st.vs_target],
                          )}
                        >
                          {st.vs_target}
                        </span>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">
                          —
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Configurable Policies */}
      {activeTab === "policies" && (
        <div className="mt-4 space-y-3">
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="text-[14px] font-semibold">
              Configurable Department SLA Policies
            </h3>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">
              These policies set overall application review windows. They are
              operational configurations, not legally mandated statutory terms.
            </p>
          </div>

          {policies?.map((p) => (
            <div
              key={p.id}
              className="rounded-lg border border-border bg-card p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h4 className="text-[14.5px] font-semibold text-foreground">
                    {p.name}
                  </h4>
                  {p.description && (
                    <p className="mt-1 text-[12.5px] text-muted-foreground max-w-[65ch] leading-relaxed">
                      {p.description}
                    </p>
                  )}
                </div>
                <div className="flex gap-6 text-[12.5px]">
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      Duration
                    </div>
                    <p className="mt-0.5 font-semibold text-[15px]">
                      {p.duration_hours}h{" "}
                      <span className="text-[12px] font-normal text-muted-foreground">
                        ({(p.duration_hours / 24).toFixed(0)} days)
                      </span>
                    </p>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      Warning Threshold
                    </div>
                    <p className="mt-0.5 font-semibold text-[15px]">
                      {(p.warning_pct * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      Category
                    </div>
                    <p className="mt-0.5 font-medium">
                      {p.requirement_type ?? "General Standard"}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </PageShell>
  );
}

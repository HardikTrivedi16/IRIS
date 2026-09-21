import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownUp,
  Clock,
  Flame,
  Info,
  Layers,
  TrendingDown,
  UserCheck,
  Users,
} from "lucide-react";
import {
  departmentApi,
  STAGE_LABELS,
  formatHours,
  type ApplicationStage,
} from "@/lib/iris/department-api";
import { PageShell, PageHeader } from "@/components/iris/page";
import { cn } from "@/lib/utils";
import { BackendUnavailableError } from "@/lib/iris/api-client";

export const Route = createFileRoute("/department/bottlenecks")({
  head: () => ({
    meta: [
      { title: "Bottleneck Analytics — IRIS Gov" },
      {
        name: "description",
        content:
          "Deterministic analysis of workflow backlogs, dwell time, and throughput.",
      },
    ],
  }),
  component: BottlenecksPage,
});

function BottlenecksPage() {
  const [activeTab, setActiveTab] = useState<"ranking" | "officers" | "trends">(
    "ranking",
  );

  const {
    data: report,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["department", "bottlenecks-report"],
    queryFn: departmentApi.getBottleneckReport,
  });

  const { data: trends } = useQuery({
    queryKey: ["department", "bottlenecks-trends"],
    queryFn: () => departmentApi.getBottleneckTrends(14),
  });

  const explanation = useQuery({
    queryKey: ["department", "bottlenecks-explanation"],
    queryFn: departmentApi.getBottleneckExplanation,
  });

  const stages = report?.stages ?? [];
  const officers = report?.officers ?? [];

  if (isLoading) {
    return (
      <PageShell wide>
        <PageHeader
          trail={[
            { label: "Department", to: "/department" },
            { label: "Bottleneck Analytics" },
          ]}
          title="Bottleneck Analytics"
        />
        <div className="mt-8 animate-pulse space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="panel h-16 bg-surface" />
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
            { label: "Bottleneck Analytics" },
          ]}
          title="Bottleneck Analytics"
        />
        <div className="mt-8 border border-destructive/25 bg-danger-surface p-6">
          <p className="text-[13px] font-medium text-destructive">
            {isOffline
              ? "IRIS backend is not reachable"
              : "Failed to load bottleneck analytics"}
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
          { label: "Bottleneck Analytics" },
        ]}
        title="Bottleneck Analytics"
        description="Deterministic workflow bottleneck diagnostics derived directly from operational timestamps and SLA instances."
      />

      {/* Methodology — what these figures are, and are not */}
      <div className="mt-6 rounded-lg border border-border bg-card p-4">
        <div className="flex items-start gap-3">
          <Info className="h-4 w-4 shrink-0 text-muted-foreground mt-0.5" />
          <div className="text-[12.5px] leading-relaxed text-muted-foreground">
            Stage figures come from recorded stage transitions and SLA
            instances. Stages are ordered by a{" "}
            <span className="font-medium text-foreground">
              prototype operational heuristic
            </span>{" "}
            (avg hours × 0.40 + backlog × 0.35 + breach % × 0.25). Its weights
            are prototype choices, not calibrated, and it adds hours, counts
            and percentages — read the components, not the score. These show
            where time and backlog currently sit, not why; no prediction or
            process mining is used.
            {explanation.data && explanation.data.data.synthetic_demo > 0 && (
              <span className="ml-1 font-medium text-warning">
                {explanation.data.data.synthetic_demo} of{" "}
                {explanation.data.data.applications_in_scope} applications are
                synthetic demo data.
              </span>
            )}
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Active Backlog
            </span>
            <Layers className="h-4 w-4 text-muted-foreground/60" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight">
            {report?.total_active ?? "—"}
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            In active pipeline
          </div>
        </div>

        <div className="rounded-lg border border-warning/30 bg-warning-surface/30 p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-warning">
              Highest heuristic rank
            </span>
            <AlertTriangle className="h-4 w-4 text-warning" />
          </div>
          <div className="mt-2 text-[18px] font-semibold tracking-tight text-warning truncate">
            {report?.top_bottleneck_stage
              ? (STAGE_LABELS[
                  report.top_bottleneck_stage as ApplicationStage
                ] ?? report.top_bottleneck_stage)
              : "None detected"}
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            Heuristic score {report?.top_bottleneck_score?.toFixed(1) ?? "0.0"} — see components below
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Monitored Stages
            </span>
            <TrendingDown className="h-4 w-4 text-muted-foreground/60" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight">
            {stages.length}
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            Non-terminal workflow states
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Active Officers
            </span>
            <Users className="h-4 w-4 text-muted-foreground/60" />
          </div>
          <div className="mt-2 text-[24px] font-semibold tracking-tight">
            {officers.length}
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            With assigned workload
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-6 flex border-b border-border">
        <button
          onClick={() => setActiveTab("ranking")}
          className={cn(
            "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors",
            activeTab === "ranking"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Workflow Stage Rankings
        </button>
        <button
          onClick={() => setActiveTab("officers")}
          className={cn(
            "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors",
            activeTab === "officers"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Officer Workload Allocation ({officers.length})
        </button>
        <button
          onClick={() => setActiveTab("trends")}
          className={cn(
            "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors",
            activeTab === "trends"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          14-Day Throughput Flow
        </button>
      </div>

      {/* Tab 1: Stage Rankings */}
      {activeTab === "ranking" && (
        <div className="mt-4">
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <thead className="border-b border-border bg-muted/40 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">Heuristic rank</th>
                    <th className="px-4 py-3">Workflow Stage</th>
                    <th className="px-4 py-3">Current Backlog</th>
                    <th className="px-4 py-3">Avg Duration</th>
                    <th className="px-4 py-3">Median Duration</th>
                    <th className="px-4 py-3">SLA Breach Rate</th>
                    <th className="px-4 py-3">Stuck &gt; 14d</th>
                    <th className="px-4 py-3">7d Throughput</th>
                    <th className="px-4 py-3 text-right font-normal normal-case tracking-normal">Heuristic score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {stages.map((st) => (
                    <tr
                      key={st.stage}
                      className={cn(
                        "hover:bg-muted/30 transition-colors",
                        st.rank === 1 && "bg-warning-surface/15",
                      )}
                    >
                      <td className="px-4 py-3 font-semibold">
                        <span
                          className={cn(
                            "inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px]",
                            st.rank === 1
                              ? "bg-destructive text-destructive-foreground font-bold"
                              : st.rank === 2
                                ? "bg-warning text-warning-foreground font-medium"
                                : "bg-muted text-muted-foreground",
                          )}
                        >
                          {st.rank}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-foreground">
                        {STAGE_LABELS[st.stage as ApplicationStage] ?? st.stage}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-semibold text-foreground">
                          {st.backlog}
                        </span>
                        <span className="ml-1 text-[11px] text-muted-foreground">
                          applications
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatHours(st.avg_duration_hours)}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatHours(st.median_duration_hours)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              "font-medium",
                              st.sla_breach_pct > 0.2
                                ? "text-destructive"
                                : st.sla_breach_pct > 0
                                  ? "text-warning"
                                  : "text-muted-foreground",
                            )}
                          >
                            {(st.sla_breach_pct * 100).toFixed(0)}%
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            ({st.breached_count} breached)
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {st.aging_14d > 0 ? (
                          <span className="font-medium text-warning">
                            {st.aging_14d}
                          </span>
                        ) : (
                          "0"
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {st.throughput_7d} completed
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-[12px] text-muted-foreground">
                        {st.bottleneck_score.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                  {stages.length === 0 && (
                    <tr>
                      <td
                        colSpan={9}
                        className="px-4 py-8 text-center text-muted-foreground"
                      >
                        No workflow data collected yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Applications currently in each stage */}
          {explanation.data && (
            <section className="mt-6">
              <h3 className="text-[13.5px] font-semibold">Applications currently in each stage</h3>
              <p className="mt-0.5 text-[12px] text-muted-foreground">
                The applications behind each backlog figure, oldest first.
              </p>
              <div className="mt-3 divide-y divide-border rounded-lg border border-border bg-card">
                {explanation.data.stages
                  .filter((s) => s.affected_applications.length > 0)
                  .map((s) => (
                    <div key={s.stage} className="px-4 py-3">
                      <p className="text-[12.5px] font-medium">
                        {STAGE_LABELS[s.stage as ApplicationStage] ?? s.stage}
                        <span className="ml-2 text-[11.5px] font-normal text-muted-foreground">
                          {s.affected_applications.length} active
                        </span>
                      </p>
                      <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
                        {s.affected_applications.map((a) => (
                          <li key={a.id}>
                            <Link
                              to="/department/application/$appId"
                              params={{ appId: a.id }}
                              className="font-mono text-primary hover:underline"
                            >
                              {a.application_id ?? a.id.slice(0, 8)}
                            </Link>
                            <span className="ml-1 text-muted-foreground">
                              {a.age_hours !== null ? formatHours(a.age_hours) : "—"}
                              {a.sla_state ? ` · ${a.sla_state.replace(/_/g, " ").toLowerCase()}` : ""}
                              {a.data_classification === "SYNTHETIC_DEMO" ? " · synthetic" : ""}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                {explanation.data.stages.every((s) => s.affected_applications.length === 0) && (
                  <p className="px-4 py-3 text-[12.5px] text-muted-foreground">
                    No applications are currently active.
                  </p>
                )}
              </div>
              <ul className="mt-3 space-y-0.5 text-[11px] text-muted-foreground">
                {explanation.data.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </section>
          )}
        </div>
      )}

      {/* Tab 2: Officer Workload */}
      {activeTab === "officers" && (
        <div className="mt-4">
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-border bg-muted/40 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Officer Name</th>
                  <th className="px-4 py-3">Active Backlog</th>
                  <th className="px-4 py-3">SLA At Risk</th>
                  <th className="px-4 py-3">SLA Breached</th>
                  <th className="px-4 py-3">Historical Completed</th>
                  <th className="px-4 py-3">Total Assigned</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {officers.map((off) => (
                  <tr key={off.officer_id} className="hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium text-foreground">
                      {off.officer_name}
                    </td>
                    <td className="px-4 py-3 font-semibold text-foreground">
                      {off.active_applications}
                    </td>
                    <td className="px-4 py-3 text-warning font-medium">
                      {off.at_risk_count}
                    </td>
                    <td className="px-4 py-3 text-destructive font-medium">
                      {off.breached_count}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {off.completed_applications}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {off.total_applications}
                    </td>
                  </tr>
                ))}
                {officers.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      No officers currently assigned to active applications.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Processing Trends */}
      {activeTab === "trends" && (
        <div className="mt-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="text-[14px] font-semibold">
              14-Day Throughput Trend (Stage Inflow & Outflow)
            </h3>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">
              Daily transition volumes into and out of stages over the last 14
              days.
            </p>
          </div>

          <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-border bg-muted/40 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3">Entered (Inflow)</th>
                  <th className="px-4 py-3">Exited (Outflow)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {trends?.map((tr, idx) => (
                  <tr
                    key={`${tr.date}-${tr.stage}-${idx}`}
                    className="hover:bg-muted/30"
                  >
                    <td className="px-4 py-3 font-mono text-[12px]">
                      {tr.date}
                    </td>
                    <td className="px-4 py-3 font-medium">
                      {STAGE_LABELS[tr.stage as ApplicationStage] ?? tr.stage}
                    </td>
                    <td className="px-4 py-3 text-success font-medium">
                      +{tr.entered}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      -{tr.exited}
                    </td>
                  </tr>
                ))}
                {(!trends || trends.length === 0) && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      No transition movements recorded in the last 14 days.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </PageShell>
  );
}

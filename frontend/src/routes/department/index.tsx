import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  Hourglass,
  TrendingUp,
  XCircle,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  departmentApi,
  STAGE_LABELS,
  SLA_LABEL,
  SLA_TONE,
} from "@/lib/iris/department-api";
import type { ApplicationStage, SlaState } from "@/lib/iris/department-api";
import { PageShell, PageHeader, SectionHeading } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import { cn } from "@/lib/utils";
import { BackendUnavailableError } from "@/lib/iris/api-client";

export const Route = createFileRoute("/department/")({
  head: () => ({
    meta: [
      { title: "Department Dashboard — IRIS Gov" },
      {
        name: "description",
        content:
          "Real-time operational dashboard for government department application processing.",
      },
    ],
  }),
  component: DepartmentDashboard,
});

const PIPELINE_COLORS: Record<string, string> = {
  SUBMITTED: "oklch(0.525 0.021 270)",
  UNDER_REVIEW: "oklch(0.5 0.15 280)",
  INFORMATION_REQUESTED: "oklch(0.58 0.14 62)",
  INSPECTION_SCHEDULED: "oklch(0.5 0.15 280)",
  INSPECTION_COMPLETED: "oklch(0.5 0.15 280)",
  RECOMMENDED: "oklch(0.5 0.11 155)",
  APPROVED: "oklch(0.5 0.11 155)",
  REJECTED: "oklch(0.53 0.19 25.5)",
};

const SLA_TONE_CLASSES: Record<SlaState, string> = {
  WITHIN_SLA: "border-success/25 bg-success-surface text-success",
  AT_RISK: "border-warning/30 bg-warning-surface text-warning",
  BREACHED: "border-destructive/25 bg-danger-surface text-destructive",
  COMPLETED: "border-border bg-neutral-surface text-muted-foreground",
};

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

function KpiCard({
  label,
  value,
  icon: Icon,
  tone = "neutral",
  sublabel,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  tone?: "neutral" | "info" | "warning" | "danger" | "success";
  sublabel?: string;
}) {
  const toneClass = {
    neutral: "text-foreground",
    info: "text-info",
    warning: "text-warning",
    danger: "text-destructive",
    success: "text-success",
  }[tone];

  const iconBg = {
    neutral: "bg-secondary",
    info: "bg-info-surface",
    warning: "bg-warning-surface",
    danger: "bg-danger-surface",
    success: "bg-success-surface",
  }[tone];

  return (
    <div className="panel flex items-start gap-4 p-5">
      <div
        className={cn(
          "flex h-10 w-10 shrink-0 items-center justify-center rounded-md",
          iconBg,
        )}
      >
        <Icon className={cn("h-5 w-5", toneClass)} />
      </div>
      <div className="min-w-0">
        <div className="label-meta">{label}</div>
        <div
          className={cn(
            "mt-1.5 tabular text-[32px] font-semibold leading-none tracking-[-0.02em]",
            toneClass,
          )}
        >
          {value}
        </div>
        {sublabel && (
          <p className="mt-1 text-[11.5px] text-muted-foreground">{sublabel}</p>
        )}
      </div>
    </div>
  );
}

function DepartmentDashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["department", "dashboard"],
    queryFn: departmentApi.getDashboard,
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <PageShell wide>
        <PageHeader
          trail={[{ label: "Department" }, { label: "Dashboard" }]}
          title="Dashboard"
        />
        <div className="mt-8 grid animate-pulse grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="panel h-24 bg-surface" />
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
          trail={[{ label: "Department" }, { label: "Dashboard" }]}
          title="Dashboard"
        />
        <div className="mt-8 border border-destructive/25 bg-danger-surface p-6">
          <p className="text-[13px] font-medium text-destructive">
            {isOffline
              ? "IRIS backend is not reachable"
              : "Failed to load dashboard data"}
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

  const { kpis, pipeline, recent_applications, attention_required } = data!;

  // Filter pipeline to stages with count > 0 for the chart
  const pipelineChart = pipeline.filter((p) => p.count > 0);

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Department" }, { label: "Dashboard" }]}
        title="Department Dashboard"
        description="Real-time operational overview of all applications in the regulatory pipeline."
        actions={
          <Link
            to="/department/applications"
            className="focus-ring inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            All Applications
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        }
      />

      {/* KPI Cards */}
      <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <KpiCard
          label="Total Applications"
          value={kpis.total}
          icon={FileText}
        />
        <KpiCard
          label="Pending"
          value={kpis.pending}
          icon={Hourglass}
          tone="neutral"
          sublabel="Awaiting review"
        />
        <KpiCard
          label="In Progress"
          value={kpis.in_progress}
          icon={TrendingUp}
          tone="info"
          sublabel="Active processing"
        />
        <KpiCard
          label="Completed"
          value={kpis.completed}
          icon={CheckCircle2}
          tone="success"
          sublabel="Approved + Rejected"
        />
        <KpiCard
          label="SLA At Risk"
          value={kpis.sla_at_risk}
          icon={Clock}
          tone="warning"
          sublabel="Warning threshold hit"
        />
        <KpiCard
          label="SLA Breached"
          value={kpis.sla_breached}
          icon={XCircle}
          tone="danger"
          sublabel="Past due date"
        />
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-8">
          {/* Application Pipeline Chart */}
          <section>
            <SectionHeading
              title="Application Pipeline"
              hint="Count by current workflow stage."
            />
            <div className="mt-3 panel p-5">
              {pipelineChart.length === 0 ? (
                <p className="py-8 text-center text-[12.5px] text-muted-foreground">
                  No applications yet. Create one from the Applications page.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart
                    data={pipelineChart}
                    margin={{ top: 4, right: 4, bottom: 4, left: -20 }}
                  >
                    <XAxis
                      dataKey="stage"
                      tick={{
                        fontSize: 10,
                        fill: "var(--color-muted-foreground)",
                      }}
                      tickFormatter={(v) =>
                        STAGE_LABELS[v as ApplicationStage] ?? v
                      }
                    />
                    <YAxis
                      tick={{
                        fontSize: 10,
                        fill: "var(--color-muted-foreground)",
                      }}
                      allowDecimals={false}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "var(--color-surface)",
                        border: "1px solid var(--color-border)",
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                      formatter={(v: number) => [v, "Applications"]}
                      labelFormatter={(l) =>
                        STAGE_LABELS[l as ApplicationStage] ?? l
                      }
                    />
                    <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                      {pipelineChart.map((entry) => (
                        <Cell
                          key={entry.stage}
                          fill={
                            PIPELINE_COLORS[entry.stage] ?? "var(--color-info)"
                          }
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </section>

          {/* Recent Applications */}
          <section>
            <SectionHeading
              title="Recent Applications"
              actions={
                <Link
                  to="/department/applications"
                  className="text-[12px] font-medium text-info transition-opacity hover:opacity-80"
                >
                  View all
                </Link>
              }
            />
            <div className="mt-3 border border-border bg-surface">
              {recent_applications.length === 0 ? (
                <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
                  No applications yet.
                </p>
              ) : (
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-border bg-surface-sunken">
                      <th className="label-meta px-4 py-2.5 font-semibold">
                        Application
                      </th>
                      <th className="label-meta px-4 py-2.5 font-semibold">
                        Requirement
                      </th>
                      <th className="label-meta px-4 py-2.5 font-semibold">
                        Stage
                      </th>
                      <th className="label-meta px-4 py-2.5 font-semibold">
                        Officer
                      </th>
                      <th className="label-meta px-4 py-2.5 font-semibold">
                        SLA
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {recent_applications.map((app) => (
                      <tr
                        key={app.id}
                        className="row-hover hover:bg-surface-sunken"
                      >
                        <td className="px-4 py-3">
                          <Link
                            to="/department/application/$appId"
                            params={{ appId: app.id }}
                            className="text-[13px] font-medium text-info hover:underline"
                          >
                            {app.application_id}
                          </Link>
                          <p className="text-[11px] text-muted-foreground">
                            {app.project_id}
                          </p>
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
                            <span className="text-warning">Unassigned</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={cn(
                              "inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-[3px] text-[10.5px] font-medium",
                              SLA_TONE_CLASSES[app.sla_state],
                            )}
                          >
                            {SLA_LABEL[app.sla_state]}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </div>

        {/* Attention Required */}
        <section>
          <SectionHeading
            title="Attention Required"
            hint="Applications needing immediate action."
          />
          <div className="mt-3 space-y-2">
            {attention_required.length === 0 ? (
              <div className="flex items-center gap-3 border border-success/25 bg-success-surface px-4 py-4">
                <CheckCircle2 className="h-4 w-4 text-success" />
                <p className="text-[12.5px] text-success">
                  All applications are on track — no immediate attention needed.
                </p>
              </div>
            ) : (
              attention_required.map((item) => (
                <div
                  key={item.id}
                  className={cn(
                    "row-hover border px-4 py-3.5",
                    item.sla_state === "BREACHED"
                      ? "border-destructive/25 bg-danger-surface"
                      : item.sla_state === "AT_RISK"
                        ? "border-warning/30 bg-warning-surface"
                        : "border-border bg-surface",
                  )}
                >
                  <div className="flex items-start gap-2">
                    <AlertTriangle
                      className={cn(
                        "mt-[2px] h-4 w-4 shrink-0",
                        item.sla_state === "BREACHED"
                          ? "text-destructive"
                          : "text-warning",
                      )}
                    />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          to="/department/application/$appId"
                          params={{ appId: item.id }}
                          className="text-[13px] font-medium hover:underline"
                        >
                          {item.application_id}
                        </Link>
                        <span
                          className={cn(
                            "inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-[3px] text-[10.5px] font-medium",
                            STAGE_TONE_CLASSES[item.current_stage],
                          )}
                        >
                          {STAGE_LABELS[item.current_stage]}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-[11.5px] text-muted-foreground">
                        {item.title}
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {item.reasons.map((r) => (
                          <Tag key={r} tone="warning">
                            {r}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* SLA Overview summary */}
          <div className="mt-6">
            <SectionHeading title="SLA Overview" />
            <div className="mt-3 grid grid-cols-2 gap-3">
              {[
                {
                  label: "Within SLA",
                  value:
                    kpis.total -
                    kpis.sla_at_risk -
                    kpis.sla_breached -
                    kpis.completed,
                  tone: "success" as const,
                  cls: SLA_TONE_CLASSES.WITHIN_SLA,
                },
                {
                  label: "At Risk",
                  value: kpis.sla_at_risk,
                  tone: "warning" as const,
                  cls: SLA_TONE_CLASSES.AT_RISK,
                },
                {
                  label: "Breached",
                  value: kpis.sla_breached,
                  tone: "danger" as const,
                  cls: SLA_TONE_CLASSES.BREACHED,
                },
                {
                  label: "Completed",
                  value: kpis.completed,
                  tone: "neutral" as const,
                  cls: SLA_TONE_CLASSES.COMPLETED,
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className={cn(
                    "flex items-center justify-between rounded-md border px-3 py-3",
                    item.cls,
                  )}
                >
                  <span className="text-[12px] font-medium">{item.label}</span>
                  <span className="tabular text-[20px] font-semibold">
                    {Math.max(0, item.value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </PageShell>
  );
}

import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, CircleAlert } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import {
  readiness,
  byAuthority,
  deriveNextActions,
  deriveDeadlines,
  lastEvaluated,
} from "@/lib/iris/derive";
import {
  useProjectRequirements,
  useProjectActivity,
} from "@/lib/iris/use-project-data";
import {
  PageShell,
  PageHeader,
  SectionHeading,
  DataField,
  StatLine,
} from "@/components/iris/page";
import { StatusBadge, StatusDot, Meter, Tag } from "@/components/iris/status";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Regulatory Overview — IRIS" },
      {
        name: "description",
        content:
          "Project-level regulatory readiness, active blockers, upcoming deadlines and next actions for industrial approvals in Maharashtra.",
      },
      { property: "og:title", content: "Regulatory Overview — IRIS" },
      {
        property: "og:description",
        content:
          "Readiness, blockers, deadlines and authority workload for the active industrial project.",
      },
    ],
  }),
  component: Overview,
});

function Overview() {
  const { activeProject } = useProject();
  const { data: reqs = [] } = useProjectRequirements(activeProject.id);
  const { data: activity = [] } = useProjectActivity(activeProject.id);
  const summary = readiness(reqs);
  const authorities = byAuthority(reqs);
  const actions = deriveNextActions(reqs);
  const deadlines = deriveDeadlines(reqs);

  const blocker = summary.blockers[0];

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Workspace" }, { label: "Overview" }]}
        title="Regulatory Overview"
        description={`${activeProject.name} · ${activeProject.stage.replace("-", " ")} stage`}
        actions={
          <>
            <Link
              to="/requirements"
              className="focus-ring rounded-md border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors duration-150 hover:border-border-strong hover:bg-secondary"
            >
              Requirements
            </Link>
            <Link
              to="/regulatory-map"
              className="focus-ring rounded-md bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground shadow-[0_1px_2px_rgba(30,20,70,0.25)] transition-opacity duration-150 hover:opacity-90"
            >
              Regulatory map
            </Link>
          </>
        }
        meta={
          <StatLine
            items={[
              {
                value: `${summary.readinessPct}%`,
                label: "ready",
                tone: summary.blocked ? "warning" : "success",
              },
              {
                value: summary.ready,
                label: `of ${summary.applicable.length} applicable`,
              },
              { value: summary.blocked, label: "blocked", tone: "danger" },
              {
                value: summary.attention,
                label: "need action",
                tone: "warning",
              },
              {
                value: <span className="tabular">{lastEvaluated}</span>,
                label: "last evaluated",
              },
            ]}
          />
        }
      />

      {/* Primary project panel */}
      <section className="panel mt-6 border border-border bg-surface">
        <div className="grid gap-x-8 gap-y-4 border-b border-border px-5 py-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:px-6">
          <div>
            <div className="label-meta">Active project</div>
            <h2 className="mt-1.5 text-[16px] font-semibold leading-snug">
              {activeProject.name}
            </h2>
            <p className="mt-1 text-[12.5px] text-muted-foreground">
              {activeProject.activity} · {activeProject.workers} workers ·{" "}
              <span className="capitalize">{activeProject.scale} scale</span>
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {Object.entries(activeProject.characteristics)
                .filter(([, v]) => v)
                .map(([k]) => (
                  <span
                    key={k}
                    className="rounded-sm border border-border bg-surface-sunken px-1.5 py-[3px] text-[10.5px] text-muted-foreground"
                  >
                    {k.replace(/([A-Z])/g, " $1").toLowerCase()}
                  </span>
                ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            <DataField
              label="Industry"
              value={
                <span className="capitalize">{activeProject.industry}</span>
              }
            />
            <DataField
              label="Location"
              value={`${activeProject.location}, IN`}
            />
            <DataField
              label="Stage"
              value={
                <span className="capitalize">
                  {activeProject.stage.replace("-", " ")}
                </span>
              }
            />
            <DataField
              label="Last evaluated"
              value={<span className="tabular">{lastEvaluated}</span>}
            />
          </div>
        </div>

        {/* Readiness strip */}
        <div className="grid divide-y divide-border md:grid-cols-4 md:divide-x md:divide-y-0">
          <div className="px-5 py-4 md:px-6">
            <div className="label-meta">Regulatory readiness</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="tabular text-[28px] font-semibold leading-none tracking-[-0.02em]">
                {summary.readinessPct}%
              </span>
              <span className="text-[12px] text-muted-foreground">
                {summary.ready}/{summary.applicable.length} ready
              </span>
            </div>
            <Meter
              value={summary.ready}
              total={summary.applicable.length}
              tone={summary.blocked ? "warning" : "success"}
              className="mt-3"
            />
          </div>
          {[
            {
              label: "Active blockers",
              value: summary.blocked,
              tone: "danger" as const,
              note: "Halting downstream approvals",
            },
            {
              label: "Action required",
              value: summary.attention,
              tone: "warning" as const,
              note: "Documents or clarifications pending",
            },
            {
              label: "Not applicable",
              value: summary.notApplicable,
              tone: "neutral" as const,
              note: "Excluded at current scale",
            },
          ].map((m) => (
            <div key={m.label} className="px-5 py-4 md:px-6">
              <div className="label-meta">{m.label}</div>
              <div className="mt-2 flex items-baseline gap-2">
                <span
                  className={cn(
                    "tabular text-[28px] font-semibold leading-none tracking-[-0.02em]",
                    m.tone === "danger" && "text-destructive",
                    m.tone === "warning" && "text-warning",
                  )}
                >
                  {m.value}
                </span>
              </div>
              <p className="mt-3 text-[11.5px] leading-relaxed text-muted-foreground">
                {m.note}
              </p>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="space-y-8">
          {/* Blocker */}
          {blocker && (
            <section>
              <SectionHeading
                title="Active blocker"
                hint="Requirement halting the current approval sequence."
              />
              <div className="mt-3 border border-destructive/25 bg-danger-surface">
                <div className="flex flex-wrap items-start gap-3 border-b border-destructive/20 px-5 py-4">
                  <CircleAlert className="mt-[3px] h-4 w-4 shrink-0 text-destructive" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-[14px] font-semibold">
                        {blocker.name}
                      </h3>
                      <StatusBadge status="blocked" />
                    </div>
                    <p className="mt-1.5 text-[12.5px] leading-relaxed text-foreground/80">
                      {blocker.reason ?? blocker.description}
                    </p>
                  </div>
                </div>
                <div className="grid gap-x-6 gap-y-4 bg-surface px-5 py-4 sm:grid-cols-4">
                  <DataField
                    label="Authority"
                    value={blocker.authority}
                    className="sm:col-span-2"
                  />
                  <DataField
                    label="Documents"
                    value={`${blocker.documents.complete} of ${blocker.documents.total}`}
                  />
                  <DataField
                    label="Downstream blocked"
                    value={`${blocker.blocks.length} requirement${blocker.blocks.length === 1 ? "" : "s"}`}
                  />
                </div>
              </div>
            </section>
          )}

          {/* Next actions */}
          <section>
            <SectionHeading
              title="Next actions"
              hint="Ordered by impact on the current approval path."
              actions={
                <Link
                  to="/requirements"
                  className="text-[12px] font-medium text-info transition-opacity hover:opacity-80"
                >
                  All requirements
                </Link>
              }
            />
            <ul className="mt-3 divide-y divide-border border border-border bg-surface">
              {actions.map((a, i) => (
                <li
                  key={a.title}
                  className="row-hover px-5 py-4 hover:bg-surface-sunken"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1.5">
                    <div className="flex min-w-0 items-baseline gap-3">
                      <span className="tabular text-[11.5px] text-muted-foreground">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <h3 className="text-[13.5px] font-medium">{a.title}</h3>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <StatusBadge status={a.severity} />
                      <span className="text-[11.5px] text-muted-foreground">
                        {a.due}
                      </span>
                    </div>
                  </div>
                  <p className="mt-1.5 pl-[30px] text-[12.5px] leading-relaxed text-muted-foreground">
                    {a.why}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 pl-[30px] text-[11.5px] text-muted-foreground">
                    <span>
                      <span className="label-meta mr-1.5">Requirement</span>
                      {a.requirement}
                    </span>
                    <span>
                      <span className="label-meta mr-1.5">Authority</span>
                      {a.authority}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* Requirements by authority */}
          <section>
            <SectionHeading
              title="Requirements by authority"
              hint="Applicable requirements only."
            />
            <table className="mt-3 w-full border border-border bg-surface text-left">
              <thead>
                <tr className="border-b border-border bg-surface-sunken">
                  <th className="label-meta px-5 py-2.5 font-semibold">
                    Authority
                  </th>
                  <th className="label-meta px-5 py-2.5 text-right font-semibold">
                    Requirements
                  </th>
                  <th className="label-meta px-5 py-2.5 text-right font-semibold">
                    Complete
                  </th>
                  <th className="label-meta px-5 py-2.5 text-right font-semibold">
                    Open
                  </th>
                  <th className="label-meta w-[140px] px-5 py-2.5 font-semibold">
                    Progress
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {authorities.map((a) => (
                  <tr
                    key={a.authority}
                    className="row-hover hover:bg-surface-sunken"
                  >
                    <td className="px-5 py-3 text-[13px] font-medium">
                      {a.authority}
                    </td>
                    <td className="tabular px-5 py-3 text-right text-[13px]">
                      {a.total}
                    </td>
                    <td className="tabular px-5 py-3 text-right text-[13px] text-success">
                      {a.ready}
                    </td>
                    <td className="tabular px-5 py-3 text-right text-[13px] text-muted-foreground">
                      {a.open}
                    </td>
                    <td className="px-5 py-3">
                      <Meter
                        value={a.ready}
                        total={a.total}
                        tone={a.open ? "warning" : "success"}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>

        <div className="space-y-8">
          {/* Deadlines */}
          <section>
            <SectionHeading title="Upcoming deadlines" hint="Next 60 days." />
            <ul className="mt-3 divide-y divide-border border border-border bg-surface">
              {deadlines.map((d) => (
                <li
                  key={d.label}
                  className="row-hover px-4 py-3.5 hover:bg-surface-sunken"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-start gap-2">
                        <StatusDot status={d.severity} className="mt-[6px]" />
                        <p className="text-[13px] font-medium leading-snug">
                          {d.label}
                        </p>
                      </div>
                      <p className="mt-1 pl-3.5 text-[11.5px] text-muted-foreground">
                        {d.authority} · {d.note}
                      </p>
                    </div>
                    <span className="tabular shrink-0 text-[11.5px] text-muted-foreground">
                      {d.date}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* Change impact prompt */}
          <section className="row-hover border border-border bg-surface px-4 py-4 hover:border-border-strong">
            <div className="flex items-center justify-between gap-3">
              <div className="label-meta">Change impact</div>
              <span className="rounded-sm border border-warning/30 bg-warning-surface px-1.5 py-[2px] text-[10px] font-medium text-warning">
                1 pending
              </span>
            </div>
            <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
              A proposed scope change is awaiting impact review before
              submission.
            </p>
            <Link
              to="/change-impact"
              className="focus-ring mt-3 inline-flex items-center gap-1.5 text-[12.5px] font-medium text-info transition-opacity hover:opacity-80"
            >
              Run change impact analysis
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </section>

          {/* Activity */}
          <section>
            <SectionHeading title="Recent project activity" />
            <ol className="mt-3 border-l border-border pl-4">
              {activity.map((a, i) => (
                <li key={`${a.time}-${i}`} className="relative pb-4 last:pb-0">
                  <span
                    className="absolute -left-[21px] top-[6px] h-[7px] w-[7px] rounded-full border border-border bg-surface"
                    aria-hidden
                  />
                  <p className="text-[12.5px] leading-relaxed">{a.text}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    <span className="tabular">{a.time}</span> · {a.actor}
                  </p>
                </li>
              ))}
            </ol>
          </section>

          <section className="flex items-center gap-2 border-t border-border pt-4">
            <Tag>Prototype dataset</Tag>
            <p className="text-[11px] text-muted-foreground">
              Adds intelligence around NSWS/MAITRI, doesn't replace them.
            </p>
          </section>
        </div>
      </div>
    </PageShell>
  );
}

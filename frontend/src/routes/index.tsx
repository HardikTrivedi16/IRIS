import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import { lastEvaluated } from "@/lib/iris/derive";
import { useProjectActivity } from "@/lib/iris/use-project-data";
import { useDatasetRequirementTitles } from "@/lib/iris/facts";
import { useEngineEvaluation } from "@/lib/iris/use-engine-evaluation";
import { useRegulatoryItems } from "@/lib/iris/use-regulatory-items";
import { rollupByAuthority, summarizeItems } from "@/lib/iris/regulatory-items";
import {
  attentionFromApplications,
  attentionFromDependencyGraph,
  attentionFromEngineDecisions,
  attentionFromRegulatoryItems,
  orderAttentionItems,
  ATTENTION_CATEGORY_LABEL,
  type AttentionItem,
} from "@/lib/iris/attention";
import { irisApi, BackendUnavailableError } from "@/lib/iris/api-client";
import {
  PageShell,
  PageHeader,
  SectionHeading,
  DataField,
  StatLine,
} from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
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
  const { data: activity = [] } = useProjectActivity(activeProject.id);
  // Regulatory intelligence comes from the engine (shared adapter), not the
  // operational project_requirements tracking table.
  const regulatory = useRegulatoryItems(activeProject.id);
  const summary = useMemo(() => summarizeItems(regulatory.items), [regulatory.items]);
  const authorities = useMemo(() => rollupByAuthority(regulatory.items), [regulatory.items]);

  // REGULATORY ATTENTION — every source below reads the project's STORED
  // state only (evaluateAll takes no ad-hoc fact overrides; the applications
  // and dependency-graph reads are plain GETs). Scenario Lab's hypothetical
  // results live only in change-impact.tsx's own local state and are never
  // read here.
  const titlesQuery = useDatasetRequirementTitles();
  const evaluationQuery = useEngineEvaluation(activeProject.id, "PRODUCTION");
  const applicationsQuery = useQuery({
    queryKey: ["project-applications", activeProject.id],
    queryFn: () => irisApi.listProjectApplications(activeProject.id),
    retry: (n, e) => !(e instanceof BackendUnavailableError) && n < 1,
  });
  const dependencyGraphQuery = useQuery({
    queryKey: ["dependency-graph", activeProject.id, "PRODUCTION"],
    queryFn: () => irisApi.getDependencyGraph(activeProject.id, "PRODUCTION"),
    retry: (n, e) => !(e instanceof BackendUnavailableError) && n < 1,
  });

  const attentionItems = useMemo<AttentionItem[]>(() => {
    const titles = titlesQuery.data ?? {};
    const titleFor = (id: string) => titles[id] ?? id;
    return orderAttentionItems([
      ...attentionFromEngineDecisions(evaluationQuery.data ?? [], titleFor),
      ...attentionFromRegulatoryItems(regulatory.items),
      ...attentionFromApplications(applicationsQuery.data ?? []),
      ...attentionFromDependencyGraph(dependencyGraphQuery.data),
    ]);
  }, [
    titlesQuery.data,
    evaluationQuery.data,
    regulatory.items,
    applicationsQuery.data,
    dependencyGraphQuery.data,
  ]);
  const attentionLoading =
    evaluationQuery.isLoading ||
    regulatory.isLoading ||
    applicationsQuery.isLoading ||
    dependencyGraphQuery.isLoading;

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
                value: summary.diagnosticApplicable,
                label: "diagnostically applicable",
                tone: "warning",
              },
              {
                value: summary.needsInformation + summary.needsReview,
                label: "need information or review",
                tone: "warning",
              },
              {
                value: summary.authoritative,
                label: `authoritative of ${summary.total}`,
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

        {/* Regulatory position — deterministic counts, not a compliance score */}
        <div className="grid divide-y divide-border md:grid-cols-4 md:divide-x md:divide-y-0">
          {[
            {
              label: "Production determinations",
              value: `${summary.authoritative}/${summary.total}`,
              tone: "neutral" as const,
              note: `${summary.awaitingVerifiedKnowledge} awaiting verified regulatory knowledge (DRAFT rules)`,
            },
            {
              label: "Diagnostic: applicable",
              value: `${summary.diagnosticApplicable}`,
              tone: "warning" as const,
              note: "Non-authoritative — the DRAFT rules match this project's facts",
            },
            {
              label: "Needs information or review",
              value: `${summary.needsInformation + summary.needsReview}`,
              tone: "warning" as const,
              note: `${summary.unresolvedTriggers} more not yet evaluable (diagnostic result: requires information)`,
            },
            {
              label: "Diagnostic: not applicable",
              value: `${summary.diagnosticNotApplicable}`,
              tone: "neutral" as const,
              note: "Non-authoritative — excluded by the recorded facts",
            },
          ].map((m) => (
            <div key={m.label} className="px-5 py-4 md:px-6">
              <div className="label-meta">{m.label}</div>
              <div className="mt-2 flex items-baseline gap-2">
                <span
                  className={cn(
                    "tabular text-[28px] font-semibold leading-none tracking-[-0.02em]",
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
          {/* Regulatory attention — what needs attention in IRIS's
              regulatory understanding or the project's regulatory
              workflow. Not a blocker list, not a compliance/risk score:
              each item keeps the distinct meaning of the signal it came
              from (see lib/iris/attention.ts). */}
          <section>
            <SectionHeading
              title="Regulatory attention"
              hint={
                attentionItems.length > 0
                  ? `${attentionItems.length} item${attentionItems.length === 1 ? "" : "s"}`
                  : "What needs attention in IRIS's regulatory understanding or this project's regulatory workflow."
              }
              actions={
                <Link
                  to="/requirements"
                  className="text-[12px] font-medium text-info transition-opacity hover:opacity-80"
                >
                  All requirements
                </Link>
              }
            />
            {attentionLoading ? (
              <p className="mt-3 border border-border bg-surface px-5 py-6 text-[12.5px] text-muted-foreground">
                Checking regulatory evaluation, applications and dependencies…
              </p>
            ) : attentionItems.length === 0 ? (
              <p className="mt-3 border border-dashed border-border bg-surface px-5 py-6 text-[12.5px] leading-relaxed text-muted-foreground">
                No unresolved regulatory attention items found from the
                information IRIS currently holds.
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-border border border-border bg-surface">
                {attentionItems.map((item) => (
                  <li key={item.id} className="row-hover px-5 py-4 hover:bg-surface-sunken">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1.5">
                      <div className="flex min-w-0 items-baseline gap-3">
                        <span className="label-meta shrink-0">
                          {ATTENTION_CATEGORY_LABEL[item.category]}
                        </span>
                        {item.diagnostic && (
                          <Tag tone="info" className="shrink-0">
                            Diagnostic — non-authoritative
                          </Tag>
                        )}
                        <h3 className="text-[13.5px] font-medium">{item.title}</h3>
                      </div>
                      <Link
                        to={item.action.route}
                        className="flex shrink-0 items-center gap-1 text-[12px] font-medium text-info transition-opacity hover:opacity-80"
                      >
                        {item.action.label}
                        <ArrowRight className="h-3 w-3" />
                      </Link>
                    </div>
                    <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">
                      {item.reason}
                    </p>
                    {item.missingFactKeys && item.missingFactKeys.length > 0 && (
                      <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5">
                        {item.missingFactKeys.map((k) => (
                          <li key={k} className="font-mono text-[11px] text-warning">
                            {k}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Requirements by authority — engine requirements this project is matched to */}
          <section>
            <SectionHeading
              title="Requirements by authority"
              hint="Diagnostic matches and information gaps, grouped by the authority in the regulatory dataset."
            />
            {authorities.length === 0 ? (
              <p className="mt-3 border border-dashed border-border bg-surface px-5 py-6 text-[12.5px] text-muted-foreground">
                {regulatory.isLoading
                  ? "Evaluating requirements…"
                  : "No requirement is matched to this project's recorded facts yet."}
              </p>
            ) : (
              <table className="mt-3 w-full border border-border bg-surface text-left">
                <thead>
                  <tr className="border-b border-border bg-surface-sunken">
                    <th className="label-meta px-5 py-2.5 font-semibold">Authority</th>
                    <th className="label-meta px-5 py-2.5 text-right font-semibold">
                      Diagnostic applicable
                    </th>
                    <th className="label-meta px-5 py-2.5 text-right font-semibold">
                      Needs information
                    </th>
                    <th className="label-meta px-5 py-2.5 text-right font-semibold">
                      Authoritative
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {authorities.map((a) => (
                    <tr key={a.authorityName} className="row-hover hover:bg-surface-sunken">
                      <td className="px-5 py-3 text-[13px] font-medium">{a.authorityName}</td>
                      <td className="tabular px-5 py-3 text-right text-[13px]">
                        {a.diagnosticApplicable}
                      </td>
                      <td className="tabular px-5 py-3 text-right text-[13px] text-muted-foreground">
                        {a.needsInformation}
                      </td>
                      <td className="tabular px-5 py-3 text-right text-[13px] text-muted-foreground">
                        {a.authoritative}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>

        <div className="space-y-8">
          {/* Deadlines — no statutory deadline is derived from engine rules */}
          <section>
            <SectionHeading title="Upcoming deadlines" hint="Next 60 days." />
            <p className="mt-3 border border-dashed border-border bg-surface px-5 py-6 text-[12.5px] leading-relaxed text-muted-foreground">
              No deadlines on record. IRIS does not derive statutory dates from regulatory rules;
              deadlines appear here only when they come from recorded project tracking data.
            </p>
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

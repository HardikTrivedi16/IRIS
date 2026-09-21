import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useProject } from "@/lib/iris/project-context";
import { useProjectRequirements } from "@/lib/iris/use-project-data";
import {
  PageHeader,
  PageShell,
  Drawer,
  DrawerSection,
  DataField,
  EmptyState,
} from "@/components/iris/page";
import { StatusBadge, StatusDot, Meter, Tag } from "@/components/iris/status";
import { EngineDecisionPanel } from "@/components/iris/engine-decision-panel";
import { EngineStatusStrip } from "@/components/iris/engine-status-strip";
import { isEngineBacked } from "@/lib/iris/engine-mapping";
import type { Requirement, Status } from "@/lib/iris/types";
import { readiness } from "@/lib/iris/derive";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/requirements")({
  head: () => ({
    meta: [
      { title: "Requirements & Readiness — IRIS" },
      {
        name: "description",
        content:
          "Filterable register of regulatory requirements with authority, stage, documents, dependencies and risk for the active project.",
      },
      { property: "og:title", content: "Requirements & Readiness — IRIS" },
      {
        property: "og:description",
        content:
          "Operational checklist of applicable regulatory requirements grouped by readiness.",
      },
    ],
  }),
  component: RequirementsPage,
});

const groups: {
  key: string;
  label: string;
  match: (r: Requirement) => boolean;
}[] = [
  { key: "blocked", label: "Blocked", match: (r) => r.status === "blocked" },
  {
    key: "attention",
    label: "Action required",
    match: (r) => r.status === "attention",
  },
  { key: "ready", label: "Completed", match: (r) => r.status === "ready" },
  {
    key: "pending",
    label: "Awaiting prerequisites",
    match: (r) =>
      r.applicability === "applicable" &&
      (r.status === "not-ready" || r.status === "not-applicable"),
  },
  {
    key: "na",
    label: "Not applicable",
    match: (r) => r.applicability === "not-applicable",
  },
];

function riskOf(r: Requirement): { status: Status; label: string } {
  if (r.status === "blocked") return { status: "blocked", label: "High" };
  if (r.status === "attention") return { status: "attention", label: "Medium" };
  if (r.status === "ready") return { status: "ready", label: "None" };
  return { status: "not-ready", label: "Low" };
}

function RequirementsPage() {
  const { activeProject } = useProject();
  const { data: reqs = [], isLoading } = useProjectRequirements(
    activeProject.id,
  );
  const summary = readiness(reqs);
  const [authority, setAuthority] = useState("all");
  const [stage, setStage] = useState("all");
  const [selected, setSelected] = useState<Requirement | null>(null);

  const authorities = useMemo(
    () =>
      [
        ...new Set(reqs.map((r) => r.authority).filter((a) => a !== "—")),
      ].sort(),
    [reqs],
  );
  const stages = useMemo(() => [...new Set(reqs.map((r) => r.stage))], [reqs]);

  const filtered = reqs.filter(
    (r) =>
      (authority === "all" || r.authority === authority) &&
      (stage === "all" || r.stage === stage),
  );

  const nameOf = (id: string) => reqs.find((r) => r.id === id)?.name ?? id;

  return (
    <PageShell wide>
      <PageHeader
        trail={[
          { label: "Regulatory intelligence" },
          { label: "Requirements" },
        ]}
        title="Requirements & Readiness"
        description={`${activeProject.name} · grouped by status · select a row for detail`}
        actions={
          <Link
            to="/documents"
            className="rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors hover:bg-secondary"
          >
            Document register
          </Link>
        }
        meta={
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
            <div className="flex items-baseline gap-2">
              <span className="tabular text-[15px] font-semibold">
                {summary.ready} of {summary.applicable.length}
              </span>
              <span className="text-[12.5px] text-muted-foreground">
                requirements ready
              </span>
            </div>
            <Meter
              value={summary.ready}
              total={summary.applicable.length}
              tone={summary.blocked ? "warning" : "success"}
              className="w-[180px]"
            />
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <StatusDot status="blocked" /> {summary.blocked} blocked
              </span>
              <span className="flex items-center gap-1.5">
                <StatusDot status="attention" /> {summary.attention} action
                required
              </span>
              <span className="flex items-center gap-1.5">
                <StatusDot status="not-applicable" /> {summary.notApplicable}{" "}
                not applicable
              </span>
            </div>
          </div>
        }
      />

      <EngineStatusStrip />

      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-3 border border-border bg-surface px-4 py-3">
        <div className="flex items-center gap-2">
          <label className="label-meta" htmlFor="req-authority">
            Authority
          </label>
          <select
            id="req-authority"
            value={authority}
            onChange={(e) => setAuthority(e.target.value)}
            className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12.5px]"
          >
            <option value="all">All authorities</option>
            {authorities.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="label-meta" htmlFor="req-stage">
            Stage
          </label>
          <select
            id="req-stage"
            value={stage}
            onChange={(e) => setStage(e.target.value)}
            className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12.5px]"
          >
            <option value="all">All stages</option>
            {stages.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <p className="ml-auto tabular text-[11.5px] text-muted-foreground">
          {filtered.length} of {reqs.length} requirements shown
        </p>
      </div>

      <div className="mt-5 border border-border bg-surface">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border bg-surface-sunken">
              <th className="label-meta px-5 py-2.5 font-semibold">
                Requirement
              </th>
              <th className="label-meta px-4 py-2.5 font-semibold">
                Authority
              </th>
              <th className="label-meta px-4 py-2.5 font-semibold">Stage</th>
              <th className="label-meta px-4 py-2.5 font-semibold">Status</th>
              <th className="label-meta px-4 py-2.5 text-right font-semibold">
                Documents
              </th>
              <th className="label-meta px-4 py-2.5 font-semibold">
                Dependency
              </th>
              <th className="label-meta px-4 py-2.5 font-semibold">Risk</th>
              <th className="label-meta px-5 py-2.5 text-right font-semibold">
                Timeline
              </th>
            </tr>
          </thead>
          {groups.map((g) => {
            const rows = filtered.filter(g.match);
            if (rows.length === 0) return null;
            return (
              <tbody
                key={g.key}
                className="divide-y divide-border border-b border-border last:border-b-0"
              >
                <tr className="bg-surface-sunken/70">
                  <td colSpan={8} className="px-5 py-2">
                    <span className="label-meta">{g.label}</span>
                    <span className="tabular ml-2 text-[11px] text-muted-foreground">
                      {rows.length}
                    </span>
                  </td>
                </tr>
                {rows.map((r) => {
                  const risk = riskOf(r);
                  return (
                    <tr
                      key={r.id}
                      onClick={() => setSelected(r)}
                      className={cn(
                        "row-hover cursor-pointer hover:bg-surface-sunken",
                        selected?.id === r.id && "bg-info-surface",
                      )}
                    >
                      <td className="px-5 py-3">
                        <div className="text-[13px] font-medium">{r.name}</div>
                        {r.reason && (
                          <div className="mt-1 text-[11.5px] text-destructive">
                            {r.reason}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground">
                        {r.authority}
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground">
                        {r.stage}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="tabular px-4 py-3 text-right text-[12.5px]">
                        {r.documents.total > 0 ? (
                          <span
                            className={cn(
                              r.documents.complete === r.documents.total
                                ? "text-success"
                                : "text-muted-foreground",
                            )}
                          >
                            {r.documents.complete}/{r.documents.total}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground">
                        {r.dependsOn.length > 0 ? nameOf(r.dependsOn[0]!) : "—"}
                        {r.dependsOn.length > 1 && (
                          <span className="text-muted-foreground/70">
                            {" "}
                            +{r.dependsOn.length - 1}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                          <StatusDot status={risk.status} />
                          {risk.label}
                        </span>
                      </td>
                      <td className="tabular px-5 py-3 text-right text-[12px] text-muted-foreground">
                        {r.timeline}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            );
          })}
        </table>
        {filtered.length === 0 && (
          <EmptyState
            title={isLoading ? "Loading requirements…" : "No requirements found"}
            description={
              isLoading
                ? "Fetching this project's regulatory register from the backend."
                : "This project has no requirements in the register yet. Adjust the filters, or seed the project's requirements."
            }
          />
        )}
      </div>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        eyebrow="Requirement detail"
        title={selected?.name ?? ""}
        subtitle={selected ? <StatusBadge status={selected.status} /> : null}
        footer={
          <Link
            to="/regulatory-map"
            className="inline-flex rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Show in regulatory map
          </Link>
        }
      >
        {selected && (
          <div>
            <DrawerSection label="Overview">
              <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
                <DataField label="Authority" value={selected.authority} />
                <DataField label="Stage" value={selected.stage} />
                <DataField
                  label="Expected timeline"
                  value={<span className="tabular">{selected.timeline}</span>}
                />
                <DataField
                  label="Applicability"
                  value={
                    selected.applicability === "applicable"
                      ? "Applicable"
                      : "Not applicable"
                  }
                />
              </div>
            </DrawerSection>

            <DrawerSection
              label="Regulatory engine"
              className={cn(
                !isEngineBacked(selected.id) && "bg-neutral-surface/40",
              )}
            >
              {isEngineBacked(selected.id) ? (
                <EngineDecisionPanel
                  project={activeProject}
                  frontendRequirementId={selected.id}
                />
              ) : (
                <div className="flex items-center gap-2">
                  <Tag tone="neutral">Prototype content</Tag>
                  <p className="text-[12px] text-muted-foreground">
                    Not yet backed by the Phase 9 regulatory engine — the
                    supplied dataset doesn't include a rule for this
                    requirement.
                  </p>
                </div>
              )}
            </DrawerSection>

            <DrawerSection label="Why this applies">
              <p className="text-muted-foreground">{selected.description}</p>
            </DrawerSection>

            {selected.reason && (
              <DrawerSection label="Blocking reason">
                <p className="border-l-2 border-destructive pl-3 text-destructive">
                  {selected.reason}
                </p>
              </DrawerSection>
            )}

            <DrawerSection label="Documents">
              <div className="flex items-baseline justify-between">
                <span className="tabular text-[15px] font-semibold">
                  {selected.documents.complete}
                  <span className="text-[12px] font-normal text-muted-foreground">
                    {" "}
                    / {selected.documents.total} verified
                  </span>
                </span>
                <Link
                  to="/documents"
                  className="text-[12px] font-medium text-info hover:opacity-80"
                >
                  Document register
                </Link>
              </div>
              {selected.documents.total > 0 && (
                <Meter
                  value={selected.documents.complete}
                  total={selected.documents.total}
                  tone={
                    selected.documents.complete === selected.documents.total
                      ? "success"
                      : "warning"
                  }
                  className="mt-2.5"
                />
              )}
            </DrawerSection>

            <DrawerSection label="Prerequisites">
              {selected.dependsOn.length ? (
                <ul className="space-y-1.5">
                  {selected.dependsOn.map((id) => (
                    <li key={id} className="text-[12.5px]">
                      {nameOf(id)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[12.5px] text-muted-foreground">
                  No upstream prerequisites.
                </p>
              )}
            </DrawerSection>

            <DrawerSection label="Blocks downstream">
              {selected.blocks.length ? (
                <ul className="space-y-1.5">
                  {selected.blocks.map((id) => (
                    <li key={id} className="text-[12.5px]">
                      {nameOf(id)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[12.5px] text-muted-foreground">
                  Nothing downstream depends on this item.
                </p>
              )}
            </DrawerSection>

            <DrawerSection label="Source reference">
              <p className="text-[12.5px]">{selected.source}</p>
              <p className="mt-1 text-[11.5px] text-muted-foreground">
                Verified September 2026 · prototype source record
              </p>
            </DrawerSection>
          </div>
        )}
      </Drawer>
    </PageShell>
  );
}

import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useProject } from "@/lib/iris/project-context";
import { useProjectRequirements } from "@/lib/iris/use-project-data";
import { buildRegulatoryGraph } from "@/lib/iris/derive";
import {
  PageHeader,
  PageShell,
  Drawer,
  DrawerSection,
  DataField,
} from "@/components/iris/page";
import { DependencyGraph } from "@/components/iris/dependency-graph";
import { StatusBadge, StatusDot, Meter } from "@/components/iris/status";
import type { GraphNode, Status } from "@/lib/iris/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/regulatory-map")({
  head: () => ({
    meta: [
      { title: "Regulatory Map — IRIS" },
      {
        name: "description",
        content:
          "Dependency map of approvals, prerequisites and documents shaping the industrial project approval path.",
      },
      { property: "og:title", content: "Regulatory Map — IRIS" },
      {
        property: "og:description",
        content:
          "Understand how approvals, documents and dependencies affect the project path.",
      },
    ],
  }),
  component: RegulatoryMap,
});

const stageFilters = [
  { key: "all", label: "All stages" },
  { key: "pre", label: "Pre-establishment" },
  { key: "construction", label: "Construction" },
  { key: "operations", label: "Operations" },
];

const preIds = new Set([
  "project",
  "midc-site",
  "building-plan",
  "mpcb-cte",
  "fire-approval",
  "factory-plan",
  "fssai-licence",
]);
const constructionIds = new Set([
  "construction",
  "inspection",
  "building-plan",
  "mpcb-cte",
  "fire-approval",
]);
const operationsIds = new Set([
  "factory-licence",
  "drug-licence",
  "mpcb-cto",
  "operation-ready",
  "fssai-licence",
]);

const statusFilters: { key: "all" | Status; label: string }[] = [
  { key: "all", label: "Any status" },
  { key: "ready", label: "Completed" },
  { key: "attention", label: "Action required" },
  { key: "blocked", label: "Blocked" },
  { key: "not-ready", label: "Not started" },
];

function RegulatoryMap() {
  const { activeProject } = useProject();
  const { data: reqs = [] } = useProjectRequirements(activeProject.id);
  const { nodes, edges } = useMemo(
    () => buildRegulatoryGraph(reqs, activeProject.name),
    [reqs, activeProject.name],
  );

  const [stage, setStage] = useState("all");
  const [authority, setAuthority] = useState("all");
  const [status, setStatus] = useState<"all" | Status>("all");
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const authorities = useMemo(
    () =>
      [
        ...new Set(nodes.map((n) => n.authority).filter(Boolean) as string[]),
      ].sort(),
    [nodes],
  );

  const focusIds = useMemo(() => {
    if (stage === "all" && authority === "all" && status === "all") return null;
    const stageSet =
      stage === "pre"
        ? preIds
        : stage === "construction"
          ? constructionIds
          : stage === "operations"
            ? operationsIds
            : null;
    return new Set(
      nodes
        .filter((n) => (stageSet ? stageSet.has(n.id) : true))
        .filter((n) => (authority === "all" ? true : n.authority === authority))
        .filter((n) => (status === "all" ? true : n.status === status))
        .map((n) => n.id),
    );
  }, [nodes, stage, authority, status]);

  const req = selected ? reqs.find((r) => r.id === selected.id) : undefined;
  const nameOf = (id: string) =>
    reqs.find((r) => r.id === id)?.name ??
    nodes.find((n) => n.id === id)?.label ??
    id;

  const blockedCount = nodes.filter((n) => n.status === "blocked").length;
  const attentionCount = nodes.filter((n) => n.status === "attention").length;

  return (
    <PageShell wide className="pb-0">
      <PageHeader
        trail={[
          { label: "Regulatory intelligence" },
          { label: "Regulatory Map" },
        ]}
        title="Regulatory Map"
        description="Dependency path across approvals · select a node for detail"
        actions={
          <>
            <Link
              to="/change-impact"
              className="rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors hover:bg-secondary"
            >
              Change impact
            </Link>
            <Link
              to="/requirements"
              className="rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Requirement list
            </Link>
          </>
        }
        meta={
          <dl className="flex flex-wrap items-center gap-x-8 gap-y-2">
            {[
              { label: "Nodes", value: `${nodes.length}` },
              { label: "Dependencies", value: `${edges.length}` },
              { label: "Blocked", value: `${blockedCount}` },
              { label: "Action required", value: `${attentionCount}` },
              {
                label: "Critical path",
                value: "Site → Building → Factory plan → Licence",
              },
            ].map((s) => (
              <div key={s.label} className="flex items-baseline gap-2">
                <dt className="label-meta">{s.label}</dt>
                <dd className="tabular text-[13px] font-medium">{s.value}</dd>
              </div>
            ))}
          </dl>
        }
      />

      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3 border border-border bg-surface px-4 py-3">
        <div className="flex items-center gap-1">
          {stageFilters.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setStage(f.key)}
              className={cn(
                "rounded-sm px-2.5 py-[6px] text-[12.5px] transition-colors",
                stage === f.key
                  ? "bg-primary font-medium text-primary-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <label className="label-meta" htmlFor="authority-filter">
            Authority
          </label>
          <select
            id="authority-filter"
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
          <label className="label-meta" htmlFor="status-filter">
            Status
          </label>
          <select
            id="status-filter"
            value={status}
            onChange={(e) => setStatus(e.target.value as "all" | Status)}
            className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12.5px]"
          >
            {statusFilters.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {(stage !== "all" || authority !== "all" || status !== "all") && (
          <button
            type="button"
            onClick={() => {
              setStage("all");
              setAuthority("all");
              setStatus("all");
            }}
            className="text-[12px] font-medium text-info transition-opacity hover:opacity-80"
          >
            Clear filters
          </button>
        )}

        <p className="ml-auto text-[11.5px] text-muted-foreground">
          Drag to pan · dependencies flow left to right
        </p>
      </div>

      <div className="mt-4 grid gap-0 border border-border lg:grid-cols-[minmax(0,1fr)_260px]">
        <DependencyGraph
          nodes={nodes}
          edges={edges}
          selectedId={selected?.id ?? null}
          onSelect={setSelected}
          focusIds={focusIds}
          className="h-[560px] border-b border-border lg:border-b-0 lg:border-r"
        />

        <aside className="bg-surface">
          <div className="border-b border-border px-4 py-3">
            <div className="label-meta">Sequence</div>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
              Approvals must clear in dependency order. Items below are listed
              by depth in the path.
            </p>
          </div>
          <ol className="max-h-[492px] overflow-y-auto divide-y divide-border">
            {nodes.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => setSelected(n)}
                  className={cn(
                    "row-hover flex w-full items-start gap-2 px-4 py-2.5 text-left hover:bg-surface-sunken",
                    selected?.id === n.id && "bg-info-surface",
                    focusIds && !focusIds.has(n.id) && "opacity-45",
                  )}
                >
                  <StatusDot status={n.status} className="mt-[6px]" />
                  <span className="min-w-0">
                    <span className="block truncate text-[12.5px] font-medium">
                      {n.label}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {n.authority ?? "Project milestone"}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      <p className="mt-3 pb-8 text-[11.5px] text-muted-foreground">
        Regulatory information is represented using verified source references
        in this prototype.
      </p>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        eyebrow={
          selected?.type === "milestone"
            ? "Project milestone"
            : "Requirement detail"
        }
        title={selected?.label ?? ""}
        subtitle={selected ? <StatusBadge status={selected.status} /> : null}
        footer={
          selected && (
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11.5px] text-muted-foreground">
                {req?.stage ?? "Project path"} · {req?.timeline ?? "—"}
              </p>
              <Link
                to="/requirements"
                className="rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Open in requirements
              </Link>
            </div>
          )
        }
      >
        {selected && (
          <div>
            <DrawerSection label="Authority">
              <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
                <DataField
                  label="Regulator"
                  value={selected.authority ?? "—"}
                />
                <DataField label="Stage" value={req?.stage ?? "Project path"} />
              </div>
            </DrawerSection>

            <DrawerSection label="Why this applies">
              <p className="text-muted-foreground">
                {req?.description ??
                  selected.description ??
                  "This milestone marks completion of the preceding approval sequence."}
              </p>
            </DrawerSection>

            {req?.reason && (
              <DrawerSection label="Blocking reason">
                <p className="border-l-2 border-destructive pl-3 text-destructive">
                  {req.reason}
                </p>
              </DrawerSection>
            )}

            <DrawerSection label="Prerequisites">
              {selected.dependsOn && selected.dependsOn.length > 0 ? (
                <ul className="space-y-1.5">
                  {selected.dependsOn.map((id) => {
                    const dep = nodes.find((n) => n.id === id);
                    return (
                      <li key={id} className="flex items-center gap-2">
                        {dep && <StatusDot status={dep.status} />}
                        <span className="text-[12.5px]">{nameOf(id)}</span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-[12.5px] text-muted-foreground">
                  No upstream prerequisites.
                </p>
              )}
            </DrawerSection>

            <DrawerSection label="Documents required">
              {selected.documents ? (
                <>
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
                </>
              ) : (
                <p className="text-[12.5px] text-muted-foreground">
                  No documentation attached.
                </p>
              )}
            </DrawerSection>

            <DrawerSection label="Blocking items downstream">
              {selected.blocks && selected.blocks.length > 0 ? (
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

            <DrawerSection label="Expected timeline">
              <span className="tabular">{req?.timeline ?? "—"}</span>
            </DrawerSection>

            <DrawerSection label="Source reference">
              <p className="text-[12.5px]">
                {selected.source ?? req?.source ?? "—"}
              </p>
              <p className="mt-1 text-[11.5px] text-muted-foreground">
                Verified September 2026 · prototype source record
              </p>
            </DrawerSection>

            <DrawerSection label="Next action">
              <p className="text-[12.5px]">
                {selected.status === "blocked"
                  ? "Complete the outstanding site and building documentation, then request re-evaluation."
                  : selected.status === "attention"
                    ? "Complete outstanding documents and submit for authority review."
                    : selected.status === "ready"
                      ? "No action required. Retain approval evidence for downstream applications."
                      : "Awaiting prerequisites. No submission possible yet."}
              </p>
            </DrawerSection>
          </div>
        )}
      </Drawer>
    </PageShell>
  );
}

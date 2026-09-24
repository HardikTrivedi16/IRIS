import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useProject } from "@/lib/iris/project-context";
import {
  PageHeader,
  PageShell,
  Drawer,
  DrawerSection,
  DataField,
} from "@/components/iris/page";
import { DependencyGraph } from "@/components/iris/dependency-graph";
import { StatusDot, Tag } from "@/components/iris/status";
import { finalStateMeta } from "@/lib/iris/decision-states";
import { useRegulatoryItems } from "@/lib/iris/use-regulatory-items";
import {
  stageLabel,
  summarizeItems,
  toMapNodes,
  type RegulatoryItem,
} from "@/lib/iris/regulatory-items";
import type { GraphEdge, GraphNode } from "@/lib/iris/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/regulatory-map")({
  head: () => ({
    meta: [
      { title: "Regulatory Map — IRIS" },
      {
        name: "description",
        content:
          "The regulatory requirements evaluated for this project, by authority and lifecycle stage. Dependencies are shown only when verified.",
      },
      { property: "og:title", content: "Regulatory Map — IRIS" },
      {
        property: "og:description",
        content:
          "Requirements, authorities and rule-version status for the project. No dependency is inferred.",
      },
    ],
  }),
  component: RegulatoryMap,
});

type StateFilter = "relevant" | "applicable" | "not-applicable" | "needs" | "all";

const stateFilters: { key: StateFilter; label: string }[] = [
  { key: "relevant", label: "Relevant: applicable + needs information/review" },
  { key: "applicable", label: "Applicable" },
  { key: "needs", label: "Needs information / review" },
  { key: "not-applicable", label: "Not applicable" },
  { key: "all", label: "All requirements" },
];

const legend = [
  { status: "attention" as const, label: "Diagnostic: applicable" },
  { status: "not-applicable" as const, label: "Diagnostic: not applicable" },
  { status: "not-ready" as const, label: "Needs information / not yet evaluable" },
];

function matchesState(i: RegulatoryItem, f: StateFilter): boolean {
  const s = i.diagnostic?.finalState;
  switch (f) {
    case "relevant":
      // Default map: diagnostically applicable, or the project's own information/review gaps.
      // Diagnostic NOT_APPLICABLE requirements stay in the full catalogue (Not applicable / All).
      return s === "APPLICABLE" || i.relevance === "NEEDS_INFORMATION";
    case "applicable":
      return s === "APPLICABLE";
    case "not-applicable":
      return s === "NOT_APPLICABLE";
    case "needs":
      return i.relevance === "NEEDS_INFORMATION";
    default:
      return true;
  }
}

function RegulatoryMap() {
  const { activeProject } = useProject();
  const { items, isLoading } = useRegulatoryItems(activeProject.id);
  const summary = useMemo(() => summarizeItems(items), [items]);

  const [stage, setStage] = useState("all");
  const [authority, setAuthority] = useState("all");
  const [state, setState] = useState<StateFilter>("relevant");
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const authorities = useMemo(
    () => [...new Set(items.map((i) => i.authorityName).filter((a) => a !== "—"))].sort(),
    [items],
  );
  const stages = useMemo(
    () => [...new Set(items.flatMap((i) => i.lifecycleStageIds))].sort(),
    [items],
  );

  const visible = useMemo(
    () =>
      items.filter(
        (i) =>
          matchesState(i, state) &&
          (authority === "all" || i.authorityName === authority) &&
          (stage === "all" || i.lifecycleStageIds.includes(stage)),
      ),
    [items, state, authority, stage],
  );
  // Nodes come from the engine's own requirement catalogue. There are NO
  // edges: the dataset has zero verified Requirement->Requirement
  // dependencies and none is inferred.
  const nodes = useMemo(() => toMapNodes(visible), [visible]);
  const edges: GraphEdge[] = [];

  const item = selected ? items.find((i) => i.requirementId === selected.id) : undefined;
  const filtersActive = stage !== "all" || authority !== "all" || state !== "relevant";

  return (
    <PageShell wide className="pb-0">
      <PageHeader
        trail={[{ label: "Regulatory intelligence" }, { label: "Regulatory Map" }]}
        title="Regulatory Map"
        description="Requirements the rule engine evaluates for this project · select a node for detail"
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
              { label: "Shown", value: `${nodes.length} of ${items.length}` },
              { label: "Diagnostic applicable", value: `${summary.diagnosticApplicable}` },
              {
                label: "Need information",
                value: `${summary.needsInformation + summary.needsReview}`,
              },
              { label: "Verified regulatory dependencies", value: "0" },
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
        <div className="flex items-center gap-2">
          <label className="label-meta" htmlFor="stage-filter">
            Stage
          </label>
          <select
            id="stage-filter"
            value={stage}
            onChange={(e) => setStage(e.target.value)}
            className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12.5px]"
          >
            <option value="all">All stages</option>
            {stages.map((s) => (
              <option key={s} value={s}>
                {stageLabel(s)}
              </option>
            ))}
          </select>
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
          <label className="label-meta" htmlFor="state-filter">
            Show
          </label>
          <select
            id="state-filter"
            value={state}
            onChange={(e) => setState(e.target.value as StateFilter)}
            className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12.5px]"
          >
            {stateFilters.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {filtersActive && (
          <button
            type="button"
            onClick={() => {
              setStage("all");
              setAuthority("all");
              setState("relevant");
            }}
            className="text-[12px] font-medium text-info transition-opacity hover:opacity-80"
          >
            Reset filters
          </button>
        )}

        <p className="ml-auto text-[11.5px] text-muted-foreground">
          Drag to pan · states are diagnostic (non-authoritative)
        </p>
      </div>

      <div className="mt-4 grid gap-0 border border-border lg:grid-cols-[minmax(0,1fr)_260px]">
        {nodes.length > 0 ? (
          <DependencyGraph
            nodes={nodes}
            edges={edges}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            legend={legend}
            className="h-[560px] border-b border-border lg:border-b-0 lg:border-r"
          />
        ) : (
          <div className="flex h-[560px] items-center justify-center border-b border-border px-6 text-center text-[12.5px] text-muted-foreground lg:border-b-0 lg:border-r">
            {isLoading
              ? "Evaluating requirements…"
              : "No requirements match these filters."}
          </div>
        )}

        <aside className="bg-surface">
          <div className="border-b border-border px-4 py-3">
            <div className="label-meta">Requirements</div>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
              Listed by requirement id. There is no sequence: the dataset contains no verified
              prerequisite relationships, and unlinked items are not thereby shown to be parallel.
            </p>
          </div>
          <ol className="max-h-[492px] divide-y divide-border overflow-y-auto">
            {nodes.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => setSelected(n)}
                  className={cn(
                    "row-hover flex w-full items-start gap-2 px-4 py-2.5 text-left hover:bg-surface-sunken",
                    selected?.id === n.id && "bg-info-surface",
                  )}
                >
                  <StatusDot status={n.status} className="mt-[6px]" />
                  <span className="min-w-0">
                    <span className="block truncate text-[12.5px] font-medium">{n.label}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {n.authority ?? "—"}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      <p className="mt-3 pb-8 text-[11.5px] text-muted-foreground">
        Nodes come from the regulatory dataset and the rule engine's evaluation of this project's
        stored facts. The dataset currently has zero verified dependency edges, so IRIS shows no legal
        sequencing, critical path or parallel-approval claim. Node colours are diagnostic states, not
        completion status.
      </p>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        eyebrow="Requirement detail"
        title={selected?.label ?? ""}
        subtitle={
          item?.diagnostic ? (
            <Tag tone="info">Diagnostic — non-authoritative</Tag>
          ) : null
        }
        footer={
          selected && (
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11.5px] text-muted-foreground">
                {item?.lifecycleStageIds.map(stageLabel).join(", ") || "—"}
              </p>
              <Link
                to="/evaluation"
                className="rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Open in evaluation
              </Link>
            </div>
          )
        }
      >
        {selected && item && (
          <div>
            <DrawerSection label="Authority">
              <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
                <DataField label="Regulator" value={item.authorityName} />
                <DataField
                  label="Stage"
                  value={item.lifecycleStageIds.map(stageLabel).join(", ") || "—"}
                />
              </div>
            </DrawerSection>

            <DrawerSection label="Rule engine">
              <div className="space-y-2 text-[12.5px]">
                <p>
                  <span className="text-muted-foreground">Production: </span>
                  {finalStateMeta(item.production.finalState).label}
                </p>
                {item.diagnostic && (
                  <p>
                    <span className="text-muted-foreground">Diagnostic: </span>
                    {finalStateMeta(item.diagnostic.finalState).label}
                  </p>
                )}
                <p className="font-mono text-[11px] text-muted-foreground">
                  {item.requirementId} · {item.ruleVersionId ?? "no rule version"}
                  {item.ruleVersionStatus ? ` (${item.ruleVersionStatus})` : ""}
                </p>
              </div>
            </DrawerSection>

            {(item.diagnostic?.reasonText ?? item.production.reasonText) && (
              <DrawerSection label="Reason">
                <p className="text-muted-foreground">
                  {item.diagnostic?.reasonText ?? item.production.reasonText}
                </p>
              </DrawerSection>
            )}

            {(item.diagnostic?.missingFactKeys.length ?? 0) > 0 && (
              <DrawerSection label="Additional information required">
                <ul>
                  {item.diagnostic?.missingFactKeys.map((k) => (
                    <li key={k} className="font-mono text-[11px] text-muted-foreground">
                      {k}
                    </li>
                  ))}
                </ul>
              </DrawerSection>
            )}

            <DrawerSection label="Prerequisites">
              <p className="text-[12.5px] text-muted-foreground">
                No verified prerequisite relationships are recorded for this requirement.
              </p>
            </DrawerSection>
          </div>
        )}
      </Drawer>
    </PageShell>
  );
}

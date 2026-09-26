import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useProject } from "@/lib/iris/project-context";
import { PageHeader, PageShell, Drawer, DrawerSection, DataField } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import {
  DecisionProofDrawer,
  type ProofTarget,
} from "@/components/iris/decision-proof-drawer";
import {
  MapLegend,
  RegulatoryMapGraph,
  isVerifiedPrerequisite,
  relationshipMeaning,
} from "@/components/iris/regulatory-map-graph";
import { useDependencyRelationships, useRegulatoryItems } from "@/lib/iris/use-regulatory-items";
import type { MapEdge } from "@/lib/iris/regulatory-map-layout";
import { stageLabel } from "@/lib/iris/regulatory-items";
import {
  LANDSCAPE_FILTERS,
  effectiveState,
  laneFor,
  matchesLandscapeFilter,
  shortTitle,
  type LandscapeFilter,
} from "@/lib/iris/regulatory-landscape";
import { INDUSTRY_LABELS } from "@/lib/iris/types";

export const Route = createFileRoute("/regulatory-map")({
  head: () => ({
    meta: [
      { title: "Regulatory Map — IRIS" },
      {
        name: "description",
        content:
          "The project's regulatory map: requirements evaluated for the project, with verified and diagnostic dependencies between them.",
      },
      { property: "og:title", content: "Regulatory Map — IRIS" },
      {
        property: "og:description",
        content:
          "Project-specific regulatory map. Dependencies are shown only where an authored, labelled relationship exists.",
      },
    ],
  }),
  component: RegulatoryMap,
});

function RegulatoryMap() {
  const { activeProject } = useProject();
  const { items, isLoading, isError } = useRegulatoryItems(activeProject.id);
  const { relationships, isError: relError } = useDependencyRelationships(activeProject.id);

  const [filter, setFilter] = useState<LandscapeFilter>("relevant");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [edge, setEdge] = useState<MapEdge | null>(null);
  const [proof, setProof] = useState<ProofTarget | null>(null);

  const counts = useMemo(() => {
    const c = { applicable: 0, needs: 0, notApplicable: 0, verified: 0 };
    for (const i of items) {
      if (matchesLandscapeFilter(i, "applicable")) c.applicable += 1;
      if (matchesLandscapeFilter(i, "needs")) c.needs += 1;
      if (matchesLandscapeFilter(i, "not-applicable")) c.notApplicable += 1;
      if (i.production.authoritative) c.verified += 1;
    }
    return c;
  }, [items]);

  const visible = useMemo(() => items.filter((i) => matchesLandscapeFilter(i, filter)), [items, filter]);

  const item = selectedId ? items.find((i) => i.requirementId === selectedId) : undefined;
  const view = item ? effectiveState(item) : undefined;

  const openProof = (n: { id: string; item: { production: { authoritative: boolean } } }) =>
    setProof({
      requirementId: n.id,
      evaluationMode: n.item.production.authoritative ? "PRODUCTION" : "NON_PRODUCTION",
    });

  return (
    <PageShell wide className="pb-0">
      <PageHeader
        trail={[{ label: "Regulatory intelligence" }, { label: "Regulatory Map" }]}
        title="Regulatory map"
        description="Requirements evaluated for this project and the dependencies between them · select a node or a dependency for detail"
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
      />

      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 border border-border bg-surface px-4 py-2.5">
        <div role="tablist" aria-label="Requirement filter" className="flex flex-wrap items-center gap-1.5">
          {LANDSCAPE_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={
                filter === f.key
                  ? "rounded-sm border border-primary bg-primary px-3 py-[5px] text-[12px] font-medium text-primary-foreground"
                  : "rounded-sm border border-border px-3 py-[5px] text-[12px] font-medium text-muted-foreground transition-colors hover:bg-secondary"
              }
            >
              {f.label}
            </button>
          ))}
        </div>
        <dl className="ml-auto flex flex-wrap items-center gap-x-6 gap-y-1 text-[12px]">
          {[
            { label: "Applicable", value: counts.applicable },
            { label: "Needs information", value: counts.needs },
            { label: "Not applicable", value: counts.notApplicable },
            { label: "Verified results", value: counts.verified },
          ].map((s) => (
            <div key={s.label} className="flex items-baseline gap-1.5">
              <dt className="text-muted-foreground">{s.label}</dt>
              <dd className="tabular font-semibold">{s.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="mt-3 border border-border bg-surface">
        {visible.length > 0 ? (
          <RegulatoryMapGraph
            project={{
              name: activeProject.name,
              industry: INDUSTRY_LABELS[activeProject.industry],
              location: activeProject.location || "",
            }}
            items={visible}
            relationships={relationships}
            selectedId={selectedId}
            selectedEdgeId={edge?.rel.dependency_id ?? null}
            onSelect={(id) => {
              setEdge(null);
              setSelectedId(id);
            }}
            onSelectEdge={(e) => {
              setSelectedId(null);
              setEdge(e);
            }}
            className="h-[calc(100vh-300px)] min-h-[430px]"
          />
        ) : (
          <div className="flex h-[240px] items-center justify-center px-6 text-center text-[12.5px] text-muted-foreground">
            {isLoading
              ? "Evaluating requirements…"
              : isError
                ? "The rule engine could not be reached."
                : "No requirements match this filter."}
          </div>
        )}
      </div>

      <div className="mt-2.5 space-y-1.5 pb-6">
        <MapLegend />
        <p className="text-[11.5px] text-muted-foreground">
          Project links show what was evaluated, not a dependency. Requirement-to-requirement arrows come
          only from authored relationships; a requirement without one is not thereby shown to be
          independent or parallel.
          {relError ? " Dependency relationships could not be loaded." : ""} Showing {visible.length} of{" "}
          {items.length} requirements · drag to pan.
        </p>
      </div>

      <Drawer
        open={!!item}
        onClose={() => setSelectedId(null)}
        eyebrow="Requirement detail"
        title={item?.title ?? ""}
        subtitle={
          view ? (
            <Tag tone={view.trust === "VERIFIED" ? "success" : "info"}>
              {view.trust === "VERIFIED" ? "Verified" : "Diagnostic"} · {view.label}
            </Tag>
          ) : null
        }
        footer={
          item && (
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono text-[11px] text-muted-foreground">
                {item.requirementId} · {item.ruleVersionId ?? "no rule version"}
              </p>
              <button
                type="button"
                onClick={() =>
                  setProof({
                    requirementId: item.requirementId,
                    evaluationMode: item.production.authoritative ? "PRODUCTION" : "NON_PRODUCTION",
                  })
                }
                className="rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Decision proof
              </button>
            </div>
          )
        }
      >
        {item && view && (
          <div>
            <DrawerSection label="Authority and stage">
              <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
                <DataField label="Regulator" value={item.authorityName} />
                <DataField label="Domain" value={laneFor(item).label} />
                <DataField
                  label="Lifecycle stage"
                  value={item.lifecycleStageIds.map(stageLabel).join(", ") || "—"}
                />
                <DataField label="Rule version" value={item.ruleVersionId ?? "—"} />
              </div>
            </DrawerSection>

            <DrawerSection label="Rule engine">
              <div className="space-y-2 text-[12.5px]">
                <p>
                  <span className="text-muted-foreground">Production: </span>
                  {item.production.authoritative
                    ? `${effectiveState(item).label} (verified)`
                    : "No authoritative result — the governing rule is not yet verified"}
                </p>
                {!item.production.authoritative && item.diagnostic && (
                  <p>
                    <span className="text-muted-foreground">Diagnostic: </span>
                    {view.label}
                    <span className="text-muted-foreground"> (non-authoritative)</span>
                  </p>
                )}
              </div>
            </DrawerSection>

            {(item.diagnostic?.reasonText ?? item.production.reasonText) && (
              <DrawerSection label="Reason">
                <p className="text-muted-foreground">
                  {item.production.authoritative
                    ? item.production.reasonText
                    : (item.diagnostic?.reasonText ?? item.production.reasonText)}
                </p>
              </DrawerSection>
            )}

            {item.presentFactKeys.length > 0 && (
              <DrawerSection label="Facts used">
                <ul>
                  {item.presentFactKeys.map((k) => (
                    <li key={k} className="font-mono text-[11px] text-muted-foreground">
                      {k}
                    </li>
                  ))}
                </ul>
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

            <DrawerSection label="Dependencies">
              {(() => {
                const mine = relationships.filter(
                  (r) =>
                    r.from_requirement_id === item.requirementId || r.to_requirement_id === item.requirementId,
                );
                if (mine.length === 0)
                  return (
                    <p className="text-[12.5px] text-muted-foreground">
                      No authored dependency relationship is recorded for this requirement.
                    </p>
                  );
                return (
                  <ul className="space-y-2 text-[12.5px]">
                    {mine.map((r) => {
                      const outgoing = r.from_requirement_id === item.requirementId;
                      const otherId = outgoing ? r.to_requirement_id : r.from_requirement_id;
                      const other = items.find((x) => x.requirementId === otherId);
                      return (
                        <li key={r.dependency_id}>
                          <span className="font-medium">
                            {isVerifiedPrerequisite(r) ? "Verified prerequisite" : "Diagnostic · requires outcome"}
                          </span>
                          <span className="text-muted-foreground">
                            {" "}
                            · {outgoing ? "→" : "←"} {shortTitle(other?.title ?? otherId)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                );
              })()}
            </DrawerSection>
          </div>
        )}
      </Drawer>

      <Drawer
        open={!!edge}
        onClose={() => setEdge(null)}
        eyebrow="Dependency detail"
        title={edge ? `${shortTitle(edge.from.item.title)} → ${shortTitle(edge.to.item.title)}` : ""}
        subtitle={
          edge ? (
            <Tag tone={isVerifiedPrerequisite(edge.rel) ? "success" : "info"}>
              {isVerifiedPrerequisite(edge.rel) ? "Verified prerequisite" : "Diagnostic · requires outcome"}
            </Tag>
          ) : null
        }
        footer={
          edge && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-[11px] text-muted-foreground">{edge.rel.dependency_id}</p>
              <div className="flex gap-2">
                {[edge.from, edge.to].map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => openProof(n)}
                    className="rounded-sm border border-border px-2.5 py-[6px] text-[12px] font-medium transition-colors hover:bg-secondary"
                  >
                    Decision proof · {n.id}
                  </button>
                ))}
              </div>
            </div>
          )
        }
      >
        {edge && (
          <div>
            <DrawerSection label="Relationship">
              <p className="text-[12.5px]">
                {relationshipMeaning(edge.rel, shortTitle(edge.from.item.title), shortTitle(edge.to.item.title))}
              </p>
            </DrawerSection>
            <DrawerSection label="From / to">
              <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
                <DataField label="From" value={`${edge.from.id} · ${shortTitle(edge.from.item.title)}`} />
                <DataField label="To" value={`${edge.to.id} · ${shortTitle(edge.to.item.title)}`} />
                <DataField label="Type" value={edge.rel.dependency_type} />
                <DataField
                  label="Trust"
                  value={
                    isVerifiedPrerequisite(edge.rel)
                      ? `Verified — human-approved (${edge.rel.verification_ids.join(", ")})`
                      : "Diagnostic — informational, not an executable prerequisite"
                  }
                />
              </div>
            </DrawerSection>
            {edge.rel.description && (
              <DrawerSection label="Why the relationship exists">
                <p className="text-muted-foreground">{edge.rel.description}</p>
              </DrawerSection>
            )}
            {edge.rel.note && (
              <DrawerSection label="Bounded scope">
                <p className="text-muted-foreground">{edge.rel.note}</p>
              </DrawerSection>
            )}
            <DrawerSection label="Provenance">
              <p className="font-mono text-[11px] text-muted-foreground">
                Sources: {edge.rel.source_ids.join(", ") || "—"}
                <br />
                Evidence: {edge.rel.evidence_ids.join(", ") || "—"}
              </p>
            </DrawerSection>
          </div>
        )}
      </Drawer>

      <DecisionProofDrawer projectId={activeProject.id} target={proof} onClose={() => setProof(null)} />
    </PageShell>
  );
}

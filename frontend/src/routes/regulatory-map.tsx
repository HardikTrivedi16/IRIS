import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useProject } from "@/lib/iris/project-context";
import { PageHeader, PageShell, Drawer, DrawerSection, DataField } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import {
  DecisionProofDrawer,
  type ProofTarget,
} from "@/components/iris/decision-proof-drawer";
import { LandscapeLegend, RegulatoryLandscape } from "@/components/iris/regulatory-landscape";
import { useRegulatoryItems } from "@/lib/iris/use-regulatory-items";
import { stageLabel } from "@/lib/iris/regulatory-items";
import {
  LANDSCAPE_FILTERS,
  buildLandscape,
  effectiveState,
  laneFor,
  matchesLandscapeFilter,
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
          "The project's regulatory landscape: requirements grouped by authority and lifecycle stage, with the rule engine's result for each.",
      },
      { property: "og:title", content: "Regulatory Map — IRIS" },
      {
        property: "og:description",
        content:
          "Project-specific regulatory landscape by authority and lifecycle stage. No dependency is inferred.",
      },
    ],
  }),
  component: RegulatoryMap,
});

function RegulatoryMap() {
  const { activeProject } = useProject();
  const { items, isLoading, isError } = useRegulatoryItems(activeProject.id);

  const [filter, setFilter] = useState<LandscapeFilter>("relevant");
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
  const landscape = useMemo(() => buildLandscape(visible), [visible]);

  const item = selectedId ? items.find((i) => i.requirementId === selectedId) : undefined;
  const view = item ? effectiveState(item) : undefined;

  return (
    <PageShell wide className="pb-0">
      <PageHeader
        trail={[{ label: "Regulatory intelligence" }, { label: "Regulatory Map" }]}
        title="Regulatory landscape"
        description="What the regulatory landscape looks like for this project · select a requirement for detail"
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
              { label: "Project", value: activeProject.name },
              { label: "Industry", value: INDUSTRY_LABELS[activeProject.industry] },
              { label: "Location", value: activeProject.location || "—" },
            ].map((s) => (
              <div key={s.label} className="flex items-baseline gap-2">
                <dt className="label-meta">{s.label}</dt>
                <dd className="text-[13px] font-medium">{s.value}</dd>
              </div>
            ))}
          </dl>
        }
      />

      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3 border border-border bg-surface px-4 py-3">
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

      <div className="mt-4 border border-border bg-surface">
        {visible.length > 0 ? (
          <RegulatoryLandscape landscape={landscape} selectedId={selectedId} onSelect={setSelectedId} />
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

      <div className="mt-3 space-y-2 pb-8">
        <LandscapeLegend />
        <p className="text-[11.5px] text-muted-foreground">
          Requirements are grouped by regulatory authority/domain and project lifecycle stage.
          Connections are shown only when verified relationships exist. Showing {visible.length} of{" "}
          {items.length} requirements; a requirement spanning several stages is drawn once, in its
          earliest stage.
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

            <DrawerSection label="Prerequisites">
              <p className="text-[12.5px] text-muted-foreground">
                No verified prerequisite relationships are recorded for this requirement.
              </p>
            </DrawerSection>
          </div>
        )}
      </Drawer>

      <DecisionProofDrawer projectId={activeProject.id} target={proof} onClose={() => setProof(null)} />
    </PageShell>
  );
}

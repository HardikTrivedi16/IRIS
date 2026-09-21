import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { useMemo } from "react";
import { useProject } from "@/lib/iris/project-context";
import { useProjectRequirements } from "@/lib/iris/use-project-data";
import { buildRegulatoryGraph } from "@/lib/iris/derive";
import {
  PageHeader,
  PageShell,
  SectionHeading,
  DataField,
} from "@/components/iris/page";
import { StatusBadge, Tag, StatusDot } from "@/components/iris/status";
import { DependencyGraph } from "@/components/iris/dependency-graph";
import type { GraphNode, ChangeImpactResult } from "@/lib/iris/types";
import { cn } from "@/lib/utils";

// A worked change-impact scenario shown for demonstration. This is an
// illustrative "what if" narrative (not a live engine computation — the Phase 9
// dataset has no verified dependency edges yet), so it is kept here as a local
// constant rather than per-project data.
const changeImpactResult: ChangeImpactResult = {
  requirementsAffected: 2,
  newPathways: 1,
  dependencyChanges: 2,
  affectedRequirements: [
    {
      id: "env-clearance",
      name: "Environmental Clearance",
      authority: "SEIAA",
      status: "new",
      label: "NEW / REVIEW REQUIRED",
    },
    {
      id: "hazardous-waste",
      name: "Additional Hazardous Waste Requirements",
      authority: "MPCB",
      status: "affected",
      label: "AFFECTED",
    },
  ],
  beforePath: ["Project", "CTE", "Construction", "CTO"],
  afterPath: ["Project", "Environmental Review", "CTE", "Construction", "CTO"],
  explanation:
    "Adding API manufacturing introduces active pharmaceutical ingredient processes, which trigger Environmental Clearance requirements under the EIA Notification. This creates a new regulatory pathway before CTE and modifies hazardous waste handling obligations under MPCB rules.",
};

export const Route = createFileRoute("/change-impact")({
  head: () => ({
    meta: [
      { title: "Change Impact Analysis — IRIS" },
      {
        name: "description",
        content:
          "See how a proposed project change affects regulatory requirements, approvals, dependencies, documentation and timeline.",
      },
      { property: "og:title", content: "Change Impact Analysis — IRIS" },
      {
        property: "og:description",
        content:
          "Structured before/after impact assessment for proposed industrial project changes.",
      },
    ],
  }),
  component: ChangeImpact,
});

const changeOptions = [
  {
    id: "api",
    label: "Add API manufacturing",
    detail:
      "Introduce active pharmaceutical ingredient synthesis alongside formulation",
  },
  {
    id: "capacity",
    label: "Increase production capacity by 40%",
    detail: "Higher effluent load and expanded solvent storage",
  },
  {
    id: "solvent",
    label: "Add solvent recovery unit",
    detail: "New hazardous process with additional safety obligations",
  },
];

const impactAreas = [
  {
    area: "Regulatory requirements",
    severity: "blocked" as const,
    level: "High impact",
    findings: [
      "MPCB category may require re-evaluation under revised process classification",
      "Drug Manufacturing Licence scope requires amendment for API processes",
    ],
  },
  {
    area: "Environmental approvals",
    severity: "blocked" as const,
    level: "High impact",
    findings: [
      "Environmental Clearance applicability requires review before Consent to Establish",
      "Consent to Establish conditions likely to be re-issued with revised effluent limits",
    ],
  },
  {
    area: "Documents",
    severity: "attention" as const,
    level: "Medium impact",
    findings: [
      "Additional hazardous-process documentation may apply",
      "Chemical inventory and process flow require revision and re-verification",
    ],
  },
  {
    area: "Dependencies",
    severity: "attention" as const,
    level: "Medium impact",
    findings: [
      "Existing dependency path changes — an environmental review step precedes CTE",
      "Factory Plan Approval gains a prerequisite on the revised process layout",
    ],
  },
  {
    area: "Inspection requirements",
    severity: "attention" as const,
    level: "Medium impact",
    findings: [
      "Additional safety inspection expected before Factory Licence issuance",
    ],
  },
  {
    area: "Project timeline",
    severity: "not-ready" as const,
    level: "Low impact",
    findings: ["Estimated 8–12 weeks added to the pre-establishment stage"],
  },
];

function PathRow({
  label,
  path,
  tone,
}: {
  label: string;
  path: string[];
  tone: "muted" | "active";
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
      <span className="label-meta w-[52px] shrink-0">{label}</span>
      {path.map((step, i) => (
        <span key={`${step}-${i}`} className="flex items-center gap-2">
          {i > 0 && <ArrowRight className="h-3 w-3 text-muted-foreground/60" />}
          <span
            className={cn(
              "rounded-sm border px-2 py-[4px] text-[12px]",
              tone === "active" &&
                !["Project", "CTE", "Construction", "CTO"].includes(step)
                ? "border-info bg-info-surface font-medium text-info"
                : tone === "active"
                  ? "border-border bg-surface"
                  : "border-border bg-surface-sunken text-muted-foreground",
            )}
          >
            {step}
          </span>
        </span>
      ))}
    </div>
  );
}

function ChangeImpact() {
  const { activeProject } = useProject();
  const [change, setChange] = useState(changeOptions[0]!.id);
  const [analysed, setAnalysed] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const { data: reqs = [] } = useProjectRequirements(activeProject.id);
  const { nodes, edges } = useMemo(
    () => buildRegulatoryGraph(reqs, activeProject.name),
    [reqs, activeProject.name],
  );
  const result = changeImpactResult;
  const selectedChange = changeOptions.find((c) => c.id === change)!;

  const impactPath = new Set([
    "project",
    "midc-site",
    "mpcb-cte",
    "building-plan",
    "factory-plan",
    "factory-licence",
    "mpcb-cto",
    "operation-ready",
  ]);

  return (
    <PageShell wide>
      <PageHeader
        trail={[
          { label: "Regulatory intelligence" },
          { label: "Change Impact" },
        ]}
        title="Change Impact Analysis"
        description="Preview how a proposed change affects approvals before you file"
        actions={
          <Link
            to="/regulatory-map"
            className="rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors hover:bg-secondary"
          >
            Open regulatory map
          </Link>
        }
      />

      {/* Change definition */}
      <section className="mt-6 grid border border-border bg-surface lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="border-b border-border px-5 py-5 lg:border-b-0 lg:border-r">
          <div className="label-meta">Current project scope</div>
          <h2 className="mt-1.5 text-[15px] font-semibold">
            {activeProject.name}
          </h2>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            {activeProject.activity}
          </p>
          <div className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
            <DataField
              label="Stage"
              value={
                <span className="capitalize">
                  {activeProject.stage.replace("-", " ")}
                </span>
              }
            />
            <DataField
              label="Location"
              value={`${activeProject.location}, IN`}
            />
            <DataField
              label="Workers"
              value={<span className="tabular">{activeProject.workers}</span>}
            />
            <DataField
              label="Scale"
              value={<span className="capitalize">{activeProject.scale}</span>}
            />
          </div>
        </div>

        <div className="px-5 py-5">
          <div className="label-meta">Proposed change</div>
          <div className="mt-2.5 space-y-1.5">
            {changeOptions.map((opt) => (
              <label
                key={opt.id}
                className={cn(
                  "row-hover flex cursor-pointer items-start gap-3 rounded-sm border px-3 py-2.5",
                  change === opt.id
                    ? "border-info bg-info-surface"
                    : "border-border hover:bg-surface-sunken",
                )}
              >
                <input
                  type="radio"
                  name="change"
                  className="mt-[3px] accent-[var(--info)]"
                  checked={change === opt.id}
                  onChange={() => {
                    setChange(opt.id);
                    setAnalysed(false);
                  }}
                />
                <span>
                  <span className="block text-[13px] font-medium">
                    {opt.label}
                  </span>
                  <span className="mt-0.5 block text-[11.5px] text-muted-foreground">
                    {opt.detail}
                  </span>
                </span>
              </label>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setAnalysed(true)}
            className="mt-4 rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            {analysed ? "Re-run analysis" : "Analyse impact"}
          </button>
        </div>
      </section>

      {!analysed ? (
        <div className="mt-6 border border-dashed border-border bg-surface px-6 py-10">
          <p className="text-[13.5px] font-medium">
            No analysis for the selected change
          </p>
          <p className="mt-1.5 max-w-[54ch] text-[12.5px] leading-relaxed text-muted-foreground">
            Run the analysis to compare the current approval path against the
            path implied by the proposed change.
          </p>
        </div>
      ) : (
        <>
          {/* Change detected banner */}
          <section className="mt-6 border border-warning/30 bg-warning-surface px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3">
              <div>
                <div className="flex items-center gap-2.5">
                  <Tag tone="warning">Change detected</Tag>
                  <span className="text-[13.5px] font-semibold">
                    {selectedChange.label}
                  </span>
                </div>
                <p className="mt-1.5 max-w-[70ch] text-[12.5px] leading-relaxed text-foreground/80">
                  {result.explanation}
                </p>
              </div>
              <dl className="flex gap-x-8">
                {[
                  {
                    label: "Requirements affected",
                    value: result.requirementsAffected,
                  },
                  { label: "New pathways", value: result.newPathways },
                  {
                    label: "Dependency changes",
                    value: result.dependencyChanges,
                  },
                ].map((s) => (
                  <div key={s.label}>
                    <dt className="label-meta">{s.label}</dt>
                    <dd className="tabular mt-1 text-[20px] font-semibold leading-none">
                      {s.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div className="space-y-8">
              {/* Impact areas */}
              <section>
                <SectionHeading
                  title="Affected areas"
                  hint="Structured assessment across the regulatory surfaces IRIS tracks."
                />
                <div className="mt-3 divide-y divide-border border border-border bg-surface">
                  {impactAreas.map((a) => (
                    <div
                      key={a.area}
                      className="row-hover px-5 py-4 hover:bg-surface-sunken"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
                        <h3 className="text-[13.5px] font-medium">{a.area}</h3>
                        <StatusBadge status={a.severity} label={a.level} />
                      </div>
                      <ul className="mt-2 space-y-1.5">
                        {a.findings.map((f) => (
                          <li
                            key={f}
                            className="flex gap-2.5 text-[12.5px] leading-relaxed text-muted-foreground"
                          >
                            <StatusDot
                              status={a.severity}
                              className="mt-[7px]"
                            />
                            <span>{f}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </section>

              {/* Path comparison */}
              <section>
                <SectionHeading
                  title="Approval path comparison"
                  hint="Sequence before and after the proposed change."
                />
                <div className="mt-3 space-y-4 border border-border bg-surface px-5 py-4">
                  <PathRow
                    label="Before"
                    path={result.beforePath}
                    tone="muted"
                  />
                  <div className="border-t border-border" />
                  <PathRow
                    label="After"
                    path={result.afterPath}
                    tone="active"
                  />
                </div>
              </section>

              {/* Affected regulatory path graph */}
              <section>
                <SectionHeading
                  title="Affected regulatory path"
                  hint="Highlighted nodes sit on the path revised by this change."
                  actions={
                    <Link
                      to="/regulatory-map"
                      className="text-[12px] font-medium text-info hover:opacity-80"
                    >
                      Open full map
                    </Link>
                  }
                />
                <div className="mt-3 border border-border">
                  <DependencyGraph
                    nodes={nodes}
                    edges={edges}
                    selectedId={selectedNode?.id ?? null}
                    onSelect={setSelectedNode}
                    highlightPath={impactPath}
                    className="h-[360px]"
                  />
                </div>
              </section>
            </div>

            <div className="space-y-8">
              <section>
                <SectionHeading title="Affected requirements" />
                <ul className="mt-3 divide-y divide-border border border-border bg-surface">
                  {result.affectedRequirements.map((r) => (
                    <li key={r.id} className="px-4 py-3.5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-[13px] font-medium leading-snug">
                            {r.name}
                          </p>
                          <p className="mt-1 text-[11.5px] text-muted-foreground">
                            {r.authority}
                          </p>
                        </div>
                        <Tag tone={r.status === "new" ? "info" : "warning"}>
                          {r.status === "new" ? "New / review" : "Affected"}
                        </Tag>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <section>
                <SectionHeading title="Recommended sequence" />
                <ol className="mt-3 space-y-3 border border-border bg-surface px-4 py-4">
                  {[
                    "Confirm revised process description and chemical inventory with the project team.",
                    "Request MPCB category re-evaluation before submitting the amended CTE application.",
                    "Review Environmental Clearance applicability against the revised process scope.",
                    "Amend the Drug Manufacturing Licence application to cover API operations.",
                  ].map((step, i) => (
                    <li
                      key={step}
                      className="flex gap-3 text-[12.5px] leading-relaxed"
                    >
                      <span className="tabular text-muted-foreground">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="border-t border-border pt-4">
                <Tag>Prototype analysis</Tag>
                <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                  Flags areas for review — not a final regulatory determination.
                </p>
              </section>
            </div>
          </div>
        </>
      )}
    </PageShell>
  );
}

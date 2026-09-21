import { createFileRoute, Link } from "@tanstack/react-router";
import { ShieldCheck } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import { useProjectRequirements } from "@/lib/iris/use-project-data";
import { deriveCompliance } from "@/lib/iris/derive";
import {
  PageHeader,
  PageShell,
  SectionHeading,
  DataField,
  EmptyState,
  StatLine,
} from "@/components/iris/page";
import { StatusDot, Tag } from "@/components/iris/status";
import type { ComplianceItem, Status } from "@/lib/iris/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/compliance")({
  head: () => ({
    meta: [
      { title: "Compliance Oversight — IRIS" },
      {
        name: "description",
        content:
          "Ongoing compliance obligations, active licences and renewal windows for the active industrial project.",
      },
      { property: "og:title", content: "Compliance Oversight — IRIS" },
      {
        property: "og:description",
        content:
          "Track active licences, renewal windows and post-approval obligations.",
      },
    ],
  }),
  component: CompliancePage,
});

const statusMeta: Record<
  ComplianceItem["status"],
  { status: Status; tone: "success" | "warning" }
> = {
  active: { status: "ready", tone: "success" },
  "renewal-due": { status: "attention", tone: "warning" },
  attention: { status: "attention", tone: "warning" },
};

function CompliancePage() {
  const { activeProject } = useProject();
  const { data: reqs = [] } = useProjectRequirements(activeProject.id);
  const items = deriveCompliance(reqs);
  const activeCount = items.filter((i) => i.status === "active").length;
  const dueCount = items.filter((i) => i.status !== "active").length;

  const sorted = [...items].sort((a, b) => {
    if (a.status === "active" && b.status !== "active") return 1;
    if (a.status !== "active" && b.status === "active") return -1;
    return (a.daysRemaining ?? 999) - (b.daysRemaining ?? 999);
  });

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Oversight" }, { label: "Compliance" }]}
        title="Compliance Oversight"
        description={`${activeProject.name} · post-approval obligations`}
        actions={
          <Link
            to="/requirements"
            className="focus-ring rounded-md border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors duration-150 hover:border-border-strong hover:bg-secondary"
          >
            Requirements
          </Link>
        }
        meta={
          <StatLine
            items={[
              { value: activeCount, label: "active", tone: "success" },
              {
                value: dueCount,
                label: "awaiting renewal or review",
                tone: dueCount ? "warning" : "neutral",
              },
            ]}
          />
        }
      />

      {items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No standing obligations yet"
            description="Compliance items appear here once approvals are issued and enter an active or renewal-tracked state."
          />
        </div>
      ) : (
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <section>
            <SectionHeading
              title="Licences & consents"
              hint="Renewal windows are calculated from the last verified issue or renewal date."
            />
            <div className="mt-3 divide-y divide-border border border-border bg-surface">
              {sorted.map((item) => {
                const meta = statusMeta[item.status];
                return (
                  <div
                    key={item.id}
                    className="row-hover px-5 py-4 hover:bg-surface-sunken"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
                      <div className="flex min-w-0 items-start gap-2.5">
                        <ShieldCheck className="mt-[2px] h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0">
                          <h3 className="text-[13.5px] font-medium">
                            {item.name}
                          </h3>
                          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
                            {item.authority}
                          </p>
                        </div>
                      </div>
                      <Tag tone={meta.tone}>{item.label}</Tag>
                    </div>
                    <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 pl-[26px] text-[12px] text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        <StatusDot status={meta.status} />
                        {item.detail}
                      </span>
                      {typeof item.daysRemaining === "number" && (
                        <span
                          className={cn(
                            "tabular font-medium",
                            item.daysRemaining <= 30
                              ? "text-destructive"
                              : "text-warning",
                          )}
                        >
                          {item.daysRemaining} days remaining
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <div className="space-y-8">
            <section>
              <SectionHeading
                title="Renewal calendar"
                hint="Ordered by urgency."
              />
              <ul className="mt-3 divide-y divide-border border border-border bg-surface">
                {sorted
                  .filter((i) => typeof i.daysRemaining === "number")
                  .map((i) => (
                    <li
                      key={i.id}
                      className="flex items-center justify-between gap-3 px-4 py-3"
                    >
                      <DataField label={i.authority} value={i.name} />
                      <span className="tabular text-[13px] font-semibold text-warning">
                        {i.daysRemaining}d
                      </span>
                    </li>
                  ))}
                {sorted.every((i) => typeof i.daysRemaining !== "number") && (
                  <li className="px-4 py-4 text-[12.5px] text-muted-foreground">
                    No renewal windows currently tracked.
                  </li>
                )}
              </ul>
            </section>

            <section className="row-hover border border-border bg-surface px-4 py-4 hover:border-border-strong">
              <div className="flex items-center justify-between gap-3">
                <div className="label-meta">Underlying approvals</div>
                <span className="tabular text-[12px] font-semibold">
                  {reqs.filter((r) => r.status === "ready").length} completed
                </span>
              </div>
              <Link
                to="/requirements"
                className="focus-ring mt-2 inline-flex text-[12px] font-medium text-info hover:opacity-80"
              >
                View requirement register →
              </Link>
            </section>

            <section className="border-t border-border pt-4">
              <Tag>Prototype dataset</Tag>
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                Renewal timing is illustrative — confirm exact windows with the
                issuing authority.
              </p>
            </section>
          </div>
        </div>
      )}
    </PageShell>
  );
}

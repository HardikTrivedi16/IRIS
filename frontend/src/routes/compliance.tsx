import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useProject } from "@/lib/iris/project-context";
import {
  BackendUnavailableError,
  irisApi,
  type RenewalItem,
  type RenewalStatus,
} from "@/lib/iris/api-client";
import {
  PageHeader,
  PageShell,
  SectionHeading,
  EmptyState,
  StatLine,
} from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import type { DecisionTone } from "@/lib/iris/decision-states";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/compliance")({
  head: () => ({
    meta: [
      { title: "Compliance & Renewals — IRIS" },
      {
        name: "description",
        content:
          "Upcoming renewals for the active project, computed only from expiry dates on record.",
      },
    ],
  }),
  component: CompliancePage,
});

const STATUS_META: Record<RenewalStatus, { label: string; tone: DecisionTone }> = {
  EXPIRED: { label: "Expired", tone: "danger" },
  ACTION_REQUIRED: { label: "Action required", tone: "warning" },
  UPCOMING: { label: "Upcoming", tone: "info" },
  COMPLETED: { label: "Completed", tone: "success" },
  NO_EXPIRY_ON_RECORD: { label: "No expiry on record", tone: "neutral" },
};

// Deliberately generic: IRIS does not know statutory renewal procedure, so it
// points to the issuing authority rather than inventing steps.
function actionFor(item: RenewalItem): string {
  if (item.status === "EXPIRED")
    return "Confirm current status and renewal procedure with the issuing authority.";
  if (item.status === "ACTION_REQUIRED")
    return "Check renewal requirements with the issuing authority.";
  return "—";
}

const WINDOWS = [30, 60, 90, 180];

function CompliancePage() {
  const { activeProject } = useProject();
  const [windowDays, setWindowDays] = useState(90);
  const [showUndated, setShowUndated] = useState(false);
  const query = useQuery({
    queryKey: ["renewals", activeProject.id, windowDays],
    queryFn: () => irisApi.getRenewals(activeProject.id, windowDays),
  });

  const data = query.data;
  const dated = (data?.items ?? []).filter((i) => i.status !== "NO_EXPIRY_ON_RECORD");
  const undated = (data?.items ?? []).filter((i) => i.status === "NO_EXPIRY_ON_RECORD");
  const s = data?.summary;

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Oversight" }, { label: "Compliance" }]}
        title="Upcoming Compliance & Renewals"
        description={`${activeProject.name} · computed from expiry dates on record`}
        actions={
          <Link
            to="/documents"
            className="focus-ring rounded-md border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors duration-150 hover:border-border-strong hover:bg-secondary"
          >
            Documents
          </Link>
        }
        meta={
          s ? (
            <StatLine
              items={[
                { value: s.EXPIRED, label: "expired", tone: s.EXPIRED ? "danger" : "neutral" },
                { value: s.ACTION_REQUIRED, label: "action required", tone: s.ACTION_REQUIRED ? "warning" : "neutral" },
                { value: s.UPCOMING, label: "upcoming", tone: "neutral" },
              ]}
            />
          ) : undefined
        }
      />

      <div className="mt-6 flex flex-wrap items-center gap-2 text-[12px]">
        <span className="label-meta">Action window</span>
        {WINDOWS.map((w) => (
          <button
            key={w}
            type="button"
            onClick={() => setWindowDays(w)}
            className={cn(
              "rounded-sm border px-2 py-[3px]",
              w === windowDays
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border text-muted-foreground hover:bg-secondary",
            )}
          >
            {w} days
          </button>
        ))}
        <span className="text-[11px] text-muted-foreground">
          Demo policy for flagging — not a statutory renewal lead time.
        </span>
      </div>

      {query.isLoading ? (
        <p className="mt-6 text-[12.5px] text-muted-foreground">Loading renewals…</p>
      ) : query.isError ? (
        <p className="mt-6 text-[12.5px] text-muted-foreground">
          {query.error instanceof BackendUnavailableError
            ? "The IRIS backend isn't reachable."
            : "Renewals could not be loaded."}
        </p>
      ) : dated.length === 0 && undated.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No expiry dates on record"
            description="Renewals appear once a licence or certificate with a validity date is recorded — for example by confirming a document's 'valid until' field on the Documents page. IRIS never assumes a validity period."
          />
        </div>
      ) : (
        <>
          <section className="mt-6">
            <SectionHeading
              title="Dated licences & certificates"
              hint="Days remaining = expiry date on record − today. Nothing here is estimated."
            />
            {dated.length === 0 ? (
              <p className="mt-3 text-[12.5px] text-muted-foreground">
                None of this project's records carry an expiry date.
              </p>
            ) : (
              <div className="mt-3 overflow-x-auto border border-border bg-surface">
                <table className="w-full min-w-[760px] text-left text-[12.5px]">
                  <thead className="border-b border-border bg-surface-sunken">
                    <tr className="label-meta">
                      <th className="px-4 py-2 font-medium">Record</th>
                      <th className="px-4 py-2 font-medium">Expiry</th>
                      <th className="px-4 py-2 text-right font-medium">Days remaining</th>
                      <th className="px-4 py-2 font-medium">Status</th>
                      <th className="px-4 py-2 font-medium">Source</th>
                      <th className="px-4 py-2 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {dated.map((i) => {
                      const meta = STATUS_META[i.status];
                      return (
                        <tr key={i.record_id} className="align-top">
                          <td className="px-4 py-2.5">
                            <p className="font-medium">{i.title}</p>
                            <p className="mt-0.5 text-[11px] text-muted-foreground">
                              {[i.document_number, i.issuing_authority].filter(Boolean).join(" · ") || "—"}
                            </p>
                          </td>
                          <td className="tabular px-4 py-2.5">{i.expiry_date}</td>
                          <td
                            className={cn(
                              "tabular px-4 py-2.5 text-right font-medium",
                              i.status === "EXPIRED" && "text-destructive",
                              i.status === "ACTION_REQUIRED" && "text-warning",
                            )}
                          >
                            {i.days_remaining}
                          </td>
                          <td className="px-4 py-2.5">
                            <Tag tone={meta.tone}>{meta.label}</Tag>
                          </td>
                          <td className="px-4 py-2.5">
                            {i.is_synthetic ? (
                              <Tag tone="warning">Synthetic demo data</Tag>
                            ) : (
                              <span className="text-[11.5px] text-muted-foreground">{i.source_label}</span>
                            )}
                          </td>
                          <td className="px-4 py-2.5 text-[11.5px] text-muted-foreground">{actionFor(i)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {undated.length > 0 && (
            <section className="mt-6">
              <button
                type="button"
                onClick={() => setShowUndated((v) => !v)}
                className="text-[12px] font-medium text-info hover:opacity-80"
              >
                {showUndated ? "Hide" : "Show"} {undated.length} record{undated.length === 1 ? "" : "s"} with no expiry on record
              </button>
              {showUndated && (
                <ul className="mt-2 divide-y divide-border border border-border bg-surface text-[12.5px]">
                  {undated.map((i) => (
                    <li key={i.record_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                      <span>
                        {i.title}
                        <span className="ml-2 text-[11px] text-muted-foreground">{i.document_number ?? ""}</span>
                      </span>
                      {i.is_synthetic && <Tag tone="warning">Synthetic demo data</Tag>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <ul className="mt-6 space-y-1 border-t border-border pt-4 text-[11px] leading-relaxed text-muted-foreground">
            {data?.notes.map((n, idx) => <li key={idx}>{n}</li>)}
            <li>As of {data?.as_of_date}.</li>
          </ul>
        </>
      )}
    </PageShell>
  );
}

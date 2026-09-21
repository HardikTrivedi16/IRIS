import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageShell, PageHeader, EmptyState } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import { departmentApi } from "@/lib/iris/department-api";
import type { Grievance, GrievanceStatus } from "@/lib/iris/api-client";
import {
  GRIEVANCE_DISCLAIMER,
  GRIEVANCE_STATUS_META,
  SLA_META,
  fmtDateTime,
  stageLabel,
} from "@/lib/iris/grievance-meta";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/department/grievances")({
  head: () => ({ meta: [{ title: "Grievances — IRIS Gov" }] }),
  component: DepartmentGrievancesPage,
});

const FILTERS: (GrievanceStatus | "ALL")[] = ["ALL", "OPEN", "ASSIGNED", "UNDER_REVIEW", "RESOLVED", "CLOSED"];

function GrievanceDetail({ g }: { g: Grievance }) {
  const qc = useQueryClient();
  const [officerId, setOfficerId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["dept-grievance", g.id],
    queryFn: () => departmentApi.getGrievance(g.id),
  });
  const officers = useQuery({
    queryKey: ["dept-users"],
    queryFn: () => departmentApi.listDepartmentUsers(),
    enabled: g.status === "OPEN" || g.status === "ASSIGNED",
  });

  const refresh = async () => {
    setNote("");
    await qc.invalidateQueries({ queryKey: ["dept-grievances"] });
    await qc.invalidateQueries({ queryKey: ["dept-grievance", g.id] });
  };
  const onError = (e: unknown) => setError(e instanceof Error ? e.message.replace(/^HTTP \d+: /, "") : "Action failed.");
  const assign = useMutation({
    mutationFn: () => departmentApi.assignGrievance(g.id, officerId, note || undefined),
    onSuccess: refresh,
    onError,
  });
  const move = useMutation({
    mutationFn: (to: "UNDER_REVIEW" | "RESOLVED" | "CLOSED") =>
      departmentApi.transitionGrievance(g.id, to, note || undefined),
    onSuccess: refresh,
    onError,
  });

  const d = detail.data ?? g;
  const ctx = d.context_snapshot;
  const busy = assign.isPending || move.isPending;
  const btn =
    "focus-ring rounded-sm border border-border px-2.5 py-[5px] text-[12px] font-medium hover:bg-secondary disabled:opacity-40";

  return (
    <div className="border-t border-border bg-surface-sunken px-5 py-4 text-[12.5px]">
      <p className="leading-relaxed">{d.description}</p>

      <p className="label-meta mt-3">Context attached at filing ({fmtDateTime(ctx.captured_at)})</p>
      <dl className="mt-1 grid gap-x-6 gap-y-1 sm:grid-cols-4">
        <div><dt className="text-muted-foreground">Application</dt><dd className="font-mono">{ctx.application_number}</dd></div>
        <div><dt className="text-muted-foreground">Stage then</dt><dd>{stageLabel(ctx.current_stage)}</dd></div>
        <div><dt className="text-muted-foreground">SLA then</dt><dd>{SLA_META[ctx.sla.state ?? ""]?.label ?? "—"}</dd></div>
        <div><dt className="text-muted-foreground">SLA due</dt><dd>{fmtDateTime(ctx.sla.due_at)}</dd></div>
      </dl>
      {ctx.data_classification === "SYNTHETIC_DEMO" && (
        <div className="mt-2"><Tag tone="warning">Synthetic demo application</Tag></div>
      )}

      <p className="label-meta mt-3">History</p>
      <ol className="mt-1 space-y-1">
        {(detail.data?.history ?? []).map((h) => (
          <li key={h.id} className="text-[11.5px]">
            <span className="tabular text-muted-foreground">{fmtDateTime(h.created_at)}</span>{" "}
            {h.from_status ? `${h.from_status} → ` : ""}<span className="font-medium">{h.to_status}</span>
            {h.actor_name ? ` · ${h.actor_name} (${h.actor_role})` : ""}
            {h.note ? ` — ${h.note}` : ""}
          </li>
        ))}
      </ol>

      {d.status !== "CLOSED" && (
        <div className="mt-4 space-y-2 border-t border-border pt-3">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder={d.status === "UNDER_REVIEW" ? "Resolution note (required to resolve)" : "Note (optional)"}
            className="focus-ring w-full rounded-sm border border-border bg-surface px-2 py-1.5 text-[12.5px]"
          />
          <div className="flex flex-wrap items-center gap-2">
            {(d.status === "OPEN" || d.status === "ASSIGNED") && (
              <>
                <select
                  value={officerId}
                  onChange={(e) => setOfficerId(e.target.value)}
                  className="focus-ring rounded-sm border border-border bg-surface px-2 py-[5px] text-[12px]"
                >
                  <option value="">Select officer…</option>
                  {(officers.data ?? [])
                    .filter((o) => o.is_active !== false && o.department_id === d.department_id)
                    .map((o) => (
                      <option key={o.id} value={o.id}>{o.name} · {o.role.replace("DEPARTMENT_", "").toLowerCase()}</option>
                    ))}
                </select>
                <button type="button" className={btn} disabled={!officerId || busy} onClick={() => { setError(null); assign.mutate(); }}>
                  Assign
                </button>
              </>
            )}
            {(d.status === "OPEN" || d.status === "ASSIGNED" || d.status === "RESOLVED") && (
              <button type="button" className={btn} disabled={busy} onClick={() => { setError(null); move.mutate("UNDER_REVIEW"); }}>
                {d.status === "RESOLVED" ? "Reopen for review" : "Start review"}
              </button>
            )}
            {d.status === "UNDER_REVIEW" && (
              <button type="button" className={btn} disabled={busy || note.trim().length < 10} onClick={() => { setError(null); move.mutate("RESOLVED"); }}>
                Resolve
              </button>
            )}
            {d.status === "RESOLVED" && (
              <button type="button" className={btn} disabled={busy} onClick={() => { setError(null); move.mutate("CLOSED"); }}>
                Close
              </button>
            )}
          </div>
          {error && <p className="text-[11.5px] text-destructive">{error}</p>}
        </div>
      )}
    </div>
  );
}

function DepartmentGrievancesPage() {
  const [filter, setFilter] = useState<GrievanceStatus | "ALL">("ALL");
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["dept-grievances", filter],
    queryFn: () => departmentApi.listGrievances(filter === "ALL" ? undefined : filter),
  });

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Department", to: "/department" }, { label: "Grievances" }]}
        title="Applicant Grievances"
        description="Grievances handed off by applicants, with the application context attached at filing."
      />
      <p className="mt-4 max-w-[90ch] border-l-2 border-info pl-3 text-[12px] leading-relaxed text-muted-foreground">
        {GRIEVANCE_DISCLAIMER}
      </p>

      <div className="mt-5 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-sm border px-2 py-[3px] text-[12px]",
              f === filter ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:bg-secondary",
            )}
          >
            {f === "ALL" ? "All" : GRIEVANCE_STATUS_META[f].label}
          </button>
        ))}
      </div>

      {list.isLoading ? (
        <p className="mt-4 text-[12.5px] text-muted-foreground">Loading grievances…</p>
      ) : list.isError ? (
        <p className="mt-4 text-[12.5px] text-muted-foreground">
          Grievances could not be loaded{String(list.error).includes("502") ? " — grievance storage is not provisioned (apply migration 0007)." : "."}
        </p>
      ) : (list.data ?? []).length === 0 ? (
        <div className="mt-4">
          <EmptyState title="No grievances" description="Grievances raised by applicants against this department's applications appear here." />
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-border border border-border bg-surface">
          {(list.data ?? []).map((g) => {
            const meta = GRIEVANCE_STATUS_META[g.status];
            return (
              <li key={g.id}>
                <button
                  type="button"
                  onClick={() => setOpenId(openId === g.id ? null : g.id)}
                  className="flex w-full flex-wrap items-center justify-between gap-2 px-5 py-3 text-left hover:bg-surface-sunken"
                >
                  <div>
                    <p className="text-[13px] font-medium">
                      <span className="font-mono text-[12px]">{g.grievance_number}</span> · {g.category_label}
                    </p>
                    <p className="mt-0.5 text-[11.5px] text-muted-foreground">
                      {g.context_snapshot.application_number} · {g.raised_by_name ?? "Applicant"} · {fmtDateTime(g.created_at)}
                      {g.assigned_officer_name ? ` · ${g.assigned_officer_name}` : " · unassigned"}
                    </p>
                  </div>
                  <Tag tone={meta.tone}>{meta.label}</Tag>
                </button>
                {openId === g.id && <GrievanceDetail g={g} />}
              </li>
            );
          })}
        </ul>
      )}
    </PageShell>
  );
}

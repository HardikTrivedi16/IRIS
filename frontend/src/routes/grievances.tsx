import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useProject } from "@/lib/iris/project-context";
import {
  ApiError,
  BackendUnavailableError,
  GRIEVANCE_CATEGORY_LABEL,
  irisApi,
  type ApplicantApplication,
  type Grievance,
  type GrievanceCategory,
} from "@/lib/iris/api-client";
import { PageHeader, PageShell, SectionHeading, EmptyState } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import {
  GRIEVANCE_DISCLAIMER as DISCLAIMER,
  GRIEVANCE_STATUS_META,
  SLA_META,
  fmtDateTime as fmtDate,
  stageLabel,
} from "@/lib/iris/grievance-meta";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/grievances")({
  head: () => ({
    meta: [
      { title: "Grievances — IRIS" },
      {
        name: "description",
        content:
          "Prepare, hand off and track a grievance about an application, with its stage and SLA context attached.",
      },
    ],
  }),
  component: GrievancesPage,
});

function RaiseForm({
  projectId,
  application,
  onDone,
}: {
  projectId: string;
  application: ApplicantApplication;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [category, setCategory] = useState<GrievanceCategory>(
    application.sla.state === "BREACHED" ? "PROCESSING_DELAY" : "OTHER",
  );
  const [description, setDescription] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () =>
      irisApi.createGrievance(projectId, {
        application_id: application.id,
        category,
        description: description.trim(),
        acknowledge_not_statutory: ack,
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["grievances", projectId] });
      onDone();
    },
    onError: (e) =>
      setError(
        e instanceof BackendUnavailableError
          ? "Backend unreachable — nothing was submitted."
          : e instanceof ApiError && e.status === 502
            ? "Grievance storage isn't provisioned yet on this server."
            : "The grievance could not be submitted.",
      ),
  });

  const sla = SLA_META[application.sla.state ?? ""];
  return (
    <div className="border-t border-border bg-surface-sunken px-5 py-4">
      <p className="label-meta">Context IRIS will attach (from the application record)</p>
      <dl className="mt-1.5 grid gap-x-6 gap-y-1 text-[12px] sm:grid-cols-4">
        <div><dt className="text-muted-foreground">Application</dt><dd className="font-mono">{application.application_id}</dd></div>
        <div><dt className="text-muted-foreground">Stage</dt><dd>{stageLabel(application.current_stage)}</dd></div>
        <div><dt className="text-muted-foreground">SLA</dt><dd>{sla?.label ?? "—"}</dd></div>
        <div><dt className="text-muted-foreground">SLA due</dt><dd>{fmtDate(application.sla.due_at)}</dd></div>
      </dl>
      <div className="mt-3 grid gap-3 sm:grid-cols-[220px_minmax(0,1fr)]">
        <label className="text-[12px] font-medium">
          Category
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as GrievanceCategory)}
            className="focus-ring mt-1 w-full rounded-sm border border-border bg-surface px-2 py-[6px] text-[12.5px] font-normal"
          >
            {(Object.keys(GRIEVANCE_CATEGORY_LABEL) as GrievanceCategory[]).map((c) => (
              <option key={c} value={c}>{GRIEVANCE_CATEGORY_LABEL[c]}</option>
            ))}
          </select>
        </label>
        <label className="text-[12px] font-medium">
          Describe the issue
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            maxLength={4000}
            className="focus-ring mt-1 w-full rounded-sm border border-border bg-surface px-2 py-1.5 text-[12.5px] font-normal"
            placeholder="What happened, and what you need from the department (at least 10 characters)."
          />
        </label>
      </div>
      <label className="mt-3 flex items-start gap-2 text-[12px]">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-[2px]" />
        <span>{DISCLAIMER} I understand this.</span>
      </label>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!ack || description.trim().length < 10 || submit.isPending}
          onClick={() => { setError(null); submit.mutate(); }}
          className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground hover:opacity-90 disabled:opacity-40"
        >
          {submit.isPending ? "Submitting…" : "Submit grievance"}
        </button>
        <button type="button" onClick={onDone} className="text-[12px] text-muted-foreground hover:text-foreground">
          Cancel
        </button>
        {error && <span className="text-[11.5px] text-destructive">{error}</span>}
      </div>
    </div>
  );
}

function GrievanceRow({ g }: { g: Grievance }) {
  const [open, setOpen] = useState(false);
  const meta = GRIEVANCE_STATUS_META[g.status];
  const detail = useQuery({
    queryKey: ["grievance", g.project_id, g.id],
    queryFn: () => irisApi.getGrievance(g.project_id, g.id),
    enabled: open,
  });
  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[13px] font-medium">
            <span className="font-mono text-[12px]">{g.grievance_number}</span> · {g.category_label}
          </p>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            {g.context_snapshot.application_number} · raised {fmtDate(g.created_at)}
            {g.assigned_officer_name ? ` · assigned to ${g.assigned_officer_name}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Tag tone={meta.tone}>{meta.label}</Tag>
          <button type="button" onClick={() => setOpen((v) => !v)} className="text-[12px] font-medium text-info hover:opacity-80">
            {open ? "Hide" : "Track"}
          </button>
        </div>
      </div>
      {open && (
        <div className="mt-2 border-l-2 border-border pl-3 text-[12px]">
          <p className="text-muted-foreground">{g.description}</p>
          {g.resolution_note && <p className="mt-1">Resolution: {g.resolution_note}</p>}
          <p className="mt-2 text-[11px] text-muted-foreground">
            Context at filing: stage {stageLabel(g.context_snapshot.current_stage)}, SLA{" "}
            {SLA_META[g.context_snapshot.sla.state ?? ""]?.label ?? "—"} (captured {fmtDate(g.context_snapshot.captured_at)})
          </p>
          <ol className="mt-2 space-y-1">
            {(detail.data?.history ?? []).map((h) => (
              <li key={h.id} className="text-[11.5px]">
                <span className="tabular text-muted-foreground">{fmtDate(h.created_at)}</span>{" "}
                {h.from_status ? `${h.from_status} → ` : ""}<span className="font-medium">{h.to_status}</span>
                {h.actor_name ? ` · ${h.actor_name}` : ""}
                {h.note ? ` — ${h.note}` : ""}
              </li>
            ))}
          </ol>
        </div>
      )}
    </li>
  );
}

function GrievancesPage() {
  const { activeProject } = useProject();
  const [raising, setRaising] = useState<string | null>(null);
  const apps = useQuery({
    queryKey: ["project-applications", activeProject.id],
    queryFn: () => irisApi.listProjectApplications(activeProject.id),
  });
  const grievances = useQuery({
    queryKey: ["grievances", activeProject.id],
    queryFn: () => irisApi.listGrievances(activeProject.id),
  });

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Oversight" }, { label: "Grievances" }]}
        title="Grievance Preparation & Tracking"
        description={`${activeProject.name} · structured hand-off to the department`}
      />
      <p className="mt-4 max-w-[90ch] border-l-2 border-info pl-3 text-[12px] leading-relaxed text-muted-foreground">
        {DISCLAIMER}
      </p>

      <section className="mt-6">
        <SectionHeading title="Your applications" hint="Stage and SLA timing as recorded by the department." />
        {apps.isLoading ? (
          <p className="mt-3 text-[12.5px] text-muted-foreground">Loading applications…</p>
        ) : apps.isError ? (
          <p className="mt-3 text-[12.5px] text-muted-foreground">Applications could not be loaded.</p>
        ) : (apps.data ?? []).length === 0 ? (
          <div className="mt-3">
            <EmptyState title="No applications on record" description="Grievances attach to an application the department has recorded for this project." />
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-border border border-border bg-surface">
            {(apps.data ?? []).map((a) => {
              const sla = SLA_META[a.sla.state ?? ""];
              return (
                <li key={a.id}>
                  <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
                    <div>
                      <p className="text-[13px] font-medium">{a.title ?? a.requirement_id}</p>
                      <p className="mt-0.5 text-[11.5px] text-muted-foreground">
                        <span className="font-mono">{a.application_id}</span> · {stageLabel(a.current_stage)} · SLA due {fmtDate(a.sla.due_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {a.data_classification === "SYNTHETIC_DEMO" && <Tag tone="warning">Synthetic demo data</Tag>}
                      {sla && <Tag tone={sla.tone}>{sla.label}</Tag>}
                      {a.sla.state !== "COMPLETED" && (
                        <button
                          type="button"
                          onClick={() => setRaising(raising === a.id ? null : a.id)}
                          className={cn(
                            "focus-ring rounded-sm border px-2.5 py-[5px] text-[12px] font-medium",
                            a.sla.state === "BREACHED"
                              ? "border-destructive text-destructive hover:bg-danger-surface"
                              : "border-border hover:bg-secondary",
                          )}
                        >
                          Raise grievance
                        </button>
                      )}
                    </div>
                  </div>
                  {raising === a.id && (
                    <RaiseForm projectId={activeProject.id} application={a} onDone={() => setRaising(null)} />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="mt-8">
        <SectionHeading title="Your grievances" />
        {(grievances.data ?? []).length === 0 ? (
          <p className="mt-3 text-[12.5px] text-muted-foreground">
            {grievances.isError ? "Grievances could not be loaded." : "No grievances raised for this project."}
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-border border border-border bg-surface">
            {(grievances.data ?? []).map((g) => <GrievanceRow key={g.id} g={g} />)}
          </ul>
        )}
      </section>
    </PageShell>
  );
}

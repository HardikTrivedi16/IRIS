import { useQuery } from "@tanstack/react-query";
import { departmentApi, type SlaExplanation } from "@/lib/iris/department-api";
import { Tag } from "@/components/iris/status";

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function h(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v >= 48 ? `${v} h (${(v / 24).toFixed(1)} d)` : `${v} h`;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-[150px] shrink-0 text-muted-foreground">{label}</dt>
      <dd className="tabular">{value}</dd>
    </div>
  );
}

/** "Why this SLA status?" — every value comes from the backend's single
 * authoritative SLA calculation over the application's recorded timestamps. */
export function SlaExplanationPanel({ appId }: { appId: string }) {
  const q = useQuery({
    queryKey: ["sla-explanation", appId],
    queryFn: () => departmentApi.getSlaExplanation(appId),
  });
  if (q.isLoading) return <p className="text-[12px] text-muted-foreground">Loading explanation…</p>;
  if (q.isError || !q.data) return <p className="text-[12px] text-muted-foreground">Explanation unavailable.</p>;
  const e: SlaExplanation = q.data;
  return (
    <div className="grid gap-6 text-[12px] md:grid-cols-2">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <p className="label-meta">Why {e.state.replace(/_/g, " ").toLowerCase()}?</p>
          {e.is_synthetic && <Tag tone="warning">Synthetic demo data</Tag>}
        </div>
        <p className="mt-1 leading-relaxed">{e.reason}</p>
        <dl className="mt-2 space-y-1">
          <Row label="Clock started" value={fmt(e.clock.started_at)} />
          <Row label="Evaluated at" value={fmt(e.clock.evaluated_at)} />
          <Row label="Elapsed" value={h(e.clock.elapsed_hours)} />
          <Row label="Warning point" value={fmt(e.clock.warning_at)} />
          <Row label="Due" value={fmt(e.clock.due_at)} />
          {e.clock.remaining_hours !== null && <Row label="Remaining" value={h(e.clock.remaining_hours)} />}
          {e.clock.overdue_hours !== null && (
            <Row label="Overdue by" value={<span className="text-destructive">{h(e.clock.overdue_hours)}</span>} />
          )}
        </dl>
      </div>
      <div>
        <p className="label-meta">Policy & current stage</p>
        <dl className="mt-1 space-y-1">
          <Row label="Policy" value={e.policy ? `${e.policy.name} — ${h(e.policy.duration_hours)}, warning at ${Math.round((e.policy.warning_pct ?? 0) * 100)}%` : "None attached"} />
          <Row label="Current stage" value={e.stage.current_stage?.replace(/_/g, " ") ?? "—"} />
          <Row label="Stage entered" value={fmt(e.stage.entered_at)} />
          <Row label="Time in stage" value={h(e.stage.hours_in_stage)} />
          <Row label="Stage target" value={e.stage.target_hours ? `${h(e.stage.target_hours)} (${e.stage.status ?? "—"})` : "No stage target"} />
        </dl>
        <ul className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
          {e.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      </div>
    </div>
  );
}

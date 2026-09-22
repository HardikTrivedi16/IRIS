/**
 * Presentation pieces shared between the Documents-page embedded
 * PreSubmissionCheck (pre-submission-check.tsx) and the standalone Evidence
 * Consistency page (routes/consistency.tsx). Nothing here calls the API or
 * decides a status — every value rendered comes verbatim from the existing
 * POST /projects/{id}/consistency-check response (backend/app/consistency.py).
 */
import { useState } from "react";
import type { ConsistencyCheck, ConsistencyField, ConsistencyObservationInput } from "@/lib/iris/api-client";
import { Tag } from "@/components/iris/status";
import { BASIS_LABEL, FIELD_OPTIONS, fmt, STATUS_META, type CheckSource } from "@/lib/iris/consistency";

export function ObservationBlock({
  heading,
  obs,
}: {
  heading: string;
  obs: ConsistencyCheck["reference"];
}) {
  if (!obs) return null;
  const src = obs.source;
  return (
    <div className="min-w-0">
      <p className="label-meta">{heading}</p>
      <p className="mt-0.5 break-words text-[13px] font-medium">{fmt(obs.raw_value, obs.unit)}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {src.kind === "PROJECT_RECORD"
          ? `Confirmed project record (${src.fact_key ?? "document.*"})`
          : `${src.document_name ?? "Unnamed source"}${src.page ? ` · p.${src.page}` : ""}`}
        {typeof obs.confidence === "number" && ` · ${(obs.confidence * 100).toFixed(0)}% extraction confidence`}
      </p>
      {src.evidence_text && (
        <p className="mt-1 text-[11px] italic text-muted-foreground">Evidence: "{src.evidence_text}"</p>
      )}
    </div>
  );
}

/** One finding: field/concept, status, reference vs candidate evidence side
 * by side (with document/page/evidence-text/confidence where the engine
 * supplied it — nothing fabricated when a field is absent), and the plain
 * deterministic explanation the engine itself produced. */
export function IssueCard({ check }: { check: ConsistencyCheck }) {
  const meta = STATUS_META[check.status];
  const isLowConfidence = check.status === "LOW_CONFIDENCE";
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.05em]">
          {check.field_label} — {meta.label}
        </h4>
        <div className="flex items-center gap-1.5">
          <Tag tone={meta.tone}>{meta.label}</Tag>
          {check.human_review_required && <Tag tone="neutral">Human review required</Tag>}
        </div>
      </div>
      <div className="mt-2.5 grid gap-4 sm:grid-cols-2">
        <ObservationBlock
          heading={check.reference_basis ? BASIS_LABEL[check.reference_basis] ?? "Reference" : "Reference"}
          obs={check.reference}
        />
        <ObservationBlock heading={check.reference ? "Compared with" : "Source"} obs={check.candidate} />
      </div>
      <p className="mt-2 text-[12px]">
        {check.message}
        {typeof check.days_remaining === "number" && check.status !== "EXPIRED" &&
          ` (${check.days_remaining} days remaining)`}
      </p>
      {isLowConfidence && (
        <p className="mt-1 text-[11.5px] font-medium text-warning">
          Extraction requires human verification — this is not presented as a conflict.
        </p>
      )}
      <p className="mt-1 text-[11px] text-muted-foreground">Rule: {check.comparison_rule}</p>
    </li>
  );
}

export function ManualEntry({ onAdd }: { onAdd: (source: CheckSource) => void }) {
  const [field, setField] = useState<ConsistencyField>("batch_number");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const needsUnit = FIELD_OPTIONS.find((f) => f.value === field)?.needsUnit;
  const input =
    "focus-ring w-full rounded-sm border border-border bg-surface px-2 py-[6px] text-[12.5px]";

  function add() {
    if (!name.trim()) return setError("Name the source this value comes from.");
    if (!value.trim()) return setError("Enter the value exactly as it appears.");
    setError(null);
    const obs: ConsistencyObservationInput = {
      field,
      value: value.trim(),
      source: { kind: "MANUAL", document_name: name.trim() },
    };
    if (needsUnit && unit.trim()) obs.unit = unit.trim();
    onAdd({
      id: `manual-${Date.now()}`,
      name: name.trim(),
      kind: "MANUAL",
      observations: [obs],
    });
    setValue("");
    setUnit("");
  }

  return (
    <div className="border-t border-border px-5 py-3">
      <p className="label-meta">Add a value manually</p>
      <div className="mt-2 grid gap-2 sm:grid-cols-[1.2fr_1fr_1fr_80px_auto]">
        <select value={field} onChange={(e) => setField(e.target.value as ConsistencyField)} className={input}>
          {FIELD_OPTIONS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <input value={value} onChange={(e) => setValue(e.target.value)} className={input}
          placeholder="Value as written" />
        <input value={name} onChange={(e) => setName(e.target.value)} className={input}
          placeholder="Source (e.g. Product label)" />
        <input value={unit} onChange={(e) => setUnit(e.target.value)} className={input}
          placeholder="Unit" disabled={!needsUnit} />
        <button type="button" onClick={add}
          className="focus-ring rounded-sm border border-border px-3 py-[6px] text-[12.5px] font-medium hover:bg-secondary">
          Add
        </button>
      </div>
      {error && <p className="mt-1 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}

/** The permanent core-principle statement: a factual conflict is never
 * presented as a legal conclusion. Shown identically wherever a consistency
 * result is rendered — this is product-principle copy, not fine print. */
export function ConsistencySafetyNote({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={
        compact
          ? "border-l-2 border-info pl-3 text-[11.5px] leading-relaxed text-muted-foreground"
          : "border border-info/30 bg-info-surface px-4 py-3 text-[12.5px] leading-relaxed"
      }
    >
      <p className="font-medium text-foreground">
        Evidence inconsistency does not automatically mean regulatory non-compliance.
      </p>
      <p className="mt-1 text-muted-foreground">
        IRIS compares evidence objectively. Legal significance requires
        verified regulatory grounding and, where necessary, human review.
      </p>
    </div>
  );
}

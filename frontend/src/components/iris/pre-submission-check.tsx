import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type ConsistencyCheck,
  type ConsistencyField,
  type ConsistencyObservationInput,
  type ConsistencyResult,
  type ConsistencyStatus,
  type ExtractedDocumentFields,
} from "@/lib/iris/api-client";
import { Tag } from "@/components/iris/status";
import type { DecisionTone } from "@/lib/iris/decision-states";

/** A document (or manual entry) whose values were added to this session's
 * check set. Session-only: never persisted. */
export interface CheckSource {
  id: string;
  name: string;
  kind: "DOCUMENT" | "MANUAL";
  observations: ConsistencyObservationInput[];
}

const STATUS_META: Record<ConsistencyStatus, { label: string; tone: DecisionTone }> = {
  CONFLICT: { label: "Conflict", tone: "danger" },
  EXPIRED: { label: "Expired", tone: "danger" },
  MISSING: { label: "Missing", tone: "warning" },
  REVIEW_REQUIRED: { label: "Review required", tone: "warning" },
  LOW_CONFIDENCE: { label: "Low confidence", tone: "warning" },
  NOT_COMPARABLE: { label: "Not comparable", tone: "neutral" },
  CONSISTENT: { label: "Consistent", tone: "success" },
};

const FIELD_OPTIONS: { value: ConsistencyField; label: string; needsUnit?: boolean }[] = [
  { value: "entity_name", label: "Entity / business name" },
  { value: "address", label: "Premises address" },
  { value: "registration_number", label: "Registration / licence number" },
  { value: "batch_number", label: "Batch number" },
  { value: "net_quantity", label: "Net quantity / pack size", needsUnit: true },
  { value: "production_capacity", label: "Production capacity", needsUnit: true },
  { value: "valid_until", label: "Validity end date (YYYY-MM-DD)" },
];

const BASIS_LABEL: Record<string, string> = {
  PROJECT_RECORD: "Project record",
  EXPLICIT_REFERENCE: "Reference document",
  FIRST_SUBMITTED: "First source",
};

/**
 * Maps the existing AI extractor's output onto consistency observations.
 * Only same-meaning fields are mapped; each keeps the extractor's own
 * confidence, evidence span and source page. The extractor does not produce
 * batch numbers or pack sizes — those can be entered manually.
 */
export function observationsFromExtraction(
  data: ExtractedDocumentFields,
  documentName: string,
  documentId: string,
): ConsistencyObservationInput[] {
  const map: [keyof ExtractedDocumentFields, ConsistencyField][] = [
    ["business_name", "entity_name"],
    ["location", "address"],
    ["registration_number", "registration_number"],
    ["valid_until", "valid_until"],
  ];
  const source = (key: string): ConsistencyObservationInput["source"] => {
    const s: ConsistencyObservationInput["source"] = {
      kind: "DOCUMENT",
      document_id: documentId,
      document_name: documentName,
    };
    const page = data.field_source_pages[key];
    const evidence = data.field_evidence[key];
    if (typeof page === "number" && page >= 1) s.page = page;
    if (evidence) s.evidence_text = evidence;
    return s;
  };
  const out: ConsistencyObservationInput[] = [];
  for (const [key, field] of map) {
    const value = data[key];
    if (typeof value !== "string" || !value.trim()) continue;
    const obs: ConsistencyObservationInput = { field, value, source: source(key) };
    const conf = data.field_confidence[key];
    if (typeof conf === "number") obs.confidence = conf;
    out.push(obs);
  }
  if (typeof data.capacity_value === "number" && data.capacity_unit) {
    const obs: ConsistencyObservationInput = {
      field: "production_capacity",
      value: data.capacity_value,
      unit: data.capacity_unit,
      source: source("capacity_value"),
    };
    const conf = data.field_confidence["capacity_value"];
    if (typeof conf === "number") obs.confidence = conf;
    out.push(obs);
  }
  return out;
}

function fmt(v: unknown, unit?: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  return unit ? `${String(v)} ${unit}` : String(v);
}

function ObservationBlock({
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

function IssueCard({ check }: { check: ConsistencyCheck }) {
  const meta = STATUS_META[check.status];
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
      <p className="mt-1 text-[11px] text-muted-foreground">Rule: {check.comparison_rule}</p>
    </li>
  );
}

function ManualEntry({ onAdd }: { onAdd: (source: CheckSource) => void }) {
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

/**
 * PRE-SUBMISSION CHECK — "What does not match before I file?"
 *
 * Compares values from the project's confirmed record and the documents
 * added in this session. The comparison is deterministic and server-side;
 * nothing is saved and no Project Fact is changed.
 */
export function PreSubmissionCheck({
  projectId,
  sources,
  onRemoveSource,
  onAddSource,
}: {
  projectId: string;
  sources: CheckSource[];
  onRemoveSource: (id: string) => void;
  onAddSource: (source: CheckSource) => void;
}) {
  const [result, setResult] = useState<ConsistencyResult | null>(null);
  const [showConsistent, setShowConsistent] = useState(false);

  const run = useMutation({
    mutationFn: () =>
      irisApi.runConsistencyCheck(projectId, {
        observations: sources.flatMap((s) => s.observations),
      }),
    onSuccess: setResult,
  });

  const issues = result?.checks.filter((c) => c.status !== "CONSISTENT") ?? [];
  const consistent = result?.checks.filter((c) => c.status === "CONSISTENT") ?? [];

  return (
    <div className="border border-border bg-surface">
      <div className="border-b border-border px-5 py-3">
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          Compares the same fact across your confirmed project record and the
          documents you add here — names, addresses, identifiers, batches,
          quantities and validity dates. This is an objective data check, not
          a compliance decision. Sources added here are kept for this session
          only; nothing is saved and no Project Fact is changed.
        </p>
      </div>

      <div className="px-5 py-3">
        <p className="label-meta">Sources in this check ({sources.length})</p>
        {sources.length === 0 ? (
          <p className="mt-1 text-[12px] text-muted-foreground">
            Extract a document below and choose “Add to pre-submission check”,
            or add a value manually. The project's confirmed record is always included.
          </p>
        ) : (
          <ul className="mt-1.5 divide-y divide-border">
            {sources.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 py-1.5 text-[12.5px]">
                <span>
                  {s.name}{" "}
                  <span className="text-[11px] text-muted-foreground">
                    · {s.kind === "MANUAL" ? "manual entry" : "extracted"} ·{" "}
                    {s.observations.map((o) => o.field.replace(/_/g, " ")).join(", ") || "no comparable fields"}
                  </span>
                </span>
                <button type="button" onClick={() => onRemoveSource(s.id)}
                  className="text-[11.5px] text-muted-foreground hover:text-foreground">
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ManualEntry onAdd={onAddSource} />

      <div className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-3">
        <button type="button" onClick={() => run.mutate()} disabled={run.isPending}
          className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40">
          {run.isPending ? "Checking…" : "Run pre-submission check"}
        </button>
        {run.isError && (
          <span className="text-[11.5px] text-destructive">
            {run.error instanceof BackendUnavailableError
              ? "Backend unreachable."
              : run.error instanceof ApiError && run.error.status === 422
                ? "Some values were rejected — check fields and units."
                : "The check could not be run."}
          </span>
        )}
      </div>

      {result && (
        <div className="border-t border-border">
          <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2 px-5 py-3">
            <div>
              <span className="tabular text-[20px] font-semibold">{result.checks_performed}</span>{" "}
              <span className="text-[12px] text-muted-foreground">checks performed</span>
            </div>
            <div>
              <span className="tabular text-[20px] font-semibold">{result.issues_found}</span>{" "}
              <span className="text-[12px] text-muted-foreground">issues found</span>
            </div>
            <span className="text-[11px] text-muted-foreground">As of {result.as_of_date}</span>
          </div>

          {issues.length > 0 ? (
            <ul className="divide-y divide-border border-t border-border">
              {issues.map((c) => (
                <IssueCard key={c.check_id} check={c} />
              ))}
            </ul>
          ) : (
            <p className="border-t border-border px-5 py-3 text-[12.5px] text-muted-foreground">
              No issues among the values compared.
            </p>
          )}

          {consistent.length > 0 && (
            <div className="border-t border-border px-5 py-2.5">
              <button type="button" onClick={() => setShowConsistent((v) => !v)}
                className="text-[12px] font-medium text-info hover:opacity-80">
                {showConsistent ? "Hide" : "Show"} {consistent.length} consistent check{consistent.length === 1 ? "" : "s"}
              </button>
              {showConsistent && (
                <ul className="mt-2 divide-y divide-border">
                  {consistent.map((c) => (
                    <IssueCard key={c.check_id} check={c} />
                  ))}
                </ul>
              )}
            </div>
          )}

          {result.uncompared_fields.length > 0 && (
            <div className="border-t border-border px-5 py-2.5 text-[11.5px] text-muted-foreground">
              Not compared:{" "}
              {result.uncompared_fields.map((u) => u.field_label).join(", ")} — only one source states each.
            </div>
          )}
          <p className="border-t border-border px-5 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
            {result.policy.note}
          </p>
        </div>
      )}
    </div>
  );
}

import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type ChangeImpactCategory,
  type ChangeImpactRequirement,
  type ChangeImpactResponse,
  type ChangeImpactSide,
  type FactRegistryEntry,
} from "@/lib/iris/api-client";
import { PageHeader, PageShell, SectionHeading } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import { finalStateMeta } from "@/lib/iris/decision-states";
import {
  FACT_UNKNOWN,
  factLabel,
  fieldErrorsFromDetail,
  formatFactValue,
  parseFactInput,
  useFactRegistry,
  useProjectFacts,
} from "@/lib/iris/facts";
import {
  DecisionProofDrawer,
  type ProofTarget,
} from "@/components/iris/decision-proof-drawer";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/change-impact")({
  head: () => ({
    meta: [
      { title: "Change Impact Analysis — IRIS" },
      {
        name: "description",
        content:
          "Re-evaluate the deterministic rule engine against a proposed change to this project's facts, and compare the result with the current one.",
      },
      { property: "og:title", content: "Change Impact Analysis — IRIS" },
      {
        property: "og:description",
        content:
          "Deterministic before/after regulatory comparison for a proposed project change.",
      },
    ],
  }),
  component: ChangeImpact,
});

// ---------------------------------------------------------------------------
// Presentation metadata. These describe ENGINE STATE TRANSITIONS reported by
// the backend — not legal consequences. No requirement, threshold, pathway or
// narrative is authored here; everything rendered below comes from the
// /change-impact response.
// ---------------------------------------------------------------------------

const CATEGORY_META: Record<
  ChangeImpactCategory,
  { label: string; tone: "success" | "warning" | "danger" | "info" | "neutral" }
> = {
  NEWLY_APPLICABLE: { label: "Newly applicable", tone: "info" },
  NO_LONGER_APPLICABLE: { label: "No longer applicable", tone: "success" },
  REQUIRES_REVIEW: { label: "Requires review", tone: "warning" },
  REQUIRES_INFORMATION: { label: "Requires information", tone: "warning" },
  CHANGED: { label: "Changed", tone: "warning" },
  UNCHANGED: { label: "Unchanged", tone: "neutral" },
};

function stateLabel(state: string): string {
  return finalStateMeta(state).label;
}

const formatValue = formatFactValue;

// ---------------------------------------------------------------------------

/** One editable proposed value per supported fact. Empty string means "leave
 * this fact untouched" — it is not sent to the backend at all. */
type DraftValues = Record<string, string>;

function parseDraft(entry: FactRegistryEntry, raw: string) {
  // "Clear" in this editor means "set back to unknown" — same as the shared
  // FACT_UNKNOWN sentinel the intake form uses.
  return parseFactInput(entry, raw === "__CLEAR__" ? FACT_UNKNOWN : raw);
}

function FactInput({
  entry,
  currentValue,
  value,
  onChange,
}: {
  entry: FactRegistryEntry;
  currentValue: unknown;
  value: string;
  onChange: (next: string) => void;
}) {
  const unit = entry.units[0];
  const referenced = entry.values_referenced_by_rules;

  return (
    <div className="grid gap-x-6 gap-y-2 border-b border-border px-5 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_200px]">
      <div>
        <p className="text-[13px] font-medium capitalize">
          {factLabel(entry.key)}
        </p>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
          {entry.key}
          {unit ? ` · ${unit}` : ""}
        </p>
        <p className="mt-1 text-[11.5px] text-muted-foreground">
          Current: <span className="tabular">{formatValue(currentValue)}</span>
          {referenced.length > 0 && (
            <>
              {" · "}
              Values referenced by rules:{" "}
              <span className="tabular">
                {referenced.map((v) => formatValue(v)).join(", ")}
              </span>
            </>
          )}
        </p>
      </div>

      <div className="flex items-start">
        {entry.value_type === "boolean" ? (
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="focus-ring w-full rounded-sm border border-border bg-surface px-2 py-[7px] text-[12.5px]"
          >
            <option value="">No change</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
            <option value="__CLEAR__">Clear (unknown)</option>
          </select>
        ) : entry.value_type === "number" ? (
          <input
            type="number"
            value={value === "__CLEAR__" ? "" : value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="No change"
            className="focus-ring w-full rounded-sm border border-border bg-surface px-2 py-[7px] text-[12.5px] tabular"
          />
        ) : (
          <input
            type="text"
            value={value === "__CLEAR__" ? "" : value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="No change"
            className="focus-ring w-full rounded-sm border border-border bg-surface px-2 py-[7px] text-[12.5px]"
          />
        )}
      </div>
    </div>
  );
}

function SideColumn({
  label,
  side,
  tone,
}: {
  label: string;
  side: ChangeImpactSide;
  tone: "muted" | "active";
}) {
  return (
    <div
      className={cn(
        "px-4 py-3",
        tone === "muted" ? "bg-surface-sunken" : "bg-surface",
      )}
    >
      <div className="label-meta">{label}</div>
      <p className="mt-1 text-[13px] font-medium">
        {stateLabel(side.final_state)}
      </p>
      {side.reason_text && (
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
          {side.reason_text}
        </p>
      )}
      {side.missing_project_fact_keys.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {side.missing_project_fact_keys.map((k) => (
            <li key={k} className="font-mono text-[11px] text-warning">
              missing: {k}
            </li>
          ))}
        </ul>
      )}
      {side.classification && (
        <div className="mt-2 border-t border-border/60 pt-2">
          <span className="label-meta">Classification sub-rules</span>
          <p className="mt-0.5 text-[11.5px]">
            {side.classification.combined_state ?? "—"}
          </p>
          <ul className="mt-0.5 space-y-0.5">
            {Object.entries(side.classification.rule_results).map(
              ([ruleId, state]) => (
                <li
                  key={ruleId}
                  className="font-mono text-[10.5px] text-muted-foreground"
                >
                  {ruleId}: {state}
                </li>
              ),
            )}
          </ul>
        </div>
      )}

      <p className="mt-2 font-mono text-[10.5px] text-muted-foreground/80">
        {side.rule_version_id ?? "no rule version"}
        {side.rule_version_status ? ` · ${side.rule_version_status}` : ""}
      </p>
    </div>
  );
}

function RequirementDiff({
  req,
  onProof,
}: {
  req: ChangeImpactRequirement;
  onProof: (requirementId: string, side: "current" | "proposed") => void;
}) {
  const meta = CATEGORY_META[req.category];
  return (
    <div className="border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border px-4 py-3">
        <div>
          <h3 className="text-[13.5px] font-medium">{req.requirement_title}</h3>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            {req.requirement_id}
            {req.authority_id ? ` · ${req.authority_id}` : ""}
          </p>
        </div>
        <Tag tone={meta.tone}>{meta.label}</Tag>
      </div>

      <div className="grid sm:grid-cols-[minmax(0,1fr)_28px_minmax(0,1fr)]">
        <SideColumn label="Current" side={req.before} tone="muted" />
        <div className="hidden items-center justify-center sm:flex">
          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground/60" />
        </div>
        <SideColumn label="Proposed" side={req.after} tone="active" />
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-2">
        <button
          type="button"
          onClick={() => onProof(req.requirement_id, "current")}
          className="text-[12px] font-medium text-info hover:opacity-80"
        >
          Decision proof — current →
        </button>
        <button
          type="button"
          onClick={() => onProof(req.requirement_id, "proposed")}
          className="text-[12px] font-medium text-info hover:opacity-80"
        >
          Decision proof — proposed →
        </button>
      </div>

      {req.changed_facts_used_by_this_requirement.length > 0 && (
        <div className="border-t border-border px-4 py-2.5">
          <span className="label-meta">Changed facts this rule reads</span>
          <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
            {req.changed_facts_used_by_this_requirement.map((k) => (
              <li key={k} className="font-mono text-[11px] text-info">
                {k}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ChangeImpact() {
  const { activeProject } = useProject();
  const [draft, setDraft] = useState<DraftValues>({});
  const [showUnchanged, setShowUnchanged] = useState(false);
  const [diagnostic, setDiagnostic] = useState(false);
  const [result, setResult] = useState<ChangeImpactResponse | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [proof, setProof] = useState<ProofTarget | null>(null);

  function openProof(requirementId: string, side: "current" | "proposed") {
    if (!result) return;
    const target: ProofTarget = {
      requirementId,
      evaluationMode: result.evaluation_mode,
    };
    if (side === "proposed") {
      // Exactly the effective changes the diff used — proven as hypothetical,
      // never saved.
      target.hypotheticalFacts = Object.fromEntries(
        result.proposed_changes.map((c) => [c.key, c.proposed_value]),
      );
    }
    setProof(target);
  }

  const registryQuery = useFactRegistry();
  const factsQuery = useProjectFacts(activeProject.id);

  const currentFacts = factsQuery.data?.facts ?? {};

  const supported = useMemo(
    () => (registryQuery.data?.facts ?? []).filter((f) => f.typed_input_supported),
    [registryQuery.data],
  );

  const mutation = useMutation({
    mutationFn: (proposedFacts: Record<string, unknown>) =>
      irisApi.analyseChangeImpact(activeProject.id, {
        proposedFacts,
        evaluationMode: diagnostic ? "NON_PRODUCTION" : "PRODUCTION",
      }),
    onSuccess: (data) => {
      setResult(data);
      setFieldErrors({});
    },
    onError: (error) => {
      setResult(null);
      if (error instanceof ApiError && error.status === 422) {
        // The backend reports every bad field at once.
        setFieldErrors(fieldErrorsFromDetail(error.detail));
      }
    },
  });

  function analyse() {
    const proposed: Record<string, unknown> = {};
    const errors: Record<string, string> = {};
    for (const entry of supported) {
      const raw = draft[entry.key];
      if (raw === undefined || raw === "") continue;
      const parsed = parseDraft(entry, raw);
      if (parsed.ok) proposed[entry.key] = parsed.value;
      else errors[entry.key] = parsed.message;
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setResult(null);
      return;
    }
    setFieldErrors({});
    mutation.mutate(proposed);
  }

  const changed = (result?.requirements ?? []).filter(
    (r) => r.category !== "UNCHANGED",
  );
  const unchanged = (result?.requirements ?? []).filter(
    (r) => r.category === "UNCHANGED",
  );

  return (
    <PageShell wide>
      <PageHeader
        trail={[
          { label: "Regulatory intelligence" },
          { label: "Change Impact" },
        ]}
        title="Change Impact Analysis"
        description={`Re-evaluate ${activeProject.name} against a proposed change to its project facts`}
      />

      <section className="mt-6 border border-border bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border px-5 py-3">
          <div>
            <h2 className="text-[13.5px] font-semibold">Proposed change</h2>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              Only facts the current regulatory dataset's rules actually read
              are listed. Leave a field blank to keep its current value.
            </p>
          </div>
          <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <input
              type="checkbox"
              checked={diagnostic}
              onChange={(e) => setDiagnostic(e.target.checked)}
              className="accent-[var(--info)]"
            />
            Diagnostic (non-production) mode
          </label>
        </div>

        {registryQuery.isLoading || factsQuery.isLoading ? (
          <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
            Loading the supported project facts…
          </p>
        ) : registryQuery.isError || factsQuery.isError ? (
          <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
            {registryQuery.error instanceof BackendUnavailableError ||
            factsQuery.error instanceof BackendUnavailableError
              ? "The IRIS backend isn't reachable, so a change cannot be analysed right now."
              : "The supported project facts could not be loaded."}
          </p>
        ) : supported.length === 0 ? (
          <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
            The regulatory dataset declares no typed project facts, so there is
            nothing to vary.
          </p>
        ) : (
          <>
            {supported.map((entry) => (
              <div key={entry.key}>
                <FactInput
                  entry={entry}
                  currentValue={currentFacts[entry.key]}
                  value={draft[entry.key] ?? ""}
                  onChange={(next) =>
                    setDraft((prev) => ({ ...prev, [entry.key]: next }))
                  }
                />
                {fieldErrors[entry.key] && (
                  <p className="px-5 pb-2 text-[11.5px] text-destructive">
                    {fieldErrors[entry.key]}
                  </p>
                )}
              </div>
            ))}

            <div className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-3">
              <button
                type="button"
                onClick={analyse}
                disabled={mutation.isPending}
                className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {mutation.isPending ? "Analysing…" : "Analyse impact"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft({});
                  setResult(null);
                  setFieldErrors({});
                }}
                className="focus-ring rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors hover:bg-secondary"
              >
                Reset
              </button>
              <span className="text-[11.5px] text-muted-foreground">
                Preview only — proposed values are never saved to this project.
              </span>
            </div>
          </>
        )}
      </section>

      {mutation.isError && Object.keys(fieldErrors).length === 0 && (
        <p className="mt-4 border border-destructive/30 bg-danger-surface px-5 py-3 text-[12.5px]">
          {mutation.error instanceof BackendUnavailableError
            ? "The IRIS backend isn't reachable right now."
            : "The change could not be analysed. Check the proposed values and try again."}
        </p>
      )}

      {result && (
        <>
          <section className="mt-6 border border-border bg-surface px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Tag tone={result.authoritative ? "success" : "warning"}>
                    {result.authoritative
                      ? "Authoritative result"
                      : "Not an authoritative determination"}
                  </Tag>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {result.evaluation_mode} · {result.engine_version}
                  </span>
                </div>
                {result.proposed_changes.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {result.proposed_changes.map((c) => (
                      <li key={c.key} className="text-[12.5px]">
                        <span className="capitalize">{factLabel(c.key)}</span>:{" "}
                        <span className="tabular text-muted-foreground">
                          {formatValue(c.previous_value)}
                        </span>{" "}
                        <ArrowRight className="inline h-3 w-3 text-muted-foreground/60" />{" "}
                        <span className="tabular font-medium">
                          {formatValue(c.proposed_value)}
                        </span>
                        {c.units[0] ? ` ${c.units[0]}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-[12.5px] text-muted-foreground">
                    No effective fact change was supplied.
                  </p>
                )}
              </div>
              <dl className="flex flex-wrap gap-x-8 gap-y-3">
                {(
                  [
                    ["Newly applicable", result.summary.NEWLY_APPLICABLE],
                    ["No longer applicable", result.summary.NO_LONGER_APPLICABLE],
                    ["Changed", result.summary.CHANGED],
                    ["Unchanged", result.summary.UNCHANGED],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <dt className="label-meta">{label}</dt>
                    <dd className="tabular mt-1 text-[20px] font-semibold leading-none">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>

            {result.notes.length > 0 && (
              <ul className="mt-4 space-y-1.5 border-t border-border pt-3">
                {result.notes.map((n, i) => (
                  <li
                    key={i}
                    className="text-[11.5px] leading-relaxed text-muted-foreground"
                  >
                    {n}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-6">
            <SectionHeading
              title={
                changed.length > 0
                  ? "Requirements whose engine result changed"
                  : "No requirement changed result"
              }
              hint="Each side is a separate evaluation of the same deterministic rule engine."
            />
            <div className="mt-3 space-y-3">
              {changed.length > 0 ? (
                changed.map((r) => (
                  <RequirementDiff key={r.requirement_id} req={r} onProof={openProof} />
                ))
              ) : (
                <div className="border border-dashed border-border bg-surface px-5 py-6">
                  <p className="text-[12.5px] leading-relaxed text-muted-foreground">
                    Both evaluations returned the same result for every
                    requirement in the dataset.
                  </p>
                </div>
              )}
            </div>
          </section>

          {unchanged.length > 0 && (
            <section className="mt-6">
              <button
                type="button"
                onClick={() => setShowUnchanged((v) => !v)}
                className="text-[12px] font-medium text-info hover:opacity-80"
              >
                {showUnchanged ? "Hide" : "Show"} {unchanged.length} unchanged
                requirement{unchanged.length === 1 ? "" : "s"}
              </button>
              {showUnchanged && (
                <div className="mt-3 space-y-3">
                  {unchanged.map((r) => (
                    <RequirementDiff key={r.requirement_id} req={r} onProof={openProof} />
                  ))}
                </div>
              )}
            </section>
          )}

          <p className="mt-6 border-t border-border pt-4 text-[11px] leading-relaxed text-muted-foreground">
            {result.persistence_note}
          </p>
        </>
      )}
      <DecisionProofDrawer
        projectId={activeProject.id}
        target={proof}
        onClose={() => setProof(null)}
      />
    </PageShell>
  );
}

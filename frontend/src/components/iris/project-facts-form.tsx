import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type FactRegistryEntry,
} from "@/lib/iris/api-client";
import {
  FACT_UNKNOWN,
  factLabel,
  factToInput,
  fieldErrorsFromDetail,
  formatFactValue,
  parseFactInput,
  useDatasetRequirementTitles,
  useFactRegistry,
  useProjectFacts,
} from "@/lib/iris/facts";

const inputClass =
  "focus-ring w-full rounded-sm border border-border bg-surface px-2 py-[7px] text-[12.5px]";

function FactField({
  entry,
  value,
  error,
  onChange,
}: {
  entry: FactRegistryEntry;
  value: string;
  error: string | undefined;
  onChange: (next: string) => void;
}) {
  const unit = entry.units[0];
  const listId = `fact-values-${entry.key}`;
  const referenced = entry.values_referenced_by_rules;
  return (
    <div className="grid gap-x-6 gap-y-2 px-5 py-3.5 sm:grid-cols-[minmax(0,1fr)_220px]">
      <div>
        <label htmlFor={entry.key} className="text-[13px] font-medium capitalize">
          {factLabel(entry.key)}
        </label>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
          {entry.key}
          {unit ? ` · ${unit}` : ""}
        </p>
        {referenced.length > 0 && entry.value_type === "string" && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            Values the rules compare against:{" "}
            {referenced.map((v) => formatFactValue(v)).join(", ")}{" "}
            <span className="italic">(not an exhaustive list)</span>
          </p>
        )}
        {error && <p className="mt-1 text-[11.5px] text-destructive">{error}</p>}
      </div>
      <div>
        {entry.value_type === "boolean" ? (
          <select
            id={entry.key}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className={inputClass}
          >
            <option value="">Not provided</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
            <option value={FACT_UNKNOWN}>Unknown</option>
          </select>
        ) : entry.value_type === "number" ? (
          <input
            id={entry.key}
            type="number"
            inputMode="decimal"
            value={value === FACT_UNKNOWN ? "" : value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={unit ? `Not provided (${unit})` : "Not provided"}
            className={`${inputClass} tabular`}
          />
        ) : (
          <>
            <input
              id={entry.key}
              type="text"
              list={referenced.length ? listId : undefined}
              value={value === FACT_UNKNOWN ? "" : value}
              onChange={(e) => onChange(e.target.value)}
              placeholder="Not provided"
              className={inputClass}
            />
            {referenced.length > 0 && (
              <datalist id={listId}>
                {referenced.map((v) => (
                  <option key={String(v)} value={String(v)} />
                ))}
              </datalist>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Captures the Project Facts the regulatory dataset's Rule Versions declare
 * in `required_project_facts` — and only those. The field list comes from
 * GET /api/v1/facts/registry, so it grows with the verified regulatory pack
 * without code changes.
 *
 * "Not provided"/"Unknown" is always a legitimate answer: the engine then
 * reports REQUIRES_INFORMATION instead of the UI guessing.
 */
export function ProjectFactsForm({
  projectId,
  onSaved,
  submitLabel = "Save project facts",
}: {
  projectId: string;
  onSaved?: () => void;
  submitLabel?: string;
}) {
  const queryClient = useQueryClient();
  const registry = useFactRegistry();
  const stored = useProjectFacts(projectId);
  const titles = useDatasetRequirementTitles();

  const entries = useMemo(
    () => (registry.data?.facts ?? []).filter((f) => f.typed_input_supported),
    [registry.data],
  );

  const initial = useMemo(() => {
    const facts = stored.data?.facts ?? {};
    return Object.fromEntries(entries.map((e) => [e.key, factToInput(facts[e.key])]));
  }, [entries, stored.data]);

  const [draft, setDraft] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [savedCount, setSavedCount] = useState<number | null>(null);

  // Re-seed the form whenever the stored facts (or the project) change.
  useEffect(() => {
    setDraft(initial);
    setErrors({});
  }, [initial]);

  // Group facts under the requirements whose rules read them. A fact read by
  // several requirements is listed once, under the first, with the rest named.
  const groups = useMemo(() => {
    const byReq = new Map<string, FactRegistryEntry[]>();
    for (const e of entries) {
      const first = e.requirement_ids[0] ?? "—";
      byReq.set(first, [...(byReq.get(first) ?? []), e]);
    }
    return [...byReq.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [entries]);

  const save = useMutation({
    mutationFn: (facts: Record<string, unknown>) =>
      irisApi.mergeProjectFacts(projectId, facts),
    onSuccess: async (_res, facts) => {
      setSavedCount(Object.keys(facts).length);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project-facts", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["engine-evaluation", projectId] }),
      ]);
      onSaved?.();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 422) {
        setErrors(fieldErrorsFromDetail(error.detail));
      }
    },
  });

  function submit() {
    const changed: Record<string, unknown> = {};
    const errs: Record<string, string> = {};
    for (const e of entries) {
      const now = draft[e.key] ?? "";
      if (now === (initial[e.key] ?? "")) continue;
      if (now === "") {
        changed[e.key] = null; // cleared -> explicitly unknown
        continue;
      }
      const parsed = parseFactInput(e, now);
      if (parsed.ok) changed[e.key] = parsed.value;
      else errs[e.key] = parsed.message;
    }
    setErrors(errs);
    setSavedCount(null);
    if (Object.keys(errs).length) return;
    if (Object.keys(changed).length === 0) {
      setSavedCount(0);
      onSaved?.();
      return;
    }
    save.mutate(changed);
  }

  if (registry.isLoading || stored.isLoading) {
    return (
      <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
        Loading the facts the regulatory rules ask for…
      </p>
    );
  }
  if (registry.isError || stored.isError) {
    const offline =
      registry.error instanceof BackendUnavailableError ||
      stored.error instanceof BackendUnavailableError;
    return (
      <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
        {offline
          ? "The IRIS backend isn't reachable, so project facts can't be loaded."
          : "Project facts could not be loaded."}
      </p>
    );
  }
  if (entries.length === 0) {
    return (
      <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
        The regulatory dataset declares no typed project facts.
      </p>
    );
  }

  return (
    <div>
      {groups.map(([reqId, facts]) => (
        <div key={reqId} className="border-b border-border last:border-b-0">
          <div className="bg-surface-sunken px-5 py-2">
            <span className="label-meta">Asked by</span>{" "}
            <span className="text-[12px] font-medium">
              {titles.data?.[reqId] ?? reqId}
            </span>{" "}
            <span className="font-mono text-[11px] text-muted-foreground">{reqId}</span>
          </div>
          <div className="divide-y divide-border">
            {facts.map((e) => (
              <FactField
                key={e.key}
                entry={e}
                value={draft[e.key] ?? ""}
                error={errors[e.key]}
                onChange={(next) => setDraft((d) => ({ ...d, [e.key]: next }))}
              />
            ))}
          </div>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-3">
        <button
          type="button"
          onClick={submit}
          disabled={save.isPending}
          className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {save.isPending ? "Saving…" : submitLabel}
        </button>
        {savedCount !== null && !save.isPending && (
          <span className="text-[11.5px] text-muted-foreground">
            {savedCount === 0 ? "No changes to save." : `Saved ${savedCount} fact${savedCount === 1 ? "" : "s"}.`}
          </span>
        )}
        {save.isError && !(save.error instanceof ApiError && save.error.status === 422) && (
          <span className="text-[11.5px] text-destructive">
            {save.error instanceof BackendUnavailableError
              ? "Backend unreachable — nothing was saved."
              : "Facts could not be saved."}
          </span>
        )}
      </div>
      <p className="border-t border-border px-5 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
        These are your declarations about the project, stored as Project Facts.
        Leave a fact unprovided rather than guessing — IRIS will report
        additional information required instead of assuming an answer.
      </p>
    </div>
  );
}

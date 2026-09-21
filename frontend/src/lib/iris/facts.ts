/**
 * Shared helpers for Project Facts driven by the backend's dataset-derived
 * fact registry (GET /api/v1/facts/registry).
 *
 * Nothing here knows about any specific fact key, unit or threshold — every
 * form built on these helpers renders whatever the regulatory dataset's own
 * Conditions/Rule Versions declare. Parsing is strict and never coerces a
 * value the user did not clearly give: an empty input means "unknown", which
 * the engine resolves to UNKNOWN / REQUIRES_INFORMATION rather than FALSE.
 */
import { useQuery } from "@tanstack/react-query";
import { irisApi, type FactRegistryEntry } from "./api-client";

/** Sentinel select value meaning "explicitly unknown" (sent as null). */
export const FACT_UNKNOWN = "__UNKNOWN__";

/** Last dotted segment, underscores to spaces — a mechanical relabel of the
 * engine's own key. Callers always show the full key alongside it. */
export function factLabel(key: string): string {
  const tail = key.includes(".") ? key.slice(key.indexOf(".") + 1) : key;
  return tail.replace(/_/g, " ");
}

export function formatFactValue(value: unknown): string {
  if (value === null || value === undefined) return "not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

/** Converts a stored value into the string a form input holds. */
export function factToInput(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export type ParsedFact =
  | { ok: true; value: unknown }
  | { ok: false; message: string };

/** Strictly parses one form input for a registry entry. "" is never passed
 * here — callers treat it as "leave unchanged / not provided". */
export function parseFactInput(entry: FactRegistryEntry, raw: string): ParsedFact {
  if (raw === FACT_UNKNOWN) return { ok: true, value: null };
  if (entry.value_type === "boolean") {
    if (raw === "true") return { ok: true, value: true };
    if (raw === "false") return { ok: true, value: false };
    return { ok: false, message: "Choose Yes, No or Unknown." };
  }
  if (entry.value_type === "number") {
    const n = Number(raw);
    if (raw.trim() === "" || !Number.isFinite(n)) {
      return { ok: false, message: "Enter a number." };
    }
    return { ok: true, value: n };
  }
  if (!raw.trim()) return { ok: false, message: "Enter a value." };
  return { ok: true, value: raw.trim() };
}

/** Pulls the backend's per-key 422 detail ({errors:[{key,message}]}) into a
 * key -> message map. Returns {} for any other error shape. */
export function fieldErrorsFromDetail(detail: unknown): Record<string, string> {
  if (typeof detail !== "object" || detail === null || !("errors" in detail)) {
    return {};
  }
  const errs =
    (detail as { errors?: { key: string; message: string }[] }).errors ?? [];
  return Object.fromEntries(errs.map((e) => [e.key, e.message]));
}

export function useFactRegistry() {
  return useQuery({
    queryKey: ["fact-registry"],
    queryFn: () => irisApi.getFactRegistry(),
    staleTime: 5 * 60_000,
  });
}

export function useProjectFacts(projectId: string) {
  return useQuery({
    queryKey: ["project-facts", projectId],
    queryFn: () => irisApi.getProjectFacts(projectId),
  });
}

/** requirement_id -> title, straight from the regulatory dataset. */
export function useDatasetRequirementTitles() {
  return useQuery({
    queryKey: ["dataset-requirements"],
    queryFn: async () => {
      const rows = (await irisApi.listRequirements()) as {
        requirement_id: string;
        title?: string;
      }[];
      return Object.fromEntries(
        rows.map((r) => [r.requirement_id, r.title ?? r.requirement_id]),
      ) as Record<string, string>;
    },
    staleTime: 5 * 60_000,
  });
}

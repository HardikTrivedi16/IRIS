/**
 * Project-aware PRESENTATION grouping of the (global) Unified Project Fact Registry.
 *
 * The registry stays global and every fact stays reachable and editable. This module only decides
 * in which section a fact is shown, using generic signals — never a sector name, requirement id or
 * fact key:
 *   - the registry entry's own requirement_ids / scheme_ids;
 *   - the project's STORED facts;
 *   - the project's current diagnostic regulatory items (RegulatoryItem.relevance / finalState);
 *   - the project's current diagnostic scheme matches, when available.
 *
 * Relevance is presentation only: it never feeds back into any engine result, applicability,
 * persistence, Decision Proof or scheme matching. PURE — no fetching, no React.
 */
import type { FactRegistryEntry, SchemeMatch } from "./api-client";
import type { RegulatoryItem } from "./regulatory-items";

export interface FactGroups {
  /** Facts directly missing from currently relevant regulatory determinations. */
  needsInformation: FactRegistryEntry[];
  /** Facts read by currently relevant regulatory items / potentially-eligible schemes. */
  relevant: FactRegistryEntry[];
  /** Other facts already stored on the project. */
  recorded: FactRegistryEntry[];
  /** Everything else in the global registry (collapsed by default). */
  other: FactRegistryEntry[];
}

const hasValue = (v: unknown) => v !== null && v !== undefined;

/** A requirement is "currently relevant" when the diagnostic evaluation says APPLICABLE, or the
 * project itself has an information/review gap on it — the same notion the Regulatory Map default
 * uses. Diagnostic NOT_APPLICABLE and not-yet-evaluable requirements are not. */
export function isRelevantItem(i: RegulatoryItem): boolean {
  return i.diagnostic?.finalState === "APPLICABLE" || i.relevance === "NEEDS_INFORMATION";
}

export function groupFactsByRelevance(input: {
  entries: FactRegistryEntry[];
  stored: Record<string, unknown>;
  items: RegulatoryItem[];
  schemeMatches?: SchemeMatch[] | undefined;
}): FactGroups {
  const relevantIds = new Set(input.items.filter(isRelevantItem).map((i) => i.requirementId));

  const missing = new Set<string>();
  for (const i of input.items) {
    if (!isRelevantItem(i) || !i.diagnostic) continue;
    if (i.diagnostic.finalState === "REQUIRES_INFORMATION" || i.diagnostic.finalState === "REQUIRES_REVIEW") {
      for (const k of i.diagnostic.missingFactKeys) missing.add(k);
    }
  }

  const schemeKeys = new Set<string>();
  for (const m of input.schemeMatches ?? []) {
    if (m.outcome !== "POTENTIALLY_ELIGIBLE") continue;
    for (const w of m.why) if (w.fact_key) schemeKeys.add(w.fact_key);
  }

  const groups: FactGroups = { needsInformation: [], relevant: [], recorded: [], other: [] };
  for (const e of input.entries) {
    if (missing.has(e.key)) {
      groups.needsInformation.push(e);
    } else if (e.requirement_ids.some((r) => relevantIds.has(r)) || schemeKeys.has(e.key)) {
      groups.relevant.push(e);
    } else if (hasValue(input.stored[e.key])) {
      groups.recorded.push(e);
    } else {
      groups.other.push(e);
    }
  }
  return groups;
}

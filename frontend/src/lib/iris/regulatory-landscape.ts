/**
 * Regulatory Landscape (Graph 2.0) — PURE presentation helpers over `RegulatoryItem[]`.
 *
 * The landscape groups the engine's own requirement catalogue by regulatory authority/domain
 * (lanes) and lifecycle stage (columns). Grouping is layout only: it never implies a legal
 * prerequisite, sequence or dependency, and no edge is produced anywhere. Every state shown is
 * copied from an engine decision: the PRODUCTION result when it is authoritative, otherwise the
 * labelled DIAGNOSTIC result of the same rule.
 */
import type { RegulatoryItem } from "./regulatory-items";

export type TrustState = "VERIFIED" | "DIAGNOSTIC";
export type LandscapeTone = "success" | "warning" | "neutral";

export interface EffectiveState {
  /** Engine final_state actually displayed, or null when nothing is evaluable yet. */
  state: string | null;
  trust: TrustState;
  tone: LandscapeTone;
  label: string;
}

const isApplicable = (s: string | null) => s === "APPLICABLE";
const isNotApplicable = (s: string | null) => s === "NOT_APPLICABLE";

/** Production first: the authoritative result when there is one, else the diagnostic result. */
export function effectiveState(item: RegulatoryItem): EffectiveState {
  const authoritative = item.production.authoritative;
  const state = authoritative ? item.production.finalState : (item.diagnostic?.finalState ?? null);
  const trust: TrustState = authoritative ? "VERIFIED" : "DIAGNOSTIC";
  if (isApplicable(state)) return { state, trust, tone: "success", label: "Applicable" };
  if (isNotApplicable(state)) return { state, trust, tone: "neutral", label: "Not applicable" };
  if (state === "REQUIRES_REVIEW") return { state, trust, tone: "warning", label: "Needs review" };
  if (state === "REQUIRES_INFORMATION")
    return { state, trust, tone: "warning", label: "Needs information" };
  return { state, trust, tone: "neutral", label: "Not yet evaluable" };
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

export type LandscapeFilter = "relevant" | "applicable" | "needs" | "not-applicable" | "all";

export const LANDSCAPE_FILTERS: { key: LandscapeFilter; label: string }[] = [
  { key: "relevant", label: "Relevant" },
  { key: "applicable", label: "Applicable" },
  { key: "needs", label: "Needs information / review" },
  { key: "not-applicable", label: "Not applicable" },
  { key: "all", label: "All" },
];

/**
 * Relevant = the requirement is applicable to the project, or the project has started to answer its
 * rule family and information/review is still missing (the engine-derived `relevance`). A
 * NOT_APPLICABLE requirement is never "relevant"; it stays in the catalogue under Not applicable / All.
 */
export function matchesLandscapeFilter(item: RegulatoryItem, filter: LandscapeFilter): boolean {
  // Deprecated historical requirements (e.g. the general FSSAI licence logic, superseded by the
  // Central/State/Registration tiers) never compete in the default view; they stay in the catalogue.
  if (item.deprecated && filter === "relevant") return false;
  const { state } = effectiveState(item);
  // Information is "the project's own gap" when the engine cannot decide AND the project has already
  // recorded at least one fact this requirement's rules read (or the shared relevance model says so).
  const undecided = !isApplicable(state) && !isNotApplicable(state) && state !== null;
  // A VERIFIED (authoritative Production) "needs information" result is itself a finding of the
  // deterministic engine — the project must answer that regulatory question — so it is relevant.
  const needs =
    undecided &&
    (item.production.authoritative ||
      item.relevance === "NEEDS_INFORMATION" ||
      item.presentFactKeys.length > 0);
  switch (filter) {
    case "relevant":
      return isApplicable(state) || needs;
    case "applicable":
      return isApplicable(state);
    case "needs":
      return needs;
    case "not-applicable":
      return isNotApplicable(state);
    default:
      return true;
  }
}

// ---------------------------------------------------------------------------
// Columns (lifecycle stage) and lanes (authority / domain)
// ---------------------------------------------------------------------------

export interface StageColumn {
  id: string;
  label: string;
}

/** Display order of lifecycle stages. Dataset ids that are spelling variants of one stage share a column. */
export const STAGE_COLUMNS: StageColumn[] = [
  { id: "PRE_CONSTRUCTION", label: "Pre-construction" },
  { id: "PRE_ESTABLISHMENT", label: "Pre-establishment" },
  { id: "PRE_OPERATION", label: "Pre-operation" },
  { id: "OPERATION", label: "Operation" },
  { id: "UNSPECIFIED", label: "Stage not specified" },
];

const STAGE_ALIAS: Record<string, string> = { OPERATIONAL: "OPERATION" };

export function stageColumnId(stageId: string): string {
  const id = STAGE_ALIAS[stageId] ?? stageId;
  return STAGE_COLUMNS.some((c) => c.id === id) ? id : "UNSPECIFIED";
}

/** A requirement is drawn ONCE, in its earliest stage column; later stages are listed as a note. */
export function primaryColumn(item: RegulatoryItem): string {
  const ids = item.lifecycleStageIds.map(stageColumnId);
  if (ids.length === 0) return "UNSPECIFIED";
  return STAGE_COLUMNS.map((c) => c.id).find((c) => ids.includes(c)) ?? "UNSPECIFIED";
}

export function otherStageLabels(item: RegulatoryItem): string[] {
  const primary = primaryColumn(item);
  const seen = new Set<string>([primary]);
  const out: string[] = [];
  for (const s of item.lifecycleStageIds) {
    const c = stageColumnId(s);
    if (seen.has(c)) continue;
    seen.add(c);
    out.push(STAGE_COLUMNS.find((x) => x.id === c)?.label ?? c);
  }
  return out;
}

/**
 * Lanes are regulatory domains. Authority records that regulate one domain share a lane (for
 * example the Central FSSAI and the State food wing). Keyed by authority id; any authority
 * without an entry gets its own lane named after the authority itself.
 */
const LANE_BY_AUTHORITY: Record<string, { id: string; label: string }> = {
  "AUTH-MPCB": { id: "pollution-state", label: "MPCB" },
  "AUTH-CPCB": { id: "pollution-central", label: "CPCB" },
  "AUTH-FSSAI": { id: "food", label: "FSSAI / Food safety" },
  "AUTH-FDA-MH-FOOD": { id: "food", label: "FSSAI / Food safety" },
  "AUTH-FDA-MH": { id: "drugs", label: "Drugs (FDA / CDSCO)" },
  "AUTH-CDSCO": { id: "drugs", label: "Drugs (FDA / CDSCO)" },
  "AUTH-DISH-MH": { id: "factory", label: "Factory safety (DISH)" },
  "AUTH-BOILER-MH": { id: "boiler", label: "Boilers" },
  "AUTH-LMO-MH": { id: "legal-metrology", label: "Legal Metrology" },
  "AUTH-MoEFCC": { id: "environment", label: "Environment clearance" },
  "AUTH-SEIAA-MH": { id: "environment", label: "Environment clearance" },
  "AUTH-CGWA": { id: "groundwater", label: "Groundwater (CGWA)" },
  "AUTH-MORTH": { id: "transport", label: "Vehicle approval (MoRTH)" },
};

function shortName(name: string): string {
  return name.split(/\s[—(-]\s?|\s\(/)[0]?.trim() || name;
}

export function laneFor(item: RegulatoryItem): { id: string; label: string } {
  const known = item.authorityId ? LANE_BY_AUTHORITY[item.authorityId] : undefined;
  if (known) return known;
  const label = shortName(item.authorityName);
  return { id: item.authorityId ?? label, label };
}

export interface LandscapeNode {
  item: RegulatoryItem;
  view: EffectiveState;
  otherStages: string[];
}

export interface LandscapeLane {
  id: string;
  label: string;
  count: number;
  cells: Record<string, LandscapeNode[]>;
}

export interface Landscape {
  columns: StageColumn[];
  lanes: LandscapeLane[];
  total: number;
}

const stateRank = (n: LandscapeNode) =>
  n.view.tone === "success" ? 0 : n.view.tone === "warning" ? 1 : 2;

/** Builds the lane x stage grid for the given (already filtered) items. Empty columns are dropped. */
export function buildLandscape(items: RegulatoryItem[]): Landscape {
  const lanes = new Map<string, LandscapeLane>();
  const usedColumns = new Set<string>();
  for (const item of items) {
    const lane = laneFor(item);
    const col = primaryColumn(item);
    usedColumns.add(col);
    const row = lanes.get(lane.id) ?? { id: lane.id, label: lane.label, count: 0, cells: {} };
    (row.cells[col] ??= []).push({
      item,
      view: effectiveState(item),
      otherStages: otherStageLabels(item),
    });
    row.count += 1;
    lanes.set(lane.id, row);
  }
  for (const lane of lanes.values()) {
    for (const nodes of Object.values(lane.cells)) {
      nodes.sort(
        (a, b) => stateRank(a) - stateRank(b) || a.item.requirementId.localeCompare(b.item.requirementId),
      );
    }
  }
  return {
    columns: STAGE_COLUMNS.filter((c) => usedColumns.has(c.id)),
    lanes: [...lanes.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)),
    total: items.length,
  };
}

/** Short node title: drops the trailing legal citation ("— Water Act, 1974") for readability. */
export function shortTitle(title: string): string {
  const head = title.split(/\s[—–-]\s/)[0]?.trim();
  return head && head.length >= 8 ? head : title;
}

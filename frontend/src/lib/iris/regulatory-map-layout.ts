/**
 * Regulatory Map layout — PURE, deterministic, left-to-right.
 *
 *   PROJECT  ->  requirements  ->  requirements that depend on them
 *
 * Layers come ONLY from the relationships the dependency API supplies (longest path over the
 * edges whose endpoints are both visible). Requirements with no such edge sit in the first
 * requirement layer, ordered by regulatory domain. No relationship is ever invented to influence
 * placement, and the project->requirement links drawn by the component are evaluation links, not
 * dependencies.
 */
import type { DependencyRelationship } from "./api-client";
import type { RegulatoryItem } from "./regulatory-items";
import { effectiveState, laneFor, type EffectiveState } from "./regulatory-landscape";

export const PROJECT_W = 196;
export const PROJECT_H = 92;
export const NODE_W = 220;
export const NODE_H = 76;
export const COL_GAP = 120;
export const ROW_GAP = 10;
const FAMILY_TOP = 24;
const FAMILY_BOTTOM = 10;
const MARGIN = 24;
const SUB_GAP = 40;
/** Entry requirements wrap into side-by-side sub-columns beyond this many rows (keeps the map horizontal). */
const MAX_ROWS = 7;

/**
 * Presentation-only grouping. These requirements are mutually exclusive classification outcomes
 * of one licensing question, NOT dependencies: the group is a background bracket, never an arrow.
 */
export const CLASSIFICATION_FAMILIES: { id: string; label: string; requirementIds: string[] }[] = [
  { id: "fssai-licence", label: "FSSAI licence classification", requirementIds: ["REQ-0011", "REQ-0012", "REQ-0013"] },
];

export interface MapNode {
  id: string;
  item: RegulatoryItem;
  view: EffectiveState;
  laneLabel: string;
  layer: number;
  x: number;
  y: number;
}

export interface MapEdge {
  rel: DependencyRelationship;
  from: MapNode;
  to: MapNode;
}

export interface FamilyBox {
  id: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface MapLayout {
  project: { x: number; y: number };
  nodes: MapNode[];
  edges: MapEdge[];
  families: FamilyBox[];
  width: number;
  height: number;
}

const familyOf = (id: string) => CLASSIFICATION_FAMILIES.find((f) => f.requirementIds.includes(id));

export function layoutRegulatoryMap(items: RegulatoryItem[], relationships: DependencyRelationship[]): MapLayout {
  const byId = new Map(items.map((i) => [i.requirementId, i]));
  const rels = relationships.filter(
    (r) =>
      byId.has(r.from_requirement_id) &&
      byId.has(r.to_requirement_id) &&
      r.from_requirement_id !== r.to_requirement_id,
  );

  // Layer = 1 + longest path from an entry requirement (cycle-guarded).
  const parents = new Map<string, string[]>();
  for (const r of rels) parents.set(r.to_requirement_id, [...(parents.get(r.to_requirement_id) ?? []), r.from_requirement_id]);
  const layerOf = new Map<string, number>();
  const resolve = (id: string, stack: Set<string>): number => {
    const known = layerOf.get(id);
    if (known !== undefined) return known;
    if (stack.has(id)) return 1;
    stack.add(id);
    const ps = parents.get(id) ?? [];
    const v = ps.length ? Math.max(...ps.map((p) => resolve(p, stack))) + 1 : 1;
    stack.delete(id);
    layerOf.set(id, v);
    return v;
  };
  for (const i of items) resolve(i.requirementId, new Set());
  const maxLayer = Math.max(1, ...layerOf.values());

  const mk = (item: RegulatoryItem): MapNode => ({
    id: item.requirementId,
    item,
    view: effectiveState(item),
    laneLabel: laneFor(item).label,
    layer: layerOf.get(item.requirementId) ?? 1,
    x: MARGIN + PROJECT_W + COL_GAP + ((layerOf.get(item.requirementId) ?? 1) - 1) * (NODE_W + COL_GAP),
    y: 0,
  });
  const nodes = items.map(mk);
  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  // Layer 1: by domain, classification-family members kept contiguous.
  const sortKey = (n: MapNode) => {
    const fam = familyOf(n.id);
    return `${n.laneLabel.toLowerCase()}|${fam ? `0${fam.id}` : "1"}|${n.id}`;
  };
  const stack = (col: MapNode[], startY: number, boxes?: FamilyBox[]) => {
    let y = startY;
    let openFam: { id: string; label: string; top: number; first: MapNode; last: MapNode; count: number } | null = null;
    const closeFam = () => {
      if (openFam && openFam.count >= 2 && boxes) {
        boxes.push({
          id: openFam.id,
          label: openFam.label,
          x: openFam.first.x - 8,
          y: openFam.top,
          w: NODE_W + 16,
          h: openFam.last.y + NODE_H + 8 - openFam.top,
        });
      }
      if (openFam) y += FAMILY_BOTTOM;
      openFam = null;
    };
    for (const n of col) {
      const fam = familyOf(n.id);
      if (openFam && (!fam || fam.id !== openFam.id)) closeFam();
      if (fam && !openFam) {
        // only bracket when at least two members are actually visible in this column
        const visibleMembers = col.filter((m) => familyOf(m.id)?.id === fam.id).length;
        if (visibleMembers >= 2) {
          y += FAMILY_TOP;
          openFam = { id: fam.id, label: fam.label, top: y - FAMILY_TOP + 4, first: n, last: n, count: 0 };
        }
      }
      n.y = y;
      y += NODE_H + ROW_GAP;
      if (openFam) {
        openFam.last = n;
        openFam.count += 1;
      }
    }
    closeFam();
    return y;
  };

  const families: FamilyBox[] = [];
  const hasChildren = new Set(rels.map((r) => r.from_requirement_id));
  // Entry requirements: those that parent a dependency go last (right next to their dependents).
  const layer1 = nodes
    .filter((n) => n.layer === 1)
    .sort(
      (a, b) =>
        Number(hasChildren.has(a.id)) - Number(hasChildren.has(b.id)) ||
        sortKey(a).localeCompare(sortKey(b)),
    );
  // Chunk into sub-columns without splitting a classification family.
  const chunks: MapNode[][] = [];
  if (layer1.length <= MAX_ROWS + 1) chunks.push(layer1);
  else {
    const nCols = Math.ceil(layer1.length / MAX_ROWS);
    const per = Math.ceil(layer1.length / nCols);
    let cur: MapNode[] = [];
    for (const n of layer1) {
      const fam = familyOf(n.id)?.id;
      const prev = cur[cur.length - 1];
      const sameFam = !!fam && !!prev && familyOf(prev.id)?.id === fam;
      if (cur.length >= per && !sameFam && chunks.length < nCols - 1) {
        chunks.push(cur);
        cur = [];
      }
      cur.push(n);
    }
    if (cur.length) chunks.push(cur);
  }
  const firstX = MARGIN + PROJECT_W + COL_GAP;
  let endY = MARGIN;
  chunks.forEach((col, k) => {
    for (const n of col) n.x = firstX + k * (NODE_W + SUB_GAP);
    endY = Math.max(endY, stack(col, MARGIN, families));
  });
  const lastSubX = firstX + (chunks.length - 1) * (NODE_W + SUB_GAP);
  for (const n of nodes) if (n.layer > 1) n.x = lastSubX + NODE_W + COL_GAP + (n.layer - 2) * (NODE_W + COL_GAP);
  let height = Math.max(endY - ROW_GAP + MARGIN, MARGIN * 2 + PROJECT_H);

  for (let l = 2; l <= maxLayer; l++) {
    const col = nodes.filter((n) => n.layer === l);
    // aim each node at the mean centre of its parents, then resolve collisions downward
    const target = (n: MapNode) => {
      const ps = (parents.get(n.id) ?? []).map((p) => nodeById.get(p)!).filter(Boolean);
      return ps.length ? ps.reduce((s, p) => s + p.y, 0) / ps.length : 0;
    };
    col.sort((a, b) => target(a) - target(b) || a.id.localeCompare(b.id));
    let y = MARGIN;
    for (const n of col) {
      n.y = Math.max(target(n), y);
      y = n.y + NODE_H + ROW_GAP;
    }
    height = Math.max(height, y - ROW_GAP + MARGIN);
  }

  const first = nodes.filter((n) => n.layer === 1);
  const top = first.length ? Math.min(...first.map((n) => n.y)) : MARGIN;
  const bottom = first.length ? Math.max(...first.map((n) => n.y + NODE_H)) : MARGIN + PROJECT_H;
  const project = { x: MARGIN, y: Math.max(MARGIN, (top + bottom) / 2 - PROJECT_H / 2) };

  const edges: MapEdge[] = rels.map((rel) => ({
    rel,
    from: nodeById.get(rel.from_requirement_id)!,
    to: nodeById.get(rel.to_requirement_id)!,
  }));

  return {
    project,
    nodes: nodes.sort((a, b) => a.layer - b.layer || a.y - b.y),
    edges,
    families,
    width: lastSubX + NODE_W + (maxLayer - 1) * (NODE_W + COL_GAP) + MARGIN,
    height,
  };
}

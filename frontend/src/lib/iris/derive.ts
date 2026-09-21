import type {
  Requirement,
  Status,
  GraphNode,
  GraphEdge,
} from "./types";

// ---------------------------------------------------------------------------
// Readiness / grouping helpers (operate on a Requirement[] passed in — the
// data now comes from the backend via useProjectRequirements, not mock-data).
// ---------------------------------------------------------------------------

export interface ReadinessSummary {
  applicable: Requirement[];
  ready: number;
  attention: number;
  blocked: number;
  notStarted: number;
  notApplicable: number;
  readinessPct: number;
  blockers: Requirement[];
}

export function readiness(reqs: Requirement[]): ReadinessSummary {
  const applicable = reqs.filter((r) => r.applicability === "applicable");
  const count = (s: Status) => reqs.filter((r) => r.status === s).length;
  const ready = count("ready");
  return {
    applicable,
    ready,
    attention: count("attention"),
    blocked: count("blocked"),
    notStarted: applicable.filter(
      (r) => r.status === "not-ready" || r.status === "not-applicable",
    ).length,
    notApplicable: reqs.filter((r) => r.applicability === "not-applicable")
      .length,
    readinessPct: applicable.length
      ? Math.round((ready / applicable.length) * 100)
      : 0,
    blockers: reqs.filter((r) => r.status === "blocked"),
  };
}

export function byAuthority(reqs: Requirement[]) {
  const map = new Map<
    string,
    { authority: string; total: number; ready: number; open: number }
  >();
  reqs
    .filter((r) => r.applicability === "applicable" && r.authority !== "—")
    .forEach((r) => {
      const entry = map.get(r.authority) ?? {
        authority: r.authority,
        total: 0,
        ready: 0,
        open: 0,
      };
      entry.total += 1;
      if (r.status === "ready") entry.ready += 1;
      else entry.open += 1;
      map.set(r.authority, entry);
    });
  return [...map.values()].sort((a, b) => b.total - a.total);
}

// ---------------------------------------------------------------------------
// Derived views (Next actions / Deadlines / Compliance / Graph) — all
// computed from the same Requirement[] so there is a single source of truth.
// ---------------------------------------------------------------------------

export interface NextAction {
  title: string;
  why: string;
  requirement: string;
  authority: string;
  severity: Status;
  due: string;
}

const SEVERITY_ORDER: Record<string, number> = {
  blocked: 0,
  attention: 1,
  "not-ready": 2,
  ready: 3,
  "not-applicable": 4,
};

/** Actionable items: blocked/attention requirements first, ordered by severity. */
export function deriveNextActions(reqs: Requirement[]): NextAction[] {
  return reqs
    .filter(
      (r) =>
        r.applicability === "applicable" &&
        (r.status === "blocked" || r.status === "attention"),
    )
    .sort((a, b) => SEVERITY_ORDER[a.status]! - SEVERITY_ORDER[b.status]!)
    .map((r) => ({
      title:
        r.status === "blocked"
          ? `Unblock ${r.name}`
          : `Complete ${r.name}`,
      why: r.reason ?? r.description,
      requirement: r.name,
      authority: r.authority,
      severity: r.status,
      due: r.timeline,
    }));
}

export interface Deadline {
  label: string;
  authority: string;
  date: string;
  note: string;
  severity: Status;
}

/** Upcoming items: anything applicable that is not yet complete. */
export function deriveDeadlines(reqs: Requirement[]): Deadline[] {
  return reqs
    .filter(
      (r) =>
        r.applicability === "applicable" &&
        r.authority !== "—" &&
        r.status !== "ready",
    )
    .sort((a, b) => SEVERITY_ORDER[a.status]! - SEVERITY_ORDER[b.status]!)
    .map((r) => ({
      label: r.name,
      authority: r.authority,
      date: r.timeline,
      note:
        r.reason ??
        `${r.documents.complete}/${r.documents.total} documents complete`,
      severity: r.status,
    }));
}

// deriveCompliance() was removed: it labelled every in-progress approval with
// an invented `daysRemaining: 30`. Renewals now come from the backend
// (GET /projects/{id}/renewals), computed only from expiry dates on record.

/** Build the regulatory dependency graph from requirement rows. Applicable
 * requirements become approval/milestone nodes; a synthetic "project" root
 * feeds requirements that have no prerequisites; edges follow dependsOn. */
export function buildRegulatoryGraph(
  reqs: Requirement[],
  projectName: string,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const applicable = reqs.filter((r) => r.applicability === "applicable");
  if (applicable.length === 0) return { nodes: [], edges: [] };

  const ids = new Set(applicable.map((r) => r.id));

  const nodes: GraphNode[] = [
    {
      id: "project",
      label: projectName,
      type: "project",
      status: "ready",
      description: "Project milestone",
    },
    ...applicable.map<GraphNode>((r) => {
      const node: GraphNode = {
        id: r.id,
        label: r.name,
        type: r.authority === "—" ? "milestone" : "approval",
        status: r.status,
        dependsOn: r.dependsOn,
        blocks: r.blocks,
        documents: r.documents,
        source: r.source,
        description: r.description,
      };
      if (r.authority !== "—") node.authority = r.authority;
      return node;
    }),
  ];

  const edges: GraphEdge[] = [];
  for (const r of applicable) {
    const deps = r.dependsOn.filter((d) => ids.has(d));
    if (deps.length === 0) {
      edges.push({ from: "project", to: r.id });
    } else {
      for (const d of deps) edges.push({ from: d, to: r.id });
    }
  }

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Static display constants (not project data)
// ---------------------------------------------------------------------------

export const stageBuckets: { key: string; label: string }[] = [
  { key: "Pre-establishment", label: "Pre-establishment" },
  { key: "Construction", label: "Construction" },
  { key: "Commissioning", label: "Commissioning" },
  { key: "Pre-operation", label: "Pre-operation" },
  { key: "Operations", label: "Operations" },
];

export const lifecycleStages = [
  { key: "plan", label: "Plan", stages: ["Pre-establishment"] },
  { key: "establish", label: "Establish", stages: ["Pre-establishment"] },
  { key: "construct", label: "Construct", stages: ["Construction"] },
  { key: "commission", label: "Commission", stages: ["Commissioning"] },
  { key: "operate", label: "Operate", stages: ["Pre-operation", "Operations"] },
  { key: "renew", label: "Renew", stages: [] },
];

export const lastEvaluated = "Live — evaluated on load";

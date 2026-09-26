import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { DependencyRelationship } from "@/lib/iris/api-client";
import type { RegulatoryItem } from "@/lib/iris/regulatory-items";
import { STAGE_COLUMNS, primaryColumn, shortTitle, type LandscapeTone } from "@/lib/iris/regulatory-landscape";
import {
  NODE_H,
  NODE_W,
  PROJECT_H,
  PROJECT_W,
  layoutRegulatoryMap,
  type MapEdge,
  type MapNode,
} from "@/lib/iris/regulatory-map-layout";

const VERIFIED_EDGE = "oklch(0.42 0.12 250)";
const DIAGNOSTIC_EDGE = "oklch(0.55 0.16 305)";

const toneCard: Record<LandscapeTone, string> = {
  success: "border-success/35 bg-success-surface",
  warning: "border-warning/40 bg-warning-surface",
  neutral: "border-border bg-surface-sunken text-muted-foreground",
};
const toneText: Record<LandscapeTone, string> = {
  success: "text-success",
  warning: "text-warning",
  neutral: "text-muted-foreground",
};
const toneDot: Record<LandscapeTone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  neutral: "bg-border-strong",
};

export const isVerifiedPrerequisite = (r: DependencyRelationship) =>
  r.trust === "VERIFIED" && r.dependency_type === "PREREQUISITE";

/** Plain-language meaning of a relationship. REQUIRES_OUTCOME_OF is never phrased as an ordering. */
export function relationshipMeaning(r: DependencyRelationship, fromTitle: string, toTitle: string): string {
  if (isVerifiedPrerequisite(r)) {
    return `Verified prerequisite: ${toTitle} presupposes ${fromTitle}.`;
  }
  return `Diagnostic: whether ${toTitle} applies depends partly on the legal outcome of ${fromTitle}. This is informational — it does not mean ${fromTitle} must be completed first.`;
}

const edgeLabel = (r: DependencyRelationship) => (isVerifiedPrerequisite(r) ? "Prerequisite" : "Requires outcome");

function curve(x1: number, y1: number, x2: number, y2: number) {
  const dx = Math.max(40, (x2 - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
}

function NodeCard({
  node,
  selected,
  dimmed,
  onSelect,
}: {
  node: MapNode;
  selected: boolean;
  dimmed: boolean;
  onSelect: (id: string) => void;
}) {
  const { item, view } = node;
  const stage = STAGE_COLUMNS.find((c) => c.id === primaryColumn(item))?.label ?? "";
  return (
    <button
      type="button"
      data-node-id={item.requirementId}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={() => onSelect(item.requirementId)}
      aria-pressed={selected}
      title={item.title}
      style={{ left: node.x, top: node.y, width: NODE_W, height: NODE_H }}
      className={cn(
        "focus-ring absolute flex flex-col justify-between rounded-sm border px-2.5 py-1.5 text-left transition-shadow hover:shadow-sm",
        toneCard[view.tone],
        selected && "ring-2 ring-info",
        dimmed && "opacity-40",
      )}
    >
      <span className="line-clamp-2 text-[12px] font-medium leading-[1.25] text-foreground">
        {shortTitle(item.title)}
      </span>
      <span className="block truncate text-[10.5px] text-muted-foreground">
        {node.laneLabel}
        {stage ? ` · ${stage}` : ""}
      </span>
      <span className="flex items-center justify-between gap-2 text-[11px] font-medium">
        <span className={cn("flex items-center gap-1.5", toneText[view.tone])}>
          <span aria-hidden className={cn("h-[6px] w-[6px] rounded-full", toneDot[view.tone])} />
          {view.label}
        </span>
        {view.trust === "VERIFIED" ? (
          <span className="text-[10.5px] font-semibold text-success">✓ Verified</span>
        ) : (
          <span className="text-[10.5px] font-semibold" style={{ color: DIAGNOSTIC_EDGE }}>
            Diagnostic
          </span>
        )}
      </span>
    </button>
  );
}

export function RegulatoryMapGraph({
  project,
  items,
  relationships,
  selectedId,
  selectedEdgeId,
  onSelect,
  onSelectEdge,
  className,
}: {
  project: { name: string; industry: string; location: string };
  items: RegulatoryItem[];
  relationships: DependencyRelationship[];
  selectedId: string | null;
  selectedEdgeId: string | null;
  onSelect: (id: string) => void;
  onSelectEdge: (edge: MapEdge) => void;
  className?: string;
}) {
  const layout = useMemo(() => layoutRegulatoryMap(items, relationships), [items, relationships]);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 16, y: 16 });
  const [hover, setHover] = useState<{ edge: MapEdge; x: number; y: number } | null>(null);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  const fit = useCallback(() => {
    const el = containerRef.current;
    if (!el || layout.width === 0) return;
    const s = Math.min((el.clientWidth - 24) / layout.width, (el.clientHeight - 24) / layout.height, 1);
    const next = Math.max(0.5, s);
    setScale(next);
    setPan({
      x: Math.max(12, (el.clientWidth - layout.width * next) / 2),
      y: Math.max(12, (el.clientHeight - layout.height * next) / 2),
    });
  }, [layout.width, layout.height]);

  useEffect(() => {
    fit();
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => fit());
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit]);

  const connected = useMemo(() => {
    if (!selectedId) return null;
    const set = new Set<string>([selectedId]);
    for (const e of layout.edges) {
      if (e.from.id === selectedId) set.add(e.to.id);
      if (e.to.id === selectedId) set.add(e.from.id);
    }
    return set;
  }, [layout.edges, selectedId]);

  const px1 = layout.project.x + PROJECT_W;
  const py = layout.project.y + PROJECT_H / 2;

  return (
    <div className={cn("relative overflow-hidden bg-surface-sunken", className)}>
      <div className="pointer-events-none absolute inset-0 grid-faint" aria-hidden />
      <div
        ref={containerRef}
        className="relative h-full w-full cursor-grab active:cursor-grabbing"
        onMouseDown={(e) => {
          drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
        }}
        onMouseMove={(e) => {
          if (!drag.current) return;
          setPan({
            x: drag.current.px + (e.clientX - drag.current.x),
            y: drag.current.py + (e.clientY - drag.current.y),
          });
        }}
        onMouseUp={() => (drag.current = null)}
        onMouseLeave={() => (drag.current = null)}
      >
        <div
          className="absolute origin-top-left"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            width: layout.width,
            height: layout.height,
          }}
        >
          {/* classification family brackets (no arrows: alternatives, not dependencies) */}
          {layout.families.map((f) => (
            <div
              key={f.id}
              className="absolute rounded-sm border border-dashed border-border-strong bg-surface/60"
              style={{ left: f.x, top: f.y, width: f.w, height: f.h }}
            >
              <span className="absolute left-2 top-[3px] text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {f.label}
              </span>
            </div>
          ))}

          <svg width={layout.width} height={layout.height} className="absolute left-0 top-0 overflow-visible">
            <defs>
              <marker id="rm-arrow-v" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
                <path d="M0,1 L9,5 L0,9 z" fill={VERIFIED_EDGE} />
              </marker>
              <marker id="rm-arrow-d" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                <path d="M0,1 L9,5 L0,9 z" fill={DIAGNOSTIC_EDGE} />
              </marker>
            </defs>

            {/* project evaluation links: thin, light, NOT dependencies */}
            {layout.nodes.map((n) => (
              <path
                key={`p-${n.id}`}
                d={curve(px1, py, n.x, n.y + NODE_H / 2)}
                fill="none"
                stroke="var(--border-strong)"
                strokeWidth={1}
                strokeOpacity={connected && !connected.has(n.id) ? 0.25 : 0.7}
              />
            ))}

            {layout.edges.map((e) => {
              const id = e.rel.dependency_id;
              const verified = isVerifiedPrerequisite(e.rel);
              const x1 = e.from.x + NODE_W;
              const y1 = e.from.y + NODE_H / 2;
              const x2 = e.to.x;
              const y2 = e.to.y + NODE_H / 2;
              const d = curve(x1, y1, x2, y2);
              const active = selectedEdgeId === id || hover?.edge.rel.dependency_id === id;
              const dim = connected && !(connected.has(e.from.id) && connected.has(e.to.id)) && !active;
              const color = verified ? VERIFIED_EDGE : DIAGNOSTIC_EDGE;
              return (
                <g key={id} opacity={dim ? 0.3 : 1}>
                  <path
                    d={d}
                    fill="none"
                    stroke={color}
                    strokeWidth={verified ? (active ? 3 : 2.2) : active ? 2.2 : 1.6}
                    strokeDasharray={verified ? undefined : "6 4"}
                    markerEnd={verified ? "url(#rm-arrow-v)" : "url(#rm-arrow-d)"}
                  />
                  <text
                    x={(x1 + x2) / 2}
                    y={(y1 + y2) / 2 - 6}
                    textAnchor="middle"
                    fontSize={10}
                    fontWeight={600}
                    fill={color}
                    stroke="var(--surface-sunken)"
                    strokeWidth={4}
                    paintOrder="stroke"
                    style={{ pointerEvents: "none" }}
                  >
                    {edgeLabel(e.rel)}
                  </text>
                  <path
                    d={d}
                    fill="none"
                    stroke="transparent"
                    strokeWidth={16}
                    style={{ cursor: "pointer", pointerEvents: "stroke" }}
                    data-edge-id={id}
                    onMouseDown={(ev) => ev.stopPropagation()}
                    onMouseMove={(ev) => {
                      const box = containerRef.current?.getBoundingClientRect();
                      if (box) setHover({ edge: e, x: ev.clientX - box.left, y: ev.clientY - box.top });
                    }}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => onSelectEdge(e)}
                  />
                </g>
              );
            })}
          </svg>

          <div
            className="absolute flex flex-col justify-center rounded-sm border border-primary/40 bg-primary px-3 text-primary-foreground"
            style={{ left: layout.project.x, top: layout.project.y, width: PROJECT_W, height: PROJECT_H }}
          >
            <div className="text-[9.5px] font-semibold uppercase tracking-wider opacity-70">Project</div>
            <div className="line-clamp-2 text-[12.5px] font-semibold leading-snug">{project.name}</div>
            <div className="mt-0.5 truncate text-[10.5px] opacity-80">
              {project.industry}
              {project.location ? ` · ${project.location}` : ""}
            </div>
          </div>

          {layout.nodes.map((n) => (
            <NodeCard
              key={n.id}
              node={n}
              selected={selectedId === n.id}
              dimmed={!!connected && !connected.has(n.id)}
              onSelect={onSelect}
            />
          ))}
        </div>
      </div>

      {hover && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 max-w-[280px] rounded-sm border border-border bg-surface px-3 py-2 text-[11.5px] leading-snug shadow-panel"
          style={{ left: Math.min(hover.x + 14, (containerRef.current?.clientWidth ?? 600) - 296), top: hover.y + 14 }}
        >
          <div
            className="mb-1 text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: isVerifiedPrerequisite(hover.edge.rel) ? VERIFIED_EDGE : DIAGNOSTIC_EDGE }}
          >
            {isVerifiedPrerequisite(hover.edge.rel) ? "Verified prerequisite" : "Diagnostic · requires outcome of"}
          </div>
          {relationshipMeaning(hover.edge.rel, shortTitle(hover.edge.from.item.title), shortTitle(hover.edge.to.item.title))}
          <div className="mt-1 text-muted-foreground">Click for detail</div>
        </div>
      )}

      <div className="absolute bottom-3 right-3 flex items-center gap-px overflow-hidden rounded-sm border border-border bg-surface">
        <button
          type="button"
          onClick={() => setScale((s) => Math.max(0.35, +(s - 0.1).toFixed(2)))}
          className="h-7 w-8 text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="Zoom out"
        >
          −
        </button>
        <span className="tabular w-11 border-x border-border text-center text-[11px] text-muted-foreground">
          {Math.round(scale * 100)}%
        </span>
        <button
          type="button"
          onClick={() => setScale((s) => Math.min(1.6, +(s + 0.1).toFixed(2)))}
          className="h-7 w-8 text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={fit}
          className="h-7 border-l border-border px-2.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          Fit
        </button>
      </div>
    </div>
  );
}

function Swatch({ kind }: { kind: "project" | "verified" | "diagnostic" }) {
  return (
    <svg width="30" height="10" aria-hidden className="shrink-0">
      {kind === "project" && <line x1="0" y1="5" x2="30" y2="5" stroke="var(--border-strong)" strokeWidth="1" />}
      {kind === "verified" && (
        <>
          <line x1="0" y1="5" x2="24" y2="5" stroke={VERIFIED_EDGE} strokeWidth="2.2" />
          <path d="M22,1.5 L29,5 L22,8.5 z" fill={VERIFIED_EDGE} />
        </>
      )}
      {kind === "diagnostic" && (
        <>
          <line x1="0" y1="5" x2="24" y2="5" stroke={DIAGNOSTIC_EDGE} strokeWidth="1.6" strokeDasharray="5 3" />
          <path d="M22,1.5 L29,5 L22,8.5 z" fill={DIAGNOSTIC_EDGE} />
        </>
      )}
    </svg>
  );
}

export function MapLegend() {
  const dots: { tone: LandscapeTone; label: string }[] = [
    { tone: "success", label: "Applicable" },
    { tone: "warning", label: "Needs information" },
    { tone: "neutral", label: "Not applicable" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[11.5px] text-muted-foreground">
      {dots.map((d) => (
        <span key={d.label} className="flex items-center gap-1.5">
          <span aria-hidden className={cn("h-[8px] w-[8px] rounded-full", toneDot[d.tone])} />
          {d.label}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <span className="font-semibold text-success">✓ Verified</span> requirement
      </span>
      <span className="flex items-center gap-1.5">
        <span className="font-semibold" style={{ color: DIAGNOSTIC_EDGE }}>
          Diagnostic
        </span>{" "}
        requirement
      </span>
      <span className="flex items-center gap-1.5">
        <Swatch kind="project" /> Project evaluation link
      </span>
      <span className="flex items-center gap-1.5">
        <Swatch kind="verified" /> Verified prerequisite
      </span>
      <span className="flex items-center gap-1.5">
        <Swatch kind="diagnostic" /> Diagnostic outcome dependency
      </span>
    </div>
  );
}

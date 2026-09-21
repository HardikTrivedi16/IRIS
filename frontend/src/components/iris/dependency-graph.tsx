import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { GraphEdge, GraphNode, Status } from "@/lib/iris/types";
import { StatusDot, statusMeta } from "@/components/iris/status";

const NODE_W = 208;
const NODE_H = 74;
const COL_GAP = 86;
const ROW_GAP = 26;

export interface LaidOutNode extends GraphNode {
  x: number;
  y: number;
  level: number;
}

export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const incoming = new Map<string, string[]>();
  nodes.forEach((n) => incoming.set(n.id, []));
  edges.forEach((e) => {
    if (byId.has(e.from) && byId.has(e.to)) incoming.get(e.to)!.push(e.from);
  });

  const level = new Map<string, number>();
  const resolve = (id: string, seen: Set<string>): number => {
    if (level.has(id)) return level.get(id)!;
    if (seen.has(id)) return 0;
    seen.add(id);
    const parents = incoming.get(id) ?? [];
    const value = parents.length
      ? Math.max(...parents.map((p) => resolve(p, seen))) + 1
      : 0;
    level.set(id, value);
    return value;
  };
  nodes.forEach((n) => resolve(n.id, new Set()));

  const columns = new Map<number, GraphNode[]>();
  nodes.forEach((n) => {
    const l = level.get(n.id) ?? 0;
    columns.set(l, [...(columns.get(l) ?? []), n]);
  });

  const maxRows = Math.max(...[...columns.values()].map((c) => c.length));
  const height = maxRows * NODE_H + (maxRows - 1) * ROW_GAP;

  const laid: LaidOutNode[] = [];
  [...columns.keys()]
    .sort((a, b) => a - b)
    .forEach((l) => {
      const col = columns.get(l)!;
      const colHeight = col.length * NODE_H + (col.length - 1) * ROW_GAP;
      const offset = (height - colHeight) / 2;
      col.forEach((n, i) => {
        laid.push({
          ...n,
          level: l,
          x: l * (NODE_W + COL_GAP),
          y: offset + i * (NODE_H + ROW_GAP),
        });
      });
    });

  const levels = [...columns.keys()].length;
  return {
    nodes: laid,
    width: levels * NODE_W + (levels - 1) * COL_GAP,
    height,
    levelOf: level,
  };
}

const statusStroke: Record<Status, string> = {
  ready: "var(--success)",
  attention: "var(--warning)",
  blocked: "var(--destructive)",
  "not-ready": "var(--border-strong)",
  "not-applicable": "var(--border-strong)",
};

function NodeCard({
  node,
  selected,
  dimmed,
  onSelect,
}: {
  node: LaidOutNode;
  selected: boolean;
  dimmed: boolean;
  onSelect: (node: LaidOutNode) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(node)}
      style={{ left: node.x, top: node.y, width: NODE_W, height: NODE_H }}
      className={cn(
        "focus-ring absolute flex flex-col justify-between rounded-sm border bg-surface px-3 py-2.5 text-left transition-all duration-150",
        selected
          ? "border-info shadow-raised ring-1 ring-info/40"
          : "border-border hover:border-border-strong hover:shadow-panel",
        dimmed && "opacity-35",
        node.type === "milestone" &&
          !selected &&
          "border-dashed bg-surface-sunken",
      )}
    >
      <div className="flex items-start gap-2">
        <StatusDot status={node.status} className="mt-[5px]" />
        <span className="line-clamp-2 text-[12.5px] font-medium leading-snug">
          {node.label}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 text-[10.5px] text-muted-foreground">
        <span className="truncate">
          {node.authority ??
            (node.type === "milestone" ? "Project milestone" : "—")}
        </span>
        {node.documents ? (
          <span className="tabular shrink-0">
            {node.documents.complete}/{node.documents.total} docs
          </span>
        ) : null}
      </div>
    </button>
  );
}

export function DependencyGraph({
  nodes,
  edges,
  selectedId,
  onSelect,
  focusIds,
  highlightPath,
  className,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  onSelect: (node: GraphNode) => void;
  focusIds?: Set<string> | null;
  highlightPath?: Set<string> | null;
  className?: string;
}) {
  const layout = useMemo(() => layoutGraph(nodes, edges), [nodes, edges]);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 24, y: 24 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(
    null,
  );

  const fit = useCallback(() => {
    const el = containerRef.current;
    if (!el || layout.width === 0) return;
    const s = Math.min(
      (el.clientWidth - 56) / layout.width,
      (el.clientHeight - 56) / layout.height,
      1,
    );
    const next = Math.max(0.35, s);
    setScale(next);
    setPan({
      x: (el.clientWidth - layout.width * next) / 2,
      y: (el.clientHeight - layout.height * next) / 2,
    });
  }, [layout.width, layout.height]);

  useEffect(() => {
    fit();
  }, [fit]);

  const visible = useMemo(() => {
    if (!focusIds) return layout.nodes;
    return layout.nodes;
  }, [layout.nodes, focusIds]);

  const nodePos = useMemo(
    () => new Map(layout.nodes.map((n) => [n.id, n])),
    [layout.nodes],
  );

  const connected = useMemo(() => {
    if (!selectedId) return null;
    const set = new Set<string>([selectedId]);
    edges.forEach((e) => {
      if (e.from === selectedId) set.add(e.to);
      if (e.to === selectedId) set.add(e.from);
    });
    return set;
  }, [edges, selectedId]);

  return (
    <div
      className={cn("relative overflow-hidden bg-surface-sunken", className)}
    >
      <div
        className="pointer-events-none absolute inset-0 grid-faint"
        aria-hidden
      />

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
          <svg
            width={layout.width}
            height={layout.height}
            className="absolute left-0 top-0 overflow-visible"
            aria-hidden
          >
            <defs>
              <marker
                id="iris-arrow"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="7"
                markerHeight="7"
                orient="auto"
              >
                <path d="M0,1 L7,4 L0,7 z" fill="var(--border-strong)" />
              </marker>
              <marker
                id="iris-arrow-active"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="7"
                markerHeight="7"
                orient="auto"
              >
                <path d="M0,1 L7,4 L0,7 z" fill="var(--info)" />
              </marker>
            </defs>
            {edges.map((e) => {
              const a = nodePos.get(e.from);
              const b = nodePos.get(e.to);
              if (!a || !b) return null;
              const x1 = a.x + NODE_W;
              const y1 = a.y + NODE_H / 2;
              const x2 = b.x;
              const y2 = b.y + NODE_H / 2;
              const mid = x1 + Math.max(24, (x2 - x1) / 2);
              const onPath =
                highlightPath?.has(e.from) && highlightPath?.has(e.to);
              const isActive =
                onPath ||
                (!!selectedId &&
                  (e.from === selectedId || e.to === selectedId));
              const blockedEdge = nodePos.get(e.from)?.status === "blocked";
              return (
                <path
                  key={`${e.from}-${e.to}`}
                  d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
                  fill="none"
                  stroke={
                    isActive
                      ? "var(--info)"
                      : blockedEdge
                        ? "var(--destructive)"
                        : "var(--border-strong)"
                  }
                  strokeWidth={isActive ? 1.6 : 1}
                  strokeOpacity={
                    selectedId && !isActive
                      ? 0.3
                      : blockedEdge && !isActive
                        ? 0.55
                        : 0.8
                  }
                  strokeDasharray={blockedEdge && !isActive ? "4 3" : undefined}
                  markerEnd={
                    isActive ? "url(#iris-arrow-active)" : "url(#iris-arrow)"
                  }
                />
              );
            })}
          </svg>

          {visible.map((n) => (
            <NodeCard
              key={n.id}
              node={n}
              selected={selectedId === n.id}
              dimmed={
                (!!focusIds && !focusIds.has(n.id)) ||
                (!!connected && !connected.has(n.id) && !focusIds)
              }
              onSelect={onSelect}
            />
          ))}
        </div>
      </div>

      <div className="absolute bottom-3 right-3 flex items-center gap-px overflow-hidden rounded-sm border border-border bg-surface">
        <button
          type="button"
          onClick={() => setScale((s) => Math.min(1.6, +(s + 0.1).toFixed(2)))}
          className="h-7 w-8 text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="Zoom in"
        >
          +
        </button>
        <span className="tabular w-10 border-x border-border text-center text-[11px] text-muted-foreground">
          {Math.round(scale * 100)}%
        </span>
        <button
          type="button"
          onClick={() => setScale((s) => Math.max(0.35, +(s - 0.1).toFixed(2)))}
          className="h-7 w-8 text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="Zoom out"
        >
          −
        </button>
        <button
          type="button"
          onClick={fit}
          className="h-7 border-l border-border px-2.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          Fit view
        </button>
        <button
          type="button"
          onClick={() => {
            setScale(1);
            setPan({ x: 24, y: 24 });
          }}
          className="h-7 border-l border-border px-2.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          Reset
        </button>
      </div>

      <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-x-3.5 gap-y-1.5 rounded-sm border border-border bg-surface px-3 py-2">
        {(
          [
            "ready",
            "attention",
            "blocked",
            "not-ready",
            "not-applicable",
          ] as Status[]
        )
          .filter((s, i, arr) => arr.indexOf(s) === i)
          .map((s) => (
            <span
              key={s}
              className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
            >
              <span
                className="h-[6px] w-[6px] rounded-full"
                style={{ background: statusStroke[s] }}
                aria-hidden
              />
              {statusMeta[s].label}
            </span>
          ))}
      </div>
    </div>
  );
}

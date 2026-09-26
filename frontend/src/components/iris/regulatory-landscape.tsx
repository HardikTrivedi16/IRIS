import { cn } from "@/lib/utils";
import {
  shortTitle,
  type Landscape,
  type LandscapeNode,
  type LandscapeTone,
  type TrustState,
} from "@/lib/iris/regulatory-landscape";

const toneCard: Record<LandscapeTone, string> = {
  success: "border-success/30 bg-success-surface",
  warning: "border-warning/35 bg-warning-surface",
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

function TrustMark({ trust }: { trust: TrustState }) {
  return trust === "VERIFIED" ? (
    <span className="rounded-sm border border-success/30 px-1 py-px text-[9.5px] font-semibold uppercase tracking-wide text-success">
      Verified
    </span>
  ) : (
    <span className="rounded-sm border border-dashed border-info/50 px-1 py-px text-[9.5px] font-semibold uppercase tracking-wide text-info">
      Diagnostic
    </span>
  );
}

function NodeCard({
  node,
  selected,
  onSelect,
}: {
  node: LandscapeNode;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const { item, view } = node;
  return (
    <button
      type="button"
      onClick={() => onSelect(item.requirementId)}
      aria-pressed={selected}
      title={item.title}
      className={cn(
        "focus-ring w-full rounded-sm border px-2.5 py-2 text-left transition-shadow hover:shadow-sm",
        toneCard[view.tone],
        selected && "ring-2 ring-info",
      )}
    >
      <span className="block text-[12.5px] font-medium leading-snug text-foreground [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2] overflow-hidden">
        {shortTitle(item.title)}
      </span>
      <span className="mt-1.5 flex items-center justify-between gap-2">
        <span className={cn("flex items-center gap-1.5 text-[11px] font-medium", toneText[view.tone])}>
          <span aria-hidden className={cn("h-[6px] w-[6px] rounded-full", toneDot[view.tone])} />
          {view.label}
        </span>
        <TrustMark trust={view.trust} />
      </span>
      {node.otherStages.length > 0 && (
        <span className="mt-1 block text-[10.5px] text-muted-foreground">
          Also: {node.otherStages.join(", ")}
        </span>
      )}
    </button>
  );
}

/**
 * Lane (regulatory domain) x column (lifecycle stage) grid. Pure CSS grid: nothing is positioned
 * absolutely, so nodes cannot overlap, and there are NO edges — grouping is the only relationship
 * shown.
 */
export function RegulatoryLandscape({
  landscape,
  selectedId,
  onSelect,
}: {
  landscape: Landscape;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const cols = landscape.columns.length;
  return (
    <div className="overflow-x-auto">
      <div
        className="grid min-w-[760px] gap-px bg-border"
        style={{ gridTemplateColumns: `148px repeat(${cols}, minmax(200px, 1fr))` }}
      >
        <div className="bg-surface-sunken px-3 py-2 label-meta">Authority / domain</div>
        {landscape.columns.map((c) => (
          <div key={c.id} className="bg-surface-sunken px-3 py-2 label-meta">
            {c.label}
          </div>
        ))}

        {landscape.lanes.map((lane) => (
          <LaneRow
            key={lane.id}
            lane={lane}
            columns={landscape.columns}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

function LaneRow({
  lane,
  columns,
  selectedId,
  onSelect,
}: {
  lane: Landscape["lanes"][number];
  columns: Landscape["columns"];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <>
      <div className="bg-surface px-3 py-3">
        <div className="text-[12.5px] font-semibold leading-snug">{lane.label}</div>
        <div className="mt-0.5 text-[11px] text-muted-foreground tabular">
          {lane.count} requirement{lane.count === 1 ? "" : "s"}
        </div>
      </div>
      {columns.map((c) => (
        <div key={c.id} className="space-y-2 bg-surface p-2">
          {(lane.cells[c.id] ?? []).map((n) => (
            <NodeCard
              key={n.item.requirementId}
              node={n}
              selected={selectedId === n.item.requirementId}
              onSelect={onSelect}
            />
          ))}
        </div>
      ))}
    </>
  );
}

export function LandscapeLegend() {
  const chips: { tone: LandscapeTone; label: string }[] = [
    { tone: "success", label: "Applicable" },
    { tone: "warning", label: "Needs information / review" },
    { tone: "neutral", label: "Not applicable" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[11.5px] text-muted-foreground">
      {chips.map((c) => (
        <span key={c.label} className="flex items-center gap-1.5">
          <span aria-hidden className={cn("h-[8px] w-[8px] rounded-full", toneDot[c.tone])} />
          {c.label}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <TrustMark trust="VERIFIED" /> authoritative result
      </span>
      <span className="flex items-center gap-1.5">
        <TrustMark trust="DIAGNOSTIC" /> non-authoritative analysis
      </span>
    </div>
  );
}

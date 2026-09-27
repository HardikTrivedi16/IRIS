import { useState } from "react";
import { Tag } from "@/components/iris/status";
import { finalStateMeta } from "@/lib/iris/decision-states";
import { stageLabel, type RegulatoryItem } from "@/lib/iris/regulatory-items";
import type { EvaluationMode } from "@/lib/iris/api-client";

/** Which evaluation the list is organised around. DIAGNOSTIC is the labelled,
 * non-authoritative evaluation of the DRAFT rules; PRODUCTION is the
 * authoritative determination (withheld while a Rule Version is DRAFT). */
export type Lens = "DIAGNOSTIC" | "PRODUCTION";

type OpenProof = ((requirementId: string, mode: EvaluationMode) => void) | undefined;

const DIAG_ORDER: Record<string, number> = {
  APPLICABLE: 0,
  NOT_APPLICABLE: 1,
  REQUIRES_REVIEW: 2,
  REQUIRES_INFORMATION: 3,
};

function diagRank(i: RegulatoryItem) {
  return DIAG_ORDER[i.diagnostic?.finalState ?? ""] ?? 4;
}

/** One compact line: a reason if the engine gave one, else a missing-facts summary. */
function summaryLine(item: RegulatoryItem, showingDiagnostic: boolean): string | null {
  const missing = item.diagnostic?.missingFactKeys ?? [];
  if (showingDiagnostic && missing.length > 0) {
    return missing.length === 1
      ? `Missing: ${missing[0]}`
      : `Missing ${missing.length} facts: ${missing[0]} +${missing.length - 1} more`;
  }
  const reason = showingDiagnostic
    ? (item.diagnostic?.reviewReason ?? item.diagnostic?.reasonText)
    : item.production.reasonText;
  return reason ?? null;
}

function ItemRow({
  item,
  lens,
  onOpenProof,
  forceDiagnostic,
}: {
  item: RegulatoryItem;
  lens: Lens;
  onOpenProof: OpenProof;
  /** Row is inside a Production-lens group that itself shows diagnostic knowledge
   * (e.g. "Additional diagnostic requirements") — trust badge reads DIAGNOSTIC
   * even though the surrounding lens is PRODUCTION. */
  forceDiagnostic?: boolean | undefined;
}) {
  const [open, setOpen] = useState(false);
  const isDiagnostic = !!forceDiagnostic;
  const prod = finalStateMeta(item.production.finalState);
  const diag = item.diagnostic ? finalStateMeta(item.diagnostic.finalState) : null;
  const missing = item.diagnostic?.missingFactKeys ?? [];
  const showDiagnostic = (lens === "DIAGNOSTIC" || isDiagnostic) && diag !== null;
  const view = showDiagnostic && diag ? diag : prod;
  const line = summaryLine(item, showDiagnostic);
  const hasDetail = missing.length > 0 || !!item.ruleVersionId;

  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-1.5">
        <div className="min-w-0">
          <p className="text-[13.5px] font-medium leading-snug">{item.title}</p>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            {item.authorityName}
            {item.lifecycleStageIds.length > 0 &&
              ` · ${item.lifecycleStageIds.map(stageLabel).join(", ")}`}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <Tag tone={view.tone}>{view.label}</Tag>
          {showDiagnostic ? (
            <span className="rounded-sm border border-dashed border-info/50 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-info">
              Diagnostic
            </span>
          ) : (
            <span className="rounded-sm border border-success/30 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-success">
              Verified
            </span>
          )}
        </div>
      </div>

      {line && (
        <p className="mt-1.5 line-clamp-2 text-[12px] text-foreground/75">{line}</p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {onOpenProof && (
          <button
            type="button"
            onClick={() => onOpenProof(item.requirementId, showDiagnostic ? "NON_PRODUCTION" : "PRODUCTION")}
            className="text-[12px] font-medium text-info hover:opacity-80"
          >
            Decision proof →
          </button>
        )}
        {hasDetail && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="text-[12px] font-medium text-muted-foreground hover:text-foreground"
          >
            {open ? "Hide details" : "View details"}
          </button>
        )}
      </div>

      {open && (
        <div className="mt-2.5 space-y-1.5 border-l-2 border-border pl-3 text-[11.5px] text-muted-foreground">
          <p className="font-mono">
            {item.requirementId} · {item.ruleVersionId ?? "no rule version"}
            {item.ruleVersionStatus ? ` (${item.ruleVersionStatus})` : ""}
          </p>
          {!showDiagnostic && lens === "PRODUCTION" && diag && (
            <p>
              Diagnostic (non-authoritative): <span className="font-medium text-foreground/80">{diag.label}</span>
            </p>
          )}
          {missing.length > 0 && (
            <div>
              <p className="font-semibold uppercase tracking-[0.06em] text-warning">
                Additional information required
              </p>
              <ul className="mt-0.5">
                {missing.map((k) => (
                  <li key={k} className="font-mono">
                    {k}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {item.presentFactKeys.length > 0 && (
            <p>
              Facts used: <span className="font-mono">{item.presentFactKeys.join(", ")}</span>
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function Group({
  label,
  hint,
  items,
  lens,
  onOpenProof,
  collapsed,
  forceDiagnostic,
}: {
  label: string;
  hint?: string;
  items: RegulatoryItem[];
  lens: Lens;
  onOpenProof: OpenProof;
  collapsed?: boolean;
  forceDiagnostic?: boolean | undefined;
}) {
  if (items.length === 0) return null;
  const body = (
    <ul className="divide-y divide-border">
      {items.map((i) => (
        <ItemRow
          key={i.requirementId}
          item={i}
          lens={lens}
          onOpenProof={onOpenProof}
          forceDiagnostic={forceDiagnostic}
        />
      ))}
    </ul>
  );
  const heading = (
    <>
      <span className="label-meta">{label}</span>
      <span className="tabular ml-2 text-[11px] text-muted-foreground">{items.length}</span>
      {hint && <span className="ml-3 text-[11px] text-muted-foreground">{hint}</span>}
    </>
  );
  if (collapsed) {
    return (
      <details className="border-b border-border last:border-b-0">
        <summary className="cursor-pointer bg-surface-sunken/70 px-5 py-2">{heading}</summary>
        {body}
      </details>
    );
  }
  return (
    <div className="border-b border-border last:border-b-0">
      <div className="bg-surface-sunken/70 px-5 py-2">{heading}</div>
      {body}
    </div>
  );
}

/**
 * Regulatory items grouped by a generic, engine-derived relevance signal —
 * never by sector or requirement id.
 *
 * PRODUCTION (the default, "what applies now"): Applicable and Needs
 * information are open by default; Not applicable and the DRAFT-rule
 * "Additional diagnostic requirements" both collapse behind a one-line
 * summary, so a five-second read shows only what currently matters.
 *
 * DIAGNOSTIC ("full diagnostic analysis"): the complete non-authoritative
 * evaluation of every requirement, grouped by relevance — for technical
 * review, not the default jury view.
 */
export function RegulatoryItemList({
  items,
  lens,
  onOpenProof,
}: {
  items: RegulatoryItem[];
  lens: Lens;
  onOpenProof?: ((requirementId: string, mode: EvaluationMode) => void) | undefined;
}) {
  if (lens === "PRODUCTION") {
    const authoritative = items.filter((i) => i.production.authoritative);
    const applicable = authoritative.filter((i) => i.production.finalState === "APPLICABLE");
    const notApplicable = authoritative.filter((i) => i.production.finalState === "NOT_APPLICABLE");
    const needsInfo = authoritative.filter(
      (i) => i.production.finalState !== "APPLICABLE" && i.production.finalState !== "NOT_APPLICABLE",
    );
    const withheld = items.filter((i) => !i.production.authoritative);
    return (
      <div>
        <Group label="Applicable" items={applicable} lens={lens} onOpenProof={onOpenProof} />
        <Group label="Needs information" items={needsInfo} lens={lens} onOpenProof={onOpenProof} />
        <Group label="Not applicable" items={notApplicable} lens={lens} onOpenProof={onOpenProof} collapsed />
        <Group
          label="Additional diagnostic requirements"
          hint="Governing Rule Version not yet ACTIVE — non-authoritative"
          items={withheld}
          lens={lens}
          onOpenProof={onOpenProof}
          collapsed
          forceDiagnostic
        />
      </div>
    );
  }
  const by = (r: RegulatoryItem["relevance"]) =>
    items
      .filter((i) => i.relevance === r)
      .sort((a, b) => diagRank(a) - diagRank(b) || a.requirementId.localeCompare(b.requirementId));
  return (
    <div>
      <Group
        label="Matched to this project"
        hint="Enough facts recorded to evaluate"
        items={by("MATCHED")}
        lens={lens}
        onOpenProof={onOpenProof}
      />
      <Group
        label="Needs information or review"
        items={by("NEEDS_INFORMATION")}
        lens={lens}
        onOpenProof={onOpenProof}
      />
      <Group
        label="Other requirements — not yet evaluable"
        hint="Engine requires more information; few or none of their facts are recorded for this project"
        items={by("OTHER")}
        lens={lens}
        onOpenProof={onOpenProof}
        collapsed
      />
    </div>
  );
}

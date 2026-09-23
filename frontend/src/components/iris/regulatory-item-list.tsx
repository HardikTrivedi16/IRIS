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

function ItemRow({
  item,
  lens,
  onOpenProof,
}: {
  item: RegulatoryItem;
  lens: Lens;
  onOpenProof: OpenProof;
}) {
  const prod = finalStateMeta(item.production.finalState);
  const diag = item.diagnostic ? finalStateMeta(item.diagnostic.finalState) : null;
  const missing = item.diagnostic?.missingFactKeys ?? [];
  const showDiagnostic = lens === "DIAGNOSTIC" && diag !== null;
  return (
    <li className="px-5 py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <p className="text-[13px] font-medium leading-snug">{item.title}</p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            {item.requirementId} · {item.ruleVersionId ?? "no rule version"}
            {item.ruleVersionStatus ? ` (${item.ruleVersionStatus})` : ""}
          </p>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            {item.authorityName}
            {item.lifecycleStageIds.length > 0 &&
              ` · ${item.lifecycleStageIds.map(stageLabel).join(", ")}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {showDiagnostic && diag ? (
            <>
              <Tag tone="info">Diagnostic — non-authoritative</Tag>
              <Tag tone={diag.tone}>{diag.label}</Tag>
            </>
          ) : (
            <Tag tone={prod.tone}>{prod.label}</Tag>
          )}
        </div>
      </div>

      {lens === "DIAGNOSTIC" && (
        <p className="mt-1.5 text-[11.5px] text-muted-foreground">
          Production: <span className="font-medium">{prod.label}</span>
        </p>
      )}

      {showDiagnostic &&
        item.diagnostic?.finalState === "REQUIRES_REVIEW" &&
        item.diagnostic.reviewReason && (
          <p className="mt-2 border-l-2 border-warning pl-3 text-[12px] text-foreground/80">
            {item.diagnostic.reviewReason}
          </p>
        )}

      {showDiagnostic && missing.length > 0 && (
        <div className="mt-2 border-l-2 border-warning pl-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-warning">
            Additional information required
          </p>
          <ul className="mt-0.5">
            {missing.map((k) => (
              <li key={k} className="font-mono text-[11px] text-muted-foreground">
                {k}
              </li>
            ))}
          </ul>
        </div>
      )}

      {onOpenProof && (
        <button
          type="button"
          onClick={() =>
            onOpenProof(item.requirementId, lens === "DIAGNOSTIC" ? "NON_PRODUCTION" : "PRODUCTION")
          }
          className="mt-2 text-[12px] font-medium text-info hover:opacity-80"
        >
          View decision proof →
        </button>
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
}: {
  label: string;
  hint?: string;
  items: RegulatoryItem[];
  lens: Lens;
  onOpenProof: OpenProof;
  collapsed?: boolean;
}) {
  if (items.length === 0) return null;
  const body = (
    <ul className="divide-y divide-border">
      {items.map((i) => (
        <ItemRow key={i.requirementId} item={i} lens={lens} onOpenProof={onOpenProof} />
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
 * never by sector or requirement id. The DIAGNOSTIC lens is organised by
 * relevance; the PRODUCTION lens by whether an authoritative determination
 * exists.
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
    const withheld = items.filter((i) => !i.production.authoritative);
    return (
      <div>
        <Group
          label="Authoritative determinations"
          items={authoritative}
          lens={lens}
          onOpenProof={onOpenProof}
        />
        <Group
          label="Awaiting verified regulatory knowledge"
          hint="Production result withheld — the governing Rule Version is not ACTIVE."
          items={withheld}
          lens={lens}
          onOpenProof={onOpenProof}
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

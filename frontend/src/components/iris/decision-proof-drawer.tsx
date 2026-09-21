import { useQuery } from "@tanstack/react-query";
import {
  BackendUnavailableError,
  irisApi,
  type ConditionTreeNode,
  type DecisionProof,
  type EvaluationMode,
} from "@/lib/iris/api-client";
import { Drawer, DrawerSection } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import { finalStateMeta } from "@/lib/iris/decision-states";
import { formatFactValue } from "@/lib/iris/facts";
import { cn } from "@/lib/utils";

export interface ProofTarget {
  requirementId: string;
  evaluationMode: EvaluationMode;
  /** When set, the proof describes a hypothetical (unsaved) fact set. */
  hypotheticalFacts?: Record<string, unknown>;
}

const RESULT_TONE: Record<string, string> = {
  TRUE: "text-success",
  FALSE: "text-muted-foreground",
  UNKNOWN: "text-warning",
};

function fmt(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map((x) => formatFactValue(x)).join(", ")}]`;
  return formatFactValue(v);
}

/** Renders the engine's condition tree exactly as the engine reported it —
 * composite operators with their children, leaves with the comparison, the
 * project's actual value and the Kleene result. Nothing is re-evaluated. */
function ConditionTree({ node, depth = 0 }: { node: ConditionTreeNode; depth?: number }) {
  const isComposite = node.predicate_type === "COMPOSITE";
  return (
    <div className={cn(depth > 0 && "ml-3 border-l border-border pl-3")}>
      <div className="py-1">
        {isComposite ? (
          <p className="text-[12px]">
            <span className="font-mono font-semibold">{node.operator}</span>{" "}
            <span className="font-mono text-[10.5px] text-muted-foreground">{node.condition_id}</span>{" "}
            <span className={cn("font-mono text-[11px] font-semibold", RESULT_TONE[node.result ?? ""])}>
              → {node.result ?? "—"}
            </span>
          </p>
        ) : (
          <div className="text-[12px]">
            <p>
              <span className="font-mono text-[10.5px] text-muted-foreground">{node.condition_id}</span>{" "}
              <span className="font-mono">{node.target_variable_key}</span>{" "}
              <span className="font-mono font-semibold">{node.operator}</span>{" "}
              <span className="font-mono">{fmt(node.expected_value)}</span>
            </p>
            <p className="mt-0.5 text-[11.5px] text-muted-foreground">
              project value:{" "}
              <span className="tabular font-medium text-foreground">
                {fmt(node.actual_project_value)}
              </span>{" "}
              <span className={cn("font-mono font-semibold", RESULT_TONE[node.result ?? ""])}>
                → {node.result ?? "—"}
              </span>
              {node.missing_fact_keys.length > 0 && (
                <span className="text-warning"> (missing)</span>
              )}
              {node.error && <span className="text-destructive"> · error: {node.error}</span>}
            </p>
          </div>
        )}
      </div>
      {node.children.map((c) => (
        <ConditionTree key={c.condition_id} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}

function MappingList({ mapping }: { mapping: Record<string, string> }) {
  const entries = Object.entries(mapping);
  if (!entries.length) return <p className="text-[12px] text-muted-foreground">—</p>;
  return (
    <ul className="space-y-0.5">
      {entries.map(([k, v]) => (
        <li key={k} className="font-mono text-[11.5px]">
          {k} → {v}
        </li>
      ))}
    </ul>
  );
}

function IdList({ label, ids }: { label: string; ids: (string | null)[] }) {
  const present = ids.filter(Boolean) as string[];
  return (
    <div className="flex gap-3 text-[12px]">
      <span className="w-[120px] shrink-0 text-muted-foreground">{label}</span>
      <span className="font-mono text-[11.5px]">{present.length ? present.join(", ") : "—"}</span>
    </div>
  );
}

function ProofBody({ proof }: { proof: DecisionProof }) {
  const meta = finalStateMeta(proof.outcome.final_state);
  const id = proof.identity;
  return (
    <>
      <DrawerSection label="Outcome">
        <div className="flex flex-wrap items-center gap-1.5">
          <Tag tone={meta.tone}>{meta.label}</Tag>
          <Tag tone={proof.outcome.evaluation_mode === "PRODUCTION" ? "neutral" : "info"}>
            {proof.outcome.evaluation_mode === "PRODUCTION" ? "Production" : "Diagnostic — non-authoritative"}
          </Tag>
          {proof.fact_basis === "HYPOTHETICAL" && <Tag tone="warning">Hypothetical facts — not saved</Tag>}
        </div>
        {proof.outcome.reason_text && (
          <p className="mt-2 text-[12.5px] leading-relaxed">{proof.outcome.reason_text}</p>
        )}
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Outcome text is the Rule Version's own authored wording.
        </p>
      </DrawerSection>

      {proof.refuses_to_guess && (
        <DrawerSection label="IRIS refuses to guess">
          <div className="border-l-2 border-warning pl-3">
            <ul className="space-y-1">
              {proof.refusal_reasons.map((r, i) => (
                <li key={i} className="text-[12.5px] leading-relaxed">{r}</li>
              ))}
            </ul>
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              A definite answer is withheld rather than assumed.
            </p>
          </div>
        </DrawerSection>
      )}

      {proof.fact_basis === "HYPOTHETICAL" && (
        <DrawerSection label="Hypothetical values used">
          <ul>
            {Object.entries(proof.hypothetical_facts).map(([k, v]) => (
              <li key={k} className="font-mono text-[11.5px]">{k} = {fmt(v)}</li>
            ))}
          </ul>
        </DrawerSection>
      )}

      <DrawerSection label="Project facts the rules read">
        {proof.facts_used.length === 0 ? (
          <p className="text-[12px] text-muted-foreground">
            None — the evaluation did not reach condition logic.
          </p>
        ) : (
          <table className="w-full text-left text-[12px]">
            <tbody className="divide-y divide-border">
              {proof.facts_used.map((f) => (
                <tr key={f.key}>
                  <td className="py-1.5 pr-3 font-mono text-[11.5px]">{f.key}</td>
                  <td className="py-1.5 text-right">
                    {f.provided ? (
                      <span className="tabular font-medium">{fmt(f.value)}</span>
                    ) : (
                      <span className="text-warning">not provided</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {proof.missing_facts.length > 0 && (
          <p className="mt-2 text-[11.5px] text-warning">
            Missing: <span className="font-mono">{proof.missing_facts.join(", ")}</span>
          </p>
        )}
      </DrawerSection>

      <DrawerSection label="Condition evaluation">
        {proof.condition_tree ? (
          <>
            <ConditionTree node={proof.condition_tree} />
            <div className="mt-3">
              <p className="label-meta mb-1">Rule output mapping</p>
              <MappingList mapping={proof.rule_output_mapping} />
            </div>
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground">
            Not evaluated — the engine stopped before condition logic (see outcome).
          </p>
        )}
      </DrawerSection>

      {proof.classification && (
        <DrawerSection label="Classification sub-rules">
          <p className="text-[12px]">
            Combined: <span className="font-medium">{proof.classification.block.combined_state ?? "—"}</span>
            {proof.classification.block.conflict_id && (
              <span className="text-warning"> · conflict {proof.classification.block.conflict_id}</span>
            )}
          </p>
          {Object.entries(proof.classification.block.rule_results).map(([ruleId, state]) => {
            const tree = proof.classification?.condition_trees?.[ruleId];
            const mapping = proof.classification?.output_mappings?.[ruleId] ?? {};
            return (
              <div key={ruleId} className="mt-3 border-t border-border pt-2">
                <p className="text-[12px] font-medium">
                  <span className="font-mono">{ruleId}</span> → {state}
                </p>
                {tree && <ConditionTree node={tree} />}
                <div className="mt-1"><MappingList mapping={mapping} /></div>
              </div>
            );
          })}
        </DrawerSection>
      )}

      <DrawerSection label="Evaluation identity">
        <div className="space-y-1">
          <IdList label="Rule" ids={[id.rule_id]} />
          <IdList label="Rule version" ids={[id.rule_version_id ? `${id.rule_version_id} (${id.rule_version_status ?? "?"})` : null]} />
          <IdList label="All rule versions" ids={id.rule_version_ids} />
          <IdList label="Engine version" ids={[id.engine_version]} />
          <IdList label="Evaluated at" ids={[id.evaluated_at]} />
          <div className="flex gap-3 text-[12px]">
            <span className="w-[120px] shrink-0 text-muted-foreground">Decision ID</span>
            <span className="break-all font-mono text-[11px]">{id.decision_id}</span>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Same facts + same rule version + same engine version always produce the same decision ID.
        </p>
      </DrawerSection>

      <DrawerSection label="Source & provenance">
        {proof.provenance.status === "UNRESOLVED" && (
          <div className="mb-2 border border-warning/30 bg-warning-surface px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-warning">
              Source details unresolved
            </p>
            <p className="mt-1 text-[11.5px] leading-relaxed text-foreground/80">
              Only reference IDs are available. The underlying source, evidence
              and instrument records are not in this dataset, so no citation is shown.
            </p>
          </div>
        )}
        <div className="space-y-1">
          <IdList label="Instrument" ids={[proof.provenance.instrument_id]} />
          <IdList label="Authority" ids={[proof.provenance.authority_id]} />
          <IdList label="Sources" ids={proof.provenance.source_ids} />
          <IdList label="Evidence" ids={proof.provenance.evidence_ids} />
          <IdList label="Regulatory facts" ids={proof.provenance.regulatory_fact_ids} />
        </div>
      </DrawerSection>
    </>
  );
}

/** Decision Proof for one requirement — loaded from the backend, which
 * reshapes the Rule Engine's own Decision. */
export function DecisionProofDrawer({
  projectId,
  target,
  onClose,
}: {
  projectId: string;
  target: ProofTarget | null;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: [
      "decision-proof",
      projectId,
      target?.requirementId,
      target?.evaluationMode,
      target?.hypotheticalFacts ?? null,
    ],
    queryFn: async () => {
      const args: Parameters<typeof irisApi.getDecisionProof>[0] = {
        projectId,
        requirementId: target!.requirementId,
        evaluationMode: target!.evaluationMode,
      };
      if (target!.hypotheticalFacts) args.hypotheticalFacts = target!.hypotheticalFacts;
      return (await irisApi.getDecisionProof(args)).proof;
    },
    enabled: !!target,
    retry: (n, e) => !(e instanceof BackendUnavailableError) && n < 1,
  });

  const proof = query.data;
  return (
    <Drawer
      open={!!target}
      onClose={onClose}
      wide
      eyebrow="Decision proof"
      title={proof?.requirement.title ?? target?.requirementId ?? ""}
      subtitle={
        <span className="font-mono text-[11px] text-muted-foreground">
          {target?.requirementId}
          {proof?.requirement.authority_id ? ` · ${proof.requirement.authority_id}` : ""}
        </span>
      }
    >
      {query.isLoading ? (
        <p className="px-5 py-6 text-[12.5px] text-muted-foreground">Building proof from the engine…</p>
      ) : query.isError ? (
        <p className="px-5 py-6 text-[12.5px] text-muted-foreground">
          {query.error instanceof BackendUnavailableError
            ? "The backend isn't reachable."
            : "The decision proof could not be produced."}
        </p>
      ) : proof ? (
        <ProofBody proof={proof} />
      ) : null}
    </Drawer>
  );
}

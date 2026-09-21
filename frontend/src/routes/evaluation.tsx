import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useProject } from "@/lib/iris/project-context";
import { PageHeader, PageShell, SectionHeading } from "@/components/iris/page";
import { ProjectFactsForm } from "@/components/iris/project-facts-form";
import { EngineEvaluationPanel } from "@/components/iris/engine-evaluation-panel";
import {
  DecisionProofDrawer,
  type ProofTarget,
} from "@/components/iris/decision-proof-drawer";

export const Route = createFileRoute("/evaluation")({
  head: () => ({
    meta: [
      { title: "Regulatory Evaluation — IRIS" },
      {
        name: "description",
        content:
          "Which approvals apply to this project and why — evaluated by the deterministic rule engine from the project's own facts.",
      },
    ],
  }),
  component: EvaluationPage,
});

function EvaluationPage() {
  const { activeProject } = useProject();
  const [proof, setProof] = useState<ProofTarget | null>(null);
  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Regulatory intelligence" }, { label: "Evaluation" }]}
        title="Regulatory Evaluation"
        description={`Which approvals apply to ${activeProject.name} — and why`}
      />
      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section>
          <SectionHeading
            title="Engine result"
            hint="Every requirement in the regulatory dataset, evaluated from stored Project Facts."
          />
          <div className="mt-3 border border-border bg-surface">
            <EngineEvaluationPanel
              projectId={activeProject.id}
              onOpenProof={(requirementId, evaluationMode) =>
                setProof({ requirementId, evaluationMode })
              }
            />
          </div>
        </section>
        <section>
          <SectionHeading
            title="Project facts"
            hint="The questions the rules ask. Saving re-evaluates immediately."
          />
          <div className="mt-3 border border-border bg-surface">
            <ProjectFactsForm projectId={activeProject.id} />
          </div>
        </section>
      </div>
      <DecisionProofDrawer
        projectId={activeProject.id}
        target={proof}
        onClose={() => setProof(null)}
      />
    </PageShell>
  );
}

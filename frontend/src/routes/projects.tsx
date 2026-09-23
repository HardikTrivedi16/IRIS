import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Building2, Factory, Plus } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import { readiness } from "@/lib/iris/derive";
import { useProjectRequirements } from "@/lib/iris/use-project-data";
import { PageHeader, PageShell, DataField } from "@/components/iris/page";
import { Meter, Tag } from "@/components/iris/status";
import { NewProjectForm } from "@/components/iris/new-project-form";
import { ProjectFactsForm } from "@/components/iris/project-facts-form";
import { EngineEvaluationPanel } from "@/components/iris/engine-evaluation-panel";
import {
  DecisionProofDrawer,
  type ProofTarget,
} from "@/components/iris/decision-proof-drawer";
import type { Project } from "@/lib/iris/types";
import { INDUSTRY_LABELS } from "@/lib/iris/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/projects")({
  head: () => ({
    meta: [
      { title: "Projects — IRIS" },
      {
        name: "description",
        content:
          "Portfolio of industrial projects tracked in IRIS, with regulatory readiness and blockers at a glance.",
      },
      { property: "og:title", content: "Projects — IRIS" },
      {
        property: "og:description",
        content:
          "Switch between tracked projects and compare regulatory readiness across the portfolio.",
      },
    ],
  }),
  // ?new=1 opens intake at step 1; ?setup=<projectId> resumes it at step 2
  // (used right after creation, including first-run creation).
  validateSearch: (search: Record<string, unknown>): { new?: boolean; setup?: string } => {
    const out: { new?: boolean; setup?: string } = {};
    if (search["new"] === true || search["new"] === "1" || search["new"] === 1) out.new = true;
    if (typeof search["setup"] === "string" && search["setup"]) out.setup = search["setup"];
    return out;
  },
  component: ProjectsPage,
});

const STEPS = ["Basic project information", "Project facts", "Regulatory evaluation"];

function StepIndicator({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap gap-x-6 gap-y-1 border-b border-border px-5 py-3">
      {STEPS.map((label, i) => (
        <li
          key={label}
          className={cn(
            "flex items-center gap-2 text-[12px]",
            i === current ? "font-semibold text-foreground" : "text-muted-foreground",
          )}
        >
          <span
            className={cn(
              "tabular flex h-5 w-5 items-center justify-center rounded-full border text-[10.5px]",
              i < current
                ? "border-success bg-success-surface text-success"
                : i === current
                  ? "border-primary text-foreground"
                  : "border-border",
            )}
          >
            {i + 1}
          </span>
          {label}
        </li>
      ))}
    </ol>
  );
}

function ProjectSetup({
  mode,
  setupId,
}: {
  mode: "new" | "setup";
  setupId: string | undefined;
}) {
  const { projects, registerCreatedProject, setActiveProjectId } = useProject();
  const navigate = useNavigate();
  const [step, setStep] = useState(mode === "new" ? 0 : 1);
  const [proof, setProof] = useState<ProofTarget | null>(null);
  const project = setupId ? projects.find((p) => p.id === setupId) : undefined;

  useEffect(() => {
    setStep(mode === "new" ? 0 : 1);
  }, [mode, setupId]);

  // Resuming setup always works on the project being set up.
  useEffect(() => {
    if (project) setActiveProjectId(project.id);
  }, [project, setActiveProjectId]);

  const close = () => void navigate({ to: "/projects", search: {} });

  if (mode === "setup" && !project) {
    return (
      <section className="mt-6 border border-border bg-surface px-5 py-5">
        <p className="text-[13px] font-medium">Project not found</p>
        <p className="mt-1 text-[12px] text-muted-foreground">
          It may not exist or you may not have access to it.
        </p>
        <button type="button" onClick={close} className="mt-3 text-[12px] font-medium text-info">
          Back to projects
        </button>
      </section>
    );
  }

  return (
    <section className="mt-6 border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <h2 className="text-[13.5px] font-semibold">
          {project ? `Set up ${project.name}` : "New project"}
        </h2>
        <button type="button" onClick={close} className="text-[12px] text-muted-foreground hover:text-foreground">
          Close
        </button>
      </div>
      <StepIndicator current={step} />

      {step === 0 && (
        <NewProjectForm
          onCreated={(created) => {
            registerCreatedProject(created);
            void navigate({ to: "/projects", search: { setup: created.id }, replace: true });
          }}
          onCancel={close}
        />
      )}

      {step === 1 && project && (
        <>
          <p className="border-b border-border px-5 py-3 text-[12px] leading-relaxed text-muted-foreground">
            Answer what you know. Each question comes from a regulatory rule in
            the dataset; anything left unprovided is reported as additional
            information required — IRIS does not guess.
          </p>
          <ProjectFactsForm
            projectId={project.id}
            submitLabel="Save and continue"
            onSaved={() => setStep(2)}
          />
        </>
      )}

      {step === 2 && project && (
        <>
          <EngineEvaluationPanel
            projectId={project.id}
            onOpenProof={(requirementId, evaluationMode) =>
              setProof({ requirementId, evaluationMode })
            }
          />
          <DecisionProofDrawer
            projectId={project.id}
            target={proof}
            onClose={() => setProof(null)}
          />
          <div className="flex flex-wrap gap-3 border-t border-border px-5 py-3">
            <button type="button" onClick={() => setStep(1)}
              className="focus-ring rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium hover:bg-secondary">
              Back to project facts
            </button>
            <button type="button" onClick={() => void navigate({ to: "/evaluation" })}
              className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground hover:opacity-90">
              Finish — open regulatory evaluation
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function ProjectCard({
  project,
  isActive,
  onOpen,
}: {
  project: Project;
  isActive: boolean;
  onOpen: (id: string) => void;
}) {
  const { data: reqs = [] } = useProjectRequirements(project.id);
  const summary = readiness(reqs);
  return (
    <button
      type="button"
      onClick={() => onOpen(project.id)}
      className={cn(
        "row-hover flex flex-col border bg-surface px-5 py-5 text-left transition-colors hover:bg-surface-sunken",
        isActive ? "border-primary" : "border-border",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-sunken text-muted-foreground">
            {project.industry === "pharmaceutical" ? (
              <Building2 className="h-4 w-4" />
            ) : (
              <Factory className="h-4 w-4" />
            )}
          </span>
          <div className="min-w-0">
            <h3 className="text-[14.5px] font-semibold leading-snug">
              {project.name}
            </h3>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              {project.activity} · {project.location}
            </p>
          </div>
        </div>
        {isActive && <Tag tone="info">Active</Tag>}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <DataField
          label="Industry"
          value={<span>{INDUSTRY_LABELS[project.industry]}</span>}
        />
        <DataField
          label="Stage"
          value={
            <span className="capitalize">{project.stage.replace("-", " ")}</span>
          }
        />
        <DataField
          label="Scale"
          value={<span className="capitalize">{project.scale}</span>}
        />
        <DataField
          label="Workers"
          value={<span className="tabular">{project.workers}</span>}
        />
      </div>

      <div className="mt-5 border-t border-border pt-4">
        {reqs.length === 0 ? (
          <p className="text-[11.5px] leading-relaxed text-muted-foreground">
            No requirements tracking register for this project. See{" "}
            <span className="font-medium text-foreground">Evaluation</span> for
            its rule-engine result.
          </p>
        ) : (
          <>
            <div className="flex items-baseline justify-between">
              <span className="label-meta">Regulatory readiness</span>
              <span className="tabular text-[13px] font-semibold">
                {summary.readinessPct}%{" "}
                <span className="font-normal text-muted-foreground">
                  ({summary.ready}/{summary.applicable.length})
                </span>
              </span>
            </div>
            <Meter
              value={summary.ready}
              total={summary.applicable.length}
              tone={summary.blocked ? "warning" : "success"}
              className="mt-2"
            />
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[11.5px] text-muted-foreground">
              <span>{summary.blocked} blocked</span>
              <span>{summary.attention} action required</span>
              <span>{summary.notApplicable} not applicable</span>
            </div>
          </>
        )}
      </div>
    </button>
  );
}

function ProjectsPage() {
  const { projects, activeProject, setActiveProjectId } = useProject();
  const navigate = useNavigate();
  const search = Route.useSearch();
  const setupMode = search.setup ? "setup" : search.new ? "new" : null;

  function openProject(id: string) {
    setActiveProjectId(id);
    navigate({ to: "/" });
  }

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Workspace" }, { label: "Projects" }]}
        title="Projects"
        description="Select a project to open its overview"
        actions={
          <button
            type="button"
            onClick={() => void navigate({ to: "/projects", search: { new: true } })}
            className="focus-ring inline-flex items-center gap-1.5 rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Plus className="h-3.5 w-3.5" />
            New project
          </button>
        }
        meta={
          <div className="flex items-baseline gap-2">
            <span className="tabular text-[15px] font-semibold">
              {projects.length}
            </span>
            <span className="text-[12.5px] text-muted-foreground">
              tracked projects
            </span>
          </div>
        }
      />

      {setupMode && <ProjectSetup mode={setupMode} setupId={search.setup} />}

      <p className="mt-4 text-[11.5px] leading-relaxed text-muted-foreground">
        Project list is live (
        <span className="font-medium text-foreground">
          GET /api/v1/projects
        </span>
        ). Readiness/blocker summaries are loaded per project from the backend.
      </p>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        {projects.map((project) => (
          <ProjectCard
            key={project.id}
            project={project}
            isActive={project.id === activeProject.id}
            onOpen={openProject}
          />
        ))}
      </div>

    </PageShell>
  );
}

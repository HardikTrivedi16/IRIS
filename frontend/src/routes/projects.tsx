import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Building2, Factory } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import { readiness } from "@/lib/iris/derive";
import { useProjectRequirements } from "@/lib/iris/use-project-data";
import { PageHeader, PageShell, DataField } from "@/components/iris/page";
import { Meter, Tag } from "@/components/iris/status";
import type { Project } from "@/lib/iris/types";
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
  component: ProjectsPage,
});

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
          value={<span className="capitalize">{project.industry}</span>}
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
            No requirements register for this project yet. See{" "}
            <span className="font-medium text-foreground">Requirements</span> for
            the real Phase 9 engine-backed requirements.
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

      <section className="mt-8 border border-dashed border-border bg-surface px-5 py-6 text-center">
        <p className="text-[13px] font-medium">Add a new project</p>
        <p className="mx-auto mt-1.5 max-w-[52ch] text-[12px] leading-relaxed text-muted-foreground">
          Project intake is not part of this prototype. New projects are
          provisioned by the IRIS team from a completed project profile
          questionnaire.
        </p>
      </section>
    </PageShell>
  );
}

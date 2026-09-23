import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  irisApi,
  ApiError,
  BackendUnavailableError,
} from "@/lib/iris/api-client";
import { normalizeIndustry } from "@/lib/iris/types";
import type {
  Project,
  Industry,
  ProjectStage,
  ProjectScale,
  ProjectCharacteristics,
} from "@/lib/iris/types";
import { useAuth } from "@/lib/auth-context";
import {
  NewProjectForm,
  type CreatedProject,
} from "@/components/iris/new-project-form";

interface ProjectContextValue {
  activeProject: Project;
  setActiveProjectId: (id: string) => void;
  projects: Project[];
  /** Adds a just-created project to the list and makes it active, without
   * waiting for the projects query to refetch. */
  registerCreatedProject: (project: CreatedProject) => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

// ---------------------------------------------------------------------------
// Real backend projects, normalized into the strict Project shape.
//
// This used to be a hardcoded array of two fixture projects ("mahapharm",
// "freshbite") that the whole app assumed always existed. That was fine
// only because the in-memory demo store happens to seed rows with those
// exact ids (backend/app/store/memory_store.py) — it silently broke the
// moment a real Supabase-backed store was used, since nothing guarantees
// those ids (or any project at all) exist there. Projects now always come
// from GET /api/v1/projects — whatever the active store (in-memory demo
// seed, or real Supabase rows the user has inserted) actually returns.
// ---------------------------------------------------------------------------

const DEFAULT_CHARACTERISTICS: ProjectCharacteristics = {
  hazardousChemicals: false,
  hazardousWaste: false,
  wastewater: false,
  airEmissions: false,
  waterUse: false,
  chemicalStorage: false,
};

const KNOWN_STAGES: readonly ProjectStage[] = [
  "pre-establishment",
  "construction",
  "commissioning",
  "operations",
];
const KNOWN_SCALES: readonly ProjectScale[] = ["small", "medium", "large"];

function includesValue<T extends string>(list: readonly T[], value: string): value is T {
  return (list as readonly string[]).includes(value);
}

/**
 * Normalizes one raw backend project record into the Project shape every
 * existing page already assumes (non-null strings, closed industry/stage/
 * scale unions). Real Supabase rows may have NULL activity/location/stage/
 * scale/workers (see supabase/migrations/0001_iris_application_schema.sql —
 * all nullable) and free-text industry — this fills honest, neutral
 * display defaults rather than inventing a specific value. It never
 * changes `id`/`name`, and it is never used to decide anything
 * regulatory — Phase 9 evaluation reads Project Facts, not this object.
 */
function normalizeProject(raw: Record<string, unknown>): Project {
  const industry: Industry = normalizeIndustry(raw["industry"]);

  // Stored stage may be any case and "operation" (canonical in the portfolio)
  // rather than the frontend union's "operations".
  const stageAliases: Record<string, string> = { operation: "operations", operational: "operations" };
  const stageKey = String(raw["stage"] ?? "").trim().toLowerCase().replace(/[_\s]+/g, "-");
  const rawStage = stageAliases[stageKey] ?? stageKey;
  const stage: ProjectStage = includesValue(KNOWN_STAGES, rawStage)
    ? rawStage
    : "pre-establishment";

  const rawScale = String(raw["scale"] ?? "");
  const scale: ProjectScale = includesValue(KNOWN_SCALES, rawScale)
    ? rawScale
    : "medium";

  const rawCharacteristics = raw["characteristics"];
  const characteristics: ProjectCharacteristics = {
    ...DEFAULT_CHARACTERISTICS,
    ...(rawCharacteristics && typeof rawCharacteristics === "object"
      ? (rawCharacteristics as Partial<ProjectCharacteristics>)
      : {}),
  };

  const workersRaw = raw["workers"];

  return {
    id: String(raw["id"]),
    name: String(raw["name"] ?? raw["id"]),
    industry,
    activity: (raw["activity"] as string) || "Not specified",
    location: (raw["location"] as string) || "Not specified",
    stage,
    scale,
    workers: typeof workersRaw === "number" ? workersRaw : 0,
    characteristics,
  };
}

function FullPageMessage({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="max-w-md text-center">
        <p className="text-[15px] font-semibold text-foreground">{title}</p>
        <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
          {description}
        </p>
        {action && <div className="mt-5">{action}</div>}
      </div>
    </div>
  );
}

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [activeProjectId, setActiveProjectIdState] = useState<string | null>(
    null,
  );

  const { session, irisUser, isLoading, isDemoMode } = useAuth();
  // Auth state has three distinct phases; only the last two may decide anything.
  //  - resolving: still loading, or a session exists but GET /auth/me has not
  //    returned the IRIS profile yet (irisUser is null in both cases)
  //  - resolved: session + profile known (demo mode is always resolved)
  // A government role is not an applicant, so it never queries owned projects
  // and an empty list must not push it into applicant intake.
  const authResolved =
    isDemoMode || (!isLoading && session !== null && irisUser !== null);
  const isGovernment =
    !isDemoMode && authResolved && Boolean(irisUser?.role.startsWith("DEPARTMENT_"));
  const query = useQuery({
    queryKey: ["projects"],
    enabled: authResolved && !isGovernment,
    queryFn: () => irisApi.listProjects(),
    staleTime: 30_000,
    retry: (failureCount, error) =>
      !(error instanceof BackendUnavailableError) && failureCount < 1,
  });

  const setActiveProjectId = useCallback(
    (id: string) => setActiveProjectIdState(id),
    [],
  );

  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // Set by first-run intake; consumed once the provider has switched from the
  // intake form to the app, so the navigation is not lost in that swap.
  const [pendingSetupId, setPendingSetupId] = useState<string | null>(null);

  // activeProjectId is local component state, not part of the TanStack Query
  // cache that __root.tsx clears on an account change — it must be reset
  // here too, or it could keep pointing at a project id that belonged to
  // the previous account (see __root.tsx's identity-change comment for why
  // this matters). `undefined` (not yet observed) is not a change, so this
  // doesn't fire on first mount.
  const identityRef = useRef<string | null | undefined>(undefined);
  const identity = isDemoMode ? "demo" : (session?.user?.id ?? null);
  useEffect(() => {
    if (identityRef.current !== undefined && identityRef.current !== identity) {
      setActiveProjectIdState(null);
      setPendingSetupId(null);
    }
    identityRef.current = identity;
  }, [identity]);
  const registerCreatedProject = useCallback(
    (project: CreatedProject) => {
      queryClient.setQueryData<unknown[]>(["projects"], (old) => [
        ...(old ?? []).filter(
          (p) => (p as { id?: string }).id !== project.id,
        ),
        project,
      ]);
      setActiveProjectIdState(project.id);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    [queryClient],
  );

  const projects = useMemo<Project[]>(
    () =>
      (query.data ?? []).map((p) =>
        normalizeProject(p as unknown as Record<string, unknown>),
      ),
    [query.data],
  );

  const value = useMemo<ProjectContextValue | null>(() => {
    if (projects.length === 0) return null;
    const activeProject =
      projects.find((p) => p.id === activeProjectId) ?? projects[0]!;
    return { activeProject, setActiveProjectId, projects, registerCreatedProject };
  }, [projects, activeProjectId, setActiveProjectId, registerCreatedProject]);

  useEffect(() => {
    if (value && pendingSetupId) {
      void navigate({
        to: "/projects",
        search: { setup: pendingSetupId },
        replace: true,
      });
      setPendingSetupId(null);
    }
  }, [value, pendingSetupId, navigate]);

  useEffect(() => {
    if (isGovernment) void navigate({ to: "/department", replace: true });
  }, [isGovernment, navigate]);

  if (!authResolved) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-[13.5px] text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (isGovernment) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-[13.5px] text-muted-foreground">
          Opening the government portal…
        </p>
      </div>
    );
  }

  if (query.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-[13.5px] text-muted-foreground">
          Loading projects…
        </p>
      </div>
    );
  }

  if (query.isError) {
    const isOffline = query.error instanceof BackendUnavailableError;
    const isUnauthorized =
      query.error instanceof ApiError && query.error.status === 401;
    return (
      <FullPageMessage
        title={
          isOffline
            ? "IRIS backend is not reachable"
            : isUnauthorized
              ? "Sign-in required"
              : "Could not load projects"
        }
        description={
          isOffline
            ? "Start the backend with: cd backend && uvicorn app.main:app"
            : isUnauthorized
              ? "Your session may have expired. Sign in again to continue."
              : String((query.error as Error).message ?? query.error)
        }
        action={
          isUnauthorized ? (
            <a
              href="/login"
              className="focus-ring inline-flex items-center rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Sign in
            </a>
          ) : (
            <button
              type="button"
              onClick={() => void query.refetch()}
              className="focus-ring inline-flex items-center rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Retry
            </button>
          )
        }
      />
    );
  }

  if (!value) {
    // First-run state: no projects for this account yet. Offer intake here
    // (the rest of the app needs an active project), then continue the same
    // setup flow on /projects at the Project Facts step.
    return (
      <div className="mx-auto max-w-[760px] px-6 py-12">
        <p className="text-[15px] font-semibold text-foreground">
          Create your first project
        </p>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">
          This account has no projects yet. Start with the basic project
          profile; the next step asks the questions the regulatory rules need.
        </p>
        <div className="mt-5 border border-border bg-surface">
          <NewProjectForm
            onCreated={(project) => {
              registerCreatedProject(project);
              setPendingSetupId(project.id);
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
  );
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within ProjectProvider");
  return ctx;
}

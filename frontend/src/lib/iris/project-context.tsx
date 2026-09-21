import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { useQuery } from "@tanstack/react-query";
import {
  irisApi,
  ApiError,
  BackendUnavailableError,
} from "@/lib/iris/api-client";
import type {
  Project,
  Industry,
  ProjectStage,
  ProjectScale,
  ProjectCharacteristics,
} from "@/lib/iris/types";

interface ProjectContextValue {
  activeProject: Project;
  setActiveProjectId: (id: string) => void;
  projects: Project[];
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

const KNOWN_INDUSTRIES: readonly Industry[] = ["pharmaceutical", "food"];
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
  const rawIndustry = String(raw["industry"] ?? "").toLowerCase();
  const industry: Industry = includesValue(KNOWN_INDUSTRIES, rawIndustry)
    ? rawIndustry
    : "pharmaceutical"; // display/icon grouping only

  const rawStage = String(raw["stage"] ?? "");
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

  const query = useQuery({
    queryKey: ["projects"],
    queryFn: () => irisApi.listProjects(),
    staleTime: 30_000,
    retry: (failureCount, error) =>
      !(error instanceof BackendUnavailableError) && failureCount < 1,
  });

  const setActiveProjectId = useCallback(
    (id: string) => setActiveProjectIdState(id),
    [],
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
    return { activeProject, setActiveProjectId, projects };
  }, [projects, activeProjectId, setActiveProjectId]);

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
    return (
      <FullPageMessage
        title="No projects found"
        description="This account has no projects yet. Projects are created via the IRIS backend (POST /api/v1/projects) — there is no project-intake form in this prototype."
      />
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

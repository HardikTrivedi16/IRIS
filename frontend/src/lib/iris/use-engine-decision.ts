import { useQuery } from "@tanstack/react-query";
import {
  irisApi,
  BackendUnavailableError,
  type EvaluationMode,
} from "@/lib/iris/api-client";
import { engineRequirementIdFor } from "@/lib/iris/engine-mapping";
import type { Project } from "@/lib/iris/types";

/** Live health/version info about the backend + regulatory engine. Used to
 * show a global "backend unavailable" state without failing every panel
 * individually, and to surface the real DRAFT/ACTIVE rule-version counts. */
export function useEngineInfo() {
  return useQuery({
    queryKey: ["engine-info"],
    queryFn: irisApi.engineInfo,
    staleTime: 60_000,
    retry: 1,
  });
}

/**
 * Evaluates one engine-backed requirement for a project. Returns
 * `undefined` data (and `enabled: false`) for prototype requirements that
 * have no real engine mapping — callers should check `isEngineBacked`
 * first and render prototype content instead in that case.
 */
export function useEngineDecision(
  project: Project,
  frontendRequirementId: string,
  evaluationMode: EvaluationMode = "PRODUCTION",
) {
  const engineRequirementId = engineRequirementIdFor(frontendRequirementId);

  return useQuery({
    queryKey: [
      "engine-decision",
      project.id,
      engineRequirementId,
      evaluationMode,
    ],
    queryFn: async () => {
      if (!engineRequirementId) throw new Error("not engine-backed");
      // READ-ONLY view: never persist a Decision merely because a page was
      // opened, and never send derived "facts" — they would be merged over the
      // project's stored Project Facts (request body wins) and silently change
      // the evaluated basis. The engine reads the stored facts itself.
      const { decision } = await irisApi.evaluate({
        projectId: project.id,
        requirementId: engineRequirementId,
        evaluationMode,
        persist: false,
      });
      return decision;
    },
    enabled: !!engineRequirementId,
    retry: (failureCount, error) =>
      !(error instanceof BackendUnavailableError) && failureCount < 1,
    staleTime: 10_000,
  });
}

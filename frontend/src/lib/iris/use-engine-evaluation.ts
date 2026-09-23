import { useQuery } from "@tanstack/react-query";
import {
  BackendUnavailableError,
  irisApi,
  type EvaluationMode,
} from "@/lib/iris/api-client";

/** Every dataset requirement evaluated from the project's STORED facts —
 * read-only (persist:false, no ad-hoc overrides). */
export function useEngineEvaluation(projectId: string, mode: EvaluationMode) {
  return useQuery({
    queryKey: ["engine-evaluation", projectId, mode],
    queryFn: async () =>
      (await irisApi.evaluateAll({ projectId, evaluationMode: mode })).decisions,
    retry: (n, e) => !(e instanceof BackendUnavailableError) && n < 1,
    staleTime: 10_000,
  });
}

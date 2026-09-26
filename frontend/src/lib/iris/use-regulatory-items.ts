import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { irisApi } from "@/lib/iris/api-client";
import { useEngineEvaluation } from "@/lib/iris/use-engine-evaluation";
import { useFactRegistry, useProjectFacts } from "@/lib/iris/facts";
import {
  buildRegulatoryItems,
  type DatasetRequirement,
  type RegulatoryItem,
} from "@/lib/iris/regulatory-items";

/** Dataset Requirement metadata (title, authority, lifecycle stages, rule
 * version status) — the engine's own catalogue, not project tracking data. */
export function useDatasetRequirements() {
  return useQuery({
    queryKey: ["dataset-requirement-records"],
    queryFn: async () => (await irisApi.listRequirements()) as DatasetRequirement[],
    staleTime: 5 * 60_000,
  });
}

/**
 * The single hook behind every regulatory-intelligence surface. Read-only:
 * both evaluations are the existing persist:false, stored-facts-only
 * `evaluateAll`. PRODUCTION is the authoritative result; NON_PRODUCTION is
 * the labelled diagnostic evaluation of the same rules.
 */
export function useRegulatoryItems(projectId: string) {
  const requirements = useDatasetRequirements();
  const production = useEngineEvaluation(projectId, "PRODUCTION");
  const diagnostic = useEngineEvaluation(projectId, "NON_PRODUCTION");
  const registry = useFactRegistry();
  const facts = useProjectFacts(projectId);

  const items = useMemo<RegulatoryItem[]>(() => {
    if (!requirements.data || !production.data) return [];
    return buildRegulatoryItems({
      requirements: requirements.data,
      production: production.data,
      diagnostic: diagnostic.data,
      registry: registry.data?.facts ?? [],
      facts: facts.data?.facts ?? {},
    });
  }, [requirements.data, production.data, diagnostic.data, registry.data, facts.data]);

  const queries = [requirements, production, diagnostic, registry, facts];
  return {
    items,
    isLoading: queries.some((q) => q.isLoading),
    isError: requirements.isError || production.isError,
    diagnosticReady: !!diagnostic.data,
  };
}


/** Authored Requirement->Requirement relationships for the project, from the existing dependency
 * graph API. Read-only; an unavailable API simply yields no relationships (never an invented one). */
export function useDependencyRelationships(projectId: string) {
  const q = useQuery({
    queryKey: ["dependency-relationships", projectId],
    queryFn: async () => (await irisApi.getDependencyGraph(projectId, "PRODUCTION")).relationships ?? [],
    staleTime: 30_000,
    retry: false,
  });
  return { relationships: q.data ?? [], isError: q.isError };
}

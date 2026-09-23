/**
 * React-Query hooks that load a project's industry-portal data from the real
 * IRIS backend (Supabase-backed) instead of the old hardcoded mock-data.ts.
 *
 * Each hook returns data already mapped into the shape the pages consume
 * (Requirement, DocumentItem, and an activity item), so page components change
 * only their data *source*, not their rendering. All hooks tolerate an empty
 * result (e.g. before the 0006 SQL has been run) by returning [].
 */
import { useQuery } from "@tanstack/react-query";
import { irisApi } from "./api-client";
import type { Requirement, DocumentItem } from "./types";

export interface ActivityItem {
  time: string;
  actor: string;
  text: string;
}

/** Requirements checklist for a project (already in Requirement shape). */
export function useProjectRequirements(projectId: string) {
  return useQuery({
    queryKey: ["project-requirements", projectId],
    queryFn: () => irisApi.getProjectRequirements(projectId),
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

const DOC_STATUSES: DocumentItem["status"][] = [
  "extracted",
  "missing-info",
  "mismatch",
];

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

/** Document register for a project, mapped from the backend DocumentRecord
 * rows into the DocumentItem shape the register renders. */
export function useProjectDocuments(projectId: string) {
  return useQuery({
    queryKey: ["project-documents", projectId],
    queryFn: async (): Promise<DocumentItem[]> => {
      const rows = await irisApi.listDocuments(projectId);
      return rows.map((r) => {
        const item: DocumentItem = {
          id: r.id,
          name: r.name,
          // The register only knows these three states; anything else
          // (e.g. a freshly "uploaded" doc) is shown as extracted.
          status: DOC_STATUSES.includes(r.status as DocumentItem["status"])
            ? (r.status as DocumentItem["status"])
            : "extracted",
          uploadedAt: formatDate(r.uploaded_at),
        };
        if (r.legacy_evidence) {
          item.legacy = {
            label: r.legacy_evidence.label,
            priorFacility: r.legacy_evidence.prior_facility,
          };
        }
        if (r.issues && r.issues.length) item.issues = r.issues;
        if (r.extracted_information && r.extracted_information.length)
          item.extractedInformation = r.extracted_information;
        return item;
      });
    },
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

/** Recent activity for a project's Overview timeline. */
export function useProjectActivity(projectId: string) {
  return useQuery({
    queryKey: ["project-activity", projectId],
    queryFn: async (): Promise<ActivityItem[]> => {
      const rows = await irisApi.getProjectActivity(projectId);
      return rows.map((r) => ({
        time: formatDate(r.created_at),
        actor: r.actor ?? "System",
        text: r.message,
      }));
    },
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

export type { Requirement };

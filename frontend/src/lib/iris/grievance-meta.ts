import type { GrievanceStatus } from "./api-client";
import type { DecisionTone } from "./decision-states";

/** Shown wherever a grievance is raised or viewed. */
export const GRIEVANCE_DISCLAIMER =
  "IRIS grievance tracking prepares and hands off your grievance with the application context attached. It is not a statutory grievance filing and does not replace MAITRI / NSWS or the department's own grievance mechanism.";

export const SLA_META: Record<string, { label: string; tone: DecisionTone }> = {
  WITHIN_SLA: { label: "Within SLA", tone: "success" },
  AT_RISK: { label: "At risk", tone: "warning" },
  BREACHED: { label: "Breached", tone: "danger" },
  COMPLETED: { label: "Completed", tone: "neutral" },
};

export const GRIEVANCE_STATUS_META: Record<GrievanceStatus, { label: string; tone: DecisionTone }> = {
  OPEN: { label: "Open", tone: "warning" },
  ASSIGNED: { label: "Assigned", tone: "info" },
  UNDER_REVIEW: { label: "Under review", tone: "info" },
  RESOLVED: { label: "Resolved", tone: "success" },
  CLOSED: { label: "Closed", tone: "neutral" },
};

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function stageLabel(s: string | null | undefined): string {
  return s ? s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "—";
}

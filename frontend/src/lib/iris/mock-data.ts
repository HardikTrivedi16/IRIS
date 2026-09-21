import type { RegulatorySource } from "./types";

// ---------------------------------------------------------------------------
// Static reference/display constants (NOT per-project mock data).
//
// All per-project data (requirements, documents, dependency graph, readiness,
// compliance, activity) now comes from the real IRIS backend / Supabase —
// see use-project-data.ts and derive.ts. The only things left here are two
// static lists that are the same regardless of project:
//   * regulatorySources  — the directory of regulators shown on /sources
//   * suggestedQuestions — example prompts on the Ask IRIS page (each is
//     actually sent to the live backend; these are not canned answers)
// ---------------------------------------------------------------------------

export const regulatorySources: RegulatorySource[] = [
  {
    id: "mpcb",
    name: "MPCB",
    fullName: "Maharashtra Pollution Control Board",
    sourceType: "Official regulatory source",
    lastVerified: "September 2026",
    documentCount: "Reference dataset",
    description:
      "Environmental consent and pollution control regulations for Maharashtra.",
  },
  {
    id: "dish",
    name: "DISH",
    fullName: "Directorate of Industrial Safety and Health",
    sourceType: "Official regulatory source",
    lastVerified: "September 2026",
    documentCount: "Reference dataset",
    description:
      "Factory safety, plan approval, and industrial health regulations.",
  },
  {
    id: "midc",
    name: "MIDC / SIIDCUL",
    fullName: "Industrial Development Corporation",
    sourceType: "Official regulatory source",
    lastVerified: "September 2026",
    documentCount: "Reference dataset",
    description:
      "Industrial land allotment, building plan approval, and fire safety.",
  },
  {
    id: "cdsco",
    name: "CDSCO",
    fullName: "Central Drugs Standard Control Organisation",
    sourceType: "Official regulatory source",
    lastVerified: "September 2026",
    documentCount: "Reference dataset",
    description:
      "Central drug regulatory framework and manufacturing guidelines.",
  },
  {
    id: "mdd",
    name: "State Drugs Department",
    fullName: "State Food and Drugs Administration",
    sourceType: "Official regulatory source",
    lastVerified: "September 2026",
    documentCount: "Reference dataset",
    description: "State-level drug manufacturing licensing and compliance.",
  },
  {
    id: "fssai",
    name: "FSSAI",
    fullName: "Food Safety and Standards Authority of India",
    sourceType: "Official regulatory source",
    lastVerified: "September 2026",
    documentCount: "Reference dataset",
    description: "Food safety standards and manufacturing licence regulations.",
  },
];

// Ask IRIS is backed by the real backend (RAG over the Phase 9 engine +
// NetworkX dependency graph + the regulatory dataset's own text — see
// backend/app/ai_integration/ask_service.py). These are example prompts only,
// not canned answers: every question here is actually sent to
// POST /api/v1/projects/{id}/ask and answered live.
export const suggestedQuestions = [
  "Which requirements apply to this project?",
  "Why is the MPCB Consent to Establish (Water Act) applicable?",
  "What is currently blocking this project?",
  "What evidence supports the FSSAI Food Business Licence requirement?",
];

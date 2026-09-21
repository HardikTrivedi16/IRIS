/**
 * Maps the existing frontend's prototype requirement IDs (mock-data.ts) to
 * real Phase 9 engine requirement IDs, and derives the (best-effort) engine
 * project_facts from the existing Project shape.
 *
 * IMPORTANT — read before changing this file:
 * The frontend prototype (mock-data.ts) lists far more requirements than
 * the supplied regulatory dataset actually covers (only 4 Requirements
 * exist: REQ-0001..REQ-0004 — see backend/regulatory-data/requirements/).
 * Only the four IDs below are wired to the real engine. Every other
 * prototype requirement (midc-site, building-plan, fire-approval, ...) is
 * intentionally left as static/prototype content — inventing an engine
 * mapping for those would mean fabricating a regulatory rule that does not
 * exist in the supplied dataset, which the integration brief explicitly
 * forbids.
 */

/** frontend Requirement.id -> engine requirement_id */
export const ENGINE_BACKED_REQUIREMENTS: Record<string, string> = {
  "mpcb-cte": "REQ-0001", // MPCB Consent to Establish — Water Act
  "mpcb-cto": "REQ-0002", // MPCB Consent to Establish/Operate — Air Act (closest engine match to "Consent to Operate")
  "drug-licence": "REQ-0003", // Drug Manufacturing Licence — Rule 69, D&C Rules
  "fssai-licence": "REQ-0004", // FSSAI Food Business Licence
};

export function engineRequirementIdFor(
  frontendRequirementId: string,
): string | undefined {
  return ENGINE_BACKED_REQUIREMENTS[frontendRequirementId];
}

export function isEngineBacked(frontendRequirementId: string): boolean {
  return frontendRequirementId in ENGINE_BACKED_REQUIREMENTS;
}

/**
 * Best-effort derivation of engine project_facts from the frontend's
 * existing Project.characteristics booleans.
 *
 * This is a NARROW bridge, not a statutory fact-capture form. A mapping is
 * only made where the source field and the engine fact ask the same
 * question. Where they don't, the fact is left UNSET — the engine then
 * reports REQUIRES_INFORMATION, which is the correct outcome, rather than
 * the UI inferring a regulatory fact nobody supplied.
 *
 * Deliberately NOT mapped
 * -----------------------
 * * `project.plant_located_in_air_pollution_control_area` — the obvious
 *   candidate source, `characteristics.airEmissions`, means "this project
 *   emits to air". The engine fact (COND-0002, Air Act 1981 s.21) asks
 *   whether the plant SITS INSIDE an air pollution control area formally
 *   declared by the State Government. Those are different questions: a
 *   plant can emit without being in a declared area, and can be in a
 *   declared area while emitting nothing. Mapping one to the other would
 *   manufacture a jurisdictional fact from an operational one. It is a
 *   location fact that must be supplied explicitly (see the fact-capture
 *   surface driven by GET /api/v1/facts/registry).
 * * `project.drug_schedule_classification` (REQ-0003) and the two dairy
 *   capacity facts (REQ-0004's classification sub-rules) — no
 *   corresponding field exists on Project at all.
 *
 * `characteristics.wastewater` IS mapped: the prototype's own field means
 * "this project generates wastewater/effluent", which is the same question
 * COND-0001 asks (Water Act 1974 s.25(1)(a) — likely to discharge sewage
 * or trade effluent). It stays a user-asserted operational claim, not a
 * derived legal conclusion.
 *
 * Any fact set here is an ad-hoc request-body fact, never a persisted
 * Project Fact — see the `hypothetical_facts` labelling in ask_service.
 */
export function deriveEngineProjectFacts(project: {
  industry: string;
  characteristics: { wastewater: boolean };
}): Record<string, unknown> {
  return {
    "project.industry":
      project.industry === "food" ? "FOOD" : project.industry.toUpperCase(),
    "project.likely_to_discharge_sewage_or_trade_effluent":
      project.characteristics.wastewater,
    // Intentionally NOT set — see docstring:
    //   project.plant_located_in_air_pollution_control_area
    //   project.drug_schedule_classification
    //   project.dairy_liquid_milk_capacity
    //   project.dairy_milk_solids_capacity
  };
}

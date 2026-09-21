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
 * This is a HEURISTIC bridge, not a statutory fact-capture form: the
 * engine's Rule Versions ask precise regulatory questions
 * ("project.likely_to_discharge_sewage_or_trade_effluent",
 * "project.plant_located_in_air_pollution_control_area") that the
 * existing prototype's characteristics model was never designed to
 * capture exactly. Two facts the engine needs
 * (project.drug_schedule_classification for REQ-0003, and the two dairy
 * capacity facts for REQ-0004's classification sub-rules) have NO
 * corresponding field in Project at all and are deliberately left
 * unset — the engine will correctly report REQUIRES_INFORMATION for
 * those rather than the UI guessing a value. A production deployment
 * should replace this with a real fact-capture form per Rule Version's
 * declared `required_project_facts`.
 */
export function deriveEngineProjectFacts(project: {
  industry: string;
  characteristics: { wastewater: boolean; airEmissions: boolean };
}): Record<string, unknown> {
  return {
    "project.industry":
      project.industry === "food" ? "FOOD" : project.industry.toUpperCase(),
    "project.likely_to_discharge_sewage_or_trade_effluent":
      project.characteristics.wastewater,
    "project.plant_located_in_air_pollution_control_area":
      project.characteristics.airEmissions,
    // Intentionally NOT set (see docstring): project.drug_schedule_classification,
    // project.dairy_liquid_milk_capacity, project.dairy_milk_solids_capacity.
  };
}

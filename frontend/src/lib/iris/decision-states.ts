/**
 * Display vocabulary for the Rule Engine's final_state values
 * (backend/iris_engine/decision.py + rules.py). Labels only — no state is
 * derived, merged or reinterpreted here. Unknown states fall through to
 * their raw engine string rather than being guessed into a nicer label.
 */
export type DecisionTone = "success" | "warning" | "danger" | "info" | "neutral";

export const FINAL_STATE_META: Record<string, { label: string; tone: DecisionTone }> = {
  APPLICABLE: { label: "Applicable", tone: "success" },
  NOT_APPLICABLE: { label: "Not applicable", tone: "neutral" },
  REQUIRES_INFORMATION: { label: "Requires information", tone: "warning" },
  REQUIRES_REVIEW: { label: "Requires review", tone: "warning" },
  UNKNOWN: { label: "Unknown", tone: "warning" },
  BLOCKED_DRAFT_NOT_PRODUCTION: { label: "Blocked — draft rule version", tone: "danger" },
  BLOCKED_NO_RULE: { label: "Blocked — no rule defined", tone: "danger" },
  BLOCKED_UNKNOWN_REQUIREMENT: { label: "Blocked — unknown requirement", tone: "danger" },
  BLOCKED_UNKNOWN_RULE_VERSION_STATUS: {
    label: "Blocked — unrecognised rule version status",
    tone: "danger",
  },
};

export function finalStateMeta(state: string | null | undefined) {
  if (!state) return { label: "—", tone: "neutral" as DecisionTone };
  return FINAL_STATE_META[state] ?? { label: state, tone: "neutral" as DecisionTone };
}

export function isBlockedState(state: string | null | undefined): boolean {
  return !!state && state.startsWith("BLOCKED_");
}

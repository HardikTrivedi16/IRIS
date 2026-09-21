"""
Rule Version evaluation.

Responsibilities (and nothing more — no regulatory knowledge lives here):
  * Evaluate the Rule Version's condition_expression_root_id via
    conditions.evaluate_condition().
  * Map the resulting Kleene value to an applicability state using THAT Rule
    Version's OWN output_mapping (never a globally hard-coded mapping).
  * Enforce Rule Version status safety (Phase 7 §4): ACTIVE may be presented
    as a production result; DRAFT may only be evaluated in NON_PRODUCTION
    (diagnostic/test) mode; any other/unknown status fails safe (blocked).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .conditions import evaluate_condition, flatten_condition_results, ConditionResult
from .kleene import Kleene, T, F, U


class EvaluationMode(Enum):
    PRODUCTION = "PRODUCTION"
    NON_PRODUCTION = "NON_PRODUCTION"


KNOWN_RULE_VERSION_STATUSES = {"DRAFT", "ACTIVE", "SUPERSEDED", "RETIRED"}

# States a Rule Version's status gate can force onto a Decision *before* any
# condition logic is consulted. These are engine-level safety states, not
# part of the Phase 2 §8 Applicability enum (APPLICABLE / NOT_APPLICABLE /
# UNKNOWN / REQUIRES_INFORMATION / REQUIRES_REVIEW) — they exist specifically
# so a DRAFT rule can never masquerade as one of those five authoritative
# states in production. See Phase7.md "Rule Version status safety".
BLOCKED_DRAFT_NOT_PRODUCTION = "BLOCKED_DRAFT_NOT_PRODUCTION"
BLOCKED_UNKNOWN_STATUS = "BLOCKED_UNKNOWN_RULE_VERSION_STATUS"


@dataclass
class RuleVersionEvaluation:
    rule_version_id: str
    rule_id: str
    status: str
    evaluation_mode: str
    blocked: bool
    blocked_reason: str | None
    kleene_result: Kleene | None
    final_state: str  # one of the 5 Phase 2 states, or a BLOCKED_* engine state
    condition_result: ConditionResult | None
    conditions_evaluated: list  # flattened list of ConditionResult
    missing_fact_keys: list
    outcome_text: str  # verbatim from the Rule Version's own *_outcome field
    is_non_production: bool
    # Phase 9 Section 5/Section 2 addition: the actual (TRUE/FALSE/UNKNOWN ->
    # state) mapping this Rule Version's own output_mapping used to reach
    # final_state -- exposed so an explanation can show that e.g.
    # RULE-0003's REQUIRES_REVIEW branch came from the Rule Version's own
    # authored data, never an engine-specific hard-code. Purely additive:
    # computed from the same normalization this module already performed
    # internally; does not change final_state/condition/missing-fact
    # behavior for any input.
    output_mapping: dict = field(default_factory=dict)


def evaluate_rule_version(
    rule_version_id: str,
    dataset,
    project_facts: dict,
    evaluation_mode: EvaluationMode = EvaluationMode.PRODUCTION,
) -> RuleVersionEvaluation:
    rv = dataset.rule_versions.get(rule_version_id)
    if rv is None:
        return RuleVersionEvaluation(
            rule_version_id=rule_version_id,
            rule_id="UNKNOWN",
            status="UNKNOWN",
            evaluation_mode=evaluation_mode.value,
            blocked=True,
            blocked_reason=f"rule version {rule_version_id} not found in dataset",
            kleene_result=None,
            final_state=BLOCKED_UNKNOWN_STATUS,
            condition_result=None,
            conditions_evaluated=[],
            missing_fact_keys=[],
            outcome_text="",
            is_non_production=(evaluation_mode == EvaluationMode.NON_PRODUCTION),
            output_mapping={},
        )

    status = rv.get("status", "")
    rule_id = rv.get("rule_id")

    # --- status gate (Phase 7 §4) --------------------------------------------
    if status == "ACTIVE":
        pass  # production evaluation allowed
    elif status == "DRAFT":
        if evaluation_mode != EvaluationMode.NON_PRODUCTION:
            return RuleVersionEvaluation(
                rule_version_id=rule_version_id,
                rule_id=rule_id,
                status=status,
                evaluation_mode=evaluation_mode.value,
                blocked=True,
                blocked_reason=(
                    "Rule Version status is DRAFT. A DRAFT rule version cannot be "
                    "presented as a production/authoritative Decision. Re-run with "
                    "evaluation_mode=NON_PRODUCTION to get a clearly-labelled "
                    "diagnostic evaluation."
                ),
                kleene_result=None,
                final_state=BLOCKED_DRAFT_NOT_PRODUCTION,
                condition_result=None,
                conditions_evaluated=[],
                missing_fact_keys=[],
                outcome_text="",
                is_non_production=False,
                output_mapping={},
            )
        # else: NON_PRODUCTION mode may proceed, clearly labelled as such below.
    else:
        # Unknown/unsupported status: fail safely rather than guess.
        return RuleVersionEvaluation(
            rule_version_id=rule_version_id,
            rule_id=rule_id,
            status=status,
            evaluation_mode=evaluation_mode.value,
            blocked=True,
            blocked_reason=f"unrecognized Rule Version status {status!r}; failing safe.",
            kleene_result=None,
            final_state=BLOCKED_UNKNOWN_STATUS,
            condition_result=None,
            conditions_evaluated=[],
            missing_fact_keys=[],
            outcome_text="",
            is_non_production=(evaluation_mode == EvaluationMode.NON_PRODUCTION),
            output_mapping={},
        )

    # --- evaluate the condition tree -----------------------------------------
    root_id = rv.get("condition_expression_root_id")
    cond_result = evaluate_condition(root_id, dataset.conditions, project_facts)
    flat = flatten_condition_results(cond_result)
    all_missing = sorted({k for cr in flat for k in cr.missing_fact_keys})

    # Kleene short-circuit fix (Phase 8 finding; see RULE-0005-V1's own
    # authored `engine_note`, which anticipated exactly this): a composite
    # OR/AND can already be fully resolved to TRUE or FALSE at the root even
    # though some leaf/child facts feeding OTHER branches were never
    # supplied (e.g. liquid-milk alone resolves COND-0007 to TRUE even if
    # milk-solids capacity was never given). In that case nothing is still
    # "needed to resolve this" — the result is final — so those irrelevant
    # missing facts must not be surfaced as outstanding. Only when the root
    # itself is genuinely UNKNOWN do the accumulated leaf-level missing keys
    # describe facts that could still change the outcome.
    missing = all_missing if cond_result.result is U else []

    # PyYAML parses bare TRUE/FALSE scalars as Python bools, not the strings
    # "TRUE"/"FALSE" — normalize so output_mapping lookups by "TRUE"/"FALSE"/
    # "UNKNOWN" always work regardless of how a given YAML file wrote them.
    raw_mapping = rv.get("output_mapping") or {}
    output_mapping = {}
    for k, v in raw_mapping.items():
        if k is True:
            output_mapping["TRUE"] = v
        elif k is False:
            output_mapping["FALSE"] = v
        else:
            output_mapping[str(k)] = v
    kleene_result = cond_result.result

    if kleene_result is T:
        final_state = output_mapping.get("TRUE", "APPLICABLE")
        outcome_text = rv.get("true_outcome", "")
    elif kleene_result is F:
        final_state = output_mapping.get("FALSE", "NOT_APPLICABLE")
        outcome_text = rv.get("false_outcome", "")
    else:
        # UNKNOWN: Phase 2 §10 example comment — REQUIRES_INFORMATION if a
        # named fact is missing, else bare UNKNOWN. We track missing facts
        # explicitly, so this is data-driven, not guessed.
        if missing:
            final_state = output_mapping.get("UNKNOWN", "REQUIRES_INFORMATION")
        else:
            final_state = "UNKNOWN"
        outcome_text = rv.get("unknown_outcome", "")

    return RuleVersionEvaluation(
        rule_version_id=rule_version_id,
        rule_id=rule_id,
        status=status,
        evaluation_mode=evaluation_mode.value,
        blocked=False,
        blocked_reason=None,
        kleene_result=kleene_result,
        final_state=final_state,
        condition_result=cond_result,
        conditions_evaluated=flat,
        missing_fact_keys=missing,
        outcome_text=outcome_text,
        is_non_production=(status == "DRAFT"),
        output_mapping=dict(output_mapping),
    )

"""
Deterministic Project Change Impact (P0-B).

    CURRENT PROJECT FACTS ──► Evaluation A
                │
                ├─ copy facts, apply proposed change to the COPY
                │
    PROPOSED FACTS ─────────► Evaluation B

                    A vs B ──► deterministic diff

This module is an ADAPTER. It owns no regulatory logic:

* Both evaluations are produced by the same frozen ``iris_engine`` the rest
  of the API uses, through ``engine_service.evaluate_all`` — there is no
  second applicability evaluator anywhere in IRIS.
* The DRAFT/PRODUCTION lifecycle is untouched. In PRODUCTION mode every
  Rule Version in the current dataset is DRAFT, so both sides come back
  BLOCKED_DRAFT_NOT_PRODUCTION and the diff honestly reports UNCHANGED with
  ``authoritative: false`` — it does not quietly switch to NON_PRODUCTION to
  manufacture a more impressive answer.
* Nothing is persisted. The proposed facts exist only as a local dict for
  the duration of the call; ``engine_service.evaluate_*`` does not write,
  and this module never calls the store.
* Which facts can be changed, and what type each value must be, comes from
  ``fact_registry`` (derived from the dataset). No threshold, fact key or
  scenario is hardcoded here.
"""
from __future__ import annotations

from typing import Any

from . import engine_service
from .fact_registry import fact_registry_index, validate_facts

# --- Diff categories --------------------------------------------------------
# Deliberately descriptive of the ENGINE STATE TRANSITION, never of legal
# consequence. NEWLY_APPLICABLE means exactly NOT_APPLICABLE -> APPLICABLE,
# NO_LONGER_APPLICABLE exactly APPLICABLE -> NOT_APPLICABLE. Any move into
# REQUIRES_INFORMATION / REQUIRES_REVIEW is reported as that state; every
# other change of outcome is CHANGED.
UNCHANGED = "UNCHANGED"
NEWLY_APPLICABLE = "NEWLY_APPLICABLE"
NO_LONGER_APPLICABLE = "NO_LONGER_APPLICABLE"
REQUIRES_INFORMATION = "REQUIRES_INFORMATION"
REQUIRES_REVIEW = "REQUIRES_REVIEW"
CHANGED = "CHANGED"

APPLICABLE_STATE = "APPLICABLE"
NOT_APPLICABLE_STATE = "NOT_APPLICABLE"

CATEGORY_ORDER = {
    NEWLY_APPLICABLE: 0,
    NO_LONGER_APPLICABLE: 1,
    REQUIRES_REVIEW: 2,
    REQUIRES_INFORMATION: 3,
    CHANGED: 4,
    UNCHANGED: 5,
}


def _classification_signature(decision: dict) -> dict | None:
    """The part of a classification sub-group that can move independently of
    the Requirement's own ``final_state``.

    REQ-0004 is the live example: its base rule (industry == FOOD) stays
    APPLICABLE while the Central/State licensing-tier sub-rules flip as
    capacity facts change. ``decision.py`` only propagates the sub-group up
    to ``final_state`` when it is REQUIRES_REVIEW/REQUIRES_INFORMATION, so
    comparing ``final_state`` alone would report UNCHANGED for a change that
    genuinely moved which licensing tier the engine resolves. Copied
    verbatim from the engine's own classification block — nothing inferred.
    """
    block = decision.get("classification")
    if not block:
        return None
    return {
        "combined_state": block.get("combined_state"),
        "rule_results": dict(block.get("rule_results") or {}),
        "conflict_id": block.get("conflict_id"),
        "review_reason": block.get("review_reason"),
    }


def _categorise(before: dict, after: dict) -> str:
    """Classify one requirement's before/after engine states.

    Pure function of the two Decisions' ``final_state``, missing-fact lists
    and classification sub-group results, so the same pair always produces
    the same category.
    """
    b_state = before.get("final_state")
    a_state = after.get("final_state")

    if b_state == a_state:
        # Same outcome, but the reason may have moved (e.g. a different
        # fact is now the missing one, or a classification sub-rule
        # resolved differently). Report that rather than hiding it.
        b_missing = sorted(before.get("missing_project_fact_keys") or [])
        a_missing = sorted(after.get("missing_project_fact_keys") or [])
        if b_missing != a_missing:
            return CHANGED
        if _classification_signature(before) != _classification_signature(after):
            return CHANGED
        return UNCHANGED

    # Unresolved outcomes first: moving INTO a missing-data or review state
    # must never be reported as "no longer applicable" — missing data is not
    # a negative determination (the engine's own core rule).
    if a_state == REQUIRES_REVIEW:
        return REQUIRES_REVIEW
    if a_state == REQUIRES_INFORMATION:
        return REQUIRES_INFORMATION
    # The two applicability categories are reserved for the exact definite
    # transitions they name. REQUIRES_REVIEW -> APPLICABLE (a review that
    # resolved) or REQUIRES_INFORMATION -> APPLICABLE (a fact supplied) are
    # NOT "newly applicable" — the engine never said NOT_APPLICABLE before —
    # so they fall through to CHANGED.
    if b_state == NOT_APPLICABLE_STATE and a_state == APPLICABLE_STATE:
        return NEWLY_APPLICABLE
    if b_state == APPLICABLE_STATE and a_state == NOT_APPLICABLE_STATE:
        return NO_LONGER_APPLICABLE
    return CHANGED


def _side(decision: dict) -> dict:
    """The subset of a Decision the diff surfaces per side. Every value is
    copied verbatim from the engine's own Decision dict."""
    return {
        "final_state": decision.get("final_state"),
        "reason_text": decision.get("reason_text"),
        "missing_project_fact_keys": list(decision.get("missing_project_fact_keys") or []),
        "rule_version_id": decision.get("rule_version_id"),
        "rule_version_status": decision.get("rule_version_status"),
        "decision_id": decision.get("decision_id"),
        "review_reason": decision.get("review_reason"),
        "conflict_id": decision.get("conflict_id"),
        "is_non_production_result": decision.get("is_non_production_result", False),
        # None for requirements with no classification sub-group.
        "classification": _classification_signature(decision),
    }


def _facts_actually_used(decision: dict) -> set[str]:
    used: set[str] = set()
    explanation = decision.get("explanation") or {}
    used.update(explanation.get("input_facts_used") or [])
    used.update(explanation.get("declared_required_facts") or [])
    used.update(decision.get("missing_project_fact_keys") or [])
    return used


def analyse_change_impact(
    project_id: str,
    current_facts: dict[str, Any],
    proposed_changes: dict[str, Any],
    evaluation_mode: str = "PRODUCTION",
) -> dict:
    """Evaluate every requirement twice and return the deterministic diff.

    ``proposed_changes`` is validated against the dataset-derived fact
    registry first (unknown key / wrong type -> FactValidationError), then
    merged onto a COPY of ``current_facts``. ``current_facts`` is never
    mutated and nothing is written to any store.
    """
    validated = validate_facts(proposed_changes)

    baseline_facts = dict(current_facts)
    proposed_facts = {**baseline_facts, **validated}

    # Facts whose value the change actually moves. A "change" that sets a
    # fact to the value it already had is reported as a no-op rather than
    # being presented as a change the user made.
    effective_changes: list[dict] = []
    noop_changes: list[dict] = []
    registry = fact_registry_index()
    for key, new_value in sorted(validated.items()):
        old_value = baseline_facts.get(key)
        entry = registry.get(key) or {}
        record = {
            "key": key,
            "previous_value": old_value,
            "proposed_value": new_value,
            "value_type": entry.get("value_type"),
            "units": entry.get("units") or [],
        }
        (noop_changes if old_value == new_value else effective_changes).append(record)

    before_decisions = engine_service.evaluate_all(
        project_id=project_id,
        project_facts=baseline_facts,
        evaluation_mode=evaluation_mode,
    )
    after_decisions = engine_service.evaluate_all(
        project_id=project_id,
        project_facts=proposed_facts,
        evaluation_mode=evaluation_mode,
    )

    after_by_req = {d["requirement_id"]: d for d in after_decisions}
    ds = engine_service.get_dataset()

    results: list[dict] = []
    for before in before_decisions:
        req_id = before["requirement_id"]
        after = after_by_req.get(req_id)
        if after is None:  # pragma: no cover - evaluate_all is symmetric
            continue
        category = _categorise(before, after)
        relevant = sorted(
            _facts_actually_used(before) | _facts_actually_used(after)
        )
        changed_keys = [c["key"] for c in effective_changes]
        results.append(
            {
                "requirement_id": req_id,
                "requirement_title": (ds.requirements.get(req_id) or {}).get("title") or req_id,
                "authority_id": (ds.requirements.get(req_id) or {}).get("authority_id"),
                "category": category,
                "before": _side(before),
                "after": _side(after),
                "facts_this_requirement_uses": relevant,
                "changed_facts_used_by_this_requirement": [
                    k for k in changed_keys if k in relevant
                ],
            }
        )

    results.sort(
        key=lambda r: (CATEGORY_ORDER.get(r["category"], 99), r["requirement_id"])
    )

    summary: dict[str, int] = {c: 0 for c in CATEGORY_ORDER}
    for r in results:
        summary[r["category"]] += 1

    blocked_states = {
        r["after"]["final_state"]
        for r in results
        if (r["after"]["final_state"] or "").startswith("BLOCKED_")
    }
    all_blocked = bool(results) and len(blocked_states) > 0 and all(
        (r["after"]["final_state"] or "").startswith("BLOCKED_") for r in results
    )

    notes: list[str] = []
    if all_blocked:
        notes.append(
            "Every requirement is currently blocked by the Rule Version "
            "lifecycle, so this comparison cannot produce an authoritative "
            "regulatory result. The dataset contains zero ACTIVE Rule "
            f"Versions; the blocking state(s) returned were: "
            f"{', '.join(sorted(blocked_states))}."
        )
    if evaluation_mode != "PRODUCTION":
        notes.append(
            "Evaluated in NON_PRODUCTION diagnostic mode. The result shows "
            "how the deterministic logic behaves, and is explicitly NOT an "
            "authoritative regulatory determination."
        )
    if noop_changes:
        notes.append(
            "Some proposed values matched the project's current value and "
            "therefore could not change any outcome: "
            + ", ".join(c["key"] for c in noop_changes)
            + "."
        )
    if not effective_changes:
        notes.append(
            "No effective fact change was supplied, so both evaluations used "
            "identical inputs and the diff is necessarily empty."
        )

    return {
        "project_id": project_id,
        "evaluation_mode": evaluation_mode,
        "engine_version": (before_decisions[0]["engine_version"] if before_decisions else None),
        # An authoritative result requires PRODUCTION mode AND at least one
        # requirement that was not blocked by the DRAFT lifecycle.
        "authoritative": evaluation_mode == "PRODUCTION" and not all_blocked,
        "proposed_changes": effective_changes,
        "ignored_changes": noop_changes,
        "summary": summary,
        "requirements": results,
        "notes": notes,
        "persistence_note": (
            "Preview only — the proposed facts were used for this comparison "
            "and were NOT written to this project's stored Project Facts."
        ),
    }

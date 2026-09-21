"""
Structured audit trail (Phase 9 Section 14, Section 15).

``build_audit_record`` reshapes an already-built Decision dict into a
security-conscious, strictly machine-readable audit record covering exactly
Section 14's list: what was evaluated, when, with which engine, with which
rule version, using which facts, what conditions returned, what decision was
produced, why, what evidence/provenance supported it, whether a
review/conflict occurred. It never re-evaluates anything and never adds
information the Decision doesn't already carry.

Section 15 (determinism/security) is enforced by ``_strip_forbidden``: any
key whose name suggests a secret, credential, or filesystem path is dropped
recursively before the record is returned. In practice this engine's data
model has no secrets and no user-facing stack traces reach a Decision (every
evaluation failure mode in conditions.py/rules.py fails safe to UNKNOWN/
BLOCKED_* with a short message, never a raised exception or a traceback) --
this is a defensive backstop, not evidence that a leak was found.
"""
from __future__ import annotations

_FORBIDDEN_KEY_SUBSTRINGS = (
    "_source_file", "source_file", "secret", "credential", "password",
    "api_key", "apikey", "token",
)


def _strip_forbidden(obj):
    if isinstance(obj, dict):
        return {
            k: _strip_forbidden(v)
            for k, v in obj.items()
            if not any(bad in str(k).lower() for bad in _FORBIDDEN_KEY_SUBSTRINGS)
        }
    if isinstance(obj, list):
        return [_strip_forbidden(v) for v in obj]
    return obj


def build_audit_record(decision: dict) -> dict:
    explanation = decision.get("explanation") or {}
    record = {
        "decision_id": decision.get("decision_id"),
        "what_was_evaluated": {
            "project_id": decision.get("project_id"),
            "requirement_id": decision.get("requirement_id"),
        },
        "when": decision.get("evaluated_at"),
        "engine_version": decision.get("engine_version"),
        "rule_version_used": {
            "rule_id": decision.get("rule_id"),
            "rule_version_id": decision.get("rule_version_id"),
            "status": decision.get("rule_version_status"),
        },
        "facts_used": explanation.get("input_facts_used", []),
        "conditions_returned": decision.get("conditions_evaluated", []),
        "condition_evaluation_tree": explanation.get("condition_evaluation_tree"),
        "decision_produced": decision.get("final_state"),
        "why": explanation.get("narrative"),
        "evidence_and_provenance": decision.get("provenance"),
        "review_or_conflict": {
            "review_reason": decision.get("review_reason"),
            "conflict_id": decision.get("conflict_id"),
            "classification": decision.get("classification"),
        },
        "evaluation_mode": decision.get("evaluation_mode"),
        "is_non_production_result": decision.get("is_non_production_result"),
    }
    return _strip_forbidden(record)

"""
Condition Evaluation Tree (Phase 9 Section 2-3).

This module contains NO regulatory knowledge and evaluates nothing itself.
It only *renders* the ConditionResult tree that ``conditions.py`` already
produced (conditions.py is not modified) into the nested, auditor-readable
shape Phase 9 Section 3 specifies -- for each node: condition ID, operator,
operands, actual project value, expected value, result, missing fact,
error -- by joining that ConditionResult against the Condition's own
authored definition in the dataset. It never re-evaluates a condition,
never second-guesses the Kleene result it is given, and never fabricates a
value the underlying evaluation didn't already determine.
"""
from __future__ import annotations

from .conditions import ConditionResult, MISSING, _get_fact


def _display_actual_value(project_facts: dict, key: str | None):
    """Read-only, presentational mirror of conditions.py's own missing-value
    policy (never returns a fabricated default) -- reused via _get_fact
    rather than reimplemented, so the two can never drift apart."""
    if key is None:
        return None
    val = _get_fact(project_facts, key)
    return None if val is MISSING else val


def build_condition_tree(cr: ConditionResult | None, conditions: dict, project_facts: dict) -> dict | None:
    """Recursively renders a ConditionResult (leaf or composite, already
    evaluated by conditions.evaluate_condition) into the Phase 9 Section 3
    tree shape. Returns None only when there is no ConditionResult to render
    at all (e.g. a blocked DRAFT-in-PRODUCTION evaluation never reached
    condition evaluation)."""
    if cr is None:
        return None

    # Deliberately copy out only the specific fields we need -- dataset
    # records also carry a "_source_file" absolute filesystem path
    # (loader.py bookkeeping) that must never reach an explanation/audit
    # surface (Phase 9 Section 15).
    cond_def = conditions.get(cr.condition_id) or {}
    predicate_type = cond_def.get("predicate_type")
    operator = cond_def.get("operator")

    node = {
        "condition_id": cr.condition_id,
        "predicate_type": predicate_type,
        "operator": operator,
        "result": cr.result.value if cr.result is not None else None,
        "missing_fact_keys": list(cr.missing_fact_keys),
        "error": cr.error,
    }

    if predicate_type == "COMPOSITE":
        node["operands"] = list(cond_def.get("child_condition_ids") or [])
        node["target_variable_key"] = None
        node["expected_value"] = None
        node["actual_project_value"] = None
        node["children"] = [
            build_condition_tree(child, conditions, project_facts) for child in cr.children
        ]
    else:
        target_key = cond_def.get("target_variable_key")
        node["operands"] = [target_key] if target_key else []
        node["target_variable_key"] = target_key
        node["expected_value"] = cond_def.get("comparison_value")
        node["actual_project_value"] = _display_actual_value(project_facts, target_key)
        node["children"] = []

    return node


def render_condition_tree_text(node: dict | None, prefix: str = "", is_last: bool = True) -> str:
    """Human-readable ASCII rendering matching the Phase 9 Section 3 example
    shape (AND/OR branches with TRUE/FALSE/UNKNOWN leaves). For docs/CLI use
    only -- never used to build a Decision artifact, which stays structured
    JSON per Section 14's preference for machine-readable output."""
    if node is None:
        return prefix + "(no condition tree -- evaluation did not reach condition logic)\n"

    connector = "" if prefix == "" else ("└── " if is_last else "├── ")
    if node["predicate_type"] == "COMPOSITE":
        label = f"{node['operator']}"
    else:
        expected = node["expected_value"]
        actual = node["actual_project_value"]
        label = (
            f"{node['condition_id']} [{node['target_variable_key']} {node['operator']} "
            f"{expected!r}] actual={actual!r} -> {node['result']}"
        )
        if node["missing_fact_keys"]:
            label += f" (missing: {', '.join(node['missing_fact_keys'])})"
        if node["error"]:
            label += f" (error: {node['error']})"

    out = prefix + connector + label + (f" -> {node['result']}" if node["predicate_type"] == "COMPOSITE" else "") + "\n"
    child_prefix = prefix + ("    " if is_last else "│   ") if prefix != "" else ""
    children = node.get("children") or []
    for i, child in enumerate(children):
        out += render_condition_tree_text(child, child_prefix, is_last=(i == len(children) - 1))
    return out

"""
Supported Project Fact registry — derived, never authored.

Every entry in this registry is computed by reading the frozen regulatory
dataset that ``engine_service`` already loads (conditions + rule versions +
rules + requirements). Nothing here authors a fact key, a unit, a threshold,
an allowed value, or a regulatory meaning: if the dataset does not mention
it, this module does not know about it.

Why this exists
---------------
Two features need to know "which project facts can a user meaningfully
supply, and what shape must the value be?":

  * P0-A fact capture — ask only for facts some Rule Version actually
    declares in ``required_project_facts``.
  * P0-B change impact — validate a proposed fact change before handing it
    to the engine, so an unsupported key or a wrong-typed value is rejected
    with a clear message instead of silently evaluating to UNKNOWN.

Deriving the registry (rather than hardcoding a list) is what keeps both
features generic: when the regulatory-research teammate adds a verified
Rule Version with new conditions, the registry, the fact-capture form and
change impact all pick it up with no code change — and no threshold such as
50000 L/day is ever written into application code.

Honesty constraints
-------------------
* ``values_referenced_by_rules`` is exactly that — the comparison values the
  dataset's own conditions mention. It is NOT an enumeration of legally
  permitted values, and is labelled as such everywhere it surfaces.
* ``value_type`` is inferred structurally from ``predicate_type`` (what the
  engine's own evaluator requires of the operand), not from any regulatory
  interpretation.
* A fact key used with conflicting predicate types is reported as
  ``"mixed"`` and marked not safely typed, rather than being guessed.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from . import engine_service

# predicate_type -> the operand shape iris_engine.conditions._apply_leaf_operator
# actually requires. This is a statement about the evaluator, not about law.
_PREDICATE_VALUE_TYPE: dict[str, str] = {
    "BOOLEAN_EQUALS": "boolean",
    "THRESHOLD_COMPARISON": "number",
    "SET_MEMBERSHIP": "string",
}


class FactValidationError(Exception):
    """One or more proposed fact keys/values are not supported by the
    current regulatory dataset. Carries a per-key breakdown so the API can
    return a precise 422 rather than a generic failure."""

    def __init__(self, errors: list[dict]) -> None:
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


def _flatten_comparison_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


@lru_cache
def build_fact_registry() -> tuple[dict, ...]:
    """Every ``project.*`` fact key any Condition in the dataset targets.

    Returned as a tuple of plain dicts (hashable container so ``lru_cache``
    is safe; callers copy before mutating). Sorted by key for determinism —
    two processes loading the same dataset produce byte-identical output.
    """
    ds = engine_service.get_dataset()

    by_key: dict[str, dict] = {}

    for cond_id, cond in sorted(ds.conditions.items()):
        target_key = cond.get("target_variable_key")
        if not target_key:
            continue  # COMPOSITE nodes have no operand of their own
        predicate_type = cond.get("predicate_type")
        entry = by_key.setdefault(
            target_key,
            {
                "key": target_key,
                "value_type": None,
                "predicate_types": set(),
                "units": set(),
                "condition_ids": [],
                "values_referenced_by_rules": [],
                "rule_version_ids": [],
                "requirement_ids": [],
            },
        )
        entry["predicate_types"].add(predicate_type)
        entry["condition_ids"].append(cond_id)
        if cond.get("unit"):
            entry["units"].add(cond["unit"])
        for v in _flatten_comparison_values(cond.get("comparison_value")):
            if v not in entry["values_referenced_by_rules"]:
                entry["values_referenced_by_rules"].append(v)

    # Which Rule Versions declare the fact as required, and which
    # Requirements those Rule Versions ultimately decide. Both links come
    # straight from the dataset's own fields.
    for rv_id, rv in sorted(ds.rule_versions.items()):
        rule = ds.rules.get(rv.get("rule_id")) or {}
        requirement_id = rule.get("requirement_id")
        for key in rv.get("required_project_facts") or []:
            entry = by_key.get(key)
            if entry is None:
                # A Rule Version declares a fact no Condition targets. Record
                # it rather than dropping it — it is still a fact a user can
                # be asked for, we just can't infer its type from a predicate.
                entry = by_key.setdefault(
                    key,
                    {
                        "key": key,
                        "value_type": None,
                        "predicate_types": set(),
                        "units": set(),
                        "condition_ids": [],
                        "values_referenced_by_rules": [],
                        "rule_version_ids": [],
                        "requirement_ids": [],
                    },
                )
            if rv_id not in entry["rule_version_ids"]:
                entry["rule_version_ids"].append(rv_id)
            if requirement_id and requirement_id not in entry["requirement_ids"]:
                entry["requirement_ids"].append(requirement_id)

    out: list[dict] = []
    for key in sorted(by_key):
        entry = by_key[key]
        predicate_types = sorted(p for p in entry["predicate_types"] if p)
        value_types = {
            _PREDICATE_VALUE_TYPE.get(p) for p in predicate_types
        } - {None}
        if len(value_types) == 1:
            value_type = value_types.pop()
        elif not value_types:
            value_type = "unknown"
        else:
            value_type = "mixed"
        out.append(
            {
                "key": key,
                "value_type": value_type,
                "typed_input_supported": value_type in ("boolean", "number", "string"),
                "predicate_types": predicate_types,
                "units": sorted(entry["units"]),
                "condition_ids": sorted(entry["condition_ids"]),
                "values_referenced_by_rules": entry["values_referenced_by_rules"],
                "rule_version_ids": sorted(entry["rule_version_ids"]),
                "requirement_ids": sorted(entry["requirement_ids"]),
                "values_note": (
                    "Comparison values that this dataset's own Conditions "
                    "reference for this fact. This is NOT an exhaustive or "
                    "legally authoritative list of permitted values."
                ),
            }
        )
    return tuple(out)


def fact_registry_index() -> dict[str, dict]:
    return {e["key"]: e for e in build_fact_registry()}


def required_facts_for_requirement(requirement_id: str) -> list[dict]:
    """The fact entries any Rule Version deciding ``requirement_id``
    declares as required (including its classification sub-rules)."""
    ds = engine_service.get_dataset()
    req = ds.requirements.get(requirement_id)
    if req is None:
        return []

    rule_ids = [req.get("evaluated_by_rule_id")]
    rule_ids.extend(req.get("classification_rule_ids") or [])

    wanted: list[str] = []
    for rule_id in [r for r in rule_ids if r]:
        rv_id = ds.latest_rule_version_id(rule_id)
        rv = ds.rule_versions.get(rv_id) if rv_id else None
        for key in (rv or {}).get("required_project_facts") or []:
            if key not in wanted:
                wanted.append(key)

    index = fact_registry_index()
    return [index[k] for k in sorted(wanted) if k in index]


def _type_error(key: str, expected: str, value: Any) -> dict:
    return {
        "key": key,
        "code": "INVALID_VALUE_TYPE",
        "message": (
            f"{key} expects a {expected} value "
            f"(got {type(value).__name__}: {value!r})."
        ),
    }


def validate_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Validate a caller-supplied fact dict against the derived registry.

    Returns the same values unchanged on success — this deliberately does
    NOT coerce ("true" -> True, "500" -> 500). A regulatory input that had
    to be guessed at is exactly the kind of silent assumption the engine's
    missing-data policy exists to prevent; the caller is told precisely what
    was wrong instead.

    Raises FactValidationError listing every problem found (not just the
    first), so a form can highlight all bad fields at once.
    """
    index = fact_registry_index()
    errors: list[dict] = []

    for key, value in facts.items():
        entry = index.get(key)
        if entry is None:
            errors.append(
                {
                    "key": key,
                    "code": "UNKNOWN_FACT_KEY",
                    "message": (
                        f"{key!r} is not a project fact any Rule Version or "
                        "Condition in the current regulatory dataset refers "
                        "to, so changing it cannot affect any decision."
                    ),
                }
            )
            continue

        if value is None:
            # Explicitly clearing a fact back to "unknown" is legitimate:
            # iris_engine.conditions._get_fact treats None as MISSING, which
            # resolves UNKNOWN rather than FALSE.
            continue

        value_type = entry["value_type"]
        if value_type == "boolean":
            if not isinstance(value, bool):
                errors.append(_type_error(key, "boolean", value))
        elif value_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(_type_error(key, "numeric", value))
            elif not math.isfinite(value):
                errors.append(
                    {
                        "key": key,
                        "code": "INVALID_VALUE_TYPE",
                        "message": f"{key} expects a finite number (got {value!r}).",
                    }
                )
        elif value_type == "string":
            if not isinstance(value, str) or not value.strip():
                errors.append(_type_error(key, "non-empty string", value))
        else:
            errors.append(
                {
                    "key": key,
                    "code": "UNTYPED_FACT_KEY",
                    "message": (
                        f"{key} is referenced by the dataset but its value type "
                        f"could not be determined ({value_type}); it cannot be "
                        "set through this endpoint."
                    ),
                }
            )

    if errors:
        raise FactValidationError(errors)
    return dict(facts)

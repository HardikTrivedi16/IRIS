"""
Semantic reproducibility comparison (Phase 9 Section 10).

``semantically_equal`` compares two Decisions (or Snapshots, or any nested
structure) while ignoring only genuinely non-semantic, timestamp/identity
fields -- exactly what Section 10 asks for: "Ignore non-semantic fields such
as timestamps when comparing results." Everything else (final_state,
condition results, missing facts, review reasons, conflict results,
dependency results, provenance references) must match exactly.
"""
from __future__ import annotations

# Field names that are allowed to legitimately differ between two
# evaluations of the *same semantic inputs* run at two different real-world
# instants, or given two different caller-supplied evaluated_at values.
# decision_id is included even though snapshot.py deliberately makes it
# evaluated_at-independent, because a Decision Snapshot's OWN decision_id
# and a plain Decision's decision_id are the same value by construction --
# stripping it here costs nothing and keeps this comparison correct even if
# that invariant is ever revisited.
_VOLATILE_KEYS = {"evaluated_at", "decision_id", "evaluation_timestamp"}


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def semantically_equal(a, b) -> bool:
    return _strip(a) == _strip(b)


def semantic_diff(a, b) -> dict:
    """A small best-effort diff for debugging a reproducibility failure --
    not used by the engine itself, only by tests/tooling."""
    sa, sb = _strip(a), _strip(b)
    if sa == sb:
        return {}
    if not (isinstance(sa, dict) and isinstance(sb, dict)):
        return {"a": sa, "b": sb}
    diff = {}
    for k in sorted(set(sa) | set(sb)):
        va, vb = sa.get(k, "<absent>"), sb.get(k, "<absent>")
        if va != vb:
            diff[k] = {"a": va, "b": vb}
    return diff

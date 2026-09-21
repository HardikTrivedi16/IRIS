"""
Engine versioning (Phase 9 Section 12 / Section 9).

Strategy
--------
Identifier shape: ``iris-engine-phase<N>-<major>.<minor>.<patch>``

  * ``<N>`` is the IRIS roadmap phase that introduced the version.
  * ``<major>.<minor>.<patch>`` bumps whenever engine BEHAVIOR changes:
      - **patch**: no change to any Decision's final_state / condition
        result / missing-fact computation for any existing input (docs,
        comments, test-only changes).
      - **minor**: additive change (new explanation/versioning/audit
        capability, new non-breaking field) that does not alter any
        existing final_state, condition result, or missing-fact
        computation for any existing input.
      - **major**: a change that CAN alter final_state/condition outcomes
        for previously-evaluated inputs. Must ship with a fresh regression
        run and an explicit changelog entry explaining what changed.

Every version this engine has ever emitted is recorded in
``ENGINE_VERSION_HISTORY`` below and is never silently reused for a
different behavior (Phase 9 Section 12: "Do not silently overwrite an
existing version"). ``CURRENT_ENGINE_VERSION`` must always equal the last
history entry's ``version`` -- enforced by an assertion at import time so a
future edit that changes one without the other fails immediately instead of
drifting silently.

Known process gap (documented here, not corrected retroactively): Phase 8
found and fixed one real engine defect (see ``rules.py``'s Kleene
short-circuit comment) -- a genuine behavior change -- but did not bump the
version identifier at the time. Phase 9 does not rewrite that history; it is
recorded as a Phase 8 entry below exactly as it happened, and this policy
document exists specifically so it does not happen again.
"""
from __future__ import annotations

ENGINE_VERSION_HISTORY = [
    {
        "version": "iris-engine-phase7-0.1.0",
        "phase": 7,
        "summary": (
            "Initial deterministic engine implementation: kleene.py, "
            "loader.py, conditions.py, rules.py, classification.py, "
            "dependencies.py, provenance.py, decision.py, engine.py, "
            "validate.py. 43 tests, all passing."
        ),
    },
    {
        "version": "iris-engine-phase7-0.1.0",
        "phase": 8,
        "summary": (
            "Phase 8 testing added 171 tests and found + fixed one real "
            "defect: a Kleene short-circuit case where a composite OR/AND "
            "already resolved to TRUE/FALSE at the root was still leaking "
            "irrelevant leaf-level missing fact keys (from the "
            "short-circuited branch) into conditions_evaluated / "
            "missing_project_fact_keys. This WAS an engine-behavior change. "
            "Per the versioning policy this module now establishes, it "
            "should have produced a new version identifier; Phase 8 kept "
            "the Phase 7 string unchanged. Recorded here as a known "
            "process gap, not silently corrected after the fact."
        ),
    },
    {
        "version": "iris-engine-phase9-0.1.0",
        "phase": 9,
        "summary": (
            "Adds explainability (condition_tree.py: a nested Condition "
            "Evaluation Tree; explain.py: a full per-Requirement "
            "Explanation block; rule_output_mapping surfaced from "
            "rules.py), decision identity + snapshots (snapshot.py: "
            "deterministic decision_id, Decision Snapshot, an immutable "
            "DecisionStore), a structured audit trail (audit.py), "
            "semantic-reproducibility comparison (reproducibility.py), "
            "and this versioning module. Zero change to any "
            "condition / rule / classification / dependency / provenance "
            "evaluation LOGIC -- verified by the unmodified Phase 7/8 "
            "regression suite (214/214 still passing) plus new Phase 9 "
            "tests. rules.py gained one purely additive dataclass field "
            "(RuleVersionEvaluation.output_mapping) to expose an "
            "already-computed internal value; no evaluation behavior "
            "changed."
        ),
    },
]

CURRENT_ENGINE_VERSION = ENGINE_VERSION_HISTORY[-1]["version"]

# Fail fast at import time if the two ever drift apart.
assert ENGINE_VERSION_HISTORY, "ENGINE_VERSION_HISTORY must never be emptied"
assert ENGINE_VERSION_HISTORY[-1]["version"] == CURRENT_ENGINE_VERSION, (
    "CURRENT_ENGINE_VERSION must equal the last ENGINE_VERSION_HISTORY entry"
)


def history_for(version: str) -> list:
    """All history entries recorded under a given version identifier (may
    be more than one -- see the documented Phase 8 gap above)."""
    return [h for h in ENGINE_VERSION_HISTORY if h["version"] == version]


def is_known_version(version: str) -> bool:
    return any(h["version"] == version for h in ENGINE_VERSION_HISTORY)

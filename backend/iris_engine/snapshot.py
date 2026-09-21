"""
Decision identity, Decision Snapshots, and an immutable DecisionStore
(Phase 9 Section 8, Section 10, Section 11, Section 12).

Decision ID
-----------
``compute_decision_id`` is a deterministic (never random, never
wall-clock-based) hash of exactly the inputs that determine a Decision's
*semantic* content: project_id, requirement_id, engine_version, the
(rule_version_id, status) pairs actually consulted, and the input fact
snapshot actually used. It deliberately does NOT include ``evaluated_at``:

  * Phase 8's existing regression test
    ``test_decision_deterministic_ignoring_timestamp`` requires that two
    Decisions for identical inputs be identical in every field except the
    single top-level ``evaluated_at`` key -- a decision_id that varied with
    evaluated_at would violate that.
  * It also directly implements Phase 9 Section 10's reproducibility
    guarantee: same engine version + same Rule Version(s) (id AND status,
    since a Rule Version can be promoted DRAFT->ACTIVE in place under the
    same id -- Phase 2's own versioning model) + same input fact snapshot +
    same evaluation mode ⇒ same decision_id ⇒ semantically identical
    Decision. Two evaluations of the same facts at two different real-world
    instants are, correctly, the same semantic decision with two different
    Snapshots (see DecisionSnapshot below, which does carry its own
    evaluated_at).

Decision Snapshot
------------------
``build_snapshot`` assembles the Phase 9 Section 8 artifact: decision_id,
project_id, evaluated_at, engine_version, rule_version_ids,
input_fact_snapshot, evaluation_mode, result, explanation. It is a
standalone object (not embedded inside the live Decision return value --
see explain.py's module docstring for why), produced on request from an
already-built Decision.

DecisionStore
-------------
A minimal immutable, in-memory store demonstrating Phase 9 Section 11
("A stored Decision must NOT silently change") and Section 12 ("Do not
silently overwrite an existing version"): once a decision_id is stored, a
second ``put`` under the same id is only accepted if the content is
byte-identical; otherwise it raises rather than overwriting. ``get`` always
returns a deep copy, so nothing the caller does to a fetched snapshot -- or
to the live dataset/project facts afterwards -- can retroactively change
what a later ``get`` of the same id returns.
"""
from __future__ import annotations

import copy
import hashlib
import json


def compute_decision_id(
    *,
    project_id: str,
    requirement_id: str,
    engine_version: str,
    rule_versions: list,  # list of (rule_version_id, status) pairs
    input_fact_snapshot: dict,
    evaluation_mode: str,
) -> str:
    payload = {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "engine_version": engine_version,
        "rule_versions": sorted(
            [list(rv) for rv in rule_versions], key=lambda pair: (pair[0] or "", pair[1] or "")
        ),
        "input_fact_snapshot": input_fact_snapshot,
        "evaluation_mode": evaluation_mode,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()[:24]
    return f"DEC-{requirement_id}-{digest}"


def build_snapshot(
    *,
    decision: dict,
    project_facts: dict,
) -> dict:
    """Builds a standalone Decision Snapshot from an already-produced
    Decision dict (as returned by Engine.evaluate_requirement). Never
    re-evaluates anything -- purely reshapes/copies data that already
    exists on the Decision."""
    explanation = decision.get("explanation") or {}
    input_keys = explanation.get("input_facts_used", [])
    input_fact_snapshot = {k: project_facts.get(k) for k in sorted(input_keys)}

    return {
        "decision_id": decision.get("decision_id"),
        "project_id": decision.get("project_id"),
        "requirement_id": decision.get("requirement_id"),
        "evaluated_at": decision.get("evaluated_at"),
        "engine_version": decision.get("engine_version"),
        "rule_version_ids": decision.get("rule_version_ids", []),
        "input_fact_snapshot": input_fact_snapshot,
        "evaluation_mode": decision.get("evaluation_mode"),
        "result": decision.get("final_state"),
        "explanation": copy.deepcopy(explanation),
    }


class SnapshotConflictError(Exception):
    """Raised when a caller attempts to store two DIFFERENT snapshots under
    the same decision_id -- Phase 9 Section 11/Section 12: a Decision
    Snapshot must never be silently overwritten."""


class DecisionStore:
    """An append-only, in-memory store of Decision Snapshots keyed by
    decision_id. Demonstrates historical-decision stability: once stored, a
    snapshot's content can never change underneath a caller, regardless of
    later dataset/project-fact/engine changes."""

    def __init__(self):
        self._snapshots: dict = {}

    def put(self, snapshot: dict) -> dict:
        decision_id = snapshot.get("decision_id")
        if not decision_id:
            raise ValueError("snapshot has no decision_id; cannot store it")
        frozen = copy.deepcopy(snapshot)
        existing = self._snapshots.get(decision_id)
        if existing is not None and existing != frozen:
            raise SnapshotConflictError(
                f"decision_id {decision_id!r} is already stored with different "
                "content. A Decision Snapshot is immutable once recorded -- "
                "if the underlying facts or dataset changed, that must "
                "produce a new decision_id, not overwrite this one."
            )
        self._snapshots[decision_id] = frozen
        return copy.deepcopy(frozen)

    def get(self, decision_id: str):
        found = self._snapshots.get(decision_id)
        return copy.deepcopy(found) if found is not None else None

    def __len__(self) -> int:
        return len(self._snapshots)

    def __contains__(self, decision_id: str) -> bool:
        return decision_id in self._snapshots

    def all_ids(self) -> list:
        return list(self._snapshots.keys())

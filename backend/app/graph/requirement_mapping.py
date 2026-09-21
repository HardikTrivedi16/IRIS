"""
Stable canonical mapping between IRIS's human-readable identifiers
(Requirement codes like ``REQ-0001`` / ``MPCB_CTE_WATER``, and Rule Version
ids like ``RULE-0001-V1``) and the UUIDs the NetworkX Dependency & Workflow
Graph Engine requires on ``ApplicableRequirement`` / ``DependencyEdge``.

Why this exists
----------------
``dependency_engine.models`` (see IRIS-networkx) types every node/edge
endpoint as a ``uuid.UUID``. IRIS's own regulatory dataset (Phase 9,
frozen) identifies Requirements by string codes (``requirement_id``,
e.g. ``REQ-0001``) — see ``backend/regulatory-data/requirements/*.yaml``.

The brief explicitly forbids two things here:
  * replacing IRIS's human-readable identifiers with UUIDs to satisfy
    NetworkX, and
  * generating a fresh, unstable UUID per request (which would make
    ``requirement_id`` in dependency-graph responses meaningless across
    calls, and would break edge-identity comparisons in ``GraphDiff``,
    which key edges on UUID pairs).

So the mapping must be a *pure function* of the requirement code: the same
code always produces the same UUID, forever, for this deployment, with no
network/database round-trip and no persisted counter. ``uuid.uuid5`` with a
fixed, private namespace UUID gives exactly that — it's a deterministic
hash, not a random allocation.

This module does not talk to Supabase and does not need to: the mapping is
recomputable at any time from the code alone, so there is nothing to
persist. If a future phase wants a DB-backed mapping table instead (e.g.
to support renaming a requirement code without changing its UUID), it can
be added later without changing any *caller* of ``code_to_uuid`` /
``uuid_to_code`` — see ``docs`` note in the integration summary.
"""
from __future__ import annotations

import uuid

# Fixed, private namespace for IRIS requirement-code -> UUID derivation.
# Generated once (uuid4) and frozen — changing this constant would silently
# reassign every requirement's UUID, breaking any previously-returned
# dependency-graph response and any stored GraphDiff comparison. Do not
# regenerate this value.
IRIS_REQUIREMENT_NAMESPACE = uuid.UUID("6f2f6c9a-6e1d-4c2b-9b1a-2e6f9d4b7a10")


def code_to_uuid(requirement_code: str) -> uuid.UUID:
    """Deterministically derive a stable UUID for an IRIS requirement code
    (or any other stable string identifier, e.g. a Rule Version id used as
    ``source_rule_version_id`` provenance). Same input -> same output,
    always, with no I/O."""
    if not requirement_code or not isinstance(requirement_code, str):
        raise ValueError(f"requirement_code must be a non-empty string, got {requirement_code!r}")
    return uuid.uuid5(IRIS_REQUIREMENT_NAMESPACE, requirement_code)


class RequirementIdMap:
    """Bidirectional code<->UUID lookup scoped to a single adapter call
    (one project's applicable requirements). Built alongside the
    ApplicableRequirement list so responses can always be translated back
    to IRIS's own ``requirement_id``/``code`` strings before leaving the
    adapter boundary — the API never returns a bare UUID without also
    resolving it back to the IRIS code.
    """

    def __init__(self) -> None:
        self._code_to_uuid: dict[str, uuid.UUID] = {}
        self._uuid_to_code: dict[uuid.UUID, str] = {}

    def register(self, requirement_code: str) -> uuid.UUID:
        u = code_to_uuid(requirement_code)
        existing = self._uuid_to_code.get(u)
        if existing is not None and existing != requirement_code:
            # uuid5 collisions on distinct inputs are effectively
            # impossible (128-bit hash), but fail loudly rather than
            # silently merging two different requirements onto one node.
            raise ValueError(
                f"UUID collision mapping requirement codes {existing!r} and "
                f"{requirement_code!r} to the same UUID {u} — refusing to "
                "silently merge them."
            )
        self._code_to_uuid[requirement_code] = u
        self._uuid_to_code[u] = requirement_code
        return u

    def uuid_for(self, requirement_code: str) -> uuid.UUID | None:
        return self._code_to_uuid.get(requirement_code)

    def code_for(self, u: uuid.UUID) -> str | None:
        return self._uuid_to_code.get(u)

"""
Scheme framework (P2-K) — catalogue loader, validator and deterministic matcher.

This is SOFTWARE ONLY. The repository ships no real scheme content: the
catalogue directory (``scheme-data/``) is empty until the scheme-research
teammate delivers verified records in the format documented in
docs/SCHEME_CATALOGUE_INPUT_REQUIREMENTS.md. Tests use explicitly synthetic
``SCH-9###`` fixtures.

    Project Facts → structured scheme conditions → deterministic matcher
      → POTENTIALLY_ELIGIBLE | NEEDS_INFORMATION | NOT_ELIGIBLE → why → source

* No LLM is involved. Conditions are evaluated with the Rule Engine's own
  generic evaluator (``iris_engine.conditions.evaluate_condition``, called
  read-only), so schemes get exactly the same three-valued semantics:
  missing data is UNKNOWN → NEEDS_INFORMATION, never NOT_ELIGIBLE.
* The strongest outcome is POTENTIALLY_ELIGIBLE, never "eligible": the
  administering authority decides.
* Lifecycle gate (same principle as Rule Versions): only ``status: ACTIVE``
  AND ``confidence: VERIFIED`` schemes produce a result in normal mode.
  Anything else is evaluated only in NON_PRODUCTION (diagnostic) mode and is
  labelled so.

Two independent claims, never collapsed into one
--------------------------------------------------
1. **Eligibility** (``outcome``) — does this project's Project Facts satisfy
   the scheme's published eligibility conditions? Computed by the
   deterministic matcher below.
2. **Application status** (``application_status`` / ``application_window``)
   — is the scheme currently accepting applications at all? A separate,
   catalogue-authored fact, copied through verbatim. A project can be
   ``POTENTIALLY_ELIGIBLE`` for a scheme whose window is
   ``VERIFIED_CLOSED``, and equally a scheme can be ``VERIFIED_OPEN`` for a
   project that is ``NOT_ELIGIBLE``. Neither ever computes or overrides the
   other; there is no wall-clock inference (no ``if today > closes``) —
   the catalogue simply records what was verified true *as of*
   ``application_window.as_of_date``.
"""
from __future__ import annotations

import datetime as _dt
import glob
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

from iris_engine.conditions import SUPPORTED_COMPOSITE_OPERATORS, SUPPORTED_LEAF_OPERATORS, evaluate_condition

POTENTIALLY_ELIGIBLE = "POTENTIALLY_ELIGIBLE"
NEEDS_INFORMATION = "NEEDS_INFORMATION"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
CANNOT_EVALUATE = "CANNOT_EVALUATE"

_LIFECYCLE = {"DRAFT", "ACTIVE", "SUPERSEDED", "RETIRED"}
_CONFIDENCE = {"UNVERIFIED", "VERIFIED"}
_PREDICATES = {"BOOLEAN_EQUALS", "SET_MEMBERSHIP", "THRESHOLD_COMPARISON", "COMPOSITE"}
_REQUIRED_SOURCE_FIELDS = ("url", "document_title", "published_date", "retrieved_date")

# --- Application status / window (independent of eligibility — see module
# docstring "Two independent claims" and docs/SCHEME_CATALOGUE_INPUT_
# REQUIREMENTS.md). Every value here describes whether/how applications are
# CURRENTLY being accepted under this scheme; NONE of them may ever feed
# back into `outcome` (POTENTIALLY_ELIGIBLE / NEEDS_INFORMATION /
# NOT_ELIGIBLE / CANNOT_EVALUATE), which is computed purely from the
# eligibility condition tree in `match_scheme` below.
_APPLICATION_STATUSES = {
    "VERIFIED_OPEN",
    "VERIFIED_CLOSED",
    "VERIFIED_CONTINUING_BUT_NOT_OPEN_FOR_NEW_APPLICATIONS",
    "VERIFIED_PERIODIC_CALL_FOR_PROPOSALS",
    "SELECTION_COMPLETED",
    "NO_CURRENT_WINDOW",
    "UNRESOLVED_CURRENT_STATUS",
    "DISCONTINUED",
    "SUPERSEDED",
}
_APPLICATION_WINDOW_MODES = {
    "CONTINUOUS",
    "PERIODIC_EOI",
    "FIXED_WINDOW",
    "PROPOSAL_BASED",
    "SELECTION_COMPLETED",
    "CLOSED",
    "UNKNOWN",
}


@dataclass
class SchemeCatalogue:
    root: str
    schemes: dict = field(default_factory=dict)
    conditions: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    @property
    def usable(self) -> list[dict]:
        """Schemes allowed to produce a normal (non-diagnostic) result."""
        return [s for s in self.schemes.values() if is_active_verified(s)]


def is_active_verified(scheme: dict) -> bool:
    return scheme.get("status") == "ACTIVE" and scheme.get("confidence") == "VERIFIED"


def _load_dir(path: str, id_key: str) -> dict:
    out = {}
    for fp in sorted(glob.glob(os.path.join(path, "*.yaml"))):
        with open(fp, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        if isinstance(doc, dict) and doc.get(id_key):
            out[doc[id_key]] = doc
    return out


def _iso(value: Any) -> bool:
    if isinstance(value, _dt.date):
        return True
    try:
        _dt.date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def validate_catalogue(cat: SchemeCatalogue) -> list[str]:
    """Structural validation mirroring iris_engine.validate for the scheme
    format. Returns human-readable problems; empty list = valid."""
    errs: list[str] = []
    for cid, c in cat.conditions.items():
        pt, op = c.get("predicate_type"), c.get("operator")
        if pt not in _PREDICATES:
            errs.append(f"{cid}: unsupported predicate_type {pt!r}")
        elif pt == "COMPOSITE":
            if op not in SUPPORTED_COMPOSITE_OPERATORS:
                errs.append(f"{cid}: unsupported composite operator {op!r}")
            for child in c.get("child_scheme_condition_ids") or []:
                if child not in cat.conditions:
                    errs.append(f"{cid}: child {child} does not exist")
            if not c.get("child_scheme_condition_ids"):
                errs.append(f"{cid}: COMPOSITE without children")
        else:
            if op not in SUPPORTED_LEAF_OPERATORS:
                errs.append(f"{cid}: unsupported operator {op!r}")
            if not str(c.get("target_variable_key") or "").startswith("project."):
                errs.append(f"{cid}: target_variable_key must start with 'project.'")
        if c.get("unresolved_behavior") != "UNKNOWN":
            errs.append(f"{cid}: unresolved_behavior must be UNKNOWN")
    for sid, s in cat.schemes.items():
        root = s.get("eligibility_condition_root_id")
        if root not in cat.conditions:
            errs.append(f"{sid}: eligibility_condition_root_id {root!r} does not exist")
        if s.get("status") not in _LIFECYCLE:
            errs.append(f"{sid}: status must be one of {sorted(_LIFECYCLE)}")
        if s.get("confidence") not in _CONFIDENCE:
            errs.append(f"{sid}: confidence must be one of {sorted(_CONFIDENCE)}")
        src = s.get("official_source") or {}
        missing = [k for k in _REQUIRED_SOURCE_FIELDS if not src.get(k)]
        if missing:
            errs.append(f"{sid}: official_source missing {missing}")
        for k in ("effective_start_date",):
            if s.get(k) and not _iso(s[k]):
                errs.append(f"{sid}: {k} must be YYYY-MM-DD")
        if s.get("effective_end_date") and not _iso(s["effective_end_date"]):
            errs.append(f"{sid}: effective_end_date must be YYYY-MM-DD")
        if is_active_verified(s) and not (s.get("last_verified") or {}).get("date"):
            errs.append(f"{sid}: ACTIVE + VERIFIED requires last_verified.date")

        # --- application status / window (independent of eligibility) -------
        app_status = s.get("application_status")
        app_window = s.get("application_window")
        if app_status is not None and app_status not in _APPLICATION_STATUSES:
            errs.append(f"{sid}: application_status must be one of {sorted(_APPLICATION_STATUSES)}")
        if app_window is not None:
            mode = app_window.get("mode") if isinstance(app_window, dict) else None
            if mode not in _APPLICATION_WINDOW_MODES:
                errs.append(f"{sid}: application_window.mode must be one of {sorted(_APPLICATION_WINDOW_MODES)}")
            for k in ("opens", "closes", "as_of_date"):
                v = app_window.get(k) if isinstance(app_window, dict) else None
                if v and not _iso(v):
                    errs.append(f"{sid}: application_window.{k} must be YYYY-MM-DD")
            # VERIFIED_OPEN under a FIXED_WINDOW means one known window with a
            # known end — if the closing date genuinely isn't published yet,
            # the correct mode is UNKNOWN (or another mode), not FIXED_WINDOW.
            if app_status == "VERIFIED_OPEN" and mode == "FIXED_WINDOW" and not app_window.get("closes"):
                errs.append(f"{sid}: application_window.closes is required for VERIFIED_OPEN + FIXED_WINDOW")
        # Every application_status value asserts a verified position AS OF a
        # specific date (even UNRESOLVED_CURRENT_STATUS asserts "as of this
        # date, status could not be resolved") — never inferred from
        # wall-clock time, so the catalogue must state it explicitly.
        if app_status is not None:
            as_of = (app_window or {}).get("as_of_date") if isinstance(app_window, dict) else None
            if not as_of:
                errs.append(f"{sid}: application_status requires application_window.as_of_date")
            elif not _iso(as_of):
                errs.append(f"{sid}: application_window.as_of_date must be YYYY-MM-DD")

        # --- supersession (optional pointers, not historical-version machinery) --
        for key in ("supersedes", "superseded_by"):
            ref = s.get(key)
            if ref and ref not in cat.schemes:
                errs.append(f"{sid}: {key} -> unknown scheme {ref!r}")
    return errs


def load_catalogue(root: str) -> SchemeCatalogue:
    cat = SchemeCatalogue(root=root)
    if not os.path.isdir(root):
        return cat
    cat.schemes = _load_dir(os.path.join(root, "schemes"), "scheme_id")
    cat.conditions = _load_dir(os.path.join(root, "scheme-conditions"), "scheme_condition_id")
    cat.errors = validate_catalogue(cat)
    return cat


def _engine_shaped(conditions: dict) -> dict:
    """Adapt SCHC records to the evaluator's key names. No semantics change."""
    return {
        cid: {
            "predicate_type": c.get("predicate_type"),
            "target_variable_key": c.get("target_variable_key"),
            "operator": c.get("operator"),
            "comparison_value": c.get("comparison_value"),
            "child_condition_ids": list(c.get("child_scheme_condition_ids") or []),
        }
        for cid, c in conditions.items()
    }


def _walk(cr) -> list:
    out = [cr]
    for ch in cr.children:
        out.extend(_walk(ch))
    return out


def _in_force(scheme: dict, as_of: _dt.date) -> Optional[str]:
    start, end = scheme.get("effective_start_date"), scheme.get("effective_end_date")
    if start and _iso(start) and as_of < _dt.date.fromisoformat(str(start)):
        return f"Not yet in force (starts {start})."
    if end and _iso(end) and as_of > _dt.date.fromisoformat(str(end)):
        return f"No longer in force (ended {end})."
    return None


def match_scheme(scheme: dict, conditions: dict, facts: dict[str, Any], as_of: _dt.date) -> dict:
    engine_conditions = _engine_shaped(conditions)
    root = scheme.get("eligibility_condition_root_id")
    cr = evaluate_condition(root, engine_conditions, facts)
    leaves = [n for n in _walk(cr) if not n.children and conditions.get(n.condition_id, {}).get("predicate_type") != "COMPOSITE"]
    errors = [n.error for n in _walk(cr) if n.error]

    if errors:
        outcome = CANNOT_EVALUATE
    elif cr.result.value == "TRUE":
        outcome = POTENTIALLY_ELIGIBLE
    elif cr.result.value == "FALSE":
        outcome = NOT_ELIGIBLE
    else:
        outcome = NEEDS_INFORMATION

    why = []
    for n in leaves:
        c = conditions.get(n.condition_id, {})
        why.append({
            "scheme_condition_id": n.condition_id,
            "fact_key": c.get("target_variable_key"),
            "operator": c.get("operator"),
            "expected_value": c.get("comparison_value"),
            "unit": c.get("unit"),
            "project_value": facts.get(c.get("target_variable_key")),
            "result": n.result.value,
            "source_reference": c.get("source_reference"),
            "description": c.get("description"),
        })

    # Catalogue-authored explanation text that applies to the whole tree (e.g. "thresholds are not
    # encoded"), passed through verbatim so a client can surface a record's stated limitations without
    # inventing any text. Read-only; never influences `outcome`.
    composite_notes = [
        {"scheme_condition_id": n.condition_id, "description": conditions.get(n.condition_id, {}).get("description")}
        for n in _walk(cr)
        if conditions.get(n.condition_id, {}).get("predicate_type") == "COMPOSITE"
        and conditions.get(n.condition_id, {}).get("description")
    ]

    return {
        "scheme_id": scheme.get("scheme_id"),
        "name": scheme.get("name"),
        "administering_authority_name": scheme.get("administering_authority_name"),
        "outcome": outcome,
        "missing_facts": sorted(set(cr.missing_fact_keys)),
        "errors": errors,
        "why": why,
        "not_in_force_reason": _in_force(scheme, as_of),
        "official_source": scheme.get("official_source"),
        "benefits_summary": scheme.get("benefits_summary"),
        "notes": scheme.get("notes"),
        "composite_notes": composite_notes,
        "status": scheme.get("status"),
        "confidence": scheme.get("confidence"),
        "last_verified": scheme.get("last_verified"),
        "is_authoritative_catalogue_entry": is_active_verified(scheme),
        # Independent application-status dimension (see module docstring and
        # docs/SCHEME_CATALOGUE_INPUT_REQUIREMENTS.md §3.2/§3.3) — copied
        # verbatim from the catalogue record, never computed from `outcome`,
        # `as_of`, or any wall-clock comparison. `outcome` above is already
        # fully determined before this dict is built; nothing below this
        # line may ever influence it.
        "application_status": scheme.get("application_status"),
        "application_window": scheme.get("application_window"),
        "supersedes": scheme.get("supersedes"),
        "superseded_by": scheme.get("superseded_by"),
    }


def match_catalogue(cat: SchemeCatalogue, facts: dict[str, Any], *, mode: str = "PRODUCTION",
                    as_of: Optional[_dt.date] = None) -> dict:
    as_of = as_of or _dt.datetime.now(_dt.timezone.utc).date()
    if cat.errors:
        # Fail closed: an invalid catalogue produces no eligibility results.
        return {
            "catalogue_state": "INVALID",
            "mode": mode,
            "results": [],
            "catalogue_errors": cat.errors,
            "notes": ["The scheme catalogue failed validation; no eligibility results are produced."],
        }
    pool = list(cat.schemes.values()) if mode == "NON_PRODUCTION" else cat.usable
    results = [match_scheme(s, cat.conditions, facts, as_of) for s in sorted(pool, key=lambda s: s["scheme_id"])]
    state = "AWAITING_VERIFIED_DATA" if not cat.usable else "READY"
    notes = ["POTENTIALLY_ELIGIBLE is never a final eligibility decision — the administering authority decides."]
    if state == "AWAITING_VERIFIED_DATA":
        notes.insert(0, "SCHEME CATALOGUE AWAITING VERIFIED DATA — no ACTIVE, VERIFIED scheme records are loaded.")
    if mode == "NON_PRODUCTION":
        notes.append("Diagnostic mode includes DRAFT / UNVERIFIED records. These results are not authoritative.")
    return {
        "catalogue_state": state,
        "mode": mode,
        "as_of_date": as_of.isoformat(),
        "counts": {"total": len(cat.schemes), "active_verified": len(cat.usable)},
        "results": results,
        "catalogue_errors": [],
        "notes": notes,
    }

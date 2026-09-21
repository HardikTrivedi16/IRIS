"""
Upcoming compliance & renewals (P1-G).

Remaining time is derived ONLY from an expiry date that is actually on
record — never from an assumed or statutory validity period, which IRIS does
not know and must not invent. Source hierarchy (highest first):

  1. CONFIRMED_DOCUMENT  — a validity end date a human confirmed from an
                           uploaded document (Project Fact
                           ``document.valid_until``, written by the
                           Documents page after review).
  2. STORED_METADATA     — ``document_metadata.expiry_date`` rows (migration
                           0005) linked to this project via its company.
     SYNTHETIC_DEMO      — the same rows when their ``manifest_source`` marks
                           them synthetic ('synthetic_generation'); always
                           labelled SYNTHETIC DEMO DATA.

A record with no expiry date is reported as NO_EXPIRY_ON_RECORD, not given a
guessed one.

Status
------
EXPIRED          expiry date is before the as-of date
ACTION_REQUIRED  expires within the action window
UPCOMING         expires after the action window
COMPLETED        the record itself says it was renewed/superseded
                 (manifest_status RENEWED or SUPERSEDED) — never inferred
NO_EXPIRY_ON_RECORD  no expiry date is recorded

The action window is a PROTOTYPE DEMO POLICY (default 90 days), not a
statutory renewal lead time. IRIS does not claim to renew anything
automatically.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

DEFAULT_ACTION_WINDOW_DAYS = 90

EXPIRED = "EXPIRED"
ACTION_REQUIRED = "ACTION_REQUIRED"
UPCOMING = "UPCOMING"
COMPLETED = "COMPLETED"
NO_EXPIRY = "NO_EXPIRY_ON_RECORD"

SOURCE_CONFIRMED = "CONFIRMED_DOCUMENT"
SOURCE_STORED = "STORED_METADATA"
SOURCE_SYNTHETIC = "SYNTHETIC_DEMO"

_SOURCE_LABEL = {
    SOURCE_CONFIRMED: "Confirmed from an uploaded document",
    SOURCE_STORED: "Stored document metadata",
    SOURCE_SYNTHETIC: "SYNTHETIC DEMO DATA",
}
_SOURCE_RANK = {SOURCE_CONFIRMED: 0, SOURCE_STORED: 1, SOURCE_SYNTHETIC: 2}
_SYNTHETIC_MARKERS = ("synthetic",)
_DONE_MANIFEST_STATUSES = {"RENEWED", "SUPERSEDED"}

_STATUS_ORDER = {EXPIRED: 0, ACTION_REQUIRED: 1, UPCOMING: 2, NO_EXPIRY: 3, COMPLETED: 4}


def _parse_date(value: Any) -> Optional[_dt.date]:
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return _dt.date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _status(expiry: Optional[_dt.date], as_of: _dt.date, window: int, completed: bool) -> tuple[str, Optional[int]]:
    if completed:
        days = (expiry - as_of).days if expiry else None
        return COMPLETED, days
    if expiry is None:
        return NO_EXPIRY, None
    days = (expiry - as_of).days
    if days < 0:
        return EXPIRED, days
    if days <= window:
        return ACTION_REQUIRED, days
    return UPCOMING, days


def records_from_metadata(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        source_text = str(r.get("manifest_source") or "").lower()
        kind = SOURCE_SYNTHETIC if any(m in source_text for m in _SYNTHETIC_MARKERS) else SOURCE_STORED
        subtype = r.get("pharma_subtype") or r.get("food_subtype") or r.get("document_type")
        out.append({
            "record_id": r.get("document_id"),
            # Stored label verbatim (underscores → spaces); no re-casing, which
            # would mangle acronyms such as WHO / GMP / NOC.
            "title": (subtype or "DOCUMENT").replace("_", " "),
            "document_number": r.get("document_number"),
            "issuing_authority": r.get("issuing_authority"),
            "issue_date": r.get("issue_date"),
            "expiry_date": r.get("expiry_date"),
            "completed": str(r.get("manifest_status") or "").upper() in _DONE_MANIFEST_STATUSES,
            "source_kind": kind,
        })
    return out


def records_from_confirmed_facts(facts: dict[str, Any]) -> list[dict]:
    value = facts.get("document.valid_until")
    if not value:
        return []
    return [{
        "record_id": "FACT-document.valid_until",
        "title": "Validity date confirmed from an uploaded document",
        "document_number": facts.get("document.registration_number"),
        "issuing_authority": None,
        "issue_date": facts.get("document.issue_date"),
        "expiry_date": value,
        "completed": False,
        "source_kind": SOURCE_CONFIRMED,
    }]


def build_renewal_register(
    records: list[dict],
    *,
    as_of: _dt.date,
    action_window_days: int = DEFAULT_ACTION_WINDOW_DAYS,
) -> dict:
    """Pure function: same records + same as-of date + same window → same
    register."""
    items = []
    unparseable = []
    for rec in records:
        raw = rec.get("expiry_date")
        expiry = _parse_date(raw)
        if raw and expiry is None:
            unparseable.append(rec.get("record_id"))
        status, days = _status(expiry, as_of, action_window_days, bool(rec.get("completed")))
        items.append({
            **{k: rec.get(k) for k in ("record_id", "title", "document_number", "issuing_authority", "issue_date")},
            "expiry_date": expiry.isoformat() if expiry else None,
            "days_remaining": days,
            "status": status,
            "source_kind": rec.get("source_kind"),
            "source_label": _SOURCE_LABEL.get(rec.get("source_kind"), "Unknown source"),
            "is_synthetic": rec.get("source_kind") == SOURCE_SYNTHETIC,
        })

    items.sort(key=lambda i: (
        _STATUS_ORDER[i["status"]],
        i["days_remaining"] if i["days_remaining"] is not None else 10**9,
        _SOURCE_RANK.get(i["source_kind"], 9),
        str(i["record_id"]),
    ))
    summary = {s: 0 for s in _STATUS_ORDER}
    for i in items:
        summary[i["status"]] += 1

    notes = [
        f"Action window: {action_window_days} days — a PROTOTYPE DEMO POLICY, not a "
        "statutory renewal lead time.",
        "Remaining time is computed only from an expiry date on record. IRIS does "
        "not assume validity periods and does not renew anything automatically.",
    ]
    if any(i["is_synthetic"] for i in items):
        notes.append("Rows marked SYNTHETIC DEMO DATA come from the synthetic seed dataset, not real licences.")
    if unparseable:
        notes.append("Some expiry values could not be read as dates and are shown as no expiry on record: "
                     + ", ".join(map(str, unparseable)) + ".")

    return {
        "as_of_date": as_of.isoformat(),
        "action_window_days": action_window_days,
        "action_window_is_policy": True,
        "summary": summary,
        "items": items,
        "notes": notes,
    }

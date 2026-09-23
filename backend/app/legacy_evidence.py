"""
Legacy-evidence presentation adapter (synthetic demo).

Some demo projects were relocated in the synthetic narrative (SwaadHarvest:
Haridwar -> Pune district MIDC; Aarav: Selaqui -> Waluj MIDC), so their
existing documents describe a PRIOR facility, not the current Maharashtra one.
The database has no ``legacy`` column and none is added here.

Legacy status is asserted only by ``backend/demo-data/legacy_evidence.json``,
which names the affected documents explicitly (exact ``storage_path`` or
``external_document_id``). It is NEVER inferred from location mismatch,
filename patterns or document age. Nothing is written anywhere: rows are
annotated on the way out and the PDFs / extraction data are untouched.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Optional

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo-data", "legacy_evidence.json")

LABEL = "Legacy evidence — prior facility"


@lru_cache(maxsize=1)
def _config() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f).get("projects") or {}
    except (OSError, ValueError):
        return {}  # no metadata -> nothing is labelled legacy


def _project(project_id: str) -> Optional[dict]:
    return _config().get(project_id)


def legacy_info(project_id: str) -> Optional[dict]:
    return _project(project_id)


def is_legacy_document(project_id: str, doc: dict) -> bool:
    cfg = _project(project_id)
    if not cfg:
        return False
    if cfg.get("match") == "storage_path":
        return doc.get("storage_path") in set(cfg.get("storage_paths") or [])
    if cfg.get("match") == "external_document_id":
        return doc.get("external_document_id") in set(cfg.get("external_document_ids") or [])
    return False


def annotate_documents(project_id: str, docs: list[dict]) -> list[dict]:
    cfg = _project(project_id)
    out = []
    for d in docs:
        row = dict(d)
        if cfg and is_legacy_document(project_id, d):
            row["legacy_evidence"] = {
                "label": LABEL,
                "prior_facility": cfg.get("prior_facility"),
                "current_facility": cfg.get("current_facility"),
                "basis": cfg.get("basis"),
            }
        out.append(row)
    return out


def is_legacy_metadata_row(project_id: str, row: dict[str, Any]) -> bool:
    """document_metadata rows are keyed by document_id, which equals the
    document's external_document_id in the Aarav seed."""
    cfg = _project(project_id)
    if not cfg or cfg.get("match") != "external_document_id":
        return False
    return row.get("document_id") in set(cfg.get("external_document_ids") or [])

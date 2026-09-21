"""
Thin, read-only wrapper around the (unmodified) Phase 9 ``iris_engine``
package. This module contains no regulatory logic of its own — it only:

  * loads the RegulatoryDataset once per process,
  * exposes the small set of read operations the API needs
    (list requirements, describe engine/version state, evaluate),
  * shapes dataset records for JSON responses by stripping the loader's
    internal ``_source_file`` bookkeeping key (never regulatory content).

Every actual regulatory decision is produced by ``iris_engine.Engine``,
copied byte-for-byte from the delivered Phase 9 package into
``backend/iris_engine`` / ``backend/regulatory-data``. Nothing in this file
alters a condition, rule, classification, or dependency result.
"""
from __future__ import annotations

import os
from functools import lru_cache

from iris_engine import RegulatoryDataset, Engine, EvaluationMode
from iris_engine.versioning import ENGINE_VERSION_HISTORY, CURRENT_ENGINE_VERSION
from iris_engine.dataset_integrity import hash_tree  # noqa: F401  (re-exported for routers)

from .config import get_settings

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_data_root(root: str) -> str:
    return root if os.path.isabs(root) else os.path.join(BACKEND_DIR, root)


@lru_cache
def get_dataset() -> RegulatoryDataset:
    settings = get_settings()
    data_root = _resolve_data_root(settings.regulatory_data_root)
    return RegulatoryDataset.load(data_root)


@lru_cache
def get_engine() -> Engine:
    return Engine(get_dataset())


def _strip_internal(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_source_file"}


def list_requirements() -> list[dict]:
    ds = get_dataset()
    out = []
    for req_id, req in ds.requirements.items():
        rec = _strip_internal(req)
        rule_id = rec.get("evaluated_by_rule_id")
        latest_rv_id = ds.latest_rule_version_id(rule_id) if rule_id else None
        rv = ds.rule_versions.get(latest_rv_id) if latest_rv_id else None
        rec["latest_rule_version_id"] = latest_rv_id
        rec["latest_rule_version_status"] = (rv or {}).get("status")
        out.append(rec)
    out.sort(key=lambda r: r.get("requirement_id", ""))
    return out


def get_requirement(requirement_id: str) -> dict | None:
    ds = get_dataset()
    req = ds.requirements.get(requirement_id)
    if req is None:
        return None
    rec = _strip_internal(req)
    rule_id = rec.get("evaluated_by_rule_id")
    latest_rv_id = ds.latest_rule_version_id(rule_id) if rule_id else None
    rv = ds.rule_versions.get(latest_rv_id) if latest_rv_id else None
    rec["latest_rule_version_id"] = latest_rv_id
    rec["latest_rule_version_status"] = (rv or {}).get("status")
    return rec


def engine_info() -> dict:
    ds = get_dataset()
    statuses: dict[str, int] = {}
    for rv in ds.rule_versions.values():
        s = rv.get("status", "UNKNOWN")
        statuses[s] = statuses.get(s, 0) + 1
    return {
        "current_engine_version": CURRENT_ENGINE_VERSION,
        "engine_version_history": ENGINE_VERSION_HISTORY,
        "evaluation_modes": [m.value for m in EvaluationMode],
        "dataset_root": ds.root,
        "counts": {
            "conditions": len(ds.conditions),
            "rules": len(ds.rules),
            "rule_versions": len(ds.rule_versions),
            "requirements": len(ds.requirements),
            "rule_versions_by_status": statuses,
        },
        "known_conflicts": ds.rule_conflict_register.get("conflicts", []),
        "notes": [
            "Every Rule Version currently in the dataset has status DRAFT; "
            "there are zero ACTIVE Rule Versions. This is the real, current "
            "state of the regulatory dataset — it is not altered by this API.",
            "Evaluating in PRODUCTION mode (the default) will therefore "
            "return BLOCKED_DRAFT_NOT_PRODUCTION for every requirement. "
            "Pass evaluation_mode=NON_PRODUCTION to get a labelled, "
            "non-authoritative diagnostic evaluation instead.",
        ],
    }


def evaluate_requirement(
    project_id: str,
    requirement_id: str,
    project_facts: dict,
    evaluation_mode: str = "PRODUCTION",
) -> dict:
    engine = get_engine()
    mode = EvaluationMode(evaluation_mode)
    return engine.evaluate_requirement(
        project_id=project_id,
        requirement_id=requirement_id,
        project_facts=project_facts,
        evaluation_mode=mode,
    )


def evaluate_all(
    project_id: str,
    project_facts: dict,
    evaluation_mode: str = "PRODUCTION",
) -> list[dict]:
    engine = get_engine()
    mode = EvaluationMode(evaluation_mode)
    return engine.evaluate_all_requirements(
        project_id=project_id,
        project_facts=project_facts,
        evaluation_mode=mode,
    )

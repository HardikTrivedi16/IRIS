"""
Provenance resolver for Decision Proof.

Read-only adapter over the loaded regulatory dataset. It follows the
relationships that actually exist:

    Rule Version -> Regulatory Fact -> Evidence -> Source
    Rule Version -> Instrument, Authority
    Rule Version <- Verification (target_type RULE_VERSION)

and exposes ONLY records genuinely present. It never fabricates a record,
never completes a partial chain, and never turns an ID into a citation.

Three separate questions are answered separately and must never be conflated:
    1. PROVENANCE RESOLVED   - do the referenced records exist in the dataset?
    2. SOURCE ARCHIVED       - is the primary artifact stored locally (source_status ARCHIVED)?
    3. HUMAN VERIFIED        - does an APPROVED Verification (VER) record target the Rule Version?

It does not evaluate anything and does not influence any engine result.
"""
from __future__ import annotations

from typing import Any


def _pick(rec: dict | None, keys: tuple[str, ...]) -> dict | None:
    if rec is None:
        return None
    return {k: rec.get(k) for k in keys if k in rec}


_AUTH = ("authority_id", "name", "level", "jurisdiction")
_INST = ("instrument_id", "short_title", "full_citation", "currency_status",
         "effective_start_date", "effective_end_date")
_RF = ("regulatory_fact_id", "statement", "verification_status")
_EVID = ("evidence_id", "source_id", "section_or_clause", "page", "excerpt", "verification_status")
_SRC = ("source_id", "title", "document_type", "official_url", "publication_date",
        "retrieved_date", "source_status", "archived_artifact_path", "checksum_sha256")


def resolve_provenance(dataset: Any, decision: dict) -> dict:
    """Build the resolved provenance block for one Decision."""
    rv_ids = list(decision.get("rule_version_ids") or [])
    if decision.get("rule_version_id") and decision["rule_version_id"] not in rv_ids:
        rv_ids.insert(0, decision["rule_version_id"])
    rv_ids = [r for r in rv_ids if r]

    gaps: list[str] = []
    authorities: dict[str, dict] = {}
    instruments: dict[str, dict] = {}
    facts: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    rule_versions: list[dict] = []
    fact_ids: list[str] = []
    evidence_ids: list[str] = []
    source_ids: list[str] = []

    def take(pool: dict, store: dict, rid: str | None, keys: tuple[str, ...], label: str, ctx: str) -> dict | None:
        if not rid:
            return None
        rec = pool.get(rid)
        if rec is None:
            gaps.append(f"{ctx}: {label} {rid} is referenced but no such record exists in the dataset.")
            return None
        store.setdefault(rid, _pick(rec, keys) or {})
        return rec

    for rv_id in rv_ids:
        rv = dataset.rule_versions.get(rv_id) or {}
        rule_versions.append({
            "rule_version_id": rv_id,
            "status": rv.get("status"),
            "confidence": rv.get("confidence"),
            "effective_end_date": rv.get("effective_end_date"),
        })
        rf_refs = list(rv.get("regulatory_fact_ids") or [])
        if not rf_refs:
            gaps.append(f"{rv_id}: no Regulatory Fact is recorded — the legal proposition behind this Rule Version is not yet grounded in a structured fact.")
        for rid in rf_refs:
            fact_ids.append(rid)
            rf = take(dataset.facts, facts, rid, _RF, "Regulatory Fact", rv_id)
            if rf is None:
                continue
            if rf.get("verification_status") != "VERIFIED":
                gaps.append(f"{rid}: Regulatory Fact is {rf.get('verification_status') or 'UNVERIFIED'}.")
        for eid in rv.get("evidence_ids") or []:
            evidence_ids.append(eid)
            ev = take(dataset.evidence, evidence, eid, _EVID, "Evidence", rv_id)
            if ev is not None and ev.get("verification_status") != "VERIFIED":
                gaps.append(f"{eid}: Evidence is {ev.get('verification_status') or 'UNVERIFIED'}.")
        for sid in rv.get("source_ids") or []:
            source_ids.append(sid)
            take(dataset.sources, sources, sid, _SRC, "Source", rv_id)
        take(dataset.authorities, authorities, rv.get("authority_id"), _AUTH, "Authority", rv_id)
        take(dataset.instruments, instruments, rv.get("instrument_id"), _INST, "Instrument", rv_id)
        if rv.get("instrument_id") is None:
            gaps.append(f"{rv_id}: no Instrument is recorded.")

    # Source archival — reported truthfully, per source.
    archived = sorted(s for s, r in sources.items() if r.get("source_status") == "ARCHIVED")
    not_archived = sorted(s for s, r in sources.items() if r.get("source_status") != "ARCHIVED")
    if not sources:
        archival_state = "NO_SOURCES"
        gaps.append("No Source record is linked, so no primary artifact is identified for this determination.")
    elif not_archived:
        archival_state = "NOT_ALL_ARCHIVED"
        gaps.append(
            "Primary artifact not archived locally for: "
            + ", ".join(f"{s} ({sources[s].get('source_status')})" for s in not_archived)
            + "."
        )
    else:
        archival_state = "ALL_ARCHIVED"

    # Human verification — only an APPROVED VER targeting an involved Rule Version counts.
    approved = sorted(
        vid
        for vid, ver in (dataset.verifications or {}).items()
        if ver.get("target_type") == "RULE_VERSION"
        and ver.get("target_id") in rv_ids
        and ver.get("result") == "APPROVED"
    )
    if not approved:
        gaps.append("No APPROVED human Verification record exists for this Rule Version.")

    gaps = list(dict.fromkeys(gaps))  # de-duplicate, keep order
    has_any = bool(facts or evidence or sources)
    complete = bool(facts) and bool(evidence) and bool(sources) and not any(
        "is referenced but no such record" in g or "no Regulatory Fact is recorded" in g for g in gaps
    )
    status = "RESOLVED" if complete else ("PARTIAL" if has_any else "UNRESOLVED")

    return {
        "status": status,
        "instrument_id": decision.get("provenance", {}).get("instrument_id") if decision.get("provenance") else None,
        "authority_id": decision.get("provenance", {}).get("authority_id") if decision.get("provenance") else None,
        "source_ids": sorted(set(source_ids)),
        "evidence_ids": sorted(set(evidence_ids)),
        "regulatory_fact_ids": sorted(set(fact_ids)),
        "resolved_records": {
            "authorities": list(authorities.values()),
            "instruments": list(instruments.values()),
            "regulatory_facts": list(facts.values()),
            "evidence": list(evidence.values()),
            "sources": list(sources.values()),
        }
        if (authorities or instruments or has_any)
        else None,
        "rule_versions": rule_versions,
        "source_archival": {"state": archival_state, "archived": archived, "not_archived": not_archived},
        "human_verification": {
            "state": "HUMAN_VERIFIED" if approved else "NOT_VERIFIED",
            "verification_ids": approved,
        },
        "gaps": gaps,
        "note": None,
    }

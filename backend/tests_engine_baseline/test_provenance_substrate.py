"""
Provenance Substrate — Tranche 1.

Exercises the new Authority/Instrument/Source/Evidence/Regulatory Fact
(RF)/Verification (VER) loader support and the ACTIVE promotion gate in
`iris_engine/validate.py`.

Every test here builds its OWN isolated, synthetic regulatory-data tree
under pytest's `tmp_path` (a fresh temp directory per test, auto-cleaned).
Nothing here reads or writes the real `backend/regulatory-data/` — that
directory's provenance record types stay genuinely empty in this tranche,
per the brief ("Do NOT create real production legal provenance records
yet"). Only `test_draft_with_unresolved_provenance_still_blocks_production`
touches the real dataset, and only to confirm existing engine behaviour is
unaffected (via the session-scoped `engine`/`dataset` fixtures from
conftest.py) — it makes no assertion about provenance content.
"""
from __future__ import annotations

import os

import yaml

from iris_engine.loader import RegulatoryDataset
from iris_engine.validate import validate_dataset

_DIRS = (
    "conditions", "rules", "rule-versions", "requirements",
    "authorities", "instruments", "sources", "evidence", "facts", "verifications",
    "index", "registers",
)


def _mk(root: str) -> None:
    for d in _DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)


def _w(root: str, sub: str, name: str, doc: dict) -> None:
    with open(os.path.join(root, sub, name), "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False)


def _rm(root: str, sub: str, name: str) -> None:
    path = os.path.join(root, sub, name)
    if os.path.exists(path):
        os.remove(path)


def _index(root: str, name: str, doc: dict) -> None:
    _w(root, "index", name, doc)


def _write_golden_chain(
    root: str,
    *,
    rv_status: str = "ACTIVE",
    rv_effective_start: str | None = "2026-01-01",
    rv_effective_end: str | None = None,
    instrument_currency: str = "IN_FORCE",
    instrument_effective_end: str | None = None,
    include_ver: bool = True,
    ver_result: str = "APPROVED",
    ver_reviewer: str = "Jane Reviewer",
) -> None:
    """A complete, self-consistent AUTH -> INST -> SRC -> EVID -> RF ->
    RuleVersion (-> Requirement) chain, isolated to `root`. Every record
    resolves; every index count matches. Callers mutate/delete individual
    files afterwards to exercise a specific failure mode."""
    _mk(root)

    _w(root, "authorities", "AUTH-T1.yaml", {
        "authority_id": "AUTH-T1", "name": "Test Authority",
        "level": "STATE_REGULATOR", "jurisdiction": "TESTLAND",
    })
    _w(root, "instruments", "INST-T1.yaml", {
        "instrument_id": "INST-T1", "short_title": "Test Act",
        "full_citation": "The Test Act, 2020", "issuing_authority_id": "AUTH-T1",
        "year": 2020, "currency_status": instrument_currency,
        "effective_start_date": "2020-01-01",
        "effective_end_date": instrument_effective_end,
        "last_currency_check": "2026-01-01",
    })
    _w(root, "sources", "SRC-T1.yaml", {
        "source_id": "SRC-T1", "title": "Test Gazette",
        "publisher_authority_id": "AUTH-T1", "document_type": "GAZETTE",
        "official_url": "https://example.test/src-t1",
        "retrieved_date": "2026-01-01", "source_status": "AVAILABLE",
    })
    _w(root, "evidence", "EVID-T1.yaml", {
        "evidence_id": "EVID-T1", "source_id": "SRC-T1",
        "section_or_clause": "Section 2(c)", "excerpt": "Test excerpt.",
        "verification_status": "VERIFIED",
    })
    _w(root, "facts", "RF-T1.yaml", {
        "regulatory_fact_id": "RF-T1", "statement": "Test proposition.",
        "evidence_ids": ["EVID-T1"], "authority_id": "AUTH-T1",
        "instrument_id": "INST-T1", "verification_status": "VERIFIED",
    })
    _w(root, "conditions", "COND-T1.yaml", {
        "condition_id": "COND-T1", "predicate_type": "BOOLEAN_EQUALS",
        "target_variable_key": "project.test_flag", "operator": "==",
        "comparison_value": True, "unresolved_behavior": "UNKNOWN",
    })
    _w(root, "rules", "RULE-T1.yaml", {
        "rule_id": "RULE-T1", "code": "TEST_RULE", "requirement_id": "REQ-T1",
        "title": "Test rule", "output_type": "APPLICABILITY", "rule_type": "APPLICABILITY_RULE",
    })
    _w(root, "rule-versions", "RULE-T1-V1.yaml", {
        "rule_version_id": "RULE-T1-V1", "rule_id": "RULE-T1", "version_number": 1,
        "condition_expression_root_id": "COND-T1",
        "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        "required_project_facts": ["project.test_flag"],
        "regulatory_fact_ids": ["RF-T1"], "evidence_ids": ["EVID-T1"], "source_ids": ["SRC-T1"],
        "authority_id": "AUTH-T1", "instrument_id": "INST-T1",
        "effective_start_date": rv_effective_start, "effective_end_date": rv_effective_end,
        "status": rv_status,
    })
    _w(root, "requirements", "REQ-T1.yaml", {
        "requirement_id": "REQ-T1", "code": "TEST_REQ", "title": "Test requirement",
        "authority_id": "AUTH-T1", "evaluated_by_rule_id": "RULE-T1",
        "grounding_regulatory_fact_ids": ["RF-T1"], "evidence_ids": ["EVID-T1"],
    })
    if include_ver:
        _w(root, "verifications", "VER-T1.yaml", {
            "verification_id": "VER-T1", "target_type": "RULE_VERSION",
            "target_id": "RULE-T1-V1", "reviewer": ver_reviewer,
            "reviewed_at": "2026-01-01", "result": ver_result,
            "source_checks": ["SRC-T1"], "evidence_checks": ["EVID-T1"],
        })

    _index(root, "authorities_index.yaml", {"authorities": [], "counts": {"total_authorities": 1}})
    _index(root, "instruments_index.yaml", {"instruments": [], "counts": {"total_instruments": 1}})
    _index(root, "sources_index.yaml", {"sources": [], "counts": {"total_sources": 1}})
    _index(root, "evidence_index.yaml", {"evidence": [], "counts": {"total_evidence": 1}})
    _index(root, "facts_index.yaml", {"facts": [], "counts": {"total_regulatory_facts": 1}})
    _index(root, "verifications_index.yaml", {
        "verifications": [], "counts": {"total_verifications": 1 if include_ver else 0},
    })


def _write_bare_active_chain(root: str, rv_overrides: dict | None = None) -> None:
    """A Rule Version claiming ACTIVE status whose provenance references
    (RF/Evidence/Source/Authority/Instrument) point at nothing — no
    provenance record of any kind exists in this tree."""
    _mk(root)
    _w(root, "conditions", "COND-T1.yaml", {
        "condition_id": "COND-T1", "predicate_type": "BOOLEAN_EQUALS",
        "target_variable_key": "project.test_flag", "operator": "==",
        "comparison_value": True, "unresolved_behavior": "UNKNOWN",
    })
    _w(root, "rules", "RULE-T1.yaml", {
        "rule_id": "RULE-T1", "code": "TEST_RULE", "requirement_id": "REQ-T1",
    })
    rv = {
        "rule_version_id": "RULE-T1-V1", "rule_id": "RULE-T1", "version_number": 1,
        "condition_expression_root_id": "COND-T1",
        "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        "regulatory_fact_ids": ["RF-T1"], "evidence_ids": ["EVID-T1"], "source_ids": ["SRC-T1"],
        "authority_id": "AUTH-T1", "instrument_id": "INST-T1",
        "effective_start_date": "2026-01-01", "status": "ACTIVE",
    }
    if rv_overrides:
        rv.update(rv_overrides)
    _w(root, "rule-versions", "RULE-T1-V1.yaml", rv)
    _w(root, "requirements", "REQ-T1.yaml", {
        "requirement_id": "REQ-T1", "code": "TEST_REQ", "evaluated_by_rule_id": "RULE-T1",
    })
    for name, key in (
        ("authorities_index.yaml", "total_authorities"),
        ("instruments_index.yaml", "total_instruments"),
        ("sources_index.yaml", "total_sources"),
        ("evidence_index.yaml", "total_evidence"),
        ("facts_index.yaml", "total_regulatory_facts"),
        ("verifications_index.yaml", "total_verifications"),
    ):
        _index(root, name, {"counts": {key: 0}})


# --- A. loader ---------------------------------------------------------------

def test_loader_reads_all_six_provenance_record_types(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    ds = RegulatoryDataset.load(root)
    assert set(ds.authorities) == {"AUTH-T1"}
    assert set(ds.instruments) == {"INST-T1"}
    assert set(ds.sources) == {"SRC-T1"}
    assert set(ds.evidence) == {"EVID-T1"}
    assert set(ds.facts) == {"RF-T1"}
    assert set(ds.verifications) == {"VER-T1"}
    # existing behavior untouched
    assert set(ds.conditions) == {"COND-T1"}
    assert set(ds.rule_versions) == {"RULE-T1-V1"}


# --- B. complete DRAFT chain validates structurally --------------------------

def test_complete_draft_chain_loads_and_validates(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root, rv_status="DRAFT", include_ver=False)
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert r.passed, r
    assert not r.active_promotion_violations


# --- C. broken Evidence -> nonexistent Source ---------------------------------

def test_evidence_to_nonexistent_source_fails_closed(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _w(root, "evidence", "EVID-T1.yaml", {
        "evidence_id": "EVID-T1", "source_id": "SRC-GHOST",
        "section_or_clause": "Section 2(c)", "excerpt": "Test excerpt.",
        "verification_status": "VERIFIED",
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("SRC-GHOST" in b for b in r.broken_references)


# --- D. broken RF -> nonexistent Evidence -------------------------------------

def test_rf_to_nonexistent_evidence_fails_closed(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _w(root, "facts", "RF-T1.yaml", {
        "regulatory_fact_id": "RF-T1", "statement": "Test proposition.",
        "evidence_ids": ["EVID-GHOST"], "authority_id": "AUTH-T1",
        "instrument_id": "INST-T1", "verification_status": "VERIFIED",
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("EVID-GHOST" in b for b in r.broken_references)


# --- E. broken RuleVersion -> nonexistent RF, where appropriate (ACTIVE) -----

def test_active_rule_version_to_nonexistent_rf_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root, rv_status="ACTIVE")
    _w(root, "rule-versions", "RULE-T1-V1.yaml", {
        "rule_version_id": "RULE-T1-V1", "rule_id": "RULE-T1", "version_number": 1,
        "condition_expression_root_id": "COND-T1",
        "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        "regulatory_fact_ids": ["RF-GHOST"], "evidence_ids": ["EVID-T1"], "source_ids": ["SRC-T1"],
        "authority_id": "AUTH-T1", "instrument_id": "INST-T1",
        "effective_start_date": "2026-01-01", "status": "ACTIVE",
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("RF-GHOST" in v for v in r.active_promotion_violations)


def test_draft_rule_version_to_nonexistent_rf_is_a_review_note_not_a_failure(tmp_path):
    """The DRAFT counterpart of test E: unresolved provenance on a
    non-ACTIVE Rule Version is informational, never a hard failure — the
    DRAFT-compatibility carve-out (§9 of the Tranche 1 brief)."""
    root = str(tmp_path)
    _write_golden_chain(root, rv_status="DRAFT", include_ver=False)
    _w(root, "rule-versions", "RULE-T1-V1.yaml", {
        "rule_version_id": "RULE-T1-V1", "rule_id": "RULE-T1", "version_number": 1,
        "condition_expression_root_id": "COND-T1",
        "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        "regulatory_fact_ids": ["RF-GHOST"], "evidence_ids": ["EVID-T1"], "source_ids": ["SRC-T1"],
        "authority_id": "AUTH-T1", "instrument_id": "INST-T1", "status": "DRAFT",
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert r.passed, r
    assert any("RF-GHOST" in n for n in r.review_notes)


# --- F. ACTIVE with missing provenance fails ----------------------------------

def test_active_rule_version_with_no_provenance_at_all_fails(tmp_path):
    root = str(tmp_path)
    _write_bare_active_chain(root)
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert r.active_promotion_violations
    joined = " ".join(r.active_promotion_violations)
    assert "RF-T1" in joined and "AUTH-T1" in joined and "INST-T1" in joined


# --- G. ACTIVE with complete provenance but no approved VER fails ------------

def test_active_rule_version_without_approved_verification_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root, rv_status="ACTIVE", include_ver=False)
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("APPROVED Verification" in v for v in r.active_promotion_violations)


def test_active_rule_version_with_non_approved_verification_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root, rv_status="ACTIVE", include_ver=True, ver_result="NEEDS_REVISION")
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("APPROVED Verification" in v for v in r.active_promotion_violations)


# --- H (temporal-correction scenario A). ACTIVE + APPROVED VER + valid current instrument passes --

def test_active_rule_version_with_full_valid_chain_passes(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root, rv_status="ACTIVE", instrument_currency="IN_FORCE")
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert r.passed, r
    assert not r.active_promotion_violations


# --- I (temporal-correction scenario B). ACTIVE + REPEALED instrument -> hard fail, unconditionally --

def test_active_rule_version_against_repealed_instrument_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(
        root, rv_status="ACTIVE", rv_effective_end=None,
        instrument_currency="REPEALED", instrument_effective_end=None,
    )
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("REPEALED" in v for v in r.active_promotion_violations)


def test_active_rule_version_against_repealed_instrument_fails_even_with_bounded_dates(tmp_path):
    """Regression guard: an earlier version of this gate let a bounded
    `effective_end_date` (a "historical window") excuse an ACTIVE Rule
    Version referencing a REPEALED/SUPERSEDED instrument. That escape hatch
    was removed — ACTIVE means CURRENTLY usable regulatory knowledge, full
    stop. Historical positions belong on a SUPERSEDED/RETIRED Rule Version
    instead (tests E/F below), which this gate does not apply to at all."""
    root = str(tmp_path)
    _write_golden_chain(
        root, rv_status="ACTIVE", rv_effective_end="2019-12-31",
        instrument_currency="REPEALED", instrument_effective_end="2020-01-01",
    )
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("REPEALED" in v for v in r.active_promotion_violations)
    assert not r.review_notes  # no "bounded historical position" note either


# --- (temporal-correction scenario C). ACTIVE + SUPERSEDED instrument -> hard fail --

def test_active_rule_version_against_superseded_instrument_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(
        root, rv_status="ACTIVE", rv_effective_end=None,
        instrument_currency="SUPERSEDED", instrument_effective_end=None,
    )
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("SUPERSEDED" in v for v in r.active_promotion_violations)


# --- J (temporal-correction scenarios E/F). historical SUPERSEDED/RETIRED version stays valid --

def test_historical_retired_rule_version_against_repealed_instrument_remains_valid(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(
        root, rv_status="RETIRED", rv_effective_end="2019-12-31",
        instrument_currency="REPEALED", instrument_effective_end="2020-01-01",
        include_ver=False,
    )
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert r.passed, r
    assert not r.active_promotion_violations


def test_historical_superseded_rule_version_against_superseded_instrument_remains_valid(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(
        root, rv_status="SUPERSEDED", rv_effective_end="2019-12-31",
        instrument_currency="SUPERSEDED", instrument_effective_end="2020-01-01",
        include_ver=False,
    )
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert r.passed, r


# --- K. DRAFT stays allowed and still blocked from authoritative PRODUCTION -

def test_draft_with_unresolved_provenance_still_blocks_production(engine):
    """Uses the REAL production dataset/engine (session fixtures from
    conftest.py) — confirms existing behaviour for the six real DRAFT Rule
    Versions is unaffected by the provenance substrate. Makes no assertion
    about provenance content."""
    from iris_engine.rules import EvaluationMode

    d = engine.evaluate_requirement(
        "P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True},
        EvaluationMode.PRODUCTION,
    )
    assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"


def test_real_dataset_still_validates_passed(dataset):
    """The real regulatory-data/ tree — six DRAFT Rule Versions with
    unresolved provenance, zero provenance records — must still validate
    PASSED after the provenance substrate lands."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regulatory-data")
    r = validate_dataset(root, dataset)
    assert r.passed, r
    assert not r.active_promotion_violations
    # the DRAFT rule versions' unresolved provenance is exactly what
    # populates review_notes, never a hard failure
    assert r.review_notes


# --- L. duplicate provenance ids fail -----------------------------------------

def test_duplicate_authority_id_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _w(root, "authorities", "AUTH-T1-dup.yaml", {
        "authority_id": "AUTH-T1", "name": "Duplicate Test Authority",
        "level": "STATE_REGULATOR", "jurisdiction": "TESTLAND",
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("AUTH-T1" in d for d in r.duplicate_ids)


def test_duplicate_verification_id_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _w(root, "verifications", "VER-T1-dup.yaml", {
        "verification_id": "VER-T1", "target_type": "RULE_VERSION",
        "target_id": "RULE-T1-V1", "reviewer": "Another Reviewer",
        "reviewed_at": "2026-01-02", "result": "APPROVED",
        "source_checks": ["SRC-T1"], "evidence_checks": ["EVID-T1"],
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("VER-T1" in d for d in r.duplicate_ids)


# --- M. new index count mismatch fails ----------------------------------------

def test_new_index_count_mismatch_fails(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _index(root, "authorities_index.yaml", {"authorities": [], "counts": {"total_authorities": 99}})
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("total_authorities" in m for m in r.index_count_mismatches)


# --- N (temporal-correction scenario D). TRANSITIONAL instrument -> review note, not a failure --

def test_transitional_instrument_produces_review_note_not_failure(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root, rv_status="ACTIVE", instrument_currency="TRANSITIONAL")
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert r.passed, r
    assert not r.active_promotion_violations
    assert any("TRANSITIONAL" in n for n in r.review_notes)


# --- extra coverage: schema shape / reviewer identity checks -----------------

def test_missing_required_field_is_a_schema_violation(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _w(root, "authorities", "AUTH-T1.yaml", {
        "authority_id": "AUTH-T1", "name": "Test Authority",
        # 'level' and 'jurisdiction' omitted
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("level" in s for s in r.schema_violations)
    assert any("jurisdiction" in s for s in r.schema_violations)


def test_regulatory_fact_with_empty_evidence_ids_is_a_schema_violation(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _w(root, "facts", "RF-T1.yaml", {
        "regulatory_fact_id": "RF-T1", "statement": "Test proposition.",
        "evidence_ids": [], "authority_id": "AUTH-T1",
        "instrument_id": "INST-T1", "verification_status": "VERIFIED",
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("evidence_ids" in s for s in r.schema_violations)


def test_empty_reviewer_is_rejected(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root, ver_reviewer="   ")
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("reviewer" in s.lower() for s in r.schema_violations)


def test_nonempty_reviewer_passes_schema_validation_regardless_of_wording(tmp_path):
    """The schema cannot establish whether a reviewer string names a real
    human — see iris_engine/validate.py's module docstring. A heuristic
    denylist that rejected names merely for containing "AI"/"system"/a
    model name was removed: it would have wrongly rejected legitimate
    human reviewers (e.g. a person named Aiden, or a team called
    "System Compliance"), and gave a false impression of an enforcement
    this schema cannot actually provide. Presence is all that's checked."""
    for reviewer in ("AI", "SYSTEM", "AUTO", "CLAUDE", "GPT", "Jane Reviewer"):
        root = str(tmp_path / reviewer)
        _write_golden_chain(root, ver_reviewer=reviewer)
        ds = RegulatoryDataset.load(root)
        r = validate_dataset(root, ds)
        assert r.passed, (reviewer, r)
        assert not any("reviewer" in s.lower() for s in r.schema_violations)


def test_verification_target_must_resolve(tmp_path):
    root = str(tmp_path)
    _write_golden_chain(root)
    _w(root, "verifications", "VER-T1.yaml", {
        "verification_id": "VER-T1", "target_type": "RULE_VERSION",
        "target_id": "RULE-GHOST-V1", "reviewer": "Jane Reviewer",
        "reviewed_at": "2026-01-01", "result": "APPROVED",
        "source_checks": ["SRC-T1"], "evidence_checks": ["EVID-T1"],
    })
    ds = RegulatoryDataset.load(root)
    r = validate_dataset(root, ds)
    assert not r.passed
    assert any("RULE-GHOST-V1" in b for b in r.broken_references)


def test_bare_dataset_with_no_provenance_directories_still_loads(tmp_path):
    """A regulatory-data tree with only the original five directories (no
    authorities/instruments/sources/evidence/facts/verifications at all)
    must still load and validate cleanly — the provenance substrate is
    additive, never required."""
    root = str(tmp_path)
    for d in ("conditions", "rules", "rule-versions", "requirements", "index", "registers"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    _w(root, "conditions", "COND-A.yaml", {
        "condition_id": "COND-A", "predicate_type": "BOOLEAN_EQUALS",
        "target_variable_key": "project.a", "operator": "==",
        "comparison_value": True, "unresolved_behavior": "UNKNOWN",
    })
    _w(root, "rules", "RULE-A.yaml", {"rule_id": "RULE-A", "requirement_id": "REQ-A"})
    _w(root, "rule-versions", "RULE-A-V1.yaml", {
        "rule_version_id": "RULE-A-V1", "rule_id": "RULE-A",
        "condition_expression_root_id": "COND-A", "status": "DRAFT",
    })
    _w(root, "requirements", "REQ-A.yaml", {"requirement_id": "REQ-A", "evaluated_by_rule_id": "RULE-A"})

    ds = RegulatoryDataset.load(root)
    assert ds.authorities == {} and ds.instruments == {} and ds.verifications == {}
    r = validate_dataset(root, ds)
    assert r.passed, r

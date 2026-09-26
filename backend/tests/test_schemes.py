"""
P2-K — scheme framework. Uses ONLY the synthetic SCH-9### fixtures in
tests/fixtures/scheme-data; the shipped catalogue is empty by design.
"""
import datetime as dt
import os
import shutil

import pytest

from app.schemes import (
    CANNOT_EVALUATE,
    NEEDS_INFORMATION,
    NOT_ELIGIBLE,
    POTENTIALLY_ELIGIBLE,
    load_catalogue,
    match_catalogue,
    match_scheme,
    validate_catalogue,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "scheme-data")
AS_OF = dt.date(2026, 9, 21)


@pytest.fixture()
def cat():
    c = load_catalogue(FIXTURES)
    assert c.errors == []
    return c


def _result(cat, facts, mode="PRODUCTION"):
    return match_catalogue(cat, facts, mode=mode, as_of=AS_OF)


def test_potentially_eligible_with_why_and_source(cat):
    out = _result(cat, {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 5000})
    [r] = out["results"]
    assert r["scheme_id"] == "SCH-9001" and r["outcome"] == POTENTIALLY_ELIGIBLE
    assert {w["scheme_condition_id"] for w in r["why"]} == {"SCHC-9001", "SCHC-9002"}
    assert all(w["result"] == "TRUE" for w in r["why"])
    assert r["official_source"]["url"].endswith(".invalid/synthetic-a")
    assert "never a final eligibility decision" in " ".join(out["notes"])


def test_not_eligible(cat):
    [r] = _result(cat, {"project.industry": "PHARMA", "project.dairy_liquid_milk_capacity": 5000})["results"]
    assert r["outcome"] == NOT_ELIGIBLE


def test_missing_fact_is_needs_information_not_ineligible(cat):
    [r] = _result(cat, {"project.industry": "FOOD"})["results"]
    assert r["outcome"] == NEEDS_INFORMATION
    assert r["missing_facts"] == ["project.dairy_liquid_milk_capacity"]


def test_kleene_false_wins_over_unknown(cat):
    # AND(FALSE, UNKNOWN) = FALSE — same semantics as the Rule Engine.
    [r] = _result(cat, {"project.industry": "PHARMA"})["results"]
    assert r["outcome"] == NOT_ELIGIBLE


def test_wrong_type_cannot_evaluate(cat):
    [r] = _result(cat, {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": "lots"})["results"]
    assert r["outcome"] == CANNOT_EVALUATE and r["errors"]


def test_draft_scheme_excluded_in_production_included_in_diagnostic(cat):
    prod = _result(cat, {})
    assert [r["scheme_id"] for r in prod["results"]] == ["SCH-9001"]
    diag = _result(cat, {}, mode="NON_PRODUCTION")
    ids = {r["scheme_id"]: r for r in diag["results"]}
    assert set(ids) == {"SCH-9001", "SCH-9002"}
    assert ids["SCH-9002"]["is_authoritative_catalogue_entry"] is False
    assert any("not authoritative" in n for n in diag["notes"])


def test_empty_catalogue_awaits_verified_data(tmp_path):
    out = match_catalogue(load_catalogue(str(tmp_path)), {"project.industry": "FOOD"}, as_of=AS_OF)
    assert out["catalogue_state"] == "AWAITING_VERIFIED_DATA"
    assert out["results"] == []
    assert out["notes"][0].startswith("SCHEME CATALOGUE AWAITING VERIFIED DATA")


def test_only_drafts_still_awaits(tmp_path):
    shutil.copytree(FIXTURES, tmp_path / "c")
    os.remove(tmp_path / "c" / "schemes" / "SCH-9001.yaml")
    out = match_catalogue(load_catalogue(str(tmp_path / "c")), {}, as_of=AS_OF)
    assert out["catalogue_state"] == "AWAITING_VERIFIED_DATA" and out["results"] == []


def test_invalid_catalogue_fails_closed(tmp_path):
    shutil.copytree(FIXTURES, tmp_path / "c")
    bad = tmp_path / "c" / "scheme-conditions" / "SCHC-9002.yaml"
    bad.write_text(bad.read_text(encoding="utf-8").replace('operator: ">="', 'operator: "<"'), encoding="utf-8")
    cat = load_catalogue(str(tmp_path / "c"))
    assert any("unsupported operator" in e for e in cat.errors)
    out = match_catalogue(cat, {}, as_of=AS_OF)
    assert out["catalogue_state"] == "INVALID" and out["results"] == []


def test_validator_requires_source_and_verification(cat):
    s = cat.schemes["SCH-9001"]
    s_bad = {**s, "official_source": {"url": "x"}, "last_verified": {}}
    cat.schemes["SCH-9001"] = s_bad
    errs = validate_catalogue(cat)
    assert any("official_source missing" in e for e in errs)
    assert any("requires last_verified" in e for e in errs)


def test_not_in_force_reported(cat):
    cat.schemes["SCH-9001"]["effective_end_date"] = "2026-01-31"
    [r] = _result(cat, {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 5000})["results"]
    assert r["not_in_force_reason"] == "No longer in force (ended 2026-01-31)."


def test_shipped_catalogue_has_no_errors_and_exactly_one_authoritative_scheme():
    """Tranche-1 production baseline (2026-09-23): backend/scheme-data/ ships
    3 real records (SCH-0001, SCH-0002, SCH-0004), of which exactly SCH-0002
    (CGTMSE) has been human-verified to ACTIVE + VERIFIED. SCH-0001 (ZED)
    and SCH-0004 (MS-EPP) remain DRAFT/UNVERIFIED. Production is no longer
    empty, but it is still not a free-for-all: lifecycle gating still
    admits only one authoritative record. See HANDOFF.md for the archival
    trail behind this."""
    from app.engine_service import BACKEND_DIR
    shipped = load_catalogue(os.path.join(BACKEND_DIR, "scheme-data"))
    assert shipped.errors == []
    # Scheme Catalogue Tranche 1 (2026-09-24) added SCH-0005..SCH-0010, all DRAFT/UNVERIFIED. Scheme
    # Verification Batch 1 (2026-09-26) promoted SCH-0001/0005/0008/0010 (limited encoded scope); the
    # lifecycle gate now admits exactly those four plus SCH-0002.
    assert set(shipped.schemes) == {"SCH-0001", "SCH-0002", "SCH-0004", "SCH-0005", "SCH-0006", "SCH-0007", "SCH-0008", "SCH-0009", "SCH-0010"}
    assert [s["scheme_id"] for s in shipped.usable] == ["SCH-0001", "SCH-0002", "SCH-0005", "SCH-0008", "SCH-0010"]
    assert shipped.schemes["SCH-0002"]["status"] == "ACTIVE"
    assert shipped.schemes["SCH-0002"]["confidence"] == "VERIFIED"
    for sid in ("SCH-0001", "SCH-0005", "SCH-0008", "SCH-0010"):   # Scheme Verification Batch 1
        assert shipped.schemes[sid]["status"] == "ACTIVE"
        assert shipped.schemes[sid]["confidence"] == "VERIFIED"
    for sid in ("SCH-0004", "SCH-0006", "SCH-0007", "SCH-0009"):
        assert shipped.schemes[sid]["status"] == "DRAFT"
        assert shipped.schemes[sid]["confidence"] == "UNVERIFIED"


# --- API ---------------------------------------------------------------------------

def test_api_shipped_state_ready_with_one_authoritative_scheme(client):
    catalogue = client.get("/api/v1/schemes/catalogue").json()
    assert catalogue["catalogue_state"] == "READY"
    assert catalogue["counts"] == {"total": 9, "active_verified": 5}
    by_id = {s["scheme_id"]: s for s in catalogue["schemes"]}
    for sid in ("SCH-0001", "SCH-0002", "SCH-0005", "SCH-0008", "SCH-0010"):
        assert by_id[sid]["is_authoritative_catalogue_entry"] is True, sid
    for sid in ("SCH-0004", "SCH-0006", "SCH-0007", "SCH-0009"):
        assert by_id[sid]["is_authoritative_catalogue_entry"] is False, sid

    # PRODUCTION-mode project matching: DRAFT records (SCH-0001, SCH-0004)
    # never appear in results at all — only the one authoritative record
    # does, evaluated normally (freshbite has no facts set, so it comes
    # back NEEDS_INFORMATION rather than being silently omitted).
    body = client.get("/api/v1/projects/freshbite/schemes").json()
    assert body["catalogue_state"] == "READY"
    assert [r["scheme_id"] for r in body["results"]] == ["SCH-0001", "SCH-0002", "SCH-0005", "SCH-0008", "SCH-0010"]
    assert body["results"][0]["outcome"] == NEEDS_INFORMATION


def test_api_with_synthetic_fixtures(client, monkeypatch):
    monkeypatch.setenv("SCHEME_DATA_ROOT", FIXTURES)
    from app.config import get_settings
    get_settings.cache_clear()
    client.post("/api/v1/projects/freshbite/facts", json={"facts": {
        "project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 2000}})
    body = client.get("/api/v1/projects/freshbite/schemes").json()
    assert body["catalogue_state"] == "READY"
    assert [r["outcome"] for r in body["results"]] == [POTENTIALLY_ELIGIBLE]
    assert client.get("/api/v1/projects/nope/schemes").status_code == 404
    get_settings.cache_clear()


# --- Application status / window (independent of eligibility) --------------
#
# SCH-9001's fixture carries application_status: VERIFIED_OPEN +
# application_window (see tests/fixtures/scheme-data/schemes/SCH-9001.yaml).
# Scenarios that need a DIFFERENT application_status build an in-memory
# overlay of that same fixture scheme + its real, loaded SCHC-9003 condition
# tree — no new YAML fixture files are needed, and no catalogue-level
# result-count assumption in the tests above is disturbed.

_ELIGIBLE_FACTS = {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 5000}
_MISSING_CAPACITY_FACTS = {"project.industry": "FOOD"}
_NOT_ELIGIBLE_FACTS = {"project.industry": "PHARMA", "project.dairy_liquid_milk_capacity": 5000}


def _overlay(cat, **application_fields):
    """A copy of the loaded SCH-9001 fixture with different application_status
    fields — never a different eligibility condition tree."""
    return {**cat.schemes["SCH-9001"], **application_fields}


def test_A_potentially_eligible_plus_verified_open(cat):
    r = match_scheme(_overlay(cat), cat.conditions, _ELIGIBLE_FACTS, AS_OF)
    assert r["outcome"] == POTENTIALLY_ELIGIBLE
    assert r["application_status"] == "VERIFIED_OPEN"
    assert r["application_window"]["mode"] == "FIXED_WINDOW"


def test_B_potentially_eligible_plus_verified_closed(cat):
    scheme = _overlay(
        cat,
        application_status="VERIFIED_CLOSED",
        application_window={
            "mode": "CLOSED", "opens": "2025-01-01", "closes": "2025-09-30",
            "as_of_date": "2026-09-21",
            "source_reference": {"document_title": "SYNTHETIC"},
        },
    )
    r = match_scheme(scheme, cat.conditions, _ELIGIBLE_FACTS, AS_OF)
    assert r["outcome"] == POTENTIALLY_ELIGIBLE
    assert r["application_status"] == "VERIFIED_CLOSED"
    assert r["application_window"]["closes"] == "2025-09-30"


def test_C_needs_information_plus_verified_open(cat):
    r = match_scheme(_overlay(cat), cat.conditions, _MISSING_CAPACITY_FACTS, AS_OF)
    assert r["outcome"] == NEEDS_INFORMATION
    assert r["application_status"] == "VERIFIED_OPEN"


def test_D_not_eligible_plus_verified_open(cat):
    r = match_scheme(_overlay(cat), cat.conditions, _NOT_ELIGIBLE_FACTS, AS_OF)
    assert r["outcome"] == NOT_ELIGIBLE
    assert r["application_status"] == "VERIFIED_OPEN"


def test_E_potentially_eligible_plus_selection_completed(cat):
    scheme = _overlay(
        cat,
        application_status="SELECTION_COMPLETED",
        application_window={
            "mode": "SELECTION_COMPLETED", "opens": None, "closes": None,
            "as_of_date": "2026-09-21",
            "source_reference": {"document_title": "SYNTHETIC"},
        },
    )
    r = match_scheme(scheme, cat.conditions, _ELIGIBLE_FACTS, AS_OF)
    assert r["outcome"] == POTENTIALLY_ELIGIBLE
    assert r["application_status"] == "SELECTION_COMPLETED"


def test_F_potentially_eligible_plus_no_current_window(cat):
    scheme = _overlay(
        cat,
        application_status="NO_CURRENT_WINDOW",
        application_window={
            "mode": "UNKNOWN", "opens": None, "closes": None,
            "as_of_date": "2026-09-21",
            "source_reference": {"document_title": "SYNTHETIC"},
        },
    )
    r = match_scheme(scheme, cat.conditions, _ELIGIBLE_FACTS, AS_OF)
    assert r["outcome"] == POTENTIALLY_ELIGIBLE
    assert r["application_status"] == "NO_CURRENT_WINDOW"


def test_G_malformed_application_status_fails_validation(cat):
    cat.schemes["SCH-9001"] = _overlay(cat, application_status="OPEN_FOREVER")
    errs = validate_catalogue(cat)
    assert any("application_status must be one of" in e for e in errs)


def test_H_malformed_application_window_mode_fails_validation(cat):
    cat.schemes["SCH-9001"] = _overlay(
        cat, application_window={**cat.schemes["SCH-9001"]["application_window"], "mode": "ALWAYS_OPEN"},
    )
    errs = validate_catalogue(cat)
    assert any("application_window.mode must be one of" in e for e in errs)


def test_I_verified_current_status_without_as_of_date_fails_validation(cat):
    window = {k: v for k, v in cat.schemes["SCH-9001"]["application_window"].items() if k != "as_of_date"}
    cat.schemes["SCH-9001"] = _overlay(cat, application_window=window)
    errs = validate_catalogue(cat)
    assert any("requires application_window.as_of_date" in e for e in errs)


def test_verified_open_fixed_window_without_closes_fails_validation(cat):
    window = {**cat.schemes["SCH-9001"]["application_window"], "closes": None}
    cat.schemes["SCH-9001"] = _overlay(cat, application_window=window)
    errs = validate_catalogue(cat)
    assert any("closes is required for VERIFIED_OPEN + FIXED_WINDOW" in e for e in errs)


def test_malformed_application_window_date_fails_validation(cat):
    window = {**cat.schemes["SCH-9001"]["application_window"], "as_of_date": "21/09/2026"}
    cat.schemes["SCH-9001"] = _overlay(cat, application_window=window)
    errs = validate_catalogue(cat)
    assert any("as_of_date must be YYYY-MM-DD" in e for e in errs)


def test_J_supersedes_unknown_scheme_fails_validation(cat):
    cat.schemes["SCH-9001"] = _overlay(cat, supersedes="SCH-9099")
    errs = validate_catalogue(cat)
    assert any("supersedes -> unknown scheme" in e for e in errs)


def test_superseded_by_unknown_scheme_fails_validation(cat):
    cat.schemes["SCH-9001"] = _overlay(cat, superseded_by="SCH-9098")
    errs = validate_catalogue(cat)
    assert any("superseded_by -> unknown scheme" in e for e in errs)


def test_supersedes_resolving_to_a_real_scheme_is_valid(cat):
    cat.schemes["SCH-9001"] = _overlay(cat, supersedes="SCH-9002")
    errs = validate_catalogue(cat)
    assert not any("supersedes" in e for e in errs)


def test_K_application_status_never_alters_eligibility(cat):
    """Same application_status/window, three different fact sets -> three
    different outcomes driven ONLY by the eligibility condition tree."""
    scheme = _overlay(cat)  # application_status: VERIFIED_OPEN, unchanged
    outcomes = {
        "eligible": match_scheme(scheme, cat.conditions, _ELIGIBLE_FACTS, AS_OF)["outcome"],
        "missing": match_scheme(scheme, cat.conditions, _MISSING_CAPACITY_FACTS, AS_OF)["outcome"],
        "not_eligible": match_scheme(scheme, cat.conditions, _NOT_ELIGIBLE_FACTS, AS_OF)["outcome"],
    }
    assert outcomes == {
        "eligible": POTENTIALLY_ELIGIBLE,
        "missing": NEEDS_INFORMATION,
        "not_eligible": NOT_ELIGIBLE,
    }
    # and conversely: same facts, every possible application_status ->
    # identical outcome, because application_status is never read by the
    # matcher's outcome computation.
    for status in (
        "VERIFIED_OPEN", "VERIFIED_CLOSED", "SELECTION_COMPLETED",
        "NO_CURRENT_WINDOW", "UNRESOLVED_CURRENT_STATUS", "DISCONTINUED",
    ):
        r = match_scheme(_overlay(cat, application_status=status), cat.conditions, _ELIGIBLE_FACTS, AS_OF)
        assert r["outcome"] == POTENTIALLY_ELIGIBLE


def test_L_production_catalogue_is_ready_with_tranche1_records():
    """The real shipped backend/scheme-data/ root, end-to-end, with the new
    schema in place. Tranche-1 baseline (2026-09-23): 3 real records
    shipped, exactly SCH-0002 (CGTMSE) human-verified to ACTIVE+VERIFIED;
    SCH-0001 (ZED) and SCH-0004 (MS-EPP) remain DRAFT and therefore never
    appear in a PRODUCTION-mode result."""
    from app.engine_service import BACKEND_DIR
    root = os.path.join(BACKEND_DIR, "scheme-data")
    cat = load_catalogue(root)
    assert cat.errors == []
    out = match_catalogue(cat, {"project.industry": "FOOD"}, as_of=AS_OF)
    assert out["catalogue_state"] == "READY"
    assert out["counts"] == {"total": 9, "active_verified": 5}
    assert [r["scheme_id"] for r in out["results"]] == ["SCH-0001", "SCH-0002", "SCH-0005", "SCH-0008", "SCH-0010"]
    # freshbite-style facts above don't touch project.msme_classification,
    # so the one authoritative record comes back NEEDS_INFORMATION, not
    # ELIGIBLE/APPROVED/GUARANTEED and not silently dropped.
    assert out["results"][0]["outcome"] == NEEDS_INFORMATION


def test_api_catalogue_exposes_application_status_fields(client, monkeypatch):
    monkeypatch.setenv("SCHEME_DATA_ROOT", FIXTURES)
    from app.config import get_settings
    get_settings.cache_clear()
    body = client.get("/api/v1/schemes/catalogue").json()
    sch9001 = next(s for s in body["schemes"] if s["scheme_id"] == "SCH-9001")
    assert sch9001["application_status"] == "VERIFIED_OPEN"
    assert sch9001["application_window"]["mode"] == "FIXED_WINDOW"
    assert sch9001["supersedes"] is None and sch9001["superseded_by"] is None
    get_settings.cache_clear()

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


def test_shipped_catalogue_is_empty():
    from app.engine_service import BACKEND_DIR
    shipped = load_catalogue(os.path.join(BACKEND_DIR, "scheme-data"))
    assert shipped.schemes == {} and shipped.conditions == {}


# --- API ---------------------------------------------------------------------------

def test_api_shipped_state_awaits_verified_data(client):
    assert client.get("/api/v1/schemes/catalogue").json()["catalogue_state"] == "AWAITING_VERIFIED_DATA"
    body = client.get("/api/v1/projects/freshbite/schemes").json()
    assert body["catalogue_state"] == "AWAITING_VERIFIED_DATA" and body["results"] == []


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

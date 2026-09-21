"""
P0-D — Deterministic Consistency Engine.

Fixture values are SYNTHETIC. The mismatches are taken from the SwaadHarvest
synthetic dataset's own scenario descriptions (reference-data/
SwaadHarvest_Foods_IRIS_Synthetic_Dataset.zip, source_data/scenarios.json):
name (SCN-0003), address (SCN-0004), pack size (SCN-0006), batch (SCN-0007),
expired report (SCN-0009). They are used only as objective comparison inputs;
the dataset's `expected_result` labels are NOT used as answers, and nothing
here is a regulatory or compliance determination.
"""
import datetime as dt

import pytest

from app.consistency import (
    CONFLICT,
    CONSISTENT,
    EXPIRED,
    LOW_CONFIDENCE,
    MISSING,
    NOT_COMPARABLE,
    REVIEW_REQUIRED,
    ConsistencyInputError,
    run_consistency_check,
)

AS_OF = dt.date(2026, 9, 7)  # the synthetic dataset's own demo evaluation date


def _obs(field, value, doc, unit=None, confidence=None, **extra):
    o = {"field": field, "value": value, "source": {"kind": "DOCUMENT", "document_id": doc,
                                                     "document_name": doc, "page": 1,
                                                     "evidence_text": f"{field}: {value}"}}
    if unit is not None:
        o["unit"] = unit
    if confidence is not None:
        o["confidence"] = confidence
    o.update(extra)
    return o


def _run(obs, **kw):
    return run_consistency_check(obs, as_of=AS_OF, **kw)


def _only(result, field):
    return [c for c in result["checks"] if c["field"] == field]


# --- equality & normalisation ---------------------------------------------------

def test_equal_values_are_consistent():
    r = _run([_obs("batch_number", "BATCH-MP-001", "BMR"), _obs("batch_number", "BATCH-MP-001", "CoA")])
    [c] = _only(r, "batch_number")
    assert c["status"] == CONSISTENT and r["issues_found"] == 0


def test_normalized_equal_names_are_consistent():
    r = _run([
        _obs("entity_name", "SwaadHarvest Foods Private Limited", "GST"),
        _obs("entity_name", "M/s. SWAADHARVEST FOODS PVT. LTD.", "Licence"),
    ])
    assert _only(r, "entity_name")[0]["status"] == CONSISTENT


def test_name_differing_only_in_spacing_requires_review_not_auto_match():
    """SCN-0003 (synthetic): 'SwaadHarvest Foods Private Limited' vs
    'Swaad Harvest Foods Pvt Ltd' — never silently merged."""
    r = _run([
        _obs("entity_name", "SwaadHarvest Foods Private Limited", "FOOD-ENT-003"),
        _obs("entity_name", "Swaad Harvest Foods Pvt Ltd", "FOOD-ENT-006"),
    ])
    [c] = _only(r, "entity_name")
    assert c["status"] == REVIEW_REQUIRED
    assert c["human_review_required"] is True


def test_different_names_conflict():
    r = _run([_obs("entity_name", "SwaadHarvest Foods Private Limited", "A"),
              _obs("entity_name", "Harvest Gold Foods Private Limited", "B")])
    assert _only(r, "entity_name")[0]["status"] == CONFLICT


def test_address_plot_number_mismatch_conflicts():
    """SCN-0004 (synthetic): Plot No. 18 vs Plot No. 20, same sector."""
    r = _run([
        _obs("address", "Plot No. 18, Sector 11, IIE SIDCUL, Haridwar", "FOOD-ENT-003"),
        _obs("address", "Plot No. 20, Sector 11, IIE SIDCUL, Haridwar", "FOOD-FAC-001"),
    ])
    [c] = _only(r, "address")
    assert c["status"] == CONFLICT
    # Evidence is preserved on both sides, verbatim.
    assert c["reference"]["raw_value"] == "Plot No. 18, Sector 11, IIE SIDCUL, Haridwar"
    assert c["candidate"]["raw_value"] == "Plot No. 20, Sector 11, IIE SIDCUL, Haridwar"
    assert c["candidate"]["source"]["document_id"] == "FOOD-FAC-001"
    assert c["candidate"]["source"]["evidence_text"]
    assert c["candidate"]["source"]["page"] == 1


def test_address_normalization_equal():
    r = _run([_obs("address", "Plot No. 18, Sector 11", "A"), _obs("address", "plot 18 sector 11", "B")])
    assert _only(r, "address")[0]["status"] == CONSISTENT


def test_less_specific_address_requires_review_not_conflict():
    r = _run([_obs("address", "Plot 18, Sector 11, IIE SIDCUL, Haridwar", "A"),
              _obs("address", "Haridwar", "B")])
    assert _only(r, "address")[0]["status"] == REVIEW_REQUIRED


def test_reordered_address_requires_review():
    r = _run([_obs("address", "Plot 18, Sector 11", "A"), _obs("address", "Sector 11, Plot 18", "B")])
    assert _only(r, "address")[0]["status"] == REVIEW_REQUIRED


def test_batch_mismatch_conflicts():
    """SCN-0007 (synthetic): BMR BATCH-MP-001 vs CoA BATCH-MP-002."""
    r = _run([_obs("batch_number", "BATCH-MP-001", "FOOD-REG-010"),
              _obs("batch_number", "BATCH-MP-002", "FOOD-REG-007")])
    assert _only(r, "batch_number")[0]["status"] == CONFLICT


# --- units --------------------------------------------------------------------------

def test_pack_size_mismatch_conflicts():
    """SCN-0006 (synthetic): label 500 g vs product master 200 g."""
    r = _run([_obs("net_quantity", "200 g", "Product master"),
              _obs("net_quantity", "500 g", "FOOD-REG-011")])
    assert _only(r, "net_quantity")[0]["status"] == CONFLICT


def test_safe_unit_conversion_is_consistent():
    r = _run([_obs("net_quantity", "500 g", "A"), _obs("net_quantity", 0.5, "B", unit="kg")])
    assert _only(r, "net_quantity")[0]["status"] == CONSISTENT


def test_capacity_kld_vs_litres_per_day():
    r = _run([_obs("production_capacity", "50,000 L/day", "A"),
              _obs("production_capacity", 50, "B", unit="KLD")])
    assert _only(r, "production_capacity")[0]["status"] == CONSISTENT


def test_incompatible_units_not_comparable():
    r = _run([_obs("net_quantity", "500 g", "A"), _obs("net_quantity", "500 ml", "B")])
    assert _only(r, "net_quantity")[0]["status"] == NOT_COMPARABLE


def test_unknown_unit_not_comparable():
    r = _run([_obs("net_quantity", "500 g", "A"), _obs("net_quantity", "3 pouches", "B")])
    statuses = {c["status"] for c in _only(r, "net_quantity")}
    assert NOT_COMPARABLE in statuses


def test_missing_unit_not_comparable():
    r = _run([_obs("net_quantity", "500 g", "A"), _obs("net_quantity", 500, "B")])
    assert NOT_COMPARABLE in {c["status"] for c in _only(r, "net_quantity")}


# --- missing / expired / confidence ------------------------------------------------

def test_missing_required_field():
    r = _run([_obs("entity_name", "X Foods", "A")], required_fields=["batch_number"])
    [c] = _only(r, "batch_number")
    assert c["status"] == MISSING


def test_missing_candidate_value_is_not_an_observation():
    r = _run([_obs("batch_number", "B-1", "A"), _obs("batch_number", None, "B")])
    assert _only(r, "batch_number") == []
    assert r["uncompared_fields"][0]["field"] == "batch_number"


def test_expired_document():
    """SCN-0009 (synthetic): water report valid until 2025-11-14."""
    r = _run([_obs("valid_until", "2025-11-14", "FOOD-FAC-004")])
    [c] = _only(r, "valid_until")
    assert c["status"] == EXPIRED
    assert c["days_remaining"] == (dt.date(2025, 11, 14) - AS_OF).days


def test_valid_document_has_days_remaining():
    r = _run([_obs("valid_until", "2027-12-31", "FOOD-FAC-001")])
    [c] = _only(r, "valid_until")
    assert c["status"] == CONSISTENT
    assert c["days_remaining"] == (dt.date(2027, 12, 31) - AS_OF).days


def test_expiry_boundary_same_day_is_not_expired():
    r = _run([_obs("valid_until", AS_OF.isoformat(), "A")])
    assert _only(r, "valid_until")[0]["status"] == CONSISTENT


def test_ambiguous_date_format_not_guessed():
    r = _run([_obs("valid_until", "03/04/2026", "A")])
    assert _only(r, "valid_until")[0]["status"] == NOT_COMPARABLE


def test_low_confidence_excluded_and_flagged():
    r = _run([_obs("batch_number", "BATCH-MP-001", "A"),
              _obs("batch_number", "BATCH-MP-009", "B", confidence=0.3)])
    statuses = [c["status"] for c in _only(r, "batch_number")]
    assert statuses == [LOW_CONFIDENCE]  # never reported as a CONFLICT
    assert r["human_review_required"] is True


# --- reference selection, determinism, contract -------------------------------------

def test_explicit_reference_wins():
    r = _run([_obs("batch_number", "B-1", "A"),
              _obs("batch_number", "B-2", "B", is_reference=True)])
    [c] = _only(r, "batch_number")
    assert c["reference_basis"] == "EXPLICIT_REFERENCE"
    assert c["reference"]["raw_value"] == "B-2"


def test_project_record_is_default_reference():
    r = _run([_obs("entity_name", "Other Co", "Doc"),
              {"field": "entity_name", "value": "Acme Foods", "source": {"kind": "PROJECT_RECORD"}}])
    [c] = _only(r, "entity_name")
    assert c["reference_basis"] == "PROJECT_RECORD"


def test_deterministic_ids_and_order():
    obs = [_obs("address", "Plot 18", "A"), _obs("address", "Plot 20", "B"),
           _obs("valid_until", "2020-01-01", "C")]
    assert _run(obs) == _run(obs)


def test_result_never_claims_compliance_or_writes():
    r = _run([_obs("batch_number", "B-1", "A"), _obs("batch_number", "B-2", "B")])
    assert r["project_facts_modified"] is False
    text = str(r).lower()
    assert "non-compliant" not in text and "non_compliant" not in text


def test_unknown_field_rejected():
    with pytest.raises(ConsistencyInputError):
        _run([_obs("favourite_colour", "blue", "A")])


def test_bad_confidence_rejected():
    with pytest.raises(ConsistencyInputError):
        _run([_obs("batch_number", "B", "A", confidence=7)])


# --- API ---------------------------------------------------------------------------

P = "freshbite"


def test_api_fields_registry(client):
    fields = {f["field"] for f in client.get("/api/v1/consistency/fields").json()["fields"]}
    assert {"entity_name", "address", "batch_number", "net_quantity", "valid_until"} <= fields


def test_api_check_uses_confirmed_record_and_does_not_write(client):
    client.post(f"/api/v1/projects/{P}/facts",
                json={"facts": {"document.business_name": "FreshBite Foods Private Limited"}})
    before = client.get(f"/api/v1/projects/{P}/facts").json()["facts"]
    r = client.post(f"/api/v1/projects/{P}/consistency-check", json={
        "as_of_date": "2026-09-07",
        "observations": [
            {"field": "entity_name", "value": "Fresh Bite Foods Pvt Ltd", "confidence": 0.9,
             "source": {"kind": "DOCUMENT", "document_name": "GST certificate (synthetic)",
                        "page": 1, "evidence_text": "Legal Name: Fresh Bite Foods Pvt Ltd"}},
            {"field": "valid_until", "value": "2025-11-14",
             "source": {"document_name": "Water report (synthetic)"}},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    name = next(c for c in body["checks"] if c["field"] == "entity_name")
    assert name["reference_basis"] == "PROJECT_RECORD"
    assert name["status"] == REVIEW_REQUIRED
    assert name["candidate"]["confidence"] == 0.9
    assert name["candidate"]["source"]["evidence_text"].startswith("Legal Name")
    assert any(c["status"] == EXPIRED for c in body["checks"])
    assert client.get(f"/api/v1/projects/{P}/facts").json()["facts"] == before


def test_api_cannot_forge_project_record_source(client):
    r = client.post(f"/api/v1/projects/{P}/consistency-check", json={
        "observations": [{"field": "entity_name", "value": "X", "source": {"kind": "PROJECT_RECORD"}}]})
    assert r.status_code == 422


def test_api_invalid_field_and_date(client):
    assert client.post(f"/api/v1/projects/{P}/consistency-check", json={
        "observations": [{"field": "nope", "value": "x"}]}).status_code == 422
    assert client.post(f"/api/v1/projects/{P}/consistency-check", json={
        "as_of_date": "07/09/2026"}).status_code == 422


def test_api_unknown_project_404(client):
    assert client.post("/api/v1/projects/nope/consistency-check", json={}).status_code == 404


def test_api_fail_closed_and_cross_user(monkeypatch):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.main import app
    from app.security import CurrentUser, Role, get_current_user, get_optional_user
    from app.store import get_store

    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()
    get_store.cache_clear()
    c = TestClient(app, raise_server_exceptions=False)
    a = CurrentUser(user_id="a", email="a@x", role=Role.INDUSTRY_USER, name="a", is_demo=False)
    b = CurrentUser(user_id="b", email="b@x", role=Role.INDUSTRY_USER, name="b", is_demo=False)

    def as_(u):
        app.dependency_overrides[get_optional_user] = lambda: u
        app.dependency_overrides[get_current_user] = lambda: u

    try:
        as_(a)
        pid = c.post("/api/v1/projects", json={"name": "A", "industry": "food"}).json()["id"]
        c.post(f"/api/v1/projects/{pid}/facts",
               json={"facts": {"document.business_name": "Secret Name Pvt Ltd"}})
        assert c.post(f"/api/v1/projects/{pid}/consistency-check", json={}).status_code == 200
        as_(b)
        r = c.post(f"/api/v1/projects/{pid}/consistency-check", json={})
        assert r.status_code == 404 and "Secret" not in r.text
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        assert c.post(f"/api/v1/projects/{pid}/consistency-check", json={}).status_code == 401
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        get_settings.cache_clear()
        get_store.cache_clear()

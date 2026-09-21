"""P1-G — renewals derived only from expiry dates on record."""
import datetime as dt

from app.renewals import (
    ACTION_REQUIRED,
    COMPLETED,
    EXPIRED,
    NO_EXPIRY,
    UPCOMING,
    build_renewal_register,
    records_from_confirmed_facts,
    records_from_metadata,
)

AS_OF = dt.date(2026, 9, 21)


def _rec(rid, expiry, kind="STORED_METADATA", completed=False):
    return {"record_id": rid, "title": rid, "expiry_date": expiry, "source_kind": kind,
            "completed": completed}


def _one(records, **kw):
    return build_renewal_register(records, as_of=AS_OF, **kw)["items"]


def test_upcoming_beyond_window():
    [i] = _one([_rec("A", "2027-12-31")])
    assert i["status"] == UPCOMING
    assert i["days_remaining"] == (dt.date(2027, 12, 31) - AS_OF).days


def test_action_required_within_policy_window():
    [i] = _one([_rec("A", "2026-10-21")], action_window_days=90)
    assert i["status"] == ACTION_REQUIRED and i["days_remaining"] == 30


def test_window_is_configurable_policy():
    [i] = _one([_rec("A", "2026-10-21")], action_window_days=10)
    assert i["status"] == UPCOMING
    reg = build_renewal_register([], as_of=AS_OF, action_window_days=10)
    assert reg["action_window_is_policy"] is True
    assert any("not a statutory" in n for n in reg["notes"])


def test_expired():
    [i] = _one([_rec("A", "2025-11-14")])
    assert i["status"] == EXPIRED and i["days_remaining"] < 0


def test_expiry_today_is_not_expired():
    [i] = _one([_rec("A", AS_OF.isoformat())])
    assert i["status"] == ACTION_REQUIRED and i["days_remaining"] == 0


def test_no_expiry_is_never_given_an_assumed_date():
    [i] = _one([_rec("A", None)])
    assert i["status"] == NO_EXPIRY
    assert i["days_remaining"] is None and i["expiry_date"] is None


def test_completed_only_when_record_says_so():
    [i] = _one([_rec("A", "2020-01-01", completed=True)])
    assert i["status"] == COMPLETED
    # An old expired record is NOT inferred completed just because it is old.
    [j] = _one([_rec("B", "2020-01-01")])
    assert j["status"] == EXPIRED


def test_deterministic_and_sorted():
    recs = [_rec("up", "2028-01-01"), _rec("exp", "2020-01-01"), _rec("none", None),
            _rec("due", "2026-10-01")]
    a = build_renewal_register(recs, as_of=AS_OF)
    assert a == build_renewal_register(recs, as_of=AS_OF)
    assert [i["record_id"] for i in a["items"]] == ["exp", "due", "up", "none"]


def test_unparseable_date_not_guessed():
    [i] = _one([_rec("A", "30/06/2029")])
    assert i["status"] == NO_EXPIRY


def test_synthetic_metadata_is_labelled():
    rows = [{"document_id": "DOC-REG-004", "pharma_subtype": "STATE_DRUG_REGISTRATION",
             "expiry_date": "2021-04-30", "manifest_source": "synthetic_generation",
             "manifest_status": "ACTIVE"}]
    [i] = _one(records_from_metadata(rows))
    assert i["is_synthetic"] is True and i["source_label"] == "SYNTHETIC DEMO DATA"
    assert i["status"] == EXPIRED


def test_renewed_manifest_status_is_completed():
    rows = [{"document_id": "X", "expiry_date": "2020-01-01", "manifest_status": "RENEWED"}]
    assert _one(records_from_metadata(rows))[0]["status"] == COMPLETED


def test_confirmed_fact_source():
    [i] = _one(records_from_confirmed_facts({"document.valid_until": "2027-01-01"}))
    assert i["source_kind"] == "CONFIRMED_DOCUMENT" and i["is_synthetic"] is False
    assert records_from_confirmed_facts({}) == []


# --- API ---------------------------------------------------------------------------

def test_api_empty_without_dates(client):
    body = client.get("/api/v1/projects/freshbite/renewals").json()
    assert body["items"] == []


def test_api_uses_confirmed_fact(client):
    client.post("/api/v1/projects/freshbite/facts",
                json={"facts": {"document.valid_until": "2026-10-01"}})
    body = client.get("/api/v1/projects/freshbite/renewals",
                      params={"as_of": "2026-09-21", "action_window_days": 30}).json()
    [i] = body["items"]
    assert i["status"] == ACTION_REQUIRED and i["days_remaining"] == 10


def test_api_validation_and_404(client):
    assert client.get("/api/v1/projects/freshbite/renewals", params={"as_of": "21/09/2026"}).status_code == 422
    assert client.get("/api/v1/projects/freshbite/renewals", params={"action_window_days": 0}).status_code == 422
    assert client.get("/api/v1/projects/nope/renewals").status_code == 404


def test_supabase_store_reads_metadata_for_project_company(monkeypatch):
    from app.store.supabase_store import SupabaseStore

    calls = []

    def fake_get(self, path, params):
        calls.append((path, params))
        if path == "/companies":
            return [{"company_id": "COMP-0001"}]
        return [{"document_id": "DOC-1", "expiry_date": "2029-06-30"}]

    monkeypatch.setattr(SupabaseStore, "_get", fake_get)
    store = SupabaseStore.__new__(SupabaseStore)
    rows = store.list_document_metadata("aarav-lifesciences")
    assert rows == [{"document_id": "DOC-1", "expiry_date": "2029-06-30"}]
    assert calls[0][1]["project_id"] == "eq.aarav-lifesciences"
    assert calls[1][1]["company_id"] == 'in.("COMP-0001")'

"""Government showcase cleanup: officer/company hydration + explicit legacy operational label."""
from app.legacy_evidence import legacy_operational_info
from app.store.supabase_department_store import SupabaseDepartmentStore


def test_legacy_operational_label_is_explicit_and_exact():
    assert legacy_operational_info("aarav-lifesciences", "APP-AARAV-REQ-0001")["label"].startswith("Legacy operational record")
    assert legacy_operational_info("aarav-lifesciences", "APP-AARAV-REQ-0002") is not None
    # never inferred: other application ids / other projects are not legacy, whatever their title says
    assert legacy_operational_info("aarav-lifesciences", "APP-DEMO-OTHER") is None
    assert legacy_operational_info("voltedge-mobility", "APP-AARAV-REQ-0001") is None
    assert legacy_operational_info(None, None) is None


def test_decorate_hydrates_officer_and_company_names():
    store = SupabaseDepartmentStore("https://example.invalid", "k")

    def fake_get(path, params=None):
        if path == "/department_users":
            return [{"id": "u1", "name": "Officer One"}]
        if path == "/projects":
            return [{"id": "p1", "name": "Company One"}, {"id": "aarav-lifesciences", "name": "Aarav"}]
        return []

    store._get = fake_get  # type: ignore[assignment]
    rows = [
        {"application_id": "A1", "project_id": "p1", "assigned_officer_id": "u1"},
        {"application_id": "APP-AARAV-REQ-0001", "project_id": "aarav-lifesciences", "assigned_officer_id": None},
    ]
    store._decorate_applications(rows)
    assert rows[0]["assigned_officer_name"] == "Officer One" and rows[0]["project_name"] == "Company One"
    assert rows[0]["legacy_operational"] is None
    assert rows[1]["assigned_officer_name"] is None and rows[1]["legacy_operational"] is not None

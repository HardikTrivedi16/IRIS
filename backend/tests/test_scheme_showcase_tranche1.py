"""Scheme Catalogue Tranche 1 (SCH-0005..SCH-0010): shipped records, lifecycle, application status, and matcher outcomes
against the approved showcase facts (simulated in memory — no Supabase)."""
import datetime as dt
import os

from app.engine_service import BACKEND_DIR
from app.schemes import load_catalogue, match_catalogue

AS_OF = dt.date(2026, 9, 24)
CAT = load_catalogue(os.path.join(BACKEND_DIR, "scheme-data"))
NEW = ["SCH-0005", "SCH-0006", "SCH-0007", "SCH-0008", "SCH-0009", "SCH-0010"]

# persisted showcase facts (relevant subset) + the approved synthetic delta
SWAAD = {"project.industry": "FOOD", "project.location_state": "MAHARASHTRA", "project.annual_turnover_inr": 400000000}
AARAV = {"project.industry": "PHARMACEUTICAL", "project.location_state": "MAHARASHTRA", "project.msme_classification": "MEDIUM",
         "project.udyam_registered": True, "project.sells_within_maharashtra": True}
VOLT = {"project.industry": "AUTOMOBILE_EV", "project.location_state": "MAHARASHTRA", "project.msme_classification": "NOT_MSME",
        "project.udyam_registered": False, "project.ev_value_chain_role": "VEHICLE_OEM"}
DECCAN = {"project.industry": "ELECTRONICS_ESDM", "project.location_state": "MAHARASHTRA", "project.msme_classification": "SMALL",
          "project.udyam_registered": True, "project.manufactures_ecms_eligible_product": True, "project.ecms_target_segment": "D",
          "project.sells_within_maharashtra": True}
KONKAN = {"project.industry": "CHEMICALS", "project.location_state": "MAHARASHTRA", "project.msme_classification": "MEDIUM",
          "project.udyam_registered": True, "project.sells_within_maharashtra": True}


def _r(facts):
    out = match_catalogue(CAT, facts, mode="NON_PRODUCTION", as_of=AS_OF)
    return {r["scheme_id"]: r for r in out["results"]}


def test_catalogue_valid_and_new_records_are_draft_unverified_without_verification_metadata():
    assert CAT.errors == []
    for sid in NEW:
        s = CAT.schemes[sid]
        if sid in ("SCH-0005", "SCH-0008", "SCH-0010"):   # promoted in Scheme Verification Batch 1
            assert s["status"] == "ACTIVE" and s["confidence"] == "VERIFIED", sid
            assert s["last_verified"]["verified_by"] == "Hardik Trivedi" and str(s["last_verified"]["date"]) == "2026-09-26", sid
            continue
        assert s["status"] == "DRAFT" and s["confidence"] == "UNVERIFIED", sid
        assert "last_verified" not in s, sid
        assert "SOURCE_STATE=NOT_ARCHIVED" in " ".join(s["notes"].split()), sid
    assert "SCH-0003" not in CAT.schemes
    assert [s["scheme_id"] for s in CAT.usable] == ["SCH-0001", "SCH-0002", "SCH-0005", "SCH-0008", "SCH-0010"]


def test_application_status_vocabulary_and_windows():
    exp = {
        "SCH-0005": ("VERIFIED_OPEN", "FIXED_WINDOW", "2027-04-30"),
        "SCH-0006": ("UNRESOLVED_CURRENT_STATUS", "UNKNOWN", None),
        "SCH-0007": ("UNRESOLVED_CURRENT_STATUS", "UNKNOWN", None),
        "SCH-0008": ("VERIFIED_OPEN", "CONTINUOUS", None),
        "SCH-0009": ("NO_CURRENT_WINDOW", "PERIODIC_EOI", None),
        "SCH-0010": ("SELECTION_COMPLETED", "SELECTION_COMPLETED", None),
    }
    for sid, (status, mode, closes) in exp.items():
        s = CAT.schemes[sid]
        assert s["application_status"] == status and s["application_window"]["mode"] == mode, sid
        assert str(s["application_window"].get("closes") or "") == (closes or ""), sid
        # SCH-0005/0008/0010 were re-checked against archived official artifacts in Scheme Verification Batch 1.
        expected_asof = "2026-09-26" if sid in ("SCH-0005", "SCH-0008", "SCH-0010") else "2026-09-22"
        assert str(s["application_window"]["as_of_date"]) == expected_asof, sid


def test_showcase_acceptance_outcomes():
    assert _r(DECCAN)["SCH-0005"]["outcome"] == "POTENTIALLY_ELIGIBLE"
    assert _r(DECCAN)["SCH-0005"]["application_status"] == "VERIFIED_OPEN"
    assert _r(VOLT)["SCH-0006"]["outcome"] == "POTENTIALLY_ELIGIBLE"
    assert _r(VOLT)["SCH-0006"]["application_status"] == "UNRESOLVED_CURRENT_STATUS"
    assert _r(AARAV)["SCH-0010"]["outcome"] == "POTENTIALLY_ELIGIBLE"
    assert _r(AARAV)["SCH-0010"]["application_status"] == "SELECTION_COMPLETED"
    pmksy = _r(SWAAD)["SCH-0009"]
    assert pmksy["outcome"] == "NEEDS_INFORMATION" and pmksy["application_status"] == "NO_CURRENT_WINDOW"
    assert pmksy["missing_facts"] == ["project.is_expansion", "project.is_new_unit"]
    k = _r(KONKAN)
    assert k["SCH-0007"]["outcome"] == "POTENTIALLY_ELIGIBLE" and k["SCH-0008"]["outcome"] == "POTENTIALLY_ELIGIBLE"
    assert k["SCH-0002"]["outcome"] == "NOT_ELIGIBLE"


def test_eligibility_and_application_status_stay_independent():
    # Eligible-but-closed and ineligible-but-open both occur; neither dimension moves the other.
    assert _r(AARAV)["SCH-0010"]["outcome"] == "POTENTIALLY_ELIGIBLE"   # selection completed
    assert _r(VOLT)["SCH-0008"]["outcome"] == "NOT_ELIGIBLE" and _r(VOLT)["SCH-0008"]["application_status"] == "VERIFIED_OPEN"


def test_unknown_facts_are_not_invented_as_negative():
    # No explicit false facts: an unrelated project asking about ECMS-D / MH EV gets NEEDS_INFORMATION, not NOT_ELIGIBLE.
    assert _r(AARAV)["SCH-0005"]["outcome"] == "NEEDS_INFORMATION"
    assert _r(KONKAN)["SCH-0006"]["outcome"] == "NEEDS_INFORMATION"
    # Kleene: a known-false sector gate still decides.
    assert _r(AARAV)["SCH-0009"]["outcome"] == "NOT_ELIGIBLE"


def test_scope_only_and_unencoded_limitations_are_explicit_in_the_explanation():
    why = " ".join(w["description"] for w in _r(AARAV)["SCH-0010"]["why"])
    assert "SCOPE-LEVEL ONLY" in why and "NOT evaluated" in why
    why5 = " ".join(w["description"] for w in _r(DECCAN)["SCH-0005"]["why"]) + CAT.conditions["SCHC-0008"]["description"]
    assert "NOT ENCODED OR EVALUATED" in why5
    assert "NOT EVALUATED" in CAT.conditions["SCHC-0018"]["description"]


def test_existing_records_unchanged():
    assert _r(DECCAN)["SCH-0002"]["outcome"] == "POTENTIALLY_ELIGIBLE"
    assert _r(AARAV)["SCH-0002"]["outcome"] == "NOT_ELIGIBLE"
    assert _r(VOLT)["SCH-0002"]["outcome"] == "NOT_ELIGIBLE"
    assert _r(SWAAD)["SCH-0002"]["outcome"] == "NEEDS_INFORMATION"

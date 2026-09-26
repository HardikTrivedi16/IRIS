"""Scheme Verification Batch 1 (2026-09-26): SCH-0001/0005/0008/0010 are ACTIVE + VERIFIED for a LIMITED ENCODED
SCOPE; SCH-0004 stays blocked. Approved showcase facts are simulated in memory - no Supabase."""
import datetime as dt
import os

import pytest

from app.engine_service import BACKEND_DIR
from app.schemes import load_catalogue, match_catalogue

AS_OF = dt.date(2026, 9, 26)
CAT = load_catalogue(os.path.join(BACKEND_DIR, "scheme-data"))
PROMOTED = ["SCH-0001", "SCH-0005", "SCH-0008", "SCH-0010"]
VERIFIED = ["SCH-0001", "SCH-0002", "SCH-0005", "SCH-0008", "SCH-0010"]
STILL_DRAFT = ["SCH-0004", "SCH-0006", "SCH-0007", "SCH-0009"]

SWAAD = {"project.industry": "FOOD", "project.location_state": "MAHARASHTRA", "project.annual_turnover_inr": 400000000}
AARAV = {"project.industry": "PHARMACEUTICAL", "project.location_state": "MAHARASHTRA", "project.msme_classification": "MEDIUM",
         "project.udyam_registered": True}
VOLT = {"project.industry": "AUTOMOBILE_EV", "project.location_state": "MAHARASHTRA", "project.msme_classification": "NOT_MSME",
        "project.udyam_registered": False}
DECCAN = {"project.industry": "ELECTRONICS_ESDM", "project.location_state": "MAHARASHTRA", "project.msme_classification": "SMALL",
          "project.udyam_registered": True, "project.manufactures_ecms_eligible_product": True, "project.ecms_target_segment": "D"}
KONKAN = {"project.industry": "CHEMICALS", "project.location_state": "MAHARASHTRA", "project.msme_classification": "MEDIUM",
          "project.udyam_registered": True}


def prod(facts):
    out = match_catalogue(CAT, facts, mode="PRODUCTION", as_of=AS_OF)
    assert out["catalogue_state"] == "READY"
    return {r["scheme_id"]: r for r in out["results"]}


def test_verified_catalogue_contains_exactly_the_five_schemes():
    assert CAT.errors == []
    assert [s["scheme_id"] for s in CAT.usable] == VERIFIED
    for sid in PROMOTED:
        s = CAT.schemes[sid]
        assert s["status"] == "ACTIVE" and s["confidence"] == "VERIFIED"
        assert s["last_verified"]["verified_by"] == "Hardik Trivedi" and str(s["last_verified"]["date"]) == "2026-09-26"


def test_blocked_schemes_are_unavailable_in_production_but_present_in_diagnostic():
    assert set(prod(AARAV)) == set(VERIFIED)
    diag = match_catalogue(CAT, AARAV, mode="NON_PRODUCTION", as_of=AS_OF)
    ids = {r["scheme_id"] for r in diag["results"]}
    assert set(STILL_DRAFT) <= ids and set(VERIFIED) <= ids     # Diagnostic catalogue remains functional
    for sid in STILL_DRAFT:
        assert CAT.schemes[sid]["status"] == "DRAFT" and CAT.schemes[sid]["confidence"] == "UNVERIFIED"


def test_sch0004_is_blocked_and_carries_the_blocker():
    s = CAT.schemes["SCH-0004"]
    assert s["status"] == "DRAFT" and "last_verified" not in s
    notes = " ".join(s["notes"].split())
    assert "BLOCKED" in notes and "FIXED CAPITAL INVESTMENT" in notes and "30%" in notes


def test_zed_matches_at_scope_level_but_application_status_stays_unresolved():
    r = prod(DECCAN)["SCH-0001"]
    assert r["outcome"] == "POTENTIALLY_ELIGIBLE"
    assert r["application_status"] == "UNRESOLVED_CURRENT_STATUS"
    assert CAT.schemes["SCH-0001"]["application_window"]["mode"] == "UNKNOWN"
    assert CAT.schemes["SCH-0001"].get("effective_end_date") is None
    assert prod(VOLT)["SCH-0001"]["outcome"] == "NOT_ELIGIBLE"
    assert prod(SWAAD)["SCH-0001"]["outcome"] == "NEEDS_INFORMATION"


def test_ecms_deccan_potentially_eligible_and_window_open_through_2027_04_30():
    r = prod(DECCAN)["SCH-0005"]
    assert r["outcome"] == "POTENTIALLY_ELIGIBLE" and r["application_status"] == "VERIFIED_OPEN"
    w = CAT.schemes["SCH-0005"]["application_window"]
    assert w["mode"] == "FIXED_WINDOW" and str(w["closes"]) == "2027-04-30" and w["opens"] is None
    assert prod(AARAV)["SCH-0005"]["outcome"] == "NEEDS_INFORMATION"   # unknown facts are not invented as negative


def test_mcgs_scope_level_match_does_not_imply_guarantee_approval():
    r = prod(KONKAN)["SCH-0008"]
    assert r["outcome"] == "POTENTIALLY_ELIGIBLE" and r["application_status"] == "VERIFIED_OPEN"
    assert r["outcome"] not in ("ELIGIBLE", "APPROVED", "GUARANTEED")
    notes = " ".join(CAT.schemes["SCH-0008"]["notes"].split())
    for phrase in ("NPA status", "60% of project cost", "Rs. 100 crore ceiling", "lender participation", "cap exhaustion"):
        assert phrase in notes, phrase
    assert prod(VOLT)["SCH-0008"]["outcome"] == "NOT_ELIGIBLE"


def test_pli_pharma_is_scope_level_only_and_selection_completed():
    r = prod(AARAV)["SCH-0010"]
    assert r["outcome"] == "POTENTIALLY_ELIGIBLE" and r["application_status"] == "SELECTION_COMPLETED"
    assert CAT.schemes["SCH-0010"]["application_window"]["mode"] == "SELECTION_COMPLETED"
    notes = " ".join(CAT.schemes["SCH-0010"]["notes"].split())
    assert "no project is implied to be one of the 55" in notes
    for facts in (SWAAD, VOLT, DECCAN, KONKAN):
        assert prod(facts)["SCH-0010"]["outcome"] == "NOT_ELIGIBLE"


def test_eligibility_and_application_status_are_independent():
    aarav, volt = prod(AARAV), prod(VOLT)
    assert aarav["SCH-0010"]["outcome"] == "POTENTIALLY_ELIGIBLE" and aarav["SCH-0010"]["application_status"] == "SELECTION_COMPLETED"
    assert volt["SCH-0008"]["outcome"] == "NOT_ELIGIBLE" and volt["SCH-0008"]["application_status"] == "VERIFIED_OPEN"
    assert aarav["SCH-0001"]["outcome"] == "POTENTIALLY_ELIGIBLE" and aarav["SCH-0001"]["application_status"] == "UNRESOLVED_CURRENT_STATUS"


@pytest.mark.parametrize("sid, must_not_be", [("SCH-0001", "VERIFIED_OPEN"), ("SCH-0010", "VERIFIED_OPEN")])
def test_no_open_claim_for_unresolved_or_completed_schemes(sid, must_not_be):
    assert CAT.schemes[sid]["application_status"] != must_not_be


def test_archive_metadata_claims_match_the_files():
    import hashlib
    import re
    root = os.path.join(os.path.dirname(BACKEND_DIR), "reference-data", "scheme-evidence")
    for folder in ("SRC-SCH-005", "SRC-SCH-008", "SRC-SCH-014", "SRC-SCH-018"):
        manifest = open(os.path.join(root, folder, "MANIFEST.md"), encoding="utf8").read()
        actual = {hashlib.sha256(open(os.path.join(root, folder, f), "rb").read()).hexdigest()
                  for f in os.listdir(os.path.join(root, folder)) if f != "MANIFEST.md"}
        listed = set(re.findall(r"`([0-9a-f]{64})`", manifest))
        assert listed <= actual and listed, folder
    # the JavaScript-rendered NCGTC product page is cited, never claimed as archived
    assert "not archived" in open(os.path.join(root, "SRC-SCH-008", "MANIFEST.md"), encoding="utf8").read() or \
        "cited by URL" in open(os.path.join(root, "SRC-SCH-008", "MANIFEST.md"), encoding="utf8").read()

"""Evidence Consistency wording: document.* facts are labelled legacy ONLY when legacy_evidence.json explicitly says so."""
from app.consistency import project_record_observations
from app.legacy_evidence import legacy_document_facts_info

FACTS = {"document.location": "Plot 18, Haridwar, Uttarakhand", "document.business_name": "SwaadHarvest Foods Pvt Ltd"}


def test_explicitly_declared_project_gets_legacy_label_and_values_are_untouched():
    obs = project_record_observations(FACTS, "92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4")
    assert {o["field"] for o in obs} == {"address", "entity_name"}
    for o in obs:
        assert o["source"]["kind"] == "PROJECT_RECORD"
        assert o["source"]["document_name"].startswith("Legacy confirmed document record")
        assert o["source"]["legacy_evidence"]["label"] == o["source"]["document_name"]
    assert {o["value"] for o in obs} == set(FACTS.values())


def test_not_inferred_from_location_mismatch_or_missing_metadata():
    for pid in (None, "freshbite", "voltedge-mobility", "not-a-project"):
        assert legacy_document_facts_info(pid) is None
        for o in project_record_observations(FACTS, pid):
            assert o["source"]["document_name"] == "Confirmed project record" and "legacy_evidence" not in o["source"]
    # no project id at all keeps the previous behaviour exactly
    assert all(o["source"]["document_name"] == "Confirmed project record" for o in project_record_observations(FACTS))

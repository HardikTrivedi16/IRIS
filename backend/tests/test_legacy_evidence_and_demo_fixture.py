"""Legacy-evidence presentation adapter + SwaadHarvest consistency demo fixture."""
import json
import os

from app import legacy_evidence as le

SW = "92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4"
# The PACKAGED runtime fixture (the file the backend actually reads).
FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "demo-data", "swaadharvest_consistency_observations.json",
)


def test_only_explicitly_named_documents_are_legacy():
    named = {"name": "GST", "storage_path": "reference-data/swaadharvest-evidence/documents/FOOD-ENT-003.pdf"}
    # same look-alike path prefix / Haridwar text but NOT named in the metadata -> not legacy
    lookalike = {"name": "Haridwar doc", "storage_path": "reference-data/swaadharvest-evidence/documents/FOOD-ENT-999.pdf"}
    out = le.annotate_documents(SW, [named, lookalike])
    assert out[0]["legacy_evidence"]["label"] == le.LABEL
    assert "legacy_evidence" not in out[1]


def test_aarav_documents_match_by_external_id_only():
    assert le.is_legacy_document("aarav-lifesciences", {"external_document_id": "DOC-REG-001"})
    assert not le.is_legacy_document("aarav-lifesciences", {"external_document_id": "DOC-NEW-999"})
    assert not le.is_legacy_document("voltedge-mobility", {"external_document_id": "DOC-REG-001"})


def test_metadata_rows_for_legacy_documents_are_recognised():
    assert le.is_legacy_metadata_row("aarav-lifesciences", {"document_id": "DOC-FAC-001"})
    assert not le.is_legacy_metadata_row("aarav-lifesciences", {"document_id": "OTHER"})


def test_fixture_contains_observations_only_no_predetermined_results():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    text = json.dumps(fx["observations"]).upper()
    for forbidden in ("CONFLICT", "REVIEW_REQUIRED", "EXPIRED", "CONSISTENT", "\"STATUS\""):
        assert forbidden not in text
    assert all("confidence" not in o for o in fx["observations"])  # not live-extracted
    assert not any(k in o for o in fx["observations"] for k in ("status", "result", "expected", "expected_status"))
    from app.routers import consistency as router_mod
    assert os.path.abspath(router_mod._DEMO_FIXTURE) == os.path.abspath(FIXTURE)
    assert {o["field"] for o in fx["observations"]} == {"entity_name", "address", "net_quantity", "valid_until"}

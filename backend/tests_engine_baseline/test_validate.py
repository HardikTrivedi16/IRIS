import os

from iris_engine.validate import validate_dataset

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regulatory-data")


def test_dataset_validates_cleanly(dataset):
    report = validate_dataset(DATA_ROOT, dataset)
    assert report.yaml_parse_errors == [], report.yaml_parse_errors
    assert report.duplicate_ids == [], report.duplicate_ids
    assert report.broken_references == [], report.broken_references
    assert report.status_violations == [], report.status_violations
    assert report.index_count_mismatches == [], report.index_count_mismatches
    assert report.passed


def test_44_files_inspected(dataset):
    # 38 Phase 5/6 files + 6 provenance substrate index files added in
    # Tranche 1 (authorities/instruments/sources/evidence/facts/
    # verifications _index.yaml — all currently empty; see
    # regulatory-data/index/*_index.yaml and docs/REGULATORY_PACK_INPUT_
    # REQUIREMENTS.md). The six new record-type directories themselves
    # contain only a README.md each, which this *.yaml glob does not count.
    report = validate_dataset(DATA_ROOT, dataset)
    assert len(report.files_inspected) == 44


def test_broken_reference_is_detected(dataset):
    # sanity check the validator actually catches something, not just a
    # vacuously-empty check — inject a dangling reference and confirm it
    # is flagged, then restore.
    original = dataset.conditions["COND-0001"].get("child_condition_ids")
    dataset.conditions["COND-0001"]["child_condition_ids"] = ["COND-DOES-NOT-EXIST"]
    try:
        report = validate_dataset(DATA_ROOT, dataset)
        assert any("COND-DOES-NOT-EXIST" in b for b in report.broken_references)
    finally:
        dataset.conditions["COND-0001"]["child_condition_ids"] = original

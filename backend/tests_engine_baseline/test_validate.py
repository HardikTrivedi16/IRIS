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


def test_163_files_inspected(dataset):
    # 38 Phase 5/6 files + 6 provenance substrate index files (Tranche 1) +
    # 50 provenance records (8 AUTH + 8 INST + 8 SRC + 13 EVID + 13 RF) +
    # 50 new regulatory objects (8 REQUIREMENT + 9 RULE + 9 RULE-VERSION +
    # 24 CONDITION) added by the Shared+Food regulatory-data integration
    # pass (SH-03/04/05/07/08/10, FD-01/02/04) = 144, + 2 SRC records
    # (SRC-011, SRC-012) added by the FD-01/FD-02 source-archival pass
    # (2026-09-23) = 146, + 17 records added by the FD-01/FD-02
    # currentness-correction pass (2026-09-23): 2 EVID (FSS-07/08) + 3 RF
    # (0022-0024) + 7 CONDITION (0039-0045) + 2 RULE-VERSION (RULE-0014-V2,
    # RULE-0015-V2) + 1 REQUIREMENT (REQ-0013) + 1 RULE (RULE-0016) + 1
    # RULE-VERSION (RULE-0016-V1) = 163. See regulatory-data/index/
    # *_index.yaml and regulatory-data/registers/rule_review_register.yaml
    # RULE-REV-0006.
    report = validate_dataset(DATA_ROOT, dataset)
    assert len(report.files_inspected) == 163


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

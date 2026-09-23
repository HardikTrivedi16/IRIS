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


def test_210_files_inspected(dataset):
    # 144 (Shared+Food) + 2 SRC (FD-01/FD-02 archival pass) = 146 +
    # 17 (FD-01/FD-02 currentness-correction pass, RULE-REV-0006) = 163,
    # + 47 records added by the Pharma tranche (2026-09-23,
    # RULE-REV-0002): 3 AUTH (FDA-MH, CDSCO, SEIAA-MH) + 2 INST
    # (DRUGS-RULES-1945, EIA-2006) + 2 SRC (013, 014) + 4 EVID (DRUGS-
    # 01..04) + 4 RF (0025..0028) + 16 CONDITION (0046..0061) +
    # 2 REQUIREMENT (0014 PH-04, 0015 PH-05) + 7 RULE (0017..0023) +
    # 7 RULE-VERSION (each new rule's -V1) = 210. See
    # regulatory-data/index/*_index.yaml and
    # regulatory-data/registers/rule_review_register.yaml RULE-REV-0002.
    report = validate_dataset(DATA_ROOT, dataset)
    assert len(report.files_inspected) == 210


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

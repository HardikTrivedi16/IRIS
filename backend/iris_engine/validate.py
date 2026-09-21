"""
Programmatic dataset validation (Phase 7 §11).

Checks performed against the ACTUAL parsed files (not copied from Phase 6's
FINAL_AUDIT.md claims — those are cross-checked here, not assumed):
  * YAML parses for every file under regulatory-data/
  * no duplicate IDs within each record type
  * child_condition_ids / condition_expression_root_id resolve to real COND-###
  * evaluated_by_rule_id / classification_rule_ids resolve to real RULE-###
  * rule_id on a RULEV resolves to a real RULE-###
  * conflict register involved_rules / involved_rule_versions / involved_conditions resolve
  * dependency index edges (if any) resolve to real REQ-###
  * status fields are within the known enumeration
  * index file counts match actual on-disk counts

This module does NOT alter any regulatory data — it only reports.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import yaml

KNOWN_RULE_VERSION_STATUSES = {"DRAFT", "ACTIVE", "SUPERSEDED", "RETIRED"}


@dataclass
class ValidationReport:
    files_inspected: list = field(default_factory=list)
    yaml_parse_errors: list = field(default_factory=list)
    duplicate_ids: list = field(default_factory=list)
    broken_references: list = field(default_factory=list)
    status_violations: list = field(default_factory=list)
    index_count_mismatches: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (
            self.yaml_parse_errors
            or self.duplicate_ids
            or self.broken_references
            or self.status_violations
            or self.index_count_mismatches
        )


def _check_duplicate_ids(id_key: str, files: list, report: ValidationReport, label: str):
    seen = {}
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            try:
                doc = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                report.yaml_parse_errors.append(f"{fp}: {exc}")
                continue
        if not doc or id_key not in doc:
            continue
        rid = doc[id_key]
        if rid in seen:
            report.duplicate_ids.append(f"{label} duplicate id {rid!r}: {seen[rid]} and {fp}")
        else:
            seen[rid] = fp


def validate_dataset(root: str, dataset) -> ValidationReport:
    report = ValidationReport()
    report.files_inspected = sorted(glob.glob(os.path.join(root, "**", "*.yaml"), recursive=True))

    # --- YAML parse (re-parse everything independently of the loader) -------
    for fp in report.files_inspected:
        with open(fp, "r", encoding="utf-8") as f:
            try:
                yaml.safe_load(f)
            except yaml.YAMLError as exc:
                report.yaml_parse_errors.append(f"{fp}: {exc}")

    # --- duplicate IDs --------------------------------------------------------
    _check_duplicate_ids("condition_id", glob.glob(os.path.join(root, "conditions", "*.yaml")), report, "COND")
    _check_duplicate_ids("rule_id", glob.glob(os.path.join(root, "rules", "*.yaml")), report, "RULE")
    _check_duplicate_ids("rule_version_id", glob.glob(os.path.join(root, "rule-versions", "*.yaml")), report, "RULEV")
    _check_duplicate_ids("requirement_id", glob.glob(os.path.join(root, "requirements", "*.yaml")), report, "REQ")

    conflict_ids = [c.get("conflict_id") for c in dataset.rule_conflict_register.get("conflicts", [])]
    dup_conflicts = {c for c in conflict_ids if conflict_ids.count(c) > 1}
    for c in dup_conflicts:
        report.duplicate_ids.append(f"conflict register duplicate conflict_id {c!r}")

    rule_review_ids = [r.get("review_id") for r in dataset.rule_review_register.get("review_items", [])]
    dup_rr = {r for r in rule_review_ids if rule_review_ids.count(r) > 1}
    for r in dup_rr:
        report.duplicate_ids.append(f"rule review register duplicate review_id {r!r}")

    dep_review_ids = [r.get("review_id") for r in dataset.dependency_review_register.get("review_items", [])]
    dup_dr = {r for r in dep_review_ids if dep_review_ids.count(r) > 1}
    for r in dup_dr:
        report.duplicate_ids.append(f"dependency review register duplicate review_id {r!r}")

    # --- broken references -----------------------------------------------------
    cond_ids = set(dataset.conditions.keys())
    rule_ids = set(dataset.rules.keys())
    rulev_ids = set(dataset.rule_versions.keys())
    req_ids = set(dataset.requirements.keys())

    for cid, cond in dataset.conditions.items():
        for child in cond.get("child_condition_ids") or []:
            if child not in cond_ids:
                report.broken_references.append(f"{cid}.child_condition_ids -> missing {child}")

    for rvid, rv in dataset.rule_versions.items():
        root_cond = rv.get("condition_expression_root_id")
        if root_cond and root_cond not in cond_ids:
            report.broken_references.append(f"{rvid}.condition_expression_root_id -> missing {root_cond}")
        rid = rv.get("rule_id")
        if rid and rid not in rule_ids:
            report.broken_references.append(f"{rvid}.rule_id -> missing {rid}")
        status = rv.get("status")
        if status and status not in KNOWN_RULE_VERSION_STATUSES:
            report.status_violations.append(f"{rvid}.status={status!r} not in {KNOWN_RULE_VERSION_STATUSES}")
        for kc in rv.get("known_conflicts") or []:
            cid = kc.get("conflict_id")
            if cid and cid not in {c.get("conflict_id") for c in dataset.rule_conflict_register.get("conflicts", [])}:
                report.broken_references.append(f"{rvid}.known_conflicts -> missing conflict {cid}")

    for rid, rule in dataset.rules.items():
        req_ref = rule.get("requirement_id")
        if req_ref and req_ref not in req_ids:
            report.broken_references.append(f"{rid}.requirement_id -> missing {req_ref}")

    for reqid, req in dataset.requirements.items():
        erb = req.get("evaluated_by_rule_id")
        if erb and erb not in rule_ids:
            report.broken_references.append(f"{reqid}.evaluated_by_rule_id -> missing {erb}")
        for crid in req.get("classification_rule_ids") or []:
            if crid not in rule_ids:
                report.broken_references.append(f"{reqid}.classification_rule_ids -> missing {crid}")
        for kc in req.get("known_conflicts") or []:
            if kc not in {c.get("conflict_id") for c in dataset.rule_conflict_register.get("conflicts", [])}:
                report.broken_references.append(f"{reqid}.known_conflicts -> missing conflict {kc}")

    for c in dataset.rule_conflict_register.get("conflicts", []):
        for rid in c.get("involved_rules", []):
            if rid not in rule_ids:
                report.broken_references.append(f"conflict {c.get('conflict_id')}.involved_rules -> missing {rid}")
        for rvid in c.get("involved_rule_versions", []):
            if rvid not in rulev_ids:
                report.broken_references.append(f"conflict {c.get('conflict_id')}.involved_rule_versions -> missing {rvid}")
        for condid in c.get("involved_conditions", []):
            if condid not in cond_ids:
                report.broken_references.append(f"conflict {c.get('conflict_id')}.involved_conditions -> missing {condid}")

    # dependency index edges
    for e in dataset.dependencies_index.get("dependencies", []) or []:
        for key in ("from_requirement_id", "to_requirement_id"):
            rid = e.get(key)
            if rid and rid not in req_ids:
                report.broken_references.append(f"dependency edge {e} -> missing requirement {rid} ({key})")

    # --- index count consistency ------------------------------------------------
    idx_counts = dataset.conditions_index.get("counts", {})
    if "total_conditions" in idx_counts and idx_counts["total_conditions"] != len(dataset.conditions):
        report.index_count_mismatches.append(
            f"conditions_index.total_conditions={idx_counts['total_conditions']} != actual {len(dataset.conditions)}"
        )

    idx_rules_counts = dataset.rules_index.get("counts", {})
    if "total_rules" in idx_rules_counts and idx_rules_counts["total_rules"] != len(dataset.rules):
        report.index_count_mismatches.append(
            f"rules_index.total_rules={idx_rules_counts['total_rules']} != actual {len(dataset.rules)}"
        )
    if "total_rule_versions" in idx_rules_counts and idx_rules_counts["total_rule_versions"] != len(dataset.rule_versions):
        report.index_count_mismatches.append(
            f"rules_index.total_rule_versions={idx_rules_counts['total_rule_versions']} != actual {len(dataset.rule_versions)}"
        )

    idx_req_counts = dataset.requirements_index.get("counts", {})
    if "total_requirements" in idx_req_counts and idx_req_counts["total_requirements"] != len(dataset.requirements):
        report.index_count_mismatches.append(
            f"requirements_index.total_requirements={idx_req_counts['total_requirements']} != actual {len(dataset.requirements)}"
        )

    idx_dep_counts = dataset.dependencies_index.get("counts", {})
    actual_deps = len(dataset.dependencies_index.get("dependencies", []) or [])
    if "total_dependencies" in idx_dep_counts and idx_dep_counts["total_dependencies"] != actual_deps:
        report.index_count_mismatches.append(
            f"dependencies_index.total_dependencies={idx_dep_counts['total_dependencies']} != actual {actual_deps}"
        )

    return report

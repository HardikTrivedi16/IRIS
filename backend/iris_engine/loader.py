"""
Loads the frozen Phase 5/6 regulatory-data package (+ Phase 2 schema context)
from disk into plain in-memory dicts, keyed by ID.

This module does NOT interpret regulatory meaning. It only parses YAML and
indexes records by their declared *_id field. Phase 7 §1 "inspect first" /
§11 "validation" both depend on this being a faithful, non-interpretive
loader.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import yaml


def _load_yaml_dir(path: str) -> dict:
    """Load every *.yaml file in a directory into {id: doc}, using whichever
    of the plausible *_id keys is present in the document."""
    out = {}
    id_keys = (
        "condition_id", "rule_version_id", "rule_id", "requirement_id",
        "dependency_id",
    )
    for fp in sorted(glob.glob(os.path.join(path, "*.yaml"))):
        with open(fp, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        if doc is None:
            continue
        rec_id = None
        for k in id_keys:
            if k in doc:
                rec_id = doc[k]
                break
        if rec_id is None:
            # fall back to filename stem
            rec_id = os.path.splitext(os.path.basename(fp))[0]
        out[rec_id] = {"_source_file": fp, **doc}
    return out


def _load_yaml_file(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class RegulatoryDataset:
    root: str
    conditions: dict = field(default_factory=dict)
    rules: dict = field(default_factory=dict)
    rule_versions: dict = field(default_factory=dict)
    requirements: dict = field(default_factory=dict)
    dependencies: dict = field(default_factory=dict)

    conditions_index: dict = field(default_factory=dict)
    rules_index: dict = field(default_factory=dict)
    requirements_index: dict = field(default_factory=dict)
    dependencies_index: dict = field(default_factory=dict)

    rule_conflict_register: dict = field(default_factory=dict)
    rule_review_register: dict = field(default_factory=dict)
    dependency_conflict_register: dict = field(default_factory=dict)
    dependency_review_register: dict = field(default_factory=dict)

    all_files: list = field(default_factory=list)

    @classmethod
    def load(cls, root: str) -> "RegulatoryDataset":
        ds = cls(root=root)
        ds.conditions = _load_yaml_dir(os.path.join(root, "conditions"))
        ds.rules = _load_yaml_dir(os.path.join(root, "rules"))
        ds.rule_versions = _load_yaml_dir(os.path.join(root, "rule-versions"))
        ds.requirements = _load_yaml_dir(os.path.join(root, "requirements"))
        ds.dependencies = _load_yaml_dir(os.path.join(root, "dependencies"))

        ds.conditions_index = _load_yaml_file(
            os.path.join(root, "index", "conditions_index.yaml")) or {}
        ds.rules_index = _load_yaml_file(
            os.path.join(root, "index", "rules_index.yaml")) or {}
        ds.requirements_index = _load_yaml_file(
            os.path.join(root, "index", "requirements_index.yaml")) or {}
        ds.dependencies_index = _load_yaml_file(
            os.path.join(root, "index", "dependencies_index.yaml")) or {}

        ds.rule_conflict_register = _load_yaml_file(
            os.path.join(root, "registers", "rule_conflict_register.yaml")) or {}
        ds.rule_review_register = _load_yaml_file(
            os.path.join(root, "registers", "rule_review_register.yaml")) or {}
        ds.dependency_conflict_register = _load_yaml_file(
            os.path.join(root, "registers", "dependency_conflict_register.yaml")) or {}
        ds.dependency_review_register = _load_yaml_file(
            os.path.join(root, "registers", "dependency_review_register.yaml")) or {}

        ds.all_files = sorted(
            glob.glob(os.path.join(root, "**", "*.yaml"), recursive=True)
        )
        return ds

    # --- convenience lookups -------------------------------------------------

    def rule_versions_for_rule(self, rule_id: str):
        return [
            rv for rv in self.rule_versions.values() if rv.get("rule_id") == rule_id
        ]

    def latest_rule_version_id(self, rule_id: str):
        """Uses rules_index.yaml's declared latest_rule_version_id — does not
        guess or infer; if the index doesn't say, returns None."""
        for r in self.rules_index.get("rules", []):
            if r.get("rule_id") == rule_id:
                return r.get("latest_rule_version_id")
        return None

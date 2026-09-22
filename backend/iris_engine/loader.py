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
    of the plausible *_id keys is present in the document.

    Order matters: the FIRST key in ``id_keys`` present in a document wins.
    A document's own true id must always be checked before any *foreign*
    key it also happens to carry, or that document gets keyed by the wrong
    id. The original five (``condition_id``..``dependency_id``) never
    collide with each other or with the six provenance keys, because every
    existing record type's own id is checked before any of the six
    (e.g. a Rule Version's ``rule_version_id`` wins over its own
    ``authority_id``/``instrument_id`` fields). Within the six provenance
    keys, two real collisions exist and are ordered deliberately:
    ``regulatory_fact_id`` before ``authority_id``/``instrument_id`` (an RF
    record carries both its own id and those two as foreign keys), and
    ``evidence_id`` before ``source_id`` (an Evidence record carries both
    its own id and a ``source_id`` foreign key). Do not reorder this
    tuple without re-checking every record type for this kind of collision."""
    out = {}
    id_keys = (
        "condition_id", "rule_version_id", "rule_id", "requirement_id",
        "dependency_id",
        "evidence_id", "regulatory_fact_id", "verification_id",
        "authority_id", "instrument_id", "source_id",
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

    # Provenance substrate (Tranche 1). Directories may be empty — that is
    # the correct, honest state until verified regulatory research is
    # integrated. See docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md.
    authorities: dict = field(default_factory=dict)
    instruments: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    verifications: dict = field(default_factory=dict)

    conditions_index: dict = field(default_factory=dict)
    rules_index: dict = field(default_factory=dict)
    requirements_index: dict = field(default_factory=dict)
    dependencies_index: dict = field(default_factory=dict)

    authorities_index: dict = field(default_factory=dict)
    instruments_index: dict = field(default_factory=dict)
    sources_index: dict = field(default_factory=dict)
    evidence_index: dict = field(default_factory=dict)
    facts_index: dict = field(default_factory=dict)
    verifications_index: dict = field(default_factory=dict)

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

        ds.authorities = _load_yaml_dir(os.path.join(root, "authorities"))
        ds.instruments = _load_yaml_dir(os.path.join(root, "instruments"))
        ds.sources = _load_yaml_dir(os.path.join(root, "sources"))
        ds.evidence = _load_yaml_dir(os.path.join(root, "evidence"))
        ds.facts = _load_yaml_dir(os.path.join(root, "facts"))
        ds.verifications = _load_yaml_dir(os.path.join(root, "verifications"))

        ds.conditions_index = _load_yaml_file(
            os.path.join(root, "index", "conditions_index.yaml")) or {}
        ds.rules_index = _load_yaml_file(
            os.path.join(root, "index", "rules_index.yaml")) or {}
        ds.requirements_index = _load_yaml_file(
            os.path.join(root, "index", "requirements_index.yaml")) or {}
        ds.dependencies_index = _load_yaml_file(
            os.path.join(root, "index", "dependencies_index.yaml")) or {}

        ds.authorities_index = _load_yaml_file(
            os.path.join(root, "index", "authorities_index.yaml")) or {}
        ds.instruments_index = _load_yaml_file(
            os.path.join(root, "index", "instruments_index.yaml")) or {}
        ds.sources_index = _load_yaml_file(
            os.path.join(root, "index", "sources_index.yaml")) or {}
        ds.evidence_index = _load_yaml_file(
            os.path.join(root, "index", "evidence_index.yaml")) or {}
        ds.facts_index = _load_yaml_file(
            os.path.join(root, "index", "facts_index.yaml")) or {}
        ds.verifications_index = _load_yaml_file(
            os.path.join(root, "index", "verifications_index.yaml")) or {}

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

"""
Phase 9 Section 18 — regulatory-data immutability.

``phase9_regulatory_data_manifest.json`` is a SHA-256 manifest of every file
in ``regulatory-data/`` taken immediately before Phase 9 implementation work
began, and independently cross-checked against a hash captured at the very
start of this pass (before any file in the repository was touched). This
test pins that manifest permanently: any future change to regulatory-data
-- accidental or otherwise -- will fail this test rather than pass
silently.
"""
import json
import os

from iris_engine.dataset_integrity import hash_tree, diff_hash_trees

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(os.path.dirname(HERE), "regulatory-data")
MANIFEST_PATH = os.path.join(HERE, "phase9_regulatory_data_manifest.json")


def _load_manifest():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def test_regulatory_data_is_byte_identical_to_the_pinned_manifest():
    expected = _load_manifest()
    actual = hash_tree(DATA_ROOT)
    diff = diff_hash_trees(expected, actual)
    assert diff == {"added": [], "removed": [], "changed": []}, diff


def test_manifest_covers_every_expected_regulatory_data_subdirectory():
    manifest = _load_manifest()
    top_level_dirs = {rel.split("/")[0] for rel in manifest}
    for expected_dir in ("conditions", "rules", "rule-versions", "requirements", "registers"):
        assert expected_dir in top_level_dirs
    assert len(manifest) >= 30

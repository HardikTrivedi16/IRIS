"""
Regulatory-data immutability checking (Phase 9 Section 18).

Pure filesystem hashing -- no regulatory interpretation. Used both as a
one-off before/after check during development (see the repo-root
``scripts/check_immutability.py``) and as an ongoing regression guard
(``tests/test_phase9_data_immutability.py`` pins a manifest and asserts the
live ``regulatory-data/`` directory still hashes to it).
"""
from __future__ import annotations

import hashlib
import os


def hash_tree(root: str) -> dict:
    """Returns {relative_path: sha256_hex} for every file under root,
    sorted by relative path."""
    out = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, root).replace(os.sep, "/")
            with open(fp, "rb") as f:
                out[rel] = hashlib.sha256(f.read()).hexdigest()
    return dict(sorted(out.items()))


def diff_hash_trees(before: dict, after: dict) -> dict:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in (set(before) & set(after)) if before[k] != after[k])
    return {"added": added, "removed": removed, "changed": changed}


def is_identical(before: dict, after: dict) -> bool:
    d = diff_hash_trees(before, after)
    return not (d["added"] or d["removed"] or d["changed"])

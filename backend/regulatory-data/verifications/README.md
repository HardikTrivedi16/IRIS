# verifications/

Provenance substrate (Tranche 1). One `VER-####.yaml` human Verification
record per file, loaded by `iris_engine.loader.RegulatoryDataset.load`.

**Intentionally empty.** No Rule Version has been promoted to ACTIVE, so no
Verification record exists yet — and none should be created automatically.

Minimum record shape:

```yaml
verification_id: VER-####
target_type: RULE_VERSION       # RULE_VERSION | REGULATORY_FACT | EVIDENCE | DEPENDENCY_EDGE
target_id: RULE-####-V#         # required, must resolve according to target_type
reviewer: "<full name>"         # required — a real, accountable HUMAN identity
reviewed_at: "2026-09-01"       # required
result: APPROVED                # APPROVED | REJECTED | NEEDS_REVISION
source_checks: [SRC-####]       # sources actually checked, must resolve
evidence_checks: [EVID-####]    # evidence actually checked, must resolve
notes: >                        # optional
  ...
```

**`reviewer` must be a human identity, never an AI/system placeholder.**
This module and `iris_engine.validate` reject obvious automated/placeholder
names (e.g. "AI", "system", "auto", a model name) as a conservative
denylist — they cannot verify a name is a genuine accountable person, so
this is a floor, not a substitute for an actual review process.

**Verification records are never auto-created from AI research output.**
A human must author this record after actually checking the cited sources
and evidence — see `docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md` §4.3.

An ACTIVE Rule Version's dataset validation fails unless an `APPROVED`
Verification record with `target_type: RULE_VERSION` targets its exact
`rule_version_id` (see `iris_engine/validate.py`'s ACTIVE promotion gate).

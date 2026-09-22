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

Provenance substrate (Tranche 1) additions — see
docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md:
  * Authority / Instrument / Source / Evidence / Regulatory Fact (RF) /
    Verification (VER) records: required-field shape, duplicate ids,
    cross-references, index counts.
  * The ACTIVE PROMOTION GATE: a Rule Version whose `status` is ACTIVE must
    have a fully-resolved provenance chain, a temporally-valid instrument,
    and an APPROVED human Verification record targeting it, or it is a hard
    validation failure — never "the string ACTIVE was spelled correctly."
  * DRAFT (and SUPERSEDED/RETIRED) Rule Versions are explicitly EXEMPT from
    that hard gate: an unresolved provenance reference on a non-ACTIVE Rule
    Version is reported as a non-blocking `review_notes` entry, never a
    failure. This is intentional — the six current DRAFT Rule Versions
    already reference RF-####/EVID-####/SRC-####/AUTH-####/INST-#### ids
    that have no materialized record yet, and must remain loadable and
    valid while regulatory research is integrated (Phase 7 "missing data
    ≠ not applicable" extended to "unintegrated provenance ≠ invalid
    dataset").
  * `review_notes` is non-blocking by construction: it is never read by
    `ValidationReport.passed`.

This module does NOT alter any regulatory data — it only reports.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import yaml

KNOWN_RULE_VERSION_STATUSES = {"DRAFT", "ACTIVE", "SUPERSEDED", "RETIRED"}
KNOWN_INSTRUMENT_CURRENCY_STATUSES = {"IN_FORCE", "REPEALED", "TRANSITIONAL", "SUPERSEDED"}
KNOWN_VERIFICATION_TARGET_TYPES = {"RULE_VERSION", "REGULATORY_FACT", "EVIDENCE", "DEPENDENCY_EDGE"}
KNOWN_VERIFICATION_RESULTS = {"APPROVED", "REJECTED", "NEEDS_REVISION"}

# NORMATIVE RULE (contract, not mechanically enforceable): a Verification
# record represents human attestation. AI-generated or automatically
# generated VER records are prohibited, and `reviewer` must identify the
# human who actually performed the verification — see
# docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md §7.3. This module cannot
# determine whether a free-text string names a real human being — there is
# no identity/auth system behind this plain YAML field — so it does not try.
# A denylist of "AI"/"system"/model-name-shaped strings was removed
# deliberately: it rejected legitimate human names that happen to contain
# those substrings and gave a false impression of enforcement this schema
# cannot actually provide. The only thing checked here is presence: a
# non-empty string. Whether that string names a genuine accountable
# reviewer is a human review-process matter, not a validator rule.

_AUTHORITY_REQUIRED = ("authority_id", "name", "level", "jurisdiction")
_INSTRUMENT_REQUIRED = (
    "instrument_id", "short_title", "full_citation", "issuing_authority_id",
    "year", "currency_status", "effective_start_date", "last_currency_check",
)
_SOURCE_REQUIRED = (
    "source_id", "title", "publisher_authority_id", "document_type",
    "official_url", "retrieved_date", "source_status",
)
_EVIDENCE_REQUIRED = (
    "evidence_id", "source_id", "section_or_clause", "excerpt", "verification_status",
)
_FACT_REQUIRED = (
    "regulatory_fact_id", "statement", "evidence_ids", "authority_id",
    "instrument_id", "verification_status",
)
_VERIFICATION_REQUIRED = (
    "verification_id", "target_type", "target_id", "reviewer",
    "reviewed_at", "result", "source_checks", "evidence_checks",
)


@dataclass
class ValidationReport:
    files_inspected: list = field(default_factory=list)
    yaml_parse_errors: list = field(default_factory=list)
    duplicate_ids: list = field(default_factory=list)
    broken_references: list = field(default_factory=list)
    status_violations: list = field(default_factory=list)
    index_count_mismatches: list = field(default_factory=list)
    #: Missing/malformed required fields on a provenance record (Tranche 1).
    #: Hard failure — affects `passed`.
    schema_violations: list = field(default_factory=list)
    #: ACTIVE-promotion-gate failures (Tranche 1, see module docstring).
    #: Hard failure — affects `passed`.
    active_promotion_violations: list = field(default_factory=list)
    #: Non-blocking observations (e.g. a DRAFT rule's unresolved provenance,
    #: a TRANSITIONAL instrument, a bounded historical ACTIVE reference).
    #: Deliberately NOT read by `passed` — see module docstring.
    review_notes: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (
            self.yaml_parse_errors
            or self.duplicate_ids
            or self.broken_references
            or self.status_violations
            or self.index_count_mismatches
            or self.schema_violations
            or self.active_promotion_violations
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


def _check_required_fields(
    records: dict, required: tuple, label: str, report: ValidationReport,
    non_empty_list_fields: tuple = (),
) -> None:
    """Minimum record contract (Tranche 1, REGULATORY_PACK_INPUT_REQUIREMENTS.md
    §4/§5). A field counts as missing if absent, None, or an empty string —
    an empty list is fine unless the field is also named in
    ``non_empty_list_fields`` (e.g. a Regulatory Fact must point to at least
    one Evidence, never merely duplicate an unsourced statement)."""
    for rid, doc in records.items():
        for f in required:
            if f not in doc or doc.get(f) in (None, ""):
                report.schema_violations.append(f"{label} {rid}: missing required field {f!r}")
        for f in non_empty_list_fields:
            val = doc.get(f)
            if f in doc and isinstance(val, list) and len(val) == 0:
                report.schema_violations.append(f"{label} {rid}: {f!r} must not be an empty list")


def _check_verification_records(dataset, report: ValidationReport) -> None:
    """Verification (VER) shape: enum fields, and that `reviewer` is
    present. Whether `reviewer` actually names a human — as the contract
    requires (see module docstring) — is not something a free-text string
    can establish; this only checks presence, not identity. VER records
    are never auto-created by this codebase."""
    rulev_ids = set(dataset.rule_versions.keys())
    fact_ids = set(dataset.facts.keys())
    evidence_ids = set(dataset.evidence.keys())
    dep_ids = {
        e.get("dependency_id") for e in (dataset.dependencies_index.get("dependencies") or [])
    }
    target_dict_by_type = {
        "RULE_VERSION": rulev_ids,
        "REGULATORY_FACT": fact_ids,
        "EVIDENCE": evidence_ids,
        "DEPENDENCY_EDGE": dep_ids,
    }
    source_ids = set(dataset.sources.keys())

    for vid, ver in dataset.verifications.items():
        reviewer = ver.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            report.schema_violations.append(f"VER {vid}: reviewer must be a non-empty string")

        result = ver.get("result")
        if result is not None and result not in KNOWN_VERIFICATION_RESULTS:
            report.status_violations.append(f"VER {vid}.result={result!r} not in {KNOWN_VERIFICATION_RESULTS}")

        ttype = ver.get("target_type")
        if ttype is not None and ttype not in KNOWN_VERIFICATION_TARGET_TYPES:
            report.status_violations.append(f"VER {vid}.target_type={ttype!r} not in {KNOWN_VERIFICATION_TARGET_TYPES}")
        elif ttype in target_dict_by_type:
            tid = ver.get("target_id")
            if tid and tid not in target_dict_by_type[ttype]:
                report.broken_references.append(f"VER {vid}.target_id -> missing {tid} (target_type={ttype})")

        for sid in ver.get("source_checks") or []:
            if sid not in source_ids:
                report.broken_references.append(f"VER {vid}.source_checks -> missing {sid}")
        for eid in ver.get("evidence_checks") or []:
            if eid not in evidence_ids:
                report.broken_references.append(f"VER {vid}.evidence_checks -> missing {eid}")


def _check_provenance_layer_references(dataset, report: ValidationReport) -> None:
    """Cross-references WITHIN the provenance layer itself (Authority ->
    Authority, Instrument -> Authority/Instrument, Source -> Authority,
    Evidence -> Source, RF -> Evidence/Authority/Instrument). These are
    always hard failures, unconditionally — unlike a Rule Version's
    OUTWARD references into this layer (see
    `_check_rule_version_provenance`), a malformed record actually authored
    IN this layer (e.g. an Evidence pointing at a Source that doesn't
    exist) is never something the DRAFT-compatibility carve-out applies to:
    there is no legitimate reason for a newly-authored provenance record to
    reference another provenance record that isn't there."""
    auth_ids = set(dataset.authorities.keys())
    inst_ids = set(dataset.instruments.keys())
    source_ids = set(dataset.sources.keys())
    evidence_ids = set(dataset.evidence.keys())

    for aid, auth in dataset.authorities.items():
        parent = auth.get("parent_authority_id")
        if parent and parent not in auth_ids:
            report.broken_references.append(f"AUTH {aid}.parent_authority_id -> missing {parent}")

    for iid, inst in dataset.instruments.items():
        issuer = inst.get("issuing_authority_id")
        if issuer and issuer not in auth_ids:
            report.broken_references.append(f"INST {iid}.issuing_authority_id -> missing {issuer}")
        sup = inst.get("supersedes_instrument_id")
        if sup and sup not in inst_ids:
            report.broken_references.append(f"INST {iid}.supersedes_instrument_id -> missing {sup}")
        sup_by = inst.get("superseded_by_instrument_id")
        if sup_by and sup_by not in inst_ids:
            report.broken_references.append(f"INST {iid}.superseded_by_instrument_id -> missing {sup_by}")
        currency = inst.get("currency_status")
        if currency and currency not in KNOWN_INSTRUMENT_CURRENCY_STATUSES:
            report.status_violations.append(
                f"INST {iid}.currency_status={currency!r} not in {KNOWN_INSTRUMENT_CURRENCY_STATUSES}"
            )

    for sid, src in dataset.sources.items():
        pub = src.get("publisher_authority_id")
        if pub and pub not in auth_ids:
            report.broken_references.append(f"SRC {sid}.publisher_authority_id -> missing {pub}")

    for eid, ev in dataset.evidence.items():
        src = ev.get("source_id")
        if src and src not in source_ids:
            report.broken_references.append(f"EVID {eid}.source_id -> missing {src}")

    for rfid, rf in dataset.facts.items():
        for evid in rf.get("evidence_ids") or []:
            if evid not in evidence_ids:
                report.broken_references.append(f"RF {rfid}.evidence_ids -> missing {evid}")
        auth = rf.get("authority_id")
        if auth and auth not in auth_ids:
            report.broken_references.append(f"RF {rfid}.authority_id -> missing {auth}")
        inst = rf.get("instrument_id")
        if inst and inst not in inst_ids:
            report.broken_references.append(f"RF {rfid}.instrument_id -> missing {inst}")


def _check_rule_version_provenance(dataset, report: ValidationReport) -> None:
    """Every Rule Version's OUTWARD references into the provenance layer
    (RF, Evidence, Source, Authority, Instrument — including the RF ->
    Evidence -> Source transitive chain), and the Requirement-level
    grounding references.

    Severity depends on the referring Rule Version's `status`:
      * ACTIVE  -> hard failure (`active_promotion_violations`). An ACTIVE
        Rule Version claims to be a current, authoritative production
        answer; it must never claim provenance it cannot actually show.
      * anything else (DRAFT/SUPERSEDED/RETIRED/missing) -> non-blocking
        `review_notes`. This is deliberate (Tranche 1 brief, DRAFT
        compatibility): the six current DRAFT Rule Versions already
        reference RF-####/EVID-####/SRC-####/AUTH-####/INST-#### ids with
        no materialized record yet, and must remain valid and loadable —
        this is the SAME "missing data ≠ invalid" principle the engine
        already applies to missing Project Facts, extended to provenance.

    Requirement-level references get the same non-blocking treatment
    unconditionally: a Requirement has no lifecycle status of its own — its
    authoritativeness is entirely governed by its Rule Version(s), which
    are already checked above.
    """
    for rvid, rv in dataset.rule_versions.items():
        status = rv.get("status")
        active = status == "ACTIVE"
        bucket = report.active_promotion_violations if active else report.review_notes
        prefix = "ACTIVE " if active else f"{status or 'unknown-status'} "

        for rfid in rv.get("regulatory_fact_ids") or []:
            rf = dataset.facts.get(rfid)
            if rf is None:
                bucket.append(f"{prefix}{rvid}.regulatory_fact_ids -> unresolved {rfid}")
                continue
            for evid in rf.get("evidence_ids") or []:
                ev = dataset.evidence.get(evid)
                if ev is None:
                    bucket.append(f"{prefix}{rvid} (via {rfid}) -> unresolved evidence {evid}")
                    continue
                sid = ev.get("source_id")
                if sid and sid not in dataset.sources:
                    bucket.append(f"{prefix}{rvid} (via {rfid} -> {evid}) -> unresolved source {sid}")

        for evid in rv.get("evidence_ids") or []:
            if evid not in dataset.evidence:
                bucket.append(f"{prefix}{rvid}.evidence_ids -> unresolved {evid}")

        for sid in rv.get("source_ids") or []:
            if sid not in dataset.sources:
                bucket.append(f"{prefix}{rvid}.source_ids -> unresolved {sid}")

        auth = rv.get("authority_id")
        if auth and auth not in dataset.authorities:
            bucket.append(f"{prefix}{rvid}.authority_id -> unresolved {auth}")

        inst = rv.get("instrument_id")
        if inst and inst not in dataset.instruments:
            bucket.append(f"{prefix}{rvid}.instrument_id -> unresolved {inst}")

    for reqid, req in dataset.requirements.items():
        for rfid in req.get("grounding_regulatory_fact_ids") or []:
            if rfid not in dataset.facts:
                report.review_notes.append(f"{reqid}.grounding_regulatory_fact_ids -> unresolved {rfid}")
        for evid in req.get("evidence_ids") or []:
            if evid not in dataset.evidence:
                report.review_notes.append(f"{reqid}.evidence_ids -> unresolved {evid}")


def _check_active_promotion_gate(dataset, report: ValidationReport) -> None:
    """The remaining ACTIVE-only promotion conditions that
    `_check_rule_version_provenance` doesn't cover: `effective_start_date`
    presence, an APPROVED Verification record, and instrument temporal
    validity. `condition_expression_root_id`/`rule_id` resolution (gate
    conditions 1-2) are already unconditional hard checks below, for every
    Rule Version regardless of status — nothing additional is needed for
    them here.

    Note on a deliberately UNIMPLEMENTED check: "an ACTIVE Rule Version's
    own `effective_end_date` should not already be in the past" would need
    a "current date" to compare against. `validate_dataset` has no `as_of`
    parameter and is called with no notion of wall-clock time — introducing
    one (e.g. `datetime.date.today()`) would make the SAME dataset validate
    differently on different days, breaking the reproducibility Phase 9
    exists to guarantee ("Same Project Facts + Same Rule Version + Same
    Evaluator/Grammar Version = Same Regulatory Result", extended here to
    "same dataset = same validation result"). No deterministic basis for
    this check exists in the current contract, so it is not implemented —
    flagged here rather than guessed at."""
    for rvid, rv in dataset.rule_versions.items():
        if rv.get("status") != "ACTIVE":
            continue

        if not rv.get("effective_start_date"):
            report.active_promotion_violations.append(
                f"ACTIVE {rvid}.effective_start_date is required for an ACTIVE promotion"
            )

        approved = [
            v for v in dataset.verifications.values()
            if v.get("target_type") == "RULE_VERSION"
            and v.get("target_id") == rvid
            and v.get("result") == "APPROVED"
        ]
        if not approved:
            report.active_promotion_violations.append(
                f"ACTIVE {rvid} has no APPROVED Verification (VER) record targeting it"
            )

        inst = dataset.instruments.get(rv.get("instrument_id"))
        if inst is None:
            continue  # already reported by _check_rule_version_provenance

        currency = inst.get("currency_status")
        instrument_id = inst.get("instrument_id", rv.get("instrument_id"))

        if currency == "IN_FORCE":
            continue

        if currency == "TRANSITIONAL":
            report.review_notes.append(
                f"ACTIVE {rvid} references TRANSITIONAL instrument {instrument_id} — "
                "human review recommended before relying on this as a stable current position."
            )
            continue

        if currency in ("REPEALED", "SUPERSEDED"):
            # ACTIVE means "currently usable regulatory knowledge" — a hard
            # invariant, not a temporal judgment call. An ACTIVE Rule
            # Version referencing an instrument that is no longer in force
            # is always a hard failure, with NO escape via
            # effective_end_date: a Rule Version that is only valid for a
            # bounded past period is, by definition, not a CURRENT
            # authoritative position and must be authored as
            # SUPERSEDED/RETIRED instead (which this gate does not apply
            # to at all — see the module docstring / §18 versioning
            # strategy). Do not resurrect a historical-window exception
            # here.
            report.active_promotion_violations.append(
                f"ACTIVE {rvid} references instrument {instrument_id}, which is currently "
                f"{currency} — an ACTIVE Rule Version must reference a currently IN_FORCE "
                "(or TRANSITIONAL) instrument. Historical knowledge belongs on a "
                "SUPERSEDED/RETIRED Rule Version instead, which this gate does not apply to."
            )
            continue

        # Unrecognized currency_status is already reported as a
        # status_violation by _check_provenance_layer_references; an ACTIVE
        # Rule Version referencing it must still fail closed here rather
        # than silently passing the temporal check.
        report.active_promotion_violations.append(
            f"ACTIVE {rvid} references instrument {instrument_id} with unrecognized "
            f"currency_status {currency!r} — failing closed rather than guessing."
        )


def _check_rule_version_history(dataset, report: ValidationReport) -> None:
    """Lightweight history/versioning consistency (Tranche 1 §12): catches
    obviously broken pointers only. Does NOT enforce "exactly one ACTIVE
    version per Rule" — the finalized contract does not specify that rule,
    and inventing one here would go beyond this tranche's scope."""
    rulev_ids = set(dataset.rule_versions.keys())

    for rvid, rv in dataset.rule_versions.items():
        sup = rv.get("supersedes_rule_version_id")
        if sup and sup not in rulev_ids:
            report.broken_references.append(f"{rvid}.supersedes_rule_version_id -> missing {sup}")

    for rid, rule in dataset.rules.items():
        caid = rule.get("current_active_rule_version_id")
        if not caid:
            continue
        if caid not in rulev_ids:
            report.broken_references.append(f"{rid}.current_active_rule_version_id -> missing {caid}")
            continue
        target = dataset.rule_versions[caid]
        if target.get("status") != "ACTIVE":
            report.broken_references.append(
                f"{rid}.current_active_rule_version_id -> {caid} is not status ACTIVE "
                f"(status={target.get('status')!r})"
            )
        if target.get("rule_id") != rid:
            report.broken_references.append(
                f"{rid}.current_active_rule_version_id -> {caid} belongs to rule "
                f"{target.get('rule_id')!r}, not {rid!r}"
            )

    for r in dataset.rules_index.get("rules", []):
        latest = r.get("latest_rule_version_id")
        if latest and latest not in rulev_ids:
            report.broken_references.append(
                f"rules_index latest_rule_version_id -> missing {latest} for rule {r.get('rule_id')!r}"
            )


def _check_index_count(index_doc: dict, count_key: str, actual: int, report: ValidationReport) -> None:
    counts = (index_doc or {}).get("counts", {})
    if count_key in counts and counts[count_key] != actual:
        report.index_count_mismatches.append(
            f"{count_key}={counts[count_key]} != actual {actual}"
        )


_PROVENANCE_DATASET_ATTRS = (
    "authorities", "instruments", "sources", "evidence", "facts", "verifications",
    "authorities_index", "instruments_index", "sources_index", "evidence_index",
    "facts_index", "verifications_index",
)


def _ensure_provenance_attrs(dataset) -> None:
    """Older/duck-typed callers (e.g. tests_engine_baseline/test_phase8_input_
    validation.py's `_FakeDataset`, predating Tranche 1) may not define the
    six new provenance dicts/indexes. Default them to `{}` rather than
    requiring every existing and future caller to be updated — a dataset
    with no provenance data is exactly what an empty dict already means
    everywhere else in this module."""
    for attr in _PROVENANCE_DATASET_ATTRS:
        if not hasattr(dataset, attr):
            setattr(dataset, attr, {})


def validate_dataset(root: str, dataset) -> ValidationReport:
    _ensure_provenance_attrs(dataset)
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

    # Provenance substrate (Tranche 1) — same pattern, six more record types.
    _check_duplicate_ids("authority_id", glob.glob(os.path.join(root, "authorities", "*.yaml")), report, "AUTH")
    _check_duplicate_ids("instrument_id", glob.glob(os.path.join(root, "instruments", "*.yaml")), report, "INST")
    _check_duplicate_ids("source_id", glob.glob(os.path.join(root, "sources", "*.yaml")), report, "SRC")
    _check_duplicate_ids("evidence_id", glob.glob(os.path.join(root, "evidence", "*.yaml")), report, "EVID")
    _check_duplicate_ids("regulatory_fact_id", glob.glob(os.path.join(root, "facts", "*.yaml")), report, "RF")
    _check_duplicate_ids("verification_id", glob.glob(os.path.join(root, "verifications", "*.yaml")), report, "VER")

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

    # --- provenance substrate (Tranche 1) ---------------------------------------
    _check_required_fields(dataset.authorities, _AUTHORITY_REQUIRED, "AUTH", report)
    _check_required_fields(dataset.instruments, _INSTRUMENT_REQUIRED, "INST", report)
    _check_required_fields(dataset.sources, _SOURCE_REQUIRED, "SRC", report)
    _check_required_fields(dataset.evidence, _EVIDENCE_REQUIRED, "EVID", report)
    _check_required_fields(
        dataset.facts, _FACT_REQUIRED, "RF", report, non_empty_list_fields=("evidence_ids",)
    )
    _check_required_fields(dataset.verifications, _VERIFICATION_REQUIRED, "VER", report)

    _check_provenance_layer_references(dataset, report)
    _check_verification_records(dataset, report)
    # Outward references from Rule Versions/Requirements into the (today
    # empty) provenance layer, and the ACTIVE promotion gate. DRAFT Rule
    # Versions are explicitly exempt from hard failure here — see
    # `_check_rule_version_provenance`'s docstring.
    _check_rule_version_provenance(dataset, report)
    _check_active_promotion_gate(dataset, report)
    _check_rule_version_history(dataset, report)

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

    # Provenance substrate (Tranche 1) index counts. Production indexes are
    # expected to truthfully report zero until verified research lands.
    _check_index_count(dataset.authorities_index, "total_authorities", len(dataset.authorities), report)
    _check_index_count(dataset.instruments_index, "total_instruments", len(dataset.instruments), report)
    _check_index_count(dataset.sources_index, "total_sources", len(dataset.sources), report)
    _check_index_count(dataset.evidence_index, "total_evidence", len(dataset.evidence), report)
    _check_index_count(dataset.facts_index, "total_regulatory_facts", len(dataset.facts), report)
    _check_index_count(dataset.verifications_index, "total_verifications", len(dataset.verifications), report)

    return report

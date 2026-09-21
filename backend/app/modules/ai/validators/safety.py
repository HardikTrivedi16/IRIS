"""Deterministic Safety and Fidelity Validator for IRIS AI Module.

Checks AI outputs for structural soundness, numerical sanity, exception preservation,
and external source text provenance.
This validator is NOT the Rule Engine and NEVER evaluates project applicability.
"""

from datetime import datetime
import math
import re
from typing import Any

from app.modules.ai.schemas import (
    ApplicantDocumentExtraction,
    CandidateStatus,
    RegulatoryCandidate,
    SafetyIssue,
    SafetyValidationResult,
)


class SafetyValidator:
    """Performs deterministic safety, fidelity, and sanity validation on AI outputs."""

    @staticmethod
    def validate_document_extraction(
        extraction: ApplicantDocumentExtraction,
        source_text: str | None = None,
        low_confidence_threshold: float = 0.75,
    ) -> SafetyValidationResult:
        """Validate structural safety and basic sanity of applicant document facts.

        Does not use Python assert. Returns structured SafetyValidationResult.
        """
        issues: list[SafetyIssue] = []

        # 1. Worker count validation
        if extraction.worker_count is not None:
            if extraction.worker_count < 0:
                issues.append(
                    SafetyIssue(
                        code="NEGATIVE_WORKER_COUNT",
                        field="worker_count",
                        message=f"Worker count cannot be negative (got {extraction.worker_count}).",
                        severity="ERROR",
                    )
                )

        # 2. Capacity validation
        if extraction.capacity_value is not None:
            val = extraction.capacity_value
            if math.isnan(val) or math.isinf(val):
                issues.append(
                    SafetyIssue(
                        code="INVALID_NUMERIC",
                        field="capacity_value",
                        message="Capacity value is NaN or infinite.",
                        severity="ERROR",
                    )
                )
            elif val < 0:
                issues.append(
                    SafetyIssue(
                        code="NEGATIVE_CAPACITY",
                        field="capacity_value",
                        message=f"Production capacity cannot be negative (got {val}).",
                        severity="ERROR",
                    )
                )

        # 3. Investment validation
        if extraction.investment_crore_inr is not None:
            inv = extraction.investment_crore_inr
            if math.isnan(inv) or math.isinf(inv):
                issues.append(
                    SafetyIssue(
                        code="INVALID_NUMERIC",
                        field="investment_crore_inr",
                        message="Investment value is NaN or infinite.",
                        severity="ERROR",
                    )
                )
            elif inv < 0:
                issues.append(
                    SafetyIssue(
                        code="NEGATIVE_INVESTMENT",
                        field="investment_crore_inr",
                        message=f"Investment cannot be negative (got {inv}).",
                        severity="ERROR",
                    )
                )

        # 4. Per-field extraction confidence / evidence safety.
        # Confidence is advisory reviewer-attention metadata, never a legal score.
        standard_fields = (
            "business_name", "project_name", "registration_number", "location",
            "state", "district", "capacity_value", "capacity_unit",
            "investment_crore_inr", "worker_count", "authorised_person", "issue_date", "valid_until",
        )
        standard_field_set = set(standard_fields)
        for map_name, mapping in (
            ("field_confidence", extraction.field_confidence),
            ("field_evidence", extraction.field_evidence),
            ("field_source_pages", extraction.field_source_pages),
        ):
            for key in mapping:
                if key not in standard_field_set:
                    issues.append(SafetyIssue(
                        code="UNKNOWN_EXTRACTION_METADATA_FIELD", field=f"{map_name}.{key}",
                        message=f"{map_name} references unknown standard field '{key}'.", severity="WARNING",
                    ))
                elif getattr(extraction, key) is None:
                    issues.append(SafetyIssue(
                        code="ORPHAN_EXTRACTION_METADATA", field=f"{map_name}.{key}",
                        message=f"{map_name} contains metadata for unpopulated field '{key}'.", severity="WARNING",
                    ))

        for field_name in standard_fields:
            field_value = getattr(extraction, field_name)
            if field_value is None:
                continue
            confidence = extraction.field_confidence.get(field_name)
            if confidence is None:
                issues.append(SafetyIssue(
                    code="MISSING_FIELD_CONFIDENCE", field=f"field_confidence.{field_name}",
                    message=f"Populated field '{field_name}' has no extraction confidence; human confirmation is required.",
                    severity="WARNING",
                ))
            elif not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
                issues.append(SafetyIssue(
                    code="INVALID_FIELD_CONFIDENCE", field=f"field_confidence.{field_name}",
                    message=f"Confidence for '{field_name}' must be finite and within [0,1].", severity="ERROR",
                ))
            elif confidence < low_confidence_threshold:
                issues.append(SafetyIssue(
                    code="LOW_CONFIDENCE_EXTRACTION", field=field_name,
                    message=f"Field '{field_name}' confidence {confidence:.2f} is below reviewer threshold {low_confidence_threshold:.2f}.",
                    severity="WARNING",
                ))

            source_page = extraction.field_source_pages.get(field_name)
            if source_page is not None and source_page < 1:
                issues.append(SafetyIssue(
                    code="INVALID_SOURCE_PAGE", field=f"field_source_pages.{field_name}",
                    message=f"Source page for '{field_name}' must be 1-based (got {source_page}).", severity="ERROR",
                ))

            evidence = extraction.field_evidence.get(field_name)
            if source_text and evidence and evidence.strip():
                norm = lambda x: re.sub(r"\s+", " ", x.strip().lower())
                if norm(evidence) not in norm(source_text):
                    issues.append(SafetyIssue(
                        code="DOCUMENT_EVIDENCE_MISMATCH", field=f"field_evidence.{field_name}",
                        message=f"Evidence for '{field_name}' is not a normalized substring of supplied document text.",
                        severity="ERROR",
                    ))

        for idx, fact in enumerate(extraction.additional_facts):
            if fact.confidence is None:
                issues.append(SafetyIssue(
                    code="MISSING_FIELD_CONFIDENCE", field=f"additional_facts[{idx}].confidence",
                    message=f"Additional fact '{fact.name}' has no extraction confidence.", severity="WARNING",
                ))
            elif fact.confidence < low_confidence_threshold:
                issues.append(SafetyIssue(
                    code="LOW_CONFIDENCE_EXTRACTION", field=f"additional_facts[{idx}]",
                    message=f"Additional fact '{fact.name}' confidence {fact.confidence:.2f} is below reviewer threshold {low_confidence_threshold:.2f}.",
                    severity="WARNING",
                ))
            if source_text and fact.evidence and fact.evidence.strip():
                norm_evidence = re.sub(r"\s+", " ", fact.evidence.strip().lower())
                norm_source = re.sub(r"\s+", " ", source_text.strip().lower())
                if norm_evidence not in norm_source:
                    issues.append(SafetyIssue(
                        code="DOCUMENT_EVIDENCE_MISMATCH", field=f"additional_facts[{idx}].evidence",
                        message=f"Evidence for additional fact '{fact.name}' is not present in supplied text.", severity="ERROR",
                    ))

        # 5. Date validation
        for date_field, date_val in [
            ("valid_until", extraction.valid_until),
            ("issue_date", extraction.issue_date),
        ]:
            if date_val is not None:
                cleaned = date_val.strip()
                parsed = False
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        datetime.strptime(cleaned, fmt)
                        parsed = True
                        break
                    except ValueError:
                        continue
                if not parsed:
                    issues.append(
                        SafetyIssue(
                            code="INVALID_DATE_FORMAT",
                            field=date_field,
                            message=f"Date '{date_val}' could not be parsed into a standard format.",
                            severity="WARNING",
                        )
                    )

        if source_text and extraction.provenance and extraction.provenance.exact_source_text:
            p_text = re.sub(r"\s+", " ", extraction.provenance.exact_source_text.strip().lower())
            s_text = re.sub(r"\s+", " ", source_text.strip().lower())
            if p_text not in s_text and s_text not in p_text:
                issues.append(SafetyIssue(
                    code="DOCUMENT_PROVENANCE_MISMATCH", field="provenance.exact_source_text",
                    message="Document extraction provenance does not match supplied authoritative text.", severity="ERROR",
                ))

        has_error = any(i.severity == "ERROR" for i in issues)
        return SafetyValidationResult(
            valid=not has_error,
            requires_human_review=len(issues) > 0,
            issues=issues,
        )


    @staticmethod
    def _source_numeric_obligations(source_text: str) -> list[dict[str, Any]]:
        """Extract obvious comparison-bound numbers from source text conservatively.

        This is a fidelity guard, not a legal rule parser. It only recognizes explicit
        lexical comparison patterns so lost machine-readable thresholds are routed
        to human review.
        """
        obligations: list[dict[str, Any]] = []
        number = r"(-?\d+(?:,\d{3})*(?:\.\d+)?)"
        unit = r"(?:\s*(?:(?:contract|regular|total|projected)\s+)?(TPD|workers?|days?|kg/cm2|kg/cm²|litres?\s+per\s+day|liters?\s+per\s+day|LPD|crore\s+INR|km|kilometres?|units?\s+per\s+minute))?"

        range_pat = re.compile(
            rf"\bbetween\s+{number}(?:\s+[A-Za-z₹/²]+(?:\s+[A-Za-z]+){{0,2}})?\s+and\s+{number}{unit}",
            re.IGNORECASE,
        )
        for m in range_pat.finditer(source_text):
            obligations.append({
                "kind": "range",
                "comparison": "between",
                "lower": float(m.group(1).replace(',', '')),
                "upper": float(m.group(2).replace(',', '')),
                "unit": m.group(3),
            })

        comparator_pat = re.compile(
            rf"\b(greater\s+than|more\s+than|exceeding|at\s+least|or\s+more|less\s+than|below|at\s+most|not\s+exceeding|or\s+less|at\s+or\s+above|at\s+or\s+below|within)\s+{number}{unit}",
            re.IGNORECASE,
        )
        for m in comparator_pat.finditer(source_text):
            # Skip numbers already covered by a BETWEEN span.
            if any(o.get("kind") == "range" and o.get("lower") == float(m.group(2).replace(',', '')) for o in obligations):
                continue
            obligations.append({
                "kind": "single",
                "comparison": re.sub(r"\s+", " ", m.group(1).lower()),
                "value": float(m.group(2).replace(',', '')),
                "unit": m.group(3),
            })

        # Post-fixed comparator forms are common in regulations: "20 or more
        # workers", "10,000 litres per day or more", "5 or less units".
        # Capture both unit-before-comparator and unit-after-comparator forms.
        unit_token = r"(TPD|workers?|days?|kg/cm2|kg/cm²|litres?\s+per\s+day|liters?\s+per\s+day|LPD|crore\s+INR|km|kilometres?|units?\s+per\s+minute)"
        postfix_patterns = [
            re.compile(rf"\b{number}\s+{unit_token}\s+(or\s+more|or\s+less)\b", re.IGNORECASE),
            re.compile(rf"\b{number}\s+(or\s+more|or\s+less)\s+{unit_token}\b", re.IGNORECASE),
        ]
        for pattern_index, pat in enumerate(postfix_patterns):
            for m in pat.finditer(source_text):
                if pattern_index == 0:
                    value_text, unit_text, comparison = m.group(1), m.group(2), m.group(3)
                else:
                    value_text, comparison, unit_text = m.group(1), m.group(2), m.group(3)
                value = float(value_text.replace(',', ''))
                if any(
                    o.get("kind") == "single"
                    and math.isclose(float(o.get("value", float("nan"))), value, rel_tol=0.0, abs_tol=1e-9)
                    and o.get("comparison") == comparison.lower()
                    for o in obligations
                ):
                    continue
                obligations.append({
                    "kind": "single",
                    "comparison": re.sub(r"\s+", " ", comparison.lower()),
                    "value": value,
                    "unit": unit_text,
                })
        return obligations

    @staticmethod
    def _source_qualitative_scope_predicates(source_text: str) -> list[str]:
        """Extract only obvious leading class/scope predicates such as agro-processing.

        Conservative by design: uncertain prose is ignored rather than interpreted.
        """
        predicates: list[str] = []
        pat = re.compile(
            r"^\s*(?:all|every|any)\s+([A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,2})\s+"
            r"(?:factories|factory|units|unit|facilities|facility|projects|project)\b",
            re.IGNORECASE,
        )
        m = pat.search(source_text)
        if m:
            descriptor = re.sub(r"\s+", " ", m.group(1).strip().lower())
            generic = {"industrial", "manufacturing", "registered", "existing", "new"}
            if descriptor not in generic:
                predicates.append(descriptor)
        return predicates

    @staticmethod
    def validate_regulatory_candidate(
        candidate: RegulatoryCandidate,
        source_text: str | None = None,
    ) -> SafetyValidationResult:
        """Validate structural safety, ranges, and provenance of an AI regulatory candidate.

        Does not use Python assert. Passes source_text separately to ensure candidate
        does not validate its own provenance.
        """
        issues: list[SafetyIssue] = []

        # 1. Candidate status guard: Candidate can NEVER be ACTIVE
        if candidate.status != CandidateStatus.AI_CANDIDATE:
            issues.append(
                SafetyIssue(
                    code="INVALID_CANDIDATE_STATUS",
                    field="status",
                    message=f"AI regulatory candidates must have status AI_CANDIDATE (got {candidate.status}).",
                    severity="ERROR",
                )
            )

        # 2. Non-rule validation: if is_regulatory_requirement is False, cannot have requirement_text
        if not candidate.is_regulatory_requirement:
            if candidate.requirement_text and candidate.requirement_text.strip():
                issues.append(
                    SafetyIssue(
                        code="NON_RULE_CANNOT_HAVE_REQUIREMENT",
                        field="requirement_text",
                        message="Non-regulatory text cannot define an actionable requirement.",
                        severity="ERROR",
                    )
                )
            if len(candidate.conditions) > 0:
                issues.append(
                    SafetyIssue(
                        code="NON_RULE_CANNOT_HAVE_CONDITIONS",
                        field="conditions",
                        message="Non-regulatory text cannot define executable conditions.",
                        severity="ERROR",
                    )
                )

        # 3. Required regulatory structure checks
        if candidate.is_regulatory_requirement and (
            candidate.requirement_text is None or not candidate.requirement_text.strip()
        ):
            issues.append(
                SafetyIssue(
                    code="MISSING_REQUIREMENT_TEXT",
                    field="requirement_text",
                    message="Regulatory requirement candidate is missing requirement_text.",
                    severity="ERROR",
                )
            )

        # Qualifiers are legal modifiers. Empty or source-unsupported qualifiers are
        # never safe intermediate structure.
        source_lower = source_text.lower() if source_text else ""
        for idx, qualifier in enumerate(candidate.qualifiers):
            if not qualifier.text or not qualifier.text.strip():
                issues.append(
                    SafetyIssue(
                        code="EMPTY_QUALIFIER",
                        field=f"qualifiers[{idx}]",
                        message="Qualifier text is empty.",
                        severity="ERROR",
                    )
                )
            qword = {
                "EXCEPT": "except",
                "UNLESS": "unless",
                "PROVIDED_THAT": "provided that",
            }.get(qualifier.qualifier_type.value)
            if source_text and qword and qword not in source_lower:
                issues.append(
                    SafetyIssue(
                        code="UNSUPPORTED_QUALIFIER",
                        field=f"qualifiers[{idx}]",
                        message=f"Candidate contains {qualifier.qualifier_type.value} qualifier but authoritative source does not contain corresponding wording.",
                        severity="ERROR",
                    )
                )
            if source_text and qualifier.text and qualifier.text.strip():
                q_text = re.sub(r"\s+", " ", qualifier.text.strip().lower())
                s_text = re.sub(r"\s+", " ", source_text.strip().lower())
                if q_text not in s_text:
                    issues.append(SafetyIssue(
                        code="QUALIFIER_TEXT_MISMATCH", field=f"qualifiers[{idx}].text",
                        message="Qualifier text is not an exact normalized substring of the authoritative source.", severity="ERROR",
                    ))

        # 4. Advisory field-confidence validation for reviewer attention.
        # FR-6.7 expects confidence for proposed fields. Missing confidence is not
        # legal invalidity, but it must be visible to the reviewer.
        expected_confidence_fields: set[str] = set()
        if candidate.requirement_text:
            expected_confidence_fields.add("requirement_text")
        if candidate.conditions:
            expected_confidence_fields.add("conditions")
        if candidate.condition_logic is not None:
            expected_confidence_fields.add("condition_logic")
        if candidate.timing_text:
            expected_confidence_fields.add("timing_text")
        if candidate.qualifiers:
            expected_confidence_fields.add("qualifiers")
        if candidate.issuing_authority:
            expected_confidence_fields.add("issuing_authority")
        if candidate.required_documents:
            expected_confidence_fields.add("required_documents")
        for field_name in sorted(expected_confidence_fields):
            if field_name not in candidate.field_confidence:
                issues.append(SafetyIssue(
                    code="MISSING_FIELD_CONFIDENCE", field=f"field_confidence.{field_name}",
                    message=f"Proposed regulatory field '{field_name}' has no advisory extraction confidence.",
                    severity="WARNING",
                ))

        for field_name, confidence in candidate.field_confidence.items():
            if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
                issues.append(SafetyIssue(
                    code="INVALID_FIELD_CONFIDENCE", field=f"field_confidence.{field_name}",
                    message=f"Regulatory candidate confidence for '{field_name}' must be finite and within [0,1].",
                    severity="ERROR",
                ))

        # 5. Condition range & numeric validation
        for idx, cond in enumerate(candidate.conditions):
            # Range check: lower_value must not exceed upper_value
            if cond.lower_value is not None and cond.upper_value is not None:
                if cond.lower_value > cond.upper_value:
                    issues.append(
                        SafetyIssue(
                            code="REVERSED_RANGE",
                            field=f"conditions[{idx}]",
                            message=(
                                f"Condition '{cond.fact_text}' range is reversed: "
                                f"lower_value ({cond.lower_value}) exceeds upper_value ({cond.upper_value})."
                            ),
                            severity="ERROR",
                        )
                    )

            # Check numeric values are finite
            for val_name, num_val in [
                ("value", cond.value),
                ("lower_value", cond.lower_value),
                ("upper_value", cond.upper_value),
            ]:
                if isinstance(num_val, (int, float)) and not isinstance(num_val, bool):
                    if math.isnan(num_val) or math.isinf(num_val):
                        issues.append(
                            SafetyIssue(
                                code="INVALID_NUMERIC",
                                field=f"conditions[{idx}].{val_name}",
                                message=f"Condition '{cond.fact_text}' {val_name} is NaN or infinite.",
                                severity="ERROR",
                            )
                        )

            structured_numeric_values = [
                v for v in (cond.value, cond.lower_value, cond.upper_value)
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            ]
            if cond.is_numeric and not structured_numeric_values:
                issues.append(
                    SafetyIssue(
                        code="NUMERIC_CONDITION_MISSING_VALUE",
                        field=f"conditions[{idx}]",
                        message="Condition is marked numeric but has no structured numeric value or range bounds.",
                        severity="ERROR",
                    )
                )
            if not cond.is_numeric and structured_numeric_values:
                issues.append(
                    SafetyIssue(
                        code="NON_NUMERIC_CONDITION_HAS_NUMBER",
                        field=f"conditions[{idx}]",
                        message="Condition is marked non-numeric but contains structured numeric values.",
                        severity="ERROR",
                    )
                )

            # raw_snippet is declared exact evidence; if supplied it must occur in source.
            if source_text and cond.raw_snippet and cond.raw_snippet.strip():
                normalize = lambda x: re.sub(r"\s+", " ", x.strip().lower())
                if normalize(cond.raw_snippet) not in normalize(source_text):
                    issues.append(
                        SafetyIssue(
                            code="RAW_SNIPPET_MISMATCH",
                            field=f"conditions[{idx}].raw_snippet",
                            message="Condition raw_snippet is not an exact normalized substring of the authoritative source.",
                            severity="ERROR",
                        )
                    )

            # Fact text check
            if not cond.fact_text or not cond.fact_text.strip():
                issues.append(
                    SafetyIssue(
                        code="EMPTY_CONDITION_FACT",
                        field=f"conditions[{idx}]",
                        message="Condition has empty fact_text description.",
                        severity="ERROR",
                    )
                )

        # 4. Condition logic check
        if len(candidate.conditions) > 1 and candidate.condition_logic is None:
            issues.append(
                SafetyIssue(
                    code="AMBIGUOUS_CONDITION_LOGIC",
                    field="condition_logic",
                    message="Multiple conditions extracted without explicit condition_logic (AND/OR).",
                    severity="WARNING",
                )
            )

        # 5. Exception / Qualifier preservation check against source_text
        if source_text:
            st_lower = source_text.lower()
            has_exception_wording = bool(
                re.search(r"\b(except|unless|provided that)\b", st_lower)
            )
            if has_exception_wording and len(candidate.qualifiers) == 0:
                issues.append(
                    SafetyIssue(
                        code="LOST_EXCEPTION_CLAUSE",
                        field="qualifiers",
                        message="Authoritative text contains exception wording ('except'/'unless'/'provided that') but no qualifiers were extracted.",
                        severity="WARNING",
                    )
                )

        # 6. Deterministic source-to-structure fidelity guards.
        # These checks do NOT decide applicability. They only ensure explicit source
        # semantics were not left solely in prose/raw snippets.
        if source_text and candidate.is_regulatory_requirement:
            numeric_obligations = SafetyValidator._source_numeric_obligations(source_text)
            structured_numbers: list[float] = []
            for cond in candidate.conditions:
                for num_val in (cond.value, cond.lower_value, cond.upper_value):
                    if isinstance(num_val, (int, float)) and not isinstance(num_val, bool):
                        structured_numbers.append(float(num_val))

            for obligation in numeric_obligations:
                expected_values = (
                    [obligation["lower"], obligation["upper"]]
                    if obligation["kind"] == "range"
                    else [obligation["value"]]
                )
                for expected in expected_values:
                    if not any(math.isclose(expected, actual, rel_tol=0.0, abs_tol=1e-9) for actual in structured_numbers):
                        issues.append(
                            SafetyIssue(
                                code="SOURCE_NUMERIC_VALUE_NOT_STRUCTURED",
                                field="conditions",
                                message=f"Authoritative source comparison value {expected:g} is not preserved in structured condition value/range fields.",
                                severity="ERROR",
                            )
                        )

                matching_conditions = []
                for cond in candidate.conditions:
                    nums = [v for v in (cond.value, cond.lower_value, cond.upper_value) if isinstance(v, (int, float)) and not isinstance(v, bool)]
                    if any(any(math.isclose(float(v), expected, rel_tol=0.0, abs_tol=1e-9) for expected in expected_values) for v in nums):
                        matching_conditions.append(cond)

                def canonical_comparison(value: str | None) -> str | None:
                    if not value:
                        return None
                    v = re.sub(r"\s+", " ", value.strip().lower())
                    groups = {
                        "GT": {"greater than", "more than", "exceeding", ">"},
                        "GTE": {"at least", "greater than or equal to", "or more", "at or above", ">="},
                        "LT": {"less than", "below", "<"},
                        "LTE": {"at most", "not exceeding", "or less", "at or below", "<="},
                        "BETWEEN": {"between"},
                        "WITHIN": {"within"},
                    }
                    for key, aliases in groups.items():
                        if v in aliases:
                            return key
                    return v

                expected_cmp = canonical_comparison(obligation.get("comparison"))
                if matching_conditions and not any(canonical_comparison(c.comparison_text) == expected_cmp for c in matching_conditions):
                    issues.append(SafetyIssue(
                        code="SOURCE_COMPARISON_NOT_STRUCTURED", field="conditions",
                        message=f"Authoritative source comparison '{obligation['comparison']}' is not faithfully preserved in comparison_text.",
                        severity="ERROR",
                    ))

                def canonical_unit(value: str | None) -> str | None:
                    if not value:
                        return None
                    v = re.sub(r"\s+", " ", value.strip().lower()).replace("²", "2")
                    aliases = {"worker": "workers", "kilometre": "kilometres", "kilometer": "kilometres", "kilometers": "kilometres", "liter per day": "litres per day", "liters per day": "litres per day", "litre per day": "litres per day"}
                    return aliases.get(v, v)

                expected_unit = canonical_unit(obligation.get("unit"))
                if expected_unit and matching_conditions and not any(canonical_unit(c.unit) == expected_unit for c in matching_conditions):
                    issues.append(SafetyIssue(
                        code="SOURCE_UNIT_NOT_STRUCTURED", field="conditions",
                        message=f"Authoritative source unit '{obligation.get('unit')}' is not faithfully preserved in the structured condition unit field.",
                        severity="ERROR",
                    ))

            if len(candidate.conditions) > 1:
                logic_text = re.sub(r"\bor\s+(?:more|less)\b", "", source_text.lower())
                expected_logic = None
                if re.search(r"\bor\b", logic_text):
                    expected_logic = "OR"
                elif re.search(r"\band\b", logic_text):
                    expected_logic = "AND"
                if expected_logic and (candidate.condition_logic is None or candidate.condition_logic.value != expected_logic):
                    issues.append(SafetyIssue(
                        code="SOURCE_CONDITION_LOGIC_MISMATCH", field="condition_logic",
                        message=f"Authoritative source explicitly uses {expected_logic} between conditions but candidate condition_logic is {getattr(candidate.condition_logic, 'value', None)}.",
                        severity="ERROR",
                    ))

            for predicate in SafetyValidator._source_qualitative_scope_predicates(source_text):
                preserved = any(
                    (isinstance(cond.value, str) and predicate in cond.value.lower())
                    or predicate in (cond.fact_text or "").lower()
                    for cond in candidate.conditions
                )
                if not preserved:
                    issues.append(
                        SafetyIssue(
                            code="SOURCE_QUALITATIVE_PREDICATE_NOT_STRUCTURED",
                            field="conditions",
                            message=f"Authoritative applicability predicate '{predicate}' is not preserved as a structured condition.",
                            severity="ERROR",
                        )
                    )

        # 7. Provenance fidelity validation against supplied authoritative source_text
        if source_text:
            if candidate.provenance is None or not candidate.provenance.exact_source_text:
                issues.append(
                    SafetyIssue(
                        code="MISSING_PROVENANCE_SOURCE",
                        field="provenance.exact_source_text",
                        message="Candidate missing exact_source_text in provenance.",
                        severity="ERROR",
                    )
                )
            else:
                p_text = candidate.provenance.exact_source_text.strip().lower()
                s_text = source_text.strip().lower()
                # Provenance text must be a faithful snippet or match the supplied source text
                if p_text not in s_text and s_text not in p_text:
                    issues.append(
                        SafetyIssue(
                            code="PROVENANCE_MISMATCH",
                            field="provenance.exact_source_text",
                            message="Candidate provenance exact_source_text does not match the authoritative source text.",
                            severity="ERROR",
                        )
                    )

        has_error = any(i.severity == "ERROR" for i in issues)
        requires_review = candidate.requires_human_review or len(issues) > 0 or not candidate.is_regulatory_requirement or has_error

        return SafetyValidationResult(
            valid=not has_error,
            requires_human_review=requires_review,
            issues=issues,
        )

    @staticmethod
    def validate_explanation(
        task_type: str,
        authoritative_input: Any,
        output: Any,
    ) -> SafetyValidationResult:
        """Validate structural fidelity of an explanation against its authoritative input.

        Deterministic checks cover:
        - Statuses, outcomes, and life-cycle classifications
        - Names and IDs of requirements and entities
        - Blocker lists and dependency directions
        - Critical-path node sequences and durations
        - Numeric values, ranges, and SLA counts
        - Responsible authority preservation (null if null, exact if supplied)
        - Scheme outcome preservation (never upgraded to ELIGIBLE/APPROVED/AWARDED)
        - Risk score preservation and purpose
        - Official query text exact match and additional_document_requested boolean
        - Units (never invented if null in input)

        Does not perform fuzzy NLP; focuses on structured fields and critical high-risk guards.
        """
        issues: list[SafetyIssue] = []

        def get_val(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Generic exact structured-fidelity gate. These fields are copies of
        # already-computed deterministic results; omission is a mutation too.
        fidelity_fields = {
            "explanation_requirement_trace": ("requirement", "outcome", "missing_facts"),
            "explanation_dependency": ("requirement", "status", "blocked_by", "reason_code", "requirement_on_critical_path", "critical_path_nodes"),
            "explanation_parallel_candidates": ("requirements", "classification", "reason"),
            "explanation_critical_path": ("critical_path", "estimated_total_duration_days"),
            "explanation_document_issue": ("field_name", "issue_type", "severity", "expected_value", "actual_value", "unit"),
            "explanation_impact_change": ("changed_fact", "old_value", "new_value", "newly_applicable", "no_longer_applicable", "dependency_changes", "critical_path_changed"),
            "explanation_sla": ("status", "total_days", "elapsed_days", "remaining_days", "paused", "pause_reason", "delay_factors", "responsible_authority"),
            "explanation_scheme": ("scheme_name", "eligibility_outcome", "matched_conditions", "required_documents", "disclaimer"),
            "explanation_risk": ("risk_score", "risk_level", "factors", "purpose"),
            "explanation_official_query": ("official_text", "related_requirement", "related_document"),
            "explanation_application_status": ("status", "reasons", "pending_actions"),
        }
        for field_name in fidelity_fields.get(task_type, ()):
            expected = get_val(authoritative_input, field_name)
            actual = get_val(output, field_name)
            if expected != actual:
                issues.append(SafetyIssue(
                    code="STRUCTURED_FIDELITY_MISMATCH", field=field_name,
                    message=f"Structured fidelity field '{field_name}' changed or was omitted: expected {expected!r}, got {actual!r}.",
                    severity="ERROR",
                ))

        # 1. Requirement Trace Explanation
        if task_type == "explanation_requirement_trace":
            in_outcome = get_val(authoritative_input, "outcome")
            out_outcome = get_val(output, "outcome")
            if in_outcome and out_outcome and in_outcome != out_outcome:
                issues.append(
                    SafetyIssue(
                        code="OUTCOME_FIDELITY_MUTATION",
                        field="outcome",
                        message=f"Evaluation outcome mutated from '{in_outcome}' to '{out_outcome}'.",
                        severity="ERROR",
                    )
                )
            in_req = get_val(authoritative_input, "requirement")
            out_req = get_val(output, "requirement")
            if in_req and out_req and in_req != out_req:
                issues.append(
                    SafetyIssue(
                        code="REQUIREMENT_NAME_MUTATION",
                        field="requirement",
                        message=f"Requirement name mutated from '{in_req}' to '{out_req}'.",
                        severity="ERROR",
                    )
                )
            if in_outcome == "CONDITIONAL":
                expl = str(get_val(output, "explanation", "")).lower()
                if "requirement applies" in expl or "definitely applies" in expl:
                    issues.append(
                        SafetyIssue(
                            code="CONDITIONAL_OVERSTATED",
                            field="explanation",
                            message="Conditional requirement explained as unconditionally applicable.",
                            severity="ERROR",
                        )
                    )

        # 2. Dependency / Blocker Explanation
        elif task_type == "explanation_dependency":
            in_status = get_val(authoritative_input, "status")
            out_status = get_val(output, "status")
            if in_status and out_status and in_status != out_status:
                issues.append(
                    SafetyIssue(
                        code="STATUS_FIDELITY_MUTATION",
                        field="status",
                        message=f"Status mutated from '{in_status}' to '{out_status}'.",
                        severity="ERROR",
                    )
                )
            in_blocked = set(get_val(authoritative_input, "blocked_by") or [])
            out_blocked = set(get_val(output, "blocked_by") or [])
            if in_blocked != out_blocked:
                issues.append(
                    SafetyIssue(
                        code="BLOCKER_LIST_MISMATCH",
                        field="blocked_by",
                        message=f"Blocker list mismatch: expected {sorted(in_blocked)}, got {sorted(out_blocked)}.",
                        severity="ERROR",
                    )
                )
            in_cp_nodes = set(get_val(authoritative_input, "critical_path_nodes") or [])
            out_cp_nodes = set(get_val(output, "critical_path_nodes") or [])
            for b in in_blocked:
                if b in out_cp_nodes and b not in in_cp_nodes:
                    issues.append(
                        SafetyIssue(
                            code="INVENTED_CRITICAL_PATH_BLOCKER",
                            field="critical_path_nodes",
                            message=f"Blocker '{b}' falsely marked as critical path node without authoritative basis.",
                            severity="ERROR",
                        )
                    )

        # 3. Parallel Candidate Explanation
        elif task_type == "explanation_parallel_candidates":
            in_reqs = sorted(get_val(authoritative_input, "requirements") or [])
            out_reqs = sorted(get_val(output, "requirements") or [])
            if in_reqs != out_reqs:
                issues.append(
                    SafetyIssue(
                        code="PARALLEL_REQUIREMENTS_MISMATCH",
                        field="requirements",
                        message=f"Parallel requirements mismatch: expected {in_reqs}, got {out_reqs}.",
                        severity="ERROR",
                    )
                )

        # 4. Critical Path Explanation
        elif task_type == "explanation_critical_path":
            in_path = get_val(authoritative_input, "critical_path") or []
            out_path = get_val(output, "critical_path") or []
            if in_path != out_path:
                issues.append(
                    SafetyIssue(
                        code="CRITICAL_PATH_SEQUENCE_MISMATCH",
                        field="critical_path",
                        message=f"Critical path sequence mismatch: expected {in_path}, got {out_path}.",
                        severity="ERROR",
                    )
                )
            in_dur = get_val(authoritative_input, "estimated_total_duration_days")
            out_dur = get_val(output, "estimated_total_duration_days")
            if in_dur is not None and out_dur is not None and in_dur != out_dur:
                issues.append(
                    SafetyIssue(
                        code="DURATION_FIDELITY_MUTATION",
                        field="estimated_total_duration_days",
                        message=f"Critical path duration mutated from {in_dur} to {out_dur}.",
                        severity="ERROR",
                    )
                )

        # 5. Document Issue Explanation
        elif task_type == "explanation_document_issue":
            in_field = get_val(authoritative_input, "field_name")
            out_field = get_val(output, "field_name")
            if in_field and out_field and in_field != out_field:
                issues.append(
                    SafetyIssue(
                        code="FIELD_NAME_MUTATION",
                        field="field_name",
                        message=f"Field name mutated from '{in_field}' to '{out_field}'.",
                        severity="ERROR",
                    )
                )
            in_type = get_val(authoritative_input, "issue_type")
            out_type = get_val(output, "issue_type")
            if in_type and out_type and in_type != out_type:
                issues.append(
                    SafetyIssue(
                        code="ISSUE_TYPE_MUTATION",
                        field="issue_type",
                        message=f"Issue type mutated from '{in_type}' to '{out_type}'.",
                        severity="ERROR",
                    )
                )
            in_sev = get_val(authoritative_input, "severity")
            out_sev = get_val(output, "severity")
            if in_sev and out_sev and in_sev != out_sev:
                issues.append(
                    SafetyIssue(
                        code="SEVERITY_MUTATION",
                        field="severity",
                        message=f"Severity mutated from '{in_sev}' to '{out_sev}'.",
                        severity="ERROR",
                    )
                )
            in_exp = get_val(authoritative_input, "expected_value")
            out_exp = get_val(output, "expected_value")
            in_act = get_val(authoritative_input, "actual_value")
            out_act = get_val(output, "actual_value")
            if in_exp is not None and out_exp != in_exp:
                issues.append(
                    SafetyIssue(
                        code="NUMERIC_FIDELITY_MUTATION",
                        field="expected_value",
                        message=f"Expected value mutated from {in_exp} to {out_exp}.",
                        severity="ERROR",
                    )
                )
            if in_act is not None and out_act != in_act:
                issues.append(
                    SafetyIssue(
                        code="NUMERIC_FIDELITY_MUTATION",
                        field="actual_value",
                        message=f"Actual value mutated from {in_act} to {out_act}.",
                        severity="ERROR",
                    )
                )
            in_unit = get_val(authoritative_input, "unit")
            out_unit = get_val(output, "unit")
            if in_unit is None and out_unit is not None:
                issues.append(
                    SafetyIssue(
                        code="INVENTED_UNIT",
                        field="unit",
                        message=f"Unit '{out_unit}' invented when authoritative input provided no unit.",
                        severity="ERROR",
                    )
                )
            elif in_unit is not None and out_unit != in_unit:
                issues.append(
                    SafetyIssue(
                        code="UNIT_FIDELITY_MUTATION",
                        field="unit",
                        message=f"Unit mutated from '{in_unit}' to '{out_unit}'.",
                        severity="ERROR",
                    )
                )
            elif in_unit is None:
                expl = str(get_val(output, "explanation", "")).lower()
                if re.search(r"\b(tpd|tonnes|tons|units/day|litres|mt/year)\b", expl):
                    issues.append(
                        SafetyIssue(
                            code="INVENTED_UNIT_IN_PROSE",
                            field="explanation",
                            message="Explanation invented a unit of measurement when none was supplied in input.",
                            severity="ERROR",
                        )
                    )

        # 6. Impact Change Explanation
        elif task_type == "explanation_impact_change":
            for val_field in ("old_value", "new_value"):
                in_v = get_val(authoritative_input, val_field)
                out_v = get_val(output, val_field)
                if in_v is not None and out_v is not None and in_v != out_v:
                    issues.append(
                        SafetyIssue(
                            code="NUMERIC_FIDELITY_MUTATION",
                            field=val_field,
                            message=f"{val_field} mutated from {in_v} to {out_v}.",
                            severity="ERROR",
                        )
                    )
            in_newly = set(get_val(authoritative_input, "newly_applicable") or [])
            out_newly = set(get_val(output, "newly_applicable") or [])
            if in_newly != out_newly:
                issues.append(
                    SafetyIssue(
                        code="IMPACT_DIFF_MISMATCH",
                        field="newly_applicable",
                        message=f"Newly applicable mismatch: expected {sorted(in_newly)}, got {sorted(out_newly)}.",
                        severity="ERROR",
                    )
                )
            in_trace = get_val(authoritative_input, "condition_trace")
            if not in_trace:
                expl = str(get_val(output, "explanation", ""))
                if re.search(r">\s*50\b|threshold of 50\b|exceeds 50\b", expl, re.IGNORECASE):
                    issues.append(
                        SafetyIssue(
                            code="INVENTED_LEGAL_THRESHOLD",
                            field="explanation",
                            message="Explanation invented a '>50' threshold not supplied in authoritative input.",
                            severity="ERROR",
                        )
                    )

        # 7. SLA Explanation
        elif task_type == "explanation_sla":
            in_stat = get_val(authoritative_input, "status")
            out_stat = get_val(output, "status")
            if in_stat and out_stat and in_stat != out_stat:
                issues.append(
                    SafetyIssue(
                        code="SLA_STATUS_MUTATION",
                        field="status",
                        message=f"SLA status mutated from {in_stat} to {out_stat}.",
                        severity="ERROR",
                    )
                )
            for d_field in ("total_days", "elapsed_days", "remaining_days"):
                in_d = get_val(authoritative_input, d_field)
                out_d = get_val(output, d_field)
                if in_d is not None and out_d is not None and in_d != out_d:
                    issues.append(
                        SafetyIssue(
                            code="SLA_NUMERIC_MUTATION",
                            field=d_field,
                            message=f"{d_field} mutated from {in_d} to {out_d}.",
                            severity="ERROR",
                        )
                    )
            in_auth = get_val(authoritative_input, "responsible_authority")
            out_auth = get_val(output, "responsible_authority")
            if in_auth is None and out_auth is not None:
                issues.append(
                    SafetyIssue(
                        code="INVENTED_RESPONSIBLE_AUTHORITY",
                        field="responsible_authority",
                        message=f"Responsible authority '{out_auth}' inferred when input was null.",
                        severity="ERROR",
                    )
                )
            elif in_auth is not None and out_auth != in_auth:
                issues.append(
                    SafetyIssue(
                        code="RESPONSIBLE_AUTHORITY_MUTATION",
                        field="responsible_authority",
                        message=f"Responsible authority mutated from '{in_auth}' to '{out_auth}'.",
                        severity="ERROR",
                    )
                )
            in_delays = get_val(authoritative_input, "delay_factors") or []
            if not in_delays and in_auth is None:
                expl = str(get_val(output, "explanation", ""))
                if re.search(r"\b(pollution control board|pcb|department is responsible|officer is at fault)\b", expl, re.IGNORECASE):
                    issues.append(
                        SafetyIssue(
                            code="UNSUPPORTED_DELAY_BLAME",
                            field="explanation",
                            message="Explanation attributed delay to an authority not supported by input.",
                            severity="ERROR",
                        )
                    )

        # 8. Scheme Explanation
        elif task_type == "explanation_scheme":
            in_el = get_val(authoritative_input, "eligibility_outcome")
            out_el = get_val(output, "eligibility_outcome")
            if in_el and out_el and in_el != out_el:
                issues.append(
                    SafetyIssue(
                        code="SCHEME_OUTCOME_MUTATION",
                        field="eligibility_outcome",
                        message=f"Scheme outcome mutated from '{in_el}' to '{out_el}'.",
                        severity="ERROR",
                    )
                )
            if in_el == "POTENTIALLY_ELIGIBLE":
                expl = str(get_val(output, "explanation", "")).lower()
                if "has been approved" in expl or "is awarded" in expl or "is fully eligible" in expl:
                    issues.append(
                        SafetyIssue(
                            code="SCHEME_ELIGIBILITY_OVERSTATED",
                            field="explanation",
                            message="Scheme match claimed approved or awarded rather than potentially eligible.",
                            severity="ERROR",
                        )
                    )

        # 9. Risk Explanation
        elif task_type == "explanation_risk":
            in_score = get_val(authoritative_input, "risk_score")
            out_score = get_val(output, "risk_score")
            if in_score is not None and out_score is not None and in_score != out_score:
                issues.append(
                    SafetyIssue(
                        code="RISK_SCORE_MUTATION",
                        field="risk_score",
                        message=f"Risk score mutated from {in_score} to {out_score}.",
                        severity="ERROR",
                    )
                )
            expl = str(get_val(output, "explanation", "")).lower()
            if "application is rejected" in expl or "application will be rejected" in expl or "statutory rejection" in expl:
                issues.append(
                    SafetyIssue(
                        code="RISK_ADJUDICATION_OVERSTATEMENT",
                        field="explanation",
                        message="Risk explanation implied statutory rejection of application.",
                        severity="ERROR",
                    )
                )

        # 10. Official Query Explanation
        elif task_type == "explanation_official_query":
            in_text = get_val(authoritative_input, "official_text")
            out_text = get_val(output, "official_text")
            if in_text and out_text and in_text != out_text:
                issues.append(
                    SafetyIssue(
                        code="OFFICIAL_TEXT_MUTATION",
                        field="official_text",
                        message="Official query text must remain immutable and exactly match authoritative input.",
                        severity="ERROR",
                    )
                )
            in_text_str = str(in_text or "").lower()
            out_doc_req = get_val(output, "additional_document_requested")
            if "no additional document is requested" in in_text_str:
                if out_doc_req is not False:
                    issues.append(
                        SafetyIssue(
                            code="DOCUMENT_REQUEST_FIDELITY",
                            field="additional_document_requested",
                            message="Official text explicitly states no additional document is requested, but additional_document_requested was not False.",
                            severity="ERROR",
                        )
                    )
                expl = str(get_val(output, "explanation", "")).lower()
                if "upload a revised project report" in expl or "upload revised project report" in expl:
                    issues.append(
                        SafetyIssue(
                            code="INVENTED_DOCUMENT_UPLOAD",
                            field="explanation",
                            message="Explanation told applicant to upload revised project report despite query stating no document is requested.",
                            severity="ERROR",
                        )
                    )

        # 11. Application Status Explanation
        elif task_type == "explanation_application_status":
            in_stat = get_val(authoritative_input, "status")
            out_stat = get_val(output, "status")
            if in_stat and out_stat and in_stat != out_stat:
                issues.append(
                    SafetyIssue(
                        code="APPLICATION_STATUS_MUTATION",
                        field="status",
                        message=f"Application status mutated from '{in_stat}' to '{out_stat}'.",
                        severity="ERROR",
                    )
                )

        has_error = any(i.severity == "ERROR" for i in issues)
        requires_review = len(issues) > 0 or has_error or getattr(output, "insufficient_information", False)

        return SafetyValidationResult(
            valid=not has_error,
            requires_human_review=requires_review,
            issues=issues,
        )


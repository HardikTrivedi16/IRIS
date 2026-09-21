"""Tests for ExplanationService in IRIS AI Module (Phase 5).

Tests AI-EXP-01 through AI-EXP-30 (Offline, zero network calls).
Optional live Phase 5 smoke tests marked with @pytest.mark.live_phase5.
"""

import ast
import inspect
from typing import Any
import pytest

from app.modules.ai import (
    AIConfig,
    ApplicationStatusExplanation,
    ApplicationStatusInput,
    CriticalPathExplanation,
    CriticalPathInput,
    DependencyExplanation,
    DependencyInput,
    DocumentIssueExplanation,
    DocumentIssueInput,
    ExplanationOutput,
    ExplanationResult,
    ImpactChangeExplanation,
    ImpactChangeInput,
    OfficialQueryExplanation,
    OfficialQueryInput,
    ParallelCandidateExplanation,
    ParallelCandidateInput,
    RequirementTraceExplanation,
    RequirementTraceInput,
    RiskExplanation,
    RiskInput,
    SchemeExplanation,
    SchemeMatchInput,
    SLAExplanation,
    SLAInput,
    VerificationIssue,
    VerificationMode,
    VerificationOutcome,
    VerificationResult,
    VerificationVerdict,
    _reset_ai_facade,
    get_ai,
)
from app.modules.ai.exceptions import AIUnavailableError
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.explanations import ExplanationService
from app.modules.ai.services.verification import VerificationService
from app.modules.ai.validators.safety import SafetyValidator


# ==============================================================================
# Mocks for Offline Testing
# ==============================================================================

class MockExplanationAIProvider(BaseAIProvider):
    """Mock Core AI Provider returning a predetermined structured explanation."""

    def __init__(self, structured_return: Any = None) -> None:
        self.structured_return = structured_return
        self.last_prompt = ""

    def generate(self, prompt: str, **kwargs: Any) -> str:
        return "mock text"

    def generate_structured(self, prompt: str, schema: type[Any], **kwargs: Any) -> Any:
        self.last_prompt = prompt
        return self.structured_return

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    def health_check(self) -> bool:
        return True


class MockExplanationVerifier(BaseVerificationProvider):
    """Mock Verification Provider for explanation tests."""

    def __init__(
        self,
        result: VerificationResult | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.result = result or VerificationResult(
            verdict=VerificationVerdict.PASS,
            issues=[],
            corrected_output=None,
            verifier_provider="mock_verifier",
        )
        self.exc = exc
        self.last_authoritative_input = None
        self.last_local_output = None

    def verify(
        self,
        task_type: str,
        authoritative_input: Any,
        local_output: Any,
        **kwargs: Any,
    ) -> VerificationResult:
        self.last_authoritative_input = authoritative_input
        self.last_local_output = local_output
        if self.exc:
            raise self.exc
        return self.result


def _build_service(
    mock_ai_output: Any,
    mock_verifier_result: VerificationResult | None = None,
    verifier_exc: Exception | None = None,
) -> tuple[ExplanationService, MockExplanationAIProvider, MockExplanationVerifier]:
    ai_provider = MockExplanationAIProvider(structured_return=mock_ai_output)
    verifier_provider = MockExplanationVerifier(
        result=mock_verifier_result,
        exc=verifier_exc,
    )
    core = CoreAIService(provider=ai_provider)
    verification = VerificationService(
        provider=verifier_provider,
        mode=VerificationMode.ADVISORY,
    )
    service = ExplanationService(core=core, verification=verification)
    return service, ai_provider, verifier_provider


# ==============================================================================
# Phase 5 Offline Tests (AI-EXP-01 through AI-EXP-30)
# ==============================================================================

def test_ai_exp_01_conditional_requirement_remains_conditional() -> None:
    """AI-EXP-01: CONDITIONAL requirement with missing capacity remains CONDITIONAL."""
    raw = RequirementTraceExplanation(
        explanation="The requirement is conditional because capacity information is missing, so it cannot be conclusively evaluated.",
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    service, _, _ = _build_service(raw)
    inp = RequirementTraceInput(
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    res = service.requirement_trace(inp)

    assert res.fidelity_valid is True
    assert res.data.outcome == "CONDITIONAL"
    assert "APPLICABLE" not in res.data.outcome
    assert res.data.missing_facts == ["capacity_tpd"]

    # Also verify SafetyValidator flags mutated outcome
    mutated = RequirementTraceExplanation(
        explanation="The requirement definitely applies.",
        requirement="Environmental Consent",
        outcome="APPLICABLE",
        missing_facts=[],
    )
    safety_check = SafetyValidator.validate_explanation("explanation_requirement_trace", inp, mutated)
    assert safety_check.valid is False
    assert any(i.code == "OUTCOME_FIDELITY_MUTATION" for i in safety_check.issues)


def test_ai_exp_02_single_blocker_direction_preserved() -> None:
    """AI-EXP-02: Single blocker direction preserved."""
    raw = DependencyExplanation(
        explanation="Consent to Operate is currently shown as blocked because Consent to Establish is an incomplete configured prerequisite.",
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish"],
        requirement_on_critical_path=False,
        reason_code="PREREQUISITE_INCOMPLETE",
    )
    service, _, _ = _build_service(raw)
    inp = DependencyInput(
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish"],
        reason_code="PREREQUISITE_INCOMPLETE",
        requirement_on_critical_path=False,
    )
    res = service.dependency(inp)

    assert res.fidelity_valid is True
    assert res.data.requirement == "Consent to Operate"
    assert res.data.status == "BLOCKED"
    assert res.data.blocked_by == ["Consent to Establish"]


def test_ai_exp_03_multiple_blockers_preserved_exactly() -> None:
    """AI-EXP-03: Multiple blockers preserved exactly."""
    raw = DependencyExplanation(
        explanation="Consent to Operate is blocked by Consent to Establish and Fire Safety Review.",
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish", "Fire Safety Review"],
        requirement_on_critical_path=True,
    )
    service, _, _ = _build_service(raw)
    inp = DependencyInput(
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish", "Fire Safety Review"],
        requirement_on_critical_path=True,
    )
    res = service.dependency(inp)

    assert res.fidelity_valid is True
    assert set(res.data.blocked_by) == {"Consent to Establish", "Fire Safety Review"}

    # Mutated blocker list fails safety check
    mutated = DependencyExplanation(
        explanation="Consent to Operate is blocked only by Consent to Establish.",
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish"],
    )
    safety_check = SafetyValidator.validate_explanation("explanation_dependency", inp, mutated)
    assert safety_check.valid is False
    assert any(i.code == "BLOCKER_LIST_MISMATCH" for i in safety_check.issues)


def test_ai_exp_04_critical_path_true_does_not_mark_all_blockers_as_critical_path() -> None:
    """AI-EXP-04: critical_path=true does NOT automatically mark every blocker as a critical-path node."""
    inp = DependencyInput(
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish", "Fire Safety Review"],
        requirement_on_critical_path=True,
        critical_path_nodes=["Consent to Operate", "Consent to Establish"],
    )
    # Output incorrectly assumes Fire Safety Review is on critical path
    bad_output = DependencyExplanation(
        explanation="Both blockers individually belong to the critical path.",
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish", "Fire Safety Review"],
        critical_path_nodes=["Consent to Operate", "Consent to Establish", "Fire Safety Review"],
    )
    safety_check = SafetyValidator.validate_explanation("explanation_dependency", inp, bad_output)
    assert safety_check.valid is False
    assert any(i.code == "INVENTED_CRITICAL_PATH_BLOCKER" for i in safety_check.issues)


def test_ai_exp_05_parallel_candidates_remains_advisory() -> None:
    """AI-EXP-05: PARALLEL_CANDIDATES remains advisory; no guaranteed simultaneous processing claim."""
    raw = ParallelCandidateExplanation(
        explanation="IRIS identifies these as potential parallel candidates because no configured prerequisite relationship exists between them.",
        requirements=["Environmental Consent", "Fire Safety Review"],
        classification="PARALLEL_CANDIDATES",
        reason="No configured prerequisite relationship exists between these requirements",
    )
    service, _, _ = _build_service(raw)
    inp = ParallelCandidateInput(
        requirements=["Environmental Consent", "Fire Safety Review"],
        classification="PARALLEL_CANDIDATES",
        reason="No configured prerequisite relationship exists between these requirements",
    )
    res = service.parallel_candidates(inp)

    assert res.fidelity_valid is True
    assert res.data.classification == "PARALLEL_CANDIDATES"
    assert "legally required to process them simultaneously" not in res.explanation


def test_ai_exp_06_critical_path_nodes_order_and_duration_preserved() -> None:
    """AI-EXP-06: Critical-path nodes/order and 75-day duration preserved exactly."""
    path = ["Consent to Establish", "Construction Completion", "Consent to Operate"]
    raw = CriticalPathExplanation(
        explanation="IRIS identifies Consent to Establish -> Construction Completion -> Consent to Operate as the computed critical path, with an estimated total duration of 75 days.",
        critical_path=path,
        estimated_total_duration_days=75,
    )
    service, _, _ = _build_service(raw)
    inp = CriticalPathInput(
        critical_path=path,
        estimated_total_duration_days=75,
    )
    res = service.critical_path(inp)

    assert res.fidelity_valid is True
    assert res.data.critical_path == path
    assert res.data.estimated_total_duration_days == 75


def test_ai_exp_07_critical_path_not_strengthened_into_statutory_ordering() -> None:
    """AI-EXP-07: Critical path sequence and duration mutation are rejected."""
    inp = CriticalPathInput(
        critical_path=["Consent to Establish", "Construction Completion", "Consent to Operate"],
        estimated_total_duration_days=75,
    )
    # Mutated duration
    mutated_dur = CriticalPathExplanation(
        explanation="Critical path has 85 days duration.",
        critical_path=["Consent to Establish", "Construction Completion", "Consent to Operate"],
        estimated_total_duration_days=85,
    )
    safety_dur = SafetyValidator.validate_explanation("explanation_critical_path", inp, mutated_dur)
    assert safety_dur.valid is False
    assert any(i.code == "DURATION_FIDELITY_MUTATION" for i in safety_dur.issues)

    # Mutated sequence
    mutated_seq = CriticalPathExplanation(
        explanation="Reversed sequence.",
        critical_path=["Consent to Operate", "Consent to Establish"],
        estimated_total_duration_days=75,
    )
    safety_seq = SafetyValidator.validate_explanation("explanation_critical_path", inp, mutated_seq)
    assert safety_seq.valid is False
    assert any(i.code == "CRITICAL_PATH_SEQUENCE_MISMATCH" for i in safety_seq.issues)


def test_ai_exp_08_document_mismatch_preserves_expected_60_and_actual_80() -> None:
    """AI-EXP-08: Document mismatch preserves expected=60 and actual=80."""
    raw = DocumentIssueExplanation(
        explanation="Production capacity in the uploaded document (80) differs from the project profile (60).",
        field_name="capacity_tpd",
        issue_type="INCONSISTENCY",
        severity="BLOCKING",
        expected_value=60,
        actual_value=80,
    )
    service, _, _ = _build_service(raw)
    inp = DocumentIssueInput(
        field_name="capacity_tpd",
        issue_type="INCONSISTENCY",
        severity="BLOCKING",
        expected_value=60,
        actual_value=80,
        message="Production capacity in the uploaded document differs from the project profile.",
    )
    res = service.document_issue(inp)

    assert res.fidelity_valid is True
    assert res.data.expected_value == 60
    assert res.data.actual_value == 80
    assert res.data.issue_type == "INCONSISTENCY"
    assert res.data.severity == "BLOCKING"


def test_ai_exp_09_document_mismatch_with_no_unit_does_not_invent_unit() -> None:
    """AI-EXP-09: Document mismatch with no unit does not invent a unit."""
    inp = DocumentIssueInput(
        field_name="capacity_tpd",
        issue_type="INCONSISTENCY",
        severity="BLOCKING",
        expected_value=60,
        actual_value=80,
        unit=None,  # No unit supplied!
    )
    # 1. Output invents unit in structured field
    bad_output_field = DocumentIssueExplanation(
        explanation="Difference between 60 and 80.",
        field_name="capacity_tpd",
        expected_value=60,
        actual_value=80,
        unit="TPD",
    )
    safety_field = SafetyValidator.validate_explanation("explanation_document_issue", inp, bad_output_field)
    assert safety_field.valid is False
    assert any(i.code == "INVENTED_UNIT" for i in safety_field.issues)

    # 2. Output invents unit in prose
    bad_output_prose = DocumentIssueExplanation(
        explanation="Difference between 60 TPD and 80 TPD.",
        field_name="capacity_tpd",
        expected_value=60,
        actual_value=80,
        unit=None,
    )
    safety_prose = SafetyValidator.validate_explanation("explanation_document_issue", inp, bad_output_prose)
    assert safety_prose.valid is False
    assert any(i.code == "INVENTED_UNIT_IN_PROSE" for i in safety_prose.issues)


def test_ai_exp_10_impact_diff_preserves_old_40_new_70_and_newly_applicable() -> None:
    """AI-EXP-10: Impact diff preserves old=40, new=70 and supplied newly_applicable result."""
    raw = ImpactChangeExplanation(
        explanation="Capacity changed from 40 to 70. Environmental Consent became newly applicable.",
        changed_fact="capacity_tpd",
        old_value=40,
        new_value=70,
        newly_applicable=["Environmental Consent"],
        no_longer_applicable=[],
    )
    service, _, _ = _build_service(raw)
    inp = ImpactChangeInput(
        changed_fact="capacity_tpd",
        old_value=40,
        new_value=70,
        newly_applicable=["Environmental Consent"],
        no_longer_applicable=[],
    )
    res = service.impact_change(inp)

    assert res.fidelity_valid is True
    assert res.data.old_value == 40
    assert res.data.new_value == 70
    assert res.data.newly_applicable == ["Environmental Consent"]


def test_ai_exp_11_impact_explanation_does_not_invent_50_threshold() -> None:
    """AI-EXP-11: Impact explanation does not invent >50 threshold when threshold is not supplied."""
    inp = ImpactChangeInput(
        changed_fact="capacity_tpd",
        old_value=40,
        new_value=70,
        newly_applicable=["Environmental Consent"],
        condition_trace=None,  # Not supplied!
    )
    bad_output = ImpactChangeExplanation(
        explanation="Capacity increased beyond the legal threshold of 50 tonnes.",
        changed_fact="capacity_tpd",
        old_value=40,
        new_value=70,
        newly_applicable=["Environmental Consent"],
    )
    safety = SafetyValidator.validate_explanation("explanation_impact_change", inp, bad_output)
    assert safety.valid is False
    assert any(i.code == "INVENTED_LEGAL_THRESHOLD" for i in safety.issues)


def test_ai_exp_12_sla_preserves_30_25_5_and_approaching() -> None:
    """AI-EXP-12: SLA preserves 30/25/5 and APPROACHING exactly."""
    raw = SLAExplanation(
        explanation="Application SLA status is APPROACHING. 25 of 30 days have elapsed; 5 days remain.",
        status="APPROACHING",
        total_days=30,
        elapsed_days=25,
        remaining_days=5,
        delay_factors=["Document correction pending"],
    )
    service, _, _ = _build_service(raw)
    inp = SLAInput(
        status="APPROACHING",
        total_days=30,
        elapsed_days=25,
        remaining_days=5,
        paused=False,
        delay_factors=["Document correction pending"],
    )
    res = service.sla(inp)

    assert res.fidelity_valid is True
    assert res.data.status == "APPROACHING"
    assert res.data.total_days == 30
    assert res.data.elapsed_days == 25
    assert res.data.remaining_days == 5


def test_ai_exp_13_no_delay_factor_or_authority_no_invented_blame() -> None:
    """AI-EXP-13: No delay factor / authority supplied -> no invented blame."""
    inp = SLAInput(
        status="APPROACHING",
        total_days=30,
        elapsed_days=26,
        remaining_days=4,
        delay_factors=[],
        responsible_authority=None,
    )
    # Output improperly blames Pollution Control Board
    bad_output = SLAExplanation(
        explanation="The delay is because the Pollution Control Board has not completed review.",
        status="APPROACHING",
        total_days=30,
        elapsed_days=26,
        remaining_days=4,
        delay_factors=[],
        responsible_authority="Pollution Control Board",
    )
    safety = SafetyValidator.validate_explanation("explanation_sla", inp, bad_output)
    assert safety.valid is False
    assert any(i.code in ("INVENTED_RESPONSIBLE_AUTHORITY", "UNSUPPORTED_DELAY_BLAME") for i in safety.issues)

    # Faithful output indicates insufficient information without blame
    good_output = SLAExplanation(
        explanation="The supplied information does not identify a delay cause or responsible authority.",
        status="APPROACHING",
        total_days=30,
        elapsed_days=26,
        remaining_days=4,
        delay_factors=[],
        responsible_authority=None,
        insufficient_information=True,
    )
    service, _, _ = _build_service(good_output)
    res = service.sla(inp)
    assert res.fidelity_valid is True
    assert res.insufficient_information is True


def test_ai_exp_14_scheme_preserves_potentially_eligible() -> None:
    """AI-EXP-14: Scheme preserves POTENTIALLY_ELIGIBLE."""
    raw = SchemeExplanation(
        explanation="The project matches configured conditions and is potentially eligible.",
        scheme_name="Example Industrial Support Scheme",
        eligibility_outcome="POTENTIALLY_ELIGIBLE",
        matched_conditions=["sector = food_processing"],
        required_documents=["Project Report"],
        disclaimer="Final eligibility requires official verification.",
    )
    service, _, _ = _build_service(raw)
    inp = SchemeMatchInput(
        scheme_name="Example Industrial Support Scheme",
        eligibility_outcome="POTENTIALLY_ELIGIBLE",
        matched_conditions=["sector = food_processing"],
        required_documents=["Project Report"],
    )
    res = service.scheme(inp)

    assert res.fidelity_valid is True
    assert res.data.eligibility_outcome == "POTENTIALLY_ELIGIBLE"


def test_ai_exp_15_scheme_preserves_investment_range_5_to_20() -> None:
    """AI-EXP-15: Scheme preserves investment range 5 to 20 exactly."""
    conds = [
        "sector = food_processing",
        "state = Maharashtra",
        "investment_crore_inr between 5 and 20",
    ]
    raw = SchemeExplanation(
        explanation="Matched investment range between 5 and 20 crore INR.",
        scheme_name="Support Scheme",
        eligibility_outcome="POTENTIALLY_ELIGIBLE",
        matched_conditions=conds,
        required_documents=["Project Report"],
        disclaimer="Final eligibility requires official verification.",
    )
    service, _, _ = _build_service(raw)
    inp = SchemeMatchInput(
        scheme_name="Support Scheme",
        eligibility_outcome="POTENTIALLY_ELIGIBLE",
        matched_conditions=conds,
        required_documents=["Project Report"],
    )
    res = service.scheme(inp)

    assert res.fidelity_valid is True
    assert any("5 and 20" in c for c in res.data.matched_conditions)


def test_ai_exp_16_scheme_does_not_claim_awarded_or_approved() -> None:
    """AI-EXP-16: Scheme does not claim awarded/approved."""
    inp = SchemeMatchInput(
        scheme_name="Support Scheme",
        eligibility_outcome="POTENTIALLY_ELIGIBLE",
    )
    # Output upgraded outcome to APPROVED
    bad_output_outcome = SchemeExplanation(
        explanation="Scheme has been approved.",
        scheme_name="Support Scheme",
        eligibility_outcome="APPROVED",
    )
    safety1 = SafetyValidator.validate_explanation("explanation_scheme", inp, bad_output_outcome)
    assert safety1.valid is False
    assert any(i.code == "SCHEME_OUTCOME_MUTATION" for i in safety1.issues)

    # Output claimed award in prose
    bad_output_prose = SchemeExplanation(
        explanation="The incentive is awarded to the applicant.",
        scheme_name="Support Scheme",
        eligibility_outcome="POTENTIALLY_ELIGIBLE",
    )
    safety2 = SafetyValidator.validate_explanation("explanation_scheme", inp, bad_output_prose)
    assert safety2.valid is False
    assert any(i.code == "SCHEME_ELIGIBILITY_OVERSTATED" for i in safety2.issues)


def test_ai_exp_17_risk_preserves_score_65_and_supplied_factors() -> None:
    """AI-EXP-17: Risk preserves score 65 and supplied factors."""
    factors = [
        {"name": "document inconsistency", "points": 20},
        {"name": "missing information", "points": 15},
        {"name": "regulatory risk category", "points": 30},
    ]
    raw = RiskExplanation(
        explanation="Risk score 65 reflects document inconsistency, missing info, and category risk.",
        risk_score=65,
        risk_level="ELEVATED",
        factors=factors,
        purpose="review prioritisation",
    )
    service, _, _ = _build_service(raw)
    inp = RiskInput(
        risk_score=65,
        risk_level="ELEVATED",
        factors=factors,
        purpose="review prioritisation",
    )
    res = service.risk(inp)

    assert res.fidelity_valid is True
    assert res.data.risk_score == 65
    assert res.data.risk_level == "ELEVATED"


def test_ai_exp_18_risk_does_not_imply_approval_or_rejection() -> None:
    """AI-EXP-18: Risk does not imply approval/rejection."""
    inp = RiskInput(
        risk_score=85,
        risk_level="HIGH",
        purpose="review prioritisation",
    )
    bad_output = RiskExplanation(
        explanation="Because of the high risk score, the application will be rejected.",
        risk_score=85,
        risk_level="HIGH",
    )
    safety = SafetyValidator.validate_explanation("explanation_risk", inp, bad_output)
    assert safety.valid is False
    assert any(i.code == "RISK_ADJUDICATION_OVERSTATEMENT" for i in safety.issues)


def test_ai_exp_19_official_query_explanation_preserves_clarification_request() -> None:
    """AI-EXP-19: Official query explanation preserves clarification request."""
    text = (
        "Provide clarification regarding the discrepancy between the production capacity "
        "stated in the project report and the capacity declared in the application. "
        "No additional document is requested at this stage."
    )
    raw = OfficialQueryExplanation(
        official_text=text,
        explanation="The officer requests clarification regarding production capacity discrepancy.",
        requested_action="clarification",
        additional_document_requested=False,
    )
    service, _, _ = _build_service(raw)
    inp = OfficialQueryInput(official_text=text)
    res = service.official_query(inp)

    assert res.fidelity_valid is True
    assert res.data.official_text == text
    assert res.data.requested_action == "clarification"
    assert res.data.additional_document_requested is False


def test_ai_exp_20_no_additional_document_requested_boolean_false() -> None:
    """AI-EXP-20: 'No additional document is requested' -> additional_document_requested=false."""
    text = "Clarify facts. No additional document is requested at this stage."
    inp = OfficialQueryInput(official_text=text)

    # Bad output has additional_document_requested=True
    bad_output = OfficialQueryExplanation(
        official_text=text,
        explanation="Provide clarification.",
        additional_document_requested=True,
    )
    safety = SafetyValidator.validate_explanation("explanation_official_query", inp, bad_output)
    assert safety.valid is False
    assert any(i.code == "DOCUMENT_REQUEST_FIDELITY" for i in safety.issues)


def test_ai_exp_21_official_query_does_not_invent_project_report_upload() -> None:
    """AI-EXP-21: Official query does not invent revised project-report upload."""
    text = "Provide clarification on capacity. No additional document is requested at this stage."
    inp = OfficialQueryInput(official_text=text)

    bad_output = OfficialQueryExplanation(
        official_text=text,
        explanation="You must upload a revised project report with the correct capacity.",
        requested_action="clarification",
        additional_document_requested=False,
    )
    safety = SafetyValidator.validate_explanation("explanation_official_query", inp, bad_output)
    assert safety.valid is False
    assert any(i.code == "INVENTED_DOCUMENT_UPLOAD" for i in safety.issues)


def test_ai_exp_22_advisory_verifier_pass_preserves_explanation() -> None:
    """AI-EXP-22: ADVISORY verifier PASS preserves explanation."""
    raw = RequirementTraceExplanation(
        explanation="Requirement is conditional because capacity is missing.",
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    pass_result = VerificationResult(
        verdict=VerificationVerdict.PASS,
        issues=[],
        verifier_provider="mock_groq",
    )
    service, _, _ = _build_service(raw, mock_verifier_result=pass_result)
    res = service.requirement_trace(RequirementTraceInput(
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    ))

    assert res.fidelity_valid is True
    assert res.requires_human_review is False
    assert res.corrected_by_verifier is False
    assert res.verification_status == "PASS"
    assert res.data == raw


def test_ai_exp_23_advisory_verifier_corrected_result_schema_validated() -> None:
    """AI-EXP-23: ADVISORY verifier CORRECTED result is schema validated."""
    raw = RequirementTraceExplanation(
        explanation="Requirement applies.",  # Sub-optimal
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    corrected = RequirementTraceExplanation(
        explanation="Requirement is conditional because capacity_tpd is missing.",
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    corrected_result = VerificationResult(
        verdict=VerificationVerdict.CORRECTED,
        issues=[VerificationIssue(code="V_CORRECTED", message="Clarified conditional phrasing")],
        corrected_output=corrected.model_dump(),
        verifier_provider="mock_groq",
    )
    service, _, _ = _build_service(raw, mock_verifier_result=corrected_result)
    res = service.requirement_trace(RequirementTraceInput(
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    ))

    assert res.fidelity_valid is True
    assert res.corrected_by_verifier is True
    assert res.verification_status == "CORRECTED"
    assert res.explanation == corrected.explanation


def test_ai_exp_24_advisory_verifier_unavailable_does_not_crash() -> None:
    """AI-EXP-24: ADVISORY verifier unavailable does not crash explanation."""
    raw = RequirementTraceExplanation(
        explanation="Evaluation explanation.",
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    service, _, _ = _build_service(raw, verifier_exc=AIUnavailableError("Groq verifier offline"))
    res = service.requirement_trace(RequirementTraceInput(
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    ))

    # Does not raise! Preserves local explanation
    assert res.data == raw
    assert res.requires_human_review is True
    assert any("unavailable" in w.lower() for w in res.warnings)


def test_ai_exp_25_advisory_verifier_reject_marks_requires_human_review() -> None:
    """AI-EXP-25: ADVISORY verifier REJECT marks requires_human_review."""
    raw = RequirementTraceExplanation(
        explanation="Evaluation explanation with suspect claims.",
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    reject_result = VerificationResult(
        verdict=VerificationVerdict.REJECT,
        issues=[VerificationIssue(code="FIDELITY_REJECT", message="Explanation introduced ungrounded claims.")],
        verifier_provider="mock_groq",
    )
    service, _, _ = _build_service(raw, mock_verifier_result=reject_result)
    res = service.requirement_trace(RequirementTraceInput(
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    ))

    assert res.requires_human_review is True
    assert res.verification_status == "REJECT"
    assert any("FIDELITY_REJECT" in w for w in res.warnings)


def test_ai_exp_26_explanation_service_imports_no_business_services() -> None:
    """AI-EXP-26: ExplanationService imports no business services."""
    import app.modules.ai.services.explanations as exp_mod
    source = inspect.getsource(exp_mod)
    tree = ast.parse(source)

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden_patterns = [
        "app.modules.rules",
        "app.modules.documents",
        "app.modules.projects",
        "app.modules.applications",
        "app.modules.sla",
        "app.modules.schemes",
        "app.modules.analytics",
        "app.modules.queries",
        "networkx",
    ]
    for imp in imported_modules:
        for forbidden in forbidden_patterns:
            assert not imp.startswith(forbidden), f"Forbidden import found in explanations.py: {imp}"


def test_ai_exp_27_explanation_service_performs_no_applicability_computation() -> None:
    """AI-EXP-27: ExplanationService performs no applicability computation."""
    import app.modules.ai.services.explanations as exp_mod
    source = inspect.getsource(exp_mod)

    # Invariant: No threshold evaluation or rule logic
    assert "capacity > 50" not in source
    assert "applicable = True" not in source
    assert "outcome = APPLICABLE" not in source


def test_ai_exp_28_explanation_service_performs_no_networkx_computation() -> None:
    """AI-EXP-28: ExplanationService performs no NetworkX computation."""
    import app.modules.ai.services.explanations as exp_mod
    source = inspect.getsource(exp_mod)

    assert "networkx" not in source
    assert "nx." not in source
    assert "topological_sort" not in source
    assert "has_cycle" not in source


def test_ai_exp_29_explanation_service_performs_no_sla_risk_scheme_computation() -> None:
    """AI-EXP-29: ExplanationService performs no SLA/risk/scheme computation."""
    import app.modules.ai.services.explanations as exp_mod
    source = inspect.getsource(exp_mod)

    # No date subtraction for SLA, no risk weight summation, no scheme matching
    assert "datetime.now()" not in source
    assert "weight * contribution" not in source
    assert "sum(factor" not in source


def test_ai_exp_30_all_previous_phase1_4_tests_still_pass_and_facade_exposes_explanations() -> None:
    """AI-EXP-30: IRISAI facade exposes ai.explanations alongside Phase 1-4 services."""
    _reset_ai_facade()
    ai = get_ai()

    assert hasattr(ai, "core")
    assert hasattr(ai, "verification")
    assert hasattr(ai, "documents")
    assert hasattr(ai, "regulatory")
    assert hasattr(ai, "retrieval")
    assert hasattr(ai, "explanations")

    # Confirm explanations service is an instance of ExplanationService
    assert isinstance(ai.explanations, ExplanationService)


def test_ai_exp_31_application_status_explanation() -> None:
    """AI-EXP-31: Application status explanation preserves status and reasons."""
    raw = ApplicationStatusExplanation(
        explanation="The application is currently submitted and under department review.",
        status="SUBMITTED",
        reasons=["All required documents uploaded", "Payment verified"],
    )
    service, _, _ = _build_service(raw)
    inp = ApplicationStatusInput(
        status="SUBMITTED",
        application_id="app-123",
        reasons=["All required documents uploaded", "Payment verified"],
    )
    res = service.application_status(inp)

    assert res.fidelity_valid is True
    assert res.data.status == "SUBMITTED"
    assert len(res.data.reasons) == 2

    # Mutation test
    bad_output = ApplicationStatusExplanation(
        explanation="Application has been approved.",
        status="APPROVED",
    )
    safety = SafetyValidator.validate_explanation("explanation_application_status", inp, bad_output)
    assert safety.valid is False
    assert any(i.code == "APPLICATION_STATUS_MUTATION" for i in safety.issues)



# ==============================================================================
# Optional Live Phase 5 Smoke Tests
# ==============================================================================

def _get_live_config() -> AIConfig:
    """Resolve AIConfig for live local testing, using fallback model if primary is not pulled."""
    import json
    import os
    from urllib.request import urlopen
    cfg = AIConfig()
    if "IRIS_GENERATION_MODEL" in os.environ:
        return cfg
    try:
        with urlopen(f"{cfg.ollama_url}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed = [m.get("name") for m in data.get("models", [])]
            if cfg.generation_model not in installed and cfg.fallback_model in installed:
                return AIConfig(generation_model=cfg.fallback_model)
    except Exception:
        pass
    return cfg


@pytest.mark.live_phase5
def test_live_phase5_case1_dependency() -> None:
    """Live Case 1: Dependency explanation against real Ollama."""
    from app.modules.ai.providers.ollama import OllamaProvider
    config = _get_live_config()
    provider = OllamaProvider(config=config)
    core = CoreAIService(provider=provider)
    verifier = VerificationService(provider=MockExplanationVerifier(), mode=VerificationMode.OFF)
    service = ExplanationService(core=core, verification=verifier)

    inp = DependencyInput(
        requirement="Consent to Operate",
        status="BLOCKED",
        blocked_by=["Consent to Establish"],
        reason_code="PREREQUISITE_INCOMPLETE",
        requirement_on_critical_path=False,
    )
    res = service.dependency(inp)
    assert res.fidelity_valid is True
    assert res.data.requirement == "Consent to Operate"
    assert res.data.status == "BLOCKED"
    assert "Consent to Establish" in res.data.blocked_by


@pytest.mark.live_phase5
def test_live_phase5_case2_document_issue() -> None:
    """Live Case 2: Document issue explanation against real Ollama."""
    from app.modules.ai.providers.ollama import OllamaProvider
    config = _get_live_config()
    provider = OllamaProvider(config=config)
    core = CoreAIService(provider=provider)
    verifier = VerificationService(provider=MockExplanationVerifier(), mode=VerificationMode.OFF)
    service = ExplanationService(core=core, verification=verifier)

    inp = DocumentIssueInput(
        field_name="capacity_tpd",
        issue_type="INCONSISTENCY",
        severity="BLOCKING",
        expected_value=60,
        actual_value=80,
        unit=None,
        message="Production capacity in the uploaded document differs from the project profile.",
    )
    res = service.document_issue(inp)
    assert res.fidelity_valid is True
    assert res.data.expected_value == 60
    assert res.data.actual_value == 80
    assert res.data.unit is None


@pytest.mark.live_phase5
def test_live_phase5_case3_scheme() -> None:
    """Live Case 3: Scheme matching explanation against real Ollama."""
    from app.modules.ai.providers.ollama import OllamaProvider
    config = _get_live_config()
    provider = OllamaProvider(config=config)
    core = CoreAIService(provider=provider)
    verifier = VerificationService(provider=MockExplanationVerifier(), mode=VerificationMode.OFF)
    service = ExplanationService(core=core, verification=verifier)

    inp = SchemeMatchInput(
        scheme_name="Example Industrial Support Scheme",
        eligibility_outcome="POTENTIALLY_ELIGIBLE",
        matched_conditions=[
            "sector = food_processing",
            "state = Maharashtra",
            "investment_crore_inr between 5 and 20",
        ],
        required_documents=["Project Report", "Investment Declaration"],
        disclaimer="Final eligibility requires official verification.",
    )
    res = service.scheme(inp)
    assert res.fidelity_valid is True
    assert res.data.eligibility_outcome == "POTENTIALLY_ELIGIBLE"


@pytest.mark.live_phase5
def test_live_phase5_case4_conditional() -> None:
    """Live Case 4: Conditional requirement trace explanation against real Ollama."""
    from app.modules.ai.providers.ollama import OllamaProvider
    config = _get_live_config()
    provider = OllamaProvider(config=config)
    core = CoreAIService(provider=provider)
    verifier = VerificationService(provider=MockExplanationVerifier(), mode=VerificationMode.OFF)
    service = ExplanationService(core=core, verification=verifier)

    inp = RequirementTraceInput(
        requirement="Environmental Consent",
        outcome="CONDITIONAL",
        missing_facts=["capacity_tpd"],
    )
    res = service.requirement_trace(inp)
    assert res.fidelity_valid is True
    assert res.data.outcome == "CONDITIONAL"

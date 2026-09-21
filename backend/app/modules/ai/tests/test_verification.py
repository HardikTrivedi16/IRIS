"""Phase 2 Verification Layer Tests for the IRIS AI Module.

All standard unit and contract tests run offline using mocks/dependency injection.
The optional live Groq smoke tests are marked with @pytest.mark.live_groq and
are skipped by default during normal offline test runs.
"""

import os
from typing import Any
from unittest.mock import MagicMock, patch
import pytest
from pydantic import BaseModel, Field

from app.modules.ai import (
    AIConfig,
    AIError,
    AIInvalidOutputError,
    AITimeoutError,
    AIUnavailableError,
    AIVerificationError,
    IRISAI,
    VerificationIssue,
    VerificationMode,
    VerificationOutcome,
    VerificationResult,
    VerificationService,
    VerificationVerdict,
    _reset_ai_facade,
    get_ai,
)
from app.modules.ai.providers import (
    BaseVerificationProvider,
    GroqVerifier,
    NoOpVerifier,
)


class SampleTargetSchema(BaseModel):
    """Target schema for testing corrected output re-validation."""
    investment_condition: str
    min_crore: float
    max_crore: float


class MockVerificationProvider(BaseVerificationProvider):
    """Mock verification provider for testing VerificationService policies."""

    def __init__(self, result: VerificationResult | None = None, exc_to_raise: Exception | None = None) -> None:
        self.result = result or VerificationResult(
            verdict=VerificationVerdict.PASS,
            issues=[],
            corrected_output=None,
            verifier_provider="mock_verifier",
            verifier_model="mock_model",
        )
        self.exc_to_raise = exc_to_raise
        self.verify_calls: list[dict[str, Any]] = []

    def verify(
        self,
        task_type: str,
        authoritative_input: Any,
        local_output: Any,
        output_schema: type[BaseModel] | None = None,
    ) -> VerificationResult:
        self.verify_calls.append({
            "task_type": task_type,
            "authoritative_input": authoritative_input,
            "local_output": local_output,
            "output_schema": output_schema,
        })
        if self.exc_to_raise:
            raise self.exc_to_raise
        return self.result


@pytest.fixture(autouse=True)
def clean_facade():
    """Ensure clean facade state for every test."""
    _reset_ai_facade()
    yield
    _reset_ai_facade()


# ==============================================================================
# TEST AI-VERIFY-01: OFF mode does not call external verifier and preserves local output.
# ==============================================================================
def test_ai_verify_01_off_mode_preserves_local_output():
    mock_provider = MockVerificationProvider()
    service = VerificationService(provider=mock_provider, mode=VerificationMode.OFF)

    local_out = {"text": "Consent to Establish applies"}
    outcome = service.verify("req_check", {"authoritative": "data"}, local_out)

    assert isinstance(outcome, VerificationOutcome)
    assert outcome.mode == VerificationMode.OFF
    assert outcome.verification_performed is False
    assert outcome.effective_output == local_out
    assert outcome.result is None
    assert len(mock_provider.verify_calls) == 0


# ==============================================================================
# TEST AI-VERIFY-02: NoOpVerifier performs zero network calls and returns predictable PASS-style result.
# ==============================================================================
def test_ai_verify_02_noop_verifier_returns_pass_without_network():
    noop = NoOpVerifier()
    res = noop.verify("any_task", {"source": "doc"}, {"output": "local"})

    assert isinstance(res, VerificationResult)
    assert res.verdict == VerificationVerdict.PASS
    assert res.verifier_provider == "noop"
    assert res.verifier_model == "none"
    assert res.issues == []


# ==============================================================================
# TEST AI-VERIFY-03: ADVISORY + PASS preserves original local output.
# ==============================================================================
def test_ai_verify_03_advisory_pass_preserves_original_output():
    pass_result = VerificationResult(
        verdict=VerificationVerdict.PASS,
        issues=[],
        corrected_output=None,
        verifier_provider="mock",
    )
    mock_provider = MockVerificationProvider(result=pass_result)
    service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)

    local_out = "Valid regulatory summary"
    outcome = service.verify("summary_check", "Official text", local_out)

    assert outcome.mode == VerificationMode.ADVISORY
    assert outcome.verification_performed is True
    assert outcome.effective_output == local_out
    assert outcome.result.verdict == VerificationVerdict.PASS
    assert outcome.corrected_by_verifier is False
    assert outcome.requires_human_review is False


# ==============================================================================
# TEST AI-VERIFY-04: ADVISORY + CORRECTED returns corrected output.
# ==============================================================================
def test_ai_verify_04_advisory_corrected_returns_corrected_output():
    corrected_result = VerificationResult(
        verdict=VerificationVerdict.CORRECTED,
        issues=[VerificationIssue(code="NUMERIC_FIDELITY", field="val", message="Fixed typo")],
        corrected_output={"val": 20},
        verifier_provider="mock",
    )
    mock_provider = MockVerificationProvider(result=corrected_result)
    service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)

    outcome = service.verify("calc_check", {"val": 20}, {"val": "2:00"})

    assert outcome.verification_performed is True
    assert outcome.result.verdict == VerificationVerdict.CORRECTED
    assert outcome.corrected_by_verifier is True
    assert outcome.effective_output == {"val": 20}
    assert outcome.requires_human_review is True


# ==============================================================================
# TEST AI-VERIFY-05: Corrected structured output is validated against supplied Pydantic schema.
# ==============================================================================
def test_ai_verify_05_corrected_output_validated_against_pydantic_schema():
    corrected_data = {
        "investment_condition": "between 5 and 20 crore INR",
        "min_crore": 5.0,
        "max_crore": 20.0,
    }
    corrected_result = VerificationResult(
        verdict=VerificationVerdict.CORRECTED,
        issues=[VerificationIssue(code="NUMERIC_FIDELITY", field="max_crore", message="Restored 20.0")],
        corrected_output=corrected_data,
        verifier_provider="mock",
    )
    mock_provider = MockVerificationProvider(result=corrected_result)
    service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)

    outcome = service.verify(
        task_type="condition_extraction",
        authoritative_input="between 5 and 20 crore INR",
        local_output={"investment_condition": "between 5 and 2:00 crore INR", "min_crore": 5.0, "max_crore": 2.0},
        output_schema=SampleTargetSchema,
    )

    assert isinstance(outcome.effective_output, SampleTargetSchema)
    assert outcome.effective_output.max_crore == 20.0
    assert outcome.corrected_by_verifier is True


# ==============================================================================
# TEST AI-VERIFY-06: Invalid corrected output is rejected.
# ==============================================================================
def test_ai_verify_06_invalid_corrected_output_rejected():
    # Corrected data is invalid according to SampleTargetSchema (missing required min_crore/max_crore)
    invalid_correction = {
        "investment_condition": "corrupted",
        "min_crore": "not-a-number",
    }
    corrected_result = VerificationResult(
        verdict=VerificationVerdict.CORRECTED,
        issues=[VerificationIssue(code="CORRECTION", field=None, message="Attempted fix")],
        corrected_output=invalid_correction,
        verifier_provider="mock",
    )
    mock_provider = MockVerificationProvider(result=corrected_result)
    service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)

    with pytest.raises(AIInvalidOutputError) as exc_info:
        service.verify(
            task_type="condition_check",
            authoritative_input="official text",
            local_output="local text",
            output_schema=SampleTargetSchema,
        )
    assert "Proposed correction failed validation against SampleTargetSchema" in str(exc_info.value)


# ==============================================================================
# TEST AI-VERIFY-07: ADVISORY + verifier unavailable returns original local output
#                     with warning/status rather than crashing.
# ==============================================================================
def test_ai_verify_07_advisory_verifier_unavailable_degrades_gracefully():
    mock_provider = MockVerificationProvider(exc_to_raise=AIUnavailableError("Groq service 503"))
    service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)

    local_out = {"text": "Original local result"}
    outcome = service.verify("task", "auth", local_out)

    assert outcome.effective_output == local_out
    assert outcome.mode == VerificationMode.ADVISORY
    assert outcome.verification_performed is False
    assert outcome.requires_human_review is True
    assert outcome.warning is not None
    assert "Groq service 503" in outcome.warning


# ==============================================================================
# TEST AI-VERIFY-08: REQUIRED + verifier unavailable raises controlled AIVerificationError.
# ==============================================================================
def test_ai_verify_08_required_verifier_unavailable_raises_ai_verification_error():
    mock_provider = MockVerificationProvider(exc_to_raise=AITimeoutError("Request timed out"))
    service = VerificationService(provider=mock_provider, mode=VerificationMode.REQUIRED)

    with pytest.raises(AIVerificationError) as exc_info:
        service.verify("task", "auth", "local")
    assert "Required verification failed due to provider unavailability" in str(exc_info.value)


# ==============================================================================
# TEST AI-VERIFY-09: REJECT is NEVER silently treated as PASS.
# ==============================================================================
def test_ai_verify_09_reject_never_treated_as_pass():
    reject_result = VerificationResult(
        verdict=VerificationVerdict.REJECT,
        issues=[VerificationIssue(code="HALLUCINATED_REQUIREMENT", field=None, message="Invented statutory NOC")],
        corrected_output=None,
        verifier_provider="mock",
    )
    mock_provider = MockVerificationProvider(result=reject_result)

    # 1. In ADVISORY mode, result must stay REJECT with requires_human_review=True, never converted to PASS
    advisory_service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)
    outcome = advisory_service.verify("task", "auth", "local")
    assert outcome.result.verdict == VerificationVerdict.REJECT
    assert outcome.requires_human_review is True
    assert outcome.result.verdict != VerificationVerdict.PASS

    # 2. In REQUIRED mode, REJECT raises controlled AIVerificationError
    required_service = VerificationService(provider=mock_provider, mode=VerificationMode.REQUIRED)
    with pytest.raises(AIVerificationError) as exc_info:
        required_service.verify("task", "auth", "local")
    assert "Verification rejected output in REQUIRED mode" in str(exc_info.value)


# ==============================================================================
# TEST AI-VERIFY-10: Raw Groq/provider exceptions do not escape the public AI-module boundary.
# ==============================================================================
def test_ai_verify_10_raw_exceptions_do_not_escape_boundary():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("Low-level connection reset")

    config = AIConfig(verifier_enabled=True, verifier_provider="groq", groq_api_key="test-key")
    verifier = GroqVerifier(config=config, client=mock_client)
    service = VerificationService(provider=verifier, mode=VerificationMode.REQUIRED)

    with pytest.raises(AIVerificationError) as exc_info:
        service.verify("task", "auth", "local")

    assert not issubclass(type(exc_info.value), RuntimeError)
    assert isinstance(exc_info.value, AIError)


# ==============================================================================
# TEST AI-VERIFY-11: Importing/constructing GroqVerifier performs no inference/network request.
# ==============================================================================
def test_ai_verify_11_constructing_groq_verifier_makes_no_network_request():
    # Groq SDK is imported lazily only by _get_client()/verify(). Construction must
    # therefore work offline even when the optional SDK is not installed.
    config = AIConfig(verifier_enabled=True, verifier_provider="groq", groq_api_key="fake-key")
    verifier = GroqVerifier(config=config)
    assert verifier is not None
    assert verifier._injected_client is None


# ==============================================================================
# TEST AI-VERIFY-12: Missing GROQ_API_KEY does not break IRIS when verifier is disabled.
# ==============================================================================
def test_ai_verify_12_missing_key_does_not_break_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        config = AIConfig(verifier_enabled=False, groq_api_key=None)
        ai = get_ai(config=config)

        assert ai is not None
        assert ai.verification is not None
        assert ai.verification.mode == VerificationMode.OFF

        # Verifying in OFF mode works safely
        outcome = ai.verification.verify("task", "auth", {"out": 1})
        assert outcome.effective_output == {"out": 1}
        assert outcome.mode == VerificationMode.OFF


# ==============================================================================
# TEST AI-VERIFY-13: Missing GROQ_API_KEY with enabled Groq verification fails
#                     only when verification is requested and uses a controlled AI error.
# ==============================================================================
def test_ai_verify_13_missing_key_fails_on_demand_with_controlled_error():
    with patch.dict(os.environ, {}, clear=True):
        config = AIConfig(verifier_enabled=True, verifier_provider="groq", groq_api_key=None)
        # Constructing facade succeeds
        ai = get_ai(config=config)
        assert ai is not None

        # Calling verify in REQUIRED mode raises controlled error
        ai.verification.mode = VerificationMode.REQUIRED
        with pytest.raises(AIVerificationError) as exc_info:
            ai.verification.verify("task", "auth", "local")
        assert "GROQ_API_KEY is not configured" in str(exc_info.value)


# ==============================================================================
# TEST AI-VERIFY-14: Changing verifier provider/configuration requires no changes
#                     to calling service code.
# ==============================================================================
def test_ai_verify_14_changing_provider_requires_no_code_changes():
    # Calling code uses identical signature regardless of provider
    noop_provider = NoOpVerifier()
    service_noop = VerificationService(provider=noop_provider, mode=VerificationMode.ADVISORY)
    res_noop = service_noop.verify("task_x", "auth_doc", "local_text")
    assert res_noop.effective_output == "local_text"

    mock_provider = MockVerificationProvider()
    service_mock = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)
    res_mock = service_mock.verify("task_x", "auth_doc", "local_text")
    assert res_mock.effective_output == "local_text"


# ==============================================================================
# TEST AI-VERIFY-15: All Phase 1 tests still pass (tested in CI / test suite runner).
# ==============================================================================
def test_ai_verify_15_facade_exposes_core_and_verification():
    ai = get_ai()
    assert hasattr(ai, "core")
    assert hasattr(ai, "verification")
    assert callable(ai.core.generate)
    assert callable(ai.verification.verify)


# ==============================================================================
# TEST AI-VERIFY-16: A mocked verifier correction of "5 to 2:00 crore" to
#                     "5 to 20 crore" can be returned and validated correctly.
# ==============================================================================
def test_ai_verify_16_correction_2_00_to_20_crore():
    corrected_result = VerificationResult(
        verdict=VerificationVerdict.CORRECTED,
        issues=[
            VerificationIssue(
                code="NUMERIC_FIDELITY",
                field="investment_condition",
                message="Corrected formatting typo '2:00' to authoritative value '20'.",
            )
        ],
        corrected_output="Investment between 5 and 20 crore INR.",
        verifier_provider="mock_groq",
        verifier_model="openai/gpt-oss-120b",
    )
    mock_provider = MockVerificationProvider(result=corrected_result)
    service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)

    authoritative_input = "investment between 5 and 20 crore INR"
    local_output = "Investment between 5 and 2:00 crore INR."

    outcome = service.verify(
        task_type="condition_statement",
        authoritative_input=authoritative_input,
        local_output=local_output,
    )

    assert outcome.result.verdict == VerificationVerdict.CORRECTED
    assert outcome.corrected_by_verifier is True
    assert outcome.effective_output == "Investment between 5 and 20 crore INR."
    assert len(outcome.result.issues) == 1
    assert outcome.result.issues[0].code == "NUMERIC_FIDELITY"


# ==============================================================================
# TEST AI-VERIFY-17: A verifier REJECT result for an unsupported relationship is
#                     preserved as REJECT/failure and is not converted to PASS.
# ==============================================================================
def test_ai_verify_17_unsupported_relationship_reject_preserved():
    authoritative_input = {
        "requirement": "Consent to Operate",
        "status": "BLOCKED",
        "blocked_by": ["Consent to Establish", "Fire Safety Review"],
        "critical_path": True,
    }
    local_output = "Both blockers are critical-path dependencies."

    reject_result = VerificationResult(
        verdict=VerificationVerdict.REJECT,
        issues=[
            VerificationIssue(
                code="UNSUPPORTED_RELATIONSHIP",
                field="critical_path",
                message="Authoritative input does not establish that individual blocker nodes belong to the critical path.",
            )
        ],
        corrected_output=None,
        verifier_provider="mock_groq",
        verifier_model="openai/gpt-oss-120b",
    )
    mock_provider = MockVerificationProvider(result=reject_result)
    service = VerificationService(provider=mock_provider, mode=VerificationMode.ADVISORY)

    outcome = service.verify(
        task_type="dependency_explanation",
        authoritative_input=authoritative_input,
        local_output=local_output,
    )

    assert outcome.result.verdict == VerificationVerdict.REJECT
    assert outcome.result.verdict != VerificationVerdict.PASS
    assert outcome.requires_human_review is True
    assert "UNSUPPORTED_RELATIONSHIP" in [i.code for i in outcome.result.issues]


# ==============================================================================
# OPTIONAL LIVE GROQ SMOKE TESTS
# Skipped by default in offline CI. Run manually with:
# pytest app/modules/ai/tests/test_verification.py -v -m "live_groq"
# ==============================================================================
@pytest.mark.live_groq
def test_live_groq_smoke_synthetic_numeric_correction():
    """Optional live test against Groq using synthetic numerical typo."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY environment variable not set")

    config = AIConfig(
        verifier_enabled=True,
        verifier_provider="groq",
        groq_api_key=api_key,
        verifier_model="openai/gpt-oss-120b",
    )
    verifier = GroqVerifier(config=config)
    service = VerificationService(provider=verifier, mode=VerificationMode.ADVISORY, config=config)

    authoritative = {"investment_condition": "between 5 and 20 crore INR"}
    local = {"explanation": "Investment must be between 5 and 2:00 crore INR."}

    outcome = service.verify("numeric_fidelity_check", authoritative, local)

    assert outcome.result is not None
    # Model MUST NOT return PASS for this fidelity error
    assert outcome.result.verdict != VerificationVerdict.PASS
    assert outcome.result.verdict in (VerificationVerdict.CORRECTED, VerificationVerdict.REJECT)


@pytest.mark.live_groq
def test_live_groq_smoke_synthetic_unsupported_critical_path():
    """Optional live test against Groq verifying unsupported blocker critical path assumption."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY environment variable not set")

    config = AIConfig(
        verifier_enabled=True,
        verifier_provider="groq",
        groq_api_key=api_key,
        verifier_model="openai/gpt-oss-120b",
    )
    verifier = GroqVerifier(config=config)
    service = VerificationService(provider=verifier, mode=VerificationMode.ADVISORY, config=config)

    authoritative = {
        "requirement": "Consent to Operate",
        "status": "BLOCKED",
        "blocked_by": ["Consent to Establish", "Fire Safety Review"],
        "critical_path": True,
    }
    local = {"explanation": "Both blockers are critical-path dependencies."}

    outcome = service.verify("dependency_fidelity_check", authoritative, local)

    assert outcome.result is not None
    # Model MUST NOT return PASS for unsupported graph assumption
    assert outcome.result.verdict != VerificationVerdict.PASS
    assert outcome.result.verdict in (VerificationVerdict.REJECT, VerificationVerdict.CORRECTED)

# ==============================================================================
# VERIFICATION CONFIG HARDENING: noop provider cannot masquerade as verification
# ==============================================================================
def test_verifier_enabled_with_none_provider_stays_off():
    config = AIConfig(verifier_enabled=True, verifier_provider="none")
    ai = get_ai(config=config)
    assert ai.verification.mode == VerificationMode.OFF
    assert ai.regulatory_verification.mode == VerificationMode.OFF

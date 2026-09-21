"""Phase 1 Contract and Offline Unit Tests for the IRIS AI Module.

All standard tests run offline with mocks/dependency injection.
The optional live Ollama smoke test is marked with @pytest.mark.live_ollama
and is excluded from default offline pytest runs.
"""

from typing import Any
from unittest.mock import MagicMock, patch
import pytest
import requests
from pydantic import BaseModel, Field

from app.modules.ai import (
    AIConfig,
    AIError,
    AIInvalidOutputError,
    AITimeoutError,
    AIUnavailableError,
    BaseAIProvider,
    IRISAI,
    _reset_ai_facade,
    get_ai,
)
from app.modules.ai.providers.ollama import OllamaProvider


class SampleStructuredOutput(BaseModel):
    """Test schema for structured extraction."""
    summary: str
    confidence: float
    tags: list[str] = Field(default_factory=list)


class MockAIProvider(BaseAIProvider):
    """Simple in-memory mock provider for testing facade and service delegation."""

    def __init__(self, generation_response: str = "mocked response") -> None:
        self.generation_response = generation_response
        self.generate_calls: list[dict[str, Any]] = []
        self.structured_calls: list[dict[str, Any]] = []
        self.embed_calls: list[list[str]] = []
        self.health_status = True

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> str:
        self.generate_calls.append({
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "think": think,
        })
        return self.generation_response

    def generate_structured(
        self,
        prompt: str,
        schema: type[Any],
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> Any:
        self.structured_calls.append({
            "prompt": prompt,
            "schema": schema,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "think": think,
        })
        return schema(summary="mocked summary", confidence=0.95, tags=["mock", "test"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        if not texts:
            return []
        return [[0.1, 0.2, 0.3] for _ in texts]

    def health_check(self) -> bool:
        return self.health_status


@pytest.fixture(autouse=True)
def clean_facade():
    """Ensure clean facade state for every test."""
    _reset_ai_facade()
    yield
    _reset_ai_facade()


# ==============================================================================
# TEST AI-CORE-01: IRISAI can be constructed using a mocked provider.
# ==============================================================================
def test_ai_core_01_constructed_with_mocked_provider():
    mock_provider = MockAIProvider()
    ai = IRISAI(provider=mock_provider)

    assert ai is not None
    assert ai.core is not None
    assert ai.provider is mock_provider


# ==============================================================================
# TEST AI-CORE-02: generate() returns the provider result.
# ==============================================================================
def test_ai_core_02_generate_returns_provider_result():
    expected_text = "Analysis completed successfully."
    mock_provider = MockAIProvider(generation_response=expected_text)
    ai = get_ai(provider=mock_provider)

    result = ai.core.generate("Check requirement compliance", temperature=0.0)

    assert result == expected_text
    assert len(mock_provider.generate_calls) == 1
    assert mock_provider.generate_calls[0]["prompt"] == "Check requirement compliance"
    assert mock_provider.generate_calls[0]["temperature"] == 0.0


# ==============================================================================
# TEST AI-CORE-03: generate_structured() returns a validated Pydantic object.
# ==============================================================================
def test_ai_core_03_generate_structured_returns_validated_pydantic():
    mock_provider = MockAIProvider()
    ai = get_ai(provider=mock_provider)

    result = ai.core.generate_structured(
        prompt="Extract information from document",
        schema=SampleStructuredOutput,
    )

    assert isinstance(result, SampleStructuredOutput)
    assert result.summary == "mocked summary"
    assert result.confidence == 0.95
    assert result.tags == ["mock", "test"]


# ==============================================================================
# TEST AI-CORE-04: embed() returns vectors.
# ==============================================================================
def test_ai_core_04_embed_returns_vectors():
    mock_provider = MockAIProvider()
    ai = get_ai(provider=mock_provider)

    texts = ["Regulation 1 text", "Regulation 2 text"]
    embeddings = ai.core.embed(texts)

    assert isinstance(embeddings, list)
    assert len(embeddings) == 2
    assert all(isinstance(vec, list) for vec in embeddings)
    assert len(embeddings[0]) == 3


# ==============================================================================
# TEST AI-CORE-05: Empty embedding input returns [].
# ==============================================================================
def test_ai_core_05_empty_embedding_input_returns_empty_list():
    mock_provider = MockAIProvider()
    ai = get_ai(provider=mock_provider)

    result = ai.core.embed([])
    assert result == []


# ==============================================================================
# TEST AI-CORE-06: Provider/network failures become AI module exceptions.
#                  Raw requests exceptions must not escape.
# ==============================================================================
def test_ai_core_06_network_failures_become_ai_exceptions():
    mock_session = MagicMock(spec=requests.Session)
    config = AIConfig(max_retries=1)
    provider = OllamaProvider(config=config, session=mock_session)
    ai = get_ai(provider=provider)

    # 1. Test ConnectionError -> AIUnavailableError
    mock_session.post.side_effect = requests.exceptions.ConnectionError("Connection refused")
    with pytest.raises(AIUnavailableError) as exc_info:
        ai.core.generate("test prompt")
    assert "Unable to connect" in str(exc_info.value) or "Ollama request failed" in str(exc_info.value)
    assert not issubclass(type(exc_info.value), requests.exceptions.RequestException)

    # 2. Test Timeout -> AITimeoutError
    mock_session.post.side_effect = requests.exceptions.ReadTimeout("Read timed out")
    with pytest.raises(AITimeoutError) as exc_info:
        ai.core.generate("test prompt")
    assert "timed out" in str(exc_info.value)
    assert not issubclass(type(exc_info.value), requests.exceptions.RequestException)

    # 3. Test HTTP 500 error -> AIUnavailableError
    error_response = MagicMock(status_code=500, text="Internal Server Error")
    mock_session.post.side_effect = None
    mock_session.post.return_value = error_response
    with pytest.raises(AIUnavailableError) as exc_info:
        ai.core.generate("test prompt")
    assert "error status 500" in str(exc_info.value) or "Ollama request failed" in str(exc_info.value)


# ==============================================================================
# TEST AI-CORE-07: Configuration can select qwen3:8b or qwen3:4b
#                  without changing service code.
# ==============================================================================
def test_ai_core_07_config_selects_model_without_code_changes():
    mock_session = MagicMock(spec=requests.Session)
    success_response = MagicMock(status_code=200)
    success_response.json.return_value = {"message": {"content": "ok"}}
    mock_session.post.return_value = success_response

    # Test with primary model qwen3:8b
    config_8b = AIConfig(generation_model="qwen3:8b")
    provider_8b = OllamaProvider(config=config_8b, session=mock_session)
    ai_8b = get_ai(provider=provider_8b)
    ai_8b.core.generate("prompt 1")
    call_args_8b = mock_session.post.call_args[1]["json"]
    assert call_args_8b["model"] == "qwen3:8b"

    # Test with fallback model qwen3:4b
    config_4b = AIConfig(generation_model="qwen3:4b")
    provider_4b = OllamaProvider(config=config_4b, session=mock_session)
    ai_4b = get_ai(provider=provider_4b)
    ai_4b.core.generate("prompt 2")
    call_args_4b = mock_session.post.call_args[1]["json"]
    assert call_args_4b["model"] == "qwen3:4b"


# ==============================================================================
# TEST AI-CORE-08: Importing the AI module and obtaining a facade does NOT contact Ollama.
# ==============================================================================
def test_ai_core_08_import_and_get_facade_does_not_contact_network():
    with patch("requests.Session.post") as mock_post, patch("requests.Session.get") as mock_get:
        # Import and instantiate
        from app.modules.ai import get_ai, IRISAI
        ai = get_ai()

        assert ai is not None
        assert isinstance(ai, IRISAI)
        mock_post.assert_not_called()
        mock_get.assert_not_called()


# ==============================================================================
# TEST AI-CORE-09: Invalid structured model output produces AIInvalidOutputError
#                  instead of returning malformed data.
# ==============================================================================
def test_ai_core_09_invalid_structured_output_raises_ai_invalid_output_error():
    mock_session = MagicMock(spec=requests.Session)
    mock_response = MagicMock(status_code=200)
    mock_session.post.return_value = mock_response

    config = AIConfig()
    provider = OllamaProvider(config=config, session=mock_session)
    ai = get_ai(provider=provider)

    # 1. Output violates Pydantic schema (missing required field 'summary', wrong type for 'confidence')
    mock_response.json.return_value = {
        "message": {
            "content": '{"confidence": "not-a-float"}'
        }
    }
    with pytest.raises(AIInvalidOutputError) as exc_info:
        ai.core.generate_structured("prompt", SampleStructuredOutput)
    assert "failed validation against schema SampleStructuredOutput" in str(exc_info.value)

    # 2. Output is malformed non-JSON
    mock_response.json.return_value = {
        "message": {
            "content": "This is raw unformatted text without any JSON structure"
        }
    }
    with pytest.raises(AIInvalidOutputError) as exc_info:
        ai.core.generate_structured("prompt", SampleStructuredOutput)
    assert "failed validation against schema SampleStructuredOutput" in str(exc_info.value)


# ==============================================================================
# TEST AI-CORE-10: Empty embedding input does not make an HTTP request.
# ==============================================================================
def test_ai_core_10_empty_embedding_makes_no_http_request():
    mock_session = MagicMock(spec=requests.Session)
    config = AIConfig()
    provider = OllamaProvider(config=config, session=mock_session)
    ai = get_ai(provider=provider)

    result = ai.core.embed([])

    assert result == []
    mock_session.post.assert_not_called()
    mock_session.get.assert_not_called()


# ==============================================================================
# RETRY BEHAVIOR TEST: Verify 1 retry = 2 attempts total for retryable errors
# ==============================================================================
def test_retry_behavior_max_retries_one_equals_two_attempts():
    mock_session = MagicMock(spec=requests.Session)
    # Fail once with 503 (retryable), succeed on 2nd attempt
    fail_response = MagicMock(status_code=503, text="Service Unavailable")
    success_response = MagicMock(status_code=200)
    success_response.json.return_value = {"message": {"content": "recovered"}}
    mock_session.post.side_effect = [fail_response, success_response]

    config = AIConfig(max_retries=1)
    provider = OllamaProvider(config=config, session=mock_session)

    res = provider.generate("hello")
    assert res == "recovered"
    assert mock_session.post.call_count == 2


# ==============================================================================
# OPTIONAL LIVE OLLAMA SMOKE TEST
# Excluded from default runs. Run manually with:
# pytest app/modules/ai/tests/test_core.py -v -m "live_ollama"
# ==============================================================================
@pytest.mark.live_ollama
def test_live_ollama_smoke():
    """Optional smoke test against live Ollama daemon."""
    ai = get_ai()

    # 1. Health check
    is_healthy = ai.core.health()
    if not is_healthy:
        pytest.skip("Local Ollama daemon is not reachable at configured URL")

    # 2. Structured generation test
    structured_res = ai.core.generate_structured(
        prompt="Output a summary with confidence=1.0 and tags=['smoke_test']",
        schema=SampleStructuredOutput,
    )
    assert isinstance(structured_res, SampleStructuredOutput)
    assert structured_res.summary is not None

    # 3. Embedding test
    embeddings = ai.core.embed(["IRIS Industrial Regulatory Intelligence System"])
    assert len(embeddings) == 1
    assert len(embeddings[0]) > 0

# ==============================================================================
# AI CORE HARDENING: master AI switch is actually enforced
# ==============================================================================
def test_ai_core_master_switch_disables_all_inference_and_health():
    provider = MockAIProvider()
    ai = get_ai(config=AIConfig(ai_enabled=False), provider=provider)

    with pytest.raises(AIUnavailableError, match="IRIS_AI_ENABLED=false"):
        ai.core.generate("hello")
    with pytest.raises(AIUnavailableError, match="IRIS_AI_ENABLED=false"):
        ai.core.generate_structured("hello", SampleStructuredOutput)
    with pytest.raises(AIUnavailableError, match="IRIS_AI_ENABLED=false"):
        ai.core.embed(["hello"])
    assert ai.core.health() is False
    assert provider.generate_calls == []

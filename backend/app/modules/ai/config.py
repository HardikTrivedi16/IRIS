"""Configuration for the IRIS AI module."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIConfig(BaseSettings):
    """Configuration settings for IRIS AI module.

    Environment variables override defaults without requiring a .env file.
    Does not mutate environment variables. Independently constructible for testing
    and dependency injection.
    """

    ai_enabled: bool = Field(
        default=True,
        validation_alias="IRIS_AI_ENABLED",
        description="Master switch to enable/disable AI operations.",
    )
    ollama_url: str = Field(
        default="http://localhost:11434",
        validation_alias="IRIS_OLLAMA_URL",
        description="Base URL for the local Ollama daemon.",
    )
    generation_model: str = Field(
        default="qwen3:8b",
        validation_alias="IRIS_GENERATION_MODEL",
        description="Primary local generation model tag.",
    )
    fallback_model: str = Field(
        default="qwen3:4b",
        validation_alias="IRIS_FALLBACK_MODEL",
        description="Fallback local generation model tag.",
    )
    embedding_model: str = Field(
        default="qwen3-embedding:0.6b",
        validation_alias="IRIS_EMBEDDING_MODEL",
        description="Local embedding model tag.",
    )
    timeout_seconds: int = Field(
        default=300,
        gt=0,
        validation_alias="IRIS_AI_TIMEOUT_SECONDS",
        description="HTTP request timeout in seconds.",
    )
    max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        validation_alias="IRIS_AI_MAX_RETRIES",
        description="Maximum retry attempts on retryable network/server failures (1 = 1 retry, 2 attempts total).",
    )

    # Verification configuration (Phase 2)
    verifier_enabled: bool = Field(
        default=False,
        validation_alias="IRIS_VERIFIER_ENABLED",
        description="Whether secondary verification is enabled.",
    )
    verifier_provider: Literal["none", "noop", "groq"] = Field(
        default="none",
        validation_alias="IRIS_VERIFIER_PROVIDER",
        description="Name of the verification provider (none, noop, groq).",
    )
    verifier_model: str = Field(
        default="openai/gpt-oss-120b",
        validation_alias="IRIS_VERIFIER_MODEL",
        description="Model tag used for secondary verification.",
    )
    verifier_timeout_seconds: int = Field(
        default=30,
        gt=0,
        validation_alias="IRIS_VERIFIER_TIMEOUT_SECONDS",
        description="Timeout in seconds for verification requests.",
    )
    verifier_max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        validation_alias="IRIS_VERIFIER_MAX_RETRIES",
        description="Maximum retry attempts for verification requests.",
    )
    document_low_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        validation_alias="IRIS_DOCUMENT_LOW_CONFIDENCE_THRESHOLD",
        description="Advisory confidence threshold below which extracted document fields require human confirmation.",
    )
    rule_low_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        validation_alias="IRIS_RULE_LOW_CONFIDENCE_THRESHOLD",
        description="Advisory confidence threshold below which AI-authored candidate fields require reviewer attention.",
    )

    groq_api_key: str | None = Field(
        default=None,
        validation_alias="GROQ_API_KEY",
        description="Groq API key for Groq verification provider.",
    )

    model_config = SettingsConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

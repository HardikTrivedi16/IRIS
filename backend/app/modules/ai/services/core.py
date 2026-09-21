"""Core AI Service for IRIS.

Provides the primary interface for AI generation, structured extraction,
and embedding operations by delegating to the configured BaseAIProvider.
Keeps service logic clean and decoupled from provider-specific networking.
"""

from typing import TypeVar
from pydantic import BaseModel

from app.modules.ai.exceptions import AIUnavailableError
from app.modules.ai.providers.base import BaseAIProvider

T = TypeVar("T", bound=BaseModel)


class CoreAIService:
    """Core AI Service wrapping a BaseAIProvider."""

    def __init__(self, provider: BaseAIProvider, enabled: bool = True) -> None:
        self._provider = provider
        self._enabled = enabled

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise AIUnavailableError(
                "IRIS AI operations are disabled by IRIS_AI_ENABLED=false."
            )

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> str:
        """Generate unstructured text from prompt."""
        self._require_enabled()
        return self._provider.generate(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            think=think,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> T:
        """Generate structured JSON adhering to the Pydantic schema and return validated instance."""
        self._require_enabled()
        return self._provider.generate_structured(
            prompt=prompt,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
            think=think,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate numerical embedding vectors for input texts."""
        self._require_enabled()
        return self._provider.embed(texts)

    def health(self) -> bool:
        """Check provider reachability status."""
        if not self._enabled:
            return False
        return self._provider.health_check()

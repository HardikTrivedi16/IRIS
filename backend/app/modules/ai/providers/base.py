"""Abstract AI Provider interface for IRIS."""

from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseAIProvider(ABC):
    """Abstract interface defining the contract for AI providers in IRIS."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> str:
        """Generate unstructured text from a prompt."""
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> T:
        """Generate structured JSON adhering to the provided Pydantic model and return a validated instance."""
        pass

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate numerical embedding vectors for the provided list of texts."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Perform a lightweight check to determine whether the AI provider is reachable."""
        pass

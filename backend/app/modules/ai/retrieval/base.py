"""Base retrieval index abstraction for the IRIS AI module.

Defines the interface that InMemoryRetrievalIndex (and future PgVectorRetrievalIndex)
must satisfy. RetrievalService depends only on BaseRetrievalIndex.
"""

from abc import ABC, abstractmethod

from app.modules.ai.schemas import RegulatorySourceChunk, RetrievalResult


class BaseRetrievalIndex(ABC):
    """Abstract retrieval index. Storage-agnostic interface for IRIS retrieval.

    Implementations:
        - InMemoryRetrievalIndex  (Phase 4, prototype)
        - PgVectorRetrievalIndex  (future, not implemented in Phase 4)
    """

    @abstractmethod
    def add(self, chunk: RegulatorySourceChunk, embedding: list[float]) -> None:
        """Add or replace a chunk+embedding in the index.

        Duplicate policy: if chunk_id already exists, the entry is replaced.
        Silently creating duplicates is not permitted.
        """
        ...

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievalResult]:
        """Return up to top_k results ordered by descending cosine similarity."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return number of indexed chunks."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all indexed chunks."""
        ...

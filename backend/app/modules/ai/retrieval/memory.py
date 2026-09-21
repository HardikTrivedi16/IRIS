"""In-memory retrieval index for IRIS Phase 4 (prototype).

Uses cosine similarity computed with Python standard library math only.
No NumPy, no vector database, no persistence.

Duplicate policy: if chunk_id already exists, the existing entry is replaced.
"""

import math
from dataclasses import dataclass

from app.modules.ai.exceptions import AIInvalidOutputError
from app.modules.ai.retrieval.base import BaseRetrievalIndex
from app.modules.ai.schemas import RegulatorySourceChunk, RetrievalResult


@dataclass
class _IndexEntry:
    chunk: RegulatorySourceChunk
    embedding: list[float]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors using stdlib math only.

    Returns 0.0 if either vector has zero magnitude.
    """
    if len(a) != len(b):
        raise AIInvalidOutputError(
            f"Embedding dimension mismatch: {len(a)} vs {len(b)}"
        )
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _validate_embedding(embedding: list[float], context: str = "embedding") -> None:
    """Raise AIInvalidOutputError if embedding is empty or contains non-finite values."""
    if not embedding:
        raise AIInvalidOutputError(f"{context} must not be empty.")
    for i, v in enumerate(embedding):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise AIInvalidOutputError(
                f"{context}[{i}] must be a real number (got {v!r})."
            )
        if not math.isfinite(float(v)):
            raise AIInvalidOutputError(
                f"{context}[{i}] is not finite (got {v})."
            )


class InMemoryRetrievalIndex(BaseRetrievalIndex):
    """Prototype in-memory retrieval index backed by a Python dict.

    Stores (chunk, embedding) pairs keyed by chunk_id.
    Duplicate chunk_id entries are replaced deterministically.
    Embedding dimensions must be consistent across all entries.
    """

    def __init__(self) -> None:
        self._store: dict[str, _IndexEntry] = {}
        self._dim: int | None = None

    def add(self, chunk: RegulatorySourceChunk, embedding: list[float]) -> None:
        """Index a chunk with its pre-computed embedding.

        Validates embedding is non-empty, finite, and consistent in dimensionality.
        Replaces any existing entry with the same chunk_id.
        """
        _validate_embedding(embedding, context=f"embedding for chunk '{chunk.chunk_id}'")

        if self._dim is None:
            self._dim = len(embedding)
        elif len(embedding) != self._dim:
            raise AIInvalidOutputError(
                f"Embedding dimension mismatch: index expects {self._dim}, "
                f"got {len(embedding)} for chunk '{chunk.chunk_id}'."
            )

        self._store[chunk.chunk_id] = _IndexEntry(chunk=chunk, embedding=embedding)

    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievalResult]:
        """Return up to top_k RetrievalResult objects ordered by descending cosine similarity.

        Returns empty list for an empty index.
        """
        if top_k <= 0:
            raise AIInvalidOutputError(f"top_k must be a positive integer, got {top_k}.")

        if not self._store:
            return []

        _validate_embedding(query_embedding, context="query embedding")

        if self._dim is not None and len(query_embedding) != self._dim:
            raise AIInvalidOutputError(
                f"Query embedding dimension {len(query_embedding)} does not match "
                f"index dimension {self._dim}."
            )

        scores: list[tuple[str, float]] = []
        for chunk_id, entry in self._store.items():
            score = _cosine_similarity(query_embedding, entry.embedding)
            scores.append((chunk_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top = scores[:top_k]

        results: list[RetrievalResult] = []
        for rank, (chunk_id, score) in enumerate(top, start=1):
            entry = self._store[chunk_id]
            results.append(
                RetrievalResult(
                    chunk=entry.chunk,
                    similarity_score=score,
                    rank=rank,
                )
            )
        return results

    def count(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
        self._dim = None

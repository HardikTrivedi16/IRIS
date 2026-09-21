"""Retrieval Service for IRIS AI Module (Phase 4).

Provides semantic indexing of regulatory source chunks, cosine-similarity
search, and grounded RAG answer generation.

Invariants:
- Uses CoreAIService.embed() — never calls OllamaProvider directly.
- Uses VerificationService (ADVISORY) for RAG answer verification.
- Never determines regulatory applicability for a project.
- Never creates ACTIVE rules.
- No database, no pgvector, no external vector store.
- No conversation history.
- No Ask IRIS.
"""

from app.modules.ai.exceptions import AIError, AIInvalidOutputError
from app.modules.ai.prompts.retrieval import RAG_SYSTEM_PROMPT, build_rag_prompt
from app.modules.ai.retrieval.base import BaseRetrievalIndex
from app.modules.ai.retrieval.memory import InMemoryRetrievalIndex
from app.modules.ai.schemas import (
    GroundedAnswer,
    GroundedAnswerResult,
    RegulatorySourceChunk,
    RetrievalResult,
    SafetyIssue,
    SafetyValidationResult,
    SourceCitation,
    VerificationMode,
)
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.verification import VerificationService


class RetrievalService:
    """Semantic retrieval and grounded RAG for regulatory sources.

    Public interface:
        index_chunks(chunks)       — embed and index regulatory chunks
        search(query, top_k)       — semantic similarity search
        answer(question, ...)      — grounded RAG answer with citation validation
        clear()                    — reset the index
        count()                    — number of indexed chunks
    """

    def __init__(
        self,
        core: CoreAIService,
        verification: VerificationService,
        index: BaseRetrievalIndex | None = None,
    ) -> None:
        self._core = core
        self._verification = verification
        self._index: BaseRetrievalIndex = index if index is not None else InMemoryRetrievalIndex()

    # -------------------------------------------------------------------------
    # Indexing
    # -------------------------------------------------------------------------

    def index_chunks(self, chunks: list[RegulatorySourceChunk]) -> int:
        """Embed and index a list of regulatory source chunks.

        Returns the number of chunks successfully indexed.
        Duplicate chunk_ids are replaced (not silently duplicated).
        Empty text chunks raise AIInvalidOutputError.
        """
        if not chunks:
            return 0

        texts = []
        for chunk in chunks:
            if not chunk.text or not chunk.text.strip():
                raise AIInvalidOutputError(
                    f"Chunk '{chunk.chunk_id}' has empty text and cannot be indexed."
                )
            texts.append(chunk.text)

        embeddings = self._core.embed(texts)

        for chunk, embedding in zip(chunks, embeddings):
            self._index.add(chunk, embedding)

        return len(chunks)

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Semantic similarity search over indexed chunks.

        Args:
            query:  The natural-language search query.
            top_k:  Maximum number of results to return (must be >= 1).

        Returns empty list for an empty index.
        Raises AIInvalidOutputError for empty/whitespace query or invalid top_k.
        """
        if not query or not query.strip():
            raise AIInvalidOutputError("Search query must not be empty or whitespace-only.")
        if top_k <= 0:
            raise AIInvalidOutputError(f"top_k must be a positive integer, got {top_k}.")

        if self._index.count() == 0:
            return []

        query_embeddings = self._core.embed([query.strip()])
        query_embedding = query_embeddings[0]

        return self._index.search(query_embedding, top_k=top_k)

    # -------------------------------------------------------------------------
    # Grounded RAG
    # -------------------------------------------------------------------------

    def answer(
        self,
        question: str,
        sources: list[RetrievalResult] | None = None,
        top_k: int = 3,
    ) -> GroundedAnswerResult:
        """Generate a grounded regulatory answer from retrieved sources.

        If `sources` is None, performs semantic search internally first.
        If the index is empty (or sources is empty after search), returns
        insufficient_information=True without calling the LLM.

        Pipeline:
            question → search (if sources not supplied)
                     → grounded structured generation (Qwen)
                     → VerificationService ADVISORY
                     → citation validation
                     → GroundedAnswerResult
        """
        if not question or not question.strip():
            raise AIInvalidOutputError("Question must not be empty or whitespace-only.")

        # Retrieve if caller did not pre-supply sources
        if sources is None:
            sources = self.search(question, top_k=top_k)

        # No sources → insufficient information without LLM call
        if not sources:
            return GroundedAnswerResult(
                answer=GroundedAnswer(
                    answer="The indexed regulatory sources do not contain enough information to answer this question.",
                    citations=[],
                    insufficient_information=True,
                    warnings=["No source chunks were available for retrieval."],
                ),
                retrieved_chunks=[],
                citations_valid=True,
                requires_human_review=False,
                warnings=["No source chunks were available for retrieval."],
            )

        # Build chunk dicts for prompt and authoritative context
        chunk_dicts = [
            {
                "chunk_id": r.chunk.chunk_id,
                "source_id": r.chunk.source_id,
                "text": r.chunk.text,
                "document_name": r.chunk.document_name,
                "page_number": r.chunk.page_number,
                "section_reference": r.chunk.section_reference,
            }
            for r in sources
        ]

        prompt = f"{RAG_SYSTEM_PROMPT}\n\n{build_rag_prompt(question, chunk_dicts)}"

        # Generate grounded answer via CoreAIService
        raw_answer: GroundedAnswer = self._core.generate_structured(
            prompt=prompt,
            schema=GroundedAnswer,
            temperature=0.0,
            think=False,
        )

        # Verification (ADVISORY) — verifier receives question + all source texts
        authoritative_input = {
            "question": question,
            "supplied_sources": chunk_dicts,
        }
        outcome = None
        verification_warning: str | None = None
        try:
            outcome = self._verification.verify(
                task_type="grounded_rag_answer",
                authoritative_input=authoritative_input,
                local_output=raw_answer,
                output_schema=GroundedAnswer,
            )
        except AIError as exc:
            verification_warning = f"Verification unavailable: {exc}"

        effective_answer = raw_answer
        if outcome and outcome.effective_output is not None and isinstance(outcome.effective_output, GroundedAnswer):
            effective_answer = outcome.effective_output

        # Deterministic citation validation
        valid_chunk_ids = {r.chunk.chunk_id for r in sources}
        citation_issues: list[str] = []
        validated_citations: list[SourceCitation] = []

        for cit in effective_answer.citations:
            if cit.chunk_id not in valid_chunk_ids:
                citation_issues.append(
                    f"[HALLUCINATED_CITATION] chunk_id '{cit.chunk_id}' was not in the supplied sources."
                )
            else:
                # Enrich citation metadata from the actual chunk
                matching = next(r for r in sources if r.chunk.chunk_id == cit.chunk_id)
                validated_citations.append(
                    SourceCitation(
                        chunk_id=cit.chunk_id,
                        source_id=matching.chunk.source_id,
                        document_name=matching.chunk.document_name,
                        page_number=matching.chunk.page_number,
                        section_reference=matching.chunk.section_reference,
                    )
                )

        effective_answer.citations = validated_citations

        # A substantive grounded answer without any valid citation is not acceptable.
        # This is provenance enforcement, not a legal applicability decision.
        if not effective_answer.insufficient_information and not validated_citations:
            citation_issues.append(
                "[MISSING_CITATION] A substantive regulatory answer must cite at least one supplied source chunk."
            )

        # Assemble warnings
        warnings: list[str] = list(effective_answer.warnings or [])
        if verification_warning:
            warnings.append(verification_warning)
        if outcome and outcome.warning:
            warnings.append(outcome.warning)
        warnings.extend(citation_issues)

        citations_valid = len(citation_issues) == 0
        requires_review = (
            not citations_valid
            or bool(citation_issues)
            or (outcome is not None and outcome.requires_human_review)
            or verification_warning is not None
        )

        return GroundedAnswerResult(
            answer=effective_answer,
            outcome=outcome,
            retrieved_chunks=sources,
            citations_valid=citations_valid,
            requires_human_review=requires_review,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Index management
    # -------------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all indexed chunks from the index."""
        self._index.clear()

    def count(self) -> int:
        """Return the number of indexed chunks."""
        return self._index.count()

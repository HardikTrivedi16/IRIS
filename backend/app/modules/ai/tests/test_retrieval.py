"""Phase 4 tests for RetrievalService, InMemoryRetrievalIndex, and grounded RAG.

All tests are offline (no live Ollama or Groq).
Live tests are marked live_phase4 and skipped by default.
"""

import math
import time
from typing import Any
import pytest

from app.modules.ai import (
    AIConfig,
    ChunkMetadata,
    GroundedAnswer,
    GroundedAnswerResult,
    InMemoryRetrievalIndex,
    Provenance,
    RegulatorySourceChunk,
    RetrievalResult,
    SourceCitation,
    VerificationIssue,
    VerificationMode,
    VerificationOutcome,
    VerificationResult,
    VerificationVerdict,
    _reset_ai_facade,
    get_ai,
)
from app.modules.ai.exceptions import AIInvalidOutputError, AIUnavailableError
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.retrieval.memory import InMemoryRetrievalIndex, _cosine_similarity
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.retrieval import RetrievalService
from app.modules.ai.services.verification import VerificationService


# ==============================================================================
# Helpers / Fixtures
# ==============================================================================

def _make_chunk(
    chunk_id: str,
    text: str,
    source_id: str = "SRC-001",
    document_name: str = "Test Regulation",
    page_number: int | None = 1,
    section_reference: str | None = "Section 1",
) -> RegulatorySourceChunk:
    return RegulatorySourceChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        text=text,
        document_name=document_name,
        page_number=page_number,
        section_reference=section_reference,
    )


class MockEmbedProvider(BaseAIProvider):
    """Deterministic embedding provider for offline tests."""

    def __init__(
        self,
        embed_fn: Any = None,
        structured_return: Any = None,
    ) -> None:
        self._embed_fn = embed_fn
        self._structured_return = structured_return
        self.embed_calls: list[list[str]] = []
        self.generate_structured_calls: int = 0

    def generate(self, prompt: str, **kwargs: Any) -> str:
        return "mock"

    def generate_structured(self, prompt: str, schema: type[Any], **kwargs: Any) -> Any:
        self.generate_structured_calls += 1
        return self._structured_return

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        if self._embed_fn:
            return self._embed_fn(texts)
        # Default: return 3-dim unit vector based on index
        return [[float(i + 1), 0.0, 0.0] for i in range(len(texts))]

    def health_check(self) -> bool:
        return True


class MockVerifier(BaseVerificationProvider):
    def __init__(self, result: VerificationResult | None = None, exc: Exception | None = None) -> None:
        self.result = result or VerificationResult(
            verdict=VerificationVerdict.PASS,
            issues=[],
            corrected_output=None,
            verifier_provider="mock",
        )
        self.exc = exc

    def verify(self, task_type: str, authoritative_input: Any, local_output: Any, **kwargs: Any) -> VerificationResult:
        if self.exc:
            raise self.exc
        return self.result


def _make_service(
    embed_fn: Any = None,
    structured_return: Any = None,
    verifier: MockVerifier | None = None,
    index: InMemoryRetrievalIndex | None = None,
) -> RetrievalService:
    provider = MockEmbedProvider(embed_fn=embed_fn, structured_return=structured_return)
    core = CoreAIService(provider=provider)
    verification = VerificationService(
        provider=verifier or MockVerifier(),
        mode=VerificationMode.OFF,
    )
    return RetrievalService(core=core, verification=verification, index=index)


@pytest.fixture(autouse=True)
def clean_state():
    _reset_ai_facade()
    yield
    _reset_ai_facade()


# ==============================================================================
# AI-RAG-01: Index multiple regulatory chunks
# ==============================================================================
def test_ai_rag_01_index_multiple_chunks():
    svc = _make_service()
    chunks = [
        _make_chunk("C1", "Environmental consent required for 50 TPD units.", source_id="ENV-001"),
        _make_chunk("C2", "Fire safety review for units with 20+ workers.", source_id="FIRE-001"),
        _make_chunk("C3", "Investment declaration for projects over 10 crore.", source_id="INV-001"),
    ]
    n = svc.index_chunks(chunks)
    assert n == 3
    assert svc.count() == 3


# ==============================================================================
# AI-RAG-02: Embedding count matches chunks
# ==============================================================================
def test_ai_rag_02_embedding_count_matches_chunks():
    provider = MockEmbedProvider()
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    chunks = [
        _make_chunk("C1", "Chunk 1"),
        _make_chunk("C2", "Chunk 2"),
        _make_chunk("C3", "Chunk 3"),
    ]
    svc.index_chunks(chunks)
    # embed should have been called once with all 3 texts
    assert len(provider.embed_calls) == 1
    assert len(provider.embed_calls[0]) == 3


# ==============================================================================
# AI-RAG-03: Search returns top-K sorted descending by similarity
# ==============================================================================
def test_ai_rag_03_search_returns_top_k_sorted_descending():
    # Use fixed embeddings: chunk embeddings are orthogonal unit vectors
    # Query will align with C2 (second chunk)
    def embed_fn(texts: list[str]) -> list[list[float]]:
        vectors = {
            "A": [1.0, 0.0, 0.0],
            "B": [0.0, 1.0, 0.0],
            "C": [0.0, 0.0, 1.0],
            "Q": [0.0, 1.0, 0.0],  # aligns with B
        }
        return [vectors.get(t, [0.5, 0.5, 0.0]) for t in texts]

    provider = MockEmbedProvider(embed_fn=embed_fn)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    svc.index_chunks([
        _make_chunk("A", "A"),
        _make_chunk("B", "B"),
        _make_chunk("C", "C"),
    ])
    results = svc.search("Q", top_k=3)

    assert len(results) == 3
    assert results[0].chunk.chunk_id == "B"
    assert results[0].rank == 1
    assert results[0].similarity_score > results[1].similarity_score or results[0].similarity_score >= results[1].similarity_score
    # Verify descending order
    for i in range(len(results) - 1):
        assert results[i].similarity_score >= results[i + 1].similarity_score


# ==============================================================================
# AI-RAG-04: Cosine similarity is deterministic for known vectors
# ==============================================================================
def test_ai_rag_04_cosine_similarity_deterministic():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    c = [0.0, 1.0, 0.0]
    d = [-1.0, 0.0, 0.0]

    assert _cosine_similarity(a, b) == pytest.approx(1.0)
    assert _cosine_similarity(a, c) == pytest.approx(0.0)
    assert _cosine_similarity(a, d) == pytest.approx(-1.0)

    # Deterministic on repeated calls
    assert _cosine_similarity(a, b) == _cosine_similarity(a, b)


# ==============================================================================
# AI-RAG-05: Multiple source documents preserve provenance
# ==============================================================================
def test_ai_rag_05_multiple_sources_preserve_provenance():
    svc = _make_service()
    chunks = [
        _make_chunk("E1", "Environmental text", source_id="ENV-ACT", document_name="Environment Act"),
        _make_chunk("F1", "Fire safety text", source_id="FIRE-NOC", document_name="Fire Safety Rules"),
    ]
    svc.index_chunks(chunks)

    # Search with default provider returns any result — check provenance preserved
    results = svc.search("query text", top_k=2)
    source_ids = {r.chunk.source_id for r in results}
    assert "ENV-ACT" in source_ids
    assert "FIRE-NOC" in source_ids
    doc_names = {r.chunk.document_name for r in results}
    assert "Environment Act" in doc_names
    assert "Fire Safety Rules" in doc_names


# ==============================================================================
# AI-RAG-06: Duplicate chunk ID policy — replace, not silent duplicate
# ==============================================================================
def test_ai_rag_06_duplicate_chunk_id_replaced():
    svc = _make_service()
    c1_v1 = _make_chunk("DUP-1", "Original text")
    c1_v2 = _make_chunk("DUP-1", "Replaced text")

    svc.index_chunks([c1_v1])
    assert svc.count() == 1

    svc.index_chunks([c1_v2])
    assert svc.count() == 1  # still 1, replaced, not duplicated

    results = svc.search("test", top_k=1)
    assert results[0].chunk.text == "Replaced text"


# ==============================================================================
# AI-RAG-07: Empty index search returns empty results (no crash)
# ==============================================================================
def test_ai_rag_07_empty_index_search_returns_empty():
    svc = _make_service()
    assert svc.count() == 0
    results = svc.search("anything", top_k=5)
    assert results == []


# ==============================================================================
# AI-RAG-08: Empty query does not call embedding model
# ==============================================================================
def test_ai_rag_08_empty_query_does_not_call_embedding():
    provider = MockEmbedProvider()
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    svc.index_chunks([_make_chunk("C1", "Some text")])

    with pytest.raises(AIInvalidOutputError):
        svc.search("", top_k=3)

    with pytest.raises(AIInvalidOutputError):
        svc.search("   ", top_k=3)

    # No embedding calls after the empty-query errors
    assert all(len(call) > 0 for call in provider.embed_calls)  # only indexing calls
    assert len(provider.embed_calls) == 1  # only the index_chunks call


# ==============================================================================
# AI-RAG-09: Invalid/mismatched embedding dimensions are rejected
# ==============================================================================
def test_ai_rag_09_mismatched_embedding_dimensions_rejected():
    index = InMemoryRetrievalIndex()
    # Add first chunk with 3-dim embedding
    c1 = _make_chunk("C1", "text")
    index.add(c1, [0.5, 0.5, 0.5])
    assert index.count() == 1

    # Adding second chunk with different dimension must raise
    c2 = _make_chunk("C2", "text2")
    with pytest.raises(AIInvalidOutputError, match="dimension"):
        index.add(c2, [0.5, 0.5])  # 2-dim vs 3-dim index

    # Searching with wrong dimension must raise
    with pytest.raises(AIInvalidOutputError, match="dimension"):
        index.search([0.5, 0.5], top_k=1)


# ==============================================================================
# AI-RAG-10: top_k <= 0 handled with controlled validation
# ==============================================================================
def test_ai_rag_10_invalid_top_k_raises():
    svc = _make_service()
    svc.index_chunks([_make_chunk("C1", "text")])

    with pytest.raises(AIInvalidOutputError):
        svc.search("query", top_k=0)

    with pytest.raises(AIInvalidOutputError):
        svc.search("query", top_k=-1)


# ==============================================================================
# AI-RAG-11: Grounded answer cites only supplied chunks
# ==============================================================================
def test_ai_rag_11_grounded_answer_cites_only_supplied_chunks():
    chunk = _make_chunk("ENV-5-1", "Environmental consent required for 50 TPD.")
    good_answer = GroundedAnswer(
        answer="Environmental consent is required.",
        citations=[
            SourceCitation(
                chunk_id="ENV-5-1",
                source_id="ENV-001",
                document_name="Test Regulation",
                page_number=1,
                section_reference="Section 1",
            )
        ],
        insufficient_information=False,
    )
    provider = MockEmbedProvider(structured_return=good_answer)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    svc.index_chunks([chunk])

    # Pre-supply sources to avoid embedding the query
    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.95, rank=1)]
    result = svc.answer("What environmental permission is needed?", sources=retrieved)

    assert result.citations_valid is True
    assert len(result.answer.citations) == 1
    assert result.answer.citations[0].chunk_id == "ENV-5-1"


# ==============================================================================
# AI-RAG-12: Hallucinated citation ID is rejected/marked unsafe
# ==============================================================================
def test_ai_rag_12_hallucinated_citation_rejected():
    chunk = _make_chunk("REAL-CHUNK", "Real regulatory text.")
    hallucinated_answer = GroundedAnswer(
        answer="The regulation allows X under section Z.",
        citations=[
            SourceCitation(
                chunk_id="FAKE-CHUNK-ID",  # not in supplied sources
                source_id="FAKE-SRC",
                document_name="Fake Doc",
            )
        ],
        insufficient_information=False,
    )
    provider = MockEmbedProvider(structured_return=hallucinated_answer)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    svc.index_chunks([chunk])

    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.9, rank=1)]
    result = svc.answer("question", sources=retrieved)

    assert result.citations_valid is False
    assert result.requires_human_review is True
    # Hallucinated citation must be stripped from validated citations
    assert len(result.answer.citations) == 0
    assert any("HALLUCINATED_CITATION" in w for w in result.warnings)


# ==============================================================================
# AI-RAG-13: Citation metadata must match supplied chunk provenance
# ==============================================================================
def test_ai_rag_13_citation_metadata_matches_supplied_chunk():
    chunk = _make_chunk(
        "CHUNK-ENV",
        "Environmental text.",
        source_id="ENV-SRC",
        document_name="Environment Act",
        page_number=7,
        section_reference="Section 5.1",
    )
    answer_with_citation = GroundedAnswer(
        answer="Answer grounded.",
        citations=[
            SourceCitation(
                chunk_id="CHUNK-ENV",
                source_id="ENV-SRC",
                document_name="Environment Act",
                page_number=7,
                section_reference="Section 5.1",
            )
        ],
        insufficient_information=False,
    )
    provider = MockEmbedProvider(structured_return=answer_with_citation)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    svc.index_chunks([chunk])
    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.95, rank=1)]
    result = svc.answer("query", sources=retrieved)

    assert result.citations_valid is True
    cit = result.answer.citations[0]
    assert cit.source_id == "ENV-SRC"
    assert cit.page_number == 7
    assert cit.section_reference == "Section 5.1"
    assert cit.document_name == "Environment Act"


# ==============================================================================
# AI-RAG-14: Unsupported tax-exemption question returns insufficient_information=True
# ==============================================================================
def test_ai_rag_14_unsupported_question_insufficient_information():
    insufficient_answer = GroundedAnswer(
        answer="The supplied regulatory sources do not provide information about tax exemptions.",
        citations=[],
        insufficient_information=True,
    )
    chunk = _make_chunk("ENV-5-1", "Environmental consent required for 50 TPD.")
    provider = MockEmbedProvider(structured_return=insufficient_answer)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    svc.index_chunks([chunk])
    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.3, rank=1)]
    result = svc.answer("What tax exemption does this regulation provide?", sources=retrieved)

    assert result.answer.insufficient_information is True
    assert result.citations_valid is True


# ==============================================================================
# AI-RAG-15: Zero retrieved sources → insufficient_information=True, no LLM call
# ==============================================================================
def test_ai_rag_15_zero_sources_no_llm_call():
    provider = MockEmbedProvider(structured_return=None)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
    )
    # Empty index: search will return []
    result = svc.answer("What environmental permission is needed?", sources=[])

    assert result.answer.insufficient_information is True
    assert provider.generate_structured_calls == 0  # LLM must NOT have been called


# ==============================================================================
# AI-RAG-16: ADVISORY verifier PASS preserves grounded answer
# ==============================================================================
def test_ai_rag_16_advisory_verifier_pass_preserves_answer():
    chunk = _make_chunk("C1", "Environmental consent text.")
    good_answer = GroundedAnswer(
        answer="Environmental consent is required.",
        citations=[SourceCitation(chunk_id="C1", source_id="SRC-1")],
        insufficient_information=False,
    )
    verifier = MockVerifier(result=VerificationResult(
        verdict=VerificationVerdict.PASS,
        issues=[],
        corrected_output=None,
        verifier_provider="mock",
    ))
    provider = MockEmbedProvider(structured_return=good_answer)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=verifier, mode=VerificationMode.ADVISORY),
    )
    svc.index_chunks([chunk])
    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.9, rank=1)]
    result = svc.answer("question", sources=retrieved)

    assert result.outcome is not None
    assert result.outcome.result.verdict == VerificationVerdict.PASS
    assert result.answer.answer == "Environmental consent is required."


# ==============================================================================
# AI-RAG-17: ADVISORY verifier CORRECTED output is schema validated
# ==============================================================================
def test_ai_rag_17_advisory_verifier_corrected_schema_validated():
    chunk = _make_chunk("C1", "Environmental consent text.")
    local_answer = GroundedAnswer(
        answer="Wrong answer.",
        citations=[SourceCitation(chunk_id="C1", source_id="SRC-1")],
        insufficient_information=False,
    )
    corrected_answer = GroundedAnswer(
        answer="Corrected: environmental consent is required for capacity > 50 TPD.",
        citations=[SourceCitation(chunk_id="C1", source_id="SRC-1")],
        insufficient_information=False,
    )
    verifier = MockVerifier(result=VerificationResult(
        verdict=VerificationVerdict.CORRECTED,
        issues=[VerificationIssue(code="FIDELITY", field="answer", message="Corrected")],
        corrected_output=corrected_answer,
        verifier_provider="mock_groq",
    ))
    provider = MockEmbedProvider(structured_return=local_answer)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=verifier, mode=VerificationMode.ADVISORY),
    )
    svc.index_chunks([chunk])
    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.9, rank=1)]
    result = svc.answer("question", sources=retrieved)

    assert result.outcome.corrected_by_verifier is True
    assert "50 TPD" in result.answer.answer


# ==============================================================================
# AI-RAG-18: ADVISORY verifier unavailable does not crash RAG
# ==============================================================================
def test_ai_rag_18_advisory_verifier_unavailable_no_crash():
    chunk = _make_chunk("C1", "Regulation text.")
    local_answer = GroundedAnswer(
        answer="Environmental consent required.",
        citations=[SourceCitation(chunk_id="C1", source_id="SRC-1")],
        insufficient_information=False,
    )
    verifier = MockVerifier(exc=AIUnavailableError("Groq is offline"))
    provider = MockEmbedProvider(structured_return=local_answer)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=verifier, mode=VerificationMode.ADVISORY),
    )
    svc.index_chunks([chunk])
    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.9, rank=1)]
    result = svc.answer("question", sources=retrieved)

    assert result.answer.answer == "Environmental consent required."
    assert result.requires_human_review is True
    assert any("Groq is offline" in w or "Verification unavailable" in w for w in result.warnings)


# ==============================================================================
# AI-RAG-19: ADVISORY verifier REJECT marks result requiring human review
# ==============================================================================
def test_ai_rag_19_advisory_reject_marks_requires_human_review():
    chunk = _make_chunk("C1", "Regulation text.")
    local_answer = GroundedAnswer(
        answer="Fabricated answer.",
        citations=[SourceCitation(chunk_id="C1", source_id="SRC-1")],
        insufficient_information=False,
    )
    verifier = MockVerifier(result=VerificationResult(
        verdict=VerificationVerdict.REJECT,
        issues=[VerificationIssue(code="HALLUCINATION", field="answer", message="Answer not grounded in sources")],
        corrected_output=None,
        verifier_provider="mock",
    ))
    provider = MockEmbedProvider(structured_return=local_answer)
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=verifier, mode=VerificationMode.ADVISORY),
    )
    svc.index_chunks([chunk])
    retrieved = [RetrievalResult(chunk=chunk, similarity_score=0.9, rank=1)]
    result = svc.answer("question", sources=retrieved)

    assert result.outcome.result.verdict == VerificationVerdict.REJECT
    assert result.requires_human_review is True
    # REJECT must NOT be silently converted to PASS
    assert result.outcome.result.verdict != VerificationVerdict.PASS


# ==============================================================================
# AI-RAG-20: RetrievalService never calculates project regulatory applicability
# ==============================================================================
def test_ai_rag_20_retrieval_service_never_evaluates_applicability():
    from app.modules.ai.services import retrieval
    import inspect

    source = inspect.getsource(retrieval)
    assert "evaluate_applicability" not in source
    assert "check_applicability" not in source
    assert "project_facts" not in source
    assert "rule_engine" not in source.lower()
    assert not hasattr(RetrievalService, "evaluate_applicability")
    assert not hasattr(RetrievalService, "check_applicability")


# ==============================================================================
# AI-RAG-21: No vector database/database dependency is introduced
# ==============================================================================
def test_ai_rag_21_no_vector_database_dependency():
    from app.modules.ai.retrieval import memory
    import inspect

    source = inspect.getsource(memory)
    # Check that forbidden packages are not *imported* — a negation comment ("No NumPy") is acceptable.
    forbidden_imports = [
        "import pgvector", "import faiss", "import chromadb", "import qdrant",
        "import weaviate", "import pinecone", "import sqlalchemy", "import redis",
        "import numpy", "from numpy", "from pgvector", "from faiss",
    ]
    for forbidden in forbidden_imports:
        assert forbidden not in source, f"Forbidden import '{forbidden}' found in memory.py"


# ==============================================================================
# AI-RAG-22: Index storage abstraction allows InMemoryRetrievalIndex injection/replacement
# ==============================================================================
def test_ai_rag_22_index_abstraction_allows_injection():
    from app.modules.ai.retrieval.base import BaseRetrievalIndex

    custom_index = InMemoryRetrievalIndex()
    provider = MockEmbedProvider()
    core = CoreAIService(provider=provider)
    svc = RetrievalService(
        core=core,
        verification=VerificationService(provider=MockVerifier(), mode=VerificationMode.OFF),
        index=custom_index,
    )
    assert isinstance(svc._index, BaseRetrievalIndex)

    svc.index_chunks([_make_chunk("C1", "Injected index chunk.")])
    assert custom_index.count() == 1
    assert svc.count() == 1


# ==============================================================================
# AI-RAG: Facade exposes ai.retrieval
# ==============================================================================
def test_ai_rag_facade_exposes_retrieval():
    provider = MockEmbedProvider()
    from app.modules.ai.providers.noop_verifier import NoOpVerifier
    from app.modules.ai.retrieval.memory import InMemoryRetrievalIndex

    ai = get_ai(provider=provider, retrieval_index=InMemoryRetrievalIndex())
    assert hasattr(ai, "retrieval")
    assert hasattr(ai, "core")
    assert hasattr(ai, "verification")
    assert hasattr(ai, "documents")
    assert hasattr(ai, "regulatory")
    assert isinstance(ai.retrieval, RetrievalService)


# ==============================================================================
# OPTIONAL LIVE PHASE 4 SMOKE TEST
# Skipped by default. Run manually with:
#   pytest app/modules/ai/tests/test_retrieval.py -v -m "live_phase4"
# Requires local Ollama with qwen3-embedding:0.6b and qwen3:8b running.
# ==============================================================================
@pytest.mark.live_phase4
def test_live_phase4_retrieval_and_rag_smoke():
    ai = get_ai()
    if not ai.core.health():
        pytest.skip("Local Ollama daemon is not reachable")

    chunks = [
        RegulatorySourceChunk(
            chunk_id="SEC-5-1",
            source_id="ENV-ACT-2026",
            text=(
                "A food processing unit with a production capacity greater than 50 TPD "
                "shall obtain the applicable environmental consent before commencement "
                "of commercial operation."
            ),
            document_name="Environmental Compliance Notification 2026",
            page_number=3,
            section_reference="Section 5.1",
        ),
        RegulatorySourceChunk(
            chunk_id="SEC-6-1",
            source_id="FIRE-RULES-2026",
            text=(
                "A fire safety review shall be completed before commercial operation "
                "for all food processing units employing 20 or more workers."
            ),
            document_name="Fire Safety Rules 2026",
            page_number=5,
            section_reference="Section 6.1",
        ),
        RegulatorySourceChunk(
            chunk_id="SEC-5-2",
            source_id="ENV-ACT-2026",
            text=(
                "Where project investment exceeds 10 crore INR, the applicant shall "
                "provide an additional environmental assessment document along with "
                "the application for consent."
            ),
            document_name="Environmental Compliance Notification 2026",
            page_number=3,
            section_reference="Section 5.2",
        ),
    ]

    t0 = time.time()
    n = ai.retrieval.index_chunks(chunks)
    index_time = time.time() - t0
    assert n == 3
    print(f"\n[LIVE] Indexing time: {index_time*1000:.1f}ms")

    # --- Query 1: environmental permission ---
    t1 = time.time()
    results = ai.retrieval.search("What environmental permission is needed for a high capacity food processing unit?", top_k=2)
    search_time = time.time() - t1
    print(f"[LIVE] Search time: {search_time*1000:.1f}ms, top result: {results[0].chunk.chunk_id} score={results[0].similarity_score:.3f}")
    assert any(r.chunk.chunk_id == "SEC-5-1" for r in results[:2]), "Section 5.1 should be in top results"

    t2 = time.time()
    rag_result = ai.retrieval.answer(
        "What environmental permission is needed for a high capacity food processing unit?",
        sources=results,
    )
    gen_time = time.time() - t2
    print(f"[LIVE] Generation time: {gen_time*1000:.1f}ms")
    assert not rag_result.answer.insufficient_information
    assert any("environmental" in c.section_reference.lower() or "5.1" in (c.section_reference or "") for c in rag_result.answer.citations), \
        "Citation should reference Section 5.1"
    print(f"[LIVE] Answer: {rag_result.answer.answer[:200]}")
    print(f"[LIVE] Citations: {[(c.chunk_id, c.section_reference) for c in rag_result.answer.citations]}")
    print(f"[LIVE] Total time: {(time.time()-t0)*1000:.1f}ms")

    # --- Query 2: unsupported question (tax exemption) ---
    ai.retrieval.clear()
    ai.retrieval.index_chunks(chunks)
    tax_result = ai.retrieval.answer(
        "What tax exemption does this regulation provide?",
    )
    print(f"[LIVE] Tax query - insufficient_information: {tax_result.answer.insufficient_information}")
    assert tax_result.answer.insufficient_information is True, "No tax exemption info should be found"

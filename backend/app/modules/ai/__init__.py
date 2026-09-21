"""IRIS AI Module — Phase 1 through Phase 5.

Phase 1: Core generation, embeddings, OllamaProvider
Phase 2: Verification layer (NoOpVerifier, GroqVerifier)
Phase 3: Document + Regulatory intelligence, SafetyValidator
Phase 4: Retrieval index, semantic search, grounded RAG
Phase 5: Grounded explanations of deterministic IRIS results

Usage:
    from app.modules.ai import get_ai

    ai = get_ai()
    ai.core.generate(...)
    ai.documents.extract(...)
    ai.regulatory.extract_candidate(...)
    ai.retrieval.index_chunks([...])
    ai.retrieval.search("query")
    ai.retrieval.answer("question")

Importing makes ZERO network calls.
"""

from app.modules.ai.config import AIConfig
from app.modules.ai.exceptions import (
    AIError,
    AIInvalidOutputError,
    AISafetyRejectedError,
    AITimeoutError,
    AIUnavailableError,
    AIVerificationError,
)
from app.modules.ai.facade import IRISAI, _reset_ai_facade, get_ai
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.retrieval.base import BaseRetrievalIndex
from app.modules.ai.retrieval.memory import InMemoryRetrievalIndex
from app.modules.ai.schemas import (
    AIMetadata,
    AIResult,
    ApplicantDocumentExtraction,
    CandidateStatus,
    ChunkMetadata,
    ConditionLogic,
    DocumentClassificationResult,
    DocumentExtractionResult,
    DocumentType,
    ExtractedFact,
    GroundedAnswer,
    GroundedAnswerResult,
    Provenance,
    QualifierType,
    RegulatoryCandidate,
    RegulatoryCandidateResult,
    RegulatoryCondition,
    RegulatoryQualifier,
    RegulatorySourceChunk,
    RetrievalResult,
    SafetyIssue,
    SafetyValidationResult,
    SourceCitation,
    VerificationIssue,
    VerificationMode,
    VerificationOutcome,
    VerificationResult,
    VerificationVerdict,
    # Phase 5
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
)
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.documents import DocumentAIService
from app.modules.ai.services.explanations import ExplanationService
from app.modules.ai.services.regulatory import RegulatoryAIService
from app.modules.ai.services.retrieval import RetrievalService
from app.modules.ai.services.verification import VerificationService
from app.modules.ai.validators.safety import SafetyValidator

__all__ = [
    # Facade
    "get_ai",
    "IRISAI",
    # Config
    "AIConfig",
    # Provider ABCs
    "BaseAIProvider",
    "BaseVerificationProvider",
    "BaseRetrievalIndex",
    "InMemoryRetrievalIndex",
    # Phase 1–2 schemas
    "VerificationMode",
    "VerificationVerdict",
    "VerificationIssue",
    "VerificationResult",
    "VerificationOutcome",
    "AIMetadata",
    "AIResult",
    # Services
    "CoreAIService",
    "VerificationService",
    "DocumentAIService",
    "RegulatoryAIService",
    "RetrievalService",
    # Phase 3
    "SafetyValidator",
    "Provenance",
    "DocumentType",
    "DocumentClassificationResult",
    "ExtractedFact",
    "ApplicantDocumentExtraction",
    "DocumentExtractionResult",
    "CandidateStatus",
    "ConditionLogic",
    "QualifierType",
    "RegulatoryQualifier",
    "RegulatoryCondition",
    "RegulatoryCandidate",
    "RegulatoryCandidateResult",
    "SafetyIssue",
    "SafetyValidationResult",
    # Phase 4
    "ChunkMetadata",
    "RegulatorySourceChunk",
    "RetrievalResult",
    "SourceCitation",
    "GroundedAnswer",
    "GroundedAnswerResult",
    # Phase 5 Services
    "ExplanationService",
    # Phase 5 Authoritative Inputs
    "RequirementTraceInput",
    "DependencyInput",
    "ParallelCandidateInput",
    "CriticalPathInput",
    "DocumentIssueInput",
    "ImpactChangeInput",
    "SLAInput",
    "SchemeMatchInput",
    "RiskInput",
    "OfficialQueryInput",
    "ApplicationStatusInput",
    # Phase 5 Outputs & Envelope
    "ExplanationOutput",
    "RequirementTraceExplanation",
    "DependencyExplanation",
    "ParallelCandidateExplanation",
    "CriticalPathExplanation",
    "DocumentIssueExplanation",
    "ImpactChangeExplanation",
    "SLAExplanation",
    "SchemeExplanation",
    "RiskExplanation",
    "OfficialQueryExplanation",
    "ApplicationStatusExplanation",
    "ExplanationResult",
    # Exceptions
    "AIError",
    "AIUnavailableError",
    "AITimeoutError",
    "AIInvalidOutputError",
    "AIVerificationError",
    "AISafetyRejectedError",
    # Test helpers
    "_reset_ai_facade",
]

"""Prompt definitions for the IRIS AI module."""

from app.modules.ai.prompts.documents import (
    DOCUMENT_CLASSIFICATION_SYSTEM_PROMPT,
    DOCUMENT_EXTRACTION_SYSTEM_PROMPT,
    build_document_classification_prompt,
    build_document_extraction_prompt,
)
from app.modules.ai.prompts.explanations import (
    SHARED_EXPLANATION_SYSTEM_PROMPT,
    build_application_status_prompt,
    build_critical_path_prompt,
    build_dependency_prompt,
    build_document_issue_prompt,
    build_impact_change_prompt,
    build_official_query_prompt,
    build_parallel_candidate_prompt,
    build_requirement_trace_prompt,
    build_risk_prompt,
    build_scheme_prompt,
    build_sla_prompt,
)
from app.modules.ai.prompts.regulatory import (
    REGULATORY_EXTRACTION_SYSTEM_PROMPT,
    build_regulatory_extraction_prompt,
)
from app.modules.ai.prompts.retrieval import (
    RAG_SYSTEM_PROMPT,
    build_rag_prompt,
)
from app.modules.ai.prompts.verification import (
    VERIFICATION_SYSTEM_PROMPT,
    build_verification_prompt,
)

__all__ = [
    "VERIFICATION_SYSTEM_PROMPT",
    "build_verification_prompt",
    "DOCUMENT_EXTRACTION_SYSTEM_PROMPT",
    "build_document_extraction_prompt",
    "DOCUMENT_CLASSIFICATION_SYSTEM_PROMPT",
    "build_document_classification_prompt",
    "REGULATORY_EXTRACTION_SYSTEM_PROMPT",
    "build_regulatory_extraction_prompt",
    "RAG_SYSTEM_PROMPT",
    "build_rag_prompt",
    "SHARED_EXPLANATION_SYSTEM_PROMPT",
    "build_requirement_trace_prompt",
    "build_dependency_prompt",
    "build_parallel_candidate_prompt",
    "build_critical_path_prompt",
    "build_document_issue_prompt",
    "build_impact_change_prompt",
    "build_sla_prompt",
    "build_scheme_prompt",
    "build_risk_prompt",
    "build_official_query_prompt",
    "build_application_status_prompt",
]

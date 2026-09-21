"""Common generic schemas for the IRIS AI module.

Phases 1, 2, and 3 define generic schemas for metadata, verification outcomes,
applicant document extraction, document classification, regulatory candidates,
and safety validation results.
"""

from enum import Enum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ==============================================================================
# Phase 1: Verification Modes & Metadata Envelopes
# ==============================================================================

class VerificationMode(str, Enum):
    """Modes for AI verification."""
    OFF = "OFF"
    ADVISORY = "ADVISORY"
    REQUIRED = "REQUIRED"


class VerificationVerdict(str, Enum):
    """Verdicts returned by verification providers."""
    PASS = "PASS"
    CORRECTED = "CORRECTED"
    REJECT = "REJECT"


class VerificationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Specific fidelity issue identified during verification."""
    code: str = Field(
        description="Machine-readable issue category code (e.g., NUMERIC_FIDELITY, UNSUPPORTED_CLAIM).",
    )
    field: str | None = Field(
        default=None,
        description="JSON path or field name in the output where the defect occurs.",
    )
    message: str = Field(
        description="Human-readable explanation of why the output violates fidelity to authoritative input.",
    )


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Raw semantic verification result returned by a BaseVerificationProvider.

    Represents what the provider observed and evaluated. Does not determine
    application-level outcome or orchestration policy.
    """
    verdict: VerificationVerdict = Field(
        description="Verification verdict: PASS, CORRECTED, or REJECT.",
    )
    issues: list[VerificationIssue] = Field(
        default_factory=list,
        description="List of fidelity issues detected by the verifier.",
    )
    corrected_output: Any | None = Field(
        default=None,
        description="Proposed corrected output if verdict is CORRECTED.",
    )
    verifier_provider: str = Field(
        default="none",
        description="Name of the verifier provider (e.g., noop, groq).",
    )
    verifier_model: str | None = Field(
        default=None,
        description="Model used by the verifier, if applicable.",
    )
    raw_response: str | None = Field(
        default=None,
        description="Optional raw response text for diagnostic tracking.",
    )

    @model_validator(mode="after")
    def validate_verdict_contract(self) -> "VerificationResult":
        """Enforce internally coherent verifier responses before orchestration."""
        if self.verdict == VerificationVerdict.PASS:
            if self.corrected_output is not None:
                raise ValueError("PASS verdict must not include corrected_output.")
            if self.issues:
                raise ValueError("PASS verdict must not include fidelity issues.")
        elif self.verdict == VerificationVerdict.CORRECTED:
            if self.corrected_output is None:
                raise ValueError("CORRECTED verdict requires corrected_output.")
            if not self.issues:
                raise ValueError("CORRECTED verdict requires at least one issue describing the defect.")
        elif self.verdict == VerificationVerdict.REJECT:
            if self.corrected_output is not None:
                raise ValueError("REJECT verdict must not include corrected_output.")
            if not self.issues:
                raise ValueError("REJECT verdict requires at least one issue explaining the rejection.")
        return self


class VerificationOutcome(BaseModel):
    """Orchestrated verification outcome produced by VerificationService.

    Decides what output becomes effective, enforces verification mode policies,
    and flags human review requirements.
    """
    effective_output: Any | None = Field(
        default=None,
        description="The final output to be used by calling modules.",
    )
    result: VerificationResult | None = Field(
        default=None,
        description="The underlying provider verification result, if verification was attempted.",
    )
    mode: VerificationMode = Field(
        default=VerificationMode.OFF,
        description="Verification mode applied for this evaluation.",
    )
    verification_performed: bool = Field(
        default=False,
        description="Whether an actual verification check was executed.",
    )
    corrected_by_verifier: bool = Field(
        default=False,
        description="Flag indicating whether the effective output includes verifier corrections.",
    )
    requires_human_review: bool = Field(
        default=False,
        description="Flag indicating whether manual human review is required before downstream use.",
    )
    warning: str | None = Field(
        default=None,
        description="Diagnostic or degradation warning (e.g. verifier unavailable in advisory mode).",
    )


class AIMetadata(BaseModel):
    """Standard metadata accompanying AI outputs."""
    generation_provider: str = Field(
        default="ollama",
        description="Name of the provider that generated the result.",
    )
    generation_model: str = Field(
        description="Model identifier/tag used for generation.",
    )
    verification_mode: VerificationMode = Field(
        default=VerificationMode.OFF,
        description="Verification mode applied.",
    )
    verification_provider: str = Field(
        default="none",
        description="Name of the verification provider, if used.",
    )
    verification_status: str | None = Field(
        default=None,
        description="Status string from verification, if any.",
    )
    corrected_by_verifier: bool = Field(
        default=False,
        description="Flag indicating whether verifier revised the output.",
    )
    requires_human_review: bool = Field(
        default=False,
        description="Flag indicating whether human review is mandated.",
    )
    processing_time_ms: float | None = Field(
        default=None,
        description="Processing duration in milliseconds.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Advisory warnings or caveats generated during processing.",
    )


T = TypeVar("T")


class AIResult(BaseModel, Generic[T]):
    """Generic envelope pairing generated data with standardized AI metadata."""
    data: T
    metadata: AIMetadata


# ==============================================================================
# Phase 3: Provenance
# ==============================================================================

class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Provenance tracking for extracted text and candidate rules."""
    source_id: str | None = Field(
        default=None,
        description="ID of the authoritative source or document.",
    )
    document_name: str | None = Field(
        default=None,
        description="Human-readable filename or document title.",
    )
    page_number: int | None = Field(
        default=None, ge=1,
        description="1-based page number where the text originates.",
    )
    section_reference: str | None = Field(
        default=None,
        description="Section, clause, or paragraph reference in the document.",
    )
    exact_source_text: str | None = Field(
        default=None,
        description="Exact raw text snippet from the document/source.",
    )


# ==============================================================================
# Phase 3: Document Classification & Applicant Extraction
# ==============================================================================

class DocumentType(str, Enum):
    """Controlled document type vocabulary aligned with IRIS contracts."""
    REGISTRATION_CERTIFICATE = "REGISTRATION_CERTIFICATE"
    ENVIRONMENTAL_CONSENT = "ENVIRONMENTAL_CONSENT"
    FIRE_CERTIFICATE = "FIRE_CERTIFICATE"
    SITE_PLAN = "SITE_PLAN"
    PROJECT_REPORT = "PROJECT_REPORT"
    INVESTMENT_DECLARATION = "INVESTMENT_DECLARATION"
    PROOF_OF_PREMISES = "PROOF_OF_PREMISES"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class DocumentClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Result of classifying applicant document text."""
    document_type: DocumentType = Field(
        default=DocumentType.UNKNOWN,
        description="Predicted document classification.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Advisory confidence score between 0.0 and 1.0.",
    )
    reasoning: str | None = Field(
        default=None,
        description="Snippet or brief reason supporting the classification.",
    )
    requires_human_review: bool = Field(
        default=False,
        description="Whether classification confidence is low or uncertain.",
    )


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Controlled representation for an extra/unmodelled fact in an applicant document."""
    name: str = Field(description="Normalized name or key of the fact.")
    value: str | float | int | bool = Field(description="Extracted scalar value.")
    unit: str | None = Field(default=None, description="Explicit unit if present.")
    evidence: str | None = Field(default=None, description="Exact supporting text snippet from document.")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Advisory extraction confidence for this fact.")
    source_page: int | None = Field(default=None, ge=1, description="1-based source page when page provenance is available.")


class ApplicantDocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Structured facts extracted from an applicant document."""
    business_name: str | None = Field(default=None, description="Name of company, business, or applicant entity.")
    project_name: str | None = Field(default=None, description="Name of the specific industrial project.")
    registration_number: str | None = Field(default=None, description="Official registration, licence, or NOC number.")
    location: str | None = Field(default=None, description="Reported project location / address string.")
    state: str | None = Field(default=None, description="State (e.g. Maharashtra).")
    district: str | None = Field(default=None, description="District (e.g. Pune).")
    capacity_value: float | None = Field(default=None, description="Installed or proposed capacity number.")
    capacity_unit: str | None = Field(default=None, description="Capacity unit (e.g. TPD, MT/year).")
    investment_crore_inr: float | None = Field(default=None, description="Total project investment in crore INR.")
    worker_count: int | None = Field(default=None, description="Number of workers/employees.")
    authorised_person: str | None = Field(default=None, description="Authorised signatory/person explicitly named in the document.")
    issue_date: str | None = Field(default=None, description="Date of document issue (YYYY-MM-DD).")
    valid_until: str | None = Field(default=None, description="Expiry date or validity end date (YYYY-MM-DD).")
    additional_facts: list[ExtractedFact] = Field(default_factory=list, description="Controlled list of additional facts.")
    field_confidence: dict[str, float] = Field(default_factory=dict, description="Advisory per-field confidence scores in [0,1] for populated standard fields.")
    field_evidence: dict[str, str] = Field(default_factory=dict, description="Exact supporting snippets for populated standard fields where available.")
    field_source_pages: dict[str, int] = Field(default_factory=dict, description="1-based source page per populated standard field when page provenance is available.")
    provenance: Provenance | None = Field(default=None, description="Provenance of the document text.")


class DocumentExtractionResult(BaseModel):
    """High-level result envelope for document AI extraction."""
    data: ApplicantDocumentExtraction
    outcome: VerificationOutcome | None = None
    safety_valid: bool = True
    requires_human_review: bool = False
    warnings: list[str] = Field(default_factory=list)


# ==============================================================================
# Phase 3: Regulatory Candidate Intermediate Representation
# ==============================================================================

class CandidateStatus(str, Enum):
    """AI candidate lifecycle status. Explicitly cannot be ACTIVE."""
    AI_CANDIDATE = "AI_CANDIDATE"


class ConditionLogic(str, Enum):
    """Boolean logic connecting multiple conditions."""
    AND = "AND"
    OR = "OR"


class QualifierType(str, Enum):
    """Generic qualifier types for exceptions, provisos, and unless clauses."""
    EXCEPT = "EXCEPT"
    UNLESS = "UNLESS"
    PROVIDED_THAT = "PROVIDED_THAT"
    OTHER = "OTHER"


class RegulatoryQualifier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Generic regulatory exception or proviso representation."""
    qualifier_type: QualifierType = Field(description="Type of qualification (EXCEPT, UNLESS, PROVIDED_THAT, OTHER).")
    text: str = Field(description="Exact qualifier clause extracted from source text.")


class RegulatoryCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Intermediate representation of an extracted regulatory condition."""
    fact_text: str = Field(description="Normalized fact identifier or plain description (e.g. 'production capacity', 'worker count').")
    comparison_text: str | None = Field(default=None, description="Comparison operator phrase (e.g. 'greater than', 'at least', 'between', 'not exceeding').")
    value: float | str | bool | None = Field(default=None, description="Exact threshold or value for single-point comparisons.")
    lower_value: float | None = Field(default=None, description="Lower bound for range conditions.")
    upper_value: float | None = Field(default=None, description="Upper bound for range conditions.")
    unit: str | None = Field(default=None, description="Unit of measurement (e.g. 'TPD', 'crore INR', 'litres per day', 'workers').")
    is_numeric: bool = Field(default=True, description="Whether the condition is numeric or qualitative.")
    raw_snippet: str | None = Field(default=None, description="Exact text snippet from which the condition was extracted.")


class RegulatoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Intermediate AI candidate representation extracted from regulatory text.

    This is an intermediate extraction artifact for authoring workflows, NOT an ACTIVE rule.
    """
    is_regulatory_requirement: bool = Field(description="Whether the text defines an actionable regulatory requirement.")
    requirement_text: str | None = Field(default=None, description="Name or description of the required approval, NOC, licence, or plan.")
    status: CandidateStatus = Field(default=CandidateStatus.AI_CANDIDATE, description="Lifecycle status; always AI_CANDIDATE.")
    conditions: list[RegulatoryCondition] = Field(default_factory=list, description="Extracted conditions required for applicability.")
    condition_logic: ConditionLogic | None = Field(default=None, description="Logical operator between conditions (AND/OR).")
    timing_text: str | None = Field(default=None, description="Timing, stage, or deadline wording (e.g. 'before commercial operation').")
    qualifiers: list[RegulatoryQualifier] = Field(default_factory=list, description="Exceptions, unless clauses, and provisos.")
    provenance: Provenance | None = Field(default=None, description="Provenance linking back to official regulatory document.")
    requires_human_review: bool = Field(default=False, description="Whether human review is required before rule authoring.")
    review_reasons: list[str] = Field(default_factory=list, description="Reasons flagging why human review is required.")
    issuing_authority: str | None = Field(default=None, description="Issuing authority explicitly stated in the regulatory source, if present.")
    required_documents: list[str] = Field(default_factory=list, description="Documents explicitly required by the source clause, if any.")
    field_confidence: dict[str, float] = Field(default_factory=dict, description="Advisory confidence by candidate field for reviewer attention; never legal confidence.")


class RegulatoryCandidateResult(BaseModel):
    """High-level result envelope for regulatory AI candidate extraction."""
    candidate: RegulatoryCandidate
    outcome: VerificationOutcome | None = None
    safety_valid: bool = True
    requires_human_review: bool = False
    warnings: list[str] = Field(default_factory=list)


# ==============================================================================
# Phase 3: Safety Validation Result
# ==============================================================================

class SafetyIssue(BaseModel):
    """Structured issue produced by SafetyValidator."""
    code: str = Field(description="Machine-readable issue code (e.g., NEGATIVE_WORKER_COUNT, REVERSED_RANGE).")
    field: str | None = Field(default=None, description="Field name where safety defect occurred.")
    message: str = Field(description="Explanation of the safety defect.")
    severity: str = Field(default="ERROR", description="Issue severity: ERROR or WARNING.")


class SafetyValidationResult(BaseModel):
    """Structured result returned by SafetyValidator."""
    valid: bool = Field(description="True if no blocking ERROR-level safety issues were found.")
    requires_human_review: bool = Field(default=False, description="True if any issues or warnings require review.")
    issues: list[SafetyIssue] = Field(default_factory=list, description="Detailed list of safety issues detected.")


# ==============================================================================
# Phase 4: Retrieval Index & RAG Schemas
# ==============================================================================

class ChunkMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Controlled metadata for a regulatory source chunk. No arbitrary dicts."""
    authority: str | None = Field(default=None, description="Issuing authority (e.g. Maharashtra Pollution Control Board).")
    jurisdiction: str | None = Field(default=None, description="Jurisdiction/state this chunk applies to.")
    effective_date: str | None = Field(default=None, description="Date from which this section became effective (YYYY-MM-DD).")
    act_or_rule: str | None = Field(default=None, description="Formal Act or Rule name this chunk belongs to.")


class RegulatorySourceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """A single retrievable regulatory text chunk with full provenance.

    Designed as the unit consumed by RetrievalService.index_chunks() and
    returned in RetrievalResult. Upstream owners (Regulatory Sources module)
    prepare chunks; the AI module does not own PDF/OCR.
    """
    chunk_id: str = Field(description="Unique identifier for this chunk within the source.")
    source_id: str = Field(description="ID of the parent regulatory source/document.")
    text: str = Field(description="Extracted regulatory text for this chunk.")
    document_name: str | None = Field(default=None, description="Human-readable document or publication name.")
    page_number: int | None = Field(default=None, ge=1, description="1-based page number in the source document.")
    section_reference: str | None = Field(default=None, description="Section, clause, or sub-section reference.")
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata, description="Controlled structured metadata.")


class RetrievalResult(BaseModel):
    """Single result from a semantic similarity search."""
    chunk: RegulatorySourceChunk = Field(description="The matched regulatory chunk.")
    similarity_score: float = Field(ge=-1.0, le=1.0, description="Cosine similarity score (-1.0 to 1.0). Informational only; not legal confidence.")
    rank: int = Field(ge=1, description="1-based rank in the result list (1 = most similar).")


class SourceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Citation referencing a supplied regulatory source chunk."""
    chunk_id: str = Field(description="ID of the cited chunk (must match a supplied chunk).")
    source_id: str = Field(description="Parent source document ID.")
    document_name: str | None = Field(default=None, description="Document name for display.")
    page_number: int | None = Field(default=None, description="Page number in the source document.")
    section_reference: str | None = Field(default=None, description="Section or clause reference.")


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Structured RAG answer grounded in supplied regulatory sources.

    LLM output. Validated by Python citation checks after generation.
    """
    answer: str = Field(description="Plain-language answer grounded in supplied sources.")
    citations: list[SourceCitation] = Field(
        default_factory=list,
        description="Citations to the supplied source chunks supporting the answer.",
    )
    insufficient_information: bool = Field(
        default=False,
        description="True when supplied sources do not contain enough information to answer the question.",
    )
    warnings: list[str] = Field(default_factory=list, description="Warnings about answer quality or grounding.")


class GroundedAnswerResult(BaseModel):
    """High-level result envelope for a grounded RAG answer."""
    answer: GroundedAnswer
    outcome: VerificationOutcome | None = None
    retrieved_chunks: list[RetrievalResult] = Field(default_factory=list)
    citations_valid: bool = True
    requires_human_review: bool = False
    warnings: list[str] = Field(default_factory=list)


# ==============================================================================
# Phase 5: Grounded Explanation Schemas
# ==============================================================================

# --- Authoritative Input Schemas ---

class RequirementTraceInput(BaseModel):
    """Authoritative input from the Rule Engine evaluation trace."""
    requirement: str = Field(description="Name or code of the regulatory requirement.")
    outcome: str = Field(description="Canonical evaluation outcome: APPLICABLE, CONDITIONAL, or NOT_APPLICABLE.")
    relevant_project_facts: dict[str, Any] = Field(default_factory=dict, description="Project facts used in the evaluation.")
    rule_summary: str | None = Field(default=None, description="Summary of the rule condition evaluated.")
    trace_reason: str | None = Field(default=None, description="Engine trace reason.")
    missing_facts: list[str] = Field(default_factory=list, description="Missing fact identifiers causing CONDITIONAL outcome.")
    source_provenance: Provenance | dict[str, Any] | None = Field(default=None, description="Source provenance reference if available.")


class DependencyInput(BaseModel):
    """Authoritative input from NetworkX dependency analysis."""
    requirement: str = Field(description="Requirement identifier/name being evaluated.")
    status: str = Field(description="Graph status: BLOCKED, INDEPENDENT, or AVAILABLE.")
    blocked_by: list[str] = Field(default_factory=list, description="List of prerequisite requirement names/IDs that block this node.")
    reason_code: str | None = Field(default=None, description="Reason code, e.g. PREREQUISITE_INCOMPLETE.")
    requirement_on_critical_path: bool | None = Field(default=None, description="Whether this specific requirement is on the critical path.")
    critical_path_nodes: list[str] = Field(default_factory=list, description="Known critical path nodes if explicitly supplied.")


class ParallelCandidateInput(BaseModel):
    """Authoritative input for parallel candidate requirements."""
    requirements: list[str] = Field(default_factory=list, description="Requirements identified as parallel candidates.")
    classification: str = Field(default="PARALLEL_CANDIDATES", description="Graph classification: PARALLEL_CANDIDATES or POTENTIALLY_PARALLELISABLE.")
    reason: str | None = Field(default=None, description="Authoritative reason for parallel classification.")


class CriticalPathInput(BaseModel):
    """Authoritative input from NetworkX longest-path computation."""
    critical_path: list[str] = Field(default_factory=list, description="Ordered sequence of requirement names forming the critical path.")
    estimated_total_duration_days: int | float | None = Field(default=None, description="Computed total duration in days.")
    reason: str | None = Field(default=None, description="Additional context or notes if supplied.")


class DocumentIssueInput(BaseModel):
    """Authoritative input from document consistency/validation engine."""
    field_name: str = Field(description="Field name exhibiting the defect or inconsistency.")
    issue_type: str = Field(default="INCONSISTENCY", description="Issue category: INCONSISTENCY, MISSING_REQUIRED_FIELD, etc.")
    severity: str = Field(default="BLOCKING", description="Issue severity: BLOCKING, WARNING, etc.")
    expected_value: int | float | str | bool | None = Field(default=None, description="Expected value from project profile.")
    actual_value: int | float | str | bool | None = Field(default=None, description="Actual value extracted from document.")
    unit: str | None = Field(default=None, description="Explicit unit if present in source data; None if no unit supplied.")
    message: str | None = Field(default=None, description="Validation engine issue message.")


class ImpactChangeInput(BaseModel):
    """Authoritative input from regulatory impact diff engine."""
    changed_fact: str = Field(description="Name of the project fact that was changed.")
    old_value: int | float | str | bool | None = Field(default=None, description="Previous fact value.")
    new_value: int | float | str | bool | None = Field(default=None, description="Updated fact value.")
    newly_applicable: list[str] = Field(default_factory=list, description="Requirements that became newly applicable.")
    no_longer_applicable: list[str] = Field(default_factory=list, description="Requirements no longer applicable.")
    dependency_changes: list[str] | dict[str, Any] = Field(default_factory=list, description="Changes to dependencies if supplied.")
    critical_path_changed: bool = Field(default=False, description="Whether the critical path changed.")
    condition_trace: str | None = Field(default=None, description="Condition trace if supplied; None if exact threshold is not provided.")


class SLAInput(BaseModel):
    """Authoritative input from SLA tracking module."""
    status: str = Field(description="Computed SLA status: ON_TRACK, APPROACHING, or BREACHED.")
    total_days: int | float | None = Field(default=None, description="Total SLA policy duration in days.")
    elapsed_days: int | float | None = Field(default=None, description="Elapsed counted duration in days.")
    remaining_days: int | float | None = Field(default=None, description="Remaining days until deadline.")
    paused: bool = Field(default=False, description="Whether SLA clock is paused.")
    pause_reason: str | None = Field(default=None, description="Reason for pause if paused.")
    delay_factors: list[str] = Field(default_factory=list, description="Configured delay factors if any.")
    responsible_authority: str | None = Field(default=None, description="Responsible authority if explicitly supplied; None if absent.")
    context_question: str | None = Field(default=None, description="Optional caller inquiry or context.")


class SchemeMatchInput(BaseModel):
    """Authoritative input from scheme matching engine."""
    scheme_name: str = Field(description="Name of the industrial scheme.")
    eligibility_outcome: str = Field(default="POTENTIALLY_ELIGIBLE", description="Canonical scheme presentation outcome: POTENTIALLY_ELIGIBLE, NOT_ELIGIBLE_BY_CURATED_RULES, or CONDITIONAL.")
    matched_conditions: list[str] = Field(default_factory=list, description="List of matched condition summaries.")
    required_documents: list[str] = Field(default_factory=list, description="List of required application documents.")
    disclaimer: str | None = Field(default="Final eligibility requires official verification.", description="Authoritative disclaimer.")


class RiskInput(BaseModel):
    """Authoritative input from risk/analytics module."""
    risk_score: int | float = Field(description="Computed risk score (e.g. 0-100).")
    risk_level: str | None = Field(default=None, description="Risk level classification if supplied (e.g. ELEVATED, LOW).")
    factors: list[dict[str, Any]] | list[str] = Field(default_factory=list, description="Risk factor breakdown.")
    purpose: str | None = Field(default="review prioritisation", description="Stated purpose of the risk score.")


class OfficialQueryInput(BaseModel):
    """Authoritative input representing an official government query."""
    official_text: str = Field(description="Immutable official query text exactly as issued.")
    related_requirement: str | None = Field(default=None, description="Relevant requirement identifier/name when supplied by workflow data.")
    related_document: str | None = Field(default=None, description="Relevant document identifier/type when supplied by workflow data.")
    query_id: str | None = Field(default=None, description="Unique query identifier.")
    application_id: str | None = Field(default=None, description="Associated application ID.")
    status: str | None = Field(default=None, description="Query status (e.g. OPEN, RESPONDED).")


class ApplicationStatusInput(BaseModel):
    """Authoritative input representing application workflow status."""
    status: str = Field(description="Canonical application state, e.g. SUBMITTED, UNDER_REVIEW, READY_FOR_SUBMISSION.")
    application_id: str | None = Field(default=None, description="Application identifier.")
    reasons: list[str] = Field(default_factory=list, description="Supplied reasons for the current state.")
    pending_actions: list[str] = Field(default_factory=list, description="Pending actions supplied by workflow engine.")


# --- Explanation Structured Outputs (with Structured Fidelity Fields) ---

class ExplanationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Common base structured explanation output."""
    explanation: str = Field(description="Clear, plain-language explanation of the supplied authoritative data.")
    action_guidance: str | None = Field(default=None, description="Actionable guidance for the applicant or officer if applicable.")
    insufficient_information: bool = Field(default=False, description="True when supplied information is insufficient to address the query.")
    warnings: list[str] = Field(default_factory=list, description="Advisory caveats or warnings.")


class RequirementTraceExplanation(ExplanationOutput):
    """Structured explanation for a requirement evaluation trace."""
    requirement: str = Field(description="Fidelity copy of requirement identifier/name.")
    outcome: str = Field(description="Fidelity copy of evaluation outcome (APPLICABLE, CONDITIONAL, NOT_APPLICABLE).")
    missing_facts: list[str] = Field(default_factory=list, description="Missing fact names identified.")


class DependencyExplanation(ExplanationOutput):
    """Structured explanation for a dependency/blocker result."""
    requirement: str | None = Field(default=None, description="Fidelity copy of requirement name.")
    status: str | None = Field(default=None, description="Fidelity copy of node status (e.g. BLOCKED).")
    reason_code: str | None = Field(default=None, description="Fidelity copy of dependency reason code when supplied.")
    blocked_by: list[str] = Field(default_factory=list, description="Fidelity copy of blocker names/IDs.")
    requirement_on_critical_path: bool | None = Field(default=None, description="Fidelity copy of critical path flag.")
    critical_path_nodes: list[str] = Field(default_factory=list, description="Explicit critical path nodes if supplied.")
    parallel_candidates: list[str] = Field(default_factory=list, description="Parallel candidate requirements if applicable.")


class ParallelCandidateExplanation(ExplanationOutput):
    """Structured explanation for parallel candidate requirements."""
    requirements: list[str] = Field(default_factory=list, description="Fidelity copy of parallel candidate requirements.")
    classification: str = Field(default="PARALLEL_CANDIDATES", description="Fidelity copy of classification.")
    reason: str | None = Field(default=None, description="Fidelity copy of supplied graph reason when present.")


class CriticalPathExplanation(ExplanationOutput):
    """Structured explanation for the critical path."""
    critical_path: list[str] = Field(default_factory=list, description="Fidelity copy of ordered critical path sequence.")
    estimated_total_duration_days: int | float | None = Field(default=None, description="Fidelity copy of total duration in days.")


class DocumentIssueExplanation(ExplanationOutput):
    """Structured explanation for a document validation defect or inconsistency."""
    field_name: str | None = Field(default=None, description="Fidelity copy of affected field name.")
    issue_type: str | None = Field(default=None, description="Fidelity copy of issue type.")
    severity: str | None = Field(default=None, description="Fidelity copy of severity.")
    expected_value: int | float | str | bool | None = Field(default=None, description="Fidelity copy of expected value (scalar: number, string, boolean, or null).")
    actual_value: int | float | str | bool | None = Field(default=None, description="Fidelity copy of actual value (scalar: number, string, boolean, or null).")
    unit: str | None = Field(default=None, description="Fidelity copy of unit (must remain None if not supplied).")


class ImpactChangeExplanation(ExplanationOutput):
    """Structured explanation for regulatory impact diff."""
    changed_fact: str | None = Field(default=None, description="Fidelity copy of changed fact name.")
    old_value: int | float | str | bool | None = Field(default=None, description="Fidelity copy of old value (scalar).")
    new_value: int | float | str | bool | None = Field(default=None, description="Fidelity copy of new value (scalar).")
    newly_applicable: list[str] = Field(default_factory=list, description="Fidelity copy of newly applicable list.")
    no_longer_applicable: list[str] = Field(default_factory=list, description="Fidelity copy of no longer applicable list.")
    dependency_changes: list[str] | dict[str, Any] = Field(default_factory=list, description="Fidelity copy of supplied dependency changes.")
    critical_path_changed: bool = Field(default=False, description="Fidelity copy of whether the critical path changed.")


class SLAExplanation(ExplanationOutput):
    """Structured explanation for SLA timing and delays."""
    status: str | None = Field(default=None, description="Fidelity copy of SLA status.")
    total_days: int | float | None = Field(default=None, description="Fidelity copy of total days.")
    elapsed_days: int | float | None = Field(default=None, description="Fidelity copy of elapsed days.")
    remaining_days: int | float | None = Field(default=None, description="Fidelity copy of remaining days.")
    paused: bool = Field(default=False, description="Fidelity copy of whether the SLA clock is paused.")
    pause_reason: str | None = Field(default=None, description="Fidelity copy of pause reason when supplied.")
    delay_factors: list[str] = Field(default_factory=list, description="Fidelity copy of delay factors.")
    responsible_authority: str | None = Field(default=None, description="Fidelity copy of responsible authority (must remain None if not supplied).")


class SchemeExplanation(ExplanationOutput):
    """Structured explanation for scheme matching."""
    scheme_name: str | None = Field(default=None, description="Fidelity copy of scheme name.")
    eligibility_outcome: str | None = Field(default=None, description="Fidelity copy of eligibility outcome (e.g. POTENTIALLY_ELIGIBLE).")
    matched_conditions: list[str] = Field(default_factory=list, description="Fidelity copy of matched conditions.")
    required_documents: list[str] = Field(default_factory=list, description="Fidelity copy of required documents.")
    disclaimer: str | None = Field(default=None, description="Fidelity copy of the scheme disclaimer when supplied.")


class RiskExplanation(ExplanationOutput):
    """Structured explanation for risk assessment."""
    risk_score: int | float | None = Field(default=None, description="Fidelity copy of risk score.")
    risk_level: str | None = Field(default=None, description="Fidelity copy of risk level.")
    factors: list[dict[str, Any]] | list[str] = Field(default_factory=list, description="Fidelity copy of factors.")
    purpose: str | None = Field(default=None, description="Fidelity copy of the advisory purpose of the risk score.")


class OfficialQueryExplanation(ExplanationOutput):
    """Structured explanation for an official government query."""
    official_text: str = Field(description="Fidelity copy of the immutable official query text.")
    requested_action: str | None = Field(default=None, description="Action requested by the official query (e.g. clarification).")
    additional_document_requested: bool = Field(default=False, description="Explicit boolean: true if an additional document is requested; false if explicitly not requested or none requested.")
    related_requirement: str | None = Field(default=None, description="Fidelity copy of relevant requirement when supplied.")
    related_document: str | None = Field(default=None, description="Fidelity copy of relevant document when supplied.")


class ApplicationStatusExplanation(ExplanationOutput):
    """Structured explanation for application status."""
    status: str | None = Field(default=None, description="Fidelity copy of application status.")
    reasons: list[str] = Field(default_factory=list, description="Fidelity copy of reasons.")
    pending_actions: list[str] = Field(default_factory=list, description="Fidelity copy of workflow-supplied pending actions.")


# --- Explanation High-Level Result Envelope ---

E = TypeVar("E", bound=ExplanationOutput)


class ExplanationResult(BaseModel, Generic[E]):
    """Unified envelope for AI-generated explanations."""
    data: E
    outcome: VerificationOutcome | None = None
    fidelity_valid: bool = True
    requires_human_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    processing_time_ms: float | None = None

    @property
    def explanation(self) -> str:
        return getattr(self.data, "explanation", "")

    @property
    def action_guidance(self) -> str | None:
        return getattr(self.data, "action_guidance", None)

    @property
    def insufficient_information(self) -> bool:
        return getattr(self.data, "insufficient_information", False)

    @property
    def corrected_by_verifier(self) -> bool:
        return self.outcome.corrected_by_verifier if self.outcome else False

    @property
    def verification_status(self) -> str | None:
        if self.outcome and self.outcome.result:
            return self.outcome.result.verdict.value
        if self.outcome and self.outcome.warning:
            return "UNAVAILABLE"
        return None


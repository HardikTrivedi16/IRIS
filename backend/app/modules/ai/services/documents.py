"""Document AI Service for IRIS.

Handles applicant document fact extraction and classification.
Uses CoreAIService for local structured generation, VerificationService
for advisory fidelity verification, and SafetyValidator for sanity checks.
Does NOT perform OCR or depend on business modules.
"""

from app.modules.ai.exceptions import AIInvalidOutputError
from app.modules.ai.prompts.documents import (
    DOCUMENT_EXTRACTION_SYSTEM_PROMPT,
    build_document_classification_prompt,
    build_document_extraction_prompt,
)
from app.modules.ai.schemas import (
    ApplicantDocumentExtraction,
    DocumentClassificationResult,
    DocumentExtractionResult,
    DocumentType,
    Provenance,
    VerificationMode,
)
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.verification import VerificationService
from app.modules.ai.validators.safety import SafetyValidator


class DocumentAIService:
    """Service providing AI extraction and classification for applicant documents."""

    def __init__(
        self,
        core: CoreAIService,
        verification: VerificationService,
        low_confidence_threshold: float = 0.75,
    ) -> None:
        self._core = core
        self._verification = verification
        self._low_confidence_threshold = low_confidence_threshold

    def extract(
        self,
        text: str,
        document_type: DocumentType | str | None = None,
        provenance: Provenance | None = None,
    ) -> DocumentExtractionResult:
        """Extract structured applicant facts from supplied document text.

        Pipeline:
            text -> CoreAIService (generate_structured) -> VerificationService (ADVISORY) -> SafetyValidator
        """
        if not isinstance(text, str) or not text.strip():
            raise AIInvalidOutputError("Document text must not be empty or whitespace-only.")
        doc_type_str = str(document_type.value if isinstance(document_type, DocumentType) else (document_type or ""))
        prompt = f"{DOCUMENT_EXTRACTION_SYSTEM_PROMPT}\n\n{build_document_extraction_prompt(text, doc_type_str)}"

        # 1. Local generation via CoreAIService
        raw_extraction: ApplicantDocumentExtraction = self._core.generate_structured(
            prompt=prompt,
            schema=ApplicantDocumentExtraction,
            temperature=0.0,
            think=False,
        )

        # Caller-supplied provenance is authoritative metadata and must override
        # model-generated provenance rather than being ignored when the model invents one.
        if provenance is not None:
            raw_extraction.provenance = provenance.model_copy(deep=True)
            if not raw_extraction.provenance.exact_source_text:
                raw_extraction.provenance.exact_source_text = text
        elif raw_extraction.provenance is not None and not raw_extraction.provenance.exact_source_text:
            raw_extraction.provenance.exact_source_text = text

        # 2. Verification via VerificationService (default ADVISORY)
        outcome = self._verification.verify(
            task_type="applicant_document_extraction",
            authoritative_input=text,
            local_output=raw_extraction,
            output_schema=ApplicantDocumentExtraction,
        )

        effective_extraction = raw_extraction
        if outcome.effective_output is not None and isinstance(outcome.effective_output, ApplicantDocumentExtraction):
            effective_extraction = outcome.effective_output

        # Verifier corrections may not rewrite caller-supplied provenance.
        if provenance is not None:
            effective_extraction.provenance = provenance.model_copy(deep=True)
            if not effective_extraction.provenance.exact_source_text:
                effective_extraction.provenance.exact_source_text = text

        # 3. Deterministic Safety Validation
        safety_res = SafetyValidator.validate_document_extraction(
            effective_extraction,
            source_text=text,
            low_confidence_threshold=self._low_confidence_threshold,
        )

        # 4. Assemble warnings and review flags
        warnings: list[str] = []
        if outcome.warning:
            warnings.append(outcome.warning)
        if outcome.result and outcome.result.issues:
            for v_issue in outcome.result.issues:
                warnings.append(f"[{v_issue.code}] {v_issue.message}")

        for issue in safety_res.issues:
            warnings.append(f"[{issue.code}] {issue.message}")

        requires_review = (
            outcome.requires_human_review
            or safety_res.requires_human_review
            or not safety_res.valid
        )

        return DocumentExtractionResult(
            data=effective_extraction,
            outcome=outcome,
            safety_valid=safety_res.valid,
            requires_human_review=requires_review,
            warnings=warnings,
        )

    def classify(self, text: str) -> DocumentClassificationResult:
        """Classify document text into one of the controlled document types.

        Verification is OFF by default for classification.
        """
        if not isinstance(text, str) or not text.strip():
            raise AIInvalidOutputError("Document text must not be empty or whitespace-only.")
        prompt = build_document_classification_prompt(text)
        result = self._core.generate_structured(
            prompt=prompt,
            schema=DocumentClassificationResult,
            temperature=0.0,
            think=False,
        )
        if result.document_type == DocumentType.UNKNOWN or result.confidence < self._low_confidence_threshold:
            result.requires_human_review = True
        return result

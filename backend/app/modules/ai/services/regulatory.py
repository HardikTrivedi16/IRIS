"""Regulatory AI Service for IRIS.

Extracts candidate regulatory requirements, conditions, comparison phrases,
and qualifiers (exceptions, unless clauses) from authoritative regulatory text.
Uses CoreAIService, VerificationService, and SafetyValidator.
Never evaluates project applicability and never activates rules.
"""

from app.modules.ai.exceptions import AIInvalidOutputError, AIVerificationError
from app.modules.ai.prompts.regulatory import (
    REGULATORY_EXTRACTION_SYSTEM_PROMPT,
    build_regulatory_extraction_prompt,
)
from app.modules.ai.schemas import (
    CandidateStatus,
    Provenance,
    RegulatoryCandidate,
    RegulatoryCandidateResult,
    VerificationMode,
)
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.verification import VerificationService
from app.modules.ai.validators.safety import SafetyValidator


class RegulatoryAIService:
    """Service providing AI-assisted candidate extraction from regulatory documents."""

    def __init__(
        self,
        core: CoreAIService,
        verification: VerificationService,
        low_confidence_threshold: float = 0.75,
    ) -> None:
        self._core = core
        self._verification = verification
        self._low_confidence_threshold = low_confidence_threshold

    def extract_candidate(
        self,
        source_text: str,
        provenance: Provenance | None = None,
    ) -> RegulatoryCandidateResult:
        """Extract a regulatory candidate intermediate representation from source text.

        Pipeline:
            source_text -> CoreAIService -> VerificationService (REQUIRED if enabled) -> SafetyValidator
        """
        if not isinstance(source_text, str) or not source_text.strip():
            raise AIInvalidOutputError("Regulatory source text must not be empty or whitespace-only.")
        prompt = f"{REGULATORY_EXTRACTION_SYSTEM_PROMPT}\n\n{build_regulatory_extraction_prompt(source_text)}"

        # 1. Local generation via CoreAIService
        raw_candidate: RegulatoryCandidate = self._core.generate_structured(
            prompt=prompt,
            schema=RegulatoryCandidate,
            temperature=0.0,
            think=False,
        )

        # Enforce candidate status invariant: NEVER ACTIVE
        raw_candidate.status = CandidateStatus.AI_CANDIDATE

        # Attach provenance
        if provenance is not None:
            raw_candidate.provenance = provenance
            if not raw_candidate.provenance.exact_source_text:
                raw_candidate.provenance.exact_source_text = source_text
        elif raw_candidate.provenance is None:
            raw_candidate.provenance = Provenance(exact_source_text=source_text)
        elif not raw_candidate.provenance.exact_source_text:
            raw_candidate.provenance.exact_source_text = source_text

        # 2. Verification via VerificationService
        verification_warning: str | None = None
        outcome = None

        try:
            outcome = self._verification.verify(
                task_type="regulatory_candidate_extraction",
                authoritative_input=source_text,
                local_output=raw_candidate,
                output_schema=RegulatoryCandidate,
            )
        except (AIVerificationError, AIInvalidOutputError) as v_err:
            # REQUIRED verification rejection/unavailability or an invalid verifier
            # correction must degrade to an explicit human-review candidate rather
            # than escape as trusted data or crash the authoring workflow.
            verification_warning = f"Verification failed in REQUIRED mode: {v_err}"
            raw_candidate.requires_human_review = True
            raw_candidate.review_reasons.append(verification_warning)

        effective_candidate = raw_candidate
        if outcome and outcome.effective_output is not None and isinstance(outcome.effective_output, RegulatoryCandidate):
            effective_candidate = outcome.effective_output

        # Enforce candidate status invariant again post-verification
        effective_candidate.status = CandidateStatus.AI_CANDIDATE

        # Verifier corrections may not rewrite authoritative caller-supplied provenance.
        if provenance is not None:
            effective_candidate.provenance = provenance.model_copy(deep=True)
            if not effective_candidate.provenance.exact_source_text:
                effective_candidate.provenance.exact_source_text = source_text

        # 3. Deterministic Safety Validation (passing source_text separately)
        safety_res = SafetyValidator.validate_regulatory_candidate(
            candidate=effective_candidate,
            source_text=source_text,
        )

        # 4. Contract-level human gate. Every AI-authored regulatory candidate is
        # non-executable and requires authorised human review before it can enter the
        # DRAFT -> UNDER_REVIEW -> VERIFIED -> ACTIVE lifecycle.
        effective_candidate.requires_human_review = True
        mandatory_reason = "AI-assisted regulatory candidate requires authorised human review before rule verification or activation."
        if mandatory_reason not in effective_candidate.review_reasons:
            effective_candidate.review_reasons.append(mandatory_reason)
        for field_name, confidence in effective_candidate.field_confidence.items():
            if confidence < self._low_confidence_threshold:
                reason = f"Low confidence for {field_name}: {confidence:.2f} < {self._low_confidence_threshold:.2f}."
                if reason not in effective_candidate.review_reasons:
                    effective_candidate.review_reasons.append(reason)

        # 5. Assemble warnings and review flags
        warnings: list[str] = []
        if verification_warning:
            warnings.append(verification_warning)
        if outcome and outcome.warning:
            warnings.append(outcome.warning)

        for issue in safety_res.issues:
            warnings.append(f"[{issue.code}] {issue.message}")

        requires_review = True

        return RegulatoryCandidateResult(
            candidate=effective_candidate,
            outcome=outcome,
            safety_valid=safety_res.valid and verification_warning is None,
            requires_human_review=requires_review,
            warnings=warnings,
        )

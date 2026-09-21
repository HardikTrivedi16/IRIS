"""Explanation Service for IRIS AI Module (Phase 5).

Provides grounded plain-language explanations of already-computed IRIS results:
- Rule Engine evaluation traces (applicability / conditional requirements)
- NetworkX dependency and blocker graphs
- Critical path and estimated duration
- Document consistency defects and mismatches
- Regulatory impact recalculation diffs
- SLA timing and delay tracking
- Scheme matching and potential eligibility
- Risk indicators and review prioritisation
- Official government queries
- Application workflow status

Architectural Principles:
- AI UNDERSTANDS. RULES DECIDE. GRAPHS ORGANISE. ANALYTICS IDENTIFY. HUMANS DECIDE.
- The AI explains supplied results; it NEVER recalculates, overrides, or decides.
- Zero business module imports (no Rule Engine, no NetworkX, no SLA, no Risk, no DB).
- Uses VerificationService (default ADVISORY mode) for secondary verification.
- Uses deterministic SafetyValidator for fidelity and sanity checking.
"""

import time
from typing import Any, Callable, TypeVar
from pydantic import BaseModel

from app.modules.ai.exceptions import AIError
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
from app.modules.ai.schemas import (
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
from app.modules.ai.services.verification import VerificationService
from app.modules.ai.validators.safety import SafetyValidator

E = TypeVar("E", bound=ExplanationOutput)


class ExplanationService:
    """Grounded explanation service for already-computed IRIS results.

    Public interface:
        requirement_trace(...)
        dependency(...)
        parallel_candidates(...)
        critical_path(...)
        document_issue(...)
        impact_change(...)
        sla(...)
        scheme(...)
        risk(...)
        official_query(...)
        application_status(...)
    """

    def __init__(
        self,
        core: CoreAIService,
        verification: VerificationService,
    ) -> None:
        self._core = core
        self._verification = verification

    # -------------------------------------------------------------------------
    # Generic Orchestration Pipeline
    # -------------------------------------------------------------------------

    def _run_pipeline(
        self,
        task_type: str,
        input_obj: BaseModel,
        prompt_builder: Callable[[Any], str],
        schema: type[E],
    ) -> ExplanationResult[E]:
        """Execute the standardized explanation pipeline:

        Input → Prompt → CoreAIService (generate_structured)
              → VerificationService (ADVISORY)
              → SafetyValidator.validate_explanation (Deterministic)
              → ExplanationResult[E]
        """
        start_time = time.perf_counter()

        prompt = f"{SHARED_EXPLANATION_SYSTEM_PROMPT}\n\n{prompt_builder(input_obj)}"

        # 1. Local generation via CoreAIService (temperature=0.0, think=False)
        raw_output: E = self._core.generate_structured(
            prompt=prompt,
            schema=schema,
            temperature=0.0,
            think=False,
        )

        # 2. Verification via VerificationService (ADVISORY)
        outcome = None
        verification_warning: str | None = None
        try:
            outcome = self._verification.verify(
                task_type=task_type,
                authoritative_input=input_obj.model_dump(),
                local_output=raw_output,
                output_schema=schema,
            )
        except AIError as exc:
            verification_warning = f"Verification unavailable: {exc}"

        effective_output: E = raw_output
        if outcome and outcome.effective_output is not None and isinstance(outcome.effective_output, schema):
            effective_output = outcome.effective_output

        # 3. Deterministic Safety & Fidelity Validation
        safety_res = SafetyValidator.validate_explanation(
            task_type=task_type,
            authoritative_input=input_obj,
            output=effective_output,
        )

        # 4. Assemble warnings and review flags
        warnings: list[str] = list(effective_output.warnings or [])
        if verification_warning:
            warnings.append(verification_warning)
        if outcome and outcome.warning:
            warnings.append(outcome.warning)
        if outcome and outcome.result and outcome.result.issues:
            for issue in outcome.result.issues:
                warnings.append(f"[{issue.code}] {issue.message}")
        for s_issue in safety_res.issues:
            warnings.append(f"[{s_issue.code}] {s_issue.message}")

        requires_review = (
            not safety_res.valid
            or safety_res.requires_human_review
            or (outcome is not None and outcome.requires_human_review)
            or verification_warning is not None
            or effective_output.insufficient_information
        )

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return ExplanationResult[E](
            data=effective_output,
            outcome=outcome,
            fidelity_valid=safety_res.valid,
            requires_human_review=requires_review,
            warnings=warnings,
            processing_time_ms=duration_ms,
        )

    # -------------------------------------------------------------------------
    # Task-Specific Public Methods
    # -------------------------------------------------------------------------

    def requirement_trace(
        self,
        data: RequirementTraceInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[RequirementTraceExplanation]:
        """Explain an already-computed Rule Engine evaluation trace."""
        if isinstance(data, RequirementTraceInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = RequirementTraceInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_requirement_trace",
            input_obj=input_obj,
            prompt_builder=build_requirement_trace_prompt,
            schema=RequirementTraceExplanation,
        )

    def dependency(
        self,
        data: DependencyInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[DependencyExplanation]:
        """Explain an already-computed NetworkX dependency/blocker status."""
        if isinstance(data, DependencyInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = DependencyInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_dependency",
            input_obj=input_obj,
            prompt_builder=build_dependency_prompt,
            schema=DependencyExplanation,
        )

    def parallel_candidates(
        self,
        data: ParallelCandidateInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[ParallelCandidateExplanation]:
        """Explain requirements identified as potential parallel candidates."""
        if isinstance(data, ParallelCandidateInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = ParallelCandidateInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_parallel_candidates",
            input_obj=input_obj,
            prompt_builder=build_parallel_candidate_prompt,
            schema=ParallelCandidateExplanation,
        )

    def critical_path(
        self,
        data: CriticalPathInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[CriticalPathExplanation]:
        """Explain an already-computed critical path and total duration."""
        if isinstance(data, CriticalPathInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = CriticalPathInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_critical_path",
            input_obj=input_obj,
            prompt_builder=build_critical_path_prompt,
            schema=CriticalPathExplanation,
        )

    def document_issue(
        self,
        data: DocumentIssueInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[DocumentIssueExplanation]:
        """Explain an already-computed document inconsistency or defect."""
        if isinstance(data, DocumentIssueInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = DocumentIssueInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_document_issue",
            input_obj=input_obj,
            prompt_builder=build_document_issue_prompt,
            schema=DocumentIssueExplanation,
        )

    def impact_change(
        self,
        data: ImpactChangeInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[ImpactChangeExplanation]:
        """Explain an already-computed regulatory impact recalculation diff."""
        if isinstance(data, ImpactChangeInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = ImpactChangeInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_impact_change",
            input_obj=input_obj,
            prompt_builder=build_impact_change_prompt,
            schema=ImpactChangeExplanation,
        )

    def sla(
        self,
        data: SLAInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[SLAExplanation]:
        """Explain an already-computed application SLA status and timeline."""
        if isinstance(data, SLAInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = SLAInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_sla",
            input_obj=input_obj,
            prompt_builder=build_sla_prompt,
            schema=SLAExplanation,
        )

    def scheme(
        self,
        data: SchemeMatchInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[SchemeExplanation]:
        """Explain an already-computed industrial scheme match result."""
        if isinstance(data, SchemeMatchInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = SchemeMatchInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_scheme",
            input_obj=input_obj,
            prompt_builder=build_scheme_prompt,
            schema=SchemeExplanation,
        )

    def risk(
        self,
        data: RiskInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[RiskExplanation]:
        """Explain an already-computed application risk score and factors."""
        if isinstance(data, RiskInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = RiskInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_risk",
            input_obj=input_obj,
            prompt_builder=build_risk_prompt,
            schema=RiskExplanation,
        )

    def official_query(
        self,
        data: OfficialQueryInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[OfficialQueryExplanation]:
        """Explain an immutable official government query."""
        if isinstance(data, OfficialQueryInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = OfficialQueryInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_official_query",
            input_obj=input_obj,
            prompt_builder=build_official_query_prompt,
            schema=OfficialQueryExplanation,
        )

    def application_status(
        self,
        data: ApplicationStatusInput | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExplanationResult[ApplicationStatusExplanation]:
        """Explain an already-computed application workflow status."""
        if isinstance(data, ApplicationStatusInput):
            input_obj = data
        else:
            payload = dict(data or {})
            payload.update(kwargs)
            input_obj = ApplicationStatusInput.model_validate(payload)

        return self._run_pipeline(
            task_type="explanation_application_status",
            input_obj=input_obj,
            prompt_builder=build_application_status_prompt,
            schema=ApplicationStatusExplanation,
        )

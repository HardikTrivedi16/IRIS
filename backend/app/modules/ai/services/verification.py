"""Verification Service for IRIS AI module.

Orchestrates verification policy across OFF, ADVISORY, and REQUIRED modes.
Separates semantic provider results from application outcome decisions.
Enforces Pydantic schema re-validation on all proposed corrections.
"""

from typing import Any
from pydantic import BaseModel, ValidationError

from app.modules.ai.config import AIConfig
from app.modules.ai.exceptions import (
    AIError,
    AIInvalidOutputError,
    AITimeoutError,
    AIUnavailableError,
    AIVerificationError,
)
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.schemas import (
    VerificationMode,
    VerificationOutcome,
    VerificationResult,
    VerificationVerdict,
)


class VerificationService:
    """Service governing secondary AI output verification policies."""

    def __init__(
        self,
        provider: BaseVerificationProvider,
        mode: VerificationMode = VerificationMode.OFF,
        config: AIConfig | None = None,
    ) -> None:
        self._provider = provider
        self.mode = mode
        self.config = config or AIConfig()

    def verify(
        self,
        task_type: str,
        authoritative_input: Any,
        local_output: Any,
        output_schema: type[BaseModel] | None = None,
    ) -> VerificationOutcome:
        """Verify local output against authoritative input under the active verification mode.

        Args:
            task_type: Identifier of the verification task.
            authoritative_input: The single source of truth for the task.
            local_output: Local Qwen output being checked.
            output_schema: Optional Pydantic model for re-validating corrected outputs.

        Returns:
            VerificationOutcome detailing the effective output and verification status.

        Raises:
            AIVerificationError: In REQUIRED mode if verifier is unavailable or output is rejected.
            AIInvalidOutputError: If proposed correction violates output_schema.
        """
        # ======================================================================
        # 1. OFF MODE
        # ======================================================================
        if self.mode == VerificationMode.OFF:
            return VerificationOutcome(
                effective_output=local_output,
                result=None,
                mode=VerificationMode.OFF,
                verification_performed=False,
                corrected_by_verifier=False,
                requires_human_review=False,
                warning=None,
            )

        # ======================================================================
        # 2. ADVISORY MODE
        # ======================================================================
        if self.mode == VerificationMode.ADVISORY:
            try:
                result = self._provider.verify(
                    task_type=task_type,
                    authoritative_input=authoritative_input,
                    local_output=local_output,
                    output_schema=output_schema,
                )
            except (AITimeoutError, AIUnavailableError, AIError) as err:
                # Graceful degradation in advisory mode: preserve original output without crashing
                return VerificationOutcome(
                    effective_output=local_output,
                    result=None,
                    mode=VerificationMode.ADVISORY,
                    verification_performed=False,
                    corrected_by_verifier=False,
                    requires_human_review=True,
                    warning=f"Verification provider unavailable ({type(err).__name__}): {err}",
                )

            # Process verdict in advisory mode
            if result.verdict == VerificationVerdict.PASS:
                return VerificationOutcome(
                    effective_output=local_output,
                    result=result,
                    mode=VerificationMode.ADVISORY,
                    verification_performed=True,
                    corrected_by_verifier=False,
                    requires_human_review=False,
                )

            if result.verdict == VerificationVerdict.CORRECTED:
                validated_correction = self._validate_correction(
                    result.corrected_output,
                    output_schema,
                )
                return VerificationOutcome(
                    effective_output=validated_correction,
                    result=result,
                    mode=VerificationMode.ADVISORY,
                    verification_performed=True,
                    corrected_by_verifier=True,
                    requires_human_review=True,
                    warning="Verifier supplied a correction; downstream deterministic validation and/or human review is required before trust.",
                )

            if result.verdict == VerificationVerdict.REJECT:
                # ADVISORY + REJECT: preserve original output, do NOT crash, but clearly indicate REJECT
                issue_summary = "; ".join(f"[{i.code}] {i.message}" for i in result.issues) or "Fidelity verification rejected output."
                return VerificationOutcome(
                    effective_output=local_output,
                    result=result,
                    mode=VerificationMode.ADVISORY,
                    verification_performed=True,
                    corrected_by_verifier=False,
                    requires_human_review=True,
                    warning=f"Verification rejected output: {issue_summary}",
                )

        # ======================================================================
        # 3. REQUIRED MODE
        # ======================================================================
        if self.mode == VerificationMode.REQUIRED:
            try:
                result = self._provider.verify(
                    task_type=task_type,
                    authoritative_input=authoritative_input,
                    local_output=local_output,
                    output_schema=output_schema,
                )
            except (AITimeoutError, AIUnavailableError, AIError) as err:
                raise AIVerificationError(
                    f"Required verification failed due to provider unavailability: {err}"
                ) from err

            if result.verdict == VerificationVerdict.PASS:
                return VerificationOutcome(
                    effective_output=local_output,
                    result=result,
                    mode=VerificationMode.REQUIRED,
                    verification_performed=True,
                    corrected_by_verifier=False,
                    requires_human_review=False,
                )

            if result.verdict == VerificationVerdict.CORRECTED:
                validated_correction = self._validate_correction(
                    result.corrected_output,
                    output_schema,
                )
                return VerificationOutcome(
                    effective_output=validated_correction,
                    result=result,
                    mode=VerificationMode.REQUIRED,
                    verification_performed=True,
                    corrected_by_verifier=True,
                    requires_human_review=True,
                    warning="Verifier supplied a correction; downstream deterministic validation and/or human review is required before trust.",
                )

            if result.verdict == VerificationVerdict.REJECT:
                issue_summary = "; ".join(i.message for i in result.issues) or "Output rejected without valid correction."
                raise AIVerificationError(
                    f"Verification rejected output in REQUIRED mode: {issue_summary}"
                )

        raise AIVerificationError(f"Unsupported verification mode: {self.mode}")

    def _validate_correction(
        self,
        corrected_output: Any,
        output_schema: type[BaseModel] | None,
    ) -> Any:
        """Mandatory re-validation of proposed corrections against schema."""
        if corrected_output is None:
            raise AIInvalidOutputError("Verifier returned CORRECTED verdict but corrected_output was null.")

        if output_schema is None:
            return corrected_output

        try:
            if isinstance(corrected_output, str):
                return output_schema.model_validate_json(corrected_output)
            if isinstance(corrected_output, dict):
                return output_schema.model_validate(corrected_output)
            if isinstance(corrected_output, output_schema):
                return corrected_output
            return output_schema.model_validate(corrected_output)
        except (ValidationError, ValueError) as val_err:
            raise AIInvalidOutputError(
                f"Proposed correction failed validation against {output_schema.__name__}: {val_err}"
            ) from val_err

"""Abstract Verification Provider interface for IRIS.

This interface defines the contract for secondary AI verification providers.
The verifier checks whether an AI-generated output faithfully represents AUTHORITATIVE INPUT
supplied to it. It is not an independent decision-maker and must never alter IRIS business state.
"""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel

from app.modules.ai.schemas import VerificationResult


class BaseVerificationProvider(ABC):
    """Abstract interface for secondary output verification."""

    @abstractmethod
    def verify(
        self,
        task_type: str,
        authoritative_input: Any,
        local_output: Any,
        output_schema: type[BaseModel] | None = None,
    ) -> VerificationResult:
        """Verify that local_output faithfully represents authoritative_input.

        Args:
            task_type: Descriptive name of the verification task.
            authoritative_input: Source of truth context (str, dict, list, or BaseModel).
            local_output: Output produced by local model to be verified.
            output_schema: Optional Pydantic model for validating corrected_output.

        Returns:
            VerificationResult containing verdict, issues, and optional corrected_output.
        """
        pass

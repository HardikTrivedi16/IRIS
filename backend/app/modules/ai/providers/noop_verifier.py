"""No-Op Verification Provider for IRIS.

Used when external verification is disabled, offline, or during deterministic testing.
Performs zero network calls and clearly identifies itself in results so downstream
modules know that semantic external verification did not take place.
"""

from typing import Any
from pydantic import BaseModel

from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.schemas import VerificationResult, VerificationVerdict


class NoOpVerifier(BaseVerificationProvider):
    """Null verification provider that always passes without external network calls."""

    def __init__(self) -> None:
        self.provider_name = "noop"
        self.model_name = "none"

    def verify(
        self,
        task_type: str,
        authoritative_input: Any,
        local_output: Any,
        output_schema: type[BaseModel] | None = None,
    ) -> VerificationResult:
        """Return a predictable PASS-style verification result indicating no-op execution."""
        return VerificationResult(
            verdict=VerificationVerdict.PASS,
            issues=[],
            corrected_output=None,
            verifier_provider=self.provider_name,
            verifier_model=self.model_name,
            raw_response="NoOpVerifier executed: semantic verification bypassed.",
        )

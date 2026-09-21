"""Public facade for the IRIS AI module."""

from typing import Optional

from app.modules.ai.config import AIConfig
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.providers.groq_verifier import GroqVerifier
from app.modules.ai.providers.noop_verifier import NoOpVerifier
from app.modules.ai.providers.ollama import OllamaProvider
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.retrieval.base import BaseRetrievalIndex
from app.modules.ai.retrieval.memory import InMemoryRetrievalIndex
from app.modules.ai.schemas import VerificationMode
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.documents import DocumentAIService
from app.modules.ai.services.explanations import ExplanationService
from app.modules.ai.services.regulatory import RegulatoryAIService
from app.modules.ai.services.retrieval import RetrievalService
from app.modules.ai.services.verification import VerificationService


class IRISAI:
    """Unified facade for IRIS AI services.

    Exposes:
        ai.core:         CoreAIService
        ai.verification: VerificationService
        ai.documents:    DocumentAIService
        ai.regulatory:   RegulatoryAIService
        ai.retrieval:    RetrievalService
        ai.explanations: ExplanationService
    """

    def __init__(
        self,
        config: AIConfig | None = None,
        provider: BaseAIProvider | None = None,
        verification_provider: BaseVerificationProvider | None = None,
        retrieval_index: BaseRetrievalIndex | None = None,
    ) -> None:
        self.config = config or AIConfig()
        self.provider = provider or OllamaProvider(config=self.config)
        self.core = CoreAIService(provider=self.provider, enabled=self.config.ai_enabled)

        # Configure verification provider & mode lazily and safely
        if verification_provider is not None:
            self.verification_provider = verification_provider
        elif not self.config.verifier_enabled or self.config.verifier_provider in ("none", "noop"):
            self.verification_provider = NoOpVerifier()
        elif self.config.verifier_provider == "groq":
            self.verification_provider = GroqVerifier(config=self.config)
        else:
            self.verification_provider = NoOpVerifier()

        # Verification is active only when explicitly enabled AND backed by a real
        # configured/injected verifier. A NoOp provider must never masquerade as
        # successful semantic verification.
        verifier_active = self.config.verifier_enabled and (
            (verification_provider is not None and not isinstance(verification_provider, NoOpVerifier))
            or (verification_provider is None and self.config.verifier_provider == "groq")
        )
        mode = VerificationMode.ADVISORY if verifier_active else VerificationMode.OFF
        self.verification = VerificationService(
            provider=self.verification_provider,
            mode=mode,
            config=self.config,
        )

        # Regulatory candidate authoring is higher risk than explanatory/document
        # assistance. When an external verifier is enabled it therefore uses
        # REQUIRED verification, while other AI services remain ADVISORY.
        regulatory_mode = VerificationMode.REQUIRED if verifier_active else VerificationMode.OFF
        self.regulatory_verification = VerificationService(
            provider=self.verification_provider,
            mode=regulatory_mode,
            config=self.config,
        )

        # Phase 3 services
        self.documents = DocumentAIService(
            core=self.core,
            verification=self.verification,
            low_confidence_threshold=self.config.document_low_confidence_threshold,
        )
        self.regulatory = RegulatoryAIService(
            core=self.core,
            verification=self.regulatory_verification,
            low_confidence_threshold=self.config.rule_low_confidence_threshold,
        )

        # Phase 4 retrieval
        index = retrieval_index if retrieval_index is not None else InMemoryRetrievalIndex()
        self.retrieval = RetrievalService(
            core=self.core,
            verification=self.verification,
            index=index,
        )

        # Phase 5 explanations
        self.explanations = ExplanationService(
            core=self.core,
            verification=self.verification,
        )


_default_facade: Optional[IRISAI] = None


def get_ai(
    config: AIConfig | None = None,
    provider: BaseAIProvider | None = None,
    verification_provider: BaseVerificationProvider | None = None,
    retrieval_index: BaseRetrievalIndex | None = None,
) -> IRISAI:
    """Return the IRISAI facade.

    If custom config or providers are supplied, returns a new IRISAI instance.
    Otherwise, returns a lazily instantiated shared facade.

    Importing this module and calling get_ai() makes ZERO network calls.
    """
    global _default_facade
    if (
        config is not None
        or provider is not None
        or verification_provider is not None
        or retrieval_index is not None
    ):
        return IRISAI(
            config=config,
            provider=provider,
            verification_provider=verification_provider,
            retrieval_index=retrieval_index,
        )
    if _default_facade is None:
        _default_facade = IRISAI()
    return _default_facade


def _reset_ai_facade() -> None:
    """Internal test helper to reset the default cached facade."""
    global _default_facade
    _default_facade = None

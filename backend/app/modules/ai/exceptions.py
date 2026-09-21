"""Exceptions for the IRIS AI module.

Provider-specific implementation details and raw network exceptions (such as
requests.exceptions) must never escape through public AI service methods.
"""


class AIError(Exception):
    """Base exception for all IRIS AI module errors."""
    pass


class AIUnavailableError(AIError):
    """Raised when the AI provider service is unreachable or unavailable."""
    pass


class AITimeoutError(AIError):
    """Raised when an AI provider call times out."""
    pass


class AIInvalidOutputError(AIError):
    """Raised when AI output fails validation, cannot be parsed, or is malformed."""
    pass


class AIVerificationError(AIError):
    """Raised when required secondary verification fails or produces an unusable correction."""
    pass


class AISafetyRejectedError(AIError):
    """Raised when AI input or output is rejected by safety/policy filters."""
    pass

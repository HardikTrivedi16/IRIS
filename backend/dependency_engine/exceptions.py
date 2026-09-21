from typing import Any, List, Optional
from uuid import UUID


class DependencyEngineError(Exception):
    """Base exception for all domain errors raised by the Dependency Engine."""
    pass


class InvalidRequirementError(DependencyEngineError):
    """Raised when a requirement definition violates invariants (e.g. non-positive duration)."""
    pass


class InvalidDependencyError(DependencyEngineError):
    """Raised when a dependency definition violates invariants."""
    pass


class DuplicateRequirementError(InvalidRequirementError):
    """Raised when duplicate requirement IDs or requirement codes are supplied."""
    def __init__(self, message: str, requirement_id: Optional[UUID] = None, requirement_code: Optional[str] = None):
        super().__init__(message)
        self.requirement_id = requirement_id
        self.requirement_code = requirement_code


class DuplicateDependencyError(InvalidDependencyError):
    """Raised when duplicate dependency edges with identical endpoints are supplied."""
    def __init__(self, message: str, prerequisite_id: Optional[UUID] = None, dependent_id: Optional[UUID] = None):
        super().__init__(message)
        self.prerequisite_id = prerequisite_id
        self.dependent_id = dependent_id


class SelfDependencyError(InvalidDependencyError):
    """Raised when a requirement depends on itself (A -> A)."""
    def __init__(self, message: str, requirement_id: Optional[UUID] = None):
        super().__init__(message)
        self.requirement_id = requirement_id


class DependencyCycleError(InvalidDependencyError):
    """Raised when a circular regulatory dependency is detected."""
    def __init__(self, message: str, cycles: Optional[List[Any]] = None):
        super().__init__(message)
        self.cycles = cycles or []


class RequirementNotFoundError(DependencyEngineError):
    """Raised when querying a requirement not present in the analyzed graph."""
    def __init__(self, message: str, requirement_id: Optional[UUID] = None):
        super().__init__(message)
        self.requirement_id = requirement_id

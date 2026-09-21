"""
Three-valued (Kleene strong) logic — Phase 2 Section 10 / Phase 7 brief Section 3.

Truth tables (exactly as specified):

    AND: T&T=T  T&F=F  T&U=U  F&U=F  U&U=U
    OR:  T&T=T  T|F=T  T|U=T  F|U=U  U|U=U
    NOT: !T=F   !F=T   !U=U

UNKNOWN must never be coerced to FALSE anywhere in this module.
"""
from enum import Enum


class Kleene(Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"

    def __repr__(self):
        return self.value

    def __str__(self):
        return self.value


T = Kleene.TRUE
F = Kleene.FALSE
U = Kleene.UNKNOWN


def kleene_and(a: Kleene, b: Kleene) -> Kleene:
    if a is F or b is F:
        return F
    if a is U or b is U:
        return U
    return T


def kleene_or(a: Kleene, b: Kleene) -> Kleene:
    if a is T or b is T:
        return T
    if a is U or b is U:
        return U
    return F


def kleene_not(a: Kleene) -> Kleene:
    if a is T:
        return F
    if a is F:
        return T
    return U


_AND_TABLE = {
    (T, T): T, (T, F): F, (T, U): U,
    (F, T): F, (F, F): F, (F, U): F,
    (U, T): U, (U, F): F, (U, U): U,
}

_OR_TABLE = {
    (T, T): T, (T, F): T, (T, U): T,
    (F, T): T, (F, F): F, (F, U): U,
    (U, T): T, (U, F): U, (U, U): U,
}


def kleene_and_verified(a: Kleene, b: Kleene) -> Kleene:
    """Same as kleene_and but looked up from an explicit table (used by tests
    to cross-check the functional implementation against the literal truth
    table given in the brief)."""
    return _AND_TABLE[(a, b)]


def kleene_or_verified(a: Kleene, b: Kleene) -> Kleene:
    return _OR_TABLE[(a, b)]


assert all(kleene_and(a, b) == _AND_TABLE[(a, b)] for a in Kleene for b in Kleene)
assert all(kleene_or(a, b) == _OR_TABLE[(a, b)] for a in Kleene for b in Kleene)

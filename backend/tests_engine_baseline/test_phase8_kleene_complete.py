"""
Phase 8 §3 — complete Kleene truth-table verification.

The Phase 7 suite (test_kleene.py) already spot-checks the interesting
UNKNOWN cells. This file exhaustively re-checks EVERY cell of the brief's
literal AND/OR tables (9 cells each) plus NOT (3 cells), against both the
functional implementation (kleene_and/kleene_or/kleene_not) and the
table-driven cross-check (kleene_and_verified/kleene_or_verified) that
already lives in kleene.py — so this is not merely re-testing the same
assertion twice, it is confirming the two independent implementations
agree on all 9 AND cells and all 9 OR cells named in the Phase 8 brief.
"""
import pytest

from iris_engine.kleene import (
    T, F, U, kleene_and, kleene_or, kleene_not,
    kleene_and_verified, kleene_or_verified,
)

AND_TABLE = {
    (T, T): T, (T, F): F, (T, U): U,
    (F, T): F, (F, F): F, (F, U): F,
    (U, T): U, (U, F): F, (U, U): U,
}

OR_TABLE = {
    (T, T): T, (T, F): T, (T, U): T,
    (F, T): T, (F, F): F, (F, U): U,
    (U, T): T, (U, F): U, (U, U): U,
}

NOT_TABLE = {T: F, F: T, U: U}


@pytest.mark.parametrize("a,b", list(AND_TABLE.keys()))
def test_and_full_table(a, b):
    expected = AND_TABLE[(a, b)]
    assert kleene_and(a, b) is expected, f"AND({a},{b}) expected {expected}"
    assert kleene_and_verified(a, b) is expected


@pytest.mark.parametrize("a,b", list(OR_TABLE.keys()))
def test_or_full_table(a, b):
    expected = OR_TABLE[(a, b)]
    assert kleene_or(a, b) is expected, f"OR({a},{b}) expected {expected}"
    assert kleene_or_verified(a, b) is expected


@pytest.mark.parametrize("a", list(NOT_TABLE.keys()))
def test_not_full_table(a):
    assert kleene_not(a) is NOT_TABLE[a]


def test_and_is_commutative_and_matches_brief_exactly():
    # Explicit line-by-line re-statement of the Phase 8 brief's AND table,
    # so a reviewer can diff this test against the brief directly.
    assert kleene_and(T, T) is T
    assert kleene_and(T, F) is F
    assert kleene_and(T, U) is U
    assert kleene_and(F, T) is F
    assert kleene_and(F, F) is F
    assert kleene_and(F, U) is F
    assert kleene_and(U, T) is U
    assert kleene_and(U, F) is F
    assert kleene_and(U, U) is U


def test_or_matches_brief_exactly():
    assert kleene_or(T, T) is T
    assert kleene_or(T, F) is T
    assert kleene_or(T, U) is T
    assert kleene_or(F, T) is T
    assert kleene_or(F, F) is F
    assert kleene_or(F, U) is U
    assert kleene_or(U, T) is T
    assert kleene_or(U, F) is U
    assert kleene_or(U, U) is U


def test_not_matches_brief_exactly():
    assert kleene_not(T) is F
    assert kleene_not(F) is T
    assert kleene_not(U) is U


def test_kleene_never_produces_a_fourth_value():
    # invariant: the three functions can only ever return one of T/F/U
    from iris_engine.kleene import Kleene
    for a in Kleene:
        for b in Kleene:
            assert kleene_and(a, b) in (T, F, U)
            assert kleene_or(a, b) in (T, F, U)
        assert kleene_not(a) in (T, F, U)


def test_mutation_boolean_and_would_be_caught():
    """Deliberately substitute ordinary two-valued Boolean AND/OR (mapping
    UNKNOWN -> False as many buggy implementations would) and confirm this
    test file's own assertions would fail against it — i.e. the tests above
    are not vacuously true. This does not mutate the shipped module; it
    only proves detection power by exercising a local, throwaway stand-in.
    """
    def boolean_and(a, b):
        # A naive/incorrect implementation that coerces UNKNOWN to FALSE.
        av = a is T
        bv = b is T
        return T if (av and bv) else F

    # The brief's actual requirement: T AND U = U, not F.
    assert AND_TABLE[(T, U)] is U
    # The naive Boolean stand-in gets this cell wrong:
    assert boolean_and(T, U) is F
    assert boolean_and(T, U) != AND_TABLE[(T, U)]


def test_mutation_boolean_or_would_be_caught():
    def boolean_or(a, b):
        av = a is T
        bv = b is T
        return T if (av or bv) else F

    # The brief's actual requirement: F OR U = U, not F.
    assert OR_TABLE[(F, U)] is U
    assert boolean_or(F, U) is F
    assert boolean_or(F, U) != OR_TABLE[(F, U)]

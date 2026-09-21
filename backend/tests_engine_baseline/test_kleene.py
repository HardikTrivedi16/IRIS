from iris_engine.kleene import T, F, U, kleene_and, kleene_or, kleene_not


def test_and_true_unknown():
    assert kleene_and(T, U) is U
    assert kleene_and(U, T) is U


def test_and_false_unknown():
    assert kleene_and(F, U) is F
    assert kleene_and(U, F) is F


def test_or_true_unknown():
    assert kleene_or(T, U) is T
    assert kleene_or(U, T) is T


def test_or_false_unknown():
    assert kleene_or(F, U) is U
    assert kleene_or(U, F) is U


def test_not_unknown():
    assert kleene_not(U) is U


def test_full_and_table():
    assert kleene_and(T, T) is T
    assert kleene_and(T, F) is F
    assert kleene_and(F, F) is F
    assert kleene_and(U, U) is U


def test_full_or_table():
    assert kleene_or(T, T) is T
    assert kleene_or(T, F) is T
    assert kleene_or(F, F) is F
    assert kleene_or(U, U) is U


def test_not_table():
    assert kleene_not(T) is F
    assert kleene_not(F) is T

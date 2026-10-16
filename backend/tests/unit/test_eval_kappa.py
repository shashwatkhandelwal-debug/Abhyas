"""Tests for the coach-calibration agreement maths (spec/11 §11.4, T42)."""

import random
from typing import Any, cast

import pytest

from eval.calibration.kappa import (
    agreement,
    bootstrap_ci,
    cohen_kappa,
    confusion_matrix,
    criterion_agreement,
    exact_agreement,
    pairwise_agreement,
    render_report,
)


def _close(x: float | None, y: float, tol: float = 1e-9) -> bool:
    return x is not None and abs(x - y) <= tol


def _qwk_by_moments(a: list[int], b: list[int]) -> float:
    """Independent oracle: Fleiss & Cohen (1973) identity for quadratic-weighted kappa."""
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a) / n
    vb = sum((y - mb) ** 2 for y in b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / n
    return 2 * cov / (va + vb + (ma - mb) ** 2)


def test_textbook_two_by_two_kappa_is_0_4() -> None:
    # 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> po=0.7, pe=0.5, kappa=0.4
    a = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert _close(cohen_kappa(a, b), 0.4)
    assert _close(exact_agreement(a, b), 0.7)


def test_perfect_agreement_is_one_and_symmetric() -> None:
    a = [0, 1, 2, 2, 1, 0, 2]
    assert _close(cohen_kappa(a, a, [0, 1, 2], "quadratic"), 1.0)
    b = [0, 2, 2, 1, 1, 0, 1]
    forward = cohen_kappa(a, b, [0, 1, 2], "quadratic")
    backward = cohen_kappa(b, a, [0, 1, 2], "quadratic")
    assert forward is not None and _close(backward, forward)


def test_quadratic_kappa_matches_the_moment_identity_on_random_data() -> None:
    rng = random.Random(7)
    for _ in range(25):
        a = [rng.choice([0, 1, 2]) for _ in range(40)]
        b = [x if rng.random() < 0.6 else rng.choice([0, 1, 2]) for x in a]
        got = cohen_kappa(a, b, [0, 1, 2], "quadratic")
        assert _close(got, _qwk_by_moments(a, b), 1e-9)


def test_quadratic_penalises_far_disagreement_more_than_near() -> None:
    truth = [0, 0, 1, 1, 2, 2, 0, 2]
    near = [1, 0, 1, 2, 2, 1, 0, 2]  # off by one
    far = [2, 0, 1, 0, 2, 0, 0, 2]  # off by two
    labels = [0, 1, 2]
    unweighted_gap = (cohen_kappa(truth, near, labels) or 0) - (
        cohen_kappa(truth, far, labels) or 0
    )
    weighted_gap = (cohen_kappa(truth, near, labels, "quadratic") or 0) - (
        cohen_kappa(truth, far, labels, "quadratic") or 0
    )
    assert weighted_gap > unweighted_gap


def test_matches_scikit_learn_when_installed() -> None:
    sklearn_metrics = pytest.importorskip("sklearn.metrics")
    rng = random.Random(3)
    a = [rng.choice([0, 1, 2]) for _ in range(60)]
    b = [x if rng.random() < 0.7 else rng.choice([0, 1, 2]) for x in a]
    assert _close(cohen_kappa(a, b, [0, 1, 2]), sklearn_metrics.cohen_kappa_score(a, b))
    assert _close(
        cohen_kappa(a, b, [0, 1, 2], "quadratic"),
        sklearn_metrics.cohen_kappa_score(a, b, weights="quadratic"),
    )


def test_undefined_when_no_variation() -> None:
    assert cohen_kappa([1, 1, 1], [1, 1, 1], [0, 1, 2]) is None
    assert cohen_kappa([1, 1, 1], [1, 1, 1], [0, 1, 2], "quadratic") is None


def test_bad_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        cohen_kappa([1, 2], [1])
    with pytest.raises(ValueError):
        cohen_kappa([], [])
    with pytest.raises(ValueError):
        confusion_matrix([0, 3], [0, 1], [0, 1, 2])
    with pytest.raises(ValueError):
        cohen_kappa([0, 1], [0, 1], [0, 1], cast(Any, "linear"))


def test_confusion_matrix_counts_and_orientation() -> None:
    m = confusion_matrix([0, 0, 1, 2], [0, 1, 1, 0], [0, 1, 2])
    assert m == [[1, 1, 0], [0, 1, 0], [1, 0, 0]]
    assert sum(sum(r) for r in m) == 4


def test_bootstrap_is_deterministic_and_brackets_the_estimate() -> None:
    rng = random.Random(11)
    a = [rng.choice([0, 1, 2]) for _ in range(80)]
    b = [x if rng.random() < 0.7 else rng.choice([0, 1, 2]) for x in a]
    first = bootstrap_ci(a, b, [0, 1, 2], "quadratic", n_boot=500, seed=1)
    again = bootstrap_ci(a, b, [0, 1, 2], "quadratic", n_boot=500, seed=1)
    assert first is not None and first == again
    point = cohen_kappa(a, b, [0, 1, 2], "quadratic")
    assert point is not None and first[0] <= point <= first[1]


def test_bootstrap_gives_none_when_kappa_is_mostly_undefined() -> None:
    assert bootstrap_ci([1, 1, 1], [1, 1, 1], [0, 1, 2], n_boot=200) is None


def test_pairwise_uses_only_shared_items_and_all_pairs() -> None:
    ratings = {
        "ai": {"s1": 0, "s2": 1, "s3": 2, "s4": 2},
        "coach_a": {"s1": 0, "s2": 1, "s3": 1},
        "coach_b": {"s2": 1, "s3": 2, "s4": 2},
    }
    out = pairwise_agreement(ratings, [0, 1, 2], "quadratic", n_boot=50)
    assert set(out) == {("ai", "coach_a"), ("ai", "coach_b"), ("coach_a", "coach_b")}
    assert out[("ai", "coach_a")].n == 3
    assert out[("coach_a", "coach_b")].n == 2


def test_criterion_agreement_splits_by_criterion() -> None:
    ratings = {
        "ai": {"s1": {"c1": 2, "c2": 0}, "s2": {"c1": 1, "c2": 1}, "s3": {"c1": 0, "c2": 2}},
        "coach": {"s1": {"c1": 2, "c2": 1}, "s2": {"c1": 1, "c2": 1}, "s3": {"c1": 0, "c2": 2}},
    }
    out = criterion_agreement(ratings, [0, 1, 2], "quadratic", n_boot=50)
    assert set(out) == {"c1", "c2"}
    assert _close(out["c1"][("ai", "coach")].kappa, 1.0)
    kappa_c2 = out["c2"][("ai", "coach")].kappa
    assert kappa_c2 is not None and kappa_c2 < 1.0


def test_report_is_honest_about_small_n_and_low_kappa() -> None:
    a = [0, 1, 2, 0, 1, 2]
    b = [2, 1, 0, 1, 1, 0]
    ratings = {
        "ai": {str(i): v for i, v in enumerate(a)},
        "coach": {str(i): v for i, v in enumerate(b)},
    }
    results = {"c1": pairwise_agreement(ratings, [0, 1, 2], "quadratic", n_boot=50)}
    report = render_report("Rehearsal rubric agreement", results)
    assert "n=6 is below the target of 20" in report
    assert "below the 0.70 target" in report
    assert "Confusion matrices" in report


def test_report_with_strong_agreement_has_no_warnings_other_than_n() -> None:
    items = {str(i): i % 3 for i in range(30)}
    res = agreement(list(items.values()), list(items.values()), [0, 1, 2], "quadratic", n_boot=50)
    report = render_report("t", {"c1": {("ai", "coach"): res}})
    assert "- None." in report
    assert "| c1 | ai vs coach | 30 | 1.00 |" in report

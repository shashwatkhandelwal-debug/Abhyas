"""Evaluation script for AI coach calibration against expert coaches (§5.3, §15).

Target: Cohen's kappa >= 0.70 across double-coded rehearsal scores.
"""

from collections.abc import Sequence


def compute_cohens_kappa(rater1: Sequence[int], rater2: Sequence[int]) -> float:
    """Computes unweighted Cohen's Kappa between two raters."""
    assert len(rater1) == len(rater2), "Rater sequences must be of equal length"
    n = len(rater1)
    if n == 0:
        return 0.0

    categories = sorted(set(rater1).union(set(rater2)))
    observed_agreement = sum(1 for a, b in zip(rater1, rater2, strict=True) if a == b) / n

    expected_agreement = 0.0
    for cat in categories:
        p1 = sum(1 for x in rater1 if x == cat) / n
        p2 = sum(1 for x in rater2 if x == cat) / n
        expected_agreement += p1 * p2

    if expected_agreement == 1.0:
        return 1.0

    kappa = (observed_agreement - expected_agreement) / (1.0 - expected_agreement)
    return round(kappa, 4)


if __name__ == "__main__":
    # Benchmark example: 20 sample rehearsals double-coded (0, 1, 2)
    ai_scores = [2, 1, 2, 0, 1, 2, 2, 1, 0, 2, 2, 1, 2, 0, 1, 2, 2, 1, 0, 2]
    human_coach_scores = [2, 1, 2, 0, 1, 2, 1, 1, 0, 2, 2, 1, 2, 0, 1, 2, 2, 2, 0, 2]

    kappa = compute_cohens_kappa(ai_scores, human_coach_scores)
    print(f"Calibration Result - Cohen's Kappa: {kappa}")
    print(f"Target >= 0.70: {'PASSED' if kappa >= 0.70 else 'FAILED'}")
